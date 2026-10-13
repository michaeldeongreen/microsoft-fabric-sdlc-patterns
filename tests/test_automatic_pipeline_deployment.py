"""Every publisher resolves connections without manually supplied target GUIDs."""

from __future__ import annotations

import json
import os
from pathlib import Path
from unittest.mock import Mock

import pytest

import deploy_fabric_cicd_bulk as sdk_bulk
import deploy_fabric_cicd_non_bulk as standard
import deploy_fabric_cicd_non_bulk_plan as planned
import deploy_fabric_rest_bulk as rest
import pipeline_bindings as bindings
import prepare_fabric_workspace as preparation
from deployment_plan import load_schedule
from deployment_plan_bulk import load_schedule as load_bulk_schedule

WORKSPACE = "99999999-9999-4999-8999-999999999999"
CONNECTIONS = {
    bindings.NOTEBOOK_CONNECTION_ENV: "aaaaaaa1-1111-4111-8111-111111111111",
    bindings.REFRESH_CONNECTION_ENV: "bbbbbbb2-2222-4222-8222-222222222222",
}
SCOPE = ["Lakehouse", "Ontology", "VariableLibrary", "Notebook", "SemanticModel", "Report", "DataAgent", "DataPipeline"]


@pytest.mark.parametrize("method", ["standard", "plan", "sdk-bulk", "rest"])
def test_all_publishers_bootstrap_before_any_definition_write(
    canonical_fabric_repository: Path, monkeypatch: pytest.MonkeyPatch, method: str,
) -> None:
    repository = canonical_fabric_repository
    for key, value in {
        "REPOSITORY_DIRECTORY": str(repository), "FABRIC_WORKSPACE_ID": WORKSPACE,
        "ENVIRONMENT": "Test", "ITEM_TYPE_IN_SCOPE": json.dumps(SCOPE),
        "AZURE_TENANT_ID": "77777777-1111-4777-8777-777777777777",
        "AZURE_CLIENT_ID": "88888888-2222-4888-8888-888888888888",
        "AZURE_CLIENT_SECRET": "unit-test-only", "FABRIC_CONNECTION_MODE": "auto",
        "FABRIC_RUNTIME_AUTHENTICATION": "ServicePrincipal",
    }.items():
        monkeypatch.setenv(key, value)
    for key in CONNECTIONS:
        monkeypatch.delenv(key, raising=False)
    events: list[str] = []

    def ensure(*args: object, **kwargs: object) -> dict[str, str]:
        assert kwargs["mode"] == "auto"
        assert kwargs["authentication"] == "ServicePrincipal"
        assert kwargs["notebook_connection_id"] is None
        assert kwargs["refresh_connection_id"] is None
        events.append("bootstrap")
        return CONNECTIONS

    def publish(*args: object, **kwargs: object) -> dict[str, object]:
        assert events and events[0] == "bootstrap"
        assert {key: os.environ[key] for key in CONNECTIONS} == CONNECTIONS
        events.append("publish")
        return {}

    monkeypatch.setattr(preparation, "ensure_pipeline_connections", ensure)
    credential = Mock()
    plan_path = repository / "DeploymentPlan.DeploymentPlan" / "plan.yml"
    if method == "standard":
        monkeypatch.setattr(standard, "ClientSecretCredential", Mock(return_value=credential))
        monkeypatch.setattr(standard, "FabricWorkspace", Mock())
        monkeypatch.setattr(standard, "append_feature_flag", Mock())
        monkeypatch.setattr(standard, "publish_all_items", publish)
        monkeypatch.setattr(standard, "unpublish_all_orphan_items", Mock())
        standard.main()
    elif method == "plan":
        monkeypatch.setattr(planned, "FabricWorkspace", Mock())
        monkeypatch.setattr(planned, "append_feature_flag", Mock())
        monkeypatch.setattr(planned, "remove_feature_flag", Mock())
        monkeypatch.setattr(planned, "publish_all_items", publish)
        monkeypatch.setattr(planned, "unpublish_all_orphan_items", Mock())
        planned.deploy_schedule(load_schedule(repository, plan_path), WORKSPACE, "Test", credential)
    elif method == "sdk-bulk":
        monkeypatch.setattr(sdk_bulk, "FabricWorkspace", Mock())
        monkeypatch.setattr(sdk_bulk, "append_feature_flag", Mock())
        monkeypatch.setattr(sdk_bulk, "validate_workspace_parameters", Mock())
        monkeypatch.setattr(sdk_bulk, "_publish_selection", publish)
        monkeypatch.setattr(sdk_bulk, "unpublish_all_orphan_items", Mock())
        sdk_bulk.deploy_schedule(load_bulk_schedule(repository, plan_path, SCOPE), WORKSPACE, "Test", credential)
    else:
        monkeypatch.setattr(rest, "acquire_token", Mock(return_value="unit-test-only"))
        monkeypatch.setattr(rest, "post_bulk", publish)
        monkeypatch.setattr(rest, "load_bulk_config", Mock(return_value=rest.BulkConfig()))
        with pytest.raises(SystemExit) as result:
            rest.main()
        assert result.value.code == 0
    assert events[0] == "bootstrap"
    assert events.count("bootstrap") == 1
    assert "publish" in events
