"""Source-independent bootstrap and secret-free artifact contracts."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import Mock

import pytest
import yaml

import bootstrap_dev_connections as bootstrap
from fabric_connections import FabricConnectionError, FabricRestClient
from pipeline_bindings import DevPipelineBindings

WORKSPACE = "aaaaaaaa-1111-4111-8111-aaaaaaaaaaaa"
MODEL = "bbbbbbbb-2222-4222-8222-bbbbbbbbbbbb"
NOTEBOOK = "cccccccc-3333-4333-8333-cccccccccccc"
REFRESH = "dddddddd-4444-4444-8444-dddddddddddd"
TENANT = "eeeeeeee-5555-4555-8555-eeeeeeeeeeee"
CLIENT = "ffffffff-6666-4666-8666-ffffffffffff"
SECRET = "unit-test-only-do-not-export"
REPOSITORY = "example/workshop"
SHA = "a" * 40
ROOT = Path(__file__).resolve().parents[1]


def credentials() -> dict[str, str]:
    return {
        "tenantId": TENANT, "servicePrincipalClientId": CLIENT,
        "servicePrincipalSecret": SECRET,
    }


def artifact() -> bootstrap.BootstrapArtifact:
    return bootstrap.BootstrapArtifact(
        DevPipelineBindings(WORKSPACE, MODEL, NOTEBOOK, REFRESH),
        bootstrap.BootstrapProvenance(REPOSITORY, "123", 1, SHA, "refs/heads/dev", "push", bootstrap.DEFAULT_MODEL_NAME),
    )


@pytest.fixture()
def actions_environment(monkeypatch: pytest.MonkeyPatch) -> dict[str, str]:
    values = {
        "GITHUB_ACTIONS": "true", "GITHUB_REPOSITORY": REPOSITORY,
        "GITHUB_WORKFLOW_REF": f"{REPOSITORY}/{bootstrap.BOOTSTRAP_WORKFLOW}@refs/heads/dev",
        "GITHUB_RUN_ID": "123", "GITHUB_RUN_ATTEMPT": "1", "GITHUB_SHA": SHA,
        "GITHUB_REF": "refs/heads/dev", "GITHUB_EVENT_NAME": "push",
        "AZURE_TENANT_ID": TENANT, "AZURE_CLIENT_ID": CLIENT,
        "AZURE_CLIENT_SECRET": SECRET, "FABRIC_WORKSPACE_ID": WORKSPACE,
    }
    for key in ("SEMANTIC_MODEL_NAME", bootstrap.NOTEBOOK_CONNECTION_ENV, bootstrap.REFRESH_CONNECTION_ENV):
        monkeypatch.delenv(key, raising=False)
    for key, value in values.items():
        monkeypatch.setenv(key, value)
    return values


def fake_client() -> Mock:
    client = Mock(spec=FabricRestClient)
    client.list.return_value = [{"type": "SemanticModel", "displayName": bootstrap.DEFAULT_MODEL_NAME, "id": MODEL}]
    return client


def test_artifact_is_exactly_whitelisted_non_secret_metadata() -> None:
    document = artifact().document()
    assert bootstrap.parse_bootstrap_artifact(document) == artifact()
    serialized = json.dumps(document)
    for value in (SECRET, TENANT, CLIENT, "accessToken", "Authorization", "clientSecret"):
        assert value not in serialized
    assert set(document) == {"schemaVersion", "bindings", "provenance"}


@pytest.mark.parametrize("section", ["root", "bindings", "provenance"])
def test_unexpected_fields_are_rejected_without_echoing_values(section: str) -> None:
    document = artifact().document()
    target = document if section == "root" else document[section]
    assert isinstance(target, dict)
    target["secret"] = SECRET
    with pytest.raises(bootstrap.BootstrapMetadataError) as result:
        bootstrap.parse_bootstrap_artifact(document)
    assert SECRET not in str(result.value)


@pytest.mark.parametrize("version", [True, "1", 2, None])
@pytest.mark.parametrize("section", ["root", "bindings"])
def test_schema_versions_are_not_coerced(section: str, version: object) -> None:
    document = artifact().document()
    target = document if section == "root" else document[section]
    assert isinstance(target, dict)
    target["schemaVersion"] = version
    with pytest.raises(bootstrap.BootstrapMetadataError, match="schemaVersion"):
        bootstrap.parse_bootstrap_artifact(document)


@pytest.mark.parametrize("field,value", [
    ("workspaceId", ""), ("semanticModelId", 42), ("notebookConnectionId", None),
    ("notebookConnectionId", "11111111-1111-4111-8111-111111111111"),
    ("semanticModelRefreshConnectionId", "00000000-0000-0000-0000-000000000000"),
    ("notebookConnectionId", MODEL),
])
def test_invalid_or_duplicate_resource_ids_are_rejected(field: str, value: object) -> None:
    document = artifact().document()
    bindings = document["bindings"]
    assert isinstance(bindings, dict)
    bindings[field] = value
    with pytest.raises((bootstrap.BootstrapMetadataError, FabricConnectionError)):
        bootstrap.parse_bootstrap_artifact(document)


@pytest.mark.parametrize("field,value", [
    ("repository", "owner/repo/extra"), ("repository", "../repo"),
    ("workflowPath", ".github/workflows/run-tests.yml"),
    ("runId", "-1"), ("runId", 123), ("runAttempt", True), ("runAttempt", 0),
    ("headSha", "not-a-commit"), ("ref", "refs/heads/feature/unreviewed"),
    ("event", "pull_request_target"), ("semanticModelName", " padded "),
    ("semanticModelName", "x" * 201),
])
def test_invalid_provenance_is_rejected(field: str, value: object) -> None:
    document = artifact().document()
    provenance = document["provenance"]
    assert isinstance(provenance, dict)
    provenance[field] = value
    with pytest.raises(bootstrap.BootstrapMetadataError):
        bootstrap.parse_bootstrap_artifact(document)


def test_provenance_requires_reviewed_dev_workflow(actions_environment: dict[str, str]) -> None:
    assert bootstrap.provenance_from_environment(
        actions_environment, bootstrap.DEFAULT_MODEL_NAME,
    ) == artifact().provenance
    actions_environment["GITHUB_WORKFLOW_REF"] = f"{REPOSITORY}/{bootstrap.BOOTSTRAP_WORKFLOW}@refs/heads/feature/unreviewed"
    with pytest.raises(bootstrap.BootstrapMetadataError, match="reviewed Dev workflow"):
        bootstrap.provenance_from_environment(actions_environment, bootstrap.DEFAULT_MODEL_NAME)


def test_bootstrap_does_not_depend_on_source_definitions(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    client = fake_client()
    ensure = Mock(return_value={
        bootstrap.NOTEBOOK_CONNECTION_ENV: NOTEBOOK, bootstrap.REFRESH_CONNECTION_ENV: REFRESH,
    })
    monkeypatch.setattr(bootstrap, "ensure_pipeline_connections", ensure)
    result = bootstrap.collect_bindings(client, WORKSPACE, bootstrap.DEFAULT_MODEL_NAME, credentials())
    assert result == artifact().bindings
    assert list(tmp_path.iterdir()) == []
    assert ensure.call_args.kwargs["authentication"] == "ServicePrincipal"
    assert ensure.call_args.kwargs["credentials"] == credentials()
    client.request.assert_not_called()


@pytest.mark.parametrize("models", [
    [], [{"type": "Notebook", "displayName": bootstrap.DEFAULT_MODEL_NAME, "id": MODEL}],
    [{"type": "SemanticModel", "displayName": bootstrap.DEFAULT_MODEL_NAME, "id": MODEL}] * 2,
])
def test_missing_or_ambiguous_existing_model_fails_before_connection_writes(
    models: list[dict[str, str]], monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = fake_client()
    client.list.return_value = models
    ensure = Mock()
    monkeypatch.setattr(bootstrap, "ensure_pipeline_connections", ensure)
    with pytest.raises(bootstrap.BootstrapMetadataError, match="exactly one"):
        bootstrap.collect_bindings(client, WORKSPACE, bootstrap.DEFAULT_MODEL_NAME, credentials())
    ensure.assert_not_called()


def test_invalid_credentials_fail_before_any_fabric_call() -> None:
    client = fake_client()
    with pytest.raises(FabricConnectionError):
        bootstrap.collect_bindings(
            client, WORKSPACE, bootstrap.DEFAULT_MODEL_NAME,
            {**credentials(), "servicePrincipalSecret": ""},
        )
    client.list.assert_not_called()
    client.request.assert_not_called()


def test_repeated_bootstrap_uses_shared_ensure_without_publishing_or_running(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = fake_client()
    ensure = Mock(return_value={
        bootstrap.NOTEBOOK_CONNECTION_ENV: NOTEBOOK, bootstrap.REFRESH_CONNECTION_ENV: REFRESH,
    })
    monkeypatch.setattr(bootstrap, "ensure_pipeline_connections", ensure)
    results = [
        bootstrap.collect_bindings(
            client, WORKSPACE, bootstrap.DEFAULT_MODEL_NAME, credentials(),
            notebook_connection_id=NOTEBOOK, refresh_connection_id=REFRESH,
        )
        for _ in range(2)
    ]
    assert results == [artifact().bindings, artifact().bindings]
    assert all(call.kwargs["notebook_connection_id"] == NOTEBOOK for call in ensure.call_args_list)
    assert all(call.kwargs["refresh_connection_id"] == REFRESH for call in ensure.call_args_list)
    client.request.assert_not_called()


def test_actions_main_exports_only_metadata(
    actions_environment: dict[str, str], tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str],
) -> None:
    client = fake_client()
    monkeypatch.setattr(bootstrap, "actions_client", Mock(return_value=client))
    monkeypatch.setattr(bootstrap, "ensure_pipeline_connections", Mock(return_value={
        bootstrap.NOTEBOOK_CONNECTION_ENV: NOTEBOOK, bootstrap.REFRESH_CONNECTION_ENV: REFRESH,
    }))
    output = tmp_path / bootstrap.BOOTSTRAP_FILENAME
    bootstrap.main(["--output", str(output)])
    assert bootstrap.parse_bootstrap_artifact(json.loads(output.read_text(encoding="utf-8"))) == artifact()
    log = capsys.readouterr()
    assert SECRET not in log.out + log.err
    assert WORKSPACE not in log.out + log.err
    assert TENANT not in output.read_text(encoding="utf-8")
    assert SECRET not in output.read_text(encoding="utf-8")


def test_local_execution_is_not_a_secret_based_fallback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    client = Mock()
    monkeypatch.setattr(bootstrap, "actions_client", client)
    output = tmp_path / bootstrap.BOOTSTRAP_FILENAME
    with pytest.raises(SystemExit) as result:
        bootstrap.main(["--output", str(output)])
    assert result.value.code == 1
    client.assert_not_called()
    assert not output.exists()


def test_missing_dev_secret_names_fail_before_authentication(
    actions_environment: dict[str, str], tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.delenv("AZURE_CLIENT_SECRET")
    client = Mock()
    monkeypatch.setattr(bootstrap, "actions_client", client)
    with pytest.raises(SystemExit) as result:
        bootstrap.main(["--output", str(tmp_path / bootstrap.BOOTSTRAP_FILENAME)])
    assert result.value.code == 1
    client.assert_not_called()
    log = capsys.readouterr()
    assert "Missing Dev Environment secrets: AZURE_CLIENT_SECRET" in log.err
    assert SECRET not in log.out + log.err


def test_workflow_bootstraps_only_dev_and_uploads_metadata_after_success() -> None:
    definition = yaml.load(
        (ROOT / ".github" / "workflows" / "bootstrap-dev.yml").read_text(encoding="utf-8"),
        Loader=yaml.BaseLoader,
    )
    assert definition["on"]["push"]["branches"] == ["dev"]
    assert definition["on"]["push"]["paths"] == [
        ".github/workflows/bootstrap-dev.yml", "scripts/bootstrap_dev_connections.py",
    ]
    assert "pull_request" not in definition["on"]
    assert "pull_request_target" not in definition["on"]
    assert definition["permissions"] == {"contents": "read"}
    assert definition["concurrency"] == {"group": "fabric-deploy-dev", "cancel-in-progress": "false"}
    assert set(definition["jobs"]) == {"bootstrap"}
    job = definition["jobs"]["bootstrap"]
    assert job["environment"] == "Dev"
    assert job["if"] == "github.ref == 'refs/heads/dev'"
    assert int(job["timeout-minutes"]) == 20
    commands = [step.get("run", "") for step in job["steps"]]
    assert not any("workspace_swap" in command or "sync_fabric_git" in command or "run_fabric_etl" in command
                   for command in commands)
    execute = next(step for step in job["steps"] if "bootstrap_dev_connections.py" in step.get("run", ""))
    for name in ("AZURE_TENANT_ID", "AZURE_CLIENT_ID", "AZURE_CLIENT_SECRET", "FABRIC_WORKSPACE_ID"):
        assert execute["env"][name] == f"${{{{ secrets.{name} }}}}"
    upload = job["steps"][-1]
    assert upload["with"]["name"] == bootstrap.BOOTSTRAP_ARTIFACT
    assert upload["with"]["path"] == f"bootstrap-output/{bootstrap.BOOTSTRAP_FILENAME}"
    assert upload["with"]["if-no-files-found"] == "error"
    assert "always()" not in upload.get("if", "")
    assert "continue-on-error" not in execute
    for step in job["steps"]:
        if "uses" in step:
            assert re_full_sha(step["uses"].split("@")[1])


def re_full_sha(value: str) -> bool:
    return len(value) == 40 and all(character in "0123456789abcdef" for character in value)
