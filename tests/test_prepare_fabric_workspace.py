"""Offline baseline recording and explicit, read-only feature preparation."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import Mock

import pytest

import pipeline_bindings as pb
import prepare_fabric_workspace as prepare

WORKSPACE = "99999999-9999-4999-8999-999999999999"
CONNECTIONS = {
    pb.NOTEBOOK_CONNECTION_ENV: "aaaaaaa1-1111-4111-8111-111111111111",
    pb.REFRESH_CONNECTION_ENV: "bbbbbbb2-2222-4222-8222-222222222222",
}
MODEL = "77777777-1111-4777-8777-777777777777"


def pipeline_path(repository: Path) -> Path:
    return pb.pipeline_files(repository)[0]


def changed(bindings: pb.DevPipelineBindings) -> pb.DevPipelineBindings:
    return pb.DevPipelineBindings(bindings.workspace_id, MODEL, *CONNECTIONS.values())


def test_recording_updates_both_rules_source_but_not_platforms(canonical_fabric_repository: Path) -> None:
    repository = canonical_fabric_repository
    original = {path: path.read_bytes() for path in repository.glob("*/.platform")}
    values = changed(pb.load_dev_bindings(repository))
    prepare.record_dev_bindings(repository, values, rewrite_source=True)
    assert pb.load_dev_bindings(repository) == values
    assert prepare.validate_deployment_source(repository) == values
    assert all(path.read_bytes() == content for path, content in original.items())
    assert not (repository.parent / "fabric-dev-bindings.json").exists()


@pytest.mark.parametrize("newline", [b"\n", b"\r\n"])
def test_recording_preserves_parameter_bytes_except_ids(
    canonical_fabric_repository: Path, newline: bytes,
) -> None:
    repository = canonical_fabric_repository
    old = pb.load_dev_bindings(repository)
    new = changed(old)
    originals = {}
    for name in ("parameter.yml", "bulk-parameter.yml"):
        path = repository / name
        content = path.read_bytes().replace(b"\r\n", b"\n").replace(b"\n", newline)
        path.write_bytes(content)
        originals[path] = content
    prepare.record_dev_bindings(repository, new)
    for path, content in originals.items():
        for label, value in old.values.items():
            content = content.replace(value.encode("utf-8"), new.values[label].encode("utf-8"))
        assert path.read_bytes() == content


def test_recording_can_leave_active_feature_source_untouched(canonical_fabric_repository: Path) -> None:
    repository = canonical_fabric_repository
    original = pipeline_path(repository).read_bytes()
    prepare.record_dev_bindings(repository, changed(pb.load_dev_bindings(repository)))
    assert pipeline_path(repository).read_bytes() == original
    with pytest.raises(pb.PipelineBindingError, match="Dev baseline"):
        prepare.validate_deployment_source(repository)


def test_changed_baseline_requires_explicit_cutover(canonical_fabric_repository: Path) -> None:
    repository = canonical_fabric_repository
    values = changed(pb.load_dev_bindings(repository))
    before = (repository / "parameter.yml").read_bytes()
    with pytest.raises(pb.PipelineBindingError, match="reviewed cutover"):
        prepare.prepare_dev(repository, values)
    assert (repository / "parameter.yml").read_bytes() == before
    assert prepare.prepare_dev(repository, values, replace_bindings=True, rewrite_source=True) == values
    assert prepare.validate_deployment_source(repository) == values


def test_rule_disagreement_prevents_writes(canonical_fabric_repository: Path) -> None:
    repository = canonical_fabric_repository
    old = pb.load_dev_bindings(repository)
    path = repository / "bulk-parameter.yml"
    path.write_text(path.read_text(encoding="utf-8").replace(old.notebook_connection_id, MODEL), encoding="utf-8")
    before = (repository / "parameter.yml").read_bytes()
    with pytest.raises(pb.PipelineBindingError, match="must agree"):
        prepare.record_dev_bindings(repository, old)
    assert (repository / "parameter.yml").read_bytes() == before


def test_upper_publishers_cannot_overwrite_dev(canonical_fabric_repository: Path) -> None:
    current = pb.load_dev_bindings(canonical_fabric_repository)
    with pytest.raises(pb.PipelineBindingError, match="must not target Git-synced Dev"):
        prepare.validate_deployment_source(canonical_fabric_repository, target_workspace_id=current.workspace_id.upper())


def test_dev_cli_is_offline_and_uses_only_local_ids(
    canonical_fabric_repository: Path, monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    values = pb.load_dev_bindings(canonical_fabric_repository)
    env = tmp_path / ".env"
    env.write_text("\n".join(f"{key}={value}" for key, value in {
        "DEV_WORKSPACE_ID": values.workspace_id, "DEV_SEMANTIC_MODEL_ID": values.semantic_model_id,
        "DEV_NOTEBOOK_CONNECTION_ID": values.notebook_connection_id, "DEV_REFRESH_CONNECTION_ID": values.refresh_connection_id,
    }.items()), encoding="utf-8")
    monkeypatch.setattr(prepare, "ENV_FILE", env)
    client = Mock(side_effect=AssertionError("No Azure or GitHub access in local Dev preparation"))
    monkeypatch.setattr(prepare, "create_client", client)
    for key in ("AZURE_CLIENT_SECRET", "GH_ENV_VARIABLES_TOKEN"):
        monkeypatch.delenv(key, raising=False)
    prepare.main(["--dev", "--repository-directory", str(canonical_fabric_repository)])
    client.assert_not_called()
    assert prepare.validate_deployment_source(canonical_fabric_repository) == values


def test_duplicate_local_ids_rejected(tmp_path: Path) -> None:
    path = tmp_path / ".env"
    path.write_text("DEV_WORKSPACE_ID=x\nDEV_WORKSPACE_ID=y", encoding="utf-8")
    with pytest.raises(pb.PipelineBindingError, match="Duplicate"):
        prepare.local_dev_bindings(path)


def test_dry_run_is_local_and_read_only(
    canonical_fabric_repository: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    original = {path: path.read_bytes() for path in canonical_fabric_repository.rglob("*") if path.is_file()}
    client = Mock()
    monkeypatch.setattr(prepare, "create_client", client)
    prepare.main(["--dev", "--repository-directory", str(canonical_fabric_repository), "--dry-run"])
    client.assert_not_called()
    assert all(path.read_bytes() == value for path, value in original.items())


@pytest.mark.parametrize("mode", ["auto", "AUTO", "existing ", "typo"])
def test_publishers_cannot_implicitly_provision(mode: str) -> None:
    with pytest.raises(pb.PipelineBindingError, match="FABRIC_CONNECTION_MODE"):
        prepare.connection_mode({"FABRIC_CONNECTION_MODE": mode})


def test_publishers_require_both_ids() -> None:
    with pytest.raises(pb.PipelineBindingError, match="connection variables"):
        prepare.connection_mode({})
    assert prepare.connection_mode(CONNECTIONS) == "existing"
    assert prepare.runtime_authentication({}) == "WorkspaceIdentity"
    with pytest.raises(pb.PipelineBindingError, match="WorkspaceIdentity"):
        prepare.runtime_authentication({"FABRIC_RUNTIME_AUTHENTICATION": "ServicePrincipal"})


def test_readonly_target_ids_feed_all_publishers(
    canonical_fabric_repository: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    for key, value in CONNECTIONS.items():
        monkeypatch.setenv(key, value)
    monkeypatch.delenv("FABRIC_CONNECTION_MODE", raising=False)
    monkeypatch.delenv("FABRIC_RUNTIME_AUTHENTICATION", raising=False)
    ensure = Mock(return_value=CONNECTIONS)
    monkeypatch.setattr(prepare, "ensure_pipeline_connections", ensure)
    assert prepare.prepare_pipeline_connections(canonical_fabric_repository, WORKSPACE, lambda: "test-token") == CONNECTIONS
    assert ensure.call_args.kwargs["mode"] == "existing"
    assert ensure.call_args.kwargs["authentication"] == "WorkspaceIdentity"
    assert ensure.call_args.kwargs["credentials"] is None


def test_initial_import_stages_and_restores_exact_canonical_item(canonical_fabric_repository: Path) -> None:
    repository = canonical_fabric_repository
    folder = pipeline_path(repository).parent
    original = {path.name: path.read_bytes() for path in folder.iterdir() if path.is_file()}
    prepare.stage_initial_pipeline(repository, restore=False)
    assert not pb.pipeline_files(repository)
    assert (repository.parent / "fabric-initialization" / folder.name / ".platform").is_file()
    prepare.stage_initial_pipeline(repository, restore=True)
    assert {path.name: path.read_bytes() for path in folder.iterdir() if path.is_file()} == original
    assert not (repository.parent / "fabric-initialization").exists()


def test_staged_pipeline_can_be_rebound_before_first_import(canonical_fabric_repository: Path) -> None:
    repository = canonical_fabric_repository
    prepare.stage_initial_pipeline(repository, restore=False)
    values = changed(pb.load_dev_bindings(repository))
    prepare.record_dev_bindings(repository, values, rewrite_source=True)
    prepare.stage_initial_pipeline(repository, restore=True)
    assert prepare.validate_deployment_source(repository) == values


def test_initial_stage_never_overwrites_existing_items(canonical_fabric_repository: Path) -> None:
    repository = canonical_fabric_repository
    destination = repository.parent / "fabric-initialization" / pipeline_path(repository).parent.name
    destination.mkdir(parents=True)
    with pytest.raises(pb.PipelineBindingError, match="overwrite"):
        prepare.stage_initial_pipeline(repository, restore=False)
    assert pipeline_path(repository).exists()


def test_failed_local_write_restores_files(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
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
