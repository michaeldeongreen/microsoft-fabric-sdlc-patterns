"""Tests for scripts/deploy_bulk.py.

Covers the pure functions extracted from the bulk-import deployment script.
The orchestration in main() and the network-dependent poll loop are not
unit-tested here — those are validated end-to-end via the deploy workflows.
"""

from __future__ import annotations

import base64
import pathlib
from unittest import mock

import pytest

from deploy_bulk import (
    BULK_PARAMETER_FILENAME,
    DEPENDENCY_TYPES,
    EXCLUDED_FILES,
    SUBSTITUTABLE_EXTENSIONS,
    BulkConfig,
    SubstitutionRule,
    acquire_token,
    apply_substitutions,
    build_definition_parts,
    check_per_item_status,
    extract_item_ids,
    find_variable_library_id,
    interpret_post_response,
    item_display_name_of,
    item_type_of,
    load_bulk_config,
    partition_dependencies,
    resolve_active_value_set,
    resolve_dynamic_value,
)


# ---------- build_definition_parts ----------


def _make_item_file(repo_dir: pathlib.Path, item_path: str, content: bytes = b"x") -> None:
    """Create a file under repo_dir/<item_path>, ensuring parent dirs exist."""
    full = repo_dir / item_path
    full.parent.mkdir(parents=True, exist_ok=True)
    full.write_bytes(content)


def test_build_definition_parts_happy_path(tmp_path: pathlib.Path) -> None:
    _make_item_file(tmp_path, "MyItem.Notebook/notebook-content.py", b"print('hi')")
    parts = build_definition_parts(tmp_path)
    assert len(parts) == 1
    assert parts[0]["path"] == "/MyItem.Notebook/notebook-content.py"
    assert parts[0]["payloadType"] == "InlineBase64"
    assert base64.b64decode(parts[0]["payload"]) == b"print('hi')"


def test_build_definition_parts_excludes_gitkeep(tmp_path: pathlib.Path) -> None:
    (tmp_path / ".gitkeep").write_bytes(b"")
    _make_item_file(tmp_path, "MyItem.Notebook/notebook-content.py")
    parts = build_definition_parts(tmp_path)
    paths = [p["path"] for p in parts]
    assert "/.gitkeep" not in paths
    assert "/MyItem.Notebook/notebook-content.py" in paths


def test_build_definition_parts_excludes_parameter_yml(tmp_path: pathlib.Path) -> None:
    (tmp_path / "parameter.yml").write_bytes(b"find_replace: []")
    _make_item_file(tmp_path, "MyItem.Notebook/notebook-content.py")
    parts = build_definition_parts(tmp_path)
    paths = [p["path"] for p in parts]
    assert "/parameter.yml" not in paths


def test_build_definition_parts_excludes_bulk_parameter_yml(tmp_path: pathlib.Path) -> None:
    """bulk-parameter.yml is bulk's own config and must never be sent to Fabric."""
    (tmp_path / "bulk-parameter.yml").write_bytes(b"substitutions: []")
    _make_item_file(tmp_path, "MyItem.Notebook/notebook-content.py")
    parts = build_definition_parts(tmp_path)
    paths = [p["path"] for p in parts]
    assert "/bulk-parameter.yml" not in paths


def test_build_definition_parts_excludes_root_level_files(tmp_path: pathlib.Path) -> None:
    """Anything directly under repository_directory (not in *.<Type>/) is skipped."""
    (tmp_path / "README.md").write_bytes(b"# notes")
    _make_item_file(tmp_path, "MyItem.Notebook/notebook-content.py")
    parts = build_definition_parts(tmp_path)
    paths = [p["path"] for p in parts]
    assert "/README.md" not in paths
    assert "/MyItem.Notebook/notebook-content.py" in paths


def test_build_definition_parts_walks_recursively(tmp_path: pathlib.Path) -> None:
    _make_item_file(tmp_path, "Item.Notebook/.platform", b"{}")
    _make_item_file(tmp_path, "Item.Notebook/notebook-content.py", b"x")
    _make_item_file(
        tmp_path, "Item.SemanticModel/definition/tables/t.tmdl", b"table t"
    )
    parts = build_definition_parts(tmp_path)
    assert len(parts) == 3
    paths = sorted(p["path"] for p in parts)
    assert paths == [
        "/Item.Notebook/.platform",
        "/Item.Notebook/notebook-content.py",
        "/Item.SemanticModel/definition/tables/t.tmdl",
    ]


def test_build_definition_parts_empty_repo_exits(tmp_path: pathlib.Path) -> None:
    with pytest.raises(SystemExit) as exc:
        build_definition_parts(tmp_path)
    assert "No item definition files found" in str(exc.value)


def test_build_definition_parts_missing_dir_exits(tmp_path: pathlib.Path) -> None:
    with pytest.raises(SystemExit) as exc:
        build_definition_parts(tmp_path / "does_not_exist")
    assert "Repository directory not found" in str(exc.value)


def test_excluded_files_constant_includes_known_excludes() -> None:
    """Sanity check on the constant — protects against accidental edits."""
    assert "parameter.yml" in EXCLUDED_FILES
    assert "bulk-parameter.yml" in EXCLUDED_FILES
    assert ".gitkeep" in EXCLUDED_FILES


def test_bulk_parameter_filename_constant() -> None:
    """The filename constant must match the file we exclude and the file we read."""
    assert BULK_PARAMETER_FILENAME == "bulk-parameter.yml"
    assert BULK_PARAMETER_FILENAME in EXCLUDED_FILES


# ---------- load_bulk_config ----------


def test_load_bulk_config_missing_file_returns_empty(tmp_path: pathlib.Path) -> None:
    """Missing file is not an error — bulk path stays usable without config."""
    config = load_bulk_config(tmp_path / "does_not_exist.yml")
    assert config == BulkConfig()
    assert config.substitutions == ()
    assert config.variable_library_active_value_set is None


def test_load_bulk_config_empty_file_returns_empty(tmp_path: pathlib.Path) -> None:
    """An empty YAML file parses to None and is treated as no config."""
    path = tmp_path / "bulk-parameter.yml"
    path.write_text("", encoding="utf-8")
    assert load_bulk_config(path) == BulkConfig()


def test_load_bulk_config_full_happy_path(tmp_path: pathlib.Path) -> None:
    path = tmp_path / "bulk-parameter.yml"
    path.write_text(
        """
substitutions:
  - find: "abc"
    replace_with: "$workspace.$id"
    item_types: [Notebook, SemanticModel]
  - find: "def"
    replace_with: "$items.Lakehouse.LH.$id"
    item_types: [Notebook]

variable_library:
  active_value_set: "$environment"
""",
        encoding="utf-8",
    )
    config = load_bulk_config(path)
    assert len(config.substitutions) == 2
    assert config.substitutions[0] == SubstitutionRule(
        find="abc",
        replace_with="$workspace.$id",
        item_types=frozenset({"Notebook", "SemanticModel"}),
    )
    assert config.substitutions[1] == SubstitutionRule(
        find="def",
        replace_with="$items.Lakehouse.LH.$id",
        item_types=frozenset({"Notebook"}),
    )
    assert config.variable_library_active_value_set == "$environment"


def test_load_bulk_config_substitutions_only(tmp_path: pathlib.Path) -> None:
    path = tmp_path / "bulk-parameter.yml"
    path.write_text(
        """
substitutions:
  - find: "abc"
    replace_with: "xyz"
    item_types: [Notebook]
""",
        encoding="utf-8",
    )
    config = load_bulk_config(path)
    assert len(config.substitutions) == 1
    assert config.variable_library_active_value_set is None


def test_load_bulk_config_variable_library_only(tmp_path: pathlib.Path) -> None:
    path = tmp_path / "bulk-parameter.yml"
    path.write_text(
        """
variable_library:
  active_value_set: "Test"
""",
        encoding="utf-8",
    )
    config = load_bulk_config(path)
    assert config.substitutions == ()
    assert config.variable_library_active_value_set == "Test"


def test_load_bulk_config_variable_library_null_active_value_set(
    tmp_path: pathlib.Path,
) -> None:
    """Explicit null in YAML is the documented way to disable activation."""
    path = tmp_path / "bulk-parameter.yml"
    path.write_text(
        """
variable_library:
  active_value_set: null
""",
        encoding="utf-8",
    )
    assert load_bulk_config(path).variable_library_active_value_set is None


def test_load_bulk_config_top_level_not_a_mapping_raises(tmp_path: pathlib.Path) -> None:
    path = tmp_path / "bulk-parameter.yml"
    path.write_text("- just\n- a\n- list\n", encoding="utf-8")
    with pytest.raises(ValueError, match="YAML mapping at the top level"):
        load_bulk_config(path)


def test_load_bulk_config_substitution_missing_required_key_raises(
    tmp_path: pathlib.Path,
) -> None:
    path = tmp_path / "bulk-parameter.yml"
    path.write_text(
        """
substitutions:
  - find: "abc"
    item_types: [Notebook]
""",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="missing required key 'replace_with'"):
        load_bulk_config(path)


def test_load_bulk_config_substitution_not_a_mapping_raises(tmp_path: pathlib.Path) -> None:
    path = tmp_path / "bulk-parameter.yml"
    path.write_text(
        """
substitutions:
  - just-a-string
""",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match=r"substitutions\[0\] must be a mapping"):
        load_bulk_config(path)


def test_load_bulk_config_item_types_not_a_string_list_raises(tmp_path: pathlib.Path) -> None:
    path = tmp_path / "bulk-parameter.yml"
    path.write_text(
        """
substitutions:
  - find: "abc"
    replace_with: "xyz"
    item_types: "Notebook"
""",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="item_types must be a list of strings"):
        load_bulk_config(path)


def test_load_bulk_config_variable_library_not_a_mapping_raises(
    tmp_path: pathlib.Path,
) -> None:
    path = tmp_path / "bulk-parameter.yml"
    path.write_text("variable_library: 'not-a-mapping'\n", encoding="utf-8")
    with pytest.raises(ValueError, match="variable_library must be a mapping"):
        load_bulk_config(path)


def test_load_bulk_config_active_value_set_wrong_type_raises(tmp_path: pathlib.Path) -> None:
    path = tmp_path / "bulk-parameter.yml"
    path.write_text(
        """
variable_library:
  active_value_set: 42
""",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="active_value_set must be a string or null"):
        load_bulk_config(path)


def test_load_bulk_config_real_repo_file_parses() -> None:
    """Smoke test: the actual data/fabric/bulk-parameter.yml shipped in the repo loads."""
    repo_root = pathlib.Path(__file__).resolve().parents[1]
    path = repo_root / "data" / "fabric" / "bulk-parameter.yml"
    if not path.exists():
        pytest.skip("data/fabric/bulk-parameter.yml not present in this checkout")
    config = load_bulk_config(path)
    assert isinstance(config, BulkConfig)
    assert len(config.substitutions) >= 1
    assert config.variable_library_active_value_set is not None


# ---------- check_per_item_status ----------


def test_check_per_item_status_all_succeeded(capsys: pytest.CaptureFixture) -> None:
    result = {
        "importItemDefinitionsDetails": [
            {"itemDisplayName": "X", "itemType": "Notebook", "operationStatus": "Succeeded"},
            {"itemDisplayName": "Y", "itemType": "Report", "operationStatus": "Succeeded"},
        ]
    }
    check_per_item_status(result)  # should not raise
    assert "All 2 items deployed successfully" in capsys.readouterr().out


def test_check_per_item_status_one_failed_exits() -> None:
    result = {
        "importItemDefinitionsDetails": [
            {"itemDisplayName": "X", "itemType": "Notebook", "operationStatus": "Succeeded"},
            {"itemDisplayName": "Y", "itemType": "Report", "operationStatus": "Failed"},
        ]
    }
    with pytest.raises(SystemExit) as exc:
        check_per_item_status(result)
    assert "1 item(s) failed" in str(exc.value)
    assert "Y (Report): Failed" in str(exc.value)


def test_check_per_item_status_succeeded_despite_failures_exits() -> None:
    """SucceededDespiteFailures is treated as a failure for build-fail purposes."""
    result = {
        "importItemDefinitionsDetails": [
            {
                "itemDisplayName": "Z",
                "itemType": "Notebook",
                "operationStatus": "SucceededDespiteFailures",
            },
        ]
    }
    with pytest.raises(SystemExit) as exc:
        check_per_item_status(result)
    assert "1 item(s) failed" in str(exc.value)
    assert "SucceededDespiteFailures" in str(exc.value)


def test_check_per_item_status_missing_details_exits() -> None:
    with pytest.raises(SystemExit) as exc:
        check_per_item_status({})
    assert "no importItemDefinitionsDetails" in str(exc.value)


# ---------- interpret_post_response ----------


def test_interpret_post_response_sync_200() -> None:
    body = {"importItemDefinitionsDetails": [{"itemId": "abc"}]}
    action = interpret_post_response(200, body, {})
    assert action == ("sync", body)


def test_interpret_post_response_async_202() -> None:
    headers = {"x-ms-operation-id": "op-123", "Retry-After": "45"}
    action = interpret_post_response(202, {}, headers)
    assert action == ("async", "op-123", 45)


def test_interpret_post_response_async_202_default_retry_after() -> None:
    """When Retry-After is missing, fall back to POLL_FALLBACK_SECONDS (30)."""
    headers = {"x-ms-operation-id": "op-456"}
    action = interpret_post_response(202, {}, headers)
    assert action == ("async", "op-456", 30)


def test_interpret_post_response_missing_op_id() -> None:
    """A 202 response without x-ms-operation-id is treated as malformed."""
    action = interpret_post_response(202, {}, {})
    assert action == ("missing_op_id",)


def test_interpret_post_response_unexpected_status() -> None:
    action = interpret_post_response(500, {}, {})
    assert action == ("error", 500)


# ---------- acquire_token ----------


def test_acquire_token_success(capsys: pytest.CaptureFixture) -> None:
    fake_resp = mock.Mock(status_code=200)
    fake_resp.json.return_value = {"access_token": "fake-token-xyz"}
    with mock.patch("deploy_bulk.requests.post", return_value=fake_resp) as post:
        token = acquire_token("tenant", "client", "secret")
    assert token == "fake-token-xyz"
    # Verify the call was shaped correctly
    post.assert_called_once()
    call_kwargs = post.call_args.kwargs
    assert call_kwargs["data"]["grant_type"] == "client_credentials"
    assert call_kwargs["data"]["scope"] == "https://api.fabric.microsoft.com/.default"
    # Workflow log mask was emitted
    assert "::add-mask::fake-token-xyz" in capsys.readouterr().out


def test_acquire_token_failure_exits() -> None:
    fake_resp = mock.Mock(status_code=401, text="Unauthorized")
    with mock.patch("deploy_bulk.requests.post", return_value=fake_resp):
        with pytest.raises(SystemExit) as exc:
            acquire_token("tenant", "client", "secret")
    assert "Token acquisition failed" in str(exc.value)
    assert "401" in str(exc.value)


# ---------- Phase 2 helpers: item_type_of / item_display_name_of ----------


@pytest.mark.parametrize("path,expected", [
    ("/Foo.Notebook/notebook-content.py", "Notebook"),
    ("/PatternsLakehouse.Lakehouse/.platform", "Lakehouse"),
    ("/My.Item.SemanticModel/definition/model.tmdl", "SemanticModel"),
    ("Foo.Notebook/x.py", "Notebook"),  # tolerates missing leading slash
])
def test_item_type_of_extracts_type(path: str, expected: str) -> None:
    assert item_type_of(path) == expected


@pytest.mark.parametrize("path", [
    "/no-extension-folder/file.py",
    "/just-a-root-file.py",
    "",
    "/",
])
def test_item_type_of_returns_none_for_non_conforming(path: str) -> None:
    assert item_type_of(path) is None


@pytest.mark.parametrize("path,expected", [
    ("/Foo.Notebook/x.py", "Foo"),
    ("/PatternsLakehouse.Lakehouse/.platform", "PatternsLakehouse"),
    ("/My.Item.SemanticModel/x", "My.Item"),  # multi-dot name preserved
])
def test_item_display_name_of_extracts_name(path: str, expected: str) -> None:
    assert item_display_name_of(path) == expected


def test_item_display_name_of_returns_none_for_non_conforming() -> None:
    assert item_display_name_of("/no-extension-folder/file.py") is None
    assert item_display_name_of("") is None


# ---------- partition_dependencies ----------


def test_partition_dependencies_splits_correctly() -> None:
    parts = [
        {"path": "/A.Lakehouse/.platform"},
        {"path": "/B.Notebook/x.py"},
        {"path": "/C.Ontology/definition.json"},
        {"path": "/D.SemanticModel/model.tmdl"},
    ]
    dependencies, remaining = partition_dependencies(parts)
    assert [p["path"] for p in dependencies] == ["/A.Lakehouse/.platform", "/C.Ontology/definition.json"]
    assert [p["path"] for p in remaining] == ["/B.Notebook/x.py", "/D.SemanticModel/model.tmdl"]


def test_partition_dependencies_empty_input() -> None:
    assert partition_dependencies([]) == ([], [])


def test_partition_dependencies_all_dependencies() -> None:
    parts = [{"path": "/A.Lakehouse/.platform"}, {"path": "/B.Ontology/x"}]
    dependencies, remaining = partition_dependencies(parts)
    assert len(dependencies) == 2
    assert remaining == []


def test_partition_dependencies_no_dependencies() -> None:
    parts = [{"path": "/A.Notebook/x.py"}, {"path": "/B.Report/y.json"}]
    dependencies, remaining = partition_dependencies(parts)
    assert dependencies == []
    assert len(remaining) == 2


def test_dependency_types_constant() -> None:
    """Sanity check on the constant — protects against accidental edits."""
    assert DEPENDENCY_TYPES == ("Lakehouse", "Ontology")


# ---------- extract_item_ids ----------


def test_extract_item_ids_happy_path() -> None:
    body = {
        "importItemDefinitionsDetails": [
            {"itemType": "Lakehouse", "itemDisplayName": "LH", "itemId": "id-1",
             "operationStatus": "Succeeded"},
            {"itemType": "Notebook", "itemDisplayName": "NB", "itemId": "id-2",
             "operationStatus": "Succeeded"},
        ]
    }
    assert extract_item_ids(body) == {
        ("Lakehouse", "LH"): "id-1",
        ("Notebook", "NB"): "id-2",
    }


def test_extract_item_ids_empty_body() -> None:
    assert extract_item_ids({}) == {}
    assert extract_item_ids({"importItemDefinitionsDetails": []}) == {}


def test_extract_item_ids_skips_entries_with_missing_fields() -> None:
    body = {
        "importItemDefinitionsDetails": [
            {"itemType": "Lakehouse", "itemDisplayName": "LH", "itemId": "id-1"},
            {"itemType": "Notebook", "itemDisplayName": "NB"},  # no itemId
            {"itemDisplayName": "Other", "itemId": "id-3"},      # no itemType
        ]
    }
    assert extract_item_ids(body) == {("Lakehouse", "LH"): "id-1"}


# ---------- resolve_dynamic_value ----------


def test_resolve_dynamic_value_workspace() -> None:
    assert resolve_dynamic_value("$workspace.$id", "ws-123", {}) == "ws-123"


def test_resolve_dynamic_value_items() -> None:
    item_map = {("Lakehouse", "LH"): "lh-id"}
    assert resolve_dynamic_value("$items.Lakehouse.LH.$id", "ws", item_map) == "lh-id"


def test_resolve_dynamic_value_no_placeholders_passthrough() -> None:
    assert resolve_dynamic_value("plain-value", "ws", {}) == "plain-value"


def test_resolve_dynamic_value_mixed_string() -> None:
    """Placeholders may appear inside larger strings (defensive — the repo
    doesn't currently use this but the resolver should still handle it)."""
    item_map = {("Lakehouse", "LH"): "lh-id"}
    template = "ws=$workspace.$id;lh=$items.Lakehouse.LH.$id"
    assert resolve_dynamic_value(template, "ws-123", item_map) == "ws=ws-123;lh=lh-id"


def test_resolve_dynamic_value_unresolved_items_raises() -> None:
    with pytest.raises(ValueError, match="Unresolved placeholder"):
        resolve_dynamic_value("$items.Lakehouse.MissingName.$id", "ws", {})


def test_resolve_dynamic_value_only_workspace_resolved_no_items() -> None:
    """When item_id_map is empty, $workspace.$id still resolves cleanly."""
    assert resolve_dynamic_value("$workspace.$id", "ws-456", {}) == "ws-456"


# ---------- apply_substitutions ----------


def _make_part(path: str, content: str) -> dict:
    return {
        "path": path,
        "payload": base64.b64encode(content.encode("utf-8")).decode("ascii"),
        "payloadType": "InlineBase64",
    }


def _payload_text(part: dict) -> str:
    return base64.b64decode(part["payload"]).decode("utf-8")


def test_apply_substitutions_no_rules_passes_through() -> None:
    parts = [_make_part("/A.Notebook/x.py", "abc")]
    out = apply_substitutions(parts, (), "ws", {})
    assert out == parts


def test_apply_substitutions_substitutes_when_item_type_matches() -> None:
    rules = (
        SubstitutionRule(
            find="DEV-LAKEHOUSE",
            replace_with="$items.Lakehouse.LH.$id",
            item_types=frozenset({"Notebook"}),
        ),
    )
    parts = [_make_part("/A.Notebook/x.py", "lakehouse=DEV-LAKEHOUSE")]
    out = apply_substitutions(parts, rules, "ws", {("Lakehouse", "LH"): "lh-id"})
    assert _payload_text(out[0]) == "lakehouse=lh-id"


def test_apply_substitutions_skips_when_item_type_doesnt_match() -> None:
    rules = (
        SubstitutionRule(
            find="DEV-LAKEHOUSE",
            replace_with="lh-id",
            item_types=frozenset({"Notebook"}),  # rule scoped to Notebook only
        ),
    )
    parts = [_make_part("/A.SemanticModel/x.tmdl", "lakehouse=DEV-LAKEHOUSE")]
    out = apply_substitutions(parts, rules, "ws", {})
    assert _payload_text(out[0]) == "lakehouse=DEV-LAKEHOUSE"  # unchanged


def test_apply_substitutions_skips_non_text_extensions() -> None:
    """Files outside SUBSTITUTABLE_EXTENSIONS pass through as-is."""
    rules = (
        SubstitutionRule(
            find="abc",
            replace_with="xyz",
            item_types=frozenset({"Report"}),
        ),
    )
    parts = [_make_part("/R.Report/StaticResources/img.png", "abc")]
    out = apply_substitutions(parts, rules, "ws", {})
    assert _payload_text(out[0]) == "abc"  # unchanged


def test_apply_substitutions_multiple_rules_applied_in_order() -> None:
    rules = (
        SubstitutionRule(find="A", replace_with="X", item_types=frozenset({"Notebook"})),
        SubstitutionRule(find="B", replace_with="Y", item_types=frozenset({"Notebook"})),
    )
    parts = [_make_part("/N.Notebook/x.py", "AABB")]
    out = apply_substitutions(parts, rules, "ws", {})
    assert _payload_text(out[0]) == "XXYY"


def test_apply_substitutions_preserves_non_matching_parts() -> None:
    rules = (
        SubstitutionRule(find="abc", replace_with="xyz", item_types=frozenset({"Notebook"})),
    )
    parts = [
        _make_part("/A.Notebook/x.py", "abc"),
        _make_part("/B.SemanticModel/m.tmdl", "abc"),  # rule doesn't apply
    ]
    out = apply_substitutions(parts, rules, "ws", {})
    assert _payload_text(out[0]) == "xyz"
    assert _payload_text(out[1]) == "abc"


def test_apply_substitutions_workspace_placeholder() -> None:
    rules = (
        SubstitutionRule(
            find="DEV-WS",
            replace_with="$workspace.$id",
            item_types=frozenset({"Notebook"}),
        ),
    )
    parts = [_make_part("/A.Notebook/x.py", "ws=DEV-WS")]
    out = apply_substitutions(parts, rules, "target-ws-id", {})
    assert _payload_text(out[0]) == "ws=target-ws-id"


def test_apply_substitutions_no_change_returns_same_part_object() -> None:
    """If a rule applies but the find string isn't present, no re-encode."""
    rules = (
        SubstitutionRule(find="not-present", replace_with="x", item_types=frozenset({"Notebook"})),
    )
    parts = [_make_part("/A.Notebook/x.py", "hello")]
    out = apply_substitutions(parts, rules, "ws", {})
    # Same part object passed through (identity check is intentional)
    assert out[0] is parts[0]


def test_substitutable_extensions_constant() -> None:
    """Sanity check on the constant — protects against accidental edits."""
    assert ".json" in SUBSTITUTABLE_EXTENSIONS
    assert ".py" in SUBSTITUTABLE_EXTENSIONS
    assert ".tmdl" in SUBSTITUTABLE_EXTENSIONS
    assert ".platform" in SUBSTITUTABLE_EXTENSIONS
    assert ".png" not in SUBSTITUTABLE_EXTENSIONS


# ---------- resolve_active_value_set ----------


def test_resolve_active_value_set_environment_placeholder() -> None:
    assert resolve_active_value_set("$environment", "Test") == "Test"
    assert resolve_active_value_set("$environment", "Prod") == "Prod"


def test_resolve_active_value_set_literal_passthrough() -> None:
    assert resolve_active_value_set("Test", "Prod") == "Test"


def test_resolve_active_value_set_none_passthrough() -> None:
    assert resolve_active_value_set(None, "Test") is None


# ---------- find_variable_library_id ----------


def test_find_variable_library_id_single_match() -> None:
    item_map = {
        ("Lakehouse", "LH"): "lh-id",
        ("VariableLibrary", "VL"): "vl-id",
        ("Notebook", "NB"): "nb-id",
    }
    assert find_variable_library_id(item_map) == "vl-id"


def test_find_variable_library_id_none_present() -> None:
    item_map = {("Lakehouse", "LH"): "lh-id"}
    assert find_variable_library_id(item_map) is None


def test_find_variable_library_id_empty_map() -> None:
    assert find_variable_library_id({}) is None


def test_find_variable_library_id_multiple_raises() -> None:
    item_map = {
        ("VariableLibrary", "VL1"): "id-1",
        ("VariableLibrary", "VL2"): "id-2",
    }
    with pytest.raises(ValueError, match="Expected exactly one VariableLibrary"):
        find_variable_library_id(item_map)


# ---------- activate_variable_library_value_set ----------


def test_activate_variable_library_value_set_happy_path(
    capsys: pytest.CaptureFixture,
) -> None:
    fake_resp = mock.Mock(status_code=200, text="{}")
    headers = {"Authorization": "Bearer x", "Content-Type": "application/json"}
    with mock.patch("deploy_bulk.requests.patch", return_value=fake_resp) as patch:
        from deploy_bulk import activate_variable_library_value_set
        activate_variable_library_value_set(
            workspace_id="ws-id", library_id="vl-id",
            value_set_name="Test", headers=headers,
        )
    patch.assert_called_once()
    call_args = patch.call_args
    url = call_args.args[0]
    assert url.endswith("/v1/workspaces/ws-id/variableLibraries/vl-id")
    body = call_args.kwargs["json"]
    assert body == {"properties": {"activeValueSetName": "Test"}}
    assert call_args.kwargs["headers"] is headers
    out = capsys.readouterr().out
    assert "Test" in out
    assert "vl-id" in out


def test_activate_variable_library_value_set_failure_exits() -> None:
    fake_resp = mock.Mock(status_code=400, text="Bad value set name")
    headers = {"Authorization": "Bearer x"}
    with mock.patch("deploy_bulk.requests.patch", return_value=fake_resp):
        from deploy_bulk import activate_variable_library_value_set
        with pytest.raises(SystemExit) as exc:
            activate_variable_library_value_set(
                workspace_id="ws", library_id="vl",
                value_set_name="Bad", headers=headers,
            )
    assert "Failed to set active value set" in str(exc.value)
    assert "400" in str(exc.value)
