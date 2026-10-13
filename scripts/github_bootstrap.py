"""Retrieve non-secret Dev bindings through the authenticated GitHub CLI.

Only the registered, reviewed Dev bootstrap workflow is eligible. This module
never authenticates to Azure/Fabric, reads application credentials, imports
bindings into source, or changes the checked-out branch. Git updates only the
explicit origin/dev remote-tracking reference; artifact downloads use a scoped,
automatically cleaned directory inside the checkout.
"""

from __future__ import annotations

import json
import math
import re
import secrets
import stat
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory
from urllib.parse import urlsplit

from bootstrap_dev_connections import (
    BOOTSTRAP_ARTIFACT,
    BOOTSTRAP_FILENAME,
    BOOTSTRAP_WORKFLOW,
    BootstrapArtifact,
    BootstrapMetadataError,
    parse_bootstrap_artifact,
)
from fabric_connections import FabricConnectionError

COMMAND_TIMEOUT_SECONDS = 60.0
POLL_INTERVAL_SECONDS = 5.0
MAX_DISCOVERY_PAGES = 5
PAGE_SIZE = 100
MAX_ARTIFACT_BYTES = 64 * 1024
DEV_REF = "refs/heads/dev"
DEV_TRACKING_REF = "refs/remotes/origin/dev"
ALLOWED_EVENTS = frozenset({"push", "workflow_dispatch"})
PENDING_STATUSES = frozenset({"pending", "queued", "requested", "in_progress"})
CONCLUSIONS = frozenset({
    "success", "failure", "cancelled", "timed_out", "action_required",
    "neutral", "skipped", "stale", "startup_failure",
})
_RUN_ID = re.compile(r"[1-9][0-9]{0,19}")
_COMMIT = re.compile(r"[0-9a-f]{40}")
_REPOSITORY = re.compile(
    r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?/[A-Za-z0-9_.-]{1,100}"
)
_SCP_REMOTE = re.compile(r"git@(?i:github\.com):(.+)")


class GitHubBootstrapError(BootstrapMetadataError):
    """The approved GitHub bootstrap could not be retrieved safely."""


@dataclass(frozen=True)
class _Run:
    repository: str
    run_id: str
    attempt: int
    sha: str
    event: str
    status: str
    conclusion: str | None


def _location(run_url: str | None) -> str:
    return f" Inspect {run_url}." if run_url else ""


def _remaining(deadline: float, stage: str, run_url: str | None = None) -> float:
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise GitHubBootstrapError(f"Timed out while {stage}.{_location(run_url)}")
    return remaining


def _command(
    args: list[str], root: Path, deadline: float, stage: str,
    run_url: str | None = None,
) -> str:
    timeout = min(COMMAND_TIMEOUT_SECONDS, _remaining(deadline, stage, run_url))
    try:
        result = subprocess.run(
            args, cwd=root, check=True, capture_output=True, text=True,
            encoding="utf-8", timeout=timeout,
        )
    except FileNotFoundError:
        if args[0] == "gh":
            raise GitHubBootstrapError(
                "GitHub CLI (gh) is required. Install it and authenticate your intended "
                "human account with gh auth login --hostname github.com before retrying."
            ) from None
        raise GitHubBootstrapError("Git is required to verify this checkout.") from None
    except subprocess.TimeoutExpired:
        raise GitHubBootstrapError(f"Timed out while {stage}.{_location(run_url)}") from None
    except subprocess.CalledProcessError:
        guidance = (
            " Verify access using your intended human GitHub account; if necessary, "
            "run gh auth login --hostname github.com separately. "
            "Do not supply local application secrets."
            if args[0] == "gh" else ""
        )
        raise GitHubBootstrapError(
            f"Failed while {stage}.{_location(run_url)}{guidance}"
        ) from None
    except (OSError, UnicodeError):
        raise GitHubBootstrapError(
            f"Could not execute the command safely while {stage}.{_location(run_url)}"
        ) from None
    _remaining(deadline, stage, run_url)
    return result.stdout


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON fields are not accepted.")
        result[key] = value
    return result


def _gh_json(
    endpoint: str, root: Path, deadline: float, stage: str,
    run_url: str | None = None,
) -> dict[str, object]:
    output = _command(
        ["gh", "api", "--hostname", "github.com", "--method", "GET", endpoint],
        root, deadline, stage, run_url,
    )
    try:
        document: object = json.loads(output, object_pairs_hook=_unique_object)
    except (ValueError, UnicodeError, RecursionError):
        raise GitHubBootstrapError(
            f"GitHub returned invalid JSON while {stage}.{_location(run_url)}"
        ) from None
    if not isinstance(document, dict):
        raise GitHubBootstrapError(
            f"GitHub must return a JSON object while {stage}.{_location(run_url)}"
        )
    return document


def _objects(document: dict[str, object], key: str) -> list[dict[str, object]]:
    values = document.get(key)
    if not isinstance(values, list) or len(values) > PAGE_SIZE:
        raise GitHubBootstrapError(f"GitHub response must contain a {key} array.")
    result: list[dict[str, object]] = []
    for value in values:
        if not isinstance(value, dict):
            raise GitHubBootstrapError(f"GitHub {key} entries must be JSON objects.")
        result.append(value)
    return result


def _api_id(value: object, label: str, run_url: str | None = None) -> str:
    if type(value) is not int or not 0 < value < 10**20:
        raise GitHubBootstrapError(
            f"GitHub {label} must be a positive integer.{_location(run_url)}"
        )
    return str(value)


def _repository_from_origin(remote: str) -> str:
    problem = (
        "origin must be a standard github.com HTTPS or SSH owner/repository URL "
        "without embedded HTTPS credentials."
    )
    if not remote or any(ord(char) <= 32 or ord(char) == 127 for char in remote):
        raise GitHubBootstrapError(problem)
    scp = _SCP_REMOTE.fullmatch(remote)
    if scp:
        repository = scp.group(1)
    else:
        try:
            parsed = urlsplit(remote)
            if (
                parsed.hostname is None or parsed.hostname.lower() != "github.com"
                or parsed.query or parsed.fragment
            ):
                raise GitHubBootstrapError(problem)
            if parsed.scheme == "https":
                if parsed.username is not None or parsed.password is not None or parsed.port not in {None, 443}:
                    raise GitHubBootstrapError(problem)
            elif parsed.scheme == "ssh":
                if parsed.username != "git" or parsed.password is not None or parsed.port not in {None, 22}:
                    raise GitHubBootstrapError(problem)
            else:
                raise GitHubBootstrapError(problem)
            if not parsed.path.startswith("/"):
                raise GitHubBootstrapError(problem)
            repository = parsed.path[1:]
        except ValueError:
            raise GitHubBootstrapError(problem) from None
    if repository.endswith(".git"):
        repository = repository[:-4]
    if (
        _REPOSITORY.fullmatch(repository) is None
        or repository.split("/")[-1] in {".", ".."}
    ):
        raise GitHubBootstrapError(problem)
    return repository


def _checkout_root(git_root: Path, deadline: float) -> Path:
    try:
        root = git_root.resolve(strict=True)
        if not root.is_dir():
            raise GitHubBootstrapError("git_root must be the existing checkout root directory.")
    except (OSError, RuntimeError):
        raise GitHubBootstrapError("git_root must be the existing checkout root directory.") from None
    reported = _command(
        ["git", "rev-parse", "--show-toplevel"], root, deadline, "verifying the checkout root",
    ).rstrip("\r\n")
    if not reported or not Path(reported).is_absolute() or any(ord(char) < 32 for char in reported):
        raise GitHubBootstrapError("Git did not report a valid absolute checkout root.")
    try:
        matches = Path(reported).resolve(strict=True) == root
    except (OSError, RuntimeError, ValueError):
        matches = False
    if not matches:
        raise GitHubBootstrapError("git_root must be the checkout root, not a subdirectory or another checkout.")
    return root


def _fetch_dev(root: Path, deadline: float) -> str:
    _command(
        [
            "git", "fetch", "--no-tags", "--no-recurse-submodules", "--no-write-fetch-head",
            "origin", f"{DEV_REF}:{DEV_TRACKING_REF}",
        ],
        root, deadline,
        "fetching approved origin/dev (the reviewed dev branch must exist; no forced updates are allowed)",
    )
    sha = _command(
        ["git", "rev-parse", "--verify", f"{DEV_TRACKING_REF}^{{commit}}"],
        root, deadline, "verifying the fetched approved origin/dev commit",
    ).rstrip("\r\n")
    if _COMMIT.fullmatch(sha) is None:
        raise GitHubBootstrapError("The fetched approved origin/dev commit is invalid.")
    return sha


def _workflow_id(repository: str, root: Path, deadline: float) -> str:
    for page in range(1, MAX_DISCOVERY_PAGES + 1):
        document = _gh_json(
            f"repos/{repository}/actions/workflows?per_page={PAGE_SIZE}&page={page}",
            root, deadline, "discovering the registered Dev bootstrap workflow",
        )
        workflows = _objects(document, "workflows")
        matches = [workflow for workflow in workflows if workflow.get("path") == BOOTSTRAP_WORKFLOW]
        if len(matches) > 1:
            raise GitHubBootstrapError("The exact Dev bootstrap workflow registration is ambiguous.")
        if matches:
            workflow = matches[0]
            workflow_id = _api_id(workflow.get("id"), "workflow ID")
            if workflow.get("state") != "active":
                raise GitHubBootstrapError(
                    "The registered Dev bootstrap workflow is not active. Review/merge the "
                    "bootstrap-only infrastructure PR and enable its approved workflow in GitHub."
                )
            return workflow_id
        if len(workflows) < PAGE_SIZE:
            break
    raise GitHubBootstrapError(
        f"{BOOTSTRAP_WORKFLOW} is not registered within the bounded workflow lookup. "
        "First review and merge the bootstrap-only infrastructure PR into dev and allow "
        "its approved push run. GitHub may require workflow registration on the default "
        "branch. Do not run feature/PR code with Environment secrets or supply local SP credentials."
    )


def _discover_run(
    repository: str, workflow_id: str, root: Path, deadline: float,
    expected_title: str | None = None,
) -> str | None:
    for page in range(1, MAX_DISCOVERY_PAGES + 1):
        document = _gh_json(
            f"repos/{repository}/actions/workflows/{workflow_id}/runs"
            f"?branch=dev&per_page={PAGE_SIZE}&page={page}",
            root, deadline, "discovering Dev bootstrap runs",
        )
        runs = _objects(document, "workflow_runs")
        matches: list[str] = []
        for run in runs:
            event = run.get("event")
            if not isinstance(event, str):
                raise GitHubBootstrapError("GitHub bootstrap run event must be a string.")
            if run.get("head_branch") != "dev" or event not in ALLOWED_EVENTS:
                continue
            if expected_title is not None and (
                run.get("display_title") != expected_title
                or run.get("event") != "workflow_dispatch"
                or run.get("path") != BOOTSTRAP_WORKFLOW
                or type(run.get("workflow_id")) is not int
                or run.get("workflow_id") != int(workflow_id)
            ):
                continue
            matches.append(_api_id(run.get("id"), "run ID"))
            if expected_title is None:
                # GitHub lists newest first, including failed and waiting runs.
                return matches[0]
        if len(matches) > 1:
            raise GitHubBootstrapError("The dispatched Dev bootstrap run correlation is ambiguous.")
        if matches:
            return matches[0]
        if len(runs) < PAGE_SIZE:
            return None
    raise GitHubBootstrapError(
        "Dev bootstrap run discovery exceeded its bounded history. Select an explicit "
        "reviewed Dev run ID instead of dispatching another run."
    )


def _validate_run(
    document: dict[str, object], run_id: str, repository: str, workflow_id: str,
    run_url: str, expected_title: str | None,
) -> _Run:
    if _api_id(document.get("id"), "run ID", run_url) != run_id:
        raise GitHubBootstrapError(f"GitHub returned a different run ID.{_location(run_url)}")
    run_repository = document.get("repository")
    full_name = run_repository.get("full_name") if isinstance(run_repository, dict) else None
    if (
        not isinstance(full_name, str) or _REPOSITORY.fullmatch(full_name) is None
        or full_name.casefold() != repository.casefold()
    ):
        raise GitHubBootstrapError(f"Bootstrap run repository does not match origin.{_location(run_url)}")
    if (
        _api_id(document.get("workflow_id"), "workflow ID", run_url) != workflow_id
        or document.get("path") != BOOTSTRAP_WORKFLOW
    ):
        raise GitHubBootstrapError(f"Bootstrap run workflow does not match the approved path.{_location(run_url)}")
    if document.get("head_branch") != "dev":
        raise GitHubBootstrapError(f"Bootstrap run branch must be dev.{_location(run_url)}")
    event = document.get("event")
    if not isinstance(event, str) or event not in ALLOWED_EVENTS:
        raise GitHubBootstrapError(f"Bootstrap run event must be push or workflow_dispatch.{_location(run_url)}")
    title = document.get("display_title")
    if not isinstance(title, str) or not title:
        raise GitHubBootstrapError(f"Bootstrap run display title is invalid.{_location(run_url)}")
    if expected_title is not None and (title != expected_title or event != "workflow_dispatch"):
        raise GitHubBootstrapError(f"Bootstrap run does not match the exact dispatch request.{_location(run_url)}")
    sha = document.get("head_sha")
    if not isinstance(sha, str) or _COMMIT.fullmatch(sha) is None:
        raise GitHubBootstrapError(f"Bootstrap run source commit is invalid.{_location(run_url)}")
    attempt = document.get("run_attempt")
    if type(attempt) is not int or attempt < 1:
        raise GitHubBootstrapError(f"Bootstrap run attempt must be a positive integer.{_location(run_url)}")
    status = document.get("status")
    if not isinstance(status, str) or status not in PENDING_STATUSES | {"waiting", "completed"}:
        raise GitHubBootstrapError(f"Bootstrap run status is invalid.{_location(run_url)}")
    conclusion = document.get("conclusion")
    if status == "completed":
        if not isinstance(conclusion, str) or conclusion not in CONCLUSIONS:
            raise GitHubBootstrapError(f"Bootstrap run conclusion is invalid.{_location(run_url)}")
    elif conclusion is not None:
        raise GitHubBootstrapError(f"An unfinished bootstrap run cannot have a conclusion.{_location(run_url)}")
    return _Run(full_name, run_id, attempt, sha, event, status, conclusion)


def _wait_for_run(
    repository: str, workflow_id: str, run_id: str, root: Path, deadline: float,
    expected_title: str | None,
) -> _Run:
    run_url = f"https://github.com/{repository}/actions/runs/{run_id}"
    while True:
        document = _gh_json(
            f"repos/{repository}/actions/runs/{run_id}", root, deadline,
            "waiting for the Dev bootstrap run", run_url,
        )
        run = _validate_run(document, run_id, repository, workflow_id, run_url, expected_title)
        if run.status == "waiting":
            raise GitHubBootstrapError(
                "Dev bootstrap is waiting for GitHub Environment approval or another GitHub gate."
                f"{_location(run_url)} Approve only the reviewed Dev run in GitHub, then retry "
                "with its run ID. No automatic approval is attempted."
            )
        if run.status == "completed":
            if run.conclusion != "success":
                raise GitHubBootstrapError(
                    f"Dev bootstrap did not succeed ({run.conclusion}).{_location(run_url)} "
                    "Resolve the reviewed run's failure before retrying; no older success is substituted."
                )
            return run
        time.sleep(min(POLL_INTERVAL_SECONDS, _remaining(deadline, "waiting for the Dev bootstrap run", run_url)))


def _ensure_ancestor(run: _Run, approved_sha: str, root: Path, deadline: float, run_url: str) -> None:
    timeout = min(COMMAND_TIMEOUT_SECONDS, _remaining(deadline, "verifying Dev source ancestry", run_url))
    try:
        subprocess.run(
            ["git", "merge-base", "--is-ancestor", run.sha, approved_sha],
            cwd=root, check=True, capture_output=True, text=True, encoding="utf-8", timeout=timeout,
        )
    except subprocess.CalledProcessError as exc:
        if exc.returncode == 1:
            raise GitHubBootstrapError(
                f"Bootstrap source commit is not an ancestor of fetched approved origin/dev.{_location(run_url)} "
                "Refresh approved Dev history and retry this run ID; untrusted feature commits are not accepted."
            ) from None
        raise GitHubBootstrapError(
            f"Could not verify Dev source ancestry.{_location(run_url)} "
            "Ensure approved Dev history, including older commits in a shallow checkout, is available."
        ) from None
    except subprocess.TimeoutExpired:
        raise GitHubBootstrapError(f"Timed out verifying Dev source ancestry.{_location(run_url)}") from None
    except (OSError, UnicodeError):
        raise GitHubBootstrapError(f"Could not verify Dev source ancestry safely.{_location(run_url)}") from None
    _remaining(deadline, "verifying Dev source ancestry", run_url)


def _read_artifact(download: Path, expected_directory: Path, run_url: str) -> BootstrapArtifact:
    path = download / BOOTSTRAP_FILENAME
    try:
        if download.is_symlink() or download.resolve(strict=True) != expected_directory:
            raise GitHubBootstrapError(f"Bootstrap artifact directory escapes the scoped download.{_location(run_url)}")
        info = path.lstat()
        if not stat.S_ISREG(info.st_mode) or path.is_symlink():
            raise GitHubBootstrapError(f"Bootstrap artifact must be a regular, non-symlink file.{_location(run_url)}")
        if path.resolve(strict=True).parent != expected_directory:
            raise GitHubBootstrapError(f"Bootstrap artifact path escapes the scoped download.{_location(run_url)}")
        if info.st_size > MAX_ARTIFACT_BYTES:
            raise GitHubBootstrapError(f"Bootstrap artifact exceeds the 64 KiB limit.{_location(run_url)}")
        with path.open("rb") as stream:
            content = stream.read(MAX_ARTIFACT_BYTES + 1)
    except (OSError, RuntimeError):
        raise GitHubBootstrapError(
            f"Bootstrap artifact is missing or cannot be read safely.{_location(run_url)}"
        ) from None
    if len(content) > MAX_ARTIFACT_BYTES:
        raise GitHubBootstrapError(f"Bootstrap artifact exceeds the 64 KiB limit.{_location(run_url)}")
    try:
        document: object = json.loads(content.decode("utf-8"), object_pairs_hook=_unique_object)
    except (ValueError, UnicodeError, RecursionError):
        raise GitHubBootstrapError(f"Bootstrap artifact must be valid UTF-8 JSON.{_location(run_url)}") from None
    try:
        return parse_bootstrap_artifact(document)
    except (BootstrapMetadataError, FabricConnectionError):
        raise GitHubBootstrapError(f"Bootstrap artifact schema or bindings are invalid.{_location(run_url)}") from None


def get_bootstrap_artifact(
    git_root: Path, *, run_id: str | None = None, timeout_seconds: float = 1200,
) -> BootstrapArtifact:
    """Return validated metadata, reusing the latest eligible Dev run when possible.

    An explicit run ID never falls back to another run. Without one, a dispatch
    occurs only when bounded discovery proves there are no eligible prior runs.
    Callers must separately check the expected Dev workspace/model and decide
    whether to record bindings; this function does not read or rewrite source.
    """
    if run_id is not None and (not isinstance(run_id, str) or _RUN_ID.fullmatch(run_id) is None):
        raise GitHubBootstrapError("Bootstrap run_id must be a positive decimal GitHub run ID.")
    try:
        valid_timeout = (
            type(timeout_seconds) in {int, float}
            and math.isfinite(timeout_seconds) and timeout_seconds > 0
        )
    except OverflowError:
        valid_timeout = False
    if not valid_timeout:
        raise GitHubBootstrapError("timeout_seconds must be a positive, finite number.")
    deadline = time.monotonic() + timeout_seconds
    root = _checkout_root(git_root, deadline)
    remote = _command(
        ["git", "remote", "get-url", "origin"], root, deadline, "reading the GitHub origin",
    ).rstrip("\r\n")
    repository = _repository_from_origin(remote)
    _command(
        ["gh", "auth", "status", "--hostname", "github.com"], root, deadline,
        "checking existing GitHub CLI human authentication",
    )
    approved_sha = _fetch_dev(root, deadline)
    workflow_id = _workflow_id(repository, root, deadline)
    expected_title: str | None = None
    selected_id = run_id or _discover_run(repository, workflow_id, root, deadline)
    if selected_id is None:
        nonce = secrets.token_hex(16)
        expected_title = f"Bootstrap Dev Connections {nonce}"
        workflow_url = f"https://github.com/{repository}/actions/workflows/{BOOTSTRAP_WORKFLOW.rsplit('/', 1)[-1]}"
        _command(
            [
                "gh", "workflow", "run", workflow_id, "--repo", f"github.com/{repository}", "--ref", "dev",
                "--raw-field", f"request_id={nonce}",
            ],
            root, deadline,
            "dispatching the approved Dev bootstrap once (inspect existing runs before retrying a dispatch error)",
            workflow_url,
        )
        while selected_id is None:
            _remaining(deadline, "correlating the dispatched Dev bootstrap; inspect runs before redispatching", workflow_url)
            selected_id = _discover_run(repository, workflow_id, root, deadline, expected_title)
            if selected_id is None:
                time.sleep(min(
                    POLL_INTERVAL_SECONDS,
                    _remaining(deadline, "correlating the dispatched Dev bootstrap; inspect runs before redispatching", workflow_url),
                ))
    run = _wait_for_run(repository, workflow_id, selected_id, root, deadline, expected_title)
    run_url = f"https://github.com/{repository}/actions/runs/{selected_id}"
    _ensure_ancestor(run, approved_sha, root, deadline, run_url)
    try:
        with TemporaryDirectory(prefix=".fabric-dev-bootstrap-", dir=root) as folder:
            download = Path(folder) / "artifact"
            download.mkdir()
            expected_directory = download.resolve(strict=True)
            _command(
                [
                    "gh", "run", "download", selected_id, "--repo", f"github.com/{repository}",
                    "--name", BOOTSTRAP_ARTIFACT, "--dir", str(download),
                ],
                root, deadline,
                "downloading the Dev bootstrap artifact (missing or expired output requires an approved Dev rerun)",
                run_url,
            )
            artifact = _read_artifact(download, expected_directory, run_url)
            provenance = artifact.provenance
            if (
                provenance.repository != run.repository or provenance.run_id != run.run_id
                or provenance.run_attempt != run.attempt or provenance.head_sha != run.sha
                or provenance.ref != DEV_REF or provenance.event != run.event
            ):
                raise GitHubBootstrapError(
                    f"Bootstrap artifact provenance does not match the authenticated Dev run.{_location(run_url)}"
                )
            _remaining(deadline, "validating the Dev bootstrap artifact", run_url)
            return artifact
    except OSError:
        raise GitHubBootstrapError(
            f"Could not create, read, or clean the scoped bootstrap download.{_location(run_url)}"
        ) from None
