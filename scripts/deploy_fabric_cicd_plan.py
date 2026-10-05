"""Deploy with non-bulk fabric-cicd in a committed Deployment Plan's order.

Requires fabric-cicd >= 1.3.0 and azure-identity for public publishing APIs and
service-principal authentication; deployment_plan uses PyYAML for native YAML.
No native plan execution or Before/After actions are implemented.

Use --plan <plan.yml> --dry-run for a credentials-free deployment preview.
Live runs use the same Azure, Fabric, repository and environment variables as
deploy_fabric_cicd.py, plus DEPLOYMENT_PLAN_PATH. Plan paths are checkout-relative.
"""

from __future__ import annotations

import argparse
import json
import os
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
    remove_feature_flag,
    unpublish_all_orphan_items,
)

from deployment_plan import DeploymentSchedule, load_schedule, validate_guid

INCLUSION_FLAGS = ("enable_experimental_features", "enable_items_to_include")
# Preserve the existing standard path's cleanup scope, independently of ordering.
CLEANUP_EXCLUDED_TYPES = frozenset({"Lakehouse", "Ontology", "DeploymentPlan"})


def parse_item_types(raw: str) -> list[str] | None:
    if not raw.strip():
        return None
    value = json.loads(raw)
    if (
        not isinstance(value, list)
        or not value
        or any(not isinstance(item, str) or not item for item in value)
    ):
        raise ValueError("ITEM_TYPE_IN_SCOPE must be a nonempty JSON array of item-type strings.")
    if len(set(value)) != len(value):
        raise ValueError("ITEM_TYPE_IN_SCOPE contains duplicate item types.")
    return value


def validate_item_types(item_types: tuple[str, ...]) -> None:
    supported = {item.value for item in ItemType}
    unsupported = set(item_types) - supported
    if unsupported:
        raise ValueError(f"fabric-cicd does not support item types: {', '.join(sorted(unsupported))}.")


def cleanup_types(schedule: DeploymentSchedule) -> list[str]:
    return [item_type for item_type in schedule.item_types if item_type not in CLEANUP_EXCLUDED_TYPES]


def deploy_schedule(
    schedule: DeploymentSchedule,
    workspace_id: str,
    environment: str,
    credential: TokenCredential,
) -> None:
    validate_item_types(schedule.item_types)
    workspace_id = validate_guid(workspace_id, "FABRIC_WORKSPACE_ID")
    remove_feature_flag("enable_bulk_publish")
    for flag in INCLUSION_FLAGS:
        append_feature_flag(flag)

    for group in schedule.groups:
        print(f"Deploying group {group.name}: {group.item.selector}")
        workspace = FabricWorkspace(
            repository_directory=str(schedule.repository_directory),
            workspace_id=workspace_id,
            environment=environment,
            token_credential=credential,
            item_type_in_scope=[group.item.item_type],
        )
        publish_all_items(workspace, items_to_include=[group.item.selector])

    if schedule.remaining_items:
        selectors = [item.selector for item in schedule.remaining_items]
        print(f"Deploying {len(selectors)} remaining item(s) in fabric-cicd's standard order.")
        workspace = FabricWorkspace(
            repository_directory=str(schedule.repository_directory),
            workspace_id=workspace_id,
            environment=environment,
            token_credential=credential,
            item_type_in_scope=sorted({item.item_type for item in schedule.remaining_items}),
        )
        publish_all_items(workspace, items_to_include=selectors)

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
        f"Deployment completed: {len(schedule.groups)} planned item(s), "
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
    parser.add_argument("--dry-run", action="store_true", help="Print the schedule without Fabric calls.")
    parser.add_argument("--plan", default=os.environ.get("DEPLOYMENT_PLAN_PATH", ""))
    parser.add_argument(
        "--repository-directory", default=os.environ.get("REPOSITORY_DIRECTORY", "data/fabric")
    )
    args = parser.parse_args(argv)
    try:
        schedule = load_schedule(
            _checkout_path(args.repository_directory, "REPOSITORY_DIRECTORY"),
            _checkout_path(args.plan, "DEPLOYMENT_PLAN_PATH (or --plan)"),
            parse_item_types(os.environ.get("ITEM_TYPE_IN_SCOPE", "")),
        )
        validate_item_types(schedule.item_types)
        if not args.dry_run:
            environment = _required_environment("ENVIRONMENT")
            workspace_id = validate_guid(_required_environment("FABRIC_WORKSPACE_ID"), "FABRIC_WORKSPACE_ID")
            tenant_id = validate_guid(_required_environment("AZURE_TENANT_ID"), "AZURE_TENANT_ID")
            client_id = validate_guid(_required_environment("AZURE_CLIENT_ID"), "AZURE_CLIENT_ID")
            client_secret = _required_environment("AZURE_CLIENT_SECRET")
    except (OSError, ValueError, yaml.YAMLError) as exc:
        print(f"::error::{exc}", file=sys.stderr)
        sys.exit(1)

    summary = schedule.summary()
    summary["cleanupItemTypes"] = cleanup_types(schedule)
    print(json.dumps(summary, indent=2))
    if args.dry_run:
        return

    print(f"fabric-cicd {version('fabric-cicd')}; mode: standard publish with declared plan ordering.")
    credential = ClientSecretCredential(
        tenant_id=tenant_id, client_id=client_id, client_secret=client_secret
    )
    deploy_schedule(schedule, workspace_id, environment, credential)


if __name__ == "__main__":
    main()
