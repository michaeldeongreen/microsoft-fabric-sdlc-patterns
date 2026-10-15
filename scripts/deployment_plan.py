"""Read the ordering-only subset of a Fabric Deployment Plan.

PyYAML is needed for Fabric's native plan.yml format. This module performs no
authentication, Fabric API calls, or writes to item definitions.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from graphlib import CycleError, TopologicalSorter
from pathlib import Path
from uuid import UUID

import yaml

PLAN_SCHEMA = (
    "https://developer.microsoft.com/json-schemas/fabric/item/"
    "deploymentPlan/definition/plan/1.0.0/schema.json"
)
MAX_GROUPS = 1000
MAX_PLAN_BYTES = 1024 * 1024
CONTROL_ITEM_TYPE = "DeploymentPlan"


@dataclass(frozen=True)
class RepositoryItem:
    logical_id: str
    name: str
    item_type: str
    path: Path

    @property
    def selector(self) -> str:
        return f"{self.name}.{self.item_type}"


@dataclass(frozen=True)
class DeploymentGroup:
    name: str
    item: RepositoryItem
    depends_on: tuple[str, ...]


@dataclass(frozen=True)
class DeploymentSchedule:
    plan_path: Path
    repository_directory: Path
    groups: tuple[DeploymentGroup, ...]
    remaining_items: tuple[RepositoryItem, ...]
    item_types: tuple[str, ...]

    def summary(self) -> dict[str, object]:
        return {
            "plan": str(self.plan_path),
            "orderingBasis": "explicit-dependencies-only",
            "itemTypesInScope": list(self.item_types),
            "groups": [
                {
                    "group": group.name,
                    "item": group.item.selector,
                    "logicalId": group.item.logical_id,
                    "dependsOn": list(group.depends_on),
                }
                for group in self.groups
            ],
            "remainingItems": [item.selector for item in self.remaining_items],
        }


class _UniqueKeyLoader(yaml.SafeLoader):
    pass


def _unique_mapping(
    loader: yaml.SafeLoader, node: yaml.Node
) -> dict[str, object]:
    if not isinstance(node, yaml.MappingNode):
        raise ValueError("Expected a YAML mapping.")
    result: dict[str, object] = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node)
        if not isinstance(key, str):
            raise ValueError("Plan mapping keys must be strings.")
        if key in result:
            raise ValueError(f"Duplicate YAML key: {key!r}.")
        result[key] = loader.construct_object(value_node)
    return result


_UniqueKeyLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _unique_mapping
)


def _mapping(value: object, label: str) -> dict[str, object]:
    if not isinstance(value, dict) or not all(isinstance(k, str) for k in value):
        raise ValueError(f"{label} must be an object with string keys.")
    return value


def _text(value: object, label: str) -> str:
    if (
        not isinstance(value, str)
        or not value
        or value.strip() != value
        or "\n" in value
        or "\r" in value
    ):
        raise ValueError(f"{label} must be a nonempty string without surrounding whitespace.")
    return value


def validate_guid(value: object, label: str) -> str:
    text = _text(value, label)
    try:
        guid = UUID(text)
    except ValueError as exc:
        raise ValueError(f"{label} must be a GUID.") from exc
    if text.lower() != str(guid) or guid.int == 0:
        raise ValueError(f"{label} must be a nonzero GUID in hyphenated form.")
    return str(guid)


def _only_keys(value: dict[str, object], allowed: set[str], label: str) -> None:
    unexpected = value.keys() - allowed
    if unexpected:
        raise ValueError(f"{label} has unsupported fields: {', '.join(sorted(unexpected))}.")


def _inventory(repository_directory: Path) -> dict[str, RepositoryItem]:
    if not repository_directory.is_dir():
        raise ValueError(f"Repository directory does not exist: {repository_directory}")
    items: dict[str, RepositoryItem] = {}
    selectors: set[str] = set()
    for platform_path in sorted(repository_directory.rglob(".platform")):
        if not platform_path.resolve().is_relative_to(repository_directory):
            raise ValueError(f"Item metadata is outside the repository directory: {platform_path}")
        data = _mapping(
            json.loads(platform_path.read_text(encoding="utf-8")), str(platform_path)
        )
        metadata = _mapping(data.get("metadata"), f"{platform_path} metadata")
        config = _mapping(data.get("config"), f"{platform_path} config")
        item = RepositoryItem(
            logical_id=validate_guid(config.get("logicalId"), f"{platform_path} logicalId"),
            name=_text(metadata.get("displayName"), f"{platform_path} displayName"),
            item_type=_text(metadata.get("type"), f"{platform_path} type"),
            path=platform_path.parent,
        )
        if item.logical_id in items:
            raise ValueError(f"Duplicate item logicalId: {item.logical_id}.")
        if item.selector.casefold() in selectors:
            raise ValueError(f"Ambiguous item name/type: {item.selector}.")
        items[item.logical_id] = item
        selectors.add(item.selector.casefold())
    return items


def load_schedule(
    repository_directory: Path,
    plan_path: Path,
    item_types: list[str] | None = None,
) -> DeploymentSchedule:
    """Validate the authored graph and select all eligible repository items."""
    repository_directory = repository_directory.resolve()
    plan_path = plan_path.resolve()
    if plan_path.stat().st_size > MAX_PLAN_BYTES:
        raise ValueError("Deployment Plan exceeds the supported 1 MiB size limit.")
    data = _mapping(
        yaml.load(plan_path.read_text(encoding="utf-8"), Loader=_UniqueKeyLoader),
        "Deployment Plan",
    )
    _only_keys(data, {"$schema", "version", "groups"}, "Deployment Plan")
    if data.get("$schema") != PLAN_SCHEMA or data.get("version") != "1.0.0":
        raise ValueError("Only the published Deployment Plan schema/version 1.0.0 is supported.")
    raw_groups = data.get("groups")
    if raw_groups is None:
        raw_groups = []
    if not isinstance(raw_groups, list) or len(raw_groups) > MAX_GROUPS:
        raise ValueError(f"groups must be an array of at most {MAX_GROUPS} groups.")

    inventory = _inventory(repository_directory)
    if item_types is not None:
        if not item_types or any(not isinstance(t, str) or not t.strip() for t in item_types):
            raise ValueError("Item-type scope must be a nonempty list of item types.")
        if CONTROL_ITEM_TYPE in item_types:
            raise ValueError("DeploymentPlan is control metadata, not a publishable item type.")
    scope = set(item_types) if item_types is not None else {
        item.item_type for item in inventory.values() if item.item_type != CONTROL_ITEM_TYPE
    }
    selected = {
        key: item for key, item in inventory.items()
        if item.item_type in scope and item.item_type != CONTROL_ITEM_TYPE
    }
    if not selected:
        raise ValueError("No deployable repository items match the item-type scope.")

    groups: dict[str, DeploymentGroup] = {}
    planned_ids: set[str] = set()
    for index, raw_group in enumerate(raw_groups):
        label = f"groups[{index}]"
        group = _mapping(raw_group, label)
        _only_keys(
            group, {"name", "logicalId", "dependsOn", "preActions", "postActions", "options"},
            label,
        )
        name = _text(group.get("name"), f"{label} name")
        if len(name) > 60:
            raise ValueError(f"Group name exceeds 60 characters: {name!r}.")
        if name.casefold() in groups:
            raise ValueError(f"Duplicate group name (case-insensitive): {name!r}.")
        for field in ("preActions", "postActions", "options"):
            if group.get(field) not in (None, []):
                raise ValueError(
                    f"Group {name!r}: {field} is unsupported by this ordering-only adapter."
                )
        logical_id = validate_guid(group.get("logicalId"), f"Group {name!r} logicalId")
        if logical_id not in selected:
            raise ValueError(
                f"Group {name!r} references an item missing from the repository or "
                f"outside the deployment scope: {logical_id}."
            )
        if logical_id in planned_ids:
            raise ValueError(f"Item {selected[logical_id].selector} appears in multiple groups.")
        raw_dependencies = group.get("dependsOn")
        if raw_dependencies is None:
            raw_dependencies = []
        if not isinstance(raw_dependencies, list) or len(raw_dependencies) > MAX_GROUPS:
            raise ValueError(f"Group {name!r}: dependsOn must be an array of at most {MAX_GROUPS} entries.")
        dependencies: list[str] = []
        for raw_dependency in raw_dependencies:
            dependency = _mapping(raw_dependency, f"Group {name!r} dependency")
            _only_keys(dependency, {"groupName"}, f"Group {name!r} dependency")
            dependencies.append(_text(dependency.get("groupName"), "Dependency groupName"))
        if len({dep.casefold() for dep in dependencies}) != len(dependencies):
            raise ValueError(f"Group {name!r} has duplicate dependencies.")
        groups[name.casefold()] = DeploymentGroup(name, selected[logical_id], tuple(dependencies))
        planned_ids.add(logical_id)

    graph: dict[str, set[str]] = {}
    for key, group in sorted(groups.items()):
        dependencies = {name.casefold() for name in group.depends_on}
        missing = dependencies - groups.keys()
        if missing:
            raise ValueError(f"Group {group.name!r} has unknown dependencies: {', '.join(sorted(missing))}.")
        graph[key] = dependencies
    sorter = TopologicalSorter(graph)
    try:
        sorter.prepare()
    except CycleError as exc:
        raise ValueError(f"Deployment Plan contains a dependency cycle: {exc.args[1]}.") from exc
    ordered: list[DeploymentGroup] = []
    while sorter.is_active():
        ready = sorted(sorter.get_ready())
        ordered.extend(groups[key] for key in ready)
        sorter.done(*ready)
    remaining = sorted(
        (item for key, item in selected.items() if key not in planned_ids),
        key=lambda item: (item.item_type, item.name.casefold()),
    )
    return DeploymentSchedule(
        plan_path, repository_directory, tuple(ordered), tuple(remaining), tuple(sorted(scope))
    )
