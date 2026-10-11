"""Deployment fixtures use canonical source definitions, not feature bindings."""

from __future__ import annotations

import json
import re
import shutil
from pathlib import Path

import pytest

from pipeline_bindings import BASELINE_VALUES, rewrite

REPO_ROOT = Path(__file__).resolve().parents[1]
NOTEBOOK_CONNECTION_ID = "aaaaaaa1-1111-4111-8111-111111111111"
REFRESH_CONNECTION_ID = "bbbbbbb2-2222-4222-8222-222222222222"


@pytest.fixture
def pipeline_connection_environment(monkeypatch: pytest.MonkeyPatch) -> dict[str, str]:
    values = {
        "NOTEBOOK_CONNECTION_ID": NOTEBOOK_CONNECTION_ID,
        "SEMANTIC_MODEL_REFRESH_CONNECTION_ID": REFRESH_CONNECTION_ID,
    }
    for name, value in values.items():
        monkeypatch.setenv(name, value)
    return values


@pytest.fixture
def canonical_fabric_repository(tmp_path: Path) -> Path:
    """Copy the current inventory and restore only the copy's environment IDs."""
    directory = tmp_path / "fabric"
    shutil.copytree(REPO_ROOT / "data" / "fabric", directory)
    variables = json.loads(
        (directory / "Patterns_Variables.VariableLibrary" / "variables.json").read_text(encoding="utf-8")
    )
    defaults = {value["name"]: value["value"] for value in variables["variables"]}
    loader = directory / "Import_Patterns_Data.Notebook" / "notebook-content.py"
    source = loader.read_text(encoding="utf-8")
    lakehouse = re.search(r'"default_lakehouse":\s*"([^"]+)"', source)
    workspace = re.search(r'"default_lakehouse_workspace_id":\s*"([^"]+)"', source)
    assert lakehouse is not None and workspace is not None
    for path in directory.rglob("*"):
        if path.is_file() and path.suffix in {".py", ".json", ".tmdl"}:
            text = path.read_text(encoding="utf-8")
            text = text.replace(workspace.group(1), defaults["target_workspace_id"])
            text = text.replace(lakehouse.group(1), defaults["target_lakehouse_id"])
            if path.name == "pipeline-content.json":
                text = rewrite(text, BASELINE_VALUES)
            path.write_text(text, encoding="utf-8")
    library = directory / "Patterns_Variables.VariableLibrary"
    for path in (library / "valueSets").glob("*.json"):
        if path.stem not in {"Test", "Prod"}:
            path.unlink()
    settings_path = library / "settings.json"
    settings = json.loads(settings_path.read_text(encoding="utf-8"))
    settings["valueSetsOrder"] = [name for name in settings["valueSetsOrder"] if name in {"Test", "Prod"}]
    settings_path.write_text(json.dumps(settings), encoding="utf-8")
    return directory
