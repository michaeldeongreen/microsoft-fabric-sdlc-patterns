"""Real non-bulk SDK replacement and transport, with every HTTP call mocked."""

from __future__ import annotations

import base64
import json
import time
from pathlib import Path
from unittest.mock import Mock, patch
from urllib.parse import urlsplit
from uuid import NAMESPACE_DNS, uuid5

import pytest
from azure.core.credentials import AccessToken, TokenCredential

import deploy_fabric_cicd_non_bulk as standard
import deploy_fabric_cicd_non_bulk_plan as planned
from deployment_plan import load_schedule

WORKSPACE = "99999999-9999-4999-8999-999999999999"


@pytest.mark.parametrize("method", ["standard", "plan"])
def test_pipeline_bindings_are_resolved_after_model_and_notebooks_exist(
    canonical_fabric_repository: Path, pipeline_connection_environment: dict[str, str],
    monkeypatch: pytest.MonkeyPatch, method: str,
) -> None:
    from fabric_cicd import constants
    from fabric_cicd._common._fabric_endpoint import FabricEndpoint

    repository = canonical_fabric_repository
    metadata = {
        json.loads(path.read_text(encoding="utf-8"))["metadata"]["displayName"]:
        json.loads(path.read_text(encoding="utf-8"))
        for path in repository.glob("*/.platform")
    }
    ids = {name: str(uuid5(NAMESPACE_DNS, name)) for name in metadata}
    deployed: dict[str, dict[str, object]] = {}
    pipeline_payloads: list[dict] = []
    publications: list[str] = []
    root = f"/v1/workspaces/{WORKSPACE}"

    def invoke(method: str, url: str, body: object = None, **kwargs: object) -> dict:
        path = urlsplit(url).path
        result = {"header": {}, "body": {}, "status_code": 200}
        if method == "GET" and path == root:
            result["body"] = {"capacityId": ids["PatternsLakehouse"]}
        elif method == "GET" and path == f"{root}/items":
            result["body"] = {"value": list(deployed.values())}
        elif method == "GET" and path == f"{root}/folders":
            result["body"] = {"value": []}
        elif method == "GET" and path.startswith(f"{root}/lakehouses/"):
            result["body"] = {"properties": {"sqlEndpointProperties": {
                "id": ids["PatternsLakehouse"], "connectionString": "offline.example.test",
                "provisioningStatus": "Success",
            }}}
        elif method == "GET" and path.endswith("/shortcuts"):
            result["body"] = {"value": []}
        elif method == "POST" and path == f"{root}/items":
            assert isinstance(body, dict)
            name = body["displayName"]
            deployed[name] = {
                "id": ids[name], "displayName": name, "type": body["type"],
                "description": "", "folderId": "",
            }
            publications.append(name)
            result["body"] = {"id": ids[name]}
            if body["type"] == "DataPipeline":
                pipeline_payloads.append(body)
        elif method == "POST" and path.endswith("/updateDefinition"):
            assert isinstance(body, dict)
            if path == f"{root}/items/{ids['Patterns_Load_Validate_And_Refresh']}/updateDefinition":
                pipeline_payloads.append(body)
        elif method == "PATCH" and path == f"{root}/VariableLibraries/{ids['Patterns_Variables']}":
            assert isinstance(body, dict)
            assert body["properties"]["activeValueSetName"] == "Test"
        elif method == "PATCH" and path.startswith(f"{root}/items/"):
            pass
        else:
            raise AssertionError(f"Unexpected SDK HTTP: {method} {url}")
        return result

    monkeypatch.setattr(constants, "FEATURE_FLAG", set())
    monkeypatch.setattr(FabricEndpoint, "invoke", staticmethod(invoke))
    credential = Mock(spec=TokenCredential)
    credential.get_token.return_value = AccessToken("unit-test-token", int(time.time()) + 3600)
    for name, value in {
        "REPOSITORY_DIRECTORY": str(repository), "FABRIC_WORKSPACE_ID": WORKSPACE,
        "ENVIRONMENT": "Test", "ITEM_TYPE_IN_SCOPE": json.dumps([
            "Lakehouse", "Ontology", "Notebook", "VariableLibrary", "SemanticModel",
            "DataAgent", "Report", "DataPipeline",
        ]),
    }.items():
        monkeypatch.setenv(name, value)
    schedule = load_schedule(repository, repository / "DeploymentPlan.DeploymentPlan" / "plan.yml")
    with patch("requests.sessions.Session.request", side_effect=AssertionError("Real HTTP is forbidden")):
        for _ in range(2):
            if method == "standard":
                monkeypatch.setattr(standard, "ClientSecretCredential", Mock(return_value=credential))
                monkeypatch.setenv("AZURE_TENANT_ID", WORKSPACE)
                monkeypatch.setenv("AZURE_CLIENT_ID", WORKSPACE)
                monkeypatch.setenv("AZURE_CLIENT_SECRET", "unit-test-only")
                standard.main()
            else:
                planned.deploy_schedule(schedule, WORKSPACE, "Test", credential)

    assert len(pipeline_payloads) == 2
    assert publications.index("Patterns_Load_Validate_And_Refresh") > publications.index("Patterns_Semantic_Model")
    for payload in pipeline_payloads:
        content = json.loads(base64.b64decode(next(
            part["payload"] for part in payload["definition"]["parts"] if part["path"] == "pipeline-content.json"
        )))
        activities = content["properties"]["activities"]
        for activity in activities[:2]:
            assert activity["typeProperties"]["notebookId"] == ids[activity["name"]]
            assert activity["typeProperties"]["workspaceId"] == WORKSPACE
            assert activity["externalReferences"]["connection"] == pipeline_connection_environment["NOTEBOOK_CONNECTION_ID"]
        assert activities[2]["typeProperties"]["datasetId"] == ids["Patterns_Semantic_Model"]
        assert activities[2]["typeProperties"]["groupId"] == WORKSPACE
        assert activities[2]["externalReferences"]["connection"] == pipeline_connection_environment["SEMANTIC_MODEL_REFRESH_CONNECTION_ID"]
