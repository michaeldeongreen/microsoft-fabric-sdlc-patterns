"""Contracts for the shared ETL workflow and its Semantic Model readiness gate."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]


def workflow(name: str) -> dict:
    return yaml.load(
        (REPO_ROOT / ".github" / "workflows" / name).read_text(encoding="utf-8"),
        Loader=yaml.BaseLoader,
    )


def test_pipeline_run_label_is_optional_for_notebook_only_callers() -> None:
    inputs = workflow("reusable-fabric-etl.yml")["on"]["workflow_call"]["inputs"]
    assert inputs["run_label"]["type"] == "string"
    assert inputs["run_label"]["required"] == "false"
    assert inputs["run_label"]["default"] == ""
    assert "semantic_model_name" not in inputs
    assert inputs["item_type"]["default"] == "Notebook"
    assert inputs["job_type"]["default"] == "RunNotebook"


def test_native_pipeline_is_the_only_refresh_owner() -> None:
    job = workflow("reusable-fabric-etl.yml")["jobs"]["run-etl"]
    steps = job["steps"]
    etl_index = next(i for i, step in enumerate(steps) if step.get("run") == "python scripts/run_fabric_etl.py")
    assert sum(step.get("run") == "python scripts/run_fabric_etl.py" for step in steps) == 1
    assert not any("refresh_semantic_model" in step.get("run", "") for step in steps)
    assert "continue-on-error" not in job
    assert "continue-on-error" not in steps[etl_index]
    assert steps[etl_index]["timeout-minutes"] == "60"
    assert int(job["timeout-minutes"]) == 60
    assert not (REPO_ROOT / "scripts" / "refresh_semantic_model.py").exists()


def test_pipeline_run_uses_environment_secrets_without_inline_input_interpolation() -> None:
    reusable = workflow("reusable-fabric-etl.yml")
    job = reusable["jobs"]["run-etl"]
    assert reusable["permissions"] == {"contents": "read"}
    assert job["environment"] == "${{ inputs.environment }}"
    runner = next(step for step in job["steps"] if step.get("run") == "python scripts/run_fabric_etl.py")
    install = next(step["run"] for step in job["steps"] if "pip install" in step.get("run", ""))
    assert '"azure-identity>=1.15"' in install
    assert '"requests>=2.31"' in install
    for name in ("AZURE_TENANT_ID", "AZURE_CLIENT_ID", "AZURE_CLIENT_SECRET", "FABRIC_WORKSPACE_ID"):
        assert runner["env"][name] == f"${{{{ secrets.{name} }}}}"
    assert runner["env"]["RUN_LABEL"] == "${{ inputs.run_label }}"
    assert "${{" not in runner["run"]
    for step in job["steps"]:
        if "uses" in step:
            sha = step["uses"].split("@")[1]
            assert len(sha) == 40
            int(sha, 16)


@pytest.mark.parametrize("stage", ["test", "prod"])
def test_all_deployment_methods_share_the_native_pipeline_gate(stage: str) -> None:
    etl = workflow(f"etl-{stage}.yml")
    job = etl["jobs"]["run-etl"]
    assert job["uses"] == "./.github/workflows/reusable-fabric-etl.yml"
    assert job["with"] == {
        "environment": stage.capitalize(),
        "item_name": "Patterns_Load_Validate_And_Refresh",
        "item_type": "DataPipeline",
        "job_type": "Pipeline",
        "run_label": f"{stage.capitalize()}-${{{{ github.run_id }}}}",
    }
    assert job["secrets"] == "inherit"
    assert "github.event.workflow_run.conclusion == 'success'" in job["if"]
    assert "github.event_name == 'workflow_dispatch'" in job["if"]
    deployments = [
        workflow(f"deploy-{stage}{suffix}.yml")["name"]
        for suffix in ("", "-bulk", "-fabric-cicd-bulk", "-fabric-cicd-plan")
    ]
    assert set(etl["on"]["workflow_run"]["workflows"]) == set(deployments)


def test_loader_notebook_remains_independent_of_model_refresh() -> None:
    notebook = (
        REPO_ROOT / "data" / "fabric" / "Import_Patterns_Data.Notebook" / "notebook-content.py"
    ).read_text(encoding="utf-8")
    assert "refresh_dataset" not in notebook
    assert "refresh_semantic_model" not in notebook
    assert "SEMANTIC_MODEL_NAME" not in notebook


@pytest.mark.parametrize("name", [
    "reusable-deploy-fabric-cicd.yml", "reusable-deploy-fabric-cicd-plan.yml",
    "reusable-deploy-fabric-cicd-bulk.yml", "reusable-deploy-bulk.yml",
])
def test_all_publishers_receive_environment_connection_variables(name: str) -> None:
    job = workflow(name)["jobs"]["deploy"]
    assert job["environment"] == "${{ inputs.environment }}"
    for variable in ("NOTEBOOK_CONNECTION_ID", "SEMANTIC_MODEL_REFRESH_CONNECTION_ID"):
        assert job["env"][variable] == f"${{{{ vars.{variable} }}}}"
