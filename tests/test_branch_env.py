"""Unit tests for scripts/branch_env.py."""

import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest


# ── Fixtures ───────────────────────────────────────────────────────────────

DEV_WS_ID = "d7270f11-feba-4990-baa6-d45e47f23737"
DEV_LH_ID = "c185283c-9dd9-4e40-a17c-aa6303e3a2e9"
FEAT_WS_ID = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
FEAT_LH_ID = "11111111-2222-3333-4444-555555555555"


@pytest.fixture()
def fabric_dir(tmp_path: Path) -> Path:
    """Create a minimal Fabric directory structure for testing."""
    fabric = tmp_path / "data" / "fabric"

    # SemanticModel
    sm_dir = fabric / "Test.SemanticModel" / "definition"
    sm_dir.mkdir(parents=True)
    (sm_dir / "expressions.tmdl").write_text(
        f'Source = AzureStorage.DataLake("https://onelake.dfs.fabric.microsoft.com/{DEV_WS_ID}/{DEV_LH_ID}")\n',
        encoding="utf-8",
    )

    # Notebook with lakehouse dependency
    nb_dir = fabric / "Import_Data.Notebook"
    nb_dir.mkdir(parents=True)
    (nb_dir / "notebook-content.py").write_text(
        f'{{"default_lakehouse": "{DEV_LH_ID}", "default_lakehouse_workspace_id": "{DEV_WS_ID}"}}\n# code here\n',
        encoding="utf-8",
    )

    # Notebook without lakehouse dependency (should be skipped)
    nb2_dir = fabric / "Utility.Notebook"
    nb2_dir.mkdir(parents=True)
    (nb2_dir / "notebook-content.py").write_text(
        "# no lakehouse reference\nprint('hello')\n",
        encoding="utf-8",
    )

    # Ontology DataBindings
    ont_db_dir = fabric / "Test.Ontology" / "EntityTypes" / "123" / "DataBindings"
    ont_db_dir.mkdir(parents=True)
    (ont_db_dir / "binding.json").write_text(
        json.dumps({
            "dataBindingConfiguration": {
                "sourceTableProperties": {
                    "workspaceId": "00000000-0000-0000-0000-000000000000",
                    "itemId": "b36b3bda-0782-a846-4a40-deb97694ebac",
                }
            }
        }),
        encoding="utf-8",
    )

    # Ontology Contextualizations
    ont_ctx_dir = fabric / "Test.Ontology" / "RelationshipTypes" / "456" / "Contextualizations"
    ont_ctx_dir.mkdir(parents=True)
    (ont_ctx_dir / "ctx.json").write_text(
        json.dumps({
            "dataBindingTable": {
                "workspaceId": "00000000-0000-0000-0000-000000000000",
                "itemId": "b36b3bda-0782-a846-4a40-deb97694ebac",
            }
        }),
        encoding="utf-8",
    )

    # DataAgent datasource
    da_dir = fabric / "Test.DataAgent" / "Files" / "Config" / "draft" / "ontology-Test"
    da_dir.mkdir(parents=True)
    (da_dir / "datasource.json").write_text(
        json.dumps({
            "artifactId": "58a6c8ed-d439-a7ba-4e80-99fc40aa27c4",
            "workspaceId": "00000000-0000-0000-0000-000000000000",
        }),
        encoding="utf-8",
    )

    # Variable Library
    vl_dir = fabric / "Patterns_Variables.VariableLibrary"
    vs_dir = vl_dir / "valueSets"
    vs_dir.mkdir(parents=True)
    (vl_dir / "variables.json").write_text(
        json.dumps({
            "variables": [
                {"name": "target_workspace_id", "value": DEV_WS_ID},
                {"name": "target_lakehouse_id", "value": DEV_LH_ID},
            ]
        }),
        encoding="utf-8",
    )
    (vl_dir / "settings.json").write_text(
        json.dumps({"valueSetsOrder": ["Test", "Prod"]}),
        encoding="utf-8",
    )
    (vs_dir / "Test.json").write_text("{}", encoding="utf-8")
    (vs_dir / "Prod.json").write_text("{}", encoding="utf-8")

    return fabric


@pytest.fixture()
def _patch_paths(fabric_dir: Path):
    """Monkeypatch branch_env module-level paths to use the tmp_path fixture."""
    import branch_env

    original_fabric = branch_env.FABRIC_DIR
    original_repo = branch_env.REPO_ROOT
    original_vars = branch_env.VARIABLES_FILE
    original_settings = branch_env.SETTINGS_FILE
    original_vs_dir = branch_env.VALUE_SETS_DIR

    repo_root = fabric_dir.parent.parent
    branch_env.REPO_ROOT = repo_root
    branch_env.FABRIC_DIR = fabric_dir
    branch_env.VARIABLES_FILE = fabric_dir / "Patterns_Variables.VariableLibrary" / "variables.json"
    branch_env.SETTINGS_FILE = fabric_dir / "Patterns_Variables.VariableLibrary" / "settings.json"
    branch_env.VALUE_SETS_DIR = fabric_dir / "Patterns_Variables.VariableLibrary" / "valueSets"

    yield

    branch_env.FABRIC_DIR = original_fabric
    branch_env.REPO_ROOT = original_repo
    branch_env.VARIABLES_FILE = original_vars
    branch_env.SETTINGS_FILE = original_settings
    branch_env.VALUE_SETS_DIR = original_vs_dir


# ── sanitize_branch_name ──────────────────────────────────────────────────

class TestSanitizeBranchName:
    def test_slashes_replaced(self):
        from branch_env import sanitize_branch_name
        assert sanitize_branch_name("feature/login-fix") == "feature-login-fix"

    def test_dots_replaced(self):
        from branch_env import sanitize_branch_name
        assert sanitize_branch_name("user.name/branch") == "user-name-branch"

    def test_already_safe(self):
        from branch_env import sanitize_branch_name
        assert sanitize_branch_name("my-feature-branch") == "my-feature-branch"

    def test_multiple_special_chars(self):
        from branch_env import sanitize_branch_name
        assert sanitize_branch_name("feat/a.b@c") == "feat-a-b-c"


# ── repoint_items ─────────────────────────────────────────────────────────

@pytest.mark.usefixtures("_patch_paths")
class TestRepointItems:
    def test_rewrites_semantic_model(self, fabric_dir: Path):
        from branch_env import repoint_items
        changed = repoint_items(DEV_WS_ID, DEV_LH_ID, FEAT_WS_ID, FEAT_LH_ID, dry_run=False)
        sm_file = fabric_dir / "Test.SemanticModel" / "definition" / "expressions.tmdl"
        content = sm_file.read_text(encoding="utf-8")
        assert FEAT_WS_ID in content
        assert FEAT_LH_ID in content
        assert DEV_WS_ID not in content
        assert DEV_LH_ID not in content
        assert any("SemanticModel" in c or "expressions.tmdl" in c for c in changed)

    def test_rewrites_notebook_with_lakehouse(self, fabric_dir: Path):
        from branch_env import repoint_items
        changed = repoint_items(DEV_WS_ID, DEV_LH_ID, FEAT_WS_ID, FEAT_LH_ID, dry_run=False)
        nb_file = fabric_dir / "Import_Data.Notebook" / "notebook-content.py"
        content = nb_file.read_text(encoding="utf-8")
        assert FEAT_WS_ID in content
        assert FEAT_LH_ID in content
        assert any("Import_Data" in c for c in changed)

    def test_skips_notebook_without_lakehouse(self, fabric_dir: Path):
        from branch_env import repoint_items
        repoint_items(DEV_WS_ID, DEV_LH_ID, FEAT_WS_ID, FEAT_LH_ID, dry_run=False)
        nb2_file = fabric_dir / "Utility.Notebook" / "notebook-content.py"
        content = nb2_file.read_text(encoding="utf-8")
        assert content == "# no lakehouse reference\nprint('hello')\n"

    def test_does_not_rewrite_ontology(self, fabric_dir: Path):
        from branch_env import repoint_items
        ont_file = fabric_dir / "Test.Ontology" / "EntityTypes" / "123" / "DataBindings" / "binding.json"
        original = ont_file.read_text(encoding="utf-8")
        repoint_items(DEV_WS_ID, DEV_LH_ID, FEAT_WS_ID, FEAT_LH_ID, dry_run=False)
        assert ont_file.read_text(encoding="utf-8") == original

    def test_does_not_rewrite_data_agent(self, fabric_dir: Path):
        from branch_env import repoint_items
        da_file = fabric_dir / "Test.DataAgent" / "Files" / "Config" / "draft" / "ontology-Test" / "datasource.json"
        original = da_file.read_text(encoding="utf-8")
        repoint_items(DEV_WS_ID, DEV_LH_ID, FEAT_WS_ID, FEAT_LH_ID, dry_run=False)
        assert da_file.read_text(encoding="utf-8") == original

    def test_dry_run_does_not_modify(self, fabric_dir: Path):
        from branch_env import repoint_items
        sm_file = fabric_dir / "Test.SemanticModel" / "definition" / "expressions.tmdl"
        original = sm_file.read_text(encoding="utf-8")
        changed = repoint_items(DEV_WS_ID, DEV_LH_ID, FEAT_WS_ID, FEAT_LH_ID, dry_run=True)
        assert sm_file.read_text(encoding="utf-8") == original
        assert len(changed) > 0  # still reports what would change


# ── validate_no_ids ───────────────────────────────────────────────────────

@pytest.mark.usefixtures("_patch_paths")
class TestValidateNoIds:
    def test_detects_leftover_dev_ids(self, fabric_dir: Path):
        from branch_env import validate_no_ids
        # Files still contain dev IDs (not repointed)
        warnings = validate_no_ids(DEV_WS_ID, DEV_LH_ID)
        assert len(warnings) > 0
        assert any("workspace" in w for w in warnings)
        assert any("lakehouse" in w for w in warnings)

    def test_clean_after_repoint(self, fabric_dir: Path):
        from branch_env import repoint_items, validate_no_ids
        repoint_items(DEV_WS_ID, DEV_LH_ID, FEAT_WS_ID, FEAT_LH_ID, dry_run=False)
        warnings = validate_no_ids(DEV_WS_ID, DEV_LH_ID)
        assert warnings == []

    def test_skips_data_agent_empty_id_keys(self, fabric_dir: Path):
        from branch_env import validate_no_ids
        # Even though DataAgent files exist, id_keys=[] means no scanning
        warnings = validate_no_ids(DEV_WS_ID, DEV_LH_ID)
        assert not any("DataAgent" in w or "datasource" in w for w in warnings)

    def test_ontology_scans_lakehouse_only(self, fabric_dir: Path):
        """Ontology id_keys=["lakehouse"], so it should not flag workspace IDs."""
        from branch_env import validate_no_ids
        # The ontology files don't contain the actual dev lakehouse ID, only logicalIds
        warnings = validate_no_ids(DEV_WS_ID, DEV_LH_ID)
        ontology_warnings = [w for w in warnings if "Ontology" in w]
        assert ontology_warnings == []


# ── validate_dev_ids_present ──────────────────────────────────────────────

@pytest.mark.usefixtures("_patch_paths")
class TestValidateDevIdsPresent:
    def test_passes_when_dev_ids_present(self, fabric_dir: Path):
        from branch_env import validate_dev_ids_present
        errors = validate_dev_ids_present(DEV_WS_ID, DEV_LH_ID)
        assert errors == []

    def test_fails_when_dev_ids_replaced(self, fabric_dir: Path):
        from branch_env import repoint_items, validate_dev_ids_present
        repoint_items(DEV_WS_ID, DEV_LH_ID, FEAT_WS_ID, FEAT_LH_ID, dry_run=False)
        errors = validate_dev_ids_present(DEV_WS_ID, DEV_LH_ID)
        assert len(errors) > 0


# ── validate_no_stray_value_sets ──────────────────────────────────────────

@pytest.mark.usefixtures("_patch_paths")
class TestValidateNoStrayValueSets:
    def test_passes_with_only_allowed(self, fabric_dir: Path):
        from branch_env import validate_no_stray_value_sets
        errors = validate_no_stray_value_sets()
        assert errors == []

    def test_detects_feature_value_set(self, fabric_dir: Path):
        from branch_env import validate_no_stray_value_sets
        vs_dir = fabric_dir / "Patterns_Variables.VariableLibrary" / "valueSets"
        (vs_dir / "my-feature-branch.json").write_text("{}", encoding="utf-8")
        errors = validate_no_stray_value_sets()
        assert len(errors) == 1
        assert "my-feature-branch" in errors[0]


# ── create_or_update_value_set ────────────────────────────────────────────

@pytest.mark.usefixtures("_patch_paths")
class TestCreateOrUpdateValueSet:
    def test_creates_value_set(self, fabric_dir: Path):
        from branch_env import create_or_update_value_set, REPO_ROOT
        vs_path = fabric_dir / "Patterns_Variables.VariableLibrary" / "valueSets" / "test-branch.json"
        result = create_or_update_value_set(vs_path, "test-branch", FEAT_WS_ID, FEAT_LH_ID, dry_run=False)
        assert result is True
        assert vs_path.exists()
        data = json.loads(vs_path.read_text(encoding="utf-8"))
        assert data["name"] == "test-branch"
        overrides = {o["name"]: o["value"] for o in data["variableOverrides"]}
        assert overrides["target_workspace_id"] == FEAT_WS_ID
        assert overrides["target_lakehouse_id"] == FEAT_LH_ID

    def test_dry_run_does_not_create(self, fabric_dir: Path):
        from branch_env import create_or_update_value_set
        vs_path = fabric_dir / "Patterns_Variables.VariableLibrary" / "valueSets" / "test-branch.json"
        create_or_update_value_set(vs_path, "test-branch", FEAT_WS_ID, FEAT_LH_ID, dry_run=True)
        assert not vs_path.exists()


# ── remove_value_set ─────────────────────────────────────────────────────

@pytest.mark.usefixtures("_patch_paths")
class TestRemoveValueSet:
    def test_deletes_existing(self, fabric_dir: Path):
        from branch_env import remove_value_set
        vs_path = fabric_dir / "Patterns_Variables.VariableLibrary" / "valueSets" / "test-branch.json"
        vs_path.write_text("{}", encoding="utf-8")
        result = remove_value_set(vs_path, dry_run=False)
        assert result is True
        assert not vs_path.exists()

    def test_handles_missing(self, fabric_dir: Path):
        from branch_env import remove_value_set
        vs_path = fabric_dir / "Patterns_Variables.VariableLibrary" / "valueSets" / "nonexistent.json"
        result = remove_value_set(vs_path, dry_run=False)
        assert result is False


# ── update_settings / remove_from_settings ────────────────────────────────

@pytest.mark.usefixtures("_patch_paths")
class TestSettings:
    def test_adds_branch_label(self, fabric_dir: Path):
        from branch_env import update_settings, load_json, SETTINGS_FILE
        update_settings("my-feature", dry_run=False)
        settings = load_json(SETTINGS_FILE)
        assert "my-feature" in settings["valueSetsOrder"]

    def test_does_not_duplicate(self, fabric_dir: Path):
        from branch_env import update_settings, load_json, SETTINGS_FILE
        update_settings("my-feature", dry_run=False)
        update_settings("my-feature", dry_run=False)
        settings = load_json(SETTINGS_FILE)
        assert settings["valueSetsOrder"].count("my-feature") == 1

    def test_removes_branch_label(self, fabric_dir: Path):
        from branch_env import update_settings, remove_from_settings, load_json, SETTINGS_FILE
        update_settings("my-feature", dry_run=False)
        remove_from_settings("my-feature", dry_run=False)
        settings = load_json(SETTINGS_FILE)
        assert "my-feature" not in settings["valueSetsOrder"]
