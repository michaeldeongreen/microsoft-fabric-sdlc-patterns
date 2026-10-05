# Deployment Plan CI/CD Guide

This optional deployment method reads a committed Fabric Deployment Plan and
uses standard, non-bulk fabric-cicd to publish items in the declared order.
It replaces hard-coded deployment phases in this method only. The existing
`fabric-cicd`, `bulk`, and `fabric-cicd-bulk` methods remain available.

This is an ordering-only solution accelerator, not native Deployment Plan
execution. Deployment Plans are in preview, and the fabric-cicd item-inclusion
API used here is experimental. Validate the method in Test before production.

## How It Works

```text
Test / Prod orchestrator
  -> reusable-deploy-fabric-cicd-plan.yml
     -> deploy_fabric_cicd_plan.py
        -> validate the committed plan and repository inventory
        -> publish declared items in dependency order
        -> publish remaining in-scope items
        -> clean up eligible orphaned items
  -> existing ETL workflow, after successful deployment
```

The adapter reads [plan.yml](data/fabric/DeploymentPlan.DeploymentPlan/plan.yml)
from the same Git revision as the item definitions. It matches group logical
IDs against item `.platform` metadata, not physical workspace item IDs.
Connections between groups become `dependsOn` entries; group position in the
YAML or canvas does not establish order.

The current plan contains four groups:

```text
PatternsLakehouse -> Patterns_Semantic_Model
PatternsLakehouse -> Patterns_Ontology -> Patterns_Data_Agent
```

Each declared item gets a separate `publish_all_items(..., items_to_include=...)`
call with fresh workspace state. Later calls can therefore resolve the target
IDs created by earlier calls. Independent groups run sequentially in a
deterministic order, not in parallel.

The adapter discovers the remaining items from repository metadata and
`ITEM_TYPE_IN_SCOPE`. Here those are the report, Variable Library, and three
notebooks. They are published in one additional library call using
fabric-cicd's standard order. These are library calls, not single HTTP requests.
The DeploymentPlan control item is not published or orphan-cleaned.

## Workflows and Scripts

| File | Role |
|---|---|
| [deploy-test-fabric-cicd-plan.yml](.github/workflows/deploy-test-fabric-cicd-plan.yml) | Deploys on qualifying pushes to `test`; also supports manual runs on `test` |
| [deploy-prod-fabric-cicd-plan.yml](.github/workflows/deploy-prod-fabric-cicd-plan.yml) | Deploys on qualifying pushes to `main`, using the protected `Prod` environment |
| [reusable-deploy-fabric-cicd-plan.yml](.github/workflows/reusable-deploy-fabric-cicd-plan.yml) | Installs dependencies, previews the schedule, and runs the adapter |
| [deploy_fabric_cicd_plan.py](scripts/deploy_fabric_cicd_plan.py) | Authenticates with `ClientSecretCredential` and orchestrates public fabric-cicd calls |
| [deployment_plan.py](scripts/deployment_plan.py) | Validates the supported plan format and calculates the declared order and remainder |

The new orchestrators use the same environment-scoped secrets and seven-type
scope as the standard method. No additional source-workspace credential is
needed. The existing [Test](.github/workflows/etl-test.yml) and
[Prod](.github/workflows/etl-prod.yml) ETL listeners recognize the new workflow
names; the adapter does not run ETL itself.

## Enable the Method

Complete the [Setup Guide](SETUP.md) first. Keep the existing method selected
while promoting the new workflow files through `dev -> test -> main`.
GitHub reads `workflow_run` listeners from the default branch, and a manually
dispatched workflow must exist there too. Changing the selector before that
rollout can leave Test without its automatic ETL follow-up.

In repository Settings > Secrets and variables > Actions > Variables, set:

| Variable | Value |
|---|---|
| `DEPLOYMENT_PLAN_PATH` | `data/fabric/DeploymentPlan.DeploymentPlan/plan.yml` |
| `DEPLOY_METHOD` | `fabric-cicd-plan` |

Then:

1. Ensure no deployment from the previous method is still running.
2. In Actions, choose `Deploy to Test (fabric-cicd Plan)` and run it with branch
   `test`, or merge a qualifying change into `test`.
3. Review the schedule, deployment, and ETL results using the checks below.
4. Promote to `main` after Test passes. The existing `Prod` approval gate applies.

A manual Test run on another branch is skipped. The new workflows do not cancel
an already-running plan deployment; concurrency is controlled separately for
Test and Prod. This does not coordinate a run from another deployment method.

The workflows trigger for changes to Fabric definitions, `deployment-plans/`,
the new scripts, requirements, and workflow files. If a customer stores the
plan elsewhere, add that directory to both orchestrators' path filters.

## Preview and Customize

From the repository root, after installing [requirements-dev.txt](requirements-dev.txt):

```powershell
python scripts\deploy_fabric_cicd_plan.py --plan data\fabric\DeploymentPlan.DeploymentPlan\plan.yml --dry-run
```

The JSON output lists `groups` in execution order, `remainingItems`,
`itemTypesInScope`, and `cleanupItemTypes`. Dry-run requires no Azure credentials
and makes no Fabric calls. It validates local metadata and the authored graph;
it does not verify tenant permissions, live bindings, or data readiness.

To customize:

- Edit and commit the plan in Fabric, or select another committed plan with
  `DEPLOYMENT_PLAN_PATH`. Paths are relative to the repository checkout.
- Declare the items whose placement matters, including prerequisites of those
  items. Unlisted items run after all declared groups in this adapter.
- Keep Before/After sections empty. They run jobs in native Fabric execution;
  they are not lists of items to deploy next.
- Keep every item's logical ID nonzero, stable, and unique, including unlisted
  items. Fabric Git integration supplies these portable identifiers.
- Adjust the orchestrators' item-type scope when adding supported workload
  types. A group outside that scope is an error, not an implicit scope expansion.

The report need not have its own group here because its Semantic Model is
deployed before the remainder. A 500-item repository can likewise use a short
plan for its ordering-critical items; it does not need one group for every item.
Dependencies hidden in code or missing from the plan are not discovered.

## Configuration and Failure Boundaries

fabric-cicd still applies [parameter.yml](data/fabric/parameter.yml), resolves
physical IDs, and selects the Variable Library value set for `Test` or `Prod`.
Keep source IDs and replacement rules aligned, and restore Dev bindings before
promotion as described in the [Development Process](fabric-development-process.md).
Reading a plan does not replace parameterization.
Environment/value-set names must match exactly. fabric-cicd warns and falls
back to the default value set if no name matches; keep the committed `Test`
and `Prod` sets and verify the active set after deployment.

The adapter rejects missing items, ambiguous names/IDs, cycles, unsupported
schema versions, and nonempty actions or group options. It supports the 1.0.0
ordering format, at most 1,000 groups, and plan files up to 1 MiB. More declared
groups mean more sequential library calls and workspace discovery.

Orphan cleanup runs once, only after all publishing succeeds. Like the current
standard workflow, it excludes Lakehouse and Ontology; DeploymentPlan is also
excluded. Cleanup can delete target items absent from the repository within the
remaining configured types. Use repository-managed workspaces, not a shared
workspace containing unrelated items of those types. The library can also
remove empty workspace folders during cleanup.

An exception during publishing or cleanup stops subsequent work and prevents
automatic ETL. Completed changes are not rolled back. Review library warnings
as well; fix failures and inspect partial results before rerunning.
To return to the previous method, restore its `DEPLOY_METHOD` value; that
changes future routing, not the state already deployed.

The raw Bulk collector excludes DeploymentPlan control folders so the new
Git-synced item does not alter that older method's workload payload. It does
not attach or execute the plan. The standard and library-Bulk scripts are
unchanged.

## Verify Before Production

Use an approved Test target and check:

- The log names the installed fabric-cicd version and standard publishing mode.
- All four declared items and five remaining items deploy without duplication.
- Exported Notebook, Semantic Model, and Variable Library definitions contain
  the target workspace/Lakehouse IDs rather than source IDs.
- The correct value set is active before the existing ETL workflow runs once.
- A second deployment updates the same item IDs rather than creating duplicates.
- Cleanup affects only the expected orphaned items and types.

The [clean-workspace caveats](fabric-hybrid-cicd-guide.md#initial-deployment-to-a-clean-workspace)
still apply, including Ontology/Graph Model initialization. Deploying a notebook
does not populate tables; ordering alone does not replace ETL or connection setup.
Offline tests cover scheduling and SDK parameterization with a mocked transport;
they are not evidence of a successful live deployment in your tenant.

## Relationship to Native Deployment Plans

Native Fabric execution combines plan relationships with detected lineage and
can execute actions. This adapter enforces only declared ordering through
non-bulk fabric-cicd; it does not call a native plan-execution operation.
It is intended for customers who want to retain fabric-cicd parameterization
while evaluating explicit ordering.

Retest library upgrades and replace the adapter with a suitable public native
integration when available. Do not assume future support will include non-bulk
publishing or identical handling of unlisted items.

References: [Fabric plan automation](https://learn.microsoft.com/fabric/cicd/deployment-plan/deployment-plan-automation),
[plan semantics and limitations](https://learn.microsoft.com/fabric/cicd/deployment-plan/deployment-plan-overview),
and [fabric-cicd item inclusion](https://microsoft.github.io/fabric-cicd/1.3.0/how_to/optional_feature/#item-level-filtering).
