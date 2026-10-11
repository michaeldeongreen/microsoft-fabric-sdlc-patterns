"""Deploy supported Fabric items via non-bulk fabric-cicd.

Staged publication to satisfy item dependencies:

- Phase 1: Lakehouse + Ontology
    - Lakehouse must exist so parameter.yml ``$items.Lakehouse`` rules resolve.
    - Ontology must exist so DataAgent's logicalId reference resolves.
- Phase 2: Remaining items except DataPipeline.
- Phase 3, when selected: DataPipeline after its notebooks and model exist.

fabric-cicd caches workspace state once at the start of each
``publish_all_items()`` call, so items deployed within the same call are not
visible to later items' logicalId or ``$items`` resolution. On subsequent
deployments all items already exist and phases are idempotent — they simply
update in place.

Invoked by .github/workflows/reusable-deploy-fabric-cicd.yml.

Required environment variables:
    AZURE_TENANT_ID, AZURE_CLIENT_ID, AZURE_CLIENT_SECRET,
    FABRIC_WORKSPACE_ID, REPOSITORY_DIRECTORY, ENVIRONMENT
Optional:
    ITEM_TYPE_IN_SCOPE — JSON array of item types to deploy. Defaults to all.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from azure.identity import ClientSecretCredential
from fabric_cicd import (
    FabricWorkspace,
    append_feature_flag,
    publish_all_items,
    unpublish_all_orphan_items,
)
from pipeline_bindings import require_pipeline_connections

PHASE1_TYPES = ["Lakehouse", "Ontology"]


def remaining_types_for_phase2(item_type_in_scope: list[str] | None) -> list[str] | None:
    """Compute Phase 2 scope by subtracting Phase 1 types from the user's filter.

    Returns ``None`` when:

    - ``item_type_in_scope`` is None or empty (deploy everything in Phase 2)
    - The caller passed only Phase 1 types (nothing distinct left for Phase 2)

    Note: returning ``None`` means "all types" to ``FabricWorkspace``. So if a
    caller explicitly listed only Phase 1 types (e.g., ``["Lakehouse",
    "Ontology"]``), Phase 2 will deploy everything else too. This is a known
    behavior of the env-var contract — callers wanting strict scoping should
    include the non-Phase-1 types they want.
    """
    if not item_type_in_scope:
        return None
    phase1_set = set(PHASE1_TYPES)
    remaining = [t for t in item_type_in_scope if t not in phase1_set]
    return remaining or None


def main() -> None:
    # If item_type_in_scope is provided as a JSON array (e.g., '["Notebook"]'),
    # only those item types will be deployed. Otherwise, all types are in scope.
    item_type_in_scope: list[str] | None = None
    raw = os.environ.get("ITEM_TYPE_IN_SCOPE", "").strip()
    if raw:
        item_type_in_scope = json.loads(raw)

    repo_dir = os.environ["REPOSITORY_DIRECTORY"]
    workspace_id = os.environ["FABRIC_WORKSPACE_ID"]
    environment = os.environ["ENVIRONMENT"]
    require_pipeline_connections(repo_dir)
    credential = ClientSecretCredential(
        tenant_id=os.environ["AZURE_TENANT_ID"],
        client_id=os.environ["AZURE_CLIENT_ID"],
        client_secret=os.environ["AZURE_CLIENT_SECRET"],
    )
    append_feature_flag("enable_environment_variable_replacement")

    print("Phase 1: Deploying Lakehouse + Ontology...")
    phase1_ws = FabricWorkspace(
        repository_directory=repo_dir,
        workspace_id=workspace_id,
        environment=environment,
        token_credential=credential,
        item_type_in_scope=PHASE1_TYPES,
    )
    publish_all_items(phase1_ws)

    # Phase 2: Deploy all remaining item types.
    remaining = remaining_types_for_phase2(item_type_in_scope)
    pipelines = list(Path(repo_dir).glob("*.DataPipeline/pipeline-content.json"))
    include_pipelines = bool(pipelines) and (remaining is None or "DataPipeline" in remaining)
    phase2_types = remaining
    if include_pipelines:
        phase2_types = [
            item_type for item_type in (
                remaining or sorted({p.parent.name.rsplit(".", 1)[-1] for p in Path(repo_dir).glob("*/.platform")})
            ) if item_type not in ("DataPipeline", "DeploymentPlan", *PHASE1_TYPES)
        ]
    if not include_pipelines or phase2_types:
        print("Phase 2: Deploying remaining items: " + str(phase2_types or "all") + "...")
        workspace = FabricWorkspace(
            repository_directory=repo_dir,
            workspace_id=workspace_id,
            environment=environment,
            token_credential=credential,
            item_type_in_scope=phase2_types,
        )
        publish_all_items(workspace)
    if include_pipelines:
        print("Phase 3: Deploying DataPipeline after notebook and Semantic Model publication...")
        pipeline_workspace = FabricWorkspace(
            repository_directory=repo_dir,
            workspace_id=workspace_id,
            environment=environment,
            token_credential=credential,
            item_type_in_scope=["DataPipeline"],
        )
        publish_all_items(pipeline_workspace)
        workspace = FabricWorkspace(
            repository_directory=repo_dir,
            workspace_id=workspace_id,
            environment=environment,
            token_credential=credential,
            item_type_in_scope=[*(phase2_types or []), "DataPipeline"],
        )
    unpublish_all_orphan_items(workspace)


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, KeyError) as exc:
        print(f"::error::{exc}", file=sys.stderr)
        sys.exit(1)
