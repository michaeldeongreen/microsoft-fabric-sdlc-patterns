"""Offline preparation/source contracts; Fabric API behavior has its own tests."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import Mock

import pytest

import pipeline_bindings as pb
import prepare_fabric_workspace as prepare

TARGET_WORKSPACE = "99999999-9999-4999-8999-999999999999"
TARGET_CONNECTIONS = {
    pb.NOTEBOOK_CONNECTION_ENV: "aaaaaaa1-1111-4111-8111-111111111111",
    pb.REFRESH_CONNECTION_ENV: "bbbbbbb2-2222-4222-8222-222222222222",
}
REPLACEMENT_CONNECTIONS = {
    pb.NOTEBOOK_CONNECTION_ENV: "55555555-1111-4555-8555-555555555555",
    pb.REFRESH_CONNECTION_ENV: "66666666-2222-4666-8666-666666666666",
}


@pytest.fixture(autouse=True)
def runtime_identity(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AZURE_TENANT_ID", "77777777-1111-4777-8777-777777777777")
    monkeypatch.setenv("AZURE_CLIENT_ID", "88888888-2222-4888-8888-888888888888")
    monkeypatch.setenv("AZURE_CLIENT_SECRET", "unit-test-only-never-log")
    monkeypatch.delenv("FABRIC_RUNTIME_AUTHENTICATION", raising=False)


def pipeline_path(repository: Path) -> Path:
    return next(iter(pb.pipeline_files(repository)))


def test_recording_updates_both_rules_manifest_and_source_without_platform_changes(
    canonical_fabric_repository: Path,
) -> None:
    repository = canonical_fabric_repository
    old = pb.load_dev_bindings(repository)
    platforms = {path: path.read_bytes() for path in repository.glob("*/.platform")}
    comments = {
        path: [line for line in path.read_text(encoding="utf-8").splitlines() if line.lstrip().startswith("#")]
        for path in (repository / "parameter.yml", repository / "bulk-parameter.yml")
    }
    new = pb.DevPipelineBindings(
        old.workspace_id, old.semantic_model_id,
        REPLACEMENT_CONNECTIONS[pb.NOTEBOOK_CONNECTION_ENV], REPLACEMENT_CONNECTIONS[pb.REFRESH_CONNECTION_ENV],
    )
    prepare.record_dev_bindings(repository, new, rewrite_source=True)
    assert pb.load_dev_bindings(repository) == new
    for bulk in (False, True):
        assert prepare.validate_deployment_source(repository, bulk=bulk) == new
    for path, original in platforms.items():
        assert path.read_bytes() == original
    for path, original in comments.items():
        assert [line for line in path.read_text(encoding="utf-8").splitlines()
                if line.lstrip().startswith("#")] == original
    notebook_ids = [
        activity["typeProperties"]["notebookId"]
        for activity in json.loads(pipeline_path(repository).read_text(encoding="utf-8"))["properties"]["activities"]
        if activity["type"] == pb.NOTEBOOK_ACTIVITY_TYPE
    ]
    assert notebook_ids == ["3f21b546-f49f-9fef-4881-99b654a6701e", "decdcb11-8770-4216-8a28-eadf505d2679"]


def test_preparation_can_record_dev_without_changing_active_feature_definition(
    canonical_fabric_repository: Path,
) -> None:
    repository = canonical_fabric_repository
    old = pb.load_dev_bindings(repository)
    path = pipeline_path(repository)
    feature = pb.rewrite(path.read_text(encoding="utf-8"), {
        "Semantic model": "77777777-1111-4777-8777-777777777777",
        "Notebook connection": TARGET_CONNECTIONS[pb.NOTEBOOK_CONNECTION_ENV],
        "Refresh connection": TARGET_CONNECTIONS[pb.REFRESH_CONNECTION_ENV],
        "Refresh workspace": TARGET_WORKSPACE,
    })
    path.write_text(feature, encoding="utf-8")
    prepare.record_dev_bindings(repository, old)
    assert path.read_text(encoding="utf-8") == feature
    with pytest.raises(pb.PipelineBindingError, match="Dev baseline"):
        prepare.validate_deployment_source(repository)


@pytest.mark.parametrize("bulk", [False, True])
def test_replacement_rules_cannot_silently_miss_valid_source(
    canonical_fabric_repository: Path, bulk: bool,
) -> None:
    repository = canonical_fabric_repository
    bindings = pb.load_dev_bindings(repository)
    path = repository / ("bulk-parameter.yml" if bulk else "parameter.yml")
    path.write_text(
        path.read_text(encoding="utf-8").replace(
            bindings.notebook_connection_id, TARGET_CONNECTIONS[pb.NOTEBOOK_CONNECTION_ENV],
        ), encoding="utf-8",
    )
    with pytest.raises(pb.PipelineBindingError, match="does not match"):
        prepare.validate_deployment_source(repository, bulk=bulk)


def test_upper_publishers_cannot_overwrite_git_synced_dev(canonical_fabric_repository: Path) -> None:
    bindings = pb.load_dev_bindings(canonical_fabric_repository)
    with pytest.raises(pb.PipelineBindingError, match="must not target Git-synced Dev"):
        prepare.validate_deployment_source(
            canonical_fabric_repository, target_workspace_id=bindings.workspace_id.upper(),
        )


def test_parameter_disagreement_fails_before_provisioning(
    canonical_fabric_repository: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository = canonical_fabric_repository
    bindings = pb.load_dev_bindings(repository)
    path = repository / "bulk-parameter.yml"
    path.write_text(
        path.read_text(encoding="utf-8").replace(
            bindings.refresh_connection_id, TARGET_CONNECTIONS[pb.REFRESH_CONNECTION_ENV],
        ), encoding="utf-8",
    )
    ensure = Mock()
    monkeypatch.setattr(prepare, "ensure_pipeline_connections", ensure)
    with pytest.raises(pb.PipelineBindingError, match="must agree"):
        prepare.prepare_dev(repository, Mock(spec=prepare.FabricRestClient))
    ensure.assert_not_called()


def test_deleted_or_recreated_dev_model_is_not_silently_rebaselined(
    canonical_fabric_repository: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository = canonical_fabric_repository
    old = pb.dev_bindings_path(repository).read_bytes()
    client = Mock(spec=prepare.FabricRestClient)
    client.list.return_value = [{
        "displayName": "Patterns_Semantic_Model", "type": "SemanticModel",
        "id": "77777777-1111-4777-8777-777777777777",
    }]
    ensure = Mock()
    monkeypatch.setattr(prepare, "ensure_pipeline_connections", ensure)
    with pytest.raises(pb.PipelineBindingError, match="recreated"):
        prepare.prepare_dev(repository, client)
    ensure.assert_not_called()
    assert pb.dev_bindings_path(repository).read_bytes() == old


def test_existing_dev_connection_ids_are_pinned_during_repeat_preparation(
    canonical_fabric_repository: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository = canonical_fabric_repository
    bindings = pb.load_dev_bindings(repository)
    client = Mock(spec=prepare.FabricRestClient)
    client.list.return_value = [{
        "displayName": "Patterns_Semantic_Model", "type": "SemanticModel", "id": bindings.semantic_model_id,
    }]
    ensure = Mock(return_value={
        pb.NOTEBOOK_CONNECTION_ENV: bindings.notebook_connection_id,
        pb.REFRESH_CONNECTION_ENV: bindings.refresh_connection_id,
    })
    monkeypatch.setattr(prepare, "ensure_pipeline_connections", ensure)
    for _ in range(2):
        assert prepare.prepare_dev(repository, client) == bindings
    for call in ensure.call_args_list:
        assert call.kwargs["notebook_connection_id"] == bindings.notebook_connection_id
        assert call.kwargs["refresh_connection_id"] == bindings.refresh_connection_id
        assert call.kwargs["authentication"] == "ServicePrincipal"
        assert call.kwargs["credentials"]["servicePrincipalSecret"] == "unit-test-only-never-log"


def test_explicit_replacement_updates_source_under_review_not_github(
    canonical_fabric_repository: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository = canonical_fabric_repository
    old = pb.load_dev_bindings(repository)
    client = Mock(spec=prepare.FabricRestClient)
    model = "77777777-1111-4777-8777-777777777777"
    client.list.return_value = [{"displayName": "Patterns_Semantic_Model", "type": "SemanticModel", "id": model}]
    ensure = Mock(return_value=REPLACEMENT_CONNECTIONS)
    monkeypatch.setattr(prepare, "ensure_pipeline_connections", ensure)
    bindings = prepare.prepare_dev(repository, client, replace_bindings=True, rewrite_source=True)
    assert bindings.workspace_id == old.workspace_id
    assert bindings.semantic_model_id == model
    assert ensure.call_args.kwargs["notebook_connection_id"] is None
    assert ensure.call_args.kwargs["refresh_connection_id"] is None
    assert prepare.validate_deployment_source(repository) == bindings


def test_auto_mode_needs_no_manually_entered_target_ids(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in (pb.NOTEBOOK_CONNECTION_ENV, pb.REFRESH_CONNECTION_ENV, "FABRIC_CONNECTION_MODE"):
        monkeypatch.delenv(name, raising=False)
    assert prepare.connection_mode() == "auto"


def test_existing_mode_reports_missing_values_without_api_calls(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in (pb.NOTEBOOK_CONNECTION_ENV, pb.REFRESH_CONNECTION_ENV):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("FABRIC_CONNECTION_MODE", "existing")
    with pytest.raises(pb.PipelineBindingError, match="connection variables"):
        prepare.connection_mode()


@pytest.mark.parametrize("value", ["AUTO", "typo", " auto", "existing "])
def test_unknown_modes_are_not_silent_defaults(value: str) -> None:
    with pytest.raises(pb.PipelineBindingError, match="FABRIC_CONNECTION_MODE"):
        prepare.connection_mode({"FABRIC_CONNECTION_MODE": value})


def test_automatic_ids_feed_sdk_and_raw_rest_contract(
    canonical_fabric_repository: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    for name in (pb.NOTEBOOK_CONNECTION_ENV, pb.REFRESH_CONNECTION_ENV):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("FABRIC_CONNECTION_MODE", "auto")
    ensure = Mock(return_value=TARGET_CONNECTIONS)
    monkeypatch.setattr(prepare, "ensure_pipeline_connections", ensure)
    tokens = Mock(return_value="unit-test-only")
    assert prepare.prepare_pipeline_connections(canonical_fabric_repository, TARGET_WORKSPACE, tokens) == TARGET_CONNECTIONS
    assert pb.require_pipeline_connections(canonical_fabric_repository) == TARGET_CONNECTIONS
    assert ensure.call_args.kwargs["mode"] == "auto"
    assert ensure.call_args.kwargs["notebook_connection_id"] is None
    assert ensure.call_args.kwargs["refresh_connection_id"] is None
    assert ensure.call_args.kwargs["authentication"] == "ServicePrincipal"


def test_incomplete_bootstrap_output_cannot_fall_back_to_old_environment_ids(
    canonical_fabric_repository: Path, pipeline_connection_environment: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(prepare, "ensure_pipeline_connections", Mock(return_value={}))
    with pytest.raises(pb.PipelineBindingError, match="did not return"):
        prepare.prepare_pipeline_connections(
            canonical_fabric_repository, TARGET_WORKSPACE, lambda: "unit-test-only",
        )


def test_dry_run_has_no_credentials_no_cloud_calls_and_no_edits(
    canonical_fabric_repository: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = Mock()
    monkeypatch.setattr(prepare, "create_client", client)
    original = {path: path.read_bytes() for path in [
        pb.dev_bindings_path(canonical_fabric_repository), pipeline_path(canonical_fabric_repository),
        canonical_fabric_repository / "parameter.yml", canonical_fabric_repository / "bulk-parameter.yml",
    ]}
    prepare.main(["--dev", "--repository-directory", str(canonical_fabric_repository), "--dry-run"])
    client.assert_not_called()
    assert all(path.read_bytes() == contents for path, contents in original.items())


def test_failed_local_write_restores_owned_files(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    first, second = tmp_path / "first.json", tmp_path / "second.json"
    first.write_text("original-first", encoding="utf-8")
    second.write_text("original-second", encoding="utf-8")
    replace = Path.replace

    def fail_second(path: Path, destination: str | Path) -> Path:
        if Path(destination) == second:
            raise PermissionError("unit-test-only")
        return replace(path, destination)

    monkeypatch.setattr(Path, "replace", fail_second)
    with pytest.raises(pb.PipelineBindingError, match="rolled back"):
        prepare._write_updates({first: "updated-first", second: "updated-second"})
    assert first.read_text(encoding="utf-8") == "original-first"
    assert second.read_text(encoding="utf-8") == "original-second"
    assert {path.name for path in tmp_path.iterdir()} == {"first.json", "second.json"}
