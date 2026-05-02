"""Unit tests for scripts/workspace_swap.py."""

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
    """Monkeypatch workspace_swap module-level paths to use the tmp_path fixture."""
    import workspace_swap

    original_fabric = workspace_swap.FABRIC_DIR
    original_repo = workspace_swap.REPO_ROOT
    original_vars = workspace_swap.VARIABLES_FILE
    original_settings = workspace_swap.SETTINGS_FILE
    original_vs_dir = workspace_swap.VALUE_SETS_DIR
    original_env = workspace_swap.ENV_FILE

    repo_root = fabric_dir.parent.parent
    workspace_swap.REPO_ROOT = repo_root
    workspace_swap.FABRIC_DIR = fabric_dir
    workspace_swap.VARIABLES_FILE = fabric_dir / "Patterns_Variables.VariableLibrary" / "variables.json"
    workspace_swap.SETTINGS_FILE = fabric_dir / "Patterns_Variables.VariableLibrary" / "settings.json"
    workspace_swap.VALUE_SETS_DIR = fabric_dir / "Patterns_Variables.VariableLibrary" / "valueSets"
    workspace_swap.ENV_FILE = repo_root / ".env"

    yield

    workspace_swap.FABRIC_DIR = original_fabric
    workspace_swap.REPO_ROOT = original_repo
    workspace_swap.VARIABLES_FILE = original_vars
    workspace_swap.SETTINGS_FILE = original_settings
    workspace_swap.VALUE_SETS_DIR = original_vs_dir
    workspace_swap.ENV_FILE = original_env


# ── sanitize_branch_name ──────────────────────────────────────────────────

class TestSanitizeBranchName:
    def test_slashes_replaced(self):
        from workspace_swap import sanitize_branch_name
        assert sanitize_branch_name("feature/login-fix") == "feature-login-fix"

    def test_dots_replaced(self):
        from workspace_swap import sanitize_branch_name
        assert sanitize_branch_name("user.name/branch") == "user-name-branch"

    def test_already_safe(self):
        from workspace_swap import sanitize_branch_name
        assert sanitize_branch_name("my-feature-branch") == "my-feature-branch"

    def test_multiple_special_chars(self):
        from workspace_swap import sanitize_branch_name
        assert sanitize_branch_name("feat/a.b@c") == "feat-a-b-c"


# ── repoint_items ─────────────────────────────────────────────────────────

@pytest.mark.usefixtures("_patch_paths")
class TestRepointItems:
    def test_rewrites_semantic_model(self, fabric_dir: Path):
        from workspace_swap import repoint_items
        changed = repoint_items(DEV_WS_ID, DEV_LH_ID, FEAT_WS_ID, FEAT_LH_ID, dry_run=False)
        sm_file = fabric_dir / "Test.SemanticModel" / "definition" / "expressions.tmdl"
        content = sm_file.read_text(encoding="utf-8")
        assert FEAT_WS_ID in content
        assert FEAT_LH_ID in content
        assert DEV_WS_ID not in content
        assert DEV_LH_ID not in content
        assert any("SemanticModel" in c or "expressions.tmdl" in c for c in changed)

    def test_rewrites_notebook_with_lakehouse(self, fabric_dir: Path):
        from workspace_swap import repoint_items
        changed = repoint_items(DEV_WS_ID, DEV_LH_ID, FEAT_WS_ID, FEAT_LH_ID, dry_run=False)
        nb_file = fabric_dir / "Import_Data.Notebook" / "notebook-content.py"
        content = nb_file.read_text(encoding="utf-8")
        assert FEAT_WS_ID in content
        assert FEAT_LH_ID in content
        assert any("Import_Data" in c for c in changed)

    def test_skips_notebook_without_lakehouse(self, fabric_dir: Path):
        from workspace_swap import repoint_items
        repoint_items(DEV_WS_ID, DEV_LH_ID, FEAT_WS_ID, FEAT_LH_ID, dry_run=False)
        nb2_file = fabric_dir / "Utility.Notebook" / "notebook-content.py"
        content = nb2_file.read_text(encoding="utf-8")
        assert content == "# no lakehouse reference\nprint('hello')\n"

    def test_does_not_rewrite_ontology(self, fabric_dir: Path):
        from workspace_swap import repoint_items
        ont_file = fabric_dir / "Test.Ontology" / "EntityTypes" / "123" / "DataBindings" / "binding.json"
        original = ont_file.read_text(encoding="utf-8")
        repoint_items(DEV_WS_ID, DEV_LH_ID, FEAT_WS_ID, FEAT_LH_ID, dry_run=False)
        assert ont_file.read_text(encoding="utf-8") == original

    def test_does_not_rewrite_data_agent(self, fabric_dir: Path):
        from workspace_swap import repoint_items
        da_file = fabric_dir / "Test.DataAgent" / "Files" / "Config" / "draft" / "ontology-Test" / "datasource.json"
        original = da_file.read_text(encoding="utf-8")
        repoint_items(DEV_WS_ID, DEV_LH_ID, FEAT_WS_ID, FEAT_LH_ID, dry_run=False)
        assert da_file.read_text(encoding="utf-8") == original

    def test_dry_run_does_not_modify(self, fabric_dir: Path):
        from workspace_swap import repoint_items
        sm_file = fabric_dir / "Test.SemanticModel" / "definition" / "expressions.tmdl"
        original = sm_file.read_text(encoding="utf-8")
        changed = repoint_items(DEV_WS_ID, DEV_LH_ID, FEAT_WS_ID, FEAT_LH_ID, dry_run=True)
        assert sm_file.read_text(encoding="utf-8") == original
        assert len(changed) > 0  # still reports what would change


# ── validate_no_ids ───────────────────────────────────────────────────────

@pytest.mark.usefixtures("_patch_paths")
class TestValidateNoIds:
    def test_detects_leftover_dev_ids(self, fabric_dir: Path):
        from workspace_swap import validate_no_ids
        # Files still contain dev IDs (not repointed)
        warnings = validate_no_ids(DEV_WS_ID, DEV_LH_ID)
        assert len(warnings) > 0
        assert any("workspace" in w for w in warnings)
        assert any("lakehouse" in w for w in warnings)

    def test_clean_after_repoint(self, fabric_dir: Path):
        from workspace_swap import repoint_items, validate_no_ids
        repoint_items(DEV_WS_ID, DEV_LH_ID, FEAT_WS_ID, FEAT_LH_ID, dry_run=False)
        warnings = validate_no_ids(DEV_WS_ID, DEV_LH_ID)
        assert warnings == []

    def test_skips_data_agent_empty_id_keys(self, fabric_dir: Path):
        from workspace_swap import validate_no_ids
        # Even though DataAgent files exist, id_keys=[] means no scanning
        warnings = validate_no_ids(DEV_WS_ID, DEV_LH_ID)
        assert not any("DataAgent" in w or "datasource" in w for w in warnings)

    def test_ontology_scans_lakehouse_only(self, fabric_dir: Path):
        """Ontology id_keys=["lakehouse"], so it should not flag workspace IDs."""
        from workspace_swap import validate_no_ids
        # The ontology files don't contain the actual dev lakehouse ID, only logicalIds
        warnings = validate_no_ids(DEV_WS_ID, DEV_LH_ID)
        ontology_warnings = [w for w in warnings if "Ontology" in w]
        assert ontology_warnings == []


# ── validate_dev_ids_present ──────────────────────────────────────────────

@pytest.mark.usefixtures("_patch_paths")
class TestValidateDevIdsPresent:
    def test_passes_when_dev_ids_present(self, fabric_dir: Path):
        from workspace_swap import validate_dev_ids_present
        errors = validate_dev_ids_present(DEV_WS_ID, DEV_LH_ID)
        assert errors == []

    def test_fails_when_dev_ids_replaced(self, fabric_dir: Path):
        from workspace_swap import repoint_items, validate_dev_ids_present
        repoint_items(DEV_WS_ID, DEV_LH_ID, FEAT_WS_ID, FEAT_LH_ID, dry_run=False)
        errors = validate_dev_ids_present(DEV_WS_ID, DEV_LH_ID)
        assert len(errors) > 0


# ── validate_no_stray_value_sets ──────────────────────────────────────────

@pytest.mark.usefixtures("_patch_paths")
class TestValidateNoStrayValueSets:
    def test_passes_with_only_allowed(self, fabric_dir: Path):
        from workspace_swap import validate_no_stray_value_sets
        errors = validate_no_stray_value_sets()
        assert errors == []

    def test_detects_feature_value_set(self, fabric_dir: Path):
        from workspace_swap import validate_no_stray_value_sets
        vs_dir = fabric_dir / "Patterns_Variables.VariableLibrary" / "valueSets"
        (vs_dir / "my-feature-branch.json").write_text("{}", encoding="utf-8")
        errors = validate_no_stray_value_sets()
        assert len(errors) == 1
        assert "my-feature-branch" in errors[0]


# ── create_or_update_value_set ────────────────────────────────────────────

@pytest.mark.usefixtures("_patch_paths")
class TestCreateOrUpdateValueSet:
    def test_creates_value_set(self, fabric_dir: Path):
        from workspace_swap import create_or_update_value_set, REPO_ROOT
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
        from workspace_swap import create_or_update_value_set
        vs_path = fabric_dir / "Patterns_Variables.VariableLibrary" / "valueSets" / "test-branch.json"
        create_or_update_value_set(vs_path, "test-branch", FEAT_WS_ID, FEAT_LH_ID, dry_run=True)
        assert not vs_path.exists()


# ── remove_value_set ─────────────────────────────────────────────────────

@pytest.mark.usefixtures("_patch_paths")
class TestRemoveValueSet:
    def test_deletes_existing(self, fabric_dir: Path):
        from workspace_swap import remove_value_set
        vs_path = fabric_dir / "Patterns_Variables.VariableLibrary" / "valueSets" / "test-branch.json"
        vs_path.write_text("{}", encoding="utf-8")
        result = remove_value_set(vs_path, dry_run=False)
        assert result is True
        assert not vs_path.exists()

    def test_handles_missing(self, fabric_dir: Path):
        from workspace_swap import remove_value_set
        vs_path = fabric_dir / "Patterns_Variables.VariableLibrary" / "valueSets" / "nonexistent.json"
        result = remove_value_set(vs_path, dry_run=False)
        assert result is False


# ── update_settings / remove_from_settings ────────────────────────────────

@pytest.mark.usefixtures("_patch_paths")
class TestSettings:
    def test_adds_branch_label(self, fabric_dir: Path):
        from workspace_swap import update_settings, load_json, SETTINGS_FILE
        update_settings("my-feature", dry_run=False)
        settings = load_json(SETTINGS_FILE)
        assert "my-feature" in settings["valueSetsOrder"]

    def test_does_not_duplicate(self, fabric_dir: Path):
        from workspace_swap import update_settings, load_json, SETTINGS_FILE
        update_settings("my-feature", dry_run=False)
        update_settings("my-feature", dry_run=False)
        settings = load_json(SETTINGS_FILE)
        assert settings["valueSetsOrder"].count("my-feature") == 1

    def test_removes_branch_label(self, fabric_dir: Path):
        from workspace_swap import update_settings, remove_from_settings, load_json, SETTINGS_FILE
        update_settings("my-feature", dry_run=False)
        remove_from_settings("my-feature", dry_run=False)
        settings = load_json(SETTINGS_FILE)
        assert "my-feature" not in settings["valueSetsOrder"]


# ── _read_env_file ────────────────────────────────────────────────────────

class TestReadEnvFile:
    def test_returns_empty_dict_when_file_missing(self, tmp_path: Path):
        from workspace_swap import _read_env_file
        assert _read_env_file(tmp_path / "does-not-exist.env") == {}

    def test_empty_file_returns_empty_dict(self, tmp_path: Path):
        from workspace_swap import _read_env_file
        env_path = tmp_path / ".env"
        env_path.write_text("", encoding="utf-8")
        assert _read_env_file(env_path) == {}

    def test_single_key_value(self, tmp_path: Path):
        from workspace_swap import _read_env_file
        env_path = tmp_path / ".env"
        env_path.write_text("FOO=bar\n", encoding="utf-8")
        assert _read_env_file(env_path) == {"FOO": "bar"}

    def test_multiple_keys(self, tmp_path: Path):
        from workspace_swap import _read_env_file
        env_path = tmp_path / ".env"
        env_path.write_text("FOO=bar\nBAZ=qux\n", encoding="utf-8")
        assert _read_env_file(env_path) == {"FOO": "bar", "BAZ": "qux"}

    def test_comment_lines_skipped(self, tmp_path: Path):
        from workspace_swap import _read_env_file
        env_path = tmp_path / ".env"
        env_path.write_text("# this is a comment\nFOO=bar\n# another\n", encoding="utf-8")
        assert _read_env_file(env_path) == {"FOO": "bar"}

    def test_blank_lines_skipped(self, tmp_path: Path):
        from workspace_swap import _read_env_file
        env_path = tmp_path / ".env"
        env_path.write_text("\n\nFOO=bar\n\n   \nBAZ=qux\n", encoding="utf-8")
        assert _read_env_file(env_path) == {"FOO": "bar", "BAZ": "qux"}

    def test_whitespace_stripped_from_keys_and_values(self, tmp_path: Path):
        from workspace_swap import _read_env_file
        env_path = tmp_path / ".env"
        env_path.write_text("  FOO  =  bar  \n", encoding="utf-8")
        assert _read_env_file(env_path) == {"FOO": "bar"}

    def test_lines_without_equals_skipped(self, tmp_path: Path):
        from workspace_swap import _read_env_file
        env_path = tmp_path / ".env"
        env_path.write_text("not a key value pair\nFOO=bar\nalso garbage\n", encoding="utf-8")
        assert _read_env_file(env_path) == {"FOO": "bar"}

    def test_empty_value_preserved(self, tmp_path: Path):
        from workspace_swap import _read_env_file
        env_path = tmp_path / ".env"
        env_path.write_text("FOO=\n", encoding="utf-8")
        # Empty string preserved (key still present), distinguishing from missing.
        assert _read_env_file(env_path) == {"FOO": ""}

    def test_value_containing_equals_split_on_first(self, tmp_path: Path):
        from workspace_swap import _read_env_file
        env_path = tmp_path / ".env"
        env_path.write_text("URL=https://example.com/path?a=1&b=2\n", encoding="utf-8")
        assert _read_env_file(env_path) == {"URL": "https://example.com/path?a=1&b=2"}

    def test_quoted_values_unquoted(self, tmp_path: Path):
        from workspace_swap import _read_env_file
        env_path = tmp_path / ".env"
        env_path.write_text(
            'DOUBLE="hello world"\nSINGLE=\'hi there\'\n',
            encoding="utf-8",
        )
        result = _read_env_file(env_path)
        assert result["DOUBLE"] == "hello world"
        assert result["SINGLE"] == "hi there"

    def test_duplicate_keys_last_wins(self, tmp_path: Path):
        from workspace_swap import _read_env_file
        env_path = tmp_path / ".env"
        env_path.write_text("FOO=first\nFOO=second\n", encoding="utf-8")
        assert _read_env_file(env_path) == {"FOO": "second"}

    def test_windows_line_endings(self, tmp_path: Path):
        from workspace_swap import _read_env_file
        env_path = tmp_path / ".env"
        # Use write_bytes to bypass any platform newline translation
        env_path.write_bytes(b"FOO=bar\r\nBAZ=qux\r\n")
        assert _read_env_file(env_path) == {"FOO": "bar", "BAZ": "qux"}


# ── resolve_feature_ids ───────────────────────────────────────────────────

@pytest.mark.usefixtures("_patch_paths")
class TestResolveFeatureIds:
    """Priority order: existing value set -> .env -> interactive prompt."""

    def _vs_path(self, fabric_dir: Path) -> Path:
        return fabric_dir / "Patterns_Variables.VariableLibrary" / "valueSets" / "feat.json"

    def _write_value_set(self, path: Path, ws_id: str, lh_id: str) -> None:
        path.write_text(json.dumps({
            "name": "feat",
            "variableOverrides": [
                {"name": "target_workspace_id", "value": ws_id},
                {"name": "target_lakehouse_id", "value": lh_id},
            ],
        }), encoding="utf-8")

    def _write_env(self, fabric_dir: Path, content: str) -> None:
        # ENV_FILE = REPO_ROOT / ".env"; in the test fixture REPO_ROOT == tmp_path
        env_path = fabric_dir.parent.parent / ".env"
        env_path.write_text(content, encoding="utf-8")

    def test_value_set_takes_priority(self, fabric_dir: Path):
        from workspace_swap import resolve_feature_ids
        vs_path = self._vs_path(fabric_dir)
        self._write_value_set(vs_path, FEAT_WS_ID, FEAT_LH_ID)
        # Even with an .env present pointing elsewhere, value set wins.
        self._write_env(
            fabric_dir,
            f"FEATURE_WORKSPACE_ID=99999999-9999-9999-9999-999999999999\n"
            f"FEATURE_LAKEHOUSE_ID=88888888-8888-8888-8888-888888888888\n",
        )
        ws_id, lh_id = resolve_feature_ids("feat", vs_path)
        assert ws_id == FEAT_WS_ID
        assert lh_id == FEAT_LH_ID

    def test_env_file_used_when_no_value_set(self, fabric_dir: Path):
        from workspace_swap import resolve_feature_ids
        vs_path = self._vs_path(fabric_dir)
        self._write_env(
            fabric_dir,
            f"FEATURE_WORKSPACE_ID={FEAT_WS_ID}\nFEATURE_LAKEHOUSE_ID={FEAT_LH_ID}\n",
        )
        ws_id, lh_id = resolve_feature_ids("feat", vs_path)
        assert ws_id == FEAT_WS_ID
        assert lh_id == FEAT_LH_ID

    def test_value_set_with_partial_data_falls_through_to_env(self, fabric_dir: Path):
        from workspace_swap import resolve_feature_ids
        vs_path = self._vs_path(fabric_dir)
        # Only target_workspace_id, no target_lakehouse_id
        vs_path.write_text(json.dumps({
            "name": "feat",
            "variableOverrides": [
                {"name": "target_workspace_id", "value": FEAT_WS_ID},
            ],
        }), encoding="utf-8")
        self._write_env(
            fabric_dir,
            f"FEATURE_WORKSPACE_ID=99999999-9999-9999-9999-999999999999\n"
            f"FEATURE_LAKEHOUSE_ID={FEAT_LH_ID}\n",
        )
        ws_id, lh_id = resolve_feature_ids("feat", vs_path)
        # Falls through to .env, so .env values are returned (not partial value set)
        assert ws_id == "99999999-9999-9999-9999-999999999999"
        assert lh_id == FEAT_LH_ID

    def test_no_value_set_no_env_prompts(self, fabric_dir: Path):
        from workspace_swap import resolve_feature_ids
        vs_path = self._vs_path(fabric_dir)
        with patch("builtins.input", side_effect=[FEAT_WS_ID, FEAT_LH_ID]):
            ws_id, lh_id = resolve_feature_ids("feat", vs_path)
        assert ws_id == FEAT_WS_ID
        assert lh_id == FEAT_LH_ID

    def test_env_missing_workspace_key_falls_through_to_prompt(self, fabric_dir: Path):
        from workspace_swap import resolve_feature_ids
        vs_path = self._vs_path(fabric_dir)
        self._write_env(fabric_dir, f"FEATURE_LAKEHOUSE_ID={FEAT_LH_ID}\n")
        with patch("builtins.input", side_effect=[FEAT_WS_ID, FEAT_LH_ID]):
            ws_id, lh_id = resolve_feature_ids("feat", vs_path)
        assert ws_id == FEAT_WS_ID
        assert lh_id == FEAT_LH_ID

    def test_env_missing_lakehouse_key_falls_through_to_prompt(self, fabric_dir: Path):
        from workspace_swap import resolve_feature_ids
        vs_path = self._vs_path(fabric_dir)
        self._write_env(fabric_dir, f"FEATURE_WORKSPACE_ID={FEAT_WS_ID}\n")
        with patch("builtins.input", side_effect=[FEAT_WS_ID, FEAT_LH_ID]):
            ws_id, lh_id = resolve_feature_ids("feat", vs_path)
        assert ws_id == FEAT_WS_ID
        assert lh_id == FEAT_LH_ID

    def test_env_invalid_guid_exits(self, fabric_dir: Path):
        from workspace_swap import resolve_feature_ids
        vs_path = self._vs_path(fabric_dir)
        self._write_env(
            fabric_dir,
            "FEATURE_WORKSPACE_ID=not-a-guid\n"
            f"FEATURE_LAKEHOUSE_ID={FEAT_LH_ID}\n",
        )
        with pytest.raises(SystemExit):
            resolve_feature_ids("feat", vs_path)

    def test_env_empty_workspace_value_falls_through_to_prompt(self, fabric_dir: Path):
        from workspace_swap import resolve_feature_ids
        vs_path = self._vs_path(fabric_dir)
        self._write_env(
            fabric_dir,
            f"FEATURE_WORKSPACE_ID=\nFEATURE_LAKEHOUSE_ID={FEAT_LH_ID}\n",
        )
        with patch("builtins.input", side_effect=[FEAT_WS_ID, FEAT_LH_ID]):
            ws_id, lh_id = resolve_feature_ids("feat", vs_path)
        assert ws_id == FEAT_WS_ID
        assert lh_id == FEAT_LH_ID

    def test_env_empty_lakehouse_value_falls_through_to_prompt(self, fabric_dir: Path):
        from workspace_swap import resolve_feature_ids
        vs_path = self._vs_path(fabric_dir)
        self._write_env(
            fabric_dir,
            f"FEATURE_WORKSPACE_ID={FEAT_WS_ID}\nFEATURE_LAKEHOUSE_ID=\n",
        )
        with patch("builtins.input", side_effect=[FEAT_WS_ID, FEAT_LH_ID]):
            ws_id, lh_id = resolve_feature_ids("feat", vs_path)
        assert ws_id == FEAT_WS_ID
        assert lh_id == FEAT_LH_ID

    def test_env_both_empty_values_falls_through_to_prompt(self, fabric_dir: Path):
        from workspace_swap import resolve_feature_ids
        vs_path = self._vs_path(fabric_dir)
        self._write_env(
            fabric_dir,
            "FEATURE_WORKSPACE_ID=\nFEATURE_LAKEHOUSE_ID=\n",
        )
        with patch("builtins.input", side_effect=[FEAT_WS_ID, FEAT_LH_ID]):
            ws_id, lh_id = resolve_feature_ids("feat", vs_path)
        assert ws_id == FEAT_WS_ID
        assert lh_id == FEAT_LH_ID

    def test_env_whitespace_only_value_falls_through_to_prompt(self, fabric_dir: Path):
        from workspace_swap import resolve_feature_ids
        vs_path = self._vs_path(fabric_dir)
        self._write_env(
            fabric_dir,
            'FEATURE_WORKSPACE_ID="   "\n'
            f'FEATURE_LAKEHOUSE_ID="{FEAT_LH_ID}"\n',
        )
        with patch("builtins.input", side_effect=[FEAT_WS_ID, FEAT_LH_ID]):
            ws_id, lh_id = resolve_feature_ids("feat", vs_path)
        assert ws_id == FEAT_WS_ID
        assert lh_id == FEAT_LH_ID


# ── _validate_guid ────────────────────────────────────────────────────────

class TestValidateGuid:
    def test_lowercase_passes(self):
        from workspace_swap import _validate_guid
        _validate_guid("aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee", "field")

    def test_uppercase_passes(self):
        from workspace_swap import _validate_guid
        _validate_guid("AAAAAAAA-BBBB-CCCC-DDDD-EEEEEEEEEEEE", "field")

    def test_mixed_case_passes(self):
        from workspace_swap import _validate_guid
        _validate_guid("AaAaAaAa-bBbB-cCcC-dDdD-eEeEeEeEeEeE", "field")

    def test_too_short_exits(self):
        from workspace_swap import _validate_guid
        with pytest.raises(SystemExit):
            _validate_guid("abc-123", "field")

    def test_curly_braces_exits(self):
        from workspace_swap import _validate_guid
        with pytest.raises(SystemExit):
            _validate_guid("{aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee}", "field")


# ── get_dev_ids ───────────────────────────────────────────────────────────

@pytest.mark.usefixtures("_patch_paths")
class TestGetDevIds:
    def test_returns_workspace_and_lakehouse(self, fabric_dir: Path):
        from workspace_swap import get_dev_ids
        ws_id, lh_id = get_dev_ids()
        assert ws_id == DEV_WS_ID
        assert lh_id == DEV_LH_ID

    def test_works_regardless_of_variable_order(self, fabric_dir: Path):
        from workspace_swap import get_dev_ids
        # Reorder variables in variables.json
        vars_path = fabric_dir / "Patterns_Variables.VariableLibrary" / "variables.json"
        vars_path.write_text(json.dumps({
            "variables": [
                {"name": "target_lakehouse_id", "value": DEV_LH_ID},
                {"name": "extra_unrelated", "value": "ignored"},
                {"name": "target_workspace_id", "value": DEV_WS_ID},
            ],
        }), encoding="utf-8")
        ws_id, lh_id = get_dev_ids()
        assert ws_id == DEV_WS_ID
        assert lh_id == DEV_LH_ID


# ── main() branch guard ──────────────────────────────────────────────────

@pytest.mark.usefixtures("_patch_paths")
class TestMainBranchGuard:
    def test_main_branch_exits(self, monkeypatch):
        import workspace_swap
        monkeypatch.setattr(sys, "argv", ["workspace_swap.py"])
        monkeypatch.setattr(workspace_swap, "get_current_branch", lambda: "main")
        with pytest.raises(SystemExit):
            workspace_swap.main()

    def test_dev_branch_exits(self, monkeypatch):
        import workspace_swap
        monkeypatch.setattr(sys, "argv", ["workspace_swap.py"])
        monkeypatch.setattr(workspace_swap, "get_current_branch", lambda: "dev")
        with pytest.raises(SystemExit):
            workspace_swap.main()

    def test_feature_branch_does_not_exit_early(self, monkeypatch, fabric_dir: Path):
        """Branch guard must not block feature branches. We let main() proceed
        as far as resolve_feature_ids, where we feed it a valid .env so the
        full flow completes without prompting."""
        import workspace_swap
        env_path = fabric_dir.parent.parent / ".env"
        env_path.write_text(
            f"FEATURE_WORKSPACE_ID={FEAT_WS_ID}\nFEATURE_LAKEHOUSE_ID={FEAT_LH_ID}\n",
            encoding="utf-8",
        )
        monkeypatch.setattr(sys, "argv", ["workspace_swap.py"])
        monkeypatch.setattr(workspace_swap, "get_current_branch", lambda: "feature/safe")
        # No SystemExit expected
        workspace_swap.main()
        # Side effect: value set was created
        vs_path = (
            fabric_dir / "Patterns_Variables.VariableLibrary"
            / "valueSets" / "feature-safe.json"
        )
        assert vs_path.exists()


# ── _run_swap_to_feature orchestration ─────────────────────────────────────────

@pytest.mark.usefixtures("_patch_paths")
class TestRunSwapToFeature:
    def _vs_path(self, fabric_dir: Path, branch_label: str) -> Path:
        return (
            fabric_dir / "Patterns_Variables.VariableLibrary"
            / "valueSets" / f"{branch_label}.json"
        )

    def _write_env(self, fabric_dir: Path, ws_id: str, lh_id: str) -> None:
        env_path = fabric_dir.parent.parent / ".env"
        env_path.write_text(
            f"FEATURE_WORKSPACE_ID={ws_id}\nFEATURE_LAKEHOUSE_ID={lh_id}\n",
            encoding="utf-8",
        )

    def test_env_with_feature_ids_creates_value_set_and_repoints(self, fabric_dir: Path):
        from workspace_swap import _run_swap_to_feature, load_json, SETTINGS_FILE
        self._write_env(fabric_dir, FEAT_WS_ID, FEAT_LH_ID)
        vs_path = self._vs_path(fabric_dir, "feat")
        _run_swap_to_feature("feat", "feat", vs_path, DEV_WS_ID, DEV_LH_ID, dry_run=False)

        # Value set written with correct overrides
        assert vs_path.exists()
        data = json.loads(vs_path.read_text(encoding="utf-8"))
        overrides = {o["name"]: o["value"] for o in data["variableOverrides"]}
        assert overrides["target_workspace_id"] == FEAT_WS_ID
        assert overrides["target_lakehouse_id"] == FEAT_LH_ID

        # Settings updated
        settings = load_json(SETTINGS_FILE)
        assert "feat" in settings["valueSetsOrder"]

        # Items repointed (semantic model is the canonical example)
        sm_file = fabric_dir / "Test.SemanticModel" / "definition" / "expressions.tmdl"
        content = sm_file.read_text(encoding="utf-8")
        assert FEAT_WS_ID in content
        assert DEV_WS_ID not in content

    def test_env_with_dev_ids_exits(self, fabric_dir: Path):
        """Regression for the demo failure: if .env points at the dev workspace,
        swap-to-feature must abort with no value set written."""
        from workspace_swap import _run_swap_to_feature
        self._write_env(fabric_dir, DEV_WS_ID, DEV_LH_ID)
        vs_path = self._vs_path(fabric_dir, "feat")
        with pytest.raises(SystemExit):
            _run_swap_to_feature("feat", "feat", vs_path, DEV_WS_ID, DEV_LH_ID, dry_run=False)
        assert not vs_path.exists()

    def test_partial_dev_id_match_does_not_block(self, fabric_dir: Path):
        """The guard requires BOTH IDs to match dev. Matching only one is
        legitimate (e.g. shared workspace, different lakehouse)."""
        from workspace_swap import _run_swap_to_feature
        # Same workspace ID, different lakehouse
        self._write_env(fabric_dir, DEV_WS_ID, FEAT_LH_ID)
        vs_path = self._vs_path(fabric_dir, "feat")
        _run_swap_to_feature("feat", "feat", vs_path, DEV_WS_ID, DEV_LH_ID, dry_run=False)
        assert vs_path.exists()

    def test_dry_run_makes_no_changes(self, fabric_dir: Path):
        from workspace_swap import _run_swap_to_feature, load_json, SETTINGS_FILE
        self._write_env(fabric_dir, FEAT_WS_ID, FEAT_LH_ID)
        vs_path = self._vs_path(fabric_dir, "feat")
        sm_file = fabric_dir / "Test.SemanticModel" / "definition" / "expressions.tmdl"
        original_sm = sm_file.read_text(encoding="utf-8")
        original_settings = load_json(SETTINGS_FILE)

        _run_swap_to_feature("feat", "feat", vs_path, DEV_WS_ID, DEV_LH_ID, dry_run=True)

        assert not vs_path.exists()
        assert sm_file.read_text(encoding="utf-8") == original_sm
        assert load_json(SETTINGS_FILE) == original_settings

    def test_idempotent_swap_to_feature(self, fabric_dir: Path):
        """Running swap-to-feature twice on the same branch must not error or
        duplicate state."""
        from workspace_swap import _run_swap_to_feature, load_json, SETTINGS_FILE
        self._write_env(fabric_dir, FEAT_WS_ID, FEAT_LH_ID)
        vs_path = self._vs_path(fabric_dir, "feat")
        _run_swap_to_feature("feat", "feat", vs_path, DEV_WS_ID, DEV_LH_ID, dry_run=False)
        # Second run: value set already exists, items already repointed
        _run_swap_to_feature("feat", "feat", vs_path, DEV_WS_ID, DEV_LH_ID, dry_run=False)

        assert vs_path.exists()
        settings = load_json(SETTINGS_FILE)
        assert settings["valueSetsOrder"].count("feat") == 1


# ── _run_swap_to_dev orchestration ─────────────────────────────────────────────

@pytest.mark.usefixtures("_patch_paths")
class TestRunSwapToDev:
    def _vs_path(self, fabric_dir: Path, branch_label: str) -> Path:
        return (
            fabric_dir / "Patterns_Variables.VariableLibrary"
            / "valueSets" / f"{branch_label}.json"
        )

    def test_round_trip_swap_to_feature_then_dev(self, fabric_dir: Path):
        from workspace_swap import _run_swap_to_feature, _run_swap_to_dev, load_json, SETTINGS_FILE
        env_path = fabric_dir.parent.parent / ".env"
        env_path.write_text(
            f"FEATURE_WORKSPACE_ID={FEAT_WS_ID}\nFEATURE_LAKEHOUSE_ID={FEAT_LH_ID}\n",
            encoding="utf-8",
        )
        vs_path = self._vs_path(fabric_dir, "feat")
        sm_file = fabric_dir / "Test.SemanticModel" / "definition" / "expressions.tmdl"
        original_sm = sm_file.read_text(encoding="utf-8")

        _run_swap_to_feature("feat", "feat", vs_path, DEV_WS_ID, DEV_LH_ID, dry_run=False)
        _run_swap_to_dev("feat", "feat", vs_path, DEV_WS_ID, DEV_LH_ID, dry_run=False)

        # Items reverted to dev IDs
        assert sm_file.read_text(encoding="utf-8") == original_sm
        # Value set deleted
        assert not vs_path.exists()
        # Settings entry removed
        settings = load_json(SETTINGS_FILE)
        assert "feat" not in settings["valueSetsOrder"]

    def test_swap_to_dev_without_value_set_exits(self, fabric_dir: Path):
        from workspace_swap import _run_swap_to_dev
        vs_path = self._vs_path(fabric_dir, "never-bootstrapped")
        with pytest.raises(SystemExit):
            _run_swap_to_dev("never-bootstrapped", "never-bootstrapped",
                       vs_path, DEV_WS_ID, DEV_LH_ID, dry_run=False)

    def test_swap_to_dev_does_not_read_env(self, fabric_dir: Path):
        """Reset uses the value set as the source of truth for feature IDs.
        A wrong .env must not corrupt the revert."""
        from workspace_swap import _run_swap_to_feature, _run_swap_to_dev
        env_path = fabric_dir.parent.parent / ".env"

        # Bootstrap with the correct .env
        env_path.write_text(
            f"FEATURE_WORKSPACE_ID={FEAT_WS_ID}\nFEATURE_LAKEHOUSE_ID={FEAT_LH_ID}\n",
            encoding="utf-8",
        )
        vs_path = self._vs_path(fabric_dir, "feat")
        sm_file = fabric_dir / "Test.SemanticModel" / "definition" / "expressions.tmdl"
        original_sm = sm_file.read_text(encoding="utf-8")
        _run_swap_to_feature("feat", "feat", vs_path, DEV_WS_ID, DEV_LH_ID, dry_run=False)

        # Now corrupt the .env (different IDs from what's actually in the items)
        env_path.write_text(
            "FEATURE_WORKSPACE_ID=99999999-9999-9999-9999-999999999999\n"
            "FEATURE_LAKEHOUSE_ID=88888888-8888-8888-8888-888888888888\n",
            encoding="utf-8",
        )
        # Reset should still work because it reads feature IDs from the value set
        _run_swap_to_dev("feat", "feat", vs_path, DEV_WS_ID, DEV_LH_ID, dry_run=False)

        assert sm_file.read_text(encoding="utf-8") == original_sm


# ── .env.sample (committed file) ─────────────────────────────────────────

class TestEnvSampleFile:
    """Smoke tests that the committed .env.sample stays in sync with the
    keys the script actually expects. Catches drift if a key is renamed."""

    REQUIRED_KEYS = {"FEATURE_WORKSPACE_ID", "FEATURE_LAKEHOUSE_ID"}

    def _sample_path(self) -> Path:
        import workspace_swap
        return workspace_swap.REPO_ROOT / ".env.sample"

    def test_env_sample_exists_and_parses(self):
        from workspace_swap import _read_env_file
        sample = self._sample_path()
        assert sample.exists(), ".env.sample must exist at repo root"
        # Parsing must not raise
        parsed = _read_env_file(sample)
        assert isinstance(parsed, dict)

    def test_env_sample_has_required_keys(self):
        from workspace_swap import _read_env_file
        parsed = _read_env_file(self._sample_path())
        assert self.REQUIRED_KEYS.issubset(parsed.keys()), (
            f".env.sample is missing required keys: "
            f"{self.REQUIRED_KEYS - parsed.keys()}"
        )

