"""Strict bulk contracts, isolated plan execution, and actual SDK transport."""

from __future__ import annotations

import base64
import hashlib
import importlib
import json
import shutil
import sys
import time
from collections.abc import Iterator
from dataclasses import replace
from pathlib import Path
from typing import TypedDict
from unittest import mock
from urllib.parse import urlsplit
from uuid import NAMESPACE_DNS, UUID, uuid5

import pytest
import yaml
from azure.core.credentials import AccessToken, TokenCredential

import deploy_fabric_cicd_bulk as deploy
from deployment_plan_bulk import BulkDeploymentSchedule, DeploymentGroup, RepositoryItem, load_schedule

REPO_ROOT = Path(__file__).resolve().parents[1]
PLAN_PATH = REPO_ROOT / "data" / "fabric" / "DeploymentPlan.DeploymentPlan" / "plan.yml"
WORKSPACE_ID = "11111111-1111-1111-1111-111111111111"
SCOPE = ["Lakehouse", "Ontology", "VariableLibrary", "Notebook", "SemanticModel", "Report", "DataAgent"]
SOURCE_WORKSPACE_ID = "d7270f11-feba-4990-baa6-d45e47f23737"
SOURCE_LAKEHOUSE_ID = "c185283c-9dd9-4e40-a17c-aa6303e3a2e9"


@pytest.fixture
def schedule() -> BulkDeploymentSchedule:
    return load_schedule(REPO_ROOT / "data" / "fabric", PLAN_PATH, SCOPE)


class ItemResponse(TypedDict):
    status_code: object
    body: dict[str, object]


def _results(selectors: list[str]) -> dict[str, dict[str, ItemResponse]]:
    results: dict[str, dict[str, ItemResponse]] = {}
    for selector in selectors:
        name, item_type = selector.rsplit(".", 1)
        results.setdefault(item_type, {})[name] = {
            "status_code": 200,
            "body": {
                "itemType": item_type, "itemDisplayName": name,
                "itemId": str(uuid5(NAMESPACE_DNS, selector)),
                "operationStatus": "Succeeded", "operationType": "Create",
            },
        }
    return results


def _workspace(**kwargs: object) -> mock.Mock:
    workspace = mock.Mock()
    workspace.config = kwargs
    workspace.environment = kwargs["environment"]
    workspace.environment_parameter = {}
    workspace.bulk_publish_enabled = True
    return workspace


def test_exact_grouped_selections_fresh_state_and_single_cleanup(schedule: BulkDeploymentSchedule) -> None:
    credential = mock.Mock(spec=TokenCredential)
    instances: list[mock.Mock] = []
    published: list[str] = []

    def make_workspace(**kwargs: object) -> mock.Mock:
        workspace = _workspace(**kwargs)
        workspace.visible_at_creation = tuple(published)
        instances.append(workspace)
        return workspace

    def publish(workspace: mock.Mock, *, items_to_include: list[str]) -> dict:
        if "Patterns_Semantic_Model.SemanticModel" in items_to_include:
            assert "PatternsLakehouse.Lakehouse" in workspace.visible_at_creation
        if "Patterns_Data_Agent.DataAgent" in items_to_include:
            assert "Patterns_Ontology.Ontology" in workspace.visible_at_creation
        if "Patterns_Report.Report" in items_to_include:
            assert "Patterns_Semantic_Model.SemanticModel" in workspace.visible_at_creation
        published.extend(items_to_include)
        return _results(items_to_include)

    with (
        mock.patch.object(deploy, "FabricWorkspace", side_effect=make_workspace),
        mock.patch.object(deploy, "publish_all_items", side_effect=publish) as publish_mock,
        mock.patch.object(deploy, "unpublish_all_orphan_items") as cleanup,
        mock.patch.object(deploy, "append_feature_flag") as enable,
    ):
        deploy.deploy_schedule(schedule, WORKSPACE_ID, "Test", credential)
    assert [call.kwargs["items_to_include"] for call in publish_mock.call_args_list] == [
        ["PatternsLakehouse.Lakehouse"],
        ["Patterns_Ontology.Ontology", "Patterns_Semantic_Model.SemanticModel"],
        ["Patterns_Data_Agent.DataAgent"],
        [item.selector for item in schedule.remaining_items],
    ]
    assert len(published) == len(set(published)) == 9
    assert len(instances) == 6
    assert [instance.config["item_type_in_scope"] for instance in instances] == [
        sorted(SCOPE),
        ["Lakehouse"], ["Ontology", "SemanticModel"], ["DataAgent"],
        ["Notebook", "Report", "VariableLibrary"],
        ["DataAgent", "Notebook", "Report", "SemanticModel", "VariableLibrary"],
    ]
    cleanup.assert_called_once_with(instances[-1])
    assert enable.call_args_list == [mock.call(flag) for flag in deploy.BULK_FEATURE_FLAGS]
    for instance in instances:
        assert instance.config["repository_directory"] == str(schedule.repository_directory)
        assert instance.config["workspace_id"] == WORKSPACE_ID
        assert instance.config["environment"] == "Test"
        assert instance.config["token_credential"] is credential


@pytest.mark.parametrize("failure_call", [1, 2, 3, 4])
@pytest.mark.parametrize("failure", ["exception", "fallback", "partial", "missing"])
def test_failures_stop_later_selections_and_cleanup(
    schedule: BulkDeploymentSchedule, failure_call: int, failure: str,
) -> None:
    calls = 0

    def publish(workspace: mock.Mock, *, items_to_include: list[str]) -> object:
        nonlocal calls
        calls += 1
        if calls == failure_call:
            if failure == "exception":
                raise RuntimeError("SDK failure")
            if failure == "fallback":
                workspace.bulk_publish_enabled = False
            if failure == "missing":
                return None
        results = _results(items_to_include)
        if calls == failure_call and failure == "partial":
            first_type = next(iter(results))
            first_name = next(iter(results[first_type]))
            results[first_type][first_name]["body"]["operationStatus"] = "SucceededDespiteFailures"
        return results

    with (
        mock.patch.object(deploy, "FabricWorkspace", side_effect=_workspace),
        mock.patch.object(deploy, "publish_all_items", side_effect=publish),
        mock.patch.object(deploy, "unpublish_all_orphan_items") as cleanup,
        mock.patch.object(deploy, "append_feature_flag"),
        pytest.raises(RuntimeError),
    ):
        deploy.deploy_schedule(schedule, WORKSPACE_ID, "Test", mock.Mock(spec=TokenCredential))
    assert calls == failure_call
    cleanup.assert_not_called()


@pytest.mark.parametrize("status", ["Failed", "SucceededDespiteFailures", "Running", "NotStarted", "Unknown", None, 1])
def test_only_confirmed_success_is_accepted(tmp_path: Path, status: object) -> None:
    item = RepositoryItem(str(UUID(int=1)), "Item", "Notebook", tmp_path)
    results = _results([item.selector])
    results["Notebook"]["Item"]["body"]["operationStatus"] = status
    with pytest.raises(deploy.BulkDeploymentError):
        deploy.validate_bulk_results(results, (item,))


@pytest.mark.parametrize("case", [
    "none", "list", "empty", "missing_type", "missing_item", "extra_item", "bad_body",
    "wrong_type", "wrong_name", "bad_id", "zero_id", "missing_status", "bad_http", "bool_http",
])
def test_malformed_or_incomplete_responses_are_fatal(tmp_path: Path, case: str) -> None:
    item = RepositoryItem(str(UUID(int=1)), "Item", "Notebook", tmp_path)
    results: object = _results([item.selector])
    if case == "none":
        results = None
    elif case == "list":
        results = []
    elif case == "empty":
        results = {}
    else:
        assert isinstance(results, dict)
        if case == "missing_type":
            results = {"Report": results["Notebook"]}
        elif case == "missing_item":
            results["Notebook"] = {}
        elif case == "extra_item":
            results["Notebook"]["Other"] = results["Notebook"]["Item"]
        elif case == "bad_body":
            results["Notebook"]["Item"]["body"] = []
        else:
            response = results["Notebook"]["Item"]
            body = response["body"]
            if case == "wrong_type":
                body["itemType"] = "Report"
            elif case == "wrong_name":
                body["itemDisplayName"] = "Other"
            elif case == "bad_id":
                body["itemId"] = "bad"
            elif case == "zero_id":
                body["itemId"] = str(UUID(int=0))
            elif case == "missing_status":
                del body["operationStatus"]
            elif case == "bad_http":
                response["status_code"] = 500
            elif case == "bool_http":
                response["status_code"] = True
    with pytest.raises(deploy.BulkDeploymentError):
        deploy.validate_bulk_results(results, (item,))


def test_duplicate_physical_ids_are_not_success(tmp_path: Path) -> None:
    items = tuple(RepositoryItem(str(UUID(int=i + 1)), name, "Notebook", tmp_path) for i, name in enumerate(("A", "B")))
    results = _results([item.selector for item in items])
    results["Notebook"]["B"]["body"]["itemId"] = results["Notebook"]["A"]["body"]["itemId"]
    with pytest.raises(deploy.BulkDeploymentError, match="repeats an itemId"):
        deploy.validate_bulk_results(results, items)


def test_empty_remainder_is_skipped_and_lakehouse_is_not_cleaned(tmp_path: Path) -> None:
    item = RepositoryItem(str(UUID(int=1)), "Lake", "Lakehouse", tmp_path)
    schedule = BulkDeploymentSchedule(
        tmp_path / "plan.yml", tmp_path, ((DeploymentGroup("Lake", item, ()),),), (), ("Lakehouse",),
    )
    instance = _workspace(environment="Test")
    with (
        mock.patch.object(deploy, "FabricWorkspace", return_value=instance) as workspace,
        mock.patch.object(deploy, "publish_all_items", return_value=_results([item.selector])) as publish,
        mock.patch.object(deploy, "unpublish_all_orphan_items") as cleanup,
        mock.patch.object(deploy, "append_feature_flag"),
    ):
        deploy.deploy_schedule(schedule, WORKSPACE_ID, "Test", mock.Mock(spec=TokenCredential))
    workspace.assert_called_once()
    publish.assert_called_once_with(instance, items_to_include=["Lake.Lakehouse"])
    cleanup.assert_not_called()


@pytest.mark.parametrize("raw", [
    "", " ", "[]", "{}", '["Notebook", 1]', '["Notebook", "Notebook"]',
    '[" Notebook"]', '["DeploymentPlan"]', '["Warehouse"]', '["DataBuildToolJob"]',
    '["NotAnItemType"]', "invalid",
])
def test_invalid_scope_is_explicit(raw: str) -> None:
    with pytest.raises(ValueError):
        deploy.parse_item_types(raw)


@pytest.mark.parametrize("item_types", [(), ("Warehouse",), ("DataBuildToolJob",), ("DeploymentPlan",), ("Unknown",)])
def test_ineligible_schedule_cannot_reach_a_workspace(
    schedule: BulkDeploymentSchedule, item_types: tuple[str, ...],
) -> None:
    with (
        mock.patch.object(deploy, "FabricWorkspace") as workspace,
        pytest.raises(ValueError),
    ):
        deploy.deploy_schedule(
            replace(schedule, item_types=item_types), WORKSPACE_ID, "Test", mock.Mock(spec=TokenCredential),
        )
    workspace.assert_not_called()


def test_empty_schedule_cannot_trigger_orphan_cleanup(schedule: BulkDeploymentSchedule) -> None:
    with (
        mock.patch.object(deploy, "FabricWorkspace") as workspace,
        mock.patch.object(deploy, "unpublish_all_orphan_items") as cleanup,
        pytest.raises(deploy.BulkDeploymentError, match="No selected items"),
    ):
        deploy.deploy_schedule(
            replace(schedule, batches=(), remaining_items=()), WORKSPACE_ID, "Test", mock.Mock(spec=TokenCredential),
        )
    workspace.assert_not_called()
    cleanup.assert_not_called()


@pytest.mark.parametrize("sdk_version", ["1.3.0", "1.4.0rc1", "1.4.0.dev1", "1.5.0", "2.0.0"])
def test_unsupported_sdk_version_stops_before_any_workspace(
    schedule: BulkDeploymentSchedule, sdk_version: str,
) -> None:
    with (
        mock.patch.object(deploy, "version", return_value=sdk_version),
        mock.patch.object(deploy, "FabricWorkspace") as workspace,
        pytest.raises(ValueError, match="Unsupported fabric-cicd"),
    ):
        deploy.deploy_schedule(schedule, WORKSPACE_ID, "Test", mock.Mock(spec=TokenCredential))
    workspace.assert_not_called()


@pytest.mark.parametrize("sdk_version", ["1.4.0", "1.4.7", "1.4.0.post1", "1.4.0+local"])
def test_released_versions_in_the_window_are_accepted(sdk_version: str) -> None:
    with mock.patch.object(deploy, "version", return_value=sdk_version):
        assert deploy.validate_sdk_version() == sdk_version


def test_preview_is_independent_and_does_not_authenticate(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(REPO_ROOT)
    monkeypatch.setenv("ITEM_TYPE_IN_SCOPE", json.dumps(SCOPE))
    for name in ("AZURE_TENANT_ID", "AZURE_CLIENT_ID", "AZURE_CLIENT_SECRET", "FABRIC_WORKSPACE_ID", "ENVIRONMENT"):
        monkeypatch.delenv(name, raising=False)
    with (
        mock.patch.dict(sys.modules, {"deployment_plan": None, "deploy_fabric_cicd_non_bulk_plan": None, "deploy_fabric_cicd_non_bulk": None}),
    ):
        importlib.reload(sys.modules["deployment_plan_bulk"])
        importlib.reload(deploy)
        with (
            mock.patch.object(deploy, "ClientSecretCredential") as credential,
            mock.patch.object(deploy, "FabricWorkspace") as workspace,
        ):
            deploy.main(["--plan", str(PLAN_PATH), "--dry-run"])
    summary = json.loads(capsys.readouterr().out)
    assert [len(batch) for batch in summary["batches"]] == [1, 2, 1]
    assert len(summary["remainingItems"]) == 5
    assert "DeploymentPlan" not in summary["cleanupItemTypes"]
    credential.assert_not_called()
    workspace.assert_not_called()


@pytest.mark.parametrize("case", ["missing_plan", "missing_scope", "outside_checkout", "invalid_scope", "missing_environment"])
def test_entry_point_invalid_configuration_fails_before_authentication(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path, case: str,
) -> None:
    monkeypatch.chdir(REPO_ROOT)
    monkeypatch.delenv("ENVIRONMENT", raising=False)
    monkeypatch.delenv("DEPLOYMENT_PLAN_PATH", raising=False)
    monkeypatch.setenv("ITEM_TYPE_IN_SCOPE", json.dumps(SCOPE))
    args = ["--plan", str(PLAN_PATH)]
    if case == "missing_plan":
        args = []
    elif case == "missing_scope":
        monkeypatch.delenv("ITEM_TYPE_IN_SCOPE", raising=False)
    elif case == "outside_checkout":
        args = ["--plan", str(tmp_path / "outside.yml")]
    elif case == "invalid_scope":
        monkeypatch.setenv("ITEM_TYPE_IN_SCOPE", '["Warehouse"]')
    with (
        mock.patch.object(deploy, "ClientSecretCredential") as credential,
        mock.patch.object(deploy, "FabricWorkspace") as workspace,
        pytest.raises(SystemExit) as error,
    ):
        deploy.main(args)
    assert error.value.code == 1
    assert "::error::" in capsys.readouterr().err
    credential.assert_not_called()
    workspace.assert_not_called()


def test_live_entry_point_preserves_environment_contract_and_surfaces_bulk_failure(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(REPO_ROOT)
    values = {
        "DEPLOYMENT_PLAN_PATH": str(PLAN_PATH), "ITEM_TYPE_IN_SCOPE": json.dumps(SCOPE),
        "REPOSITORY_DIRECTORY": str(REPO_ROOT / "data" / "fabric"), "ENVIRONMENT": "Prod",
        "FABRIC_WORKSPACE_ID": WORKSPACE_ID, "AZURE_TENANT_ID": str(UUID(int=1001)),
        "AZURE_CLIENT_ID": str(UUID(int=1002)), "AZURE_CLIENT_SECRET": "secret-for-unit-test",
    }
    for name, value in values.items():
        monkeypatch.setenv(name, value)
    with (
        mock.patch.object(deploy, "ClientSecretCredential") as credential,
        mock.patch.object(deploy, "deploy_schedule", side_effect=deploy.BulkDeploymentError("Item failed")) as execute,
        pytest.raises(SystemExit) as error,
    ):
        deploy.main([])
    assert error.value.code == 1
    credential.assert_called_once_with(
        tenant_id=values["AZURE_TENANT_ID"], client_id=values["AZURE_CLIENT_ID"],
        client_secret=values["AZURE_CLIENT_SECRET"],
    )
    assert execute.call_args.args[1:] == (WORKSPACE_ID, "Prod", credential.return_value)
    output = capsys.readouterr()
    assert "Item failed" in output.err
    assert values["AZURE_CLIENT_SECRET"] not in output.out + output.err
    assert "Bulk deployment completed" not in output.out


class OfflineFabric:
    """A strict HTTP-boundary fixture; publishing and replacement remain real."""

    def __init__(self, repository: Path) -> None:
        self.repository = repository
        self.metadata = {}
        for path in repository.rglob(".platform"):
            data = json.loads(path.read_text(encoding="utf-8"))
            metadata = data["metadata"]
            selector = f"{metadata['displayName']}.{metadata['type']}"
            self.metadata[selector] = data
        self.ids = {selector: str(uuid5(NAMESPACE_DNS, selector)) for selector in self.metadata}
        self.deployed: dict[str, dict[str, object]] = {}
        self.bulk_requests: list[dict] = []
        self.selections: list[list[str]] = []
        self.activations: list[str] = []
        self.deleted: list[str] = []
        self.standard_definition_requests = 0
        self.failure_selector: str | None = None
        self.failure_status: str | None = None
        self.omit_selector: str | None = None
        self.raise_on_import: int | None = None
        self.seed("DeploymentPlan", "DeploymentPlan")

    def seed(self, name: str, item_type: str) -> None:
        selector = f"{name}.{item_type}"
        self.ids.setdefault(selector, str(uuid5(NAMESPACE_DNS, selector)))
        self.deployed[selector] = {
            "id": self.ids[selector], "type": item_type, "displayName": name,
            "description": "", "folderId": "",
        }

    def invoke(self, method: str, url: str, body: object = None, **kwargs: object) -> dict:
        path = urlsplit(url).path
        root = f"/v1/workspaces/{WORKSPACE_ID}"
        result: dict = {"header": {}, "body": {}, "status_code": 200}
        if method == "GET" and path == root:
            result["body"] = {"capacityId": str(UUID(int=501)), "displayName": "Offline Target"}
        elif method == "GET" and path == f"{root}/items":
            result["body"] = {"value": list(self.deployed.values())}
        elif method == "GET" and path == f"{root}/folders":
            result["body"] = {"value": []}
        elif method == "GET" and path.startswith(f"{root}/lakehouses/"):
            item_id = path.rsplit("/", 1)[1]
            assert any(item["id"] == item_id and item["type"] == "Lakehouse" for item in self.deployed.values())
            result["body"] = {"properties": {"sqlEndpointProperties": {
                "id": str(UUID(int=601)), "connectionString": "offline.example.test",
                "provisioningStatus": "Success",
            }}}
        elif method == "GET" and path.endswith("/shortcuts"):
            result["body"] = {"value": []}
        elif method == "POST" and path == f"{root}/items/bulkImportDefinitions":
            assert isinstance(body, dict)
            assert body["options"] == {"allowPairingByName": True}
            self.bulk_requests.append(body)
            if self.raise_on_import == len(self.bulk_requests):
                raise RuntimeError("Offline API import failure")
            selections: list[str] = []
            details: list[dict] = []
            for part in body["definitionParts"]:
                if not part["path"].endswith("/.platform"):
                    continue
                assert part["payloadType"] == "InlineBase64"
                data = json.loads(base64.b64decode(part["payload"]).decode("utf-8"))
                metadata = data["metadata"]
                selector = f"{metadata['displayName']}.{metadata['type']}"
                assert metadata["type"] != "DeploymentPlan"
                assert data["config"]["logicalId"] == self.metadata[selector]["config"]["logicalId"]
                if selector == "Patterns_Data_Agent.DataAgent":
                    assert "Patterns_Ontology.Ontology" in self.deployed
                if selector == "Patterns_Report.Report":
                    assert "Patterns_Semantic_Model.SemanticModel" in self.deployed
                selections.append(selector)
                if selector == self.omit_selector:
                    continue
                status = self.failure_status if selector == self.failure_selector else "Succeeded"
                operation = "Update" if selector in self.deployed else "Create"
                if status == "Succeeded":
                    self.seed(metadata["displayName"], metadata["type"])
                details.append({
                    "itemType": metadata["type"], "itemDisplayName": metadata["displayName"],
                    "itemId": self.ids[selector], "operationStatus": status, "operationType": operation,
                })
            assert selections
            assert len(selections) == len(set(selections))
            self.selections.append(selections)
            result["body"] = {"importItemDefinitionsDetails": details}
        elif method == "POST" and (path == f"{root}/items" or path.endswith("/updateDefinition")):
            self.standard_definition_requests += 1
            raise AssertionError("Standard definition publishing is forbidden")
        elif method == "PATCH" and path == f"{root}/VariableLibraries/{self.ids['Patterns_Variables.VariableLibrary']}":
            assert isinstance(body, dict)
            self.activations.append(body["properties"]["activeValueSetName"])
        elif method == "DELETE" and path.startswith(f"{root}/items/"):
            item_id = path.rsplit("/", 1)[1]
            selector = next(key for key, value in self.deployed.items() if value["id"] == item_id)
            assert self.deployed[selector]["type"] not in deploy.CLEANUP_EXCLUDED_TYPES
            self.deleted.append(selector)
            del self.deployed[selector]
        else:
            raise AssertionError(f"Unexpected SDK request: {method} {url}")
        return result

    def content(self, selector: str, filename: str) -> str:
        prefix = next(
            part["path"].removesuffix("/.platform")
            for request in self.bulk_requests
            for part in request["definitionParts"]
            if part["path"].endswith("/.platform")
            and json.loads(base64.b64decode(part["payload"]).decode("utf-8"))["metadata"]["displayName"]
            == selector.rsplit(".", 1)[0]
        )
        return next(
            base64.b64decode(part["payload"]).decode("utf-8")
            for request in self.bulk_requests for part in request["definitionParts"]
            if part["path"] == f"{prefix}/{filename}"
        )


@pytest.fixture
def offline_fabric(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[OfflineFabric]:
    import fabric_cicd.constants as constants
    from fabric_cicd._common._fabric_endpoint import FabricEndpoint

    repository = tmp_path / "fabric"
    shutil.copytree(REPO_ROOT / "data" / "fabric", repository)
    fabric = OfflineFabric(repository)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(constants, "FEATURE_FLAG", set())
    monkeypatch.setattr(FabricEndpoint, "invoke", fabric.invoke)
    monkeypatch.setattr(sys, "excepthook", sys.__excepthook__)
    with mock.patch("requests.sessions.Session.request", side_effect=AssertionError("Real HTTP is forbidden")):
        yield fabric


def _credential() -> mock.Mock:
    credential = mock.Mock(spec=TokenCredential)
    credential.get_token.return_value = AccessToken("unit-test-token", int(time.time()) + 3600)
    return credential


def _offline_schedule(fabric: OfflineFabric) -> BulkDeploymentSchedule:
    return load_schedule(
        fabric.repository, fabric.repository / "DeploymentPlan.DeploymentPlan" / "plan.yml", SCOPE,
    )


@pytest.mark.parametrize("environment", ["Test", "Prod"])
@pytest.mark.parametrize("warm", [False, True], ids=["cold", "warm"])
def test_real_sdk_parameterized_transport_never_falls_back(
    offline_fabric: OfflineFabric, environment: str, warm: bool,
) -> None:
    fabric = offline_fabric
    if warm:
        for selector, data in fabric.metadata.items():
            fabric.seed(data["metadata"]["displayName"], data["metadata"]["type"])
    fabric.seed("DisposableOrphan", "Notebook")
    fabric.seed("KeepOrphanLake", "Lakehouse")
    fabric.seed("KeepOrphanOntology", "Ontology")
    before = {
        path.relative_to(fabric.repository): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in fabric.repository.rglob("*") if path.is_file()
    }
    deploy.deploy_schedule(_offline_schedule(fabric), WORKSPACE_ID, environment, _credential())
    assert (fabric.repository / "parameter.yml").is_file()
    assert len(fabric.bulk_requests) == 4
    assert [len(selection) for selection in fabric.selections] == [1, 2, 1, 5]
    assert [set(selection) for selection in fabric.selections[:3]] == [
        {"PatternsLakehouse.Lakehouse"},
        {"Patterns_Ontology.Ontology", "Patterns_Semantic_Model.SemanticModel"},
        {"Patterns_Data_Agent.DataAgent"},
    ]
    assert fabric.standard_definition_requests == 0
    assert fabric.activations == [environment]
    assert fabric.deleted == ["DisposableOrphan.Notebook"]
    assert {"KeepOrphanLake.Lakehouse", "KeepOrphanOntology.Ontology", "DeploymentPlan.DeploymentPlan"} <= fabric.deployed.keys()
    notebook = fabric.content("Import_Patterns_Data.Notebook", "notebook-content.py")
    model = fabric.content("Patterns_Semantic_Model.SemanticModel", "definition/expressions.tmdl")
    target_lakehouse = fabric.ids["PatternsLakehouse.Lakehouse"]
    for content in (notebook, model):
        assert WORKSPACE_ID in content
        assert target_lakehouse in content
        assert SOURCE_WORKSPACE_ID not in content
        assert SOURCE_LAKEHOUSE_ID not in content
    variables = json.loads(fabric.content("Patterns_Variables.VariableLibrary", "variables.json"))["variables"]
    assert next(variable["value"] for variable in variables if variable["name"] == "target_lakehouse_id") == target_lakehouse
    assert next(variable["value"] for variable in variables if variable["name"] == "target_workspace_id") == SOURCE_WORKSPACE_ID
    report = json.loads(fabric.content("Patterns_Report.Report", "definition.pbir"))
    source_report = json.loads(
        (fabric.repository / "Patterns_Report.Report" / "definition.pbir").read_text(encoding="utf-8")
    )
    assert report["datasetReference"] == source_report["datasetReference"]
    assert report["datasetReference"]["byPath"]["path"] == "../Patterns_Semantic_Model.SemanticModel"
    after = {
        path.relative_to(fabric.repository): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in fabric.repository.rglob("*") if path.is_file()
    }
    assert before == after


@pytest.mark.parametrize("selector", ["Patterns_Ontology.Ontology", "Patterns_Semantic_Model.SemanticModel"])
@pytest.mark.parametrize("status", ["Failed", "SucceededDespiteFailures", "Unknown"])
def test_real_sdk_combined_batch_failure_stops_dependencies(
    offline_fabric: OfflineFabric, selector: str, status: str,
) -> None:
    fabric = offline_fabric
    fabric.failure_selector, fabric.failure_status = selector, status
    with pytest.raises(deploy.BulkDeploymentError, match="did not succeed"):
        deploy.deploy_schedule(_offline_schedule(fabric), WORKSPACE_ID, "Test", _credential())
    assert len(fabric.bulk_requests) == 2
    assert fabric.standard_definition_requests == 0
    assert fabric.activations == []
    assert fabric.deleted == []


def test_real_sdk_missing_response_stops_dependencies(offline_fabric: OfflineFabric) -> None:
    fabric = offline_fabric
    fabric.omit_selector = "Patterns_Ontology.Ontology"
    with pytest.raises(deploy.BulkDeploymentError, match="do not match"):
        deploy.deploy_schedule(_offline_schedule(fabric), WORKSPACE_ID, "Test", _credential())
    assert len(fabric.bulk_requests) == 2
    assert fabric.deleted == []
    assert fabric.activations == []


def test_real_sdk_api_error_stops_dependencies(offline_fabric: OfflineFabric) -> None:
    fabric = offline_fabric
    fabric.raise_on_import = 2
    with pytest.raises(RuntimeError, match="Offline API"):
        deploy.deploy_schedule(_offline_schedule(fabric), WORKSPACE_ID, "Test", _credential())
    assert len(fabric.bulk_requests) == 2
    assert fabric.deleted == []
    assert fabric.activations == []


def test_unfiltered_items_rule_is_rejected_before_definition_writes(offline_fabric: OfflineFabric) -> None:
    fabric = offline_fabric
    path = fabric.repository / "parameter.yml"
    parameters = yaml.safe_load(path.read_text(encoding="utf-8"))
    del parameters["find_replace"][0]["item_type"]
    path.write_text(yaml.safe_dump(parameters), encoding="utf-8")
    with pytest.raises(deploy.BulkDeploymentError, match="unfiltered"):
        deploy.deploy_schedule(_offline_schedule(fabric), WORKSPACE_ID, "Test", _credential())
    assert fabric.bulk_requests == []
    assert fabric.standard_definition_requests == 0
    assert fabric.deleted == []


def test_invalid_dynamic_syntax_is_rejected_before_definition_writes(offline_fabric: OfflineFabric) -> None:
    from fabric_cicd._common._exceptions import ParameterFileError

    fabric = offline_fabric
    path = fabric.repository / "parameter.yml"
    parameters = yaml.safe_load(path.read_text(encoding="utf-8"))
    parameters["find_replace"][0]["replace_value"]["_ALL_"] = "$items.Lakehouse.PatternsLakehouse"
    path.write_text(yaml.safe_dump(parameters), encoding="utf-8")
    with pytest.raises(ParameterFileError):
        deploy.deploy_schedule(_offline_schedule(fabric), WORKSPACE_ID, "Test", _credential())
    assert fabric.bulk_requests == []
    assert fabric.standard_definition_requests == 0
    assert fabric.deleted == []


def test_unavailable_replacement_dependency_cannot_succeed(offline_fabric: OfflineFabric) -> None:
    from fabric_cicd._common._exceptions import InputError

    fabric = offline_fabric
    path = fabric.repository / "parameter.yml"
    path.write_text(
        path.read_text(encoding="utf-8").replace("$items.Lakehouse.PatternsLakehouse.$id", "$items.Lakehouse.Missing.$id"),
        encoding="utf-8",
    )
    with pytest.raises(InputError, match="excluded from this deployment"):
        deploy.deploy_schedule(_offline_schedule(fabric), WORKSPACE_ID, "Test", _credential())
    assert len(fabric.bulk_requests) == 1
    assert fabric.standard_definition_requests == 0
    assert fabric.deleted == []


@pytest.mark.parametrize("environment", ["test", "prod", "Missing", "Test "])
def test_value_set_environment_must_match_before_any_fabric_call(
    offline_fabric: OfflineFabric, environment: str,
) -> None:
    fabric = offline_fabric
    with (
        mock.patch.object(deploy, "FabricWorkspace") as workspace,
        pytest.raises(ValueError, match="default-value-set fallback is forbidden"),
    ):
        deploy.deploy_schedule(_offline_schedule(fabric), WORKSPACE_ID, environment, _credential())
    workspace.assert_not_called()
    assert fabric.bulk_requests == []
    assert fabric.activations == []


@pytest.mark.parametrize("fault", ["missing_settings", "bad_order", "missing_file", "wrong_name"])
def test_invalid_value_set_metadata_cannot_silently_skip_activation(
    offline_fabric: OfflineFabric, fault: str,
) -> None:
    fabric = offline_fabric
    library = fabric.repository / "Patterns_Variables.VariableLibrary"
    if fault == "missing_settings":
        (library / "settings.json").unlink()
    elif fault == "bad_order":
        (library / "settings.json").write_text('{"valueSetsOrder": "Test"}', encoding="utf-8")
    elif fault == "missing_file":
        (library / "valueSets" / "Test.json").unlink()
    elif fault == "wrong_name":
        (library / "valueSets" / "Test.json").write_text('{"name": "test"}', encoding="utf-8")
    with (
        mock.patch.object(deploy, "FabricWorkspace") as workspace,
        pytest.raises(ValueError),
    ):
        deploy.deploy_schedule(_offline_schedule(fabric), WORKSPACE_ID, "Test", _credential())
    workspace.assert_not_called()
    assert fabric.bulk_requests == []
    assert fabric.activations == []


def test_preview_checks_value_sets_when_environment_is_supplied(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(REPO_ROOT)
    monkeypatch.setenv("ITEM_TYPE_IN_SCOPE", json.dumps(SCOPE))
    monkeypatch.setenv("ENVIRONMENT", "test")
    with (
        mock.patch.object(deploy, "ClientSecretCredential") as credential,
        pytest.raises(SystemExit) as error,
    ):
        deploy.main(["--plan", str(PLAN_PATH), "--dry-run"])
    assert error.value.code == 1
    assert "default-value-set fallback is forbidden" in capsys.readouterr().err
    credential.assert_not_called()


@pytest.mark.parametrize("rule", [
    {
        "find_value": '"Test",', "replace_value": {"_ALL_": " "},
        "item_type": "VariableLibrary", "file_path": "**/settings.json",
    },
    {
        "find_key": "$.valueSetsOrder", "replace_value": {"_ALL_": '["Prod"]'},
        "item_type": "VariableLibrary", "file_path": "**/settings.json",
    },
    {
        "find_value": '"name": "Test"', "replace_value": {"_ALL_": '"name": "Other"'},
        "item_type": "VariableLibrary", "file_path": "**/valueSets/Test.json",
    },
])
def test_sdk_rules_cannot_bypass_activation_metadata_preflight(
    offline_fabric: OfflineFabric, rule: dict[str, object],
) -> None:
    fabric = offline_fabric
    path = fabric.repository / "parameter.yml"
    parameters = yaml.safe_load(path.read_text(encoding="utf-8"))
    kind = "key_value_replace" if "find_key" in rule else "find_replace"
    parameters.setdefault(kind, []).append(rule)
    path.write_text(yaml.safe_dump(parameters), encoding="utf-8")
    with pytest.raises(deploy.BulkDeploymentError, match="control metadata"):
        deploy.deploy_schedule(_offline_schedule(fabric), WORKSPACE_ID, "Test", _credential())
    assert fabric.bulk_requests == []
    assert fabric.activations == []
    assert fabric.deleted == []
    assert fabric.standard_definition_requests == 0


@pytest.mark.parametrize("replacement_environment", ["_ALL_", "Prod"])
def test_key_value_normalization_cannot_create_an_unguarded_metadata_match(
    offline_fabric: OfflineFabric, replacement_environment: str,
) -> None:
    fabric = offline_fabric
    path = fabric.repository / "parameter.yml"
    parameters = yaml.safe_load(path.read_text(encoding="utf-8"))
    parameters["key_value_replace"] = [{
        "find_key": "$.nonexistent",
        "replace_value": {replacement_environment: "unused"},
        "item_type": "VariableLibrary",
        "file_path": "**/settings.json",
    }]
    parameters["find_replace"].append({
        "find_value": '"valueSetsOrder": ["Test", "Prod"]',
        "replace_value": {"_ALL_": '"valueSetsOrder": ["Prod"]'},
        "item_type": "VariableLibrary",
        "file_path": "**/settings.json",
    })
    path.write_text(yaml.safe_dump(parameters), encoding="utf-8")
    with pytest.raises(deploy.BulkDeploymentError, match="control metadata"):
        deploy.deploy_schedule(_offline_schedule(fabric), WORKSPACE_ID, "Test", _credential())
    assert fabric.bulk_requests == []
    assert fabric.activations == []
    assert fabric.deleted == []
    assert fabric.standard_definition_requests == 0


@pytest.mark.parametrize("rule", [
    {
        "find_value": '"Test",', "replace_value": {"Prod": " "},
        "item_type": "VariableLibrary", "file_path": "**/settings.json",
    },
    {
        "find_value": '"Test",', "replace_value": {"_ALL_": " "},
        "item_type": "VariableLibrary", "file_path": "**/variables.json",
    },
    {
        "find_key": "$.variables[?(@.name=='target_message')].value",
        "replace_value": {"_ALL_": "Message from SDK parameters"},
        "item_type": "VariableLibrary", "file_path": "**/variables.json",
    },
])
def test_inactive_or_nonmatching_rules_do_not_block_bulk(
    offline_fabric: OfflineFabric, rule: dict[str, object],
) -> None:
    fabric = offline_fabric
    path = fabric.repository / "parameter.yml"
    parameters = yaml.safe_load(path.read_text(encoding="utf-8"))
    kind = "key_value_replace" if "find_key" in rule else "find_replace"
    parameters.setdefault(kind, []).append(rule)
    path.write_text(yaml.safe_dump(parameters), encoding="utf-8")
    deploy.deploy_schedule(_offline_schedule(fabric), WORKSPACE_ID, "Test", _credential())
    assert len(fabric.bulk_requests) == 4
    assert fabric.activations == ["Test"]
    assert fabric.standard_definition_requests == 0
    if "find_key" in rule:
        variables = json.loads(fabric.content("Patterns_Variables.VariableLibrary", "variables.json"))["variables"]
        assert next(variable["value"] for variable in variables if variable["name"] == "target_message") == "Message from SDK parameters"


def _workflow(name: str) -> dict:
    return yaml.load(
        (REPO_ROOT / ".github" / "workflows" / name).read_text(encoding="utf-8"), Loader=yaml.BaseLoader,
    )


@pytest.mark.parametrize("stage,branch", [("test", "test"), ("prod", "main")])
def test_bulk_workflow_plan_routing_path_filters_and_etl(stage: str, branch: str) -> None:
    workflow = _workflow(f"deploy-{stage}-fabric-cicd-bulk.yml")
    job = workflow["jobs"]["deploy-fabric-cicd-bulk"]
    assert workflow["on"]["push"]["branches"] == [branch]
    assert job["if"] == "vars.DEPLOY_METHOD == 'fabric-cicd-bulk'"
    assert job["uses"] == "./.github/workflows/reusable-deploy-fabric-cicd-bulk.yml"
    assert job["with"]["environment"] == stage.capitalize()
    assert job["with"]["deployment_plan_path"] == "${{ vars.DEPLOYMENT_PLAN_PATH }}"
    assert set(json.loads(job["with"]["item_type_in_scope"])) == set(SCOPE)
    assert "fail_if_bulk_used" not in job["with"]
    assert job["secrets"] == "inherit"
    assert workflow["permissions"] == {"contents": "read"}
    assert {"data/fabric/**", "deployment-plans/**", "scripts/deploy_fabric_cicd_bulk.py", "scripts/deployment_plan_bulk.py", "requirements-dev.txt"} <= set(workflow["on"]["push"]["paths"])
    assert "scripts/deployment_plan.py" not in workflow["on"]["push"]["paths"]
    etl = _workflow(f"etl-{stage}.yml")
    assert etl["on"]["workflow_run"]["workflows"].count(workflow["name"]) == 1
    assert "github.event.workflow_run.conclusion == 'success'" in etl["jobs"]["run-etl"]["if"]


def test_bulk_preview_precedes_secrets_and_all_sdk_ranges_match() -> None:
    workflow = _workflow("reusable-deploy-fabric-cicd-bulk.yml")
    inputs = workflow["on"]["workflow_call"]["inputs"]
    assert inputs["deployment_plan_path"]["required"] == "true"
    assert inputs["item_type_in_scope"]["required"] == "true"
    assert "fail_if_bulk_used" not in inputs
    job = workflow["jobs"]["deploy"]
    assert job["environment"] == "${{ inputs.environment }}"
    assert int(job["timeout-minutes"]) > 0
    assert job["env"]["DEPLOYMENT_PLAN_PATH"] == "${{ inputs.deployment_plan_path }}"
    assert "AZURE_CLIENT_SECRET" not in job["env"]
    assert "FAIL_IF_BULK_USED" not in job["env"]
    steps = job["steps"]
    preview = next(i for i, step in enumerate(steps) if "--dry-run" in step.get("run", ""))
    execute = next(i for i, step in enumerate(steps) if "AZURE_CLIENT_SECRET" in step.get("env", {}))
    assert preview < execute
    assert all("AZURE_CLIENT_SECRET" not in step.get("env", {}) for step in steps[:execute])
    assert steps[execute]["run"] == "python scripts/deploy_fabric_cicd_bulk.py"
    for step in steps:
        if "uses" in step:
            sha = step["uses"].split("@")[1]
            assert len(sha) == 40
            int(sha, 16)
        if "python-version" in step.get("with", {}):
            assert step["with"]["python-version"] == "3.12"
    for name in ("reusable-deploy-fabric-cicd.yml", "reusable-deploy-fabric-cicd-bulk.yml", "reusable-deploy-fabric-cicd-plan.yml"):
        install = next(step["run"] for step in _workflow(name)["jobs"]["deploy"]["steps"] if "pip install" in step.get("run", ""))
        assert '"fabric-cicd>=1.4.0,<1.5.0"' in install
    assert "fabric-cicd>=1.4.0,<1.5.0" in (REPO_ROOT / "requirements-dev.txt").read_text(encoding="utf-8")
