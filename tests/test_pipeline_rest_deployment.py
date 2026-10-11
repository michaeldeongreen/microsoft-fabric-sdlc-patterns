"""Mocked raw REST publication keeps DataPipeline after its physical model."""

from __future__ import annotations

import base64
import json
from pathlib import Path
from unittest.mock import Mock
from uuid import NAMESPACE_DNS, uuid5

import pytest

import deploy_fabric_rest_bulk as deploy

WORKSPACE = "99999999-9999-4999-8999-999999999999"


def test_raw_rest_cold_pipeline_bindings_and_single_value_set_activation(
    canonical_fabric_repository: Path, pipeline_connection_environment: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for key, value in {
        "REPOSITORY_DIRECTORY": str(canonical_fabric_repository),
        "AZURE_TENANT_ID": "tenant", "AZURE_CLIENT_ID": "client",
        "AZURE_CLIENT_SECRET": "unit-test-only", "FABRIC_WORKSPACE_ID": WORKSPACE,
        "ENVIRONMENT": "Test",
    }.items():
        monkeypatch.setenv(key, value)
    monkeypatch.setattr(deploy, "acquire_token", Mock(return_value="unit-test-token"))
    publications: list[list[deploy.DefinitionPart]] = []
    item_ids: dict[tuple[str, str], str] = {}

    def publish(parts: list[deploy.DefinitionPart], *args: object, **kwargs: object) -> deploy.BulkResponseBody:
        publications.append(parts)
        details: list[deploy.ImportItemDetail] = []
        for part in parts:
            if part["path"].endswith("/.platform"):
                metadata = json.loads(base64.b64decode(part["payload"]))["metadata"]
                key = (metadata["type"], metadata["displayName"])
                item_ids[key] = str(uuid5(NAMESPACE_DNS, f"{key[0]}.{key[1]}"))
                details.append({
                    "itemType": key[0], "itemDisplayName": key[1],
                    "itemId": item_ids[key], "operationStatus": "Succeeded",
                })
        return {"importItemDefinitionsDetails": details}

    monkeypatch.setattr(deploy, "post_bulk", publish)
    activation = Mock()
    monkeypatch.setattr(deploy, "activate_variable_library_value_set", activation)
    with pytest.raises(SystemExit) as result:
        deploy.main()
    assert result.value.code == 0
    assert len(publications) == 3
    types = [{deploy.item_type_of(part["path"]) for part in batch} for batch in publications]
    assert types[0] == {"Lakehouse", "Ontology"}
    assert "SemanticModel" in types[1] and "Notebook" in types[1]
    assert "DataPipeline" not in types[1]
    assert types[2] == {"DataPipeline"}
    pipeline = json.loads(next(
        base64.b64decode(part["payload"]).decode("utf-8")
        for part in publications[2] if part["path"].endswith("pipeline-content.json")
    ))
    activities = pipeline["properties"]["activities"]
    for activity in activities[:2]:
        assert activity["externalReferences"]["connection"] == pipeline_connection_environment["NOTEBOOK_CONNECTION_ID"]
        assert activity["typeProperties"]["workspaceId"] == "00000000-0000-0000-0000-000000000000"
    refresh = activities[2]
    assert refresh["typeProperties"]["groupId"] == WORKSPACE
    assert refresh["typeProperties"]["datasetId"] == item_ids[("SemanticModel", "Patterns_Semantic_Model")]
    assert refresh["externalReferences"]["connection"] == pipeline_connection_environment["SEMANTIC_MODEL_REFRESH_CONNECTION_ID"]
    activation.assert_called_once()
    assert activation.call_args.args[:3] == (WORKSPACE, item_ids[("VariableLibrary", "Patterns_Variables")], "Test")


def test_raw_rest_missing_connections_fail_before_authentication(
    canonical_fabric_repository: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    for key, value in {
        "REPOSITORY_DIRECTORY": str(canonical_fabric_repository),
        "AZURE_TENANT_ID": "tenant", "AZURE_CLIENT_ID": "client",
        "AZURE_CLIENT_SECRET": "unit-test-only", "FABRIC_WORKSPACE_ID": WORKSPACE,
    }.items():
        monkeypatch.setenv(key, value)
    monkeypatch.delenv("NOTEBOOK_CONNECTION_ID", raising=False)
    monkeypatch.delenv("SEMANTIC_MODEL_REFRESH_CONNECTION_ID", raising=False)
    auth, publish = Mock(), Mock()
    monkeypatch.setattr(deploy, "acquire_token", auth)
    monkeypatch.setattr(deploy, "post_bulk", publish)
    with pytest.raises(ValueError, match="connection variables"):
        deploy.main()
    auth.assert_not_called()
    publish.assert_not_called()
