"""Tests for scripts/deploy_fabric_cicd_non_bulk.py.

Covers the Phase 2 scope-filter logic. The fabric-cicd library calls
themselves are not unit-tested — those are validated end-to-end via the
deploy workflows.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import Mock

import pytest

import deploy_fabric_cicd_non_bulk as deploy
from deploy_fabric_cicd_non_bulk import PHASE1_TYPES, remaining_types_for_phase2


def test_remaining_types_none_input_returns_none() -> None:
    """When item_type_in_scope is unset, Phase 2 deploys all types."""
    assert remaining_types_for_phase2(None) is None


def test_remaining_types_empty_list_returns_none() -> None:
    """An empty list has the same effect as None."""
    assert remaining_types_for_phase2([]) is None


def test_remaining_types_no_overlap_with_phase1() -> None:
    """When the user lists only non-Phase-1 types, return them unchanged."""
    assert remaining_types_for_phase2(["Notebook", "Report"]) == ["Notebook", "Report"]


def test_remaining_types_partial_overlap_strips_phase1() -> None:
    """Phase 1 types are removed from the user's list."""
    result = remaining_types_for_phase2(
        ["Lakehouse", "Notebook", "Ontology", "Report"]
    )
    assert result == ["Notebook", "Report"]


def test_remaining_types_only_phase1_returns_none() -> None:
    """Documented footgun: listing only Phase 1 types makes Phase 2 deploy all.

    The empty result is converted to None, and FabricWorkspace treats None as
    'all types in scope'. A caller wanting strict scoping must include the
    non-Phase-1 types they actually want.
    """
    assert remaining_types_for_phase2(["Lakehouse", "Ontology"]) is None
    assert remaining_types_for_phase2(["Lakehouse"]) is None


def test_phase1_types_constant_unchanged() -> None:
    """Pin the Phase 1 type list so accidental edits are caught."""
    assert PHASE1_TYPES == ["Lakehouse", "Ontology"]


def configure_runner(monkeypatch: pytest.MonkeyPatch, repository: Path, scope: list[str] | None) -> None:
    for name, value in {
        "REPOSITORY_DIRECTORY": str(repository),
        "FABRIC_WORKSPACE_ID": "11111111-1111-4111-8111-111111111111",
        "ENVIRONMENT": "Test", "AZURE_TENANT_ID": "tenant",
        "AZURE_CLIENT_ID": "client", "AZURE_CLIENT_SECRET": "unit-test-only",
        "ITEM_TYPE_IN_SCOPE": json.dumps(scope) if scope is not None else "",
    }.items():
        monkeypatch.setenv(name, value)


@pytest.mark.parametrize("scope", [
    None, ["Lakehouse", "Ontology", "Notebook", "SemanticModel", "DataPipeline"],
])
def test_pipeline_publishes_after_its_dependencies_and_cleanup_is_last(
    canonical_fabric_repository: Path, pipeline_connection_environment: dict[str, str],
    monkeypatch: pytest.MonkeyPatch, scope: list[str] | None,
) -> None:
    configure_runner(monkeypatch, canonical_fabric_repository, scope)
    workspace = Mock()
    publish = Mock()
    cleanup = Mock()
    actions: list[tuple[str, list[str] | None]] = []
    workspace.side_effect = lambda **kwargs: Mock(config=kwargs)
    publish.side_effect = lambda value: actions.append(("publish", value.config["item_type_in_scope"]))
    cleanup.side_effect = lambda value: actions.append(("cleanup", value.config["item_type_in_scope"]))
    monkeypatch.setattr(deploy, "FabricWorkspace", workspace)
    monkeypatch.setattr(deploy, "publish_all_items", publish)
    monkeypatch.setattr(deploy, "unpublish_all_orphan_items", cleanup)
    monkeypatch.setattr(deploy, "ClientSecretCredential", Mock())
    monkeypatch.setattr(deploy, "append_feature_flag", Mock())
    deploy.main()
    assert actions[0] == ("publish", ["Lakehouse", "Ontology"])
    assert actions[1][0] == "publish"
    assert {"Notebook", "SemanticModel"} <= set(actions[1][1])
    assert "DataPipeline" not in actions[1][1]
    assert actions[2] == ("publish", ["DataPipeline"])
    assert actions[3][0] == "cleanup" and "DataPipeline" in actions[3][1]
    assert publish.call_count == 3
    cleanup.assert_called_once()


def test_only_pipeline_scope_cannot_turn_empty_phase_two_into_unrestricted_publish(
    canonical_fabric_repository: Path, pipeline_connection_environment: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    configure_runner(monkeypatch, canonical_fabric_repository, ["DataPipeline"])
    workspace = Mock(side_effect=lambda **kwargs: Mock(config=kwargs))
    publish = Mock()
    monkeypatch.setattr(deploy, "FabricWorkspace", workspace)
    monkeypatch.setattr(deploy, "publish_all_items", publish)
    monkeypatch.setattr(deploy, "unpublish_all_orphan_items", Mock())
    monkeypatch.setattr(deploy, "ClientSecretCredential", Mock())
    monkeypatch.setattr(deploy, "append_feature_flag", Mock())
    deploy.main()
    assert [call.args[0].config["item_type_in_scope"] for call in publish.call_args_list] == [
        ["Lakehouse", "Ontology"], ["DataPipeline"],
    ]


def test_missing_pipeline_connection_configuration_fails_before_authentication_or_publish(
    canonical_fabric_repository: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    configure_runner(monkeypatch, canonical_fabric_repository, None)
    monkeypatch.delenv("NOTEBOOK_CONNECTION_ID", raising=False)
    monkeypatch.delenv("SEMANTIC_MODEL_REFRESH_CONNECTION_ID", raising=False)
    monkeypatch.setenv("FABRIC_CONNECTION_MODE", "existing")
    workspace, credentials = Mock(), Mock()
    monkeypatch.setattr(deploy, "FabricWorkspace", workspace)
    monkeypatch.setattr(deploy, "ClientSecretCredential", credentials)
    with pytest.raises(ValueError, match="connection variables"):
        deploy.main()
    workspace.assert_not_called()
    credentials.assert_not_called()


@pytest.mark.parametrize("failed_phase", [1, 2, 3])
def test_publication_failure_never_runs_orphan_cleanup(
    canonical_fabric_repository: Path, pipeline_connection_environment: dict[str, str],
    monkeypatch: pytest.MonkeyPatch, failed_phase: int,
) -> None:
    configure_runner(monkeypatch, canonical_fabric_repository, None)
    workspace = Mock(side_effect=lambda **kwargs: Mock(config=kwargs))
    publish = Mock(side_effect=[None] * (failed_phase - 1) + [RuntimeError("Publish failed")])
    cleanup = Mock()
    monkeypatch.setattr(deploy, "FabricWorkspace", workspace)
    monkeypatch.setattr(deploy, "publish_all_items", publish)
    monkeypatch.setattr(deploy, "unpublish_all_orphan_items", cleanup)
    monkeypatch.setattr(deploy, "ClientSecretCredential", Mock())
    monkeypatch.setattr(deploy, "append_feature_flag", Mock())
    with pytest.raises(RuntimeError, match="Publish failed"):
        deploy.main()
    assert publish.call_count == failed_phase
    cleanup.assert_not_called()
