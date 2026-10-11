"""Unit tests for scripts/workspace_swap.py."""

import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

import pipeline_bindings as pb


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
    """Source of truth: .env at repo root. Missing/blank → exit with error."""

    def _vs_path(self, fabric_dir: Path) -> Path:
        return fabric_dir / "Patterns_Variables.VariableLibrary" / "valueSets" / "feat.json"

    def _write_env(self, fabric_dir: Path, content: str) -> None:
        # ENV_FILE = REPO_ROOT / ".env"; in the test fixture REPO_ROOT == tmp_path
        env_path = fabric_dir.parent.parent / ".env"
        env_path.write_text(content, encoding="utf-8")

    def test_env_file_resolves_ids(self, fabric_dir: Path):
        from workspace_swap import resolve_feature_ids
        vs_path = self._vs_path(fabric_dir)
        self._write_env(
            fabric_dir,
            f"FEATURE_WORKSPACE_ID={FEAT_WS_ID}\nFEATURE_LAKEHOUSE_ID={FEAT_LH_ID}\n",
        )
        ws_id, lh_id = resolve_feature_ids("feat", vs_path)
        assert ws_id == FEAT_WS_ID
        assert lh_id == FEAT_LH_ID

    def test_env_takes_precedence_over_existing_value_set(self, fabric_dir: Path):
        """A pre-existing value set must NOT override .env. Stale value sets
        were the cause of a wrong-workspace swap before this change."""
        from workspace_swap import resolve_feature_ids
        vs_path = self._vs_path(fabric_dir)
        vs_path.parent.mkdir(parents=True, exist_ok=True)
        vs_path.write_text(json.dumps({
            "name": "feat",
            "variableOverrides": [
                {"name": "target_workspace_id", "value": "99999999-9999-9999-9999-999999999999"},
                {"name": "target_lakehouse_id", "value": "88888888-8888-8888-8888-888888888888"},
            ],
        }), encoding="utf-8")
        self._write_env(
            fabric_dir,
            f"FEATURE_WORKSPACE_ID={FEAT_WS_ID}\nFEATURE_LAKEHOUSE_ID={FEAT_LH_ID}\n",
        )
        ws_id, lh_id = resolve_feature_ids("feat", vs_path)
        assert ws_id == FEAT_WS_ID
        assert lh_id == FEAT_LH_ID

    def test_no_env_file_exits(self, fabric_dir: Path):
        from workspace_swap import resolve_feature_ids
        vs_path = self._vs_path(fabric_dir)
        # No .env created.
        with pytest.raises(SystemExit) as exc:
            resolve_feature_ids("feat", vs_path)
        assert ".env" in str(exc.value)

    def test_env_missing_workspace_key_exits(self, fabric_dir: Path):
        from workspace_swap import resolve_feature_ids
        vs_path = self._vs_path(fabric_dir)
        self._write_env(fabric_dir, f"FEATURE_LAKEHOUSE_ID={FEAT_LH_ID}\n")
        with pytest.raises(SystemExit) as exc:
            resolve_feature_ids("feat", vs_path)
        assert "FEATURE_WORKSPACE_ID" in str(exc.value)

    def test_env_missing_lakehouse_key_exits(self, fabric_dir: Path):
        from workspace_swap import resolve_feature_ids
        vs_path = self._vs_path(fabric_dir)
        self._write_env(fabric_dir, f"FEATURE_WORKSPACE_ID={FEAT_WS_ID}\n")
        with pytest.raises(SystemExit) as exc:
            resolve_feature_ids("feat", vs_path)
        assert "FEATURE_LAKEHOUSE_ID" in str(exc.value)

    def test_env_blank_workspace_value_exits(self, fabric_dir: Path):
        from workspace_swap import resolve_feature_ids
        vs_path = self._vs_path(fabric_dir)
        self._write_env(
            fabric_dir,
            f"FEATURE_WORKSPACE_ID=\nFEATURE_LAKEHOUSE_ID={FEAT_LH_ID}\n",
        )
        with pytest.raises(SystemExit) as exc:
            resolve_feature_ids("feat", vs_path)
        assert "FEATURE_WORKSPACE_ID" in str(exc.value)

    def test_env_blank_lakehouse_value_exits(self, fabric_dir: Path):
        from workspace_swap import resolve_feature_ids
        vs_path = self._vs_path(fabric_dir)
        self._write_env(
            fabric_dir,
            f"FEATURE_WORKSPACE_ID={FEAT_WS_ID}\nFEATURE_LAKEHOUSE_ID=\n",
        )
        with pytest.raises(SystemExit) as exc:
            resolve_feature_ids("feat", vs_path)
        assert "FEATURE_LAKEHOUSE_ID" in str(exc.value)

    def test_env_whitespace_only_value_exits(self, fabric_dir: Path):
        from workspace_swap import resolve_feature_ids
        vs_path = self._vs_path(fabric_dir)
        self._write_env(
            fabric_dir,
            'FEATURE_WORKSPACE_ID="   "\n'
            f'FEATURE_LAKEHOUSE_ID="{FEAT_LH_ID}"\n',
        )
        with pytest.raises(SystemExit) as exc:
            resolve_feature_ids("feat", vs_path)
        assert "FEATURE_WORKSPACE_ID" in str(exc.value)

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


# ── _confirm_swap_to_feature ──────────────────────────────────────────────

class TestConfirmSwapToFeature:
    """Confirmation gating before any files are rewritten by swap-to-feature."""

    def test_yes_uppercase_proceeds(self):
        from workspace_swap import _confirm_swap_to_feature
        with patch("builtins.input", return_value="YES"):
            # Should return without raising.
            _confirm_swap_to_feature("feat", DEV_WS_ID, DEV_LH_ID, FEAT_WS_ID, FEAT_LH_ID)

    def test_yes_lowercase_aborts(self):
        from workspace_swap import _confirm_swap_to_feature
        with patch("builtins.input", return_value="yes"):
            with pytest.raises(SystemExit) as exc:
                _confirm_swap_to_feature("feat", DEV_WS_ID, DEV_LH_ID, FEAT_WS_ID, FEAT_LH_ID)
        assert "Aborted" in str(exc.value)

    def test_y_aborts(self):
        from workspace_swap import _confirm_swap_to_feature
        with patch("builtins.input", return_value="y"):
            with pytest.raises(SystemExit) as exc:
                _confirm_swap_to_feature("feat", DEV_WS_ID, DEV_LH_ID, FEAT_WS_ID, FEAT_LH_ID)
        assert "Aborted" in str(exc.value)

    def test_blank_aborts(self):
        from workspace_swap import _confirm_swap_to_feature
        with patch("builtins.input", return_value=""):
            with pytest.raises(SystemExit) as exc:
                _confirm_swap_to_feature("feat", DEV_WS_ID, DEV_LH_ID, FEAT_WS_ID, FEAT_LH_ID)
        assert "Aborted" in str(exc.value)

    def test_eof_aborts(self):
        from workspace_swap import _confirm_swap_to_feature
        with patch("builtins.input", side_effect=EOFError):
            with pytest.raises(SystemExit) as exc:
                _confirm_swap_to_feature("feat", DEV_WS_ID, DEV_LH_ID, FEAT_WS_ID, FEAT_LH_ID)
        assert "Aborted" in str(exc.value)

    def test_yes_with_surrounding_whitespace_proceeds(self):
        """input().strip() removes surrounding whitespace; case still matters."""
        from workspace_swap import _confirm_swap_to_feature
        with patch("builtins.input", return_value="  YES  "):
            _confirm_swap_to_feature("feat", DEV_WS_ID, DEV_LH_ID, FEAT_WS_ID, FEAT_LH_ID)

    def test_planned_swap_is_displayed(self, capsys: pytest.CaptureFixture):
        """User must see the planned IDs before being asked to confirm."""
        from workspace_swap import _confirm_swap_to_feature
        with patch("builtins.input", return_value="YES"):
            _confirm_swap_to_feature("my-branch", DEV_WS_ID, DEV_LH_ID, FEAT_WS_ID, FEAT_LH_ID)
        out = capsys.readouterr().out
        assert "my-branch" in out
        assert DEV_WS_ID in out
        assert FEAT_WS_ID in out
        assert DEV_LH_ID in out
        assert FEAT_LH_ID in out


# ── _read_previous_feature_ids ────────────────────────────────────────────

class TestReadPreviousFeatureIds:
    """Recovery support: read the IDs a previous swap applied so the next
    swap can rewrite them if .env has changed."""

    def test_returns_none_when_value_set_missing(self, tmp_path: Path):
        from workspace_swap import _read_previous_feature_ids
        ws_id, lh_id = _read_previous_feature_ids(tmp_path / "missing.json")
        assert ws_id is None
        assert lh_id is None

    def test_reads_both_ids_from_value_set(self, tmp_path: Path):
        from workspace_swap import _read_previous_feature_ids
        path = tmp_path / "feat.json"
        path.write_text(json.dumps({
            "name": "feat",
            "variableOverrides": [
                {"name": "target_workspace_id", "value": FEAT_WS_ID},
                {"name": "target_lakehouse_id", "value": FEAT_LH_ID},
            ],
        }), encoding="utf-8")
        ws_id, lh_id = _read_previous_feature_ids(path)
        assert ws_id == FEAT_WS_ID
        assert lh_id == FEAT_LH_ID

    def test_returns_none_for_missing_overrides(self, tmp_path: Path):
        from workspace_swap import _read_previous_feature_ids
        path = tmp_path / "feat.json"
        path.write_text(json.dumps({"name": "feat", "variableOverrides": []}), encoding="utf-8")
        ws_id, lh_id = _read_previous_feature_ids(path)
        assert ws_id is None
        assert lh_id is None

    def test_returns_none_when_value_set_malformed(self, tmp_path: Path):
        """A corrupt or non-JSON value-set file shouldn't crash the swap."""
        from workspace_swap import _read_previous_feature_ids
        path = tmp_path / "feat.json"
        path.write_text("not valid json", encoding="utf-8")
        ws_id, lh_id = _read_previous_feature_ids(path)
        assert ws_id is None
        assert lh_id is None


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
        full flow completes. The confirmation prompt is auto-answered with
        YES."""
        import workspace_swap
        env_path = fabric_dir.parent.parent / ".env"
        env_path.write_text(
            f"FEATURE_WORKSPACE_ID={FEAT_WS_ID}\nFEATURE_LAKEHOUSE_ID={FEAT_LH_ID}\n",
            encoding="utf-8",
        )
        monkeypatch.setattr(sys, "argv", ["workspace_swap.py"])
        monkeypatch.setattr(workspace_swap, "get_current_branch", lambda: "feature/safe")
        # No SystemExit expected
        with patch("builtins.input", return_value="YES"):
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
        with patch("builtins.input", return_value="YES"):
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
        with patch("builtins.input", return_value="YES"):
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

    def test_dry_run_skips_confirmation(self, fabric_dir: Path):
        """--dry-run is the verification step; no confirmation prompt."""
        from workspace_swap import _run_swap_to_feature
        self._write_env(fabric_dir, FEAT_WS_ID, FEAT_LH_ID)
        vs_path = self._vs_path(fabric_dir, "feat")
        # If the prompt fired, input() would be called and raise OSError
        # under pytest's stdin capture. The fact that this passes without
        # patching input() proves dry-run skips confirmation.
        _run_swap_to_feature("feat", "feat", vs_path, DEV_WS_ID, DEV_LH_ID, dry_run=True)

    def test_idempotent_swap_to_feature(self, fabric_dir: Path):
        """Running swap-to-feature twice on the same branch must not error or
        duplicate state."""
        from workspace_swap import _run_swap_to_feature, load_json, SETTINGS_FILE
        self._write_env(fabric_dir, FEAT_WS_ID, FEAT_LH_ID)
        vs_path = self._vs_path(fabric_dir, "feat")
        with patch("builtins.input", return_value="YES"):
            _run_swap_to_feature("feat", "feat", vs_path, DEV_WS_ID, DEV_LH_ID, dry_run=False)
            # Second run: value set already exists, items already repointed
            _run_swap_to_feature("feat", "feat", vs_path, DEV_WS_ID, DEV_LH_ID, dry_run=False)

        assert vs_path.exists()
        settings = load_json(SETTINGS_FILE)
        assert settings["valueSetsOrder"].count("feat") == 1

    def test_recovers_from_stale_feature_ids_in_files(self, fabric_dir: Path):
        """Regression for the wrong-.env scenario: a previous swap applied
        stale feature IDs; .env now points at the correct workspace; re-running
        the swap must rewrite the stale IDs to the correct ones (recovery
        pass), without needing manual cleanup of the SemanticModel/Notebook
        files."""
        from workspace_swap import _run_swap_to_feature
        STALE_WS_ID = "99999999-9999-9999-9999-999999999999"
        STALE_LH_ID = "88888888-8888-8888-8888-888888888888"

        # First: simulate a prior bad swap by writing the stale IDs into the
        # value set and the SemanticModel file.
        self._write_env(fabric_dir, STALE_WS_ID, STALE_LH_ID)
        vs_path = self._vs_path(fabric_dir, "feat")
        with patch("builtins.input", return_value="YES"):
            _run_swap_to_feature("feat", "feat", vs_path, DEV_WS_ID, DEV_LH_ID, dry_run=False)

        sm_file = fabric_dir / "Test.SemanticModel" / "definition" / "expressions.tmdl"
        assert STALE_WS_ID in sm_file.read_text(encoding="utf-8")

        # Now: correct .env and re-run. Recovery pass should rewrite the
        # stale IDs even though dev IDs are no longer in the file.
        self._write_env(fabric_dir, FEAT_WS_ID, FEAT_LH_ID)
        with patch("builtins.input", return_value="YES"):
            _run_swap_to_feature("feat", "feat", vs_path, DEV_WS_ID, DEV_LH_ID, dry_run=False)

        content = sm_file.read_text(encoding="utf-8")
        assert FEAT_WS_ID in content
        assert FEAT_LH_ID in content
        assert STALE_WS_ID not in content
        assert STALE_LH_ID not in content

    def test_no_recovery_pass_when_stale_matches_target(self, fabric_dir: Path):
        """When the value set already has the target IDs (e.g., a prior run
        succeeded), the recovery pass must not run \u2014 nothing to recover."""
        from workspace_swap import _run_swap_to_feature
        self._write_env(fabric_dir, FEAT_WS_ID, FEAT_LH_ID)
        vs_path = self._vs_path(fabric_dir, "feat")

        # First run: applies feature IDs cleanly.
        with patch("builtins.input", return_value="YES"):
            _run_swap_to_feature("feat", "feat", vs_path, DEV_WS_ID, DEV_LH_ID, dry_run=False)

        # Second run with the same .env: capture stdout to confirm no recovery
        # log line.
        with patch("builtins.input", return_value="YES"):
            with patch("builtins.print") as mock_print:
                _run_swap_to_feature("feat", "feat", vs_path, DEV_WS_ID, DEV_LH_ID, dry_run=False)

        all_output = " ".join(str(call) for call in mock_print.call_args_list)
        assert "Recovery:" not in all_output


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

        with patch("builtins.input", return_value="YES"):
            _run_swap_to_feature("feat", "feat", vs_path, DEV_WS_ID, DEV_LH_ID, dry_run=False)
        # swap-to-dev does not prompt for confirmation.
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
        with patch("builtins.input", return_value="YES"):
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


# ── DataPipeline bindings (native refresh pipeline) ──────────────────────────

FEAT_MODEL_ID = "bbbbbbbb-1111-4111-8111-bbbbbbbbbbbb"
FEAT_NOTEBOOK_CONN_ID = "cccccccc-2222-4222-8222-cccccccccccc"
FEAT_REFRESH_CONN_ID = "dddddddd-3333-4333-8333-dddddddddddd"
FEAT_PIPELINE_VALUES = {
    "Semantic model": FEAT_MODEL_ID,
    "Notebook connection": FEAT_NOTEBOOK_CONN_ID,
    "Refresh connection": FEAT_REFRESH_CONN_ID,
}
NOTEBOOK_LOGICAL_IDS = (
    "3f21b546-f49f-9fef-4881-99b654a6701e",
    "decdcb11-8770-4216-8a28-eadf505d2679",
)
PIPELINE_RELPATH = Path("Patterns_Load.DataPipeline") / "pipeline-content.json"


def _pipeline_text(*, workspace: str = DEV_WS_ID, values: dict[str, str] | None = None,
                   refreshes: int = 1) -> str:
    """A pipeline in Fabric's git shape: portable notebook refs, literal refresh targets."""
    values = values or pb.BASELINE_VALUES

    def notebook(name: str, logical_id: str) -> dict:
        return {
            "name": name,
            "type": pb.NOTEBOOK_ACTIVITY_TYPE,
            "dependsOn": [],
            "typeProperties": {"notebookId": logical_id, "workspaceId": pb.ZERO_GUID},
            "externalReferences": {"connection": values["Notebook connection"]},
        }

    def refresh(name: str) -> dict:
        return {
            "name": name,
            "type": pb.REFRESH_ACTIVITY_TYPE,
            "dependsOn": [],
            "typeProperties": {
                "method": "post",
                "groupId": workspace,
                "datasetId": values["Semantic model"],
                "commitMode": "Transactional",
                "waitOnCompletion": True,
                "operationType": "SemanticModelRefresh",
            },
            "externalReferences": {"connection": values["Refresh connection"]},
        }

    activities = [
        notebook("Import_Patterns_Data", NOTEBOOK_LOGICAL_IDS[0]),
        notebook("Validate_Patterns_Data", NOTEBOOK_LOGICAL_IDS[1]),
    ]
    activities += [
        refresh("Refresh_Patterns_Semantic_Model" if refreshes == 1 else f"Refresh_{n}")
        for n in range(refreshes)
    ]
    return json.dumps({"properties": {"activities": activities}}, indent=2) + "\n"


def _write_pipeline(fabric_dir: Path, **kwargs) -> Path:
    path = fabric_dir / PIPELINE_RELPATH
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(_pipeline_text(**kwargs), encoding="utf-8")
    return path


def _write_env(fabric_dir: Path, *, pipeline: dict[str, str] | None = None,
               ws_id: str = FEAT_WS_ID, lh_id: str = FEAT_LH_ID) -> Path:
    """Write .env with the workspace/lakehouse keys plus any pipeline keys given."""
    lines = [f"FEATURE_WORKSPACE_ID={ws_id}", f"FEATURE_LAKEHOUSE_ID={lh_id}"]
    for binding in pb.PIPELINE_BINDINGS:
        if pipeline and binding["name"] in pipeline:
            lines.append(f"{binding['feature_env_key']}={pipeline[binding['name']]}")
    env_path = fabric_dir.parent.parent / ".env"
    env_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return env_path


def _value_set(fabric_dir: Path, label: str = "feat") -> Path:
    return fabric_dir / "Patterns_Variables.VariableLibrary" / "valueSets" / f"{label}.json"


def _bound(path: Path) -> dict[str, set[str]]:
    found: dict[str, set[str]] = {}
    for located in pb.locate_fields(path.read_text(encoding="utf-8")):
        found.setdefault(located.binding, set()).add(located.value)
    return found


def _group_id(path: Path) -> str:
    activities = json.loads(path.read_text(encoding="utf-8"))["properties"]["activities"]
    refresh = next(a for a in activities if a["type"] == pb.REFRESH_ACTIVITY_TYPE)
    return refresh["typeProperties"]["groupId"]


@pytest.mark.usefixtures("_patch_paths")
class TestDataPipelineRegistry:
    """The registry entry only moves the refresh activity's literal workspace ID."""

    def test_entry_is_registered_for_workspace_rewrites(self):
        from workspace_swap import ITEM_TYPES
        entry = next(t for t in ITEM_TYPES if t["name"] == "DataPipeline")
        assert entry["needs_rewrite"] is True
        assert entry["id_keys"] == ["workspace"]
        assert entry["file_patterns"] == [pb.PIPELINE_FILE_PATTERN]

    def test_repoint_swaps_the_group_workspace_and_keeps_notebook_refs_portable(self, fabric_dir: Path):
        from workspace_swap import repoint_items
        path = _write_pipeline(fabric_dir)
        changed = repoint_items(DEV_WS_ID, DEV_LH_ID, FEAT_WS_ID, FEAT_LH_ID, dry_run=False)
        assert any("Patterns_Load.DataPipeline" in c for c in changed)
        assert _group_id(path) == FEAT_WS_ID
        activities = json.loads(path.read_text(encoding="utf-8"))["properties"]["activities"]
        for notebook in activities[:2]:
            assert notebook["typeProperties"]["workspaceId"] == pb.ZERO_GUID
            assert notebook["typeProperties"]["notebookId"] in NOTEBOOK_LOGICAL_IDS

    def test_repoint_leaves_model_and_connections_to_the_binding_rewrite(self, fabric_dir: Path):
        from workspace_swap import repoint_items
        path = _write_pipeline(fabric_dir)
        repoint_items(DEV_WS_ID, DEV_LH_ID, FEAT_WS_ID, FEAT_LH_ID, dry_run=False)
        assert _bound(path) == {name: {value} for name, value in pb.BASELINE_VALUES.items()}

    def test_repoint_skips_a_pipeline_without_a_native_refresh(self, fabric_dir: Path):
        from workspace_swap import repoint_items
        other = fabric_dir / "Other.DataPipeline" / "pipeline-content.json"
        other.parent.mkdir(parents=True)
        text = json.dumps({"properties": {"activities": [
            {"name": "Run", "type": "TridentNotebook", "typeProperties": {"workspaceId": DEV_WS_ID}},
        ]}})
        other.write_text(text, encoding="utf-8")
        repoint_items(DEV_WS_ID, DEV_LH_ID, FEAT_WS_ID, FEAT_LH_ID, dry_run=False)
        assert other.read_text(encoding="utf-8") == text

    def test_check_ignores_a_pipeline_without_a_native_refresh(self, fabric_dir: Path):
        from workspace_swap import validate_dev_ids_present
        other = fabric_dir / "Other.DataPipeline" / "pipeline-content.json"
        other.parent.mkdir(parents=True)
        other.write_text('{"properties": {"activities": []}}', encoding="utf-8")
        assert validate_dev_ids_present(DEV_WS_ID, DEV_LH_ID) == []

    def test_check_requires_the_dev_group_workspace(self, fabric_dir: Path):
        from workspace_swap import repoint_items, validate_dev_ids_present
        _write_pipeline(fabric_dir)
        assert validate_dev_ids_present(DEV_WS_ID, DEV_LH_ID) == []
        repoint_items(DEV_WS_ID, DEV_LH_ID, FEAT_WS_ID, FEAT_LH_ID, dry_run=False)
        errors = validate_dev_ids_present(DEV_WS_ID, DEV_LH_ID)
        assert any("DataPipeline" in e and "workspace" in e for e in errors)

    def test_validate_no_ids_flags_a_leftover_dev_workspace(self, fabric_dir: Path):
        from workspace_swap import validate_no_ids
        _write_pipeline(fabric_dir)
        warnings = validate_no_ids(DEV_WS_ID, DEV_LH_ID)
        assert any("Patterns_Load.DataPipeline" in w and "workspace" in w for w in warnings)


@pytest.mark.usefixtures("_patch_paths")
class TestResolvePipelineFeatureValues:
    """.env supplies the feature model and connections, but only when a native refresh pipeline exists."""

    def test_returns_nothing_without_a_pipeline(self, fabric_dir: Path):
        from workspace_swap import resolve_pipeline_feature_values
        # No .env at all: nothing to resolve, so nothing may be read or required.
        assert resolve_pipeline_feature_values() == {}

    def test_ignores_a_pipeline_without_a_native_refresh(self, fabric_dir: Path):
        from workspace_swap import resolve_pipeline_feature_values
        other = fabric_dir / "Other.DataPipeline" / "pipeline-content.json"
        other.parent.mkdir(parents=True)
        other.write_text('{"properties": {"activities": []}}', encoding="utf-8")
        assert resolve_pipeline_feature_values() == {}

    def test_reads_the_three_feature_keys(self, fabric_dir: Path):
        from workspace_swap import resolve_pipeline_feature_values
        _write_pipeline(fabric_dir)
        _write_env(fabric_dir, pipeline=FEAT_PIPELINE_VALUES)
        assert resolve_pipeline_feature_values() == FEAT_PIPELINE_VALUES

    @pytest.mark.parametrize("binding", pb.PIPELINE_BINDINGS, ids=lambda b: b["feature_env_key"])
    def test_missing_key_exits_naming_it(self, fabric_dir: Path, binding):
        from workspace_swap import resolve_pipeline_feature_values
        _write_pipeline(fabric_dir)
        values = {k: v for k, v in FEAT_PIPELINE_VALUES.items() if k != binding["name"]}
        _write_env(fabric_dir, pipeline=values)
        with pytest.raises(SystemExit) as exc:
            resolve_pipeline_feature_values()
        assert binding["feature_env_key"] in str(exc.value)

    def test_without_a_env_file_every_key_is_reported(self, fabric_dir: Path):
        from workspace_swap import resolve_pipeline_feature_values
        _write_pipeline(fabric_dir)
        with pytest.raises(SystemExit) as exc:
            resolve_pipeline_feature_values()
        message = str(exc.value)
        assert all(b["feature_env_key"] in message for b in pb.PIPELINE_BINDINGS)

    def test_the_all_zero_sample_value_exits(self, fabric_dir: Path):
        from workspace_swap import resolve_pipeline_feature_values
        _write_pipeline(fabric_dir)
        _write_env(fabric_dir, pipeline={**FEAT_PIPELINE_VALUES, "Semantic model": pb.ZERO_GUID})
        with pytest.raises(SystemExit) as exc:
            resolve_pipeline_feature_values()
        assert "FEATURE_SEMANTIC_MODEL_ID" in str(exc.value)
        assert "all-zero" in str(exc.value)

    @pytest.mark.parametrize("binding", pb.PIPELINE_BINDINGS, ids=lambda b: b["name"])
    def test_a_committed_baseline_exits(self, fabric_dir: Path, binding):
        from workspace_swap import resolve_pipeline_feature_values
        _write_pipeline(fabric_dir)
        _write_env(fabric_dir, pipeline={**FEAT_PIPELINE_VALUES, binding["name"]: binding["baseline"]})
        with pytest.raises(SystemExit) as exc:
            resolve_pipeline_feature_values()
        assert binding["feature_env_key"] in str(exc.value)
        assert "baseline" in str(exc.value)

    def test_a_malformed_guid_exits(self, fabric_dir: Path):
        from workspace_swap import resolve_pipeline_feature_values
        _write_pipeline(fabric_dir)
        _write_env(fabric_dir, pipeline={**FEAT_PIPELINE_VALUES, "Refresh connection": "not-a-guid"})
        with pytest.raises(SystemExit) as exc:
            resolve_pipeline_feature_values()
        assert "FEATURE_REFRESH_CONNECTION_ID" in str(exc.value)

    def test_every_problem_is_reported_at_once(self, fabric_dir: Path):
        from workspace_swap import resolve_pipeline_feature_values
        _write_pipeline(fabric_dir)
        _write_env(fabric_dir, pipeline={"Semantic model": pb.ZERO_GUID, "Notebook connection": "nope"})
        with pytest.raises(SystemExit) as exc:
            resolve_pipeline_feature_values()
        message = str(exc.value)
        assert all(b["feature_env_key"] in message for b in pb.PIPELINE_BINDINGS)


@pytest.mark.usefixtures("_patch_paths")
class TestRepointPipelineBindings:
    def test_sets_every_binding_and_nothing_else(self, fabric_dir: Path):
        from workspace_swap import repoint_pipeline_bindings
        path = _write_pipeline(fabric_dir)
        original = path.read_text(encoding="utf-8")
        changed = repoint_pipeline_bindings(FEAT_PIPELINE_VALUES, dry_run=False)
        assert len(changed) == 1
        expected = original
        for name, baseline in pb.BASELINE_VALUES.items():
            expected = expected.replace(baseline, FEAT_PIPELINE_VALUES[name])
        assert path.read_text(encoding="utf-8") == expected

    def test_preserves_line_endings_byte_for_byte(self, fabric_dir: Path):
        from workspace_swap import repoint_pipeline_bindings
        path = fabric_dir / PIPELINE_RELPATH
        path.parent.mkdir(parents=True)
        original = _pipeline_text().replace("\n", "\r\n").encode("utf-8")
        path.write_bytes(original)
        repoint_pipeline_bindings(FEAT_PIPELINE_VALUES, dry_run=False)
        expected = original
        for name, baseline in pb.BASELINE_VALUES.items():
            expected = expected.replace(baseline.encode(), FEAT_PIPELINE_VALUES[name].encode())
        assert path.read_bytes() == expected

    def test_replaces_whatever_value_is_there(self, fabric_dir: Path):
        from workspace_swap import repoint_pipeline_bindings
        stale = {"Semantic model": pb.ZERO_GUID, "Notebook connection": FEAT_REFRESH_CONN_ID,
                 "Refresh connection": FEAT_MODEL_ID}
        path = _write_pipeline(fabric_dir, values=stale)
        repoint_pipeline_bindings(FEAT_PIPELINE_VALUES, dry_run=False)
        assert _bound(path) == {name: {value} for name, value in FEAT_PIPELINE_VALUES.items()}

    def test_dry_run_reports_without_writing(self, fabric_dir: Path):
        from workspace_swap import repoint_pipeline_bindings
        path = _write_pipeline(fabric_dir)
        original = path.read_bytes()
        changed = repoint_pipeline_bindings(FEAT_PIPELINE_VALUES, dry_run=True)
        assert len(changed) == 1
        assert path.read_bytes() == original

    def test_reports_nothing_when_already_set(self, fabric_dir: Path):
        from workspace_swap import repoint_pipeline_bindings
        _write_pipeline(fabric_dir, values=FEAT_PIPELINE_VALUES)
        assert repoint_pipeline_bindings(FEAT_PIPELINE_VALUES, dry_run=False) == []

    def test_unsupported_shape_exits(self, fabric_dir: Path):
        from workspace_swap import repoint_pipeline_bindings
        _write_pipeline(fabric_dir, refreshes=2)
        with pytest.raises(SystemExit) as exc:
            repoint_pipeline_bindings(FEAT_PIPELINE_VALUES, dry_run=False)
        assert "exactly one" in str(exc.value)


@pytest.mark.usefixtures("_patch_paths")
class TestValidatePipelineBindings:
    def test_clean_when_every_binding_holds_its_expected_value(self, fabric_dir: Path):
        from workspace_swap import validate_pipeline_bindings
        _write_pipeline(fabric_dir)
        assert validate_pipeline_bindings(pb.BASELINE_VALUES) == []

    def test_reports_each_mismatch_with_its_file(self, fabric_dir: Path):
        from workspace_swap import validate_pipeline_bindings
        _write_pipeline(fabric_dir, values=FEAT_PIPELINE_VALUES)
        problems = validate_pipeline_bindings(pb.BASELINE_VALUES)
        text = "\n".join(problems)
        assert "Patterns_Load.DataPipeline" in text
        for name in pb.BASELINE_VALUES:
            assert name in text

    def test_reports_an_unsupported_shape(self, fabric_dir: Path):
        from workspace_swap import validate_pipeline_bindings
        _write_pipeline(fabric_dir, refreshes=2)
        problems = validate_pipeline_bindings(pb.BASELINE_VALUES)
        assert len(problems) == 1
        assert "exactly one" in problems[0]

    def test_nothing_to_report_without_a_pipeline(self, fabric_dir: Path):
        from workspace_swap import validate_pipeline_bindings
        assert validate_pipeline_bindings(pb.BASELINE_VALUES) == []


@pytest.mark.usefixtures("_patch_paths")
class TestSwapFlowsWithPipeline:
    def _swap_to_feature(self, fabric_dir: Path, *, dry_run: bool = False) -> None:
        from workspace_swap import _run_swap_to_feature
        with patch("builtins.input", return_value="YES"):
            _run_swap_to_feature("feat", "feat", _value_set(fabric_dir), DEV_WS_ID, DEV_LH_ID, dry_run=dry_run)

    def _swap_to_dev(self, fabric_dir: Path, *, dry_run: bool = False) -> None:
        from workspace_swap import _run_swap_to_dev
        _run_swap_to_dev("feat", "feat", _value_set(fabric_dir), DEV_WS_ID, DEV_LH_ID, dry_run=dry_run)

    def test_swap_to_feature_rewrites_group_model_and_connections(self, fabric_dir: Path):
        path = _write_pipeline(fabric_dir)
        _write_env(fabric_dir, pipeline=FEAT_PIPELINE_VALUES)
        self._swap_to_feature(fabric_dir)

        assert _group_id(path) == FEAT_WS_ID
        assert _bound(path) == {name: {value} for name, value in FEAT_PIPELINE_VALUES.items()}
        activities = json.loads(path.read_text(encoding="utf-8"))["properties"]["activities"]
        for notebook in activities[:2]:
            assert notebook["typeProperties"]["workspaceId"] == pb.ZERO_GUID
            assert notebook["typeProperties"]["notebookId"] in NOTEBOOK_LOGICAL_IDS

    def test_value_set_still_holds_only_workspace_and_lakehouse(self, fabric_dir: Path):
        _write_pipeline(fabric_dir)
        _write_env(fabric_dir, pipeline=FEAT_PIPELINE_VALUES)
        self._swap_to_feature(fabric_dir)
        data = json.loads(_value_set(fabric_dir).read_text(encoding="utf-8"))
        assert {o["name"] for o in data["variableOverrides"]} == {"target_workspace_id", "target_lakehouse_id"}

    def test_repos_without_a_pipeline_need_no_pipeline_keys(self, fabric_dir: Path):
        _write_env(fabric_dir)
        self._swap_to_feature(fabric_dir)
        assert _value_set(fabric_dir).exists()

    def test_a_pipeline_without_a_native_refresh_needs_no_pipeline_keys(self, fabric_dir: Path):
        other = fabric_dir / "Other.DataPipeline" / "pipeline-content.json"
        other.parent.mkdir(parents=True)
        text = '{"properties": {"activities": []}}'
        other.write_text(text, encoding="utf-8")
        _write_env(fabric_dir)
        self._swap_to_feature(fabric_dir)
        assert other.read_text(encoding="utf-8") == text

    def test_missing_pipeline_key_exits_before_any_write(self, fabric_dir: Path):
        from workspace_swap import _run_swap_to_feature
        path = _write_pipeline(fabric_dir)
        sm_file = fabric_dir / "Test.SemanticModel" / "definition" / "expressions.tmdl"
        before = (path.read_text(encoding="utf-8"), sm_file.read_text(encoding="utf-8"))
        _write_env(fabric_dir, pipeline={k: v for k, v in FEAT_PIPELINE_VALUES.items() if k != "Refresh connection"})
        # No input() patch: reaching the confirmation prompt would fail the test.
        with pytest.raises(SystemExit) as exc:
            _run_swap_to_feature("feat", "feat", _value_set(fabric_dir), DEV_WS_ID, DEV_LH_ID, dry_run=False)
        assert "FEATURE_REFRESH_CONNECTION_ID" in str(exc.value)
        assert not _value_set(fabric_dir).exists()
        assert (path.read_text(encoding="utf-8"), sm_file.read_text(encoding="utf-8")) == before

    def test_unsupported_pipeline_exits_before_any_write(self, fabric_dir: Path):
        from workspace_swap import _run_swap_to_feature
        _write_pipeline(fabric_dir, refreshes=2)
        sm_file = fabric_dir / "Test.SemanticModel" / "definition" / "expressions.tmdl"
        original_sm = sm_file.read_text(encoding="utf-8")
        _write_env(fabric_dir, pipeline=FEAT_PIPELINE_VALUES)
        with pytest.raises(SystemExit) as exc:
            _run_swap_to_feature("feat", "feat", _value_set(fabric_dir), DEV_WS_ID, DEV_LH_ID, dry_run=False)
        assert "exactly one" in str(exc.value)
        assert not _value_set(fabric_dir).exists()
        assert sm_file.read_text(encoding="utf-8") == original_sm

    def test_dry_run_changes_nothing_but_still_validates_env(self, fabric_dir: Path):
        from workspace_swap import _run_swap_to_feature
        path = _write_pipeline(fabric_dir)
        original = path.read_bytes()
        _write_env(fabric_dir, pipeline=FEAT_PIPELINE_VALUES)
        _run_swap_to_feature("feat", "feat", _value_set(fabric_dir), DEV_WS_ID, DEV_LH_ID, dry_run=True)
        assert path.read_bytes() == original
        assert not _value_set(fabric_dir).exists()

        _write_env(fabric_dir)  # pipeline keys gone
        with pytest.raises(SystemExit):
            _run_swap_to_feature("feat", "feat", _value_set(fabric_dir), DEV_WS_ID, DEV_LH_ID, dry_run=True)

    def test_declined_confirmation_leaves_the_pipeline_untouched(self, fabric_dir: Path):
        from workspace_swap import _run_swap_to_feature
        path = _write_pipeline(fabric_dir)
        original = path.read_bytes()
        _write_env(fabric_dir, pipeline=FEAT_PIPELINE_VALUES)
        with patch("builtins.input", return_value="no"):
            with pytest.raises(SystemExit):
                _run_swap_to_feature("feat", "feat", _value_set(fabric_dir), DEV_WS_ID, DEV_LH_ID, dry_run=False)
        assert path.read_bytes() == original

    def test_confirmation_and_summary_list_the_pipeline_values(self, fabric_dir: Path, capsys: pytest.CaptureFixture):
        _write_pipeline(fabric_dir)
        _write_env(fabric_dir, pipeline=FEAT_PIPELINE_VALUES)
        self._swap_to_feature(fabric_dir)
        out = capsys.readouterr().out
        for name, baseline in pb.BASELINE_VALUES.items():
            assert f"{name} : {baseline} → {FEAT_PIPELINE_VALUES[name]}" in out
            assert f"{name}: {baseline} → {FEAT_PIPELINE_VALUES[name]}" in out

    def test_swap_to_dev_restores_baselines_without_reading_env(self, fabric_dir: Path):
        path = _write_pipeline(fabric_dir)
        _write_env(fabric_dir, pipeline=FEAT_PIPELINE_VALUES)
        self._swap_to_feature(fabric_dir)
        (fabric_dir.parent.parent / ".env").unlink()

        self._swap_to_dev(fabric_dir)

        assert _group_id(path) == DEV_WS_ID
        assert _bound(path) == {name: {value} for name, value in pb.BASELINE_VALUES.items()}

    def test_swap_to_dev_restores_baselines_from_any_stale_value(self, fabric_dir: Path):
        path = _write_pipeline(fabric_dir)
        _write_env(fabric_dir, pipeline=FEAT_PIPELINE_VALUES)
        self._swap_to_feature(fabric_dir)
        stale = {"Semantic model": pb.ZERO_GUID, "Notebook connection": FEAT_MODEL_ID,
                 "Refresh connection": FEAT_NOTEBOOK_CONN_ID}
        path.write_text(pb.rewrite(path.read_text(encoding="utf-8"), stale), encoding="utf-8")

        self._swap_to_dev(fabric_dir)

        assert _bound(path) == {name: {value} for name, value in pb.BASELINE_VALUES.items()}

    def test_round_trip_restores_the_original_pipeline(self, fabric_dir: Path):
        path = _write_pipeline(fabric_dir)
        original = path.read_text(encoding="utf-8")
        _write_env(fabric_dir, pipeline=FEAT_PIPELINE_VALUES)
        self._swap_to_feature(fabric_dir)
        assert path.read_text(encoding="utf-8") != original
        self._swap_to_dev(fabric_dir)
        assert path.read_text(encoding="utf-8") == original

    def test_swap_to_dev_dry_run_changes_nothing(self, fabric_dir: Path):
        path = _write_pipeline(fabric_dir)
        _write_env(fabric_dir, pipeline=FEAT_PIPELINE_VALUES)
        self._swap_to_feature(fabric_dir)
        swapped = path.read_bytes()
        self._swap_to_dev(fabric_dir, dry_run=True)
        assert path.read_bytes() == swapped
        assert _value_set(fabric_dir).exists()

    def test_swap_to_dev_exits_before_reverting_when_the_pipeline_is_unsupported(self, fabric_dir: Path):
        path = _write_pipeline(fabric_dir)
        _write_env(fabric_dir, pipeline=FEAT_PIPELINE_VALUES)
        self._swap_to_feature(fabric_dir)
        path.write_text('{"properties": {"activities": [{"type": "PBISemanticModelRefresh"', encoding="utf-8")
        sm_file = fabric_dir / "Test.SemanticModel" / "definition" / "expressions.tmdl"
        swapped_sm = sm_file.read_text(encoding="utf-8")

        with pytest.raises(SystemExit) as exc:
            self._swap_to_dev(fabric_dir)

        assert "not valid JSON" in str(exc.value)
        assert sm_file.read_text(encoding="utf-8") == swapped_sm
        assert _value_set(fabric_dir).exists()


@pytest.mark.usefixtures("_patch_paths")
class TestCheckReadyWithPipeline:
    def _check(self, capsys: pytest.CaptureFixture) -> str:
        from workspace_swap import _run_check_ready
        _run_check_ready()
        return capsys.readouterr().out

    def _failing_check(self, capsys: pytest.CaptureFixture) -> str:
        from workspace_swap import _run_check_ready
        with pytest.raises(SystemExit) as exc:
            _run_check_ready()
        assert exc.value.code == 1
        return capsys.readouterr().out

    def test_passes_without_a_pipeline(self, fabric_dir: Path, capsys: pytest.CaptureFixture):
        out = self._check(capsys)
        assert "no pipeline with a native refresh activity" in out
        assert "CHECK PASSED" in out

    def test_passes_with_baseline_values(self, fabric_dir: Path, capsys: pytest.CaptureFixture):
        _write_pipeline(fabric_dir)
        out = self._check(capsys)
        assert "semantic model and connections use baseline values" in out
        assert "CHECK PASSED" in out

    def test_fails_when_feature_values_remain(self, fabric_dir: Path, capsys: pytest.CaptureFixture):
        _write_pipeline(fabric_dir, values=FEAT_PIPELINE_VALUES)
        out = self._failing_check(capsys)
        for name in pb.BASELINE_VALUES:
            assert name in out
        assert "CHECK FAILED" in out

    def test_fails_when_only_one_binding_differs(self, fabric_dir: Path, capsys: pytest.CaptureFixture):
        _write_pipeline(fabric_dir, values={**pb.BASELINE_VALUES, "Refresh connection": FEAT_REFRESH_CONN_ID})
        out = self._failing_check(capsys)
        assert "Refresh connection" in out
        assert "Semantic model (" not in out

    def test_fails_when_the_group_workspace_is_not_dev(self, fabric_dir: Path, capsys: pytest.CaptureFixture):
        _write_pipeline(fabric_dir, workspace=FEAT_WS_ID)
        out = self._failing_check(capsys)
        assert "DataPipeline" in out

    def test_fails_without_exactly_one_native_activity(self, fabric_dir: Path, capsys: pytest.CaptureFixture):
        _write_pipeline(fabric_dir, refreshes=2)
        out = self._failing_check(capsys)
        assert "expected exactly one PBISemanticModelRefresh activity, found 2" in out

    def test_fails_when_a_notebook_activity_has_no_connection(self, fabric_dir: Path, capsys: pytest.CaptureFixture):
        path = _write_pipeline(fabric_dir)
        doc = json.loads(path.read_text(encoding="utf-8"))
        del doc["properties"]["activities"][1]["externalReferences"]
        path.write_text(json.dumps(doc, indent=2), encoding="utf-8")
        out = self._failing_check(capsys)
        assert "Validate_Patterns_Data" in out

    def test_fails_when_a_binding_is_an_expression(self, fabric_dir: Path, capsys: pytest.CaptureFixture):
        path = _write_pipeline(fabric_dir)
        text = path.read_text(encoding="utf-8").replace(pb.SEMANTIC_MODEL_BASELINE_ID, "@pipeline().parameters.model")
        path.write_text(text, encoding="utf-8")
        out = self._failing_check(capsys)
        assert "not a GUID" in out

