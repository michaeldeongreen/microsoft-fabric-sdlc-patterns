"""Deploy with strict fabric-cicd 1.4.x bulk and isolated client-side plan ordering.

Requires fabric-cicd and azure-identity for publishing/authentication and PyYAML
for the authored plan. The SDK owns all parameter.yml replacements. This is an
ordering-only bridge, not native Deployment Plan execution or a REST publisher.

Required live environment variables: AZURE_TENANT_ID, AZURE_CLIENT_ID,
AZURE_CLIENT_SECRET, FABRIC_WORKSPACE_ID, ENVIRONMENT. All runs require an
explicit ITEM_TYPE_IN_SCOPE JSON list and DEPLOYMENT_PLAN_PATH (or --plan).
REPOSITORY_DIRECTORY defaults to data/fabric. Paths must be checkout-relative
or absolute paths within the checkout. Use --dry-run for a credentials-free
schedule preview. Unexpected fallback or incomplete item success is fatal.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from importlib.metadata import version
from pathlib import Path

import yaml
from azure.core.credentials import TokenCredential
from azure.identity import ClientSecretCredential
from fabric_cicd import (
    FabricWorkspace,
    ItemType,
    append_feature_flag,
    publish_all_items,
    unpublish_all_orphan_items,
)
from fabric_cicd.constants import BULK_ACCEPTED_ITEM_TYPES

from deployment_plan_bulk import BulkDeploymentSchedule, RepositoryItem, load_schedule, validate_guid

BULK_FEATURE_FLAGS = (
    "enable_experimental_features",
    "enable_bulk_publish",
    "enable_items_to_include",
    "enable_response_collection",
)
CLEANUP_EXCLUDED_TYPES = frozenset({"Lakehouse", "Ontology", "DeploymentPlan"})


class BulkDeploymentError(RuntimeError):
    """A selection did not satisfy the strict bulk deployment contract."""


def validate_sdk_version() -> str:
    installed = version("fabric-cicd")
    if re.fullmatch(r"1\.4\.\d+(?:\.post\d+)?(?:\+[a-zA-Z0-9._-]+)?", installed) is None:
        raise ValueError(
            f"Unsupported fabric-cicd version {installed!r}; "
            "this adapter requires a released version >=1.4.0,<1.5.0."
        )
    return installed


def parse_item_types(raw: str) -> list[str]:
    if not raw.strip():
        raise ValueError("ITEM_TYPE_IN_SCOPE is required for strict bulk publishing.")
    value = json.loads(raw)
    if (
        not isinstance(value, list)
        or not value
        or any(not isinstance(item, str) or not item or item.strip() != item for item in value)
    ):
        raise ValueError("ITEM_TYPE_IN_SCOPE must be a nonempty JSON array of item-type strings.")
    if len(set(value)) != len(value):
        raise ValueError("ITEM_TYPE_IN_SCOPE contains duplicate item types.")
    validate_item_types(tuple(value))
    return value


def validate_item_types(item_types: tuple[str, ...]) -> None:
    if not item_types:
        raise ValueError("Strict bulk publishing requires an explicit nonempty item-type scope.")
    if "DeploymentPlan" in item_types:
        raise ValueError("DeploymentPlan is control metadata, not a publishable item type.")
    unsupported = set(item_types) - {item.value for item in ItemType}
    if unsupported:
        raise ValueError(f"fabric-cicd does not support item types: {', '.join(sorted(unsupported))}.")
    ineligible = set(item_types) - set(BULK_ACCEPTED_ITEM_TYPES)
    if ineligible:
        raise ValueError(f"Item types cannot use bulk publishing: {', '.join(sorted(ineligible))}.")


def cleanup_types(schedule: BulkDeploymentSchedule) -> list[str]:
    return [item_type for item_type in schedule.item_types if item_type not in CLEANUP_EXCLUDED_TYPES]


def validate_value_sets(schedule: BulkDeploymentSchedule, environment: str) -> None:
    items = tuple(group.item for batch in schedule.batches for group in batch) + schedule.remaining_items
    for item in items:
        if item.item_type != "VariableLibrary":
            continue
        settings_path = item.path / "settings.json"
        if not settings_path.is_file():
            raise ValueError(f"{item.selector} has no settings.json for value-set activation.")
        settings = json.loads(settings_path.read_text(encoding="utf-8"))
        names = settings.get("valueSetsOrder") if isinstance(settings, dict) else None
        if (
            not isinstance(names, list)
            or any(not isinstance(name, str) or not name for name in names)
            or environment not in names
        ):
            raise ValueError(
                f"{item.selector} has no value set matching ENVIRONMENT={environment!r}; "
                "default-value-set fallback is forbidden."
            )
        value_set_path = (item.path / "valueSets" / f"{environment}.json").resolve()
        if not value_set_path.is_relative_to(item.path.resolve()) or not value_set_path.is_file():
            raise ValueError(f"{item.selector} is missing the selected value-set file.")
        value_set = json.loads(value_set_path.read_text(encoding="utf-8"))
        if not isinstance(value_set, dict) or value_set.get("name") != environment:
            raise ValueError(f"{item.selector} selected value-set name does not match ENVIRONMENT.")


def validate_workspace_parameters(
    workspace: FabricWorkspace, items: tuple[RepositoryItem, ...],
) -> None:
    # Reuse read-only SDK matching; never resolve or rewrite replacement values here.
    from fabric_cicd._items._bulk_publish_dependencies import has_unfiltered_items_variable
    from fabric_cicd._parameter._utils import (
        check_replacement,
        extract_find_value,
        extract_parameter_filters,
        process_environment_key,
    )
    if has_unfiltered_items_variable(workspace):
        raise BulkDeploymentError(
            "An unfiltered current-workspace $items replacement would cause standard "
            "fallback. Add an item_type, item_name, or file_path filter."
        )
    for item in items:
        if item.item_type != "VariableLibrary":
            continue
        control_paths = [item.path / "settings.json", *sorted((item.path / "valueSets").glob("*.json"))]
        for path in control_paths:
            if not path.resolve().is_relative_to(item.path.resolve()):
                raise BulkDeploymentError(f"{item.selector} control metadata is outside its directory.")
            contents = path.read_text(encoding="utf-8")
            for kind in ("key_value_replace", "find_replace"):
                for index, parameter in enumerate(workspace.environment_parameter.get(kind, []), start=1):
                    input_type, input_name, input_path = extract_parameter_filters(workspace, parameter)
                    matches_file = check_replacement(
                        input_type, input_name, input_path, item.item_type, item.name, path,
                    )
                    if not matches_file:
                        continue
                    if kind == "find_replace":
                        replacements = process_environment_key(
                            workspace.environment, dict(parameter["replace_value"])
                        )
                        if workspace.environment not in replacements:
                            continue
                        matches_content = extract_find_value(
                            parameter, contents, matches_file, workspace_obj=workspace,
                        )["has_matches"]
                    else:
                        # SDK key-value rules reserialize JSON even without a key/environment match.
                        matches_content = True
                    if matches_content:
                        raise BulkDeploymentError(
                            f"{kind}[{index}] targets {item.selector} control metadata "
                            f"({path.relative_to(item.path)}). Keep settings/value-set files "
                            "literal; SDK parameterization of these files is forbidden in "
                            "this strict adapter. Parameterize variables.json or workload definitions instead."
                        )


def _response_mapping(value: object, label: str) -> dict[str, object]:
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise BulkDeploymentError(f"Missing or malformed bulk {label}.")
    return value


def validate_bulk_results(results: object, items: tuple[RepositoryItem, ...]) -> None:
    responses = _response_mapping(results, "response collection")
    expected: dict[str, set[str]] = {}
    for item in items:
        expected.setdefault(item.item_type, set()).add(item.name)
    if responses.keys() != expected.keys():
        raise BulkDeploymentError("Bulk response item types do not match the selected item types.")
    item_ids: set[str] = set()
    for item_type, names in expected.items():
        by_name = _response_mapping(responses[item_type], f"{item_type} item responses")
        if by_name.keys() != names:
            raise BulkDeploymentError(f"Bulk responses for {item_type} do not match the selected items.")
        for name in sorted(names):
            selector = f"{name}.{item_type}"
            response = _response_mapping(by_name[name], f"response for {selector}")
            body = _response_mapping(response.get("body"), f"item detail for {selector}")
            status_code = response.get("status_code")
            if type(status_code) is not int or not 200 <= status_code < 300:
                raise BulkDeploymentError(f"Bulk response for {selector} has no successful HTTP status.")
            if body.get("itemType") != item_type or body.get("itemDisplayName") != name:
                raise BulkDeploymentError(f"Bulk response identity does not match {selector}.")
            status = body.get("operationStatus")
            if not isinstance(status, str):
                raise BulkDeploymentError(f"Bulk response for {selector} has no valid operationStatus.")
            if status != "Succeeded":
                raise BulkDeploymentError(f"Bulk item {selector} did not succeed: {status!r}.")
            try:
                item_id = validate_guid(body.get("itemId"), f"Bulk result for {selector} itemId")
            except ValueError as exc:
                raise BulkDeploymentError(str(exc)) from exc
            if item_id in item_ids:
                raise BulkDeploymentError(f"Bulk result for {selector} repeats an itemId.")
            item_ids.add(item_id)
            print(f"  {selector}: Succeeded (bulk import API)")


def _publish_selection(
    schedule: BulkDeploymentSchedule,
    items: tuple[RepositoryItem, ...],
    label: str,
    workspace_id: str,
    environment: str,
    credential: TokenCredential,
) -> None:
    if not items:
        raise BulkDeploymentError(f"{label} has no selected items; unrestricted publishing is forbidden.")
    selectors = [item.selector for item in items]
    item_types = tuple(sorted({item.item_type for item in items}))
    validate_item_types(item_types)
    print(f"{label}: {', '.join(selectors)}")
    workspace = FabricWorkspace(
        repository_directory=str(schedule.repository_directory),
        workspace_id=workspace_id,
        environment=environment,
        token_credential=credential,
        item_type_in_scope=list(item_types),
    )
    validate_workspace_parameters(workspace, items)
    results = publish_all_items(workspace, items_to_include=selectors)
    if workspace.bulk_publish_enabled is not True:
        raise BulkDeploymentError(f"{label}: SDK fell back to standard publishing; bulk is required.")
    validate_bulk_results(results, items)


def deploy_schedule(
    schedule: BulkDeploymentSchedule,
    workspace_id: str,
    environment: str,
    credential: TokenCredential,
) -> None:
    installed = validate_sdk_version()
    validate_item_types(schedule.item_types)
    if not schedule.batches and not schedule.remaining_items:
        raise BulkDeploymentError("No selected items; publishing and orphan cleanup are forbidden.")
    workspace_id = validate_guid(workspace_id, "FABRIC_WORKSPACE_ID")
    if not environment.strip():
        raise ValueError("ENVIRONMENT must not be empty.")
    validate_value_sets(schedule, environment)
    print(f"fabric-cicd {installed}; mode: strict bulk with isolated client-side plan ordering.")
    for flag in BULK_FEATURE_FLAGS:
        append_feature_flag(flag)

    all_items = tuple(group.item for batch in schedule.batches for group in batch) + schedule.remaining_items
    if any(item.item_type == "VariableLibrary" for item in all_items):
        preflight_workspace = FabricWorkspace(
            repository_directory=str(schedule.repository_directory),
            workspace_id=workspace_id,
            environment=environment,
            token_credential=credential,
            item_type_in_scope=list(schedule.item_types),
        )
        validate_workspace_parameters(preflight_workspace, all_items)

    for index, batch in enumerate(schedule.batches, start=1):
        _publish_selection(
            schedule, tuple(group.item for group in batch),
            f"Ready batch {index} ({', '.join(group.name for group in batch)})",
            workspace_id, environment, credential,
        )
    if schedule.remaining_items:
        _publish_selection(
            schedule, schedule.remaining_items, "Remaining items",
            workspace_id, environment, credential,
        )

    scope = cleanup_types(schedule)
    if scope:
        print(f"Cleaning up orphaned items in scope: {', '.join(scope)}")
        workspace = FabricWorkspace(
            repository_directory=str(schedule.repository_directory),
            workspace_id=workspace_id,
            environment=environment,
            token_credential=credential,
            item_type_in_scope=scope,
        )
        unpublish_all_orphan_items(workspace)
    else:
        print("No item types eligible for orphan cleanup.")
    print(
        f"Bulk deployment completed: {len(schedule.batches)} plan batch(es), "
        f"{sum(len(batch) for batch in schedule.batches)} planned item(s), "
        f"{len(schedule.remaining_items)} remaining item(s)."
    )


def _required_environment(name: str) -> str:
    value = os.environ.get(name, "")
    if not value.strip():
        raise ValueError(f"Required environment variable is missing or empty: {name}")
    return value


def _checkout_path(raw: str, label: str) -> Path:
    if not raw.strip():
        raise ValueError(f"{label} is required.")
    path = Path(raw).resolve()
    if not path.is_relative_to(Path.cwd().resolve()):
        raise ValueError(f"{label} must be within the repository checkout.")
    return path


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="Preview batches without Fabric calls.")
    parser.add_argument("--plan", default=os.environ.get("DEPLOYMENT_PLAN_PATH", ""))
    parser.add_argument(
        "--repository-directory", default=os.environ.get("REPOSITORY_DIRECTORY", "data/fabric")
    )
    args = parser.parse_args(argv)
    try:
        installed = validate_sdk_version()
        schedule = load_schedule(
            _checkout_path(args.repository_directory, "REPOSITORY_DIRECTORY"),
            _checkout_path(args.plan, "DEPLOYMENT_PLAN_PATH (or --plan)"),
            parse_item_types(os.environ.get("ITEM_TYPE_IN_SCOPE", "")),
        )
        summary = schedule.summary()
        summary["fabricCicdVersion"] = installed
        summary["cleanupItemTypes"] = cleanup_types(schedule)
        print(json.dumps(summary, indent=2))
        if args.dry_run:
            preview_environment = os.environ.get("ENVIRONMENT", "")
            if preview_environment:
                validate_value_sets(schedule, preview_environment)
            return
        environment = _required_environment("ENVIRONMENT")
        validate_value_sets(schedule, environment)
        workspace_id = validate_guid(_required_environment("FABRIC_WORKSPACE_ID"), "FABRIC_WORKSPACE_ID")
        tenant_id = validate_guid(_required_environment("AZURE_TENANT_ID"), "AZURE_TENANT_ID")
        client_id = validate_guid(_required_environment("AZURE_CLIENT_ID"), "AZURE_CLIENT_ID")
        credential = ClientSecretCredential(
            tenant_id=tenant_id, client_id=client_id,
            client_secret=_required_environment("AZURE_CLIENT_SECRET"),
        )
        deploy_schedule(schedule, workspace_id, environment, credential)
    except (OSError, ValueError, yaml.YAMLError, BulkDeploymentError) as exc:
        print(f"::error::{exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
