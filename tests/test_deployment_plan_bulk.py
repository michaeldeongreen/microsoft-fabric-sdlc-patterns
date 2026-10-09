"""Validate the isolated bulk plan reader without credentials or Fabric calls."""

from __future__ import annotations

import json
from pathlib import Path
from uuid import UUID

import pytest
import yaml

from deployment_plan_bulk import MAX_GROUPS, MAX_PLAN_BYTES, PLAN_SCHEMA, load_schedule, validate_guid

REPO_ROOT = Path(__file__).resolve().parents[1]
SCOPE = ["Lakehouse", "Ontology", "VariableLibrary", "Notebook", "SemanticModel", "Report", "DataAgent"]


def _item(root: Path, name: str, item_type: str, number: int) -> str:
    logical_id = str(UUID(int=number))
    directory = root / f"{name}.{item_type}"
    directory.mkdir(parents=True, exist_ok=True)
    (directory / ".platform").write_text(json.dumps({
        "metadata": {"type": item_type, "displayName": name},
        "config": {"logicalId": logical_id},
    }), encoding="utf-8")
    return logical_id


def _plan(root: Path, groups: list[dict[str, object]]) -> Path:
    path = root / "plan.yml"
    path.write_text(yaml.safe_dump({
        "$schema": PLAN_SCHEMA, "version": "1.0.0", "groups": groups,
    }), encoding="utf-8")
    return path


def test_real_plan_combines_only_independent_ready_groups() -> None:
    schedule = load_schedule(
        REPO_ROOT / "data" / "fabric",
        REPO_ROOT / "data" / "fabric" / "DeploymentPlan.DeploymentPlan" / "plan.yml",
        SCOPE,
    )
    assert [[group.name for group in batch] for batch in schedule.batches] == [
        ["Lakehouse_Group"], ["Ontology_Group", "SemanticModel_Group"], ["DataAgent_Group"],
    ]
    assert {item.selector for item in schedule.remaining_items} == {
        "Patterns_Report.Report", "Patterns_Variables.VariableLibrary",
        "Import_Patterns_Data.Notebook", "Patterns_Demo.Notebook", "Patterns_Patients_Data.Notebook",
    }
    assert "DeploymentPlan" not in schedule.item_types
    assert schedule.summary()["adapter"] == "isolated-bulk-ordering-only"


def test_grouping_is_not_yaml_position_and_changes_with_dependencies(tmp_path: Path) -> None:
    logical_ids = [_item(tmp_path, name, "Notebook", i + 1) for i, name in enumerate(("A", "B", "C", "D"))]
    groups = [
        {"name": "A", "logicalId": logical_ids[0]},
        {"name": "B", "logicalId": logical_ids[1], "dependsOn": [{"groupName": "A"}]},
        {"name": "C", "logicalId": logical_ids[2], "dependsOn": [{"groupName": "a"}]},
        {"name": "D", "logicalId": logical_ids[3], "dependsOn": [{"groupName": "C"}]},
    ]
    forward = load_schedule(tmp_path, _plan(tmp_path, groups), ["Notebook"])
    backward = load_schedule(tmp_path, _plan(tmp_path, list(reversed(groups))), ["Notebook"])
    assert forward.batches == backward.batches
    assert [[group.name for group in batch] for batch in forward.batches] == [["A"], ["B", "C"], ["D"]]
    groups[2]["dependsOn"] = [{"groupName": "B"}]
    changed = load_schedule(tmp_path, _plan(tmp_path, groups), ["Notebook"])
    assert [[group.name for group in batch] for batch in changed.batches] == [["A"], ["B"], ["C"], ["D"]]


@pytest.mark.parametrize("scope", [[], ["Notebook", "Notebook"], [" Notebook"], ["Notebook", ""]])
def test_scope_is_explicit_and_unambiguous(tmp_path: Path, scope: list[str]) -> None:
    _item(tmp_path, "Notebook", "Notebook", 1)
    with pytest.raises(ValueError, match="scope"):
        load_schedule(tmp_path, _plan(tmp_path, []), scope)


def test_scope_applies_to_remainder_and_cannot_expand_for_a_group(tmp_path: Path) -> None:
    lake = _item(tmp_path, "Lake", "Lakehouse", 1)
    _item(tmp_path, "Notebook", "Notebook", 2)
    schedule = load_schedule(tmp_path, _plan(tmp_path, []), ["Notebook"])
    assert schedule.batches == ()
    assert [item.selector for item in schedule.remaining_items] == ["Notebook.Notebook"]
    with pytest.raises(ValueError, match="outside the deployment scope"):
        load_schedule(tmp_path, _plan(tmp_path, [{"name": "Lake", "logicalId": lake}]), ["Notebook"])
    with pytest.raises(ValueError, match="No deployable"):
        load_schedule(tmp_path, _plan(tmp_path, []), ["Report"])


def test_control_metadata_cannot_be_deployed_or_planned(tmp_path: Path) -> None:
    control = _item(tmp_path, "Control", "DeploymentPlan", 1)
    _item(tmp_path, "Notebook", "Notebook", 2)
    with pytest.raises(ValueError, match="control metadata"):
        load_schedule(tmp_path, _plan(tmp_path, []), ["Notebook", "DeploymentPlan"])
    with pytest.raises(ValueError, match="outside the deployment scope"):
        load_schedule(tmp_path, _plan(tmp_path, [{"name": "Control", "logicalId": control}]), ["Notebook"])


@pytest.mark.parametrize("value", [
    "", "bad", "0" * 32, str(UUID(int=0)), "{00000000-0000-0000-0000-000000000001}", 42,
])
def test_invalid_or_placeholder_guids_are_rejected(value: object) -> None:
    with pytest.raises(ValueError):
        validate_guid(value, "logicalId")


def test_metadata_not_folder_name_determines_identity(tmp_path: Path) -> None:
    logical_id = _item(tmp_path, "Original", "Notebook", 0xABCDEF)
    (tmp_path / "Original.Notebook").rename(tmp_path / "DifferentFolder")
    schedule = load_schedule(
        tmp_path, _plan(tmp_path, [{"name": "Group", "logicalId": logical_id.upper()}]), ["Notebook"],
    )
    assert schedule.batches[0][0].item.selector == "Original.Notebook"
    assert schedule.batches[0][0].item.logical_id == logical_id


@pytest.mark.parametrize("duplicate_id", [True, False])
def test_duplicate_inventory_is_rejected(tmp_path: Path, duplicate_id: bool) -> None:
    _item(tmp_path, "Item", "Notebook", 1)
    _item(tmp_path / "Nested", "item", "Notebook", 1 if duplicate_id else 2)
    with pytest.raises(ValueError, match="Duplicate item logicalId|Ambiguous item"):
        load_schedule(tmp_path, _plan(tmp_path, []), ["Notebook"])


@pytest.mark.parametrize("duplicate_name", [True, False])
def test_duplicate_groups_or_item_use(tmp_path: Path, duplicate_name: bool) -> None:
    first = _item(tmp_path, "First", "Notebook", 1)
    second = _item(tmp_path, "Second", "Notebook", 2)
    path = _plan(tmp_path, [
        {"name": "Group", "logicalId": first},
        {"name": "GROUP" if duplicate_name else "Other", "logicalId": second if duplicate_name else first},
    ])
    with pytest.raises(ValueError, match="Duplicate group|multiple groups"):
        load_schedule(tmp_path, path, ["Notebook"])


@pytest.mark.parametrize("cycle", [False, True])
def test_cycles_fail_explicitly(tmp_path: Path, cycle: bool) -> None:
    first = _item(tmp_path, "First", "Notebook", 1)
    second = _item(tmp_path, "Second", "Notebook", 2)
    path = _plan(tmp_path, [
        {"name": "First", "logicalId": first, "dependsOn": [{"groupName": "Second" if cycle else "First"}]},
        {"name": "Second", "logicalId": second, "dependsOn": [{"groupName": "First"}]},
    ])
    with pytest.raises(ValueError, match="cycle"):
        load_schedule(tmp_path, path, ["Notebook"])


@pytest.mark.parametrize("dependencies", [
    [{"groupName": "Typo"}],
    [{"groupName": "Group"}, {"groupName": "GROUP"}],
    ["Group"],
    [{"groupName": "Group", "unexpected": True}],
    {},
])
def test_invalid_dependencies_fail(tmp_path: Path, dependencies: object) -> None:
    logical_id = _item(tmp_path, "Item", "Notebook", 1)
    path = _plan(tmp_path, [{"name": "Group", "logicalId": logical_id, "dependsOn": dependencies}])
    with pytest.raises(ValueError):
        load_schedule(tmp_path, path, ["Notebook"])


def test_missing_repository_item_fails(tmp_path: Path) -> None:
    _item(tmp_path, "Item", "Notebook", 1)
    with pytest.raises(ValueError, match="missing from the repository"):
        load_schedule(
            tmp_path, _plan(tmp_path, [{"name": "Missing", "logicalId": str(UUID(int=2))}]), ["Notebook"],
        )


@pytest.mark.parametrize("field", ["preActions", "postActions", "options"])
def test_unsupported_actions_and_options_are_not_ignored(tmp_path: Path, field: str) -> None:
    logical_id = _item(tmp_path, "Item", "Notebook", 1)
    path = _plan(tmp_path, [{"name": "Item", "logicalId": logical_id, field: [{"name": "Run"}]}])
    with pytest.raises(ValueError, match="unsupported"):
        load_schedule(tmp_path, path, ["Notebook"])


def test_empty_actions_are_allowed_without_implementing_them(tmp_path: Path) -> None:
    logical_id = _item(tmp_path, "Item", "Notebook", 1)
    path = _plan(tmp_path, [{
        "name": "Item", "logicalId": logical_id, "preActions": [], "postActions": None, "options": [],
    }])
    assert len(load_schedule(tmp_path, path, ["Notebook"]).batches) == 1


@pytest.mark.parametrize("document", [
    None, [], {"$schema": PLAN_SCHEMA, "version": "2.0.0"},
    {"$schema": "wrong", "version": "1.0.0"},
    {"$schema": PLAN_SCHEMA, "version": "1.0.0", "groups": {}},
    {"$schema": PLAN_SCHEMA, "version": "1.0.0", "unexpected": True},
])
def test_invalid_plan_shape_or_version(tmp_path: Path, document: object) -> None:
    path = tmp_path / "plan.yml"
    path.write_text(yaml.safe_dump(document), encoding="utf-8")
    with pytest.raises(ValueError):
        load_schedule(tmp_path, path, ["Notebook"])


def test_safe_yaml_and_duplicate_key_validation(tmp_path: Path) -> None:
    path = tmp_path / "plan.yml"
    path.write_text(f"$schema: {PLAN_SCHEMA}\nversion: 1.0.0\nversion: 2.0.0\n", encoding="utf-8")
    with pytest.raises(ValueError, match="Duplicate YAML key"):
        load_schedule(tmp_path, path, ["Notebook"])
    path.write_text("!!python/object:object {}", encoding="utf-8")
    with pytest.raises(yaml.YAMLError):
        load_schedule(tmp_path, path, ["Notebook"])


def test_plan_size_limit(tmp_path: Path) -> None:
    path = tmp_path / "plan.yml"
    path.write_text(" " * (MAX_PLAN_BYTES + 1), encoding="utf-8")
    with pytest.raises(ValueError, match="size limit"):
        load_schedule(tmp_path, path, ["Notebook"])


def test_long_graph_and_group_limit(tmp_path: Path) -> None:
    groups: list[dict[str, object]] = []
    for index in range(MAX_GROUPS):
        logical_id = _item(tmp_path, f"Item{index}", "Notebook", index + 1)
        group: dict[str, object] = {"name": f"Group{index}", "logicalId": logical_id}
        if index:
            group["dependsOn"] = [{"groupName": f"Group{index - 1}"}]
        groups.append(group)
    assert len(load_schedule(tmp_path, _plan(tmp_path, groups), ["Notebook"]).batches) == MAX_GROUPS
    groups.append({"name": "Extra", "logicalId": str(UUID(int=MAX_GROUPS + 1))})
    with pytest.raises(ValueError, match="at most 1000"):
        load_schedule(tmp_path, _plan(tmp_path, groups), ["Notebook"])


def test_500_items_need_only_three_authored_groups(tmp_path: Path) -> None:
    ids = [_item(tmp_path, f"Notebook{i:04}", "Notebook", i + 1) for i in range(500)]
    path = _plan(tmp_path, [{"name": f"Group{i}", "logicalId": ids[i]} for i in range(3)])
    schedule = load_schedule(tmp_path, path, ["Notebook"])
    assert len(schedule.batches) == 1
    assert len(schedule.batches[0]) == 3
    assert len(schedule.remaining_items) == 497
    assert len({group.item.logical_id for group in schedule.batches[0]} | {
        item.logical_id for item in schedule.remaining_items
    }) == 500
