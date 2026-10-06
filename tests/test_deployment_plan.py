"""Validate the ordering subset without contacting Fabric."""

from __future__ import annotations

import json
from pathlib import Path
from uuid import UUID

import pytest
import yaml

from deployment_plan import MAX_GROUPS, MAX_PLAN_BYTES, PLAN_SCHEMA, load_schedule, validate_guid

REPO_ROOT = Path(__file__).resolve().parents[1]


def _item(root: Path, name: str, item_type: str, number: int) -> str:
    logical_id = str(UUID(int=number))
    directory = root / f"{name}.{item_type}"
    directory.mkdir(parents=True, exist_ok=True)
    (directory / ".platform").write_text(
        json.dumps({
            "metadata": {"type": item_type, "displayName": name},
            "config": {"logicalId": logical_id},
        }),
        encoding="utf-8",
    )
    return logical_id


def _plan(root: Path, groups: list[dict[str, object]]) -> Path:
    path = root / "plan.yml"
    path.write_text(
        yaml.safe_dump({"$schema": PLAN_SCHEMA, "version": "1.0.0", "groups": groups}),
        encoding="utf-8",
    )
    return path


def test_real_repository_plan_and_remaining_inventory() -> None:
    schedule = load_schedule(
        REPO_ROOT / "data" / "fabric",
        REPO_ROOT / "data" / "fabric" / "DeploymentPlan.DeploymentPlan" / "plan.yml",
    )
    assert [group.name for group in schedule.groups] == [
        "Lakehouse_Group", "Ontology_Group", "SemanticModel_Group", "DataAgent_Group"
    ]
    assert {item.selector for item in schedule.remaining_items} == {
        "Patterns_Report.Report",
        "Patterns_Variables.VariableLibrary",
        "Import_Patterns_Data.Notebook",
        "Patterns_Demo.Notebook",
        "Patterns_Patients_Data.Notebook",
    }
    assert "DeploymentPlan" not in schedule.item_types
    assert schedule.summary()["orderingBasis"] == "explicit-dependencies-only"


def test_order_is_not_yaml_position(tmp_path: Path) -> None:
    first = _item(tmp_path, "First", "Lakehouse", 1)
    second = _item(tmp_path, "Second", "Notebook", 2)
    groups: list[dict[str, object]] = [
        {"name": "First", "logicalId": first},
        {"name": "Second", "logicalId": second, "dependsOn": [{"groupName": "First"}]},
    ]
    path = _plan(tmp_path, groups)
    forward = load_schedule(tmp_path, path)
    _plan(tmp_path, list(reversed(groups)))
    backward = load_schedule(tmp_path, path)
    assert forward.groups == backward.groups
    assert [group.item.logical_id for group in forward.groups] == [first, second]


def test_case_insensitive_group_references(tmp_path: Path) -> None:
    first = _item(tmp_path, "First", "Lakehouse", 1)
    second = _item(tmp_path, "Second", "Notebook", 2)
    path = _plan(tmp_path, [
        {"name": "First", "logicalId": first},
        {"name": "Second", "logicalId": second, "dependsOn": [{"groupName": "FIRST"}]},
    ])
    assert [group.name for group in load_schedule(tmp_path, path).groups] == ["First", "Second"]


@pytest.mark.parametrize("field", ["preActions", "postActions", "options"])
def test_actions_and_options_are_not_silently_ignored(tmp_path: Path, field: str) -> None:
    item = _item(tmp_path, "Item", "Notebook", 1)
    path = _plan(tmp_path, [{"name": "Item", "logicalId": item, field: [{"name": "Run"}]}])
    with pytest.raises(ValueError, match="unsupported"):
        load_schedule(tmp_path, path)


def test_empty_action_fields_are_allowed(tmp_path: Path) -> None:
    item = _item(tmp_path, "Item", "Notebook", 1)
    path = _plan(tmp_path, [{
        "name": "Item", "logicalId": item,
        "preActions": [], "postActions": None, "options": [],
    }])
    assert len(load_schedule(tmp_path, path).groups) == 1


@pytest.mark.parametrize("value", ["", "bad", "0" * 32, str(UUID(int=0)), "{00000000-0000-0000-0000-000000000001}", 42])
def test_invalid_or_placeholder_guid(value: object) -> None:
    with pytest.raises(ValueError):
        validate_guid(value, "logicalId")


def test_guids_are_normalized_without_requiring_uuid_version(tmp_path: Path) -> None:
    logical_id = _item(tmp_path, "Item", "Notebook", 0xABCDEF)
    path = _plan(tmp_path, [{"name": "Item", "logicalId": logical_id.upper()}])
    assert load_schedule(tmp_path, path).groups[0].item.logical_id == logical_id


def test_missing_repository_item(tmp_path: Path) -> None:
    _item(tmp_path, "Item", "Notebook", 1)
    path = _plan(tmp_path, [{"name": "Missing", "logicalId": str(UUID(int=2))}])
    with pytest.raises(ValueError, match="missing from the repository"):
        load_schedule(tmp_path, path)


def test_group_outside_scope_fails_instead_of_widening_scope(tmp_path: Path) -> None:
    lakehouse = _item(tmp_path, "Lake", "Lakehouse", 1)
    _item(tmp_path, "Notebook", "Notebook", 2)
    path = _plan(tmp_path, [{"name": "Lake", "logicalId": lakehouse}])
    with pytest.raises(ValueError, match="outside the deployment scope"):
        load_schedule(tmp_path, path, ["Notebook"])


def test_scope_applies_to_unlisted_items(tmp_path: Path) -> None:
    _item(tmp_path, "Notebook", "Notebook", 1)
    _item(tmp_path, "Model", "SemanticModel", 2)
    schedule = load_schedule(tmp_path, _plan(tmp_path, []), ["Notebook"])
    assert [item.selector for item in schedule.remaining_items] == ["Notebook.Notebook"]


def test_empty_selection_cannot_trigger_cleanup(tmp_path: Path) -> None:
    _item(tmp_path, "Notebook", "Notebook", 1)
    with pytest.raises(ValueError, match="No deployable"):
        load_schedule(tmp_path, _plan(tmp_path, []), ["Report"])


def test_control_item_cannot_be_published_or_planned(tmp_path: Path) -> None:
    control = _item(tmp_path, "Plan", "DeploymentPlan", 1)
    _item(tmp_path, "Notebook", "Notebook", 2)
    path = _plan(tmp_path, [{"name": "Plan", "logicalId": control}])
    with pytest.raises(ValueError, match="outside the deployment scope"):
        load_schedule(tmp_path, path)
    with pytest.raises(ValueError, match="control metadata"):
        load_schedule(tmp_path, path, ["DeploymentPlan", "Notebook"])


def test_duplicate_item_ids_are_rejected(tmp_path: Path) -> None:
    _item(tmp_path, "One", "Notebook", 1)
    _item(tmp_path, "Two", "Notebook", 1)
    with pytest.raises(ValueError, match="Duplicate item logicalId"):
        load_schedule(tmp_path, _plan(tmp_path, []))


def test_duplicate_name_and_type_are_ambiguous(tmp_path: Path) -> None:
    _item(tmp_path, "Item", "Notebook", 1)
    _item(tmp_path / "folder", "item", "Notebook", 2)
    with pytest.raises(ValueError, match="Ambiguous item"):
        load_schedule(tmp_path, _plan(tmp_path, []))


def test_metadata_not_folder_name_determines_selector(tmp_path: Path) -> None:
    logical_id = _item(tmp_path, "Original", "Notebook", 1)
    original = tmp_path / "Original.Notebook"
    original.rename(tmp_path / "DifferentFolderName")
    schedule = load_schedule(tmp_path, _plan(tmp_path, [{"name": "Group", "logicalId": logical_id}]))
    assert schedule.groups[0].item.selector == "Original.Notebook"


@pytest.mark.parametrize("repeat_name", [True, False])
def test_duplicate_groups_or_item_use(tmp_path: Path, repeat_name: bool) -> None:
    first = _item(tmp_path, "First", "Notebook", 1)
    second = _item(tmp_path, "Second", "Notebook", 2)
    path = _plan(tmp_path, [
        {"name": "Group", "logicalId": first},
        {"name": "GROUP" if repeat_name else "Other", "logicalId": second if repeat_name else first},
    ])
    with pytest.raises(ValueError, match="Duplicate group|multiple groups"):
        load_schedule(tmp_path, path)


@pytest.mark.parametrize("cycle", [False, True])
def test_self_reference_and_two_node_cycle(tmp_path: Path, cycle: bool) -> None:
    first = _item(tmp_path, "First", "Notebook", 1)
    second = _item(tmp_path, "Second", "Notebook", 2)
    path = _plan(tmp_path, [
        {"name": "First", "logicalId": first, "dependsOn": [{"groupName": "Second" if cycle else "First"}]},
        {"name": "Second", "logicalId": second, "dependsOn": [{"groupName": "First"}]},
    ])
    with pytest.raises(ValueError, match="cycle"):
        load_schedule(tmp_path, path)


def test_missing_group_reference(tmp_path: Path) -> None:
    item = _item(tmp_path, "Item", "Notebook", 1)
    path = _plan(tmp_path, [{
        "name": "Group", "logicalId": item, "dependsOn": [{"groupName": "Typo"}],
    }])
    with pytest.raises(ValueError, match="unknown dependencies"):
        load_schedule(tmp_path, path)


def test_duplicate_yaml_key_rejected(tmp_path: Path) -> None:
    path = tmp_path / "plan.yml"
    path.write_text(f"$schema: {PLAN_SCHEMA}\nversion: 1.0.0\nversion: 2.0.0\n", encoding="utf-8")
    with pytest.raises(ValueError, match="Duplicate YAML key"):
        load_schedule(tmp_path, path)


@pytest.mark.parametrize("document", [
    None,
    [],
    {"$schema": PLAN_SCHEMA, "version": "2.0.0", "groups": []},
    {"$schema": "wrong", "version": "1.0.0"},
    {"$schema": PLAN_SCHEMA, "version": "1.0.0", "groups": {}},
    {"$schema": PLAN_SCHEMA, "version": "1.0.0", "unexpected": True},
])
def test_invalid_plan_shape_or_version(tmp_path: Path, document: object) -> None:
    path = tmp_path / "plan.yml"
    path.write_text(yaml.safe_dump(document), encoding="utf-8")
    with pytest.raises(ValueError):
        load_schedule(tmp_path, path)


def test_yaml_python_objects_are_never_constructed(tmp_path: Path) -> None:
    path = tmp_path / "plan.yml"
    path.write_text("!!python/object:object {}", encoding="utf-8")
    with pytest.raises(yaml.YAMLError):
        load_schedule(tmp_path, path)


def test_plan_size_limit(tmp_path: Path) -> None:
    path = tmp_path / "plan.yml"
    path.write_text(" " * (MAX_PLAN_BYTES + 1), encoding="utf-8")
    with pytest.raises(ValueError, match="size limit"):
        load_schedule(tmp_path, path)


def test_500_items_do_not_require_500_groups(tmp_path: Path) -> None:
    ids = [_item(tmp_path, f"Notebook{i:04}", "Notebook", i + 1) for i in range(500)]
    groups: list[dict[str, object]] = [
        {"name": f"Group{i}", "logicalId": ids[i]} for i in range(3)
    ]
    schedule = load_schedule(tmp_path, _plan(tmp_path, groups))
    assert len(schedule.groups) == 3
    assert len(schedule.remaining_items) == 497
    all_ids = {group.item.logical_id for group in schedule.groups}
    all_ids.update(item.logical_id for item in schedule.remaining_items)
    assert len(all_ids) == 500


def test_group_limit_including_long_dependency_chain(tmp_path: Path) -> None:
    groups: list[dict[str, object]] = []
    for index in range(MAX_GROUPS):
        logical_id = _item(tmp_path, f"Item{index}", "Notebook", index + 1)
        group: dict[str, object] = {"name": f"Group{index}", "logicalId": logical_id}
        if index:
            group["dependsOn"] = [{"groupName": f"Group{index - 1}"}]
        groups.append(group)
    path = _plan(tmp_path, groups)
    assert len(load_schedule(tmp_path, path).groups) == MAX_GROUPS
    groups.append({"name": "Extra", "logicalId": str(UUID(int=MAX_GROUPS + 1))})
    _plan(tmp_path, groups)
    with pytest.raises(ValueError, match="at most 1000"):
        load_schedule(tmp_path, path)
