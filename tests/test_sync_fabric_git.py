"""Offline Git sync tests; fixture files stay inside this project's directory."""

from __future__ import annotations

import base64
import copy
import json
import secrets
import shutil
import sys
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType, SimpleNamespace
from urllib.parse import urlsplit

import pytest

import pipeline_bindings
import sync_fabric_git as sync
from fabric_connections import FabricRestClient

WORKSPACE = "d7270f11-feba-4990-baa6-d45e47f23737"
MODEL = "62112b80-9cb4-4d65-befa-a8e9e6271ef0"
LOGICAL_MODEL = "a21bb471-7f10-923f-481f-2af1bbc0fb79"
NOTEBOOK_CONNECTION = "aaaaaaa1-1111-4111-8111-111111111111"
REFRESH_CONNECTION = "bbbbbbb2-2222-4222-8222-222222222222"
GIT_CONNECTION = "ccccccc3-3333-4333-8333-333333333333"
OTHER_CONNECTION = "ddddddd4-4444-4444-8444-444444444444"
OTHER_ITEM = "eeeeeee5-5555-4555-8555-555555555555"
OLD_COMMIT = "a" * 40
COMMIT = "b" * 40
OTHER_COMMIT = "c" * 40
REPOSITORY = "example/patterns"
REPOSITORY_URL = f"https://github.com/{REPOSITORY}"
PAT = "github_pat_FAKE_READ_ONLY_SECRET"
SECRET_MARKER = "NEVER_SHOW_REMOTE_SECRET"
ROOT = Path(__file__).resolve().parents[1]
ORIGINAL_ENSURE_ACTIVITY_CONNECTIONS = sync._ensure_activity_connections
ORIGINAL_LOAD_DEV_BINDINGS = pipeline_bindings.load_dev_bindings


@dataclass
class Bindings:
    workspace_id: str = WORKSPACE
    semantic_model_id: str = MODEL
    notebook_connection_id: str = NOTEBOOK_CONNECTION
    refresh_connection_id: str = REFRESH_CONNECTION

    @property
    def values(self) -> dict[str, str]:
        return {
            "Semantic model": self.semantic_model_id,
            "Notebook connection": self.notebook_connection_id,
            "Refresh connection": self.refresh_connection_id,
        }


@dataclass
class Source:
    root: Path
    fabric: Path
    bindings: Bindings
    git_state: dict[str, str]
    activity_checks: list[tuple[object, str, object, dict[str, object]]]
    source_checks: list[bool]


def provider_connection(connection_id: str = GIT_CONNECTION) -> dict[str, object]:
    return {
        "id": connection_id,
        "displayName": f"Patterns-{WORKSPACE}-GitHub",
        "connectivityType": "ShareableCloud",
        "connectionDetails": {"type": "GitHubSourceControl", "path": REPOSITORY_URL},
        "credentialDetails": {"credentialType": "Key"},
    }


def git_connection() -> dict[str, object]:
    return {
        "gitConnectionState": "ConnectedAndInitialized",
        "gitConnectionType": "Full",
        "gitProviderDetails": {
            "gitProviderType": "GitHub",
            "ownerName": "example",
            "repositoryName": "patterns",
            "branchName": "dev",
            "directoryName": "data/fabric",
        },
    }


def change(
    *, workspace: str | None = None, remote: str | None = "Modified",
    conflict: str = "None", item_type: str = "SemanticModel",
    object_id: str = MODEL, logical_id: str = LOGICAL_MODEL,
) -> dict[str, object]:
    item: dict[str, object] = {
        "itemMetadata": {
            "itemIdentifier": {"objectId": object_id, "logicalId": logical_id},
            "itemType": item_type,
            "displayName": "Patterns_Semantic_Model",
        },
        "conflictType": conflict,
    }
    if workspace is not None:
        item["workspaceChange"] = workspace
    if remote is not None:
        item["remoteChange"] = remote
    return item


def status(
    workspace_head: str = OLD_COMMIT, remote_commit: str = COMMIT,
    changes: list[dict[str, object]] | None = None,
) -> dict[str, object]:
    return {
        "workspaceHead": workspace_head,
        "remoteCommitHash": remote_commit,
        "changes": [change()] if changes is None else changes,
    }


class FakeClient(FabricRestClient):
    def __init__(self) -> None:
        super().__init__(lambda: "FAKE_FABRIC_TOKEN")
        self.calls: list[tuple[str, str, dict[str, object] | None, bool]] = []
        self.workspace: dict[str, object] = {"id": WORKSPACE}
        self.git = git_connection()
        self.configured: str | None = GIT_CONNECTION
        self.credential_response: dict[str, object] | None = None
        self.providers = {GIT_CONNECTION: provider_connection()}
        self.catalog: list[dict[str, object]] = [provider_connection()]
        self.current_status = status()
        self.status_sequence: list[dict[str, object]] = []
        self.update_residual: list[dict[str, object]] = []
        self.model: dict[str, object] = {
            "id": MODEL, "workspaceId": WORKSPACE,
            "type": "SemanticModel", "displayName": "Patterns_Semantic_Model",
        }
        self.failures: dict[tuple[str, str], Exception] = {}
        self.update_response: dict[str, object] = {}
        self.bind_response: dict[str, object] | None = None
        self.restore_clears_changes = True
        self.on_request = lambda: None

    @property
    def writes(self) -> list[tuple[str, str, dict[str, object] | None, bool]]:
        return [call for call in self.calls if call[0] in {"POST", "PATCH", "DELETE"}]

    def request(
        self, method: str, path: str, body: dict[str, object] | None = None,
        *, wait_for_result: bool = True,
    ) -> dict[str, object]:
        self.calls.append((method, path, copy.deepcopy(body), wait_for_result))
        self.on_request()
        if (method, path) in self.failures:
            raise self.failures[(method, path)]
        if method == "GET" and path == f"/workspaces/{WORKSPACE}":
            return copy.deepcopy(self.workspace)
        if method == "GET" and path == f"/workspaces/{WORKSPACE}/git/connection":
            return copy.deepcopy(self.git)
        if path == f"/workspaces/{WORKSPACE}/git/myGitCredentials":
            if method == "GET":
                if self.credential_response is not None:
                    return copy.deepcopy(self.credential_response)
                if self.configured is None:
                    return {"source": "None"}
                return {"source": "ConfiguredConnection", "connectionId": self.configured}
            if method == "PATCH":
                assert body is not None
                self.configured = str(body["connectionId"])
                return copy.deepcopy(self.bind_response if self.bind_response is not None else body)
        if method == "GET" and path.startswith("/connections/"):
            return copy.deepcopy(self.providers[path.rsplit("/", 1)[1]])
        if method == "POST" and path == "/connections":
            created = provider_connection()
            self.providers[GIT_CONNECTION] = created
            return copy.deepcopy(created)
        if method == "PATCH" and path.startswith("/connections/"):
            return copy.deepcopy(self.providers[path.rsplit("/", 1)[1]])
        if method == "GET" and path == f"/workspaces/{WORKSPACE}/git/status?includeFilesDetails=true":
            if self.status_sequence:
                return copy.deepcopy(self.status_sequence.pop(0))
            return copy.deepcopy(self.current_status)
        if method == "POST" and path == f"/workspaces/{WORKSPACE}/git/updateFromGit":
            assert body is not None
            self.current_status = status(str(body["remoteCommitHash"]), str(body["remoteCommitHash"]), self.update_residual)
            return copy.deepcopy(self.update_response)
        if method == "GET" and path == f"/workspaces/{WORKSPACE}/semanticModels/{MODEL}":
            return copy.deepcopy(self.model)
        if method == "POST" and path == f"/workspaces/{WORKSPACE}/semanticModels/{MODEL}/updateDefinition?updateMetadata=false":
            if self.restore_clears_changes:
                self.current_status["changes"] = []
            return {}
        raise AssertionError(f"Unexpected offline request: {method} {path}")

    def list(self, path: str) -> list[dict[str, object]]:
        self.calls.append(("LIST", path, None, True))
        if ("LIST", path) in self.failures:
            raise self.failures[("LIST", path)]
        assert path == "/connections"
        return copy.deepcopy(self.catalog)


@pytest.fixture
def source(monkeypatch: pytest.MonkeyPatch) -> Iterator[Source]:
    for name in (
        "FABRIC_GIT_CONNECTION_ID", "FABRIC_GITHUB_TOKEN", "FABRIC_GIT_BRANCH",
        "FABRIC_GIT_COMMIT", "FABRIC_RUNTIME_AUTHENTICATION", "FABRIC_CONNECTION_MODE",
    ):
        monkeypatch.delenv(name, raising=False)
    parent = ROOT / ".sync-git-test-fixtures"
    root = parent / secrets.token_hex(8)
    fabric = root / "data" / "fabric"
    model_dir = fabric / sync.MODEL_DIRECTORY_NAME
    pipeline_dir = fabric / "Patterns_Load_Validate_And_Refresh.DataPipeline"
    model_dir.mkdir(parents=True)
    pipeline_dir.mkdir()
    bindings = Bindings()
    platform = {
        "metadata": {"type": "SemanticModel", "displayName": "Patterns_Semantic_Model"},
        "config": {"version": "2.0", "logicalId": LOGICAL_MODEL},
    }
    (model_dir / ".platform").write_text(json.dumps(platform), encoding="utf-8")
    (model_dir / "definition.pbism").write_text('{"version":"4.0"}\n', encoding="utf-8")
    definition = model_dir / "definition"
    definition.mkdir()
    (definition / "database.tmdl").write_text("database\r\n\tcompatibilityLevel: 1604\r\n", encoding="utf-8")
    (definition / "model.tmdl").write_text("model Model\n", encoding="utf-8")
    pipeline = {
        "properties": {
            "activities": [
                {
                    "name": name, "type": "TridentNotebook",
                    "typeProperties": {"notebookId": logical_id, "workspaceId": pipeline_bindings.ZERO_GUID},
                    "externalReferences": {"connection": NOTEBOOK_CONNECTION},
                }
                for name, logical_id in (
                    ("Import_Patterns_Data", "3f21b546-f49f-9fef-4881-99b654a6701e"),
                    ("Validate_Patterns_Data", "decdcb11-8770-4216-8a28-eadf505d2679"),
                )
            ] + [
                {
                    "name": "Refresh_Patterns_Semantic_Model", "type": "PBISemanticModelRefresh",
                    "typeProperties": {"groupId": WORKSPACE, "datasetId": MODEL},
                    "externalReferences": {"connection": REFRESH_CONNECTION},
                }
            ]
        }
    }
    (pipeline_dir / "pipeline-content.json").write_text(json.dumps(pipeline), encoding="utf-8")
    git_state = {"head": COMMIT, "dirty": ""}
    activity_checks: list[tuple[object, str, object, dict[str, object]]] = []
    source_checks: list[bool] = []

    def git_output(_root: Path, arguments: list[str]) -> str:
        assert _root == root
        if arguments[:2] == ["rev-parse", "--verify"]:
            return git_state["head"]
        if arguments[:2] == ["diff", "--name-only"]:
            return git_state["dirty"]
        if arguments[:2] == ["ls-files", "-z"]:
            relative = arguments[-1]
            files = [
                path.relative_to(root).as_posix()
                for path in model_dir.rglob("*") if path.is_file()
            ]
            assert relative == model_dir.relative_to(root).as_posix()
            return "\0".join(files) + "\0"
        if arguments[:2] == ["ls-files", "--error-unmatch"]:
            return "\n".join(arguments[3:])
        raise AssertionError(f"Unexpected offline Git command: {arguments}")

    monkeypatch.setattr(pipeline_bindings, "load_dev_bindings", lambda _directory: bindings, raising=False)

    def source_guard(directory: Path, *, bulk: bool = False) -> Bindings:
        source_checks.append(bulk)
        loaded = pipeline_bindings.load_dev_bindings(directory)
        pipeline_bindings.validate_pipeline_source(directory, loaded.workspace_id, loaded.values)
        return loaded

    monkeypatch.setattr(sync, "validate_deployment_source", source_guard)
    monkeypatch.setattr(sync, "_git_output", git_output)
    monkeypatch.setattr(
        sync, "_ensure_activity_connections",
        lambda client, workspace_id, baseline, **kwargs: activity_checks.append((client, workspace_id, baseline, kwargs)),
    )
    try:
        yield Source(root, fabric, bindings, git_state, activity_checks, source_checks)
    finally:
        shutil.rmtree(root)
        if parent.exists() and not any(parent.iterdir()):
            parent.rmdir()


def run(source: Source, client: FakeClient, **kwargs: object) -> sync.GitSyncResult:
    options: dict[str, object] = {
        "workspace_id": WORKSPACE, "repository": REPOSITORY, "git_root": source.root,
        "expected_commit": COMMIT,
    }
    options.update(kwargs)
    return sync.sync_workspace(client, source.fabric, **options)


def test_strict_sync_uses_status_hashes_and_result_free_lro(source: Source) -> None:
    client = FakeClient()
    result = run(source, client)
    assert result == sync.GitSyncResult(WORKSPACE, COMMIT, GIT_CONNECTION, True, False, False)
    assert client.writes == [
        (
            "POST", f"/workspaces/{WORKSPACE}/git/updateFromGit",
            {
                "workspaceHead": OLD_COMMIT,
                "remoteCommitHash": COMMIT,
                "options": {"allowOverrideItems": False},
            },
            False,
        )
    ]
    assert source.activity_checks == [
        (client, WORKSPACE, source.bindings, {"authentication": "ServicePrincipal", "credentials": None})
    ]
    assert source.source_checks == [False, True]
    assert all(call[3] for call in client.calls if "/git/status" in call[1])
    assert not any(word in call[1] for call in client.calls for word in ("initialize", "connectTo", "commitToGit"))


def test_repeat_reuses_credentials_and_preserves_workspace_and_model_ids(source: Source) -> None:
    client = FakeClient()
    first = run(source, client)
    before = len(client.writes)
    second = run(source, client)
    assert first.updated and not second.updated
    assert len(client.writes) == before
    assert first.workspace_id == second.workspace_id == source.bindings.workspace_id
    assert first.connection_id == second.connection_id == GIT_CONNECTION
    assert source.bindings.semantic_model_id == MODEL
    assert not any(call[0] == "DELETE" for call in client.calls)


def test_no_incoming_item_changes_still_advances_changed_commit_head(source: Source) -> None:
    client = FakeClient()
    client.current_status["changes"] = []
    assert run(source, client).updated
    assert len(client.writes) == 1


def test_existing_sp_configured_connection_requires_no_pat_or_new_connection(source: Source) -> None:
    client = FakeClient()
    client.providers[GIT_CONNECTION]["displayName"] = "Enterprise approved read-only Git"
    run(source, client)
    assert not any(call[1] == "/connections" for call in client.calls)
    assert not any(call[0] == "PATCH" for call in client.calls)


def test_reuses_deterministic_connection_and_binds_only_caller_credentials(source: Source) -> None:
    client = FakeClient()
    client.configured = None
    run(source, client)
    binding = [call for call in client.writes if call[0] == "PATCH"]
    assert binding == [
        (
            "PATCH", f"/workspaces/{WORKSPACE}/git/myGitCredentials",
            {"source": "ConfiguredConnection", "connectionId": GIT_CONNECTION}, True,
        )
    ]
    assert not any(call[0] == "POST" and call[1] == "/connections" for call in client.calls)
    assert len([call for call in client.calls if call[0] == "GET" and call[1].endswith("myGitCredentials")]) == 2


def test_creates_scoped_pat_connection_once_then_reuses_without_pat(source: Source) -> None:
    client = FakeClient()
    client.configured = None
    client.catalog = []
    run(source, client, github_token=PAT)
    create = next(call for call in client.calls if call[:2] == ("POST", "/connections"))
    assert create[2] == {
        "connectivityType": "ShareableCloud",
        "displayName": f"Patterns-{WORKSPACE}-GitHub",
        "connectionDetails": {
            "type": "GitHubSourceControl",
            "creationMethod": "GitHubSourceControl.Contents",
            "parameters": [{"dataType": "Text", "name": "url", "value": REPOSITORY_URL}],
        },
        "credentialDetails": {"credentials": {"credentialType": "Key", "key": PAT}},
    }
    assert run(source, client).connection_id == GIT_CONNECTION
    assert len([call for call in client.calls if call[:2] == ("POST", "/connections")]) == 1


def test_bootstrap_with_rotation_flag_does_not_rotate_a_new_connection_twice(source: Source) -> None:
    client = FakeClient()
    client.configured = None
    client.catalog = []
    run(source, client, github_token=PAT, rotate_git_token=True)
    assert not any(call[0] == "PATCH" and call[1].startswith("/connections/") for call in client.calls)


def test_explicit_approved_connection_overrides_only_sp_binding(source: Source) -> None:
    client = FakeClient()
    client.providers[OTHER_CONNECTION] = provider_connection(OTHER_CONNECTION)
    run(source, client, connection_id=OTHER_CONNECTION)
    assert client.configured == OTHER_CONNECTION
    assert client.writes[0][2] == {"source": "ConfiguredConnection", "connectionId": OTHER_CONNECTION}
    assert not any(call[0] == "PATCH" and call[1].startswith("/connections/") for call in client.calls)


def test_inaccessible_override_does_not_fall_back_to_creation(source: Source) -> None:
    client = FakeClient()
    client.failures[("GET", f"/connections/{OTHER_CONNECTION}")] = RuntimeError(SECRET_MARKER)
    with pytest.raises(sync.GitSyncError, match="request failed") as caught:
        run(source, client, connection_id=OTHER_CONNECTION, github_token=PAT)
    assert SECRET_MARKER not in str(caught.value)
    assert client.writes == []


def test_pat_is_ignored_for_existing_connection_unless_rotation_explicit(source: Source) -> None:
    client = FakeClient()
    run(source, client, github_token=PAT)
    assert not any(PAT in json.dumps(call[2]) for call in client.calls)
    run(source, client, github_token=PAT, rotate_git_token=True)
    rotation = [call for call in client.writes if call[0] == "PATCH"]
    assert rotation == [
        (
            "PATCH", f"/connections/{GIT_CONNECTION}",
            {
                "connectivityType": "ShareableCloud",
                "credentialDetails": {"credentials": {"credentialType": "Key", "key": PAT}},
            }, True,
        )
    ]


def test_rotation_requires_pat_before_any_calls(source: Source) -> None:
    client = FakeClient()
    with pytest.raises(sync.GitSyncError, match="requires FABRIC_GITHUB_TOKEN"):
        run(source, client, rotate_git_token=True)
    assert client.calls == []


def test_missing_connection_without_pat_is_actionable_and_never_uses_github_token(
    source: Source, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GITHUB_TOKEN", "ghs_ACTIONS_INSTALLATION_TOKEN")
    client = FakeClient()
    client.configured = None
    client.catalog = []
    with pytest.raises(sync.GitSyncError, match="FABRIC_GITHUB_TOKEN"):
        run(source, client)
    assert client.writes == []


@pytest.mark.parametrize("token", ["ghs_installation", "ghp_classic", "gho_oauth", "", "not-a-token"])
def test_non_fine_grained_pat_is_rejected_without_leaking_it(source: Source, token: str) -> None:
    client = FakeClient()
    with pytest.raises(sync.GitSyncError, match="fine-grained") as caught:
        run(source, client, github_token=token)
    assert not token or token not in str(caught.value)
    assert client.calls == []


def test_ambiguous_deterministic_connection_is_rejected(source: Source) -> None:
    client = FakeClient()
    client.configured = None
    client.catalog.append(provider_connection(OTHER_CONNECTION))
    with pytest.raises(sync.GitSyncError, match="Multiple deterministic"):
        run(source, client, github_token=PAT)
    assert client.writes == []


@pytest.mark.parametrize("mutation", [
    {"connectivityType": "PersonalCloud"},
    {"connectionDetails": {"type": "GitHub", "path": REPOSITORY_URL}},
    {"connectionDetails": {"type": "GitHubSourceControl", "path": "https://github.com"}},
    {"connectionDetails": {"type": "GitHubSourceControl", "path": f"{REPOSITORY_URL}/other"}},
    {"connectionDetails": {"type": "GitHubSourceControl", "path": f"{REPOSITORY_URL}?token=secret"}},
    {"connectionDetails": {"type": "GitHubSourceControl", "path": "https://evil.example/example/patterns"}},
    {"connectionDetails": {"type": "GitHubSourceControl", "path": "https://user:secret@github.com/example/patterns"}},
    {"credentialDetails": {"credentialType": "OAuth2"}},
    {"id": OTHER_CONNECTION},
])
def test_wrong_provider_connection_fails_closed(source: Source, mutation: dict[str, object]) -> None:
    client = FakeClient()
    client.providers[GIT_CONNECTION].update(mutation)
    with pytest.raises(sync.GitSyncError):
        run(source, client)
    assert client.writes == []


@pytest.mark.parametrize("credential_response", [
    {}, {"source": "Automatic", "connectionId": GIT_CONNECTION},
    {"source": "ConfiguredConnection"}, {"source": "Unexpected"},
    {"source": "ConfiguredConnection", "connectionId": "invalid"},
    {"source": []}, {"source": {"nested": "None"}},
])
def test_malformed_credential_identity_configuration_is_rejected(
    source: Source, credential_response: dict[str, object],
) -> None:
    client = FakeClient()
    client.credential_response = credential_response
    with pytest.raises(sync.GitSyncError):
        run(source, client)
    assert client.writes == []


def test_unverified_credential_patch_prevents_git_update(source: Source) -> None:
    client = FakeClient()
    client.configured = None
    client.bind_response = {"source": "ConfiguredConnection", "connectionId": OTHER_CONNECTION}
    with pytest.raises(sync.GitSyncError, match="binding was not verified"):
        run(source, client)
    assert not any(call[1].endswith("/git/updateFromGit") for call in client.calls)


def test_manifest_workspace_mismatch_prevents_even_cloud_reads(source: Source) -> None:
    client = FakeClient()
    with pytest.raises(sync.GitSyncError, match="tracked Dev workspace"):
        run(source, client, workspace_id=OTHER_ITEM)
    assert client.calls == []


def test_cloud_workspace_mismatch_prevents_mutation(source: Source) -> None:
    client = FakeClient()
    client.workspace["id"] = OTHER_ITEM
    with pytest.raises(sync.GitSyncError, match="different workspace"):
        run(source, client)
    assert client.writes == []


@pytest.mark.parametrize(("key", "value"), [
    ("gitProviderType", "AzureDevOps"), ("ownerName", "wrong"), ("repositoryName", "wrong"),
    ("branchName", "feature/authoring"), ("directoryName", "other/fabric"),
    ("directoryName", "../fabric"), ("customDomainName", "enterprise.ghe.com"),
])
def test_git_provider_mismatch_prevents_all_mutation(source: Source, key: str, value: str) -> None:
    client = FakeClient()
    client.git["gitProviderDetails"][key] = value
    with pytest.raises(sync.GitSyncError, match="connection|directory"):
        run(source, client)
    assert client.writes == []


@pytest.mark.parametrize(("key", "value"), [
    ("gitConnectionState", "Connected"), ("gitConnectionState", "NotConnected"),
    ("gitConnectionState", "Unexpected"), ("gitConnectionType", "Selective"),
    ("gitConnectionType", None), ("gitProviderDetails", []),
])
def test_uninitialized_selective_or_malformed_connection_is_not_repaired(
    source: Source, key: str, value: object,
) -> None:
    client = FakeClient()
    client.git[key] = value
    with pytest.raises(sync.GitSyncError):
        run(source, client)
    assert client.writes == []


def test_owner_and_repository_case_and_outer_directory_slashes_are_equivalent(source: Source) -> None:
    client = FakeClient()
    client.git["gitProviderDetails"].update(
        {"ownerName": "Example", "repositoryName": "Patterns", "directoryName": "/data/fabric/"}
    )
    assert run(source, client).commit == COMMIT


def test_pipeline_source_guard_runs_before_credentials_or_item_writes(source: Source) -> None:
    path = source.fabric / "Patterns_Load_Validate_And_Refresh.DataPipeline" / "pipeline-content.json"
    text = path.read_text(encoding="utf-8").replace(NOTEBOOK_CONNECTION, OTHER_CONNECTION)
    path.write_text(text, encoding="utf-8")
    client = FakeClient()
    client.configured = None
    client.catalog = []
    with pytest.raises(sync.GitSyncError, match="source or its parameter contract"):
        run(source, client, github_token=PAT)
    assert client.calls == []


def test_manifest_parameter_contract_failure_prevents_cloud_calls(
    source: Source, monkeypatch: pytest.MonkeyPatch,
) -> None:
    def invalid_contract(_repo_dir: Path) -> None:
        raise pipeline_bindings.PipelineBindingError("parameter contract mismatch")

    monkeypatch.setattr(pipeline_bindings, "load_dev_bindings", invalid_contract)
    client = FakeClient()
    with pytest.raises(sync.GitSyncError, match="parameter contract"):
        run(source, client)
    assert client.calls == []


def test_bulk_parameter_contract_guard_is_required_before_cloud_access(
    source: Source, monkeypatch: pytest.MonkeyPatch,
) -> None:
    def source_guard(_directory: Path, *, bulk: bool = False) -> Bindings:
        if bulk:
            raise ValueError("bulk parameter contract is stale")
        return source.bindings

    monkeypatch.setattr(sync, "validate_deployment_source", source_guard)
    client = FakeClient()
    with pytest.raises(sync.GitSyncError, match="parameter contract"):
        run(source, client)
    assert client.calls == []


def test_real_shared_manifest_loader_and_pipeline_guard_integrate_with_sync(
    source: Source, monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest = pipeline_bindings.DevPipelineBindings(
        WORKSPACE, MODEL, NOTEBOOK_CONNECTION, REFRESH_CONNECTION,
    ).document()
    pipeline_bindings.dev_bindings_path(source.fabric).write_text(json.dumps(manifest), encoding="utf-8")
    library = source.fabric / "Patterns_Variables.VariableLibrary"
    library.mkdir()
    (library / "variables.json").write_text(
        json.dumps({"variables": [{"name": "target_workspace_id", "value": WORKSPACE}]}),
        encoding="utf-8",
    )
    monkeypatch.setattr(pipeline_bindings, "load_dev_bindings", ORIGINAL_LOAD_DEV_BINDINGS)
    client = FakeClient()
    assert run(source, client).commit == COMMIT
    assert source.activity_checks[0][2].values == source.bindings.values


def test_existing_activity_connections_are_validated_without_replacement(
    source: Source, monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = ModuleType("fabric_connections")
    calls: list[tuple[object, str, dict[str, object]]] = []

    def ensure(client: object, workspace_id: str, **kwargs: object) -> dict[str, str]:
        calls.append((client, workspace_id, kwargs))
        return {
            "NOTEBOOK_CONNECTION_ID": NOTEBOOK_CONNECTION,
            "SEMANTIC_MODEL_REFRESH_CONNECTION_ID": REFRESH_CONNECTION,
        }

    module.ensure_pipeline_connections = ensure
    module.FabricRestClient = FakeClient
    monkeypatch.setitem(sys.modules, "fabric_connections", module)
    real_ensure = ORIGINAL_ENSURE_ACTIVITY_CONNECTIONS
    client = FakeClient()
    real_ensure(client, WORKSPACE, source.bindings)
    assert calls == [
        (
            client, WORKSPACE,
            {
                "mode": "existing", "notebook_connection_id": NOTEBOOK_CONNECTION,
                "refresh_connection_id": REFRESH_CONNECTION,
                "authentication": "ServicePrincipal", "credentials": None,
            },
        )
    ]


def test_deleted_activity_connection_fails_before_git_credentials(
    source: Source, monkeypatch: pytest.MonkeyPatch,
) -> None:
    def missing(*_args: object, **_kwargs: object) -> None:
        raise sync.GitSyncError("Canonical Dev activity connections are missing")

    monkeypatch.setattr(sync, "_ensure_activity_connections", missing)
    client = FakeClient()
    with pytest.raises(sync.GitSyncError, match="Canonical Dev activity"):
        run(source, client)
    assert client.writes == []
    assert not any(call[1].endswith("myGitCredentials") for call in client.calls)


def test_remote_commit_mismatch_prevents_item_update(source: Source) -> None:
    client = FakeClient()
    client.current_status["remoteCommitHash"] = OTHER_COMMIT
    with pytest.raises(sync.GitSyncError, match="expected pushed commit"):
        run(source, client)
    assert client.writes == []


def test_optional_local_expected_commit_uses_verified_remote_status(source: Source) -> None:
    client = FakeClient()
    assert run(source, client, expected_commit=None).commit == COMMIT


@pytest.mark.parametrize("policy", ["strict", "source-authoritative"])
def test_all_policies_require_checked_out_source_at_expected_commit_before_writes(
    source: Source, policy: sync.SyncPolicy,
) -> None:
    source.git_state["head"] = OTHER_COMMIT
    client = FakeClient()
    with pytest.raises(sync.GitSyncError, match="exact target commit"):
        run(source, client, policy=policy)
    assert client.calls == []


def test_local_sync_does_not_deploy_a_remote_commit_that_was_not_source_checked(source: Source) -> None:
    client = FakeClient()
    client.current_status["remoteCommitHash"] = OTHER_COMMIT
    with pytest.raises(sync.GitSyncError, match="Checked-out canonical source"):
        run(source, client, expected_commit=None)
    assert client.writes == []


def test_strict_sync_rejects_uncommitted_source_even_if_ids_are_canonical(source: Source) -> None:
    source.git_state["dirty"] = "data/fabric/Patterns_Semantic_Model.SemanticModel/definition/model.tmdl"
    client = FakeClient()
    with pytest.raises(sync.GitSyncError, match="local changes"):
        run(source, client)
    assert client.calls == []


def test_untracked_manifest_is_not_accepted_as_proof_of_remote_baseline(
    source: Source, monkeypatch: pytest.MonkeyPatch,
) -> None:
    original = sync._git_output

    def git_output(root: Path, arguments: list[str]) -> str:
        if arguments[:2] == ["ls-files", "--error-unmatch"]:
            return "\n".join(arguments[4:])
        return original(root, arguments)

    monkeypatch.setattr(sync, "_git_output", git_output)
    client = FakeClient()
    with pytest.raises(sync.GitSyncError, match="must be tracked"):
        run(source, client)
    assert client.calls == []


@pytest.mark.parametrize("outgoing", [
    change(workspace="Modified"),
    change(workspace="Modified", remote="Modified", conflict="Conflict"),
    change(workspace="Modified", remote="Modified", conflict="SameChanges"),
    change(workspace="Added", remote=None, item_type="Notebook"),
    change(workspace="Deleted", remote=None),
])
def test_strict_rejects_all_outgoing_or_conflicted_items(source: Source, outgoing: dict[str, object]) -> None:
    client = FakeClient()
    client.current_status["changes"] = [outgoing]
    with pytest.raises(sync.GitSyncError, match="Strict sync will not overwrite"):
        run(source, client)
    assert client.writes == []


@pytest.mark.parametrize("mutation", [
    {"workspaceHead": None}, {"workspaceHead": "abc"}, {"remoteCommitHash": "invalid"},
    {"changes": None}, {"changes": {}}, {"changes": ["invalid"]},
    {"changes": [{}]}, {"changes": [change(remote="Unexpected")]},
    {"changes": [change(workspace="Unexpected")]},
    {"changes": [change(conflict="FutureConflict")]},
    {"changes": [change(remote=None)]},
    {"changes": [change(remote=None, workspace="Modified", conflict="Conflict")]},
    {"changes": [{"itemMetadata": []}]},
])
def test_unknown_and_malformed_status_never_triggers_sync(source: Source, mutation: dict[str, object]) -> None:
    client = FakeClient()
    client.current_status.update(mutation)
    with pytest.raises(sync.GitSyncError):
        run(source, client)
    assert client.writes == []


def test_equal_heads_with_remote_changes_is_malformed_not_a_force_reset(source: Source) -> None:
    client = FakeClient()
    client.current_status["workspaceHead"] = COMMIT
    with pytest.raises(sync.GitSyncError, match="equal commit heads"):
        run(source, client)
    assert client.writes == []


def test_duplicate_item_status_is_not_accepted(source: Source) -> None:
    client = FakeClient()
    client.current_status["changes"] = [change(), change()]
    with pytest.raises(sync.GitSyncError, match="duplicate or ambiguous"):
        run(source, client)
    assert client.writes == []


@pytest.mark.parametrize("files", [
    [None], [{"path": "../definition/model.tmdl", "remoteChange": "Modified"}],
    [{"path": "definition\\model.tmdl", "remoteChange": "Modified"}],
    [{"path": "definition/model.tmdl", "workspaceChange": "Modified"}],
    [{"path": "definition/model.tmdl", "remoteChange": "FutureChange"}],
    [{"path": "definition/model.tmdl", "remoteChange": "Modified", "conflictType": "Conflict"}],
])
def test_malformed_or_contradictory_file_status_is_rejected(
    source: Source, files: list[object],
) -> None:
    client = FakeClient()
    client.current_status["changes"][0]["fileChanges"] = files
    with pytest.raises(sync.GitSyncError):
        run(source, client)
    assert client.writes == []


def test_read_failure_does_not_echo_secret_response_content(source: Source) -> None:
    client = FakeClient()
    client.failures[("GET", f"/workspaces/{WORKSPACE}/git/status?includeFilesDetails=true")] = RuntimeError(SECRET_MARKER)
    with pytest.raises(sync.GitSyncError) as caught:
        run(source, client)
    assert SECRET_MARKER not in str(caught.value)


def test_shared_client_timeout_is_a_failed_sync(source: Source) -> None:
    client = FakeClient()
    client.failures[("POST", f"/workspaces/{WORKSPACE}/git/updateFromGit")] = TimeoutError(SECRET_MARKER)
    with pytest.raises(sync.GitSyncError, match="timed out") as caught:
        run(source, client)
    assert SECRET_MARKER not in str(caught.value)


def test_overall_deadline_stops_processing_after_a_slow_request(
    source: Source, monkeypatch: pytest.MonkeyPatch,
) -> None:
    clock = [0.0]
    monkeypatch.setattr(sync.time, "monotonic", lambda: clock[0])
    client = FakeClient()
    client.on_request = lambda: clock.__setitem__(0, clock[0] + 2)
    with pytest.raises(sync.GitSyncError, match="timed out"):
        run(source, client, timeout_seconds=1)
    assert client.writes == []


def test_incomplete_operation_response_is_not_treated_as_completion(source: Source) -> None:
    client = FakeClient()
    client.update_response = {"status": "Running"}
    with pytest.raises(sync.GitSyncError, match="did not complete"):
        run(source, client)


@pytest.mark.parametrize("final", [
    status(COMMIT, COMMIT, [change(workspace="Modified", remote=None)]),
    status(COMMIT, OTHER_COMMIT, []),
    status(OLD_COMMIT, COMMIT, []),
])
def test_dirty_or_changed_final_heads_fail(source: Source, final: dict[str, object]) -> None:
    client = FakeClient()
    client.status_sequence = [status(), status(COMMIT, COMMIT, []), final]
    with pytest.raises(sync.GitSyncError, match="clean, matching heads"):
        run(source, client)


def test_final_connection_is_rechecked_before_success(source: Source) -> None:
    client = FakeClient()
    original = client.request
    connection_reads = [0]

    def request(method: str, path: str, body: dict[str, object] | None = None, **kwargs: object) -> dict[str, object]:
        if method == "GET" and path.endswith("/git/connection"):
            connection_reads[0] += 1
            if connection_reads[0] == 2:
                client.git["gitProviderDetails"]["branchName"] = "feature/changed"
        return original(method, path, body, **kwargs)

    client.request = request
    with pytest.raises(sync.GitSyncError, match="expected GitHub"):
        run(source, client)


def test_dry_run_has_no_writes_with_existing_sp_credentials(source: Source) -> None:
    client = FakeClient()
    result = run(source, client, dry_run=True)
    assert result.dry_run and result.updated
    assert client.writes == []


def test_dry_run_refuses_to_bootstrap_caller_identity(source: Source) -> None:
    client = FakeClient()
    client.configured = None
    with pytest.raises(sync.GitSyncError, match="SP's own Git credentials"):
        run(source, client, dry_run=True)
    assert client.writes == []


def test_sp_activity_credentials_are_forwarded_on_every_sync_without_changing_ids(source: Source) -> None:
    client = FakeClient()
    credentials = {
        "tenantId": OTHER_ITEM,
        "servicePrincipalClientId": OTHER_CONNECTION,
        "servicePrincipalSecret": SECRET_MARKER,
    }
    run(source, client, credentials=credentials)
    rotated = {**credentials, "servicePrincipalSecret": f"{SECRET_MARKER}_ROTATED"}
    run(source, client, credentials=rotated)
    assert [check[3] for check in source.activity_checks] == [
        {"authentication": "ServicePrincipal", "credentials": credentials},
        {"authentication": "ServicePrincipal", "credentials": rotated},
    ]
    assert source.bindings.notebook_connection_id == NOTEBOOK_CONNECTION
    assert source.bindings.refresh_connection_id == REFRESH_CONNECTION


def test_actual_activity_helper_reconciles_existing_sp_connections_without_wi(
    source: Source, monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = FakeClient()
    for connection_id, connector_type in (
        (NOTEBOOK_CONNECTION, "Notebook"), (REFRESH_CONNECTION, "PowerBIDatasets"),
    ):
        client.providers[connection_id] = {
            "id": connection_id, "displayName": "Existing approved runtime",
            "connectivityType": "ShareableCloud",
            "connectionDetails": {"type": connector_type, "path": "default"},
            "credentialDetails": {"credentialType": "ServicePrincipal"},
        }
    credentials = {
        "tenantId": OTHER_ITEM,
        "servicePrincipalClientId": OTHER_CONNECTION,
        "servicePrincipalSecret": SECRET_MARKER,
    }
    monkeypatch.setattr(sync, "_ensure_activity_connections", ORIGINAL_ENSURE_ACTIVITY_CONNECTIONS)
    assert run(source, client, credentials=credentials).updated
    rotations = [call for call in client.writes if call[0] == "PATCH"]
    assert {call[1] for call in rotations} == {
        f"/connections/{NOTEBOOK_CONNECTION}", f"/connections/{REFRESH_CONNECTION}",
    }
    for _method, _path, body, _wait in rotations:
        assert body["connectivityType"] == "ShareableCloud"
        assert body["credentialDetails"]["credentials"] == {"credentialType": "ServicePrincipal", **credentials}
    assert not any("Identity" in path or "roleAssignments" in path for _method, path, _body, _wait in client.calls)
    assert not any(method == "POST" and path == "/connections" for method, path, _body, _wait in client.calls)


def test_preconfigured_wi_profile_is_explicit_and_receives_no_runtime_secret(source: Source) -> None:
    client = FakeClient()
    run(source, client, authentication="WorkspaceIdentity")
    assert source.activity_checks[0][3] == {"authentication": "WorkspaceIdentity", "credentials": None}


def test_dry_run_does_not_reconcile_sp_runtime_secrets(source: Source) -> None:
    client = FakeClient()
    run(
        source, client, dry_run=True,
        credentials={
            "tenantId": OTHER_ITEM, "servicePrincipalClientId": OTHER_CONNECTION,
            "servicePrincipalSecret": SECRET_MARKER,
        },
    )
    assert source.activity_checks[0][3]["credentials"] is None
    assert client.writes == []


@pytest.mark.parametrize("options", [
    {"authentication": "Unsupported"},
    {"credentials": {}},
    {"credentials": {"tenantId": OTHER_ITEM, "servicePrincipalClientId": OTHER_CONNECTION, "servicePrincipalSecret": ""}},
    {"authentication": "WorkspaceIdentity", "credentials": {
        "tenantId": OTHER_ITEM, "servicePrincipalClientId": OTHER_CONNECTION,
        "servicePrincipalSecret": SECRET_MARKER,
    }},
])
def test_invalid_activity_authentication_prevents_all_cloud_access(
    source: Source, options: dict[str, object],
) -> None:
    client = FakeClient()
    with pytest.raises(sync.GitSyncError):
        run(source, client, **options)
    assert client.calls == []


def test_source_authoritative_conflict_uses_explicit_remote_policy(source: Source) -> None:
    client = FakeClient()
    client.current_status["changes"] = [change(workspace="Modified", remote="Modified", conflict="Conflict")]
    result = run(source, client, policy="source-authoritative")
    assert result.updated and not result.restored_model
    assert client.writes[0][2] == {
        "workspaceHead": OLD_COMMIT,
        "remoteCommitHash": COMMIT,
        "options": {"allowOverrideItems": True},
        "conflictResolution": {"conflictResolutionType": "Workspace", "conflictResolutionPolicy": "PreferRemote"},
    }


def test_equal_heads_outgoing_model_is_restored_in_place_without_git_reset(source: Source) -> None:
    client = FakeClient()
    client.current_status = status(COMMIT, COMMIT, [change(workspace="Modified", remote=None)])
    result = run(source, client, policy="source-authoritative")
    assert not result.updated and result.restored_model
    assert len(client.writes) == 1
    restoration = client.writes[0]
    assert restoration[1] == f"/workspaces/{WORKSPACE}/semanticModels/{MODEL}/updateDefinition?updateMetadata=false"
    assert restoration[3] is False
    assert not any(call[1].endswith("updateFromGit") for call in client.calls)
    parts = restoration[2]["definition"]["parts"]
    assert {part["path"] for part in parts} == {
        ".platform", "definition.pbism", "definition/database.tmdl", "definition/model.tmdl",
    }
    for part in parts:
        assert base64.b64decode(part["payload"]) == (source.fabric / sync.MODEL_DIRECTORY_NAME / part["path"]).read_bytes()


def test_residual_outgoing_model_after_incoming_update_uses_supported_restoration(source: Source) -> None:
    client = FakeClient()
    client.update_residual = [change(workspace="Modified", remote=None)]
    result = run(source, client, policy="source-authoritative")
    assert result.updated and result.restored_model
    assert [call[1] for call in client.writes] == [
        f"/workspaces/{WORKSPACE}/git/updateFromGit",
        f"/workspaces/{WORKSPACE}/semanticModels/{MODEL}/updateDefinition?updateMetadata=false",
    ]


def test_restoration_that_leaves_runtime_diff_is_not_success(source: Source) -> None:
    client = FakeClient()
    client.current_status = status(COMMIT, COMMIT, [change(workspace="Modified", remote=None)])
    client.restore_clears_changes = False
    with pytest.raises(sync.GitSyncError, match="may not clear this runtime diff"):
        run(source, client, policy="source-authoritative")


@pytest.mark.parametrize("outgoing", [
    change(workspace="Added", remote=None),
    change(workspace="Deleted", remote=None),
    change(workspace="Modified", remote=None, object_id=OTHER_ITEM),
    change(workspace="Modified", remote=None, logical_id=OTHER_ITEM),
    change(workspace="Modified", remote=None, item_type="Notebook"),
    change(workspace="Modified", remote="Deleted", conflict="Conflict"),
])
def test_source_authoritative_excludes_unrelated_items_additions_and_deletions(
    source: Source, outgoing: dict[str, object],
) -> None:
    client = FakeClient()
    client.current_status["changes"] = [outgoing]
    with pytest.raises(sync.GitSyncError, match="only definition modifications"):
        run(source, client, policy="source-authoritative")
    assert client.writes == []


def test_source_authoritative_rejects_outgoing_platform_metadata_changes(source: Source) -> None:
    client = FakeClient()
    item = change(workspace="Modified", remote=None)
    item["fileChanges"] = [{"path": ".platform", "workspaceChange": "Modified", "conflictType": "None"}]
    client.current_status["changes"] = [item]
    with pytest.raises(sync.GitSyncError, match="metadata edits"):
        run(source, client, policy="source-authoritative")
    assert client.writes == []


@pytest.mark.parametrize(("key", "value"), [
    ("id", OTHER_ITEM), ("workspaceId", OTHER_ITEM), ("type", "Report"), ("displayName", "renamed"),
])
def test_restoration_validates_existing_model_identity(
    source: Source, key: str, value: str,
) -> None:
    client = FakeClient()
    client.current_status = status(COMMIT, COMMIT, [change(workspace="Modified", remote=None)])
    client.model[key] = value
    with pytest.raises(sync.GitSyncError, match="identity or metadata"):
        run(source, client, policy="source-authoritative")
    assert client.writes == []


def test_recovery_refuses_wrong_checked_out_commit_before_mutation(source: Source) -> None:
    source.git_state["head"] = OTHER_COMMIT
    client = FakeClient()
    with pytest.raises(sync.GitSyncError, match="exact target commit"):
        run(source, client, policy="source-authoritative")
    assert client.calls == []


def test_recovery_refuses_uncommitted_model_content_before_mutation(source: Source) -> None:
    source.git_state["dirty"] = "data/fabric/Patterns_Semantic_Model.SemanticModel/definition/model.tmdl"
    client = FakeClient()
    with pytest.raises(sync.GitSyncError, match="local changes"):
        run(source, client, policy="source-authoritative")
    assert client.calls == []


def test_recovery_requires_complete_public_definition_before_mutation(source: Source) -> None:
    (source.fabric / sync.MODEL_DIRECTORY_NAME / "definition.pbism").unlink()
    client = FakeClient()
    with pytest.raises(sync.GitSyncError, match="requires .platform"):
        run(source, client, policy="source-authoritative")
    assert client.calls == []


@pytest.mark.parametrize("kwargs", [
    {"workspace_id": "invalid"}, {"workspace_id": pipeline_bindings.ZERO_GUID},
    {"repository": "https://github.com/example/patterns"}, {"repository": "example/../patterns"},
    {"connection_id": "invalid"}, {"expected_commit": "short"},
    {"branch": ""}, {"branch": " dev "}, {"timeout_seconds": 0}, {"timeout_seconds": True},
    {"policy": "unknown"},
])
def test_invalid_external_inputs_are_rejected_before_api(
    source: Source, kwargs: dict[str, object],
) -> None:
    client = FakeClient()
    with pytest.raises(sync.GitSyncError):
        run(source, client, **kwargs)
    assert client.calls == []


@pytest.mark.parametrize("connection_mode", ["auto", "existing"])
def test_cli_uses_client_secret_identity_env_and_never_prints_secrets(
    source: Source, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str],
    connection_mode: str,
) -> None:
    import azure.identity

    client = FakeClient()
    credential_calls: list[dict[str, str]] = []
    scopes: list[str] = []
    client_configuration: list[dict[str, object]] = []
    module = ModuleType("fabric_connections")

    def rest_client(token_provider: object, **kwargs: object) -> FakeClient:
        assert token_provider() == SECRET_MARKER
        client_configuration.append(kwargs)
        return client

    module.FabricRestClient = rest_client
    monkeypatch.setitem(sys.modules, "fabric_connections", module)

    class Credential:
        def __init__(self, **kwargs: str) -> None:
            credential_calls.append(kwargs)

        def __enter__(self) -> Credential:
            return self

        def __exit__(self, *_args: object) -> None:
            pass

        def get_token(self, scope: str) -> SimpleNamespace:
            scopes.append(scope)
            return SimpleNamespace(token=SECRET_MARKER)

    monkeypatch.setattr(azure.identity, "ClientSecretCredential", Credential)
    monkeypatch.setenv("AZURE_TENANT_ID", OTHER_ITEM)
    monkeypatch.setenv("AZURE_CLIENT_ID", OTHER_CONNECTION)
    monkeypatch.setenv("AZURE_CLIENT_SECRET", SECRET_MARKER)
    monkeypatch.setenv("FABRIC_WORKSPACE_ID", WORKSPACE)
    monkeypatch.setenv("FABRIC_GIT_REPOSITORY", REPOSITORY)
    monkeypatch.setenv("GITHUB_REPOSITORY", "wrong/wrong")
    monkeypatch.setenv("FABRIC_GIT_COMMIT", COMMIT)
    monkeypatch.setenv("FABRIC_GITHUB_TOKEN", PAT)
    monkeypatch.setenv("FABRIC_CONNECTION_MODE", connection_mode)
    assert sync.main(["--git-root", str(source.root)]) == 0
    output = capsys.readouterr()
    assert "synced and verified clean" in output.out
    assert SECRET_MARKER not in output.out + output.err
    assert PAT not in output.out + output.err
    assert credential_calls == [
        {"tenant_id": OTHER_ITEM, "client_id": OTHER_CONNECTION, "client_secret": SECRET_MARKER}
    ]
    assert scopes == [sync.FABRIC_SCOPE]
    assert client_configuration == [{"timeout": 30, "operation_timeout": sync.DEFAULT_TIMEOUT_SECONDS}]
    assert source.activity_checks[0][3] == {
        "authentication": "ServicePrincipal",
        "credentials": {
            "tenantId": OTHER_ITEM, "servicePrincipalClientId": OTHER_CONNECTION,
            "servicePrincipalSecret": SECRET_MARKER,
        } if connection_mode == "auto" else None,
    }


def test_cli_failure_redacts_remote_error_body(
    source: Source, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str],
) -> None:
    import azure.identity

    client = FakeClient()
    client.failures[("GET", f"/workspaces/{WORKSPACE}")] = RuntimeError(SECRET_MARKER)
    module = ModuleType("fabric_connections")
    module.FabricRestClient = lambda _provider, **_kwargs: client
    monkeypatch.setitem(sys.modules, "fabric_connections", module)

    class Credential:
        def __init__(self, **_kwargs: str) -> None:
            pass

        def __enter__(self) -> Credential:
            return self

        def __exit__(self, *_args: object) -> None:
            pass

    monkeypatch.setattr(azure.identity, "ClientSecretCredential", Credential)
    monkeypatch.setenv("AZURE_TENANT_ID", OTHER_ITEM)
    monkeypatch.setenv("AZURE_CLIENT_ID", OTHER_CONNECTION)
    monkeypatch.setenv("AZURE_CLIENT_SECRET", SECRET_MARKER)
    assert sync.main([
        "--git-root", str(source.root), "--workspace-id", WORKSPACE,
        "--repository", REPOSITORY, "--commit", COMMIT,
    ]) == 1
    output = capsys.readouterr()
    assert "Dev Git sync failed" in output.err
    assert SECRET_MARKER not in output.out + output.err


@pytest.mark.parametrize("update_terminal", ["Succeeded", "Failed", "Cancelled", "Unknown", "Running"])
def test_shared_rest_client_awaits_202_status_results_and_result_free_git_updates(
    source: Source, monkeypatch: pytest.MonkeyPatch, update_terminal: str,
) -> None:
    from fabric_connections import FabricRestClient, _Response

    fake = FakeClient()
    client = FabricRestClient(lambda: "FAKE_FABRIC_TOKEN", max_polls=2)
    calls: list[tuple[str, str]] = []
    operations: dict[str, dict[str, object]] = {}
    operation_counter = [0]

    def send(method: str, url: str, body: dict[str, object] | None, _deadline: float) -> _Response:
        parsed = urlsplit(url)
        path = parsed.path.removeprefix("/v1")
        if parsed.query:
            path += f"?{parsed.query}"
        calls.append((method, path))
        if path.startswith("/operations/"):
            segments = path.split("/")
            operation = operations[segments[2]]
            if path.endswith("/result"):
                assert not operation["mutation"], "Git update has no documented operation result"
                return _Response(200, {}, copy.deepcopy(operation["result"]))
            operation["polls"] += 1
            terminal = update_terminal if operation["mutation"] else "Succeeded"
            state = "Running" if operation["polls"] == 1 else terminal
            return _Response(
                200, {"retry-after": "0"},
                {"status": state, "error": {"message": SECRET_MARKER}},
            )
        result = fake.request(method, path, body)
        if "/git/status?" in path or path.endswith("/git/updateFromGit"):
            operation_counter[0] += 1
            operation_id = f"12345678-0000-4000-8000-{operation_counter[0]:012d}"
            operations[operation_id] = {
                "mutation": method == "POST", "result": result, "polls": 0,
            }
            return _Response(202, {"x-ms-operation-id": operation_id, "retry-after": "0"}, {})
        return _Response(200, {}, result)

    monkeypatch.setattr(client, "_send", send)
    monkeypatch.setattr(client, "_pause", lambda _seconds, _deadline: None)
    if update_terminal == "Succeeded":
        result = sync.sync_workspace(
            client, source.fabric, workspace_id=WORKSPACE, repository=REPOSITORY,
            git_root=source.root, expected_commit=COMMIT,
        )
        assert result.updated
        assert len([path for _method, path in calls if path.endswith("/result")]) == 3
        assert all(operation["polls"] == 2 for operation in operations.values())
    else:
        with pytest.raises(sync.GitSyncError) as caught:
            sync.sync_workspace(
                client, source.fabric, workspace_id=WORKSPACE, repository=REPOSITORY,
                git_root=source.root, expected_commit=COMMIT,
            )
        assert SECRET_MARKER not in str(caught.value)
        assert len([path for _method, path in calls if "/git/status?" in path]) == 1
    mutation_ids = {key for key, operation in operations.items() if operation["mutation"]}
    assert not any(path == f"/operations/{key}/result" for _method, path in calls for key in mutation_ids)
