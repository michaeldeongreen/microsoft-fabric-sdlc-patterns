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


def test_model_refresh_input_is_optional_for_notebook_only_callers() -> None:
    inputs = workflow("reusable-fabric-etl.yml")["on"]["workflow_call"]["inputs"]
    assert inputs["semantic_model_name"]["type"] == "string"
    assert inputs["semantic_model_name"]["required"] == "false"
    assert inputs["semantic_model_name"]["default"] == ""
    assert inputs["item_type"]["default"] == "Notebook"
    assert inputs["job_type"]["default"] == "RunNotebook"


def test_refresh_follows_successful_etl_and_propagates_failure() -> None:
    job = workflow("reusable-fabric-etl.yml")["jobs"]["run-etl"]
    steps = job["steps"]
    etl_index = next(i for i, step in enumerate(steps) if step.get("run") == "python scripts/run_fabric_etl.py")
    refresh_index = next(i for i, step in enumerate(steps) if step.get("run") == "python scripts/refresh_semantic_model.py")
    assert refresh_index == etl_index + 1
    assert steps[refresh_index]["if"] == "${{ success() && inputs.semantic_model_name != '' }}"
    assert steps[refresh_index]["env"]["SEMANTIC_MODEL_NAME"] == "${{ inputs.semantic_model_name }}"
    assert "continue-on-error" not in job
    assert "continue-on-error" not in steps[etl_index]
    assert "continue-on-error" not in steps[refresh_index]
    assert steps[etl_index]["timeout-minutes"] == "60"
    assert steps[refresh_index]["timeout-minutes"] == "15"
    assert int(job["timeout-minutes"]) >= 75


def test_refresh_uses_environment_secrets_without_inline_input_interpolation() -> None:
    reusable = workflow("reusable-fabric-etl.yml")
    job = reusable["jobs"]["run-etl"]
    assert reusable["permissions"] == {"contents": "read"}
    assert job["environment"] == "${{ inputs.environment }}"
    refresh = next(step for step in job["steps"] if step.get("run") == "python scripts/refresh_semantic_model.py")
    install = next(step["run"] for step in job["steps"] if "pip install" in step.get("run", ""))
    assert '"azure-identity>=1.15"' in install
    assert '"requests>=2.31"' in install
    for name in ("AZURE_TENANT_ID", "AZURE_CLIENT_ID", "AZURE_CLIENT_SECRET", "FABRIC_WORKSPACE_ID"):
        assert refresh["env"][name] == f"${{{{ secrets.{name} }}}}"
    assert "${{" not in refresh["run"]
    for step in job["steps"]:
        if "uses" in step:
            sha = step["uses"].split("@")[1]
            assert len(sha) == 40
            int(sha, 16)


@pytest.mark.parametrize("stage", ["test", "prod"])
def test_all_deployment_methods_share_the_model_refresh_gate(stage: str) -> None:
    etl = workflow(f"etl-{stage}.yml")
    job = etl["jobs"]["run-etl"]
    assert job["uses"] == "./.github/workflows/reusable-fabric-etl.yml"
    assert job["with"] == {
        "environment": stage.capitalize(),
        "item_name": "Import_Patterns_Data",
        "semantic_model_name": "Patterns_Semantic_Model",
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
