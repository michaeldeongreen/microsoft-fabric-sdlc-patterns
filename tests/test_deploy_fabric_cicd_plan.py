"""Exercise scheduling and workflow wiring without making deployment calls."""

from __future__ import annotations

import base64
import json
import time
from pathlib import Path
from unittest import mock
from urllib.parse import urlsplit
from uuid import UUID

import pytest
import yaml
from azure.core.credentials import AccessToken, TokenCredential

import deploy_fabric_cicd_plan as deploy
from deployment_plan import PLAN_SCHEMA, DeploymentGroup, DeploymentSchedule, RepositoryItem, load_schedule

REPO_ROOT = Path(__file__).resolve().parents[1]
PLAN_PATH = REPO_ROOT / "data" / "fabric" / "DeploymentPlan.DeploymentPlan" / "plan.yml"
WORKSPACE_ID = "11111111-1111-1111-1111-111111111111"


@pytest.fixture
def schedule() -> DeploymentSchedule:
    return load_schedule(REPO_ROOT / "data" / "fabric", PLAN_PATH)


def test_exact_item_selection_fresh_state_and_single_cleanup(
    schedule: DeploymentSchedule,
) -> None:
    credential = mock.Mock(spec=TokenCredential)
    instances: list[mock.Mock] = []
    published: list[str] = []

    def make_workspace(**kwargs: object) -> mock.Mock:
        workspace = mock.Mock()
        workspace.config = kwargs
        workspace.items_visible_at_creation = tuple(published)
        instances.append(workspace)
        return workspace

    def publish(workspace: mock.Mock, *, items_to_include: list[str]) -> None:
        if "Patterns_Data_Agent.DataAgent" in items_to_include:
            assert "Patterns_Ontology.Ontology" in workspace.items_visible_at_creation
        if "Patterns_Semantic_Model.SemanticModel" in items_to_include:
            assert "PatternsLakehouse.Lakehouse" in workspace.items_visible_at_creation
        if "Patterns_Report.Report" in items_to_include:
            assert "Patterns_Semantic_Model.SemanticModel" in workspace.items_visible_at_creation
        published.extend(items_to_include)

    with (
        mock.patch.object(deploy, "FabricWorkspace", side_effect=make_workspace),
        mock.patch.object(deploy, "publish_all_items", side_effect=publish) as publish_mock,
        mock.patch.object(deploy, "unpublish_all_orphan_items") as cleanup,
        mock.patch.object(deploy, "append_feature_flag") as enable,
        mock.patch.object(deploy, "remove_feature_flag") as disable,
    ):
        deploy.deploy_schedule(schedule, WORKSPACE_ID, "Test", credential)

    assert publish_mock.call_count == 5
    assert len(instances) == 6
    assert len(published) == len(set(published)) == 9
    assert [call.kwargs["items_to_include"] for call in publish_mock.call_args_list[:4]] == [
        [group.item.selector] for group in schedule.groups
    ]
    cleanup.assert_called_once_with(instances[-1])
    assert instances[-1].config["item_type_in_scope"] == [
        "DataAgent", "Notebook", "Report", "SemanticModel", "VariableLibrary"
    ]
    for instance in instances:
        assert instance.config["repository_directory"] == str(schedule.repository_directory)
        assert instance.config["workspace_id"] == WORKSPACE_ID
        assert instance.config["environment"] == "Test"
        assert instance.config["token_credential"] is credential
    assert enable.call_args_list == [
        mock.call("enable_experimental_features"), mock.call("enable_items_to_include")
    ]
    disable.assert_called_once_with("enable_bulk_publish")


@pytest.mark.parametrize("failure_call", [1, 4, 5])
def test_publish_failure_stops_remaining_work_and_cleanup(
    schedule: DeploymentSchedule, failure_call: int,
) -> None:
    calls = 0

    def publish(*args: object, **kwargs: object) -> None:
        nonlocal calls
        calls += 1
        if calls == failure_call:
            raise RuntimeError("deployment failed")

    with (
        mock.patch.object(deploy, "FabricWorkspace"),
        mock.patch.object(deploy, "publish_all_items", side_effect=publish),
        mock.patch.object(deploy, "unpublish_all_orphan_items") as cleanup,
        mock.patch.object(deploy, "append_feature_flag"),
        mock.patch.object(deploy, "remove_feature_flag"),
        pytest.raises(RuntimeError, match="deployment failed"),
    ):
        deploy.deploy_schedule(schedule, WORKSPACE_ID, "Test", mock.Mock(spec=TokenCredential))
    assert calls == failure_call
    cleanup.assert_not_called()


def test_empty_remainder_is_not_an_unrestricted_publish(tmp_path: Path) -> None:
    item = RepositoryItem(str(UUID(int=1)), "Lake", "Lakehouse", tmp_path)
    schedule = DeploymentSchedule(
        tmp_path / "plan.yml", tmp_path,
        (DeploymentGroup("Lake", item, ()),), (), ("Lakehouse",),
    )
    with (
        mock.patch.object(deploy, "FabricWorkspace") as workspace,
        mock.patch.object(deploy, "publish_all_items") as publish,
        mock.patch.object(deploy, "unpublish_all_orphan_items") as cleanup,
        mock.patch.object(deploy, "append_feature_flag"),
        mock.patch.object(deploy, "remove_feature_flag"),
    ):
        deploy.deploy_schedule(schedule, WORKSPACE_ID, "Test", mock.Mock(spec=TokenCredential))
    workspace.assert_called_once()
    publish.assert_called_once_with(workspace.return_value, items_to_include=["Lake.Lakehouse"])
    cleanup.assert_not_called()


def test_500_items_use_three_planned_calls_and_one_remainder(tmp_path: Path) -> None:
    items = tuple(
        RepositoryItem(str(UUID(int=i + 1)), f"Item{i}", "Notebook", tmp_path / str(i))
        for i in range(500)
    )
    schedule = DeploymentSchedule(
        tmp_path / "plan.yml", tmp_path,
        tuple(DeploymentGroup(f"Group{i}", item, ()) for i, item in enumerate(items[:3])),
        items[3:], ("Notebook",),
    )
    with (
        mock.patch.object(deploy, "FabricWorkspace"),
        mock.patch.object(deploy, "publish_all_items") as publish,
        mock.patch.object(deploy, "unpublish_all_orphan_items"),
        mock.patch.object(deploy, "append_feature_flag"),
        mock.patch.object(deploy, "remove_feature_flag"),
    ):
        deploy.deploy_schedule(schedule, WORKSPACE_ID, "Test", mock.Mock(spec=TokenCredential))
    assert [len(call.kwargs["items_to_include"]) for call in publish.call_args_list] == [1, 1, 1, 497]


def test_real_sdk_rewrites_physical_ids_on_clean_and_existing_targets(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Use the installed SDK's real publishing/parameterization, mocking only HTTP."""
    import fabric_cicd.constants as constants
    from fabric_cicd._common._fabric_endpoint import FabricEndpoint

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(constants, "FEATURE_FLAG", set())
    logical_ids = {
        "Lakehouse": str(UUID(int=1)), "Notebook": str(UUID(int=2)),
        "DeploymentPlan": str(UUID(int=3)), "VariableLibrary": str(UUID(int=4)),
    }
    target_ids = {
        "Lakehouse": str(UUID(int=101)), "Notebook": str(UUID(int=102)),
        "DeploymentPlan": str(UUID(int=103)), "VariableLibrary": str(UUID(int=104)),
    }
    source_lakehouse, source_workspace = str(UUID(int=901)), str(UUID(int=902))
    for item_type, name in (
        ("Lakehouse", "Lake"), ("Notebook", "Notebook"), ("DeploymentPlan", "Control"),
        ("VariableLibrary", "Variables"),
    ):
        directory = tmp_path / f"{name}.{item_type}"
        directory.mkdir()
        (directory / ".platform").write_text(json.dumps({
            "metadata": {"type": item_type, "displayName": name},
            "config": {"logicalId": logical_ids[item_type], "version": "2.0"},
        }), encoding="utf-8")
    (tmp_path / "Lake.Lakehouse" / "lakehouse.metadata.json").write_text(
        '{"defaultSchema":"dbo"}', encoding="utf-8"
    )
    notebook_path = tmp_path / "Notebook.Notebook" / "notebook-content.py"
    notebook_path.write_text(
        f'# Fabric notebook source\nlakehouse = "{source_lakehouse}"\n'
        f'workspace = "{source_workspace}"\n',
        encoding="utf-8",
    )
    library = tmp_path / "Variables.VariableLibrary"
    (library / "valueSets").mkdir()
    (library / "variables.json").write_text(json.dumps({
        "variables": [{"name": "target_lakehouse_id", "type": "Guid", "value": source_lakehouse}],
    }), encoding="utf-8")
    (library / "settings.json").write_text('{"valueSetsOrder":["Test"]}', encoding="utf-8")
    (library / "valueSets" / "Test.json").write_text(
        '{"name":"Test","variableOverrides":[]}', encoding="utf-8"
    )
    (tmp_path / "parameter.yml").write_text(yaml.safe_dump({
        "find_replace": [
            {"find_value": source_lakehouse, "replace_value": {"_ALL_": "$items.Lakehouse.Lake.$id"}, "item_type": "Notebook"},
            {"find_value": source_workspace, "replace_value": {"_ALL_": "$workspace.$id"}, "item_type": "Notebook"},
            {"find_value": source_lakehouse, "replace_value": {"_ALL_": "$items.Lakehouse.Lake.$id"}, "item_type": "VariableLibrary"},
        ],
    }), encoding="utf-8")
    plan_path = tmp_path / "plan.yml"
    plan_path.write_text(yaml.safe_dump({
        "$schema": PLAN_SCHEMA, "version": "1.0.0",
        "groups": [{"name": "Lake", "logicalId": logical_ids["Lakehouse"]}],
    }), encoding="utf-8")
    schedule = load_schedule(tmp_path, plan_path)
    folder_id = str(UUID(int=701))
    deployed: dict[str, dict[str, object]] = {
        "DeploymentPlan": {
            "id": target_ids["DeploymentPlan"], "type": "DeploymentPlan",
            "displayName": "Control", "description": "", "folderId": folder_id,
        }
    }
    notebook_payloads: list[dict] = []
    library_payloads: list[dict] = []
    activated_value_sets: list[str] = []
    created: list[str] = []

    def invoke(method: str, url: str, body: object = None, **kwargs: object) -> dict:
        path = urlsplit(url).path
        workspace_path = f"/v1/workspaces/{WORKSPACE_ID}"
        result: dict = {"header": {}, "body": {}, "status_code": 200}
        if method == "GET" and path == workspace_path:
            result["body"] = {"capacityId": str(UUID(int=501))}
        elif method == "GET" and path == f"{workspace_path}/items":
            result["body"] = {"value": list(deployed.values())}
        elif method == "GET" and path == f"{workspace_path}/folders":
            result["body"] = {"value": [
                {"id": folder_id, "displayName": "Keep", "parentFolderId": None}
            ]}
        elif method == "GET" and path == f"{workspace_path}/lakehouses/{target_ids['Lakehouse']}":
            result["body"] = {"properties": {"sqlEndpointProperties": {
                "id": str(UUID(int=601)), "connectionString": "example.test",
                "provisioningStatus": "Success",
            }}}
        elif method == "GET" and path.endswith("/shortcuts"):
            result["body"] = {"value": []}
        elif method == "POST" and path == f"{workspace_path}/items":
            assert isinstance(body, dict)
            item_type = body["type"]
            deployed[item_type] = {
                "id": target_ids[item_type], "type": item_type,
                "displayName": body["displayName"], "description": "", "folderId": "",
            }
            created.append(item_type)
            result["body"] = {"id": target_ids[item_type]}
            if item_type == "Notebook":
                notebook_payloads.append(body)
            if item_type == "VariableLibrary":
                library_payloads.append(body)
        elif method == "POST" and path == f"{workspace_path}/items/{target_ids['Notebook']}/updateDefinition":
            assert isinstance(body, dict)
            notebook_payloads.append(body)
        elif method == "PATCH" and path == f"{workspace_path}/items/{target_ids['Lakehouse']}":
            assert isinstance(body, dict)
        elif method == "POST" and path == f"{workspace_path}/items/{target_ids['VariableLibrary']}/updateDefinition":
            assert isinstance(body, dict)
            library_payloads.append(body)
        elif method == "PATCH" and path == f"{workspace_path}/VariableLibraries/{target_ids['VariableLibrary']}":
            assert isinstance(body, dict)
            activated_value_sets.append(body["properties"]["activeValueSetName"])
        else:
            pytest.fail(f"Unexpected SDK request: {method} {url}")
        return result

    credential = mock.Mock(spec=TokenCredential)
    credential.get_token.return_value = AccessToken("unit-test-token", int(time.time()) + 3600)
    monkeypatch.setattr(FabricEndpoint, "invoke", staticmethod(invoke))
    with mock.patch("requests.sessions.Session.request", side_effect=AssertionError("Real HTTP is forbidden")):
        deploy.deploy_schedule(schedule, WORKSPACE_ID, "Test", credential)
        deploy.deploy_schedule(schedule, WORKSPACE_ID, "Test", credential)

    assert created[0] == "Lakehouse"
    assert sorted(created) == ["Lakehouse", "Notebook", "VariableLibrary"]
    assert deployed["DeploymentPlan"]["folderId"] == folder_id
    assert len(notebook_payloads) == 2
    for payload in notebook_payloads:
        part = next(p for p in payload["definition"]["parts"] if p["path"] == "notebook-content.py")
        content = base64.b64decode(part["payload"]).decode("utf-8")
        assert target_ids["Lakehouse"] in content
        assert WORKSPACE_ID in content
        assert source_lakehouse not in content
        assert source_workspace not in content
    assert source_lakehouse in notebook_path.read_text(encoding="utf-8")
    assert activated_value_sets == ["Test", "Test"]
    assert len(library_payloads) == 2
    for payload in library_payloads:
        part = next(p for p in payload["definition"]["parts"] if p["path"] == "variables.json")
        variables = json.loads(base64.b64decode(part["payload"]).decode("utf-8"))
        assert variables["variables"][0]["value"] == target_ids["Lakehouse"]


@pytest.mark.parametrize("value", ['[]', '{}', '["Notebook", 1]', '["Notebook", "Notebook"]', 'invalid'])
def test_invalid_scope_is_explicit(value: str) -> None:
    with pytest.raises(ValueError):
        deploy.parse_item_types(value)


def test_unknown_type_fails_before_any_fabric_call(schedule: DeploymentSchedule) -> None:
    bad = DeploymentSchedule(
        schedule.plan_path, schedule.repository_directory, schedule.groups,
        schedule.remaining_items, ("NotAnItemType",),
    )
    with mock.patch.object(deploy, "FabricWorkspace") as workspace:
        with pytest.raises(ValueError, match="does not support"):
            deploy.deploy_schedule(bad, WORKSPACE_ID, "Test", mock.Mock(spec=TokenCredential))
    workspace.assert_not_called()


def test_dry_run_has_no_credential_or_network_requirement(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(REPO_ROOT)
    for name in (
        "AZURE_TENANT_ID", "AZURE_CLIENT_ID", "AZURE_CLIENT_SECRET",
        "FABRIC_WORKSPACE_ID", "ENVIRONMENT", "ITEM_TYPE_IN_SCOPE",
    ):
        monkeypatch.delenv(name, raising=False)
    with (
        mock.patch.object(deploy, "ClientSecretCredential") as credential,
        mock.patch.object(deploy, "FabricWorkspace") as workspace,
    ):
        deploy.main(["--plan", str(PLAN_PATH), "--dry-run"])
    summary = json.loads(capsys.readouterr().out)
    assert len(summary["groups"]) == 4
    assert len(summary["remainingItems"]) == 5
    credential.assert_not_called()
    workspace.assert_not_called()


def test_invalid_plan_stops_before_authentication(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(REPO_ROOT)
    with (
        mock.patch.object(deploy, "ClientSecretCredential") as credential,
        pytest.raises(SystemExit) as error,
    ):
        deploy.main(["--plan", "missing-plan.yml"])
    assert error.value.code == 1
    assert "::error::" in capsys.readouterr().err
    credential.assert_not_called()


def test_missing_plan_configuration_is_not_a_fallback(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.delenv("DEPLOYMENT_PLAN_PATH", raising=False)
    monkeypatch.chdir(REPO_ROOT)
    with pytest.raises(SystemExit) as error:
        deploy.main(["--dry-run"])
    assert error.value.code == 1
    assert "DEPLOYMENT_PLAN_PATH" in capsys.readouterr().err


def test_live_entry_point_uses_environment_configuration_without_logging_secrets(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(REPO_ROOT)
    values = {
        "DEPLOYMENT_PLAN_PATH": str(PLAN_PATH),
        "REPOSITORY_DIRECTORY": str(REPO_ROOT / "data" / "fabric"),
        "ENVIRONMENT": "Test",
        "FABRIC_WORKSPACE_ID": WORKSPACE_ID,
        "AZURE_TENANT_ID": str(UUID(int=1001)),
        "AZURE_CLIENT_ID": str(UUID(int=1002)),
        "AZURE_CLIENT_SECRET": "secret-for-unit-test",
    }
    for name, value in values.items():
        monkeypatch.setenv(name, value)
    monkeypatch.delenv("ITEM_TYPE_IN_SCOPE", raising=False)
    with (
        mock.patch.object(deploy, "ClientSecretCredential") as credential,
        mock.patch.object(deploy, "deploy_schedule") as execute,
    ):
        deploy.main([])
    credential.assert_called_once_with(
        tenant_id=values["AZURE_TENANT_ID"],
        client_id=values["AZURE_CLIENT_ID"],
        client_secret=values["AZURE_CLIENT_SECRET"],
    )
    assert execute.call_args.args[0].plan_path == PLAN_PATH
    assert execute.call_args.args[1:] == (WORKSPACE_ID, "Test", credential.return_value)
    output = capsys.readouterr()
    assert values["AZURE_CLIENT_SECRET"] not in output.out + output.err


def test_live_entry_point_missing_configuration_stops_before_authentication(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(REPO_ROOT)
    monkeypatch.delenv("ENVIRONMENT", raising=False)
    monkeypatch.delenv("ITEM_TYPE_IN_SCOPE", raising=False)
    with (
        mock.patch.object(deploy, "ClientSecretCredential") as credential,
        pytest.raises(SystemExit) as error,
    ):
        deploy.main(["--plan", str(PLAN_PATH)])
    assert error.value.code == 1
    assert "ENVIRONMENT" in capsys.readouterr().err
    credential.assert_not_called()


def _workflow(name: str) -> dict:
    # BaseLoader preserves GitHub's "on" key instead of YAML 1.1 boolean coercion.
    return yaml.load(
        (REPO_ROOT / ".github" / "workflows" / name).read_text(encoding="utf-8"),
        Loader=yaml.BaseLoader,
    )


@pytest.mark.parametrize("environment,branch", [("Test", "test"), ("Prod", "main")])
def test_plan_workflow_wiring_and_etl_registration(environment: str, branch: str) -> None:
    stage = environment.lower()
    workflow = _workflow(f"deploy-{stage}-fabric-cicd-plan.yml")
    job = workflow["jobs"]["deploy-fabric-cicd-plan"]
    assert workflow["on"]["push"]["branches"] == [branch]
    assert "vars.DEPLOY_METHOD == 'fabric-cicd-plan'" in job["if"]
    assert job["uses"] == "./.github/workflows/reusable-deploy-fabric-cicd-plan.yml"
    assert job["with"]["environment"] == environment
    assert job["with"]["deployment_plan_path"] == "${{ vars.DEPLOYMENT_PLAN_PATH }}"
    assert len(json.loads(job["with"]["item_type_in_scope"])) == 7
    assert job["secrets"] == "inherit"
    assert workflow["permissions"] == {"contents": "read"}
    assert workflow["concurrency"]["cancel-in-progress"] == "false"
    etl = _workflow(f"etl-{stage}.yml")
    listeners = etl["on"]["workflow_run"]["workflows"]
    assert listeners.count(workflow["name"]) == 1
    assert len(listeners) == len(set(listeners)) == 4
    assert "github.event.workflow_run.conclusion == 'success'" in etl["jobs"]["run-etl"]["if"]
    assert etl["jobs"]["run-etl"]["uses"] == "./.github/workflows/reusable-fabric-etl.yml"


def test_test_manual_deployment_is_restricted_to_test_branch() -> None:
    workflow = _workflow("deploy-test-fabric-cicd-plan.yml")
    assert "workflow_dispatch" in workflow["on"]
    assert "github.ref == 'refs/heads/test'" in workflow["jobs"]["deploy-fabric-cicd-plan"]["if"]
    assert "workflow_dispatch" not in _workflow("deploy-prod-fabric-cicd-plan.yml")["on"]


def test_reusable_workflow_validates_before_loading_azure_secrets() -> None:
    workflow = _workflow("reusable-deploy-fabric-cicd-plan.yml")
    job = workflow["jobs"]["deploy"]
    assert job["environment"] == "${{ inputs.environment }}"
    assert int(job["timeout-minutes"]) > 0
    assert job["env"]["DEPLOYMENT_PLAN_PATH"] == "${{ inputs.deployment_plan_path }}"
    steps = job["steps"]
    preview = next(i for i, step in enumerate(steps) if "--dry-run" in step.get("run", ""))
    execute = next(i for i, step in enumerate(steps) if "AZURE_CLIENT_SECRET" in step.get("env", {}))
    assert preview < execute
    assert all("AZURE_CLIENT_SECRET" not in step.get("env", {}) for step in steps[:execute])
    assert steps[execute]["run"] == "python scripts/deploy_fabric_cicd_plan.py"
    for step in steps:
        if "uses" in step:
            sha = step["uses"].split("@")[1]
            assert len(sha) == 40
            int(sha, 16)


@pytest.mark.parametrize("stage", ["test", "prod"])
@pytest.mark.parametrize("method", ["", "fabric-cicd", "bulk", "fabric-cicd-bulk", "fabric-cicd-plan"])
def test_deployment_method_selects_one_route(stage: str, method: str) -> None:
    suffixes = ("", "-bulk", "-fabric-cicd-bulk", "-fabric-cicd-plan")
    selected: list[str] = []
    for suffix in suffixes:
        workflow = _workflow(f"deploy-{stage}{suffix}.yml")
        job = next(iter(workflow["jobs"].values()))
        condition = job["if"].split(" && ")[0]
        alternatives = condition.split(" || ")
        if any(alternative == f"vars.DEPLOY_METHOD == '{method}'" for alternative in alternatives):
            selected.append(suffix)
    expected = {
        "": "", "fabric-cicd": "", "bulk": "-bulk",
        "fabric-cicd-bulk": "-fabric-cicd-bulk", "fabric-cicd-plan": "-fabric-cicd-plan",
    }
    assert selected == [expected[method]]
