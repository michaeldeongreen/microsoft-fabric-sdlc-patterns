"""Sync an already Git-connected Dev workspace using its service principal.

The tracked Dev bindings and pipeline source are checked before any cloud write.
Git credentials belong to the calling principal, not the human who originally
connected the workspace. A repository-scoped ShareableCloud GitHub PAT connection
is reused or created once; GITHUB_TOKEN is deliberately not a credential source.

Strict mode refuses outgoing changes and conflicts. Explicit source-authoritative
mode is ONLY for an integration workspace where authoring occurs elsewhere. It
can discard modifications to the existing baseline-managed semantic model, using
PreferRemote for incoming conflicts and Update Semantic Model Definition for
outgoing-only changes. It never deletes/recreates an item or writes to Git.
Canonical definition restoration must produce clean status or the run fails;
the API does not guarantee that every refresh-generated diff can be cleared.

Azure identity is optional at import time and required only by the CLI. It is
already declared in requirements-dev.txt and supplies ClientSecretCredential.

Required environment: AZURE_TENANT_ID, AZURE_CLIENT_ID, AZURE_CLIENT_SECRET,
FABRIC_WORKSPACE_ID, and FABRIC_GIT_REPOSITORY or GITHUB_REPOSITORY.
Optional: FABRIC_GIT_BRANCH (dev), FABRIC_GIT_COMMIT, FABRIC_GIT_CONNECTION_ID,
FABRIC_GITHUB_TOKEN (fine-grained PAT with Contents: Read; bootstrap/rotation).
Activity connections default to ServicePrincipal and reconcile the existing
Azure secret in place. FABRIC_RUNTIME_AUTHENTICATION=WorkspaceIdentity selects
preconfigured secretless connections without creating or authorizing a new WI.
FABRIC_CONNECTION_MODE=existing checks activity connections without rotating
credentials. Both modes require the tracked IDs and never recreate missing IDs.

Official contracts:
https://learn.microsoft.com/rest/api/fabric/core/git/update-from-git
https://learn.microsoft.com/rest/api/fabric/core/git/update-my-git-credentials
https://learn.microsoft.com/fabric/cicd/git-integration/git-automation
https://learn.microsoft.com/rest/api/fabric/semanticmodel/items/update-semantic-model-definition
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import re
import subprocess
import sys
import time
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Protocol
from urllib.parse import urlsplit
from uuid import UUID

import pipeline_bindings
from fabric_connections import FabricRestClient
from prepare_fabric_workspace import (
    runtime_authentication,
    runtime_credentials,
    validate_deployment_source,
)

DEFAULT_TIMEOUT_SECONDS = 1800
DEFAULT_BRANCH = "dev"
MODEL_DIRECTORY_NAME = "Patterns_Semantic_Model.SemanticModel"
FABRIC_SCOPE = "https://api.fabric.microsoft.com/.default"
SHA_PATTERN = re.compile(r"[0-9a-fA-F]{40}")
OWNER_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9-]{0,38}")
REPOSITORY_PATTERN = re.compile(r"[A-Za-z0-9_.-]{1,128}")
PAT_PATTERN = re.compile(r"github_pat_[A-Za-z0-9_]+")
CHANGE_TYPES = frozenset({"Added", "Modified", "Deleted"})
CONFLICT_TYPES = frozenset({"None", "Conflict", "SameChanges"})

SyncPolicy = Literal["strict", "source-authoritative"]
ActivityAuthentication = Literal["ServicePrincipal", "WorkspaceIdentity"]


class GitSyncError(ValueError):
    """An unsafe configuration, incomplete operation, or unexpected API result."""


class DevBindings(Protocol):
    workspace_id: str
    semantic_model_id: str
    notebook_connection_id: str
    refresh_connection_id: str

    @property
    def values(self) -> Mapping[str, str]: ...


@dataclass(frozen=True)
class GitSyncResult:
    workspace_id: str
    commit: str
    connection_id: str
    updated: bool
    restored_model: bool
    dry_run: bool


@dataclass(frozen=True)
class GitChange:
    item_type: str
    object_id: str | None
    logical_id: str | None
    workspace_change: str | None
    remote_change: str | None
    conflict_type: str
    file_changes: tuple[dict[str, object], ...]


@dataclass(frozen=True)
class GitStatus:
    workspace_head: str
    remote_commit: str
    changes: tuple[GitChange, ...]


@dataclass(frozen=True)
class ModelSource:
    logical_id: str
    display_name: str
    definition: dict[str, object]


def _guid(value: object, label: str) -> str:
    if not isinstance(value, str):
        raise GitSyncError(f"{label} must be a nonzero, hyphenated GUID.")
    try:
        parsed = UUID(value)
    except ValueError:
        raise GitSyncError(f"{label} must be a nonzero, hyphenated GUID.") from None
    if parsed.int == 0 or str(parsed) != value.lower():
        raise GitSyncError(f"{label} must be a nonzero, hyphenated GUID.")
    return str(parsed)


def _sha(value: object, label: str) -> str:
    if not isinstance(value, str) or SHA_PATTERN.fullmatch(value) is None:
        raise GitSyncError(f"{label} must be a full 40-character Git commit hash.")
    return value.lower()


def _repository(value: str) -> tuple[str, str]:
    parts = value.split("/")
    if (
        len(parts) != 2 or OWNER_PATTERN.fullmatch(parts[0]) is None
        or REPOSITORY_PATTERN.fullmatch(parts[1]) is None or parts[1] in {".", ".."}
    ):
        raise GitSyncError("The expected GitHub repository must be OWNER/REPOSITORY.")
    return parts[0], parts[1]


def _activity_authentication(value: str) -> ActivityAuthentication:
    if value == "ServicePrincipal":
        return "ServicePrincipal"
    if value == "WorkspaceIdentity":
        return "WorkspaceIdentity"
    raise GitSyncError("Runtime authentication must be ServicePrincipal or WorkspaceIdentity.")


def _directory(value: object) -> str:
    if not isinstance(value, str) or "\\" in value:
        raise GitSyncError("Git directory must be a relative, slash-separated path.")
    trimmed = value.strip("/")
    if trimmed and any(part in {"", ".", ".."} for part in trimmed.split("/")):
        raise GitSyncError("Git directory must be a relative, slash-separated path.")
    return trimmed


def _remaining(deadline: float) -> None:
    if time.monotonic() >= deadline:
        raise GitSyncError("Dev Git sync timed out; remote operations were not cancelled.")


def _request(
    client: FabricRestClient, deadline: float, method: str, path: str,
    body: dict[str, object] | None = None, *, wait_for_result: bool = True,
) -> dict[str, object]:
    _remaining(deadline)
    try:
        response = client.request(method, path, body, wait_for_result=wait_for_result)
    except TimeoutError:
        raise GitSyncError("Fabric operation timed out; remote operations were not cancelled.") from None
    except (OSError, RuntimeError, ValueError):
        raise GitSyncError(
            f"Fabric {method} request failed. Check permissions, capacity availability, "
            "supported item types, and the operation state; no remote operation was cancelled."
        ) from None
    _remaining(deadline)
    if not isinstance(response, dict):
        raise GitSyncError("Fabric returned a malformed response.")
    if "status" in response and response["status"] != "Succeeded":
        raise GitSyncError("Fabric operation did not complete successfully.")
    return response


def _list(client: FabricRestClient, deadline: float, path: str) -> list[dict[str, object]]:
    _remaining(deadline)
    try:
        response = client.list(path)
    except TimeoutError:
        raise GitSyncError("Fabric connection lookup timed out.") from None
    except (OSError, RuntimeError, ValueError):
        raise GitSyncError("Fabric connection lookup failed; check connection permissions.") from None
    _remaining(deadline)
    if not isinstance(response, list) or any(not isinstance(item, dict) for item in response):
        raise GitSyncError("Fabric returned a malformed connection list.")
    return response


def _source_bindings(repo_dir: Path, workspace_id: str) -> DevBindings:
    try:
        bindings = validate_deployment_source(repo_dir)
        bulk_bindings = validate_deployment_source(repo_dir, bulk=True)
    except ValueError:
        raise GitSyncError(
            "Dev pipeline source or its parameter contract does not match the tracked baseline. "
            "Prepare the Dev bindings and restore source with workspace_swap.py --swap-to-dev "
            "before committing and syncing."
        ) from None
    except OSError:
        raise GitSyncError("Tracked Dev bindings or source files are missing or unreadable.") from None
    if bindings != bulk_bindings:
        raise GitSyncError("Dev source and bulk parameter contracts do not agree on the tracked baseline.")
    if _guid(bindings.workspace_id, "Tracked Dev workspace") != workspace_id:
        raise GitSyncError("FABRIC_WORKSPACE_ID does not match the tracked Dev workspace.")
    for value in (
        bindings.semantic_model_id, bindings.notebook_connection_id, bindings.refresh_connection_id,
    ):
        _guid(value, "Tracked Dev binding")
    return bindings


def _ensure_activity_connections(
    client: FabricRestClient, workspace_id: str, bindings: DevBindings,
    *, authentication: ActivityAuthentication = "ServicePrincipal",
    credentials: Mapping[str, str] | None = None,
) -> None:
    from fabric_connections import ensure_pipeline_connections

    try:
        connections = ensure_pipeline_connections(
            client, workspace_id, mode="existing",
            notebook_connection_id=bindings.notebook_connection_id,
            refresh_connection_id=bindings.refresh_connection_id,
            authentication=authentication, credentials=credentials,
        )
    except (OSError, RuntimeError, ValueError):
        raise GitSyncError(
            "Canonical Dev activity connections are missing, inaccessible, or mismatched. "
            "Run the explicit Dev preparation flow; sync will not replace their GUIDs."
        ) from None
    expected = {
        "NOTEBOOK_CONNECTION_ID": bindings.notebook_connection_id.lower(),
        "SEMANTIC_MODEL_REFRESH_CONNECTION_ID": bindings.refresh_connection_id.lower(),
    }
    if connections != expected:
        raise GitSyncError("Activity connection validation changed the tracked Dev GUIDs.")


def _validate_workspace(response: dict[str, object], workspace_id: str) -> None:
    if _guid(response.get("id"), "Fabric workspace response") != workspace_id:
        raise GitSyncError("Fabric returned a different workspace than the tracked Dev workspace.")


def _validate_git_connection(
    response: dict[str, object], owner: str, repository: str, branch: str, directory: str,
) -> None:
    if response.get("gitConnectionState") != "ConnectedAndInitialized":
        raise GitSyncError(
            "Dev must already be ConnectedAndInitialized. Sync will not connect or initialize it."
        )
    if response.get("gitConnectionType") != "Full":
        raise GitSyncError("Dev requires a Full Git connection; selective or unknown sync is refused.")
    details = response.get("gitProviderDetails")
    if not isinstance(details, dict):
        raise GitSyncError("Fabric returned malformed Git provider details.")
    if (
        details.get("gitProviderType") != "GitHub"
        or not isinstance(details.get("ownerName"), str)
        or not isinstance(details.get("repositoryName"), str)
        or details["ownerName"].casefold() != owner.casefold()
        or details["repositoryName"].casefold() != repository.casefold()
        or details.get("branchName") != branch
        or _directory(details.get("directoryName")) != directory
        or details.get("customDomainName") not in (None, "", "github.com")
    ):
        raise GitSyncError("Dev Git connection does not match the expected GitHub repository, branch, or directory.")


def _validate_provider_connection(response: dict[str, object], expected_url: str) -> str:
    connection_id = _guid(response.get("id"), "Git credential connection")
    details = response.get("connectionDetails")
    credentials = response.get("credentialDetails")
    if (
        response.get("connectivityType") != "ShareableCloud" or not isinstance(details, dict)
        or details.get("type") != "GitHubSourceControl" or not isinstance(credentials, dict)
        or credentials.get("credentialType") != "Key"
    ):
        raise GitSyncError("Git credentials require a ShareableCloud GitHubSourceControl Key connection.")
    path = details.get("path")
    if not isinstance(path, str):
        raise GitSyncError("Git credential connection must be scoped to the expected repository.")
    try:
        url = urlsplit(path)
    except ValueError:
        raise GitSyncError("Git credential connection has an invalid repository URL.") from None
    if (
        url.scheme != "https" or url.netloc.casefold() != "github.com" or url.query or url.fragment
        or path.rstrip("/").casefold() != expected_url.casefold()
        or details.get("creationMethod", "GitHubSourceControl.Contents") != "GitHubSourceControl.Contents"
    ):
        raise GitSyncError("Git credential connection must be scoped to the expected repository.")
    return connection_id


def _credentials(response: dict[str, object]) -> str | None:
    source = response.get("source")
    if not isinstance(source, str):
        raise GitSyncError("Fabric returned an unknown or malformed caller Git credential configuration.")
    if source == "ConfiguredConnection":
        return _guid(response.get("connectionId"), "My Git credential connection")
    if source in {"None", "Automatic"} and "connectionId" not in response:
        return None
    raise GitSyncError("Fabric returned an unknown or malformed caller Git credential configuration.")


def _git_credentials(
    client: FabricRestClient, deadline: float, workspace_id: str, expected_url: str,
    connection_id: str | None, github_token: str | None, rotate_git_token: bool, dry_run: bool,
) -> str:
    own_path = f"/workspaces/{workspace_id}/git/myGitCredentials"
    configured = _credentials(_request(client, deadline, "GET", own_path))
    desired = connection_id or configured
    created = False
    if desired is not None:
        connection = _request(client, deadline, "GET", f"/connections/{desired}")
        if _validate_provider_connection(connection, expected_url) != desired:
            raise GitSyncError("Fabric returned a different Git credential connection.")
    else:
        name = f"Patterns-{workspace_id}-GitHub"
        matching = [item for item in _list(client, deadline, "/connections") if item.get("displayName") == name]
        if len(matching) > 1:
            raise GitSyncError("Multiple deterministic Git credential connections exist; specify an approved ID.")
        if matching:
            desired = _validate_provider_connection(matching[0], expected_url)
            connection = _request(client, deadline, "GET", f"/connections/{desired}")
            if _validate_provider_connection(connection, expected_url) != desired:
                raise GitSyncError("Fabric returned a different Git credential connection.")
        else:
            if dry_run:
                raise GitSyncError("Dry-run requires an existing Git credential connection and caller binding.")
            if not github_token:
                raise GitSyncError(
                    "No approved Git credential connection exists. Supply FABRIC_GITHUB_TOKEN "
                    "(fine-grained PAT with Contents: Read) once, or FABRIC_GIT_CONNECTION_ID. "
                    "GITHUB_TOKEN is not used by the Fabric GitHub connector."
                )
            body: dict[str, object] = {
                "connectivityType": "ShareableCloud",
                "displayName": name,
                "connectionDetails": {
                    "type": "GitHubSourceControl",
                    "creationMethod": "GitHubSourceControl.Contents",
                    "parameters": [{"dataType": "Text", "name": "url", "value": expected_url}],
                },
                "credentialDetails": {"credentials": {"credentialType": "Key", "key": github_token}},
            }
            connection = _request(client, deadline, "POST", "/connections", body)
            desired = _validate_provider_connection(connection, expected_url)
            created = True
    if rotate_git_token and not created:
        if dry_run:
            raise GitSyncError("Dry-run cannot rotate Git credentials.")
        _request(
            client, deadline, "PATCH", f"/connections/{desired}",
            {
                "connectivityType": "ShareableCloud",
                "credentialDetails": {"credentials": {"credentialType": "Key", "key": github_token}},
            },
        )
    if configured != desired:
        if dry_run:
            raise GitSyncError("Dry-run requires the SP's own Git credentials to be configured already.")
        updated = _request(
            client, deadline, "PATCH", own_path,
            {"source": "ConfiguredConnection", "connectionId": desired},
        )
        if _credentials(updated) != desired or _credentials(_request(client, deadline, "GET", own_path)) != desired:
            raise GitSyncError("The calling SP's Git credential binding was not verified.")
    return desired


def _change_type(response: dict[str, object], field: str) -> str | None:
    if field not in response:
        return None
    value = response[field]
    if not isinstance(value, str) or value not in CHANGE_TYPES:
        raise GitSyncError("Fabric returned an unknown or malformed Git change type.")
    return value


def _conflict_type(response: dict[str, object]) -> str:
    value = response.get("conflictType", "None")
    if not isinstance(value, str) or value not in CONFLICT_TYPES:
        raise GitSyncError("Fabric returned an unknown or malformed Git conflict type.")
    return value


def _status(response: dict[str, object]) -> GitStatus:
    workspace_head = _sha(response.get("workspaceHead"), "Workspace Git head")
    remote_commit = _sha(response.get("remoteCommitHash"), "Remote Git commit")
    items = response.get("changes")
    if not isinstance(items, list):
        raise GitSyncError("Fabric returned a malformed Git changes list.")
    changes: list[GitChange] = []
    seen_identifiers: set[str] = set()
    for item in items:
        if not isinstance(item, dict):
            raise GitSyncError("Fabric returned a malformed Git change.")
        metadata = item.get("itemMetadata")
        identifier = metadata.get("itemIdentifier") if isinstance(metadata, dict) else None
        if not isinstance(metadata, dict) or not isinstance(identifier, dict):
            raise GitSyncError("Git change is missing item metadata or identity.")
        item_type = metadata.get("itemType")
        if not isinstance(item_type, str) or not item_type:
            raise GitSyncError("Git change is missing its item type.")
        object_id = _guid(identifier["objectId"], "Git item object ID") if "objectId" in identifier else None
        logical_id = _guid(identifier["logicalId"], "Git item logical ID") if "logicalId" in identifier else None
        if object_id is None and logical_id is None:
            raise GitSyncError("Git change is missing an item identifier.")
        identifiers = {value for value in (object_id, logical_id) if value is not None}
        if seen_identifiers.intersection(identifiers):
            raise GitSyncError("Fabric returned duplicate or ambiguous Git item changes.")
        seen_identifiers.update(identifiers)
        workspace_change = _change_type(item, "workspaceChange")
        remote_change = _change_type(item, "remoteChange")
        conflict_type = _conflict_type(item)
        if workspace_change is None and remote_change is None:
            raise GitSyncError("Git change does not identify a workspace or remote change.")
        if conflict_type != "None" and (workspace_change is None or remote_change is None):
            raise GitSyncError("Git conflict is missing one side of its change.")
        files = item.get("fileChanges", [])
        if not isinstance(files, list):
            raise GitSyncError("Fabric returned malformed Git file changes.")
        for file in files:
            if not isinstance(file, dict) or not isinstance(file.get("path"), str):
                raise GitSyncError("Fabric returned malformed Git file changes.")
            if _directory(file["path"]) != file["path"] or not file["path"]:
                raise GitSyncError("Git file change has an unsafe path.")
            file_workspace = _change_type(file, "workspaceChange")
            file_remote = _change_type(file, "remoteChange")
            if (
                (file_workspace is not None and workspace_change is None)
                or (file_remote is not None and remote_change is None)
                or (file_workspace is None and file_remote is None)
                or (_conflict_type(file) != "None" and conflict_type == "None")
            ):
                raise GitSyncError("Git file changes disagree with their item's status.")
        changes.append(
            GitChange(item_type, object_id, logical_id, workspace_change, remote_change, conflict_type, tuple(files))
        )
    if workspace_head == remote_commit and any(change.remote_change for change in changes):
        raise GitSyncError("Git status has incoming changes despite equal commit heads.")
    return GitStatus(workspace_head, remote_commit, tuple(changes))


def _get_status(client: FabricRestClient, deadline: float, workspace_id: str) -> GitStatus:
    return _status(
        _request(client, deadline, "GET", f"/workspaces/{workspace_id}/git/status?includeFilesDetails=true")
    )


def _git_output(git_root: Path, arguments: list[str]) -> str:
    try:
        return subprocess.run(
            ["git", "-C", str(git_root), *arguments], check=True, capture_output=True,
            text=True, encoding="utf-8",
        ).stdout
    except (OSError, subprocess.CalledProcessError):
        raise GitSyncError("Unable to verify the canonical model's checked-out Git source.") from None


def _verify_checkout(repo_dir: Path, git_root: Path, expected_commit: str | None) -> str:
    commit = _sha(_git_output(git_root, ["rev-parse", "--verify", "HEAD"]).strip(), "Checked-out commit")
    if expected_commit is not None and commit != expected_commit:
        raise GitSyncError("Git sync requires the exact target commit checked out.")
    manifest = pipeline_bindings.dev_bindings_path(repo_dir)
    pipelines = pipeline_bindings.pipeline_files(repo_dir)
    if not pipelines:
        raise GitSyncError("Canonical Dev pipeline source is missing.")
    tracked = [manifest.relative_to(git_root).as_posix(), *(path.relative_to(git_root).as_posix() for path in pipelines)]
    if set(_git_output(git_root, ["ls-files", "--error-unmatch", "--", *tracked]).splitlines()) != set(tracked):
        raise GitSyncError("Dev bindings and pipeline source must be tracked at the checked-out commit.")
    if _git_output(
        git_root, ["diff", "--name-only", "HEAD", "--", repo_dir.relative_to(git_root).as_posix(), tracked[0]],
    ).strip():
        raise GitSyncError("Canonical Fabric source or Dev bindings has local changes; commit the baseline before syncing.")
    return commit


def _model_source(repo_dir: Path, git_root: Path, commit: str) -> ModelSource:
    if _sha(_git_output(git_root, ["rev-parse", "--verify", "HEAD"]).strip(), "Checked-out commit") != commit:
        raise GitSyncError("Source-authoritative recovery requires the exact target commit checked out.")
    model_dir = repo_dir / MODEL_DIRECTORY_NAME
    relative = model_dir.relative_to(git_root).as_posix()
    if _git_output(git_root, ["diff", "--name-only", "HEAD", "--", relative]).strip():
        raise GitSyncError("Canonical model source has local changes; recovery will not use uncommitted content.")
    files = _git_output(git_root, ["ls-files", "-z", "--", relative]).split("\0")
    files = [name for name in files if name]
    if len(set(files)) != len(files):
        raise GitSyncError("Canonical model source contains duplicate definition parts.")
    parts: list[dict[str, object]] = []
    part_paths: set[str] = set()
    for name in sorted(files):
        if not name.startswith(f"{relative}/"):
            raise GitSyncError("Canonical model source contains a file outside its item directory.")
        part = name[len(relative) + 1:]
        if _directory(part) != part or not part:
            raise GitSyncError("Canonical model source contains an unsafe definition path.")
        path = model_dir / part
        if path.is_symlink() or not path.resolve().is_relative_to(model_dir.resolve()):
            raise GitSyncError("Canonical model source must not contain links outside its item directory.")
        if (
            part not in {".platform", "definition.pbism", "model.bim", "diagramLayout.json"}
            and not (part.startswith("definition/") and part.endswith(".tmdl"))
            and not part.startswith("Copilot/")
        ):
            raise GitSyncError("Canonical model source contains an unsupported public definition part.")
        try:
            with path.open("rb") as stream:
                payload = base64.b64encode(stream.read()).decode("ascii")
        except OSError:
            raise GitSyncError("Canonical model definition part is missing or unreadable.") from None
        parts.append({"path": part, "payload": payload, "payloadType": "InlineBase64"})
        part_paths.add(part)
    tmdl = any(part.startswith("definition/") for part in part_paths)
    if (
        ".platform" not in part_paths or "definition.pbism" not in part_paths
        or tmdl == ("model.bim" in part_paths)
    ):
        raise GitSyncError("Canonical semantic model requires .platform, definition.pbism, and TMDL or TMSL.")
    try:
        platform = json.loads((model_dir / ".platform").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        raise GitSyncError("Canonical semantic model metadata is missing or invalid.") from None
    metadata = platform.get("metadata") if isinstance(platform, dict) else None
    config = platform.get("config") if isinstance(platform, dict) else None
    if (
        not isinstance(metadata, dict) or metadata.get("type") != "SemanticModel"
        or not isinstance(metadata.get("displayName"), str) or not metadata["displayName"]
        or not isinstance(config, dict)
    ):
        raise GitSyncError("Canonical semantic model metadata is missing or invalid.")
    return ModelSource(
        _guid(config.get("logicalId"), "Canonical model logical ID"), metadata["displayName"],
        {"parts": parts},
    )


def _validate_changes(
    status: GitStatus, policy: SyncPolicy, bindings: DevBindings, model: ModelSource | None,
) -> None:
    for change in status.changes:
        if change.workspace_change is None and change.conflict_type == "None":
            continue
        if policy == "strict":
            raise GitSyncError(
                "Dev has outgoing workspace changes or conflicts. Strict sync will not overwrite them. "
                "Resolve them outside automation; only an explicitly dedicated integration workspace "
                "may opt into --policy source-authoritative."
            )
        if (
            model is None or change.item_type != "SemanticModel"
            or change.object_id != bindings.semantic_model_id.lower()
            or (change.logical_id is not None and change.logical_id != model.logical_id)
            or change.workspace_change != "Modified" or change.remote_change not in {None, "Modified"}
            or any(
                file.get("workspaceChange") is not None and file["path"] == ".platform"
                for file in change.file_changes
            )
        ):
            raise GitSyncError(
                "Source-authoritative recovery permits only definition modifications to the existing "
                "baseline-managed semantic model. Workspace additions, deletions, metadata edits, "
                "and unrelated items require explicit operator resolution."
            )


def sync_workspace(
    client: FabricRestClient, repository_directory: Path, *, workspace_id: str, repository: str,
    git_root: Path | None = None, branch: str = DEFAULT_BRANCH, expected_commit: str | None = None,
    connection_id: str | None = None, github_token: str | None = None, rotate_git_token: bool = False,
    policy: SyncPolicy = "strict", timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
    dry_run: bool = False, authentication: ActivityAuthentication = "ServicePrincipal",
    credentials: Mapping[str, str] | None = None,
) -> GitSyncResult:
    """Validate, bind the caller's credentials, sync, and verify; never start ETL."""
    workspace_id = _guid(workspace_id, "FABRIC_WORKSPACE_ID")
    owner, repository_name = _repository(repository)
    if policy not in {"strict", "source-authoritative"}:
        raise GitSyncError("Unknown Git sync policy.")
    if authentication not in {"ServicePrincipal", "WorkspaceIdentity"}:
        raise GitSyncError("Unknown activity connection authentication.")
    if credentials is not None:
        if authentication != "ServicePrincipal":
            raise GitSyncError("WorkspaceIdentity connections must not receive service-principal secrets.")
        if set(credentials) != {"tenantId", "servicePrincipalClientId", "servicePrincipalSecret"}:
            raise GitSyncError("Activity credentials require tenantId, servicePrincipalClientId, and servicePrincipalSecret.")
        _guid(credentials["tenantId"], "Activity credential tenant ID")
        _guid(credentials["servicePrincipalClientId"], "Activity credential client ID")
        if not isinstance(credentials["servicePrincipalSecret"], str) or not credentials["servicePrincipalSecret"]:
            raise GitSyncError("Activity credential secret must be set.")
    if not branch or branch != branch.strip() or any(char in branch for char in "\r\n\\"):
        raise GitSyncError("The expected Git branch must be a nonempty branch name.")
    if isinstance(timeout_seconds, bool) or not isinstance(timeout_seconds, int) or timeout_seconds <= 0:
        raise GitSyncError("Git sync timeout must be a positive number of seconds.")
    if expected_commit is not None:
        expected_commit = _sha(expected_commit, "FABRIC_GIT_COMMIT")
    if connection_id is not None:
        connection_id = _guid(connection_id, "FABRIC_GIT_CONNECTION_ID")
    if github_token is not None and PAT_PATTERN.fullmatch(github_token) is None:
        raise GitSyncError(
            "FABRIC_GITHUB_TOKEN must be a fine-grained GitHub PAT with Contents: Read, "
            "not an Actions installation token."
        )
    if rotate_git_token and not github_token:
        raise GitSyncError("--rotate-git-token requires FABRIC_GITHUB_TOKEN.")
    root = (git_root or Path(__file__).resolve().parents[1]).resolve()
    repo_dir = repository_directory if repository_directory.is_absolute() else root / repository_directory
    repo_dir = repo_dir.resolve()
    if not repo_dir.is_relative_to(root) or not repo_dir.is_dir():
        raise GitSyncError("The Fabric repository directory must exist inside the Git root.")
    if not pipeline_bindings.dev_bindings_path(repo_dir).is_relative_to(root):
        raise GitSyncError("The sibling Dev bindings manifest must also be inside the Git root.")
    directory = _directory(repo_dir.relative_to(root).as_posix()) if repo_dir != root else ""
    bindings = _source_bindings(repo_dir, workspace_id)
    checked_out_commit = _verify_checkout(repo_dir, root, expected_commit)
    model = _model_source(repo_dir, root, expected_commit) if policy == "source-authoritative" and expected_commit else None
    deadline = time.monotonic() + timeout_seconds
    workspace_path = f"/workspaces/{workspace_id}"
    _validate_workspace(_request(client, deadline, "GET", workspace_path), workspace_id)
    connection_path = f"{workspace_path}/git/connection"
    _validate_git_connection(
        _request(client, deadline, "GET", connection_path), owner, repository_name, branch, directory,
    )
    _ensure_activity_connections(
        client, workspace_id, bindings, authentication=authentication,
        credentials=None if dry_run else credentials,
    )
    _remaining(deadline)
    credential_id = _git_credentials(
        client, deadline, workspace_id, f"https://github.com/{owner}/{repository_name}",
        connection_id, github_token, rotate_git_token, dry_run,
    )
    status = _get_status(client, deadline, workspace_id)
    target = expected_commit or status.remote_commit
    if status.remote_commit != target:
        raise GitSyncError("Remote Git commit does not match the expected pushed commit; no items were synced.")
    if checked_out_commit != target:
        raise GitSyncError("Checked-out canonical source does not match the remote Git commit; no items were synced.")
    if policy == "source-authoritative" and model is None:
        model = _model_source(repo_dir, root, target)
    _validate_changes(status, policy, bindings, model)
    updated = status.workspace_head != target
    if dry_run:
        return GitSyncResult(workspace_id, target, credential_id, updated, False, True)
    if updated:
        body: dict[str, object] = {
            "workspaceHead": status.workspace_head, "remoteCommitHash": target,
            "options": {"allowOverrideItems": policy == "source-authoritative"},
        }
        if policy == "source-authoritative":
            body["conflictResolution"] = {
                "conflictResolutionType": "Workspace", "conflictResolutionPolicy": "PreferRemote",
            }
        _request(
            client, deadline, "POST", f"{workspace_path}/git/updateFromGit", body,
            wait_for_result=False,
        )
        status = _get_status(client, deadline, workspace_id)
    if status.workspace_head != target or status.remote_commit != target:
        raise GitSyncError("Dev Git heads changed or failed to reach the requested commit.")
    _validate_changes(status, policy, bindings, model)
    restored = False
    if policy == "source-authoritative" and status.changes:
        if any(change.remote_change is not None for change in status.changes):
            raise GitSyncError("Incoming Git changes remain after update; model recovery will not run.")
        if model is None:
            raise GitSyncError("Canonical model source is unavailable.")
        item_path = f"{workspace_path}/semanticModels/{bindings.semantic_model_id}"
        item = _request(client, deadline, "GET", item_path)
        if (
            _guid(item.get("id"), "Managed model response") != bindings.semantic_model_id.lower()
            or _guid(item.get("workspaceId"), "Managed model workspace") != workspace_id
            or item.get("type") != "SemanticModel" or item.get("displayName") != model.display_name
        ):
            raise GitSyncError("Managed model identity or metadata does not match the canonical source.")
        _request(
            client, deadline, "POST", f"{item_path}/updateDefinition?updateMetadata=false",
            {"definition": model.definition}, wait_for_result=False,
        )
        restored = True
    final = _get_status(client, deadline, workspace_id)
    _validate_git_connection(
        _request(client, deadline, "GET", connection_path), owner, repository_name, branch, directory,
    )
    if final.workspace_head != target or final.remote_commit != target or final.changes:
        raise GitSyncError(
            "Dev Git sync did not finish at clean, matching heads. No ETL should start. "
            "Canonical definition restoration may not clear this runtime diff; operator investigation is required."
        )
    return GitSyncResult(workspace_id, target, credential_id, updated, restored, False)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository-directory", "--repository_directory", type=Path, default=Path("data") / "fabric")
    parser.add_argument("--git-root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--workspace-id", default=os.environ.get("FABRIC_WORKSPACE_ID", ""))
    parser.add_argument("--repository", default=os.environ.get("FABRIC_GIT_REPOSITORY") or os.environ.get("GITHUB_REPOSITORY", ""))
    parser.add_argument("--branch", default=os.environ.get("FABRIC_GIT_BRANCH", DEFAULT_BRANCH))
    parser.add_argument("--commit", default=os.environ.get("FABRIC_GIT_COMMIT") or None)
    parser.add_argument("--git-connection-id", default=os.environ.get("FABRIC_GIT_CONNECTION_ID") or None)
    parser.add_argument("--rotate-git-token", action="store_true")
    parser.add_argument("--policy", choices=("strict", "source-authoritative"), default="strict")
    parser.add_argument(
        "--authentication", choices=("ServicePrincipal", "WorkspaceIdentity"),
        default=None,
        help="Existing activity connection profile; Git authentication always uses its own PAT connection.",
    )
    parser.add_argument(
        "--connection-mode", choices=("auto", "existing"),
        default=os.environ.get("FABRIC_CONNECTION_MODE", "auto"),
        help="Auto reconciles SP secrets; existing checks activity connections without writes. IDs are always preserved.",
    )
    parser.add_argument("--timeout-seconds", type=int, default=DEFAULT_TIMEOUT_SECONDS)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    try:
        from azure.core.exceptions import AzureError
        from azure.identity import ClientSecretCredential
        from fabric_connections import FabricRestClient
    except ImportError:
        print("Dev Git sync requires the runtime dependencies in requirements-dev.txt.", file=sys.stderr)
        return 1
    try:
        if args.connection_mode not in {"auto", "existing"}:
            raise GitSyncError("FABRIC_CONNECTION_MODE must be auto or existing.")
        try:
            authentication = _activity_authentication(args.authentication or runtime_authentication())
            connection_credentials = runtime_credentials(
                authentication, required=args.connection_mode != "existing",
            )
        except ValueError:
            raise GitSyncError("Runtime connection authentication or Azure credentials are invalid.") from None
        tenant_id = _guid(os.environ.get("AZURE_TENANT_ID"), "AZURE_TENANT_ID")
        client_id = _guid(os.environ.get("AZURE_CLIENT_ID"), "AZURE_CLIENT_ID")
        secret = os.environ.get("AZURE_CLIENT_SECRET")
        if not secret:
            raise GitSyncError("AZURE_CLIENT_SECRET must be set.")
        if args.timeout_seconds <= 0:
            raise GitSyncError("Git sync timeout must be a positive number of seconds.")
        with ClientSecretCredential(tenant_id=tenant_id, client_id=client_id, client_secret=secret) as credential:
            client = FabricRestClient(
                lambda: credential.get_token(FABRIC_SCOPE).token,
                timeout=min(30, args.timeout_seconds), operation_timeout=args.timeout_seconds,
            )
            result = sync_workspace(
                client, args.repository_directory, workspace_id=args.workspace_id,
                repository=args.repository, git_root=args.git_root, branch=args.branch,
                expected_commit=args.commit, connection_id=args.git_connection_id,
                github_token=os.environ.get("FABRIC_GITHUB_TOKEN") or None,
                rotate_git_token=args.rotate_git_token, policy=args.policy,
                timeout_seconds=args.timeout_seconds, dry_run=args.dry_run,
                authentication=authentication,
                credentials=connection_credentials,
            )
    except GitSyncError as exc:
        print(f"Dev Git sync failed: {exc}", file=sys.stderr)
        return 1
    except AzureError:
        print("Dev Git sync failed: service-principal authentication failed.", file=sys.stderr)
        return 1
    action = "preflight checked (dry-run; no writes)" if result.dry_run else "synced and verified clean"
    print(
        f"Dev workspace {result.workspace_id}: {action} at {result.commit}; "
        f"Git connection {result.connection_id}; model restored: {result.restored_model}. "
        "This command did not start an ETL job."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
