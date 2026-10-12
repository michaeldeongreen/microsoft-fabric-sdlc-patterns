"""Hermetic GitHub bootstrap transport tests; no git, gh, or network executes."""

from __future__ import annotations

import json
import os
import socket
import subprocess
import traceback
import urllib.request
from collections.abc import Callable, Iterator, MutableMapping
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import IO
from unittest.mock import Mock

import pytest

import bootstrap_dev_connections as producer
import fabric_connections as fabric
import github_bootstrap as bootstrap

PROJECT_ROOT = Path(__file__).resolve().parents[1]
REPOSITORY = "michaeldeongreen/microsoft-fabric-sdlc-patterns"
WORKFLOW_ID = 2468
RUN_ID = "12345"
RUN_URL = f"https://github.com/{REPOSITORY}/actions/runs/{RUN_ID}"
WORKFLOW_URL = f"https://github.com/{REPOSITORY}/actions/workflows/bootstrap-dev.yml"
APPROVED_SHA = "a" * 40
RUN_SHA = "b" * 40
NONCE = "0123456789abcdef" * 2
TITLE = f"Bootstrap Dev Connections {NONCE}"
WORKSPACE = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
MODEL = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"
NOTEBOOK = "cccccccc-cccc-4ccc-8ccc-cccccccccccc"
REFRESH = "dddddddd-dddd-4ddd-8ddd-dddddddddddd"
BODY_SECRET = "offline-provider-body-must-not-appear"
TOKEN_SECRET = "offline-token-must-not-appear"
WORKFLOWS_ENDPOINT = f"repos/{REPOSITORY}/actions/workflows?per_page=100&page=1"
RUNS_ENDPOINT = (
    f"repos/{REPOSITORY}/actions/workflows/{WORKFLOW_ID}/runs?branch=dev&per_page=100&page=1"
)
RUN_ENDPOINT = f"repos/{REPOSITORY}/actions/runs/{RUN_ID}"


def run_document(**changes: object) -> dict[str, object]:
    document: dict[str, object] = {
        "id": int(RUN_ID),
        "repository": {"full_name": REPOSITORY},
        "path": producer.BOOTSTRAP_WORKFLOW,
        "workflow_id": WORKFLOW_ID,
        "run_attempt": 1,
        "head_sha": RUN_SHA,
        "head_branch": "dev",
        "event": "push",
        "status": "completed",
        "conclusion": "success",
        "display_title": f"Bootstrap Dev Connections {RUN_ID}",
    }
    document.update(changes)
    return document


def artifact_document(**provenance_changes: object) -> dict[str, object]:
    provenance: dict[str, object] = {
        "repository": REPOSITORY,
        "workflowPath": producer.BOOTSTRAP_WORKFLOW,
        "runId": RUN_ID,
        "runAttempt": 1,
        "headSha": RUN_SHA,
        "ref": "refs/heads/dev",
        "event": "push",
        "semanticModelName": producer.DEFAULT_MODEL_NAME,
    }
    provenance.update(provenance_changes)
    return {
        "schemaVersion": 1,
        "bindings": {
            "schemaVersion": 1,
            "workspaceId": WORKSPACE,
            "semanticModelId": MODEL,
            "notebookConnectionId": NOTEBOOK,
            "semanticModelRefreshConnectionId": REFRESH,
        },
        "provenance": provenance,
    }


class Clock:
    def __init__(self) -> None:
        self.now = 0.0
        self.sleeps: list[float] = []

    def monotonic(self) -> float:
        return self.now

    def sleep(self, delay: float) -> None:
        assert delay > 0
        self.sleeps.append(delay)
        self.now += delay


class FakeCLI:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.reported_root = str(root)
        self.origin = f"https://github.com/{REPOSITORY}.git"
        self.approved_sha = APPROVED_SHA
        self.artifact: object = artifact_document()
        self.download_writer: Callable[[Path], None] | None = None
        self.calls: list[list[str]] = []
        self.timeouts: list[float] = []
        self.download_directories: list[Path] = []
        self.failures: dict[tuple[str, ...], Exception] = {}
        self.responses: dict[str, list[object]] = {
            WORKFLOWS_ENDPOINT: [{
                "workflows": [{
                    "id": WORKFLOW_ID, "path": producer.BOOTSTRAP_WORKFLOW, "state": "active",
                }],
            }],
            RUNS_ENDPOINT: [{"workflow_runs": [run_document()]}],
            RUN_ENDPOINT: [run_document()],
        }

    def matching(self, *prefix: str) -> list[list[str]]:
        return [args for args in self.calls if args[:len(prefix)] == list(prefix)]

    def __call__(
        self, args: list[str], *, cwd: Path, check: bool, capture_output: bool,
        text: bool, encoding: str, timeout: float,
    ) -> subprocess.CompletedProcess[str]:
        assert cwd == self.root
        assert check is True and capture_output is True and text is True
        assert encoding == "utf-8"
        assert 0 < timeout <= bootstrap.COMMAND_TIMEOUT_SECONDS
        self.calls.append(list(args))
        self.timeouts.append(timeout)
        if args[:3] == ["gh", "run", "download"]:
            self.download_directories.append(Path(args[args.index("--dir") + 1]))
        for prefix, exception in self.failures.items():
            if tuple(args[:len(prefix)]) == prefix:
                raise exception
        if args == ["git", "rev-parse", "--show-toplevel"]:
            output = f"{self.reported_root}\n"
        elif args == ["git", "remote", "get-url", "origin"]:
            output = f"{self.origin}\n"
        elif args == ["gh", "auth", "status", "--hostname", "github.com"]:
            output = ""
        elif args[:2] == ["git", "fetch"]:
            assert args == [
                "git", "fetch", "--no-tags", "--no-recurse-submodules", "--no-write-fetch-head",
                "origin", "refs/heads/dev:refs/remotes/origin/dev",
            ]
            output = ""
        elif args == ["git", "rev-parse", "--verify", "refs/remotes/origin/dev^{commit}"]:
            output = f"{self.approved_sha}\n"
        elif args[:3] == ["git", "merge-base", "--is-ancestor"]:
            assert args == ["git", "merge-base", "--is-ancestor", RUN_SHA, APPROVED_SHA]
            output = ""
        elif args[:2] == ["gh", "api"]:
            assert args[2:-1] == ["--hostname", "github.com", "--method", "GET"]
            assert args[-1] in self.responses, "Unscripted GitHub API call"
            responses = self.responses[args[-1]]
            assert responses
            response = responses.pop(0) if len(responses) > 1 else responses[0]
            if isinstance(response, Exception):
                raise response
            output = response if isinstance(response, str) else json.dumps(response)
        elif args[:3] == ["gh", "workflow", "run"]:
            assert args == [
                "gh", "workflow", "run", str(WORKFLOW_ID), "--repo", f"github.com/{REPOSITORY}",
                "--ref", "dev", "--raw-field", f"request_id={NONCE}",
            ]
            output = ""
        elif args[:3] == ["gh", "run", "download"]:
            destination = self.download_directories[-1]
            assert destination.parent.parent == self.root
            assert destination.name == "artifact"
            assert args == [
                "gh", "run", "download", RUN_ID, "--repo", f"github.com/{REPOSITORY}",
                "--name", producer.BOOTSTRAP_ARTIFACT, "--dir", str(destination),
            ]
            if self.download_writer is not None:
                self.download_writer(destination)
            else:
                (destination / producer.BOOTSTRAP_FILENAME).write_text(
                    json.dumps(self.artifact), encoding="utf-8",
                )
            output = ""
        else:
            pytest.fail(f"Unscripted subprocess command: {args}")
        return subprocess.CompletedProcess(args, 0, stdout=output, stderr="")


@pytest.fixture(autouse=True)
def offline_only(monkeypatch: pytest.MonkeyPatch) -> None:
    forbidden = Mock(side_effect=AssertionError("Real subprocess/Fabric/network calls are forbidden"))
    monkeypatch.setattr(bootstrap.subprocess, "run", forbidden)
    monkeypatch.setattr(urllib.request, "urlopen", forbidden)
    monkeypatch.setattr(socket, "create_connection", forbidden)
    monkeypatch.setattr(fabric, "build_opener", forbidden)
    monkeypatch.setattr(producer, "FabricRestClient", forbidden)
    monkeypatch.setattr(producer, "collect_bindings", forbidden)
    monkeypatch.setattr(producer, "ensure_pipeline_connections", forbidden)
    monkeypatch.setattr(bootstrap.secrets, "token_hex", Mock(return_value=NONCE))


@pytest.fixture(autouse=True)
def clock(monkeypatch: pytest.MonkeyPatch) -> Clock:
    clock = Clock()
    monkeypatch.setattr(bootstrap, "time", clock)
    return clock


@pytest.fixture
def checkout() -> Iterator[Path]:
    with TemporaryDirectory(prefix=".test-github-bootstrap-", dir=PROJECT_ROOT) as folder:
        root = Path(folder).resolve()
        (root / "source.json").write_text('{"unchanged": true}\n', encoding="utf-8")
        yield root


@pytest.fixture
def cli(checkout: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[FakeCLI]:
    cli = FakeCLI(checkout)
    monkeypatch.setattr(bootstrap.subprocess, "run", cli)
    yield cli
    assert all(not folder.exists() for folder in cli.download_directories), "Artifact download leaked"
    assert all(not folder.parent.exists() for folder in cli.download_directories), "Scoped directory leaked"


def formatted_error(error: BaseException) -> str:
    return "".join(traceback.format_exception(type(error), error, error.__traceback__))


def test_reuses_latest_successful_dev_run_with_real_artifact_parser(
    checkout: Path, cli: FakeCLI, monkeypatch: pytest.MonkeyPatch,
) -> None:
    parser = Mock(wraps=producer.parse_bootstrap_artifact)
    monkeypatch.setattr(bootstrap, "parse_bootstrap_artifact", parser)

    result = bootstrap.get_bootstrap_artifact(checkout)

    assert isinstance(result, producer.BootstrapArtifact)
    assert result.bindings.workspace_id == WORKSPACE
    assert result.bindings.semantic_model_id == MODEL
    assert result.bindings.notebook_connection_id == NOTEBOOK
    assert result.bindings.refresh_connection_id == REFRESH
    assert result.document() == artifact_document()
    parser.assert_called_once_with(artifact_document())
    assert not cli.matching("gh", "workflow", "run")
    assert len(cli.matching("git", "merge-base", "--is-ancestor")) == 1
    assert len(cli.matching("gh", "run", "download")) == 1
    assert not cli.matching("git", "checkout")
    assert not cli.matching("git", "reset")
    assert list(checkout.iterdir()) == [checkout / "source.json"]
    assert (checkout / "source.json").read_text(encoding="utf-8") == '{"unchanged": true}\n'


@pytest.mark.parametrize("origin", [
    f"https://github.com/{REPOSITORY}.git",
    f"https://github.com/{REPOSITORY}",
    f"https://GITHUB.COM:443/{REPOSITORY}.git",
    f"git@github.com:{REPOSITORY}.git",
    f"git@GITHUB.COM:{REPOSITORY}",
    f"ssh://git@github.com/{REPOSITORY}.git",
    f"ssh://git@github.com:22/{REPOSITORY}.git",
])
def test_standard_github_origins(checkout: Path, cli: FakeCLI, origin: str) -> None:
    cli.origin = origin
    assert bootstrap.get_bootstrap_artifact(checkout).provenance.repository == REPOSITORY


@pytest.mark.parametrize("origin", [
    "",
    f"http://github.com/{REPOSITORY}.git",
    f"https://example.com/{REPOSITORY}.git",
    f"https://github.com.example.com/{REPOSITORY}.git",
    f"https://{TOKEN_SECRET}@github.com/{REPOSITORY}.git",
    f"https://user:{TOKEN_SECRET}@github.com/{REPOSITORY}.git",
    f"https://github.com/{REPOSITORY}.git?token={TOKEN_SECRET}",
    f"https://github.com/{REPOSITORY}.git#{TOKEN_SECRET}",
    f"https://github.com:invalid/{REPOSITORY}",
    f"https://github.com:444/{REPOSITORY}",
    f"ssh://other@github.com/{REPOSITORY}",
    f"ssh://git:{TOKEN_SECRET}@github.com/{REPOSITORY}",
    f"ssh://git@github.com:2222/{REPOSITORY}",
    f"git@example.com:{REPOSITORY}.git",
    f"file:///{REPOSITORY}.git",
    f"git://github.com/{REPOSITORY}.git",
    "https://github.com/owner/../repo",
    "https://github.com/owner/..",
    "https://github.com/owner/%2e%2e",
    "https://github.com/owner/repo/extra",
    "https://github.com/owner/repo/",
    "https://github.com/-bad/repo",
    f"\t https://github.com/{REPOSITORY}",
    f"https://github.com/{REPOSITORY}\n{TOKEN_SECRET}",
])
def test_rejects_unsafe_origins_without_leaking_urls(
    checkout: Path, cli: FakeCLI, origin: str,
) -> None:
    cli.origin = origin
    with pytest.raises(bootstrap.GitHubBootstrapError, match="origin must") as caught:
        bootstrap.get_bootstrap_artifact(checkout)
    assert TOKEN_SECRET not in formatted_error(caught.value)
    assert not cli.matching("gh")
    assert not cli.matching("git", "fetch")


@pytest.mark.parametrize("reported", ["", ".", "..", "relative", "bad\nroot"])
def test_git_must_report_an_absolute_root(checkout: Path, cli: FakeCLI, reported: str) -> None:
    cli.reported_root = reported
    with pytest.raises(bootstrap.GitHubBootstrapError, match="absolute checkout root"):
        bootstrap.get_bootstrap_artifact(checkout)
    assert len(cli.calls) == 1


def test_git_root_cannot_be_a_subdirectory_or_other_checkout(checkout: Path, cli: FakeCLI) -> None:
    cli.reported_root = str(checkout.parent)
    with pytest.raises(bootstrap.GitHubBootstrapError, match="not a subdirectory"):
        bootstrap.get_bootstrap_artifact(checkout)
    assert len(cli.calls) == 1


@pytest.mark.parametrize("name", ["missing", "source.json"])
def test_git_root_must_exist_and_be_a_directory(checkout: Path, cli: FakeCLI, name: str) -> None:
    with pytest.raises(bootstrap.GitHubBootstrapError, match="existing checkout root"):
        bootstrap.get_bootstrap_artifact(checkout / name)
    assert not cli.calls


@pytest.mark.parametrize("run_id", [
    "", "0", "-1", "+1", "01", " 1", "1 ", "1\n", "../1", "--help", "1/../../runs",
    "a", "1" * 21, 1, True, [], {},
])
def test_bad_explicit_run_ids_fail_before_commands(checkout: Path, cli: FakeCLI, run_id: object) -> None:
    with pytest.raises(bootstrap.GitHubBootstrapError, match="positive decimal"):
        bootstrap.get_bootstrap_artifact(checkout, run_id=run_id)  # type: ignore[arg-type]
    assert not cli.calls


@pytest.mark.parametrize("timeout", [
    0, -1, float("nan"), float("inf"), float("-inf"), True, "1200", None, 10**500,
])
def test_timeout_must_be_positive_and_finite(checkout: Path, cli: FakeCLI, timeout: object) -> None:
    with pytest.raises(bootstrap.GitHubBootstrapError, match="positive, finite"):
        bootstrap.get_bootstrap_artifact(checkout, timeout_seconds=timeout)  # type: ignore[arg-type]
    assert not cli.calls


@pytest.mark.parametrize("sha", ["", "a" * 39, "A" * 40, f"--{TOKEN_SECRET}"])
def test_fetched_dev_tip_is_validated(checkout: Path, cli: FakeCLI, sha: str) -> None:
    cli.approved_sha = sha
    with pytest.raises(bootstrap.GitHubBootstrapError, match="origin/dev commit is invalid") as caught:
        bootstrap.get_bootstrap_artifact(checkout)
    assert TOKEN_SECRET not in formatted_error(caught.value)
    assert not cli.matching("gh", "api")


@pytest.mark.parametrize("explicit_run_id", [None, RUN_ID])
def test_workflow_registration_is_a_hard_prerequisite(
    checkout: Path, cli: FakeCLI, explicit_run_id: str | None,
) -> None:
    cli.responses[WORKFLOWS_ENDPOINT] = [{"workflows": []}]
    with pytest.raises(bootstrap.GitHubBootstrapError, match="bootstrap-only infrastructure PR") as caught:
        bootstrap.get_bootstrap_artifact(checkout, run_id=explicit_run_id)
    assert "default branch" in str(caught.value)
    assert not cli.matching("gh", "workflow", "run")
    assert not cli.matching("gh", "run", "download")


@pytest.mark.parametrize("state", ["disabled_manually", "disabled_inactivity", "deleted", None])
def test_disabled_workflow_is_not_enabled_implicitly(
    checkout: Path, cli: FakeCLI, state: object,
) -> None:
    cli.responses[WORKFLOWS_ENDPOINT] = [{
        "workflows": [{"id": WORKFLOW_ID, "path": producer.BOOTSTRAP_WORKFLOW, "state": state}],
    }]
    with pytest.raises(bootstrap.GitHubBootstrapError, match="not active"):
        bootstrap.get_bootstrap_artifact(checkout)
    assert not cli.matching("gh", "workflow", "run")


@pytest.mark.parametrize("workflow_id", [0, -1, True, "2468", None, [], 10**20])
def test_workflow_ids_are_validated_before_use(
    checkout: Path, cli: FakeCLI, workflow_id: object,
) -> None:
    cli.responses[WORKFLOWS_ENDPOINT] = [{
        "workflows": [{"id": workflow_id, "path": producer.BOOTSTRAP_WORKFLOW, "state": "active"}],
    }]
    with pytest.raises(bootstrap.GitHubBootstrapError, match="workflow ID"):
        bootstrap.get_bootstrap_artifact(checkout)
    assert not cli.matching("gh", "workflow", "run")


def test_ambiguous_workflow_registration_fails(checkout: Path, cli: FakeCLI) -> None:
    workflow = {"id": WORKFLOW_ID, "path": producer.BOOTSTRAP_WORKFLOW, "state": "active"}
    cli.responses[WORKFLOWS_ENDPOINT] = [{"workflows": [workflow, workflow]}]
    with pytest.raises(bootstrap.GitHubBootstrapError, match="ambiguous"):
        bootstrap.get_bootstrap_artifact(checkout)


def other_workflows() -> list[dict[str, object]]:
    return [
        {"id": index + 1, "path": f".github/workflows/other-{index}.yml", "state": "active"}
        for index in range(bootstrap.PAGE_SIZE)
    ]


def test_workflow_discovery_paginates_by_exact_path(checkout: Path, cli: FakeCLI) -> None:
    cli.responses[WORKFLOWS_ENDPOINT] = [{"workflows": other_workflows()}]
    cli.responses[WORKFLOWS_ENDPOINT.replace("&page=1", "&page=2")] = [{
        "workflows": [{"id": WORKFLOW_ID, "path": producer.BOOTSTRAP_WORKFLOW, "state": "active"}],
    }]
    assert bootstrap.get_bootstrap_artifact(checkout).bindings.workspace_id == WORKSPACE
    workflow_calls = [
        args for args in cli.matching("gh", "api") if "/actions/workflows?" in args[-1]
    ]
    assert len(workflow_calls) == 2


def test_workflow_lookup_has_a_page_bound(checkout: Path, cli: FakeCLI) -> None:
    for page in range(1, bootstrap.MAX_DISCOVERY_PAGES + 1):
        endpoint = WORKFLOWS_ENDPOINT.replace("&page=1", f"&page={page}")
        cli.responses[endpoint] = [{"workflows": other_workflows()}]
    with pytest.raises(bootstrap.GitHubBootstrapError, match="bounded workflow lookup"):
        bootstrap.get_bootstrap_artifact(checkout)
    assert len(cli.matching("gh", "api")) == bootstrap.MAX_DISCOVERY_PAGES
    assert not cli.matching("gh", "workflow", "run")


@pytest.mark.parametrize("response", [
    "null", "[]", "1", '"text"', f"{{{BODY_SECRET}", '{"workflows":[],"workflows":[]}',
    {"workflows": None}, {"workflows": {}}, {"workflows": [None]},
    {"workflows": [{}] * (bootstrap.PAGE_SIZE + 1)}, "[" * 2000 + "]" * 2000,
])
def test_workflow_json_boundary_is_guarded_and_redacted(
    checkout: Path, cli: FakeCLI, response: object,
) -> None:
    cli.responses[WORKFLOWS_ENDPOINT] = [response]
    with pytest.raises(bootstrap.GitHubBootstrapError) as caught:
        bootstrap.get_bootstrap_artifact(checkout)
    assert BODY_SECRET not in formatted_error(caught.value)
    assert not cli.matching("gh", "workflow", "run")


def test_explicit_run_bypasses_latest_lookup_and_never_dispatches(checkout: Path, cli: FakeCLI) -> None:
    cli.responses[RUNS_ENDPOINT] = [{"workflow_runs": [run_document(conclusion="failure")]}]
    result = bootstrap.get_bootstrap_artifact(checkout, run_id=RUN_ID)
    assert result.provenance.run_id == RUN_ID
    assert not any(args[-1] == RUNS_ENDPOINT for args in cli.matching("gh", "api"))
    assert not cli.matching("gh", "workflow", "run")


def test_run_lookup_skips_nondev_and_pr_runs_but_not_failed_dev_runs(
    checkout: Path, cli: FakeCLI,
) -> None:
    cli.responses[RUNS_ENDPOINT] = [{"workflow_runs": [
        run_document(id=99999, head_branch="feature/untrusted"),
        run_document(id=99998, event="pull_request"),
        run_document(id=99997, event="pull_request_target"),
        run_document(),
    ]}]
    assert bootstrap.get_bootstrap_artifact(checkout).provenance.run_id == RUN_ID
    assert not cli.matching("gh", "workflow", "run")


@pytest.mark.parametrize("bad_id", [0, True, "12345", [], None])
def test_discovered_run_id_is_validated(checkout: Path, cli: FakeCLI, bad_id: object) -> None:
    cli.responses[RUNS_ENDPOINT] = [{"workflow_runs": [run_document(id=bad_id)]}]
    with pytest.raises(bootstrap.GitHubBootstrapError, match="run ID"):
        bootstrap.get_bootstrap_artifact(checkout)
    assert not cli.matching("gh", "run", "download")
    assert not cli.matching("gh", "workflow", "run")


@pytest.mark.parametrize("response", [
    {"workflow_runs": None}, {"workflow_runs": [1]},
    {"workflow_runs": [run_document(event=[])]},
    {"workflow_runs": [run_document(event={})]},
])
def test_malformed_run_listing_fails_instead_of_dispatching(
    checkout: Path, cli: FakeCLI, response: object,
) -> None:
    cli.responses[RUNS_ENDPOINT] = [response]
    with pytest.raises(bootstrap.GitHubBootstrapError):
        bootstrap.get_bootstrap_artifact(checkout)
    assert not cli.matching("gh", "workflow", "run")


def test_run_history_pagination_is_bounded_without_dispatch(checkout: Path, cli: FakeCLI) -> None:
    irrelevant = [run_document(id=index + 1, event="pull_request") for index in range(bootstrap.PAGE_SIZE)]
    for page in range(1, bootstrap.MAX_DISCOVERY_PAGES + 1):
        cli.responses[RUNS_ENDPOINT.replace("&page=1", f"&page={page}")] = [{"workflow_runs": irrelevant}]
    with pytest.raises(bootstrap.GitHubBootstrapError, match="bounded history"):
        bootstrap.get_bootstrap_artifact(checkout)
    assert not cli.matching("gh", "workflow", "run")


def test_latest_eligible_run_can_be_on_second_page(checkout: Path, cli: FakeCLI) -> None:
    cli.responses[RUNS_ENDPOINT] = [{"workflow_runs": [
        run_document(id=index + 1, event="pull_request") for index in range(bootstrap.PAGE_SIZE)
    ]}]
    cli.responses[RUNS_ENDPOINT.replace("&page=1", "&page=2")] = [{"workflow_runs": [run_document()]}]
    assert bootstrap.get_bootstrap_artifact(checkout).provenance.run_id == RUN_ID


@pytest.mark.parametrize("status", ["pending", "queued", "requested", "in_progress"])
def test_pending_runs_poll_then_reuse_success(
    checkout: Path, cli: FakeCLI, clock: Clock, status: str,
) -> None:
    cli.responses[RUN_ENDPOINT] = [
        run_document(status=status, conclusion=None),
        run_document(),
    ]
    assert bootstrap.get_bootstrap_artifact(checkout).provenance.run_id == RUN_ID
    assert clock.sleeps == [bootstrap.POLL_INTERVAL_SECONDS]
    assert not cli.matching("gh", "workflow", "run")


def test_environment_approval_stops_without_spinning_or_older_success(
    checkout: Path, cli: FakeCLI, clock: Clock,
) -> None:
    cli.responses[RUNS_ENDPOINT] = [{"workflow_runs": [
        run_document(status="waiting", conclusion=None),
        run_document(id=12344),
    ]}]
    cli.responses[RUN_ENDPOINT] = [run_document(status="waiting", conclusion=None)]
    with pytest.raises(bootstrap.GitHubBootstrapError, match="Environment approval") as caught:
        bootstrap.get_bootstrap_artifact(checkout)
    assert RUN_URL in str(caught.value)
    assert "No automatic approval" in str(caught.value)
    assert clock.sleeps == []
    assert not cli.matching("gh", "workflow", "run")
    assert not cli.matching("gh", "run", "download")


@pytest.mark.parametrize("conclusion", [
    "failure", "cancelled", "timed_out", "action_required",
    "neutral", "skipped", "stale", "startup_failure",
])
def test_latest_failed_run_never_falls_back_to_an_older_success(
    checkout: Path, cli: FakeCLI, conclusion: str,
) -> None:
    cli.responses[RUNS_ENDPOINT] = [{"workflow_runs": [
        run_document(conclusion=conclusion), run_document(id=12344),
    ]}]
    cli.responses[RUN_ENDPOINT] = [run_document(conclusion=conclusion)]
    with pytest.raises(bootstrap.GitHubBootstrapError, match="did not succeed") as caught:
        bootstrap.get_bootstrap_artifact(checkout)
    assert RUN_URL in str(caught.value)
    assert not cli.matching("gh", "workflow", "run")
    assert not cli.matching("gh", "run", "download")
    assert not any(args[-1].endswith("/12344") for args in cli.matching("gh", "api"))


def test_pending_run_deadline_caps_sleeps_and_command_timeouts(
    checkout: Path, cli: FakeCLI, clock: Clock,
) -> None:
    cli.responses[RUN_ENDPOINT] = [run_document(status="in_progress", conclusion=None)]
    with pytest.raises(bootstrap.GitHubBootstrapError, match="Timed out") as caught:
        bootstrap.get_bootstrap_artifact(checkout, timeout_seconds=7)
    assert RUN_URL in str(caught.value)
    assert clock.sleeps == [5.0, 2.0]
    assert clock.now == 7
    assert all(timeout <= 7 for timeout in cli.timeouts)
    assert not cli.matching("gh", "workflow", "run")
    assert not cli.matching("gh", "run", "download")


@pytest.mark.parametrize(("field", "value"), [
    ("id", 12346), ("id", True), ("id", "12345"),
    ("repository", None), ("repository", {"full_name": "someone/other"}),
    ("repository", {"full_name": f"https://{TOKEN_SECRET}@github.com/owner/repo"}),
    ("path", ".github/workflows/feature.yml"), ("workflow_id", 9999),
    ("workflow_id", True), ("workflow_id", "2468"),
    ("head_branch", "feature/untrusted"), ("head_branch", None),
    ("event", "pull_request"), ("event", "pull_request_target"), ("event", "schedule"),
    ("event", []), ("head_sha", "B" * 40), ("head_sha", "b" * 39),
    ("head_sha", f"--{TOKEN_SECRET}"),
    ("run_attempt", 0), ("run_attempt", -1), ("run_attempt", True),
    ("run_attempt", "1"), ("run_attempt", None),
    ("status", "unknown"), ("status", []), ("conclusion", None),
    ("conclusion", []), ("conclusion", TOKEN_SECRET),
    ("display_title", None), ("display_title", ""),
])
def test_authenticated_run_metadata_must_match_the_approved_dev_workflow(
    checkout: Path, cli: FakeCLI, field: str, value: object,
) -> None:
    cli.responses[RUN_ENDPOINT] = [run_document(**{field: value})]
    with pytest.raises(bootstrap.GitHubBootstrapError) as caught:
        bootstrap.get_bootstrap_artifact(checkout, run_id=RUN_ID)
    assert RUN_URL in str(caught.value)
    assert TOKEN_SECRET not in formatted_error(caught.value)
    assert not cli.matching("git", "merge-base")
    assert not cli.matching("gh", "run", "download")


def test_unfinished_run_cannot_claim_a_success_conclusion(checkout: Path, cli: FakeCLI) -> None:
    cli.responses[RUN_ENDPOINT] = [run_document(status="queued", conclusion="success")]
    with pytest.raises(bootstrap.GitHubBootstrapError, match="unfinished bootstrap run"):
        bootstrap.get_bootstrap_artifact(checkout)


def test_repository_case_is_resolved_against_authenticated_full_name(
    checkout: Path, cli: FakeCLI, monkeypatch: pytest.MonkeyPatch,
) -> None:
    alias = REPOSITORY.upper()
    cli.origin = f"https://github.com/{alias}.git"
    cli.responses = {
        endpoint.replace(REPOSITORY, alias): responses for endpoint, responses in cli.responses.items()
    }

    def download(destination: Path) -> None:
        (destination / producer.BOOTSTRAP_FILENAME).write_text(json.dumps(cli.artifact), encoding="utf-8")

    cli.download_writer = download
    original = cli.__call__

    def case_aware(
        args: list[str], *, cwd: Path, check: bool, capture_output: bool,
        text: bool, encoding: str, timeout: float,
    ) -> subprocess.CompletedProcess[str]:
        normalized = [arg.replace(f"github.com/{alias}", f"github.com/{REPOSITORY}") for arg in args]
        return original(
            normalized, cwd=cwd, check=check, capture_output=capture_output,
            text=text, encoding=encoding, timeout=timeout,
        )

    monkeypatch.setattr(bootstrap.subprocess, "run", case_aware)
    assert bootstrap.get_bootstrap_artifact(checkout).provenance.repository == REPOSITORY


@pytest.mark.parametrize(("returncode", "message"), [(1, "not an ancestor"), (128, "Could not verify")])
def test_commit_ancestry_is_checked_and_specific_git_failures_are_redacted(
    checkout: Path, cli: FakeCLI, returncode: int, message: str,
) -> None:
    cli.failures[("git", "merge-base")] = subprocess.CalledProcessError(
        returncode, [TOKEN_SECRET], output=BODY_SECRET, stderr=TOKEN_SECRET,
    )
    with pytest.raises(bootstrap.GitHubBootstrapError, match=message) as caught:
        bootstrap.get_bootstrap_artifact(checkout)
    assert RUN_URL in str(caught.value)
    assert BODY_SECRET not in formatted_error(caught.value)
    assert TOKEN_SECRET not in formatted_error(caught.value)
    assert not cli.matching("gh", "run", "download")


def dispatch_setup(cli: FakeCLI) -> None:
    cli.responses[RUNS_ENDPOINT] = [
        {"workflow_runs": []},
        {"workflow_runs": [run_document(event="workflow_dispatch", display_title=TITLE)]},
    ]
    cli.responses[RUN_ENDPOINT] = [run_document(event="workflow_dispatch", display_title=TITLE)]
    cli.artifact = artifact_document(event="workflow_dispatch")


def test_initial_dispatch_is_once_and_correlates_exact_title_event_ref_and_workflow(
    checkout: Path, cli: FakeCLI, clock: Clock,
) -> None:
    dispatch_setup(cli)
    cli.responses[RUNS_ENDPOINT].insert(1, {"workflow_runs": [
        run_document(id=22222, event="workflow_dispatch", display_title=f"{TITLE}-unrelated"),
        run_document(id=22223, event="workflow_dispatch", display_title=TITLE, head_branch="feature/untrusted"),
        run_document(id=22224, event="push", display_title=TITLE),
        run_document(id=22225, event="workflow_dispatch", display_title=TITLE, workflow_id=9999),
        run_document(id=22226, event="workflow_dispatch", display_title=TITLE, path=".github/workflows/other.yml"),
        run_document(id=22227, event="workflow_dispatch", display_title=TITLE, workflow_id=True),
    ]})
    result = bootstrap.get_bootstrap_artifact(checkout)
    assert result.provenance.event == "workflow_dispatch"
    assert len(cli.matching("gh", "workflow", "run")) == 1
    assert clock.sleeps == [5.0]
    assert not any("/2222" in args[-1] for args in cli.matching("gh", "api"))
    token_hex = bootstrap.secrets.token_hex
    assert isinstance(token_hex, Mock)
    token_hex.assert_called_once_with(16)


@pytest.mark.parametrize(("field", "value"), [
    ("display_title", f"{TITLE}-unrelated"), ("event", "push"),
    ("path", ".github/workflows/other.yml"), ("head_branch", "feature/untrusted"),
])
def test_correlated_run_is_revalidated_in_full_before_download(
    checkout: Path, cli: FakeCLI, field: str, value: object,
) -> None:
    dispatch_setup(cli)
    cli.responses[RUN_ENDPOINT] = [
        run_document(event="workflow_dispatch", display_title=TITLE, **{field: value})
        if field not in {"event", "display_title"}
        else {
            **run_document(event="workflow_dispatch", display_title=TITLE),
            field: value,
        },
    ]
    with pytest.raises(bootstrap.GitHubBootstrapError):
        bootstrap.get_bootstrap_artifact(checkout)
    assert len(cli.matching("gh", "workflow", "run")) == 1
    assert not cli.matching("gh", "run", "download")


def test_dispatch_does_not_match_ambiguous_runs(checkout: Path, cli: FakeCLI) -> None:
    dispatch_setup(cli)
    cli.responses[RUNS_ENDPOINT][1] = {"workflow_runs": [
        run_document(event="workflow_dispatch", display_title=TITLE),
        run_document(id=12346, event="workflow_dispatch", display_title=TITLE),
    ]}
    with pytest.raises(bootstrap.GitHubBootstrapError, match="ambiguous"):
        bootstrap.get_bootstrap_artifact(checkout)
    assert len(cli.matching("gh", "workflow", "run")) == 1


def test_dispatch_correlation_timeout_never_redispatches(
    checkout: Path, cli: FakeCLI, clock: Clock,
) -> None:
    cli.responses[RUNS_ENDPOINT] = [{"workflow_runs": []}]
    with pytest.raises(bootstrap.GitHubBootstrapError, match="Timed out") as caught:
        bootstrap.get_bootstrap_artifact(checkout, timeout_seconds=7)
    assert WORKFLOW_URL in str(caught.value)
    assert "inspect runs before redispatching" in str(caught.value)
    assert clock.sleeps == [5.0, 2.0]
    assert len(cli.matching("gh", "workflow", "run")) == 1
    assert not cli.matching("gh", "run", "download")


@pytest.mark.parametrize("failure", [
    subprocess.CalledProcessError(1, [TOKEN_SECRET], output=BODY_SECRET, stderr=TOKEN_SECRET),
    subprocess.TimeoutExpired([TOKEN_SECRET], 60, output=BODY_SECRET, stderr=TOKEN_SECRET),
])
def test_dispatch_errors_never_retry_an_ambiguous_submission(
    checkout: Path, cli: FakeCLI, failure: Exception,
) -> None:
    dispatch_setup(cli)
    cli.failures[("gh", "workflow", "run")] = failure
    with pytest.raises(bootstrap.GitHubBootstrapError) as caught:
        bootstrap.get_bootstrap_artifact(checkout)
    assert WORKFLOW_URL in str(caught.value)
    assert TOKEN_SECRET not in formatted_error(caught.value)
    assert BODY_SECRET not in formatted_error(caught.value)
    assert len(cli.matching("gh", "workflow", "run")) == 1
    assert not cli.matching("gh", "run", "download")


@pytest.mark.parametrize("prefix", [
    ("git", "rev-parse", "--show-toplevel"), ("git", "remote", "get-url"),
    ("gh", "auth", "status"), ("git", "fetch"), ("git", "rev-parse", "--verify"),
    ("gh", "api"), ("git", "merge-base"), ("gh", "run", "download"),
])
def test_subprocess_failure_boundaries_never_expose_stdout_stderr_or_command_secrets(
    checkout: Path, cli: FakeCLI, prefix: tuple[str, ...], capsys: pytest.CaptureFixture[str],
) -> None:
    cli.failures[prefix] = subprocess.CalledProcessError(
        128, [TOKEN_SECRET], output=BODY_SECRET, stderr=TOKEN_SECRET,
    )
    with pytest.raises(bootstrap.GitHubBootstrapError) as caught:
        bootstrap.get_bootstrap_artifact(checkout)
    error = formatted_error(caught.value)
    assert TOKEN_SECRET not in error and BODY_SECRET not in error
    assert capsys.readouterr() == ("", "")
    if prefix[0] == "gh":
        assert "gh auth login --hostname github.com" in str(caught.value)
    if prefix == ("gh", "run", "download"):
        assert "missing or expired" in str(caught.value)
        assert RUN_URL in str(caught.value)


@pytest.mark.parametrize("prefix", [
    ("gh", "api"), ("git", "fetch"), ("git", "merge-base"), ("gh", "run", "download"),
])
def test_command_timeouts_are_explicit_and_redacted(
    checkout: Path, cli: FakeCLI, prefix: tuple[str, ...],
) -> None:
    cli.failures[prefix] = subprocess.TimeoutExpired(
        [TOKEN_SECRET], 60, output=BODY_SECRET, stderr=TOKEN_SECRET,
    )
    with pytest.raises(bootstrap.GitHubBootstrapError, match="Timed out") as caught:
        bootstrap.get_bootstrap_artifact(checkout)
    assert TOKEN_SECRET not in formatted_error(caught.value)
    assert BODY_SECRET not in formatted_error(caught.value)
    if prefix in {("git", "merge-base"), ("gh", "run", "download")}:
        assert RUN_URL in str(caught.value)


@pytest.mark.parametrize(("prefix", "message"), [
    (("git", "rev-parse"), "Git is required"),
    (("gh", "auth", "status"), "gh auth login --hostname github.com"),
])
def test_missing_cli_has_actionable_safe_errors(
    checkout: Path, cli: FakeCLI, prefix: tuple[str, ...], message: str,
) -> None:
    cli.failures[prefix] = FileNotFoundError(TOKEN_SECRET)
    with pytest.raises(bootstrap.GitHubBootstrapError, match=message) as caught:
        bootstrap.get_bootstrap_artifact(checkout)
    assert TOKEN_SECRET not in formatted_error(caught.value)


@pytest.mark.parametrize("failure", [
    PermissionError(TOKEN_SECRET),
    UnicodeDecodeError("utf-8", b"\xff", 0, 1, TOKEN_SECRET),
])
def test_unsafe_command_execution_errors_are_redacted(
    checkout: Path, cli: FakeCLI, failure: Exception,
) -> None:
    cli.failures[("gh", "api")] = failure
    with pytest.raises(bootstrap.GitHubBootstrapError, match="safely") as caught:
        bootstrap.get_bootstrap_artifact(checkout)
    assert TOKEN_SECRET not in formatted_error(caught.value)


@pytest.mark.parametrize(("field", "value"), [
    ("repository", "someone/other"), ("runId", "12346"), ("runAttempt", 2),
    ("headSha", "c" * 40), ("event", "workflow_dispatch"),
    ("ref", "refs/heads/feature"), ("workflowPath", ".github/workflows/other.yml"),
])
def test_artifact_provenance_must_match_authenticated_run(
    checkout: Path, cli: FakeCLI, field: str, value: object,
) -> None:
    cli.artifact = artifact_document(**{field: value})
    with pytest.raises(bootstrap.GitHubBootstrapError) as caught:
        bootstrap.get_bootstrap_artifact(checkout)
    assert RUN_URL in str(caught.value)
    assert len(cli.matching("gh", "run", "download")) == 1


def test_rerun_attempt_is_verified_against_downloaded_metadata(checkout: Path, cli: FakeCLI) -> None:
    cli.responses[RUN_ENDPOINT] = [run_document(run_attempt=2)]
    cli.artifact = artifact_document(runAttempt=2)
    assert bootstrap.get_bootstrap_artifact(checkout).provenance.run_attempt == 2


def test_transport_leaves_workspace_and_model_target_checks_to_caller(checkout: Path, cli: FakeCLI) -> None:
    cli.artifact = artifact_document(semanticModelName="A separately selected model")
    result = bootstrap.get_bootstrap_artifact(checkout)
    assert result.provenance.model_name == "A separately selected model"
    assert result.bindings.workspace_id == WORKSPACE


@pytest.mark.parametrize(("field", "value"), [
    ("schemaVersion", 2), ("schemaVersion", True), ("schemaVersion", None),
    ("workspaceId", None), ("workspaceId", "not-a-guid"), ("workspaceId", NOTEBOOK),
    ("notebookConnectionId", "11111111-1111-4111-8111-111111111111"),
    ("semanticModelRefreshConnectionId", "22222222-2222-4222-8222-222222222222"),
    ("semanticModelRefreshConnectionId", "00000000-0000-0000-0000-000000000000"),
    ("semanticModelId", {"secret": BODY_SECRET}),
])
def test_binding_validation_uses_the_real_producer_parser(
    checkout: Path, cli: FakeCLI, field: str, value: object,
) -> None:
    document = artifact_document()
    bindings = document["bindings"]
    assert isinstance(bindings, dict)
    bindings[field] = value
    cli.artifact = document
    with pytest.raises(bootstrap.GitHubBootstrapError, match="schema or bindings") as caught:
        bootstrap.get_bootstrap_artifact(checkout)
    assert BODY_SECRET not in formatted_error(caught.value)
    assert RUN_URL in str(caught.value)


@pytest.mark.parametrize("kind", [
    "extra_top", "extra_binding", "extra_provenance", "missing_binding", "missing_provenance",
    "schema", "boolean_schema", "null", "list",
])
def test_malformed_or_secret_bearing_artifact_shapes_are_rejected(
    checkout: Path, cli: FakeCLI, kind: str,
) -> None:
    document = artifact_document()
    if kind in {"extra_top", "schema", "boolean_schema"}:
        if kind == "extra_top":
            document["clientSecret"] = BODY_SECRET
        else:
            document["schemaVersion"] = True if kind == "boolean_schema" else 2
    elif kind in {"null", "list"}:
        cli.artifact = None if kind == "null" else []
    else:
        key = "bindings" if "binding" in kind else "provenance"
        nested = document[key]
        assert isinstance(nested, dict)
        if kind.startswith("extra"):
            nested["clientSecret"] = BODY_SECRET
        else:
            del nested["workspaceId" if key == "bindings" else "event"]
    if kind not in {"null", "list"}:
        cli.artifact = document
    with pytest.raises(bootstrap.GitHubBootstrapError, match="schema or bindings") as caught:
        bootstrap.get_bootstrap_artifact(checkout)
    assert BODY_SECRET not in formatted_error(caught.value)


@pytest.mark.parametrize("content", [
    b"\xff", b"{invalid-json", b"", b"null",
    json.dumps(artifact_document()).replace(
        '"schemaVersion": 1', '"schemaVersion": 1, "schemaVersion": 1', 1,
    ).encode("utf-8"),
    ("[" * 2000 + "]" * 2000).encode("utf-8"),
])
def test_artifact_json_is_utf8_bounded_and_rejects_duplicate_keys(
    checkout: Path, cli: FakeCLI, content: bytes,
) -> None:
    def write(destination: Path) -> None:
        (destination / producer.BOOTSTRAP_FILENAME).write_bytes(content)

    cli.download_writer = write
    with pytest.raises(bootstrap.GitHubBootstrapError) as caught:
        bootstrap.get_bootstrap_artifact(checkout)
    assert RUN_URL in str(caught.value)


@pytest.mark.parametrize("kind", ["missing", "directory", "wrong_filename"])
def test_only_the_exact_artifact_file_is_read(checkout: Path, cli: FakeCLI, kind: str) -> None:
    def write(destination: Path) -> None:
        if kind == "directory":
            (destination / producer.BOOTSTRAP_FILENAME).mkdir()
        elif kind == "wrong_filename":
            (destination / "some-other-bindings.json").write_text(
                json.dumps(artifact_document()), encoding="utf-8",
            )

    cli.download_writer = write
    with pytest.raises(bootstrap.GitHubBootstrapError, match="missing|regular"):
        bootstrap.get_bootstrap_artifact(checkout)


@pytest.mark.parametrize("excess", [0, 1])
def test_artifact_size_limit_is_in_bytes(checkout: Path, cli: FakeCLI, excess: int) -> None:
    content = json.dumps(artifact_document()).encode("utf-8")
    content += b" " * (bootstrap.MAX_ARTIFACT_BYTES + excess - len(content))

    def write(destination: Path) -> None:
        (destination / producer.BOOTSTRAP_FILENAME).write_bytes(content)

    cli.download_writer = write
    if excess:
        with pytest.raises(bootstrap.GitHubBootstrapError, match="64 KiB"):
            bootstrap.get_bootstrap_artifact(checkout)
    else:
        assert bootstrap.get_bootstrap_artifact(checkout).bindings.workspace_id == WORKSPACE


@pytest.mark.parametrize("symlink_directory", [False, True])
def test_symlink_artifact_is_rejected_without_windows_symlink_privileges(
    checkout: Path, cli: FakeCLI, monkeypatch: pytest.MonkeyPatch, symlink_directory: bool,
) -> None:
    original = Path.is_symlink
    suspect: list[Path] = []

    def is_symlink(path: Path) -> bool:
        return path in suspect or original(path)

    def write(destination: Path) -> None:
        path = destination / producer.BOOTSTRAP_FILENAME
        path.write_text(json.dumps(artifact_document()), encoding="utf-8")
        suspect.append(destination if symlink_directory else path)

    monkeypatch.setattr(Path, "is_symlink", is_symlink)
    cli.download_writer = write
    with pytest.raises(bootstrap.GitHubBootstrapError, match="non-symlink|escapes"):
        bootstrap.get_bootstrap_artifact(checkout)


@pytest.mark.parametrize("escape_directory", [False, True])
def test_resolved_artifact_path_and_directory_must_remain_contained(
    checkout: Path, cli: FakeCLI, monkeypatch: pytest.MonkeyPatch, escape_directory: bool,
) -> None:
    original = Path.resolve
    suspect: list[Path] = []

    def resolve(path: Path, strict: bool = False) -> Path:
        if path in suspect:
            return checkout.parent / "outside-bootstrap-download" / path.name
        return original(path, strict=strict)

    def write(destination: Path) -> None:
        path = destination / producer.BOOTSTRAP_FILENAME
        path.write_text(json.dumps(artifact_document()), encoding="utf-8")
        suspect.append(destination if escape_directory else path)

    monkeypatch.setattr(Path, "resolve", resolve)
    cli.download_writer = write
    with pytest.raises(bootstrap.GitHubBootstrapError, match="escapes"):
        bootstrap.get_bootstrap_artifact(checkout)


def test_artifact_read_failure_is_redacted_and_cleaned(
    checkout: Path, cli: FakeCLI, monkeypatch: pytest.MonkeyPatch,
) -> None:
    original = Path.open

    def guarded_open(
        path: Path, mode: str = "r", buffering: int = -1,
        encoding: str | None = None, errors: str | None = None, newline: str | None = None,
    ) -> IO[str] | IO[bytes]:
        if path.name == producer.BOOTSTRAP_FILENAME and mode == "rb":
            raise PermissionError(TOKEN_SECRET)
        return original(path, mode, buffering, encoding, errors, newline)

    monkeypatch.setattr(Path, "open", guarded_open)
    with pytest.raises(bootstrap.GitHubBootstrapError, match="cannot be read safely") as caught:
        bootstrap.get_bootstrap_artifact(checkout)
    assert TOKEN_SECRET not in formatted_error(caught.value)


def test_timeout_after_download_is_redacted_and_cleans_the_directory(
    checkout: Path, cli: FakeCLI, clock: Clock,
) -> None:
    def write(destination: Path) -> None:
        (destination / producer.BOOTSTRAP_FILENAME).write_text(
            json.dumps(artifact_document()), encoding="utf-8",
        )
        clock.now = 1201

    cli.download_writer = write
    with pytest.raises(bootstrap.GitHubBootstrapError, match="Timed out") as caught:
        bootstrap.get_bootstrap_artifact(checkout)
    assert RUN_URL in str(caught.value)


class SecretReadGuard(MutableMapping[str, str]):
    def __init__(self, delegate: MutableMapping[str, str]) -> None:
        self.delegate = delegate

    def __getitem__(self, key: str) -> str:
        assert not key.startswith(("AZURE_", "FABRIC_", "SERVICE_PRINCIPAL_")), "Local SP secrets were read"
        return self.delegate[key]

    def __setitem__(self, key: str, value: str) -> None:
        self.delegate[key] = value

    def __delitem__(self, key: str) -> None:
        del self.delegate[key]

    def __iter__(self) -> Iterator[str]:
        return iter(self.delegate)

    def __len__(self) -> int:
        return len(self.delegate)


def test_local_sp_environment_and_source_are_never_read_or_written(
    checkout: Path, cli: FakeCLI, monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = checkout / "source.json"
    dotenv = checkout / ".env"
    dotenv.write_text(f"AZURE_CLIENT_SECRET={BODY_SECRET}\n", encoding="utf-8")
    before = {path.name: path.read_bytes() for path in (source, dotenv)}
    original = Path.open

    def guarded_open(
        path: Path, mode: str = "r", buffering: int = -1,
        encoding: str | None = None, errors: str | None = None, newline: str | None = None,
    ) -> IO[str] | IO[bytes]:
        assert path not in {source, dotenv}, "Bootstrap transport accessed local source/config"
        return original(path, mode, buffering, encoding, errors, newline)

    with monkeypatch.context() as guard:
        guard.setattr(Path, "open", guarded_open)
        guard.setattr(os, "environ", SecretReadGuard(os.environ))
        assert bootstrap.get_bootstrap_artifact(checkout).bindings.workspace_id == WORKSPACE
    assert {path.name: path.read_bytes() for path in (source, dotenv)} == before
    assert {path.name for path in checkout.iterdir()} == set(before)
    assert all("AZURE_" not in arg and BODY_SECRET not in arg for args in cli.calls for arg in args)


def test_parser_output_is_not_logged_on_success(
    checkout: Path, cli: FakeCLI, capsys: pytest.CaptureFixture[str],
) -> None:
    assert bootstrap.get_bootstrap_artifact(checkout).document() == artifact_document()
    assert capsys.readouterr() == ("", "")


def test_explicit_missing_run_does_not_dispatch_or_select_another_run(checkout: Path, cli: FakeCLI) -> None:
    cli.responses[RUN_ENDPOINT] = [
        subprocess.CalledProcessError(1, [TOKEN_SECRET], output=BODY_SECRET, stderr=TOKEN_SECRET),
    ]
    with pytest.raises(bootstrap.GitHubBootstrapError) as caught:
        bootstrap.get_bootstrap_artifact(checkout, run_id=RUN_ID)
    assert RUN_URL in str(caught.value)
    assert BODY_SECRET not in formatted_error(caught.value)
    assert not cli.matching("gh", "workflow", "run")
    assert not any(args[-1] == RUNS_ENDPOINT for args in cli.matching("gh", "api"))


def test_artifact_provenance_uses_authenticated_repository_casing_not_an_alias(
    checkout: Path, cli: FakeCLI,
) -> None:
    cli.artifact = artifact_document(repository=REPOSITORY.upper())
    with pytest.raises(bootstrap.GitHubBootstrapError, match="provenance does not match"):
        bootstrap.get_bootstrap_artifact(checkout)


def test_parser_specific_error_text_does_not_escape_the_boundary(
    checkout: Path, cli: FakeCLI, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        bootstrap, "parse_bootstrap_artifact",
        Mock(side_effect=producer.BootstrapMetadataError(BODY_SECRET)),
    )
    with pytest.raises(bootstrap.GitHubBootstrapError, match="schema or bindings") as caught:
        bootstrap.get_bootstrap_artifact(checkout)
    assert BODY_SECRET not in formatted_error(caught.value)


def test_download_is_scoped_to_checkout_even_when_system_temp_is_elsewhere(
    checkout: Path, cli: FakeCLI, monkeypatch: pytest.MonkeyPatch,
) -> None:
    temporary_directory = bootstrap.TemporaryDirectory
    calls: list[dict[str, object]] = []

    def scoped_directory(*, prefix: str, dir: Path) -> TemporaryDirectory[str]:
        calls.append({"prefix": prefix, "dir": dir})
        assert dir == checkout
        return temporary_directory(prefix=prefix, dir=dir)

    monkeypatch.setattr(bootstrap, "TemporaryDirectory", scoped_directory)
    assert bootstrap.get_bootstrap_artifact(checkout).bindings.workspace_id == WORKSPACE
    assert calls == [{"prefix": ".fabric-dev-bootstrap-", "dir": checkout}]


def test_growing_file_cannot_bypass_the_byte_limit(
    checkout: Path, cli: FakeCLI, monkeypatch: pytest.MonkeyPatch,
) -> None:
    original = Path.lstat
    content = json.dumps(artifact_document()).encode("utf-8")
    content += b" " * (bootstrap.MAX_ARTIFACT_BYTES + 100 - len(content))

    def lstat(path: Path) -> os.stat_result:
        result = original(path)
        if path.name == producer.BOOTSTRAP_FILENAME:
            fields = list(result)
            fields[6] = 0
            return os.stat_result(fields)
        return result

    def write(destination: Path) -> None:
        (destination / producer.BOOTSTRAP_FILENAME).write_bytes(content)

    monkeypatch.setattr(Path, "lstat", lstat)
    cli.download_writer = write
    with pytest.raises(bootstrap.GitHubBootstrapError, match="64 KiB"):
        bootstrap.get_bootstrap_artifact(checkout)


def test_other_artifact_files_are_not_read_or_logged(
    checkout: Path, cli: FakeCLI, capsys: pytest.CaptureFixture[str],
) -> None:
    def write(destination: Path) -> None:
        (destination / producer.BOOTSTRAP_FILENAME).write_text(
            json.dumps(artifact_document()), encoding="utf-8",
        )
        (destination / "unrelated-output.txt").write_text(BODY_SECRET, encoding="utf-8")

    cli.download_writer = write
    assert bootstrap.get_bootstrap_artifact(checkout).bindings.workspace_id == WORKSPACE
    assert capsys.readouterr() == ("", "")


def test_download_directory_creation_failure_is_redacted(
    checkout: Path, cli: FakeCLI, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        bootstrap, "TemporaryDirectory", Mock(side_effect=PermissionError(TOKEN_SECRET)),
    )
    with pytest.raises(bootstrap.GitHubBootstrapError, match="scoped bootstrap download") as caught:
        bootstrap.get_bootstrap_artifact(checkout)
    assert TOKEN_SECRET not in formatted_error(caught.value)
    assert RUN_URL in str(caught.value)
    assert not cli.matching("gh", "run", "download")
