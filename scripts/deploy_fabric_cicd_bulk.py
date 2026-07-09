"""Deploy supported Fabric items via fabric-cicd with bulk publish requested.

This is the THIRD deploy method (``DEPLOY_METHOD=fabric-cicd-bulk``), alongside
the standard fabric-cicd path (``scripts/deploy_fabric_cicd.py``) and the raw
REST bulk path (``scripts/deploy_bulk.py``).

It enables fabric-cicd's experimental bulk publish
(``enable_experimental_features`` + ``enable_bulk_publish``) and then runs the
SAME two-phase deployment as the standard path against the SAME parameter.yml.

Purpose — demonstrate the documented fallback. fabric-cicd only uses the bulk
import API when the parameter file has NO dynamic variables. This repo's
parameter.yml is built entirely on ``$items``/``$workspace`` dynamic variables,
so ``FabricWorkspace.contains_param_vars`` is True and fabric-cicd ALWAYS falls
back to standard per-item publish here. The script surfaces that outcome
explicitly via each phase's ``bulk_publish_enabled`` value.

Because the run falls back to standard mode, parameter.yml is required and used
exactly as in the standard path — it rewrites the dev ``$items``/``$workspace``
IDs to the target workspace. Withholding it would push dev IDs into the target.

Invoked by .github/workflows/reusable-deploy-fabric-cicd-bulk.yml.

Required environment variables:
    AZURE_TENANT_ID, AZURE_CLIENT_ID, AZURE_CLIENT_SECRET,
    FABRIC_WORKSPACE_ID, REPOSITORY_DIRECTORY, ENVIRONMENT
Optional:
    ITEM_TYPE_IN_SCOPE — JSON array of item types to deploy. Defaults to all.
    FAIL_IF_BULK_USED  — set to 1/true/yes to exit non-zero if bulk publish was
                         actually used (i.e., the expected fallback did NOT
                         happen). Off by default (log-only).
"""

from __future__ import annotations

import json
import os
import sys

from azure.identity import ClientSecretCredential
from fabric_cicd import (
    FabricWorkspace,
    append_feature_flag,
    publish_all_items,
    unpublish_all_orphan_items,
)

from deploy_fabric_cicd import PHASE1_TYPES, remaining_types_for_phase2

# Both flags are required to request bulk publish — enable_bulk_publish without
# enable_experimental_features raises InputError in fabric-cicd.
BULK_FEATURE_FLAGS = ["enable_experimental_features", "enable_bulk_publish"]

_TRUE_VALUES = {"1", "true", "yes"}


def _env_flag(name: str) -> bool:
    """Return True if the named env var is set to a truthy value (1/true/yes)."""
    return os.environ.get(name, "").strip().lower() in _TRUE_VALUES


def print_fallback_proof(
    *, contains_param_vars: bool, phase_bulk_results: dict[str, bool]
) -> None:
    """Print an explicit summary of whether bulk publish engaged or fell back.

    Args:
        contains_param_vars: ``FabricWorkspace.contains_param_vars`` after
            publish — True when parameter.yml uses ``$items``/``$workspace``
            dynamic variables.
        phase_bulk_results: Mapping of phase label to the workspace's
            ``bulk_publish_enabled`` value after that phase's publish call.
    """
    any_bulk = any(phase_bulk_results.values())
    print("=" * 70)
    print("BULK PUBLISH EVALUATION (fabric-cicd)")
    print(f"  requested feature flags : {', '.join(BULK_FEATURE_FLAGS)}")
    print(
        f"  contains_param_vars     : {contains_param_vars} "
        "(parameter.yml uses $items/$workspace)"
    )
    for phase, used_bulk in phase_bulk_results.items():
        mode = "bulk import API" if used_bulk else "standard per-item (fallback)"
        print(f"  {phase} bulk_publish_enabled : {used_bulk} -> {mode}")
    if any_bulk:
        print("  result: bulk import API engaged for at least one phase")
    else:
        print("  result: fell back to standard per-item publish for all phases")
        print(
            "  reason: parameter.yml uses $items/$workspace dynamic variables, "
            "which bulk cannot resolve, so fabric-cicd reverts to standard mode"
        )
    print("=" * 70)


def main() -> None:
    credential = ClientSecretCredential(
        tenant_id=os.environ["AZURE_TENANT_ID"],
        client_id=os.environ["AZURE_CLIENT_ID"],
        client_secret=os.environ["AZURE_CLIENT_SECRET"],
    )

    # If item_type_in_scope is provided as a JSON array (e.g., '["Notebook"]'),
    # only those item types are deployed. Otherwise, all types are in scope.
    item_type_in_scope: list[str] | None = None
    raw = os.environ.get("ITEM_TYPE_IN_SCOPE", "").strip()
    if raw:
        item_type_in_scope = json.loads(raw)

    repo_dir = os.environ["REPOSITORY_DIRECTORY"]
    workspace_id = os.environ["FABRIC_WORKSPACE_ID"]
    environment = os.environ["ENVIRONMENT"]

    # Enable fabric-cicd's experimental bulk publish. Feature flags are
    # process-global, so this applies to every publish_all_items() call below.
    for flag in BULK_FEATURE_FLAGS:
        append_feature_flag(flag)

    phase_bulk_results: dict[str, bool] = {}

    print("Phase 1: Deploying Lakehouse + Ontology (bulk publish requested)...")
    phase1_ws = FabricWorkspace(
        repository_directory=repo_dir,
        workspace_id=workspace_id,
        environment=environment,
        token_credential=credential,
        item_type_in_scope=PHASE1_TYPES,
    )
    publish_all_items(phase1_ws)
    phase_bulk_results["phase 1"] = bool(phase1_ws.bulk_publish_enabled)

    # Phase 2: Deploy all remaining item types.
    remaining = remaining_types_for_phase2(item_type_in_scope)
    print(
        "Phase 2: Deploying remaining items: "
        + str(remaining or "all")
        + " (bulk publish requested)..."
    )
    workspace = FabricWorkspace(
        repository_directory=repo_dir,
        workspace_id=workspace_id,
        environment=environment,
        token_credential=credential,
        item_type_in_scope=remaining,
    )
    publish_all_items(workspace)
    phase_bulk_results["phase 2"] = bool(workspace.bulk_publish_enabled)
    unpublish_all_orphan_items(workspace)

    print_fallback_proof(
        contains_param_vars=bool(workspace.contains_param_vars),
        phase_bulk_results=phase_bulk_results,
    )

    # Optional guardrail: fail loudly if bulk publish was actually used, i.e.,
    # the expected fallback did NOT happen (parameter.yml stopped using dynamic
    # variables). Off by default so the demo deploy always succeeds.
    if _env_flag("FAIL_IF_BULK_USED") and any(phase_bulk_results.values()):
        message = (
            "FAIL_IF_BULK_USED is set but bulk publish engaged; a fallback to "
            "standard was expected for this repository's parameter.yml."
        )
        print(f"::error::{message}")
        sys.exit(message)


if __name__ == "__main__":
    main()
