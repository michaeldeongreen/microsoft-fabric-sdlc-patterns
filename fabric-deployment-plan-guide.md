# Deployment Plan CI/CD Guide

Two independent repository-owned adapters read a committed Fabric Deployment
Plan: `fabric-cicd-plan` uses sequential non-bulk publishing, and
`fabric-cicd-bulk` combines independent ready groups into strict fabric-cicd bulk
selections. Each replaces hard-coded phases in its own method. The default non-bulk
`fabric-cicd` and raw REST `bulk` implementations remain available and unchanged.

These are ordering-only solution accelerators, not native Deployment Plan
execution. Deployment Plans are in preview, and the fabric-cicd item-inclusion
API used here is experimental. Validate the method in Test before production.
Native Fabric Deployment Pipelines are a separate service and are not invoked
by either adapter. Use the [README comparison](README.md#choose-a-deployment-method)
to choose a route and the [shared workflow reference](fabric-hybrid-cicd-guide.md#github-actions-workflows)
to locate its caller and runner.

> Support boundary: fabric-cicd maintainers describe selective deployment as
> [not a best practice](https://github.com/microsoft/fabric-cicd/issues/384)
> and state that it is
> [not officially supported or recommended](https://github.com/microsoft/fabric-cicd/issues/290#issuecomment-2881790140).
> Use this bridge with explicit ownership, complete dependency definitions,
> nonproduction validation, and a rollback route to the standard full-deployment
> method. It is intended for advanced teams evaluating a documented gap, not as
> a new default for every fabric-cicd customer.

## How It Works

This walkthrough describes **fabric-cicd non-bulk + client-read plan** (`fabric-cicd-plan`). fabric-cicd bulk reads the
same supported plan format but groups independent ready items; its instructions
begin at [Isolated Bulk Adapter](#isolated-bulk-adapter-14x).

<pre>
<a href=".github/workflows/deploy-test-fabric-cicd-plan.yml">deploy-test-fabric-cicd-plan.yml</a> / <a href=".github/workflows/deploy-prod-fabric-cicd-plan.yml">deploy-prod-fabric-cicd-plan.yml</a>
  (orchestrator workflows)
  -&gt; <a href=".github/workflows/reusable-deploy-fabric-cicd-plan.yml">reusable-deploy-fabric-cicd-plan.yml</a> (reusable workflow)
     -&gt; <a href="scripts/deploy_fabric_cicd_non_bulk_plan.py">deploy_fabric_cicd_non_bulk_plan.py</a> (deployment adapter)
        -&gt; <a href="scripts/deployment_plan.py">deployment_plan.py</a> (plan reader and scheduler)
        -&gt; validate the committed plan and repository inventory
        -&gt; publish declared items in dependency order
        -&gt; publish remaining in-scope items
        -&gt; clean up eligible orphaned items
  -&gt; <a href=".github/workflows/etl-test.yml">etl-test.yml</a> / <a href=".github/workflows/etl-prod.yml">etl-prod.yml</a> (ETL workflows), after successful deployment
</pre>

[deploy_fabric_cicd_non_bulk_plan.py](scripts/deploy_fabric_cicd_non_bulk_plan.py) calls
[deployment_plan.py](scripts/deployment_plan.py), which reads
[plan.yml](data/fabric/DeploymentPlan.DeploymentPlan/plan.yml) from the same Git
revision as the item definitions.
[deployment_plan.py](scripts/deployment_plan.py) matches group logical IDs
against each item's
[`.platform` metadata](data/fabric/PatternsLakehouse.Lakehouse/.platform), not
physical workspace item IDs. Connections between groups become `dependsOn`
entries; group position in the YAML or canvas does not establish order.

This matching method follows Fabric's identity model. Microsoft defines the
logical ID as the automatically generated, cross-workspace identity that binds
a Fabric item to its Git representation. Deployment Plan groups use that same
logical ID so the plan remains valid as items move between workspaces. See
[Logical IDs in Fabric Git integration](https://learn.microsoft.com/fabric/cicd/git-integration/logical-id-conflict-resolution)
and [Deployment Plan examples](https://learn.microsoft.com/fabric/cicd/deployment-plan/deployment-plan-sample-plans#understand-the-planyml-structure).

[deployment_plan.py](scripts/deployment_plan.py) rejects missing, zero,
malformed, and duplicate logical IDs before authentication or deployment. The
remaining risk is metadata drift: replacing a logical ID while resolving a Git
conflict changes the item's identity and requires the committed plan to be
updated. Preserve Fabric-generated logical IDs and review metadata-overwrite
prompts before accepting them.

The current plan contains four groups:

```text
                     ┌──> SemanticModel_Group
Lakehouse_Group ─────┤
                     └──> Ontology_Group ───> DataAgent_Group
```

These groups deploy `PatternsLakehouse`, `Patterns_Semantic_Model`,
`Patterns_Ontology`, and `Patterns_Data_Agent`, respectively.

In the non-bulk method, each declared item gets a separate `publish_all_items(..., items_to_include=...)`
call with fresh workspace state. Later calls can therefore resolve the target
IDs created by earlier calls. Independent groups run sequentially in a
deterministic order, not in parallel.

[deployment_plan.py](scripts/deployment_plan.py) discovers the remaining items
from repository metadata and `ITEM_TYPE_IN_SCOPE`.
[deploy_fabric_cicd_non_bulk_plan.py](scripts/deploy_fabric_cicd_non_bulk_plan.py) publishes
those items in one additional library call using fabric-cicd's standard order.
Here the remaining items are the report, Variable Library, and three notebooks.
These are library calls, not single HTTP requests. The DeploymentPlan control
item is not published or orphan-cleaned.

## Isolated Bulk Adapter (1.4.x)

[deploy_fabric_cicd_bulk.py](scripts/deploy_fabric_cicd_bulk.py) calls
[deployment_plan_bulk.py](scripts/deployment_plan_bulk.py). Bulk owns its
inventory, safe YAML parsing, validation, scheduler, and orchestration; neither
module imports the non-bulk plan implementation. Both readers support the same
ordering-only schema, but the Python code is deliberately isolated.

Only explicit `dependsOn` determines readiness. Independent ready groups are
combined into one exact fabric-cicd selection, not sent in parallel. The current plan
and inventory produce:

| Selection | Items | Count |
|---|---|---|
| Ready batch 1 | Lakehouse | 1 |
| Ready batch 2 | Ontology + Semantic Model | 2 |
| Ready batch 3 | Data Agent | 1 |
| Remainder | Report, Variable Library, three Notebooks | 5 |

The table is a fixture result, not a hardcoded type order. Changing authored
dependencies changes the batches. Every call uses fresh workspace state,
explicit item types, and exact `Name.ItemType` inclusion selectors.
fabric-cicd may split a selection into additional internal dependency batches for
other repositories; one library call is not a fixed HTTP request count.

### Enable and Preview Bulk

Promote the updated code and workflows through the existing controls before
changing repository-wide routing. Copy the two repository-variable values from
[Setup: fabric-cicd-bulk settings](SETUP.md#fabric-cicd-bulk-settings), and use
the shared environment secrets there. Select this route only when ready for
approved Test validation.
The Test and Prod callers already supply the seven-type explicit scope.
Unlike non-bulk, an omitted or empty scope is an error, not an all-types default.

From the checkout root, with dependencies installed:

```powershell
$env:ITEM_TYPE_IN_SCOPE = '["Lakehouse","Ontology","VariableLibrary","Notebook","SemanticModel","Report","DataAgent"]'
python scripts\deploy_fabric_cicd_bulk.py --plan data\fabric\DeploymentPlan.DeploymentPlan\plan.yml --dry-run
```

The preview returns `batches`, `remainingItems`, `itemTypesInScope`,
`cleanupItemTypes`, and the installed fabric-cicd version without credentials or Fabric
calls. A missing/invalid plan never restores phases or switches methods.
When `ENVIRONMENT` is supplied, preview also checks selected Variable Library
value-set metadata; it remains optional for a local credentials-free preview.
Both bulk workflows preview before receiving Azure/Fabric secrets in the
deployment step. Their path filters cover Fabric definitions, `deployment-plans/`,
the bulk-only scripts, dependencies, and workflows. Add a custom plan directory
to both caller filters if it is stored elsewhere.

<a id="sdk-replacements-and-strict-success"></a>

### fabric-cicd Replacements and Strict Success

fabric-cicd 1.4.0 supports this repository's five filtered dynamic rules in
[parameter.yml](data/fabric/parameter.yml) with bulk enabled. fabric-cicd owns
replacement and Test/Prod value-set activation. Bulk does not port the raw
REST find/replace engine or read [bulk-parameter.yml](data/fabric/bulk-parameter.yml).
Before live authentication, the adapter requires each selected Variable Library
to declare the exact environment name and contain its matching value-set file.
Missing/mismatched metadata fails rather than letting fabric-cicd activate Default
or silently skip activation. It does not make a second activation PATCH.

To keep that check valid after parameterization, an authenticated, read-only fabric-cicd
rule preflight runs for all selected libraries before the first definition
import, then again for each selection. This is not part of `--dry-run`.
Library `settings.json` and `valueSets/*.json`, including override bodies, must
remain literal. Active `find_replace` rules with matching control-file content
are rejected. Any `key_value_replace` rule whose filters include those files is
also rejected: fabric-cicd reserializes JSON even without a matching key or
environment, which can enable a later text rule to change activation metadata.
Scope library key-value rules to `**/variables.json`; ordinary workload files
and library variables still use fabric-cicd parameterization. The five committed rules
are unaffected. This is a conservative adapter safety restriction, not an
upstream fabric-cicd limitation.

The adapter requests experimental features, bulk publishing, item inclusion,
and response collection. It rejects bulk-ineligible types and uses the bounded
fabric-cicd 1.4.x read-only eligibility helper to reject unfiltered current-workspace
`$items` rules before publishing. It uses public publishing APIs, not private
transport calls or fabric-cicd patches.

After each selection it requires actual `bulk_publish_enabled=True` and
complete, correctly identified per-item results with `operationStatus=Succeeded`
and valid target IDs. Failed, partially successful, unknown, missing, or malformed
results stop dependent selections, the remainder, and orphan cleanup.
The mode check runs after `publish_all_items` returns: known fallback causes
are rejected before publishing, but an unexpected fallback may already have
performed standard writes. Failing the run does not undo them.
`FAIL_IF_BULK_USED` and `fail_if_bulk_used` have been removed; choosing this route
requires genuine bulk. For standard publishing, select the standard route.

Only after successful publishing does the adapter run the existing fabric-cicd orphan
cleanup once. Lakehouse, Ontology, and DeploymentPlan remain excluded. Inventory
GETs, fabric-cicd post-hooks/activation PATCHes, and cleanup DELETEs are legitimate
separate requests, not standard definition-publish fallback.

### Verified Client Behavior and Remaining Service Checks

[The bulk contract tests](tests/test_deploy_fabric_cicd_bulk.py) run the actual
released 1.4.0 publishing and parameterization code with only HTTP mocked and
real requests blocked. Cold/warm Test/Prod fixtures observe four bulk imports
each (sixteen total), with the parameter file present, correct physical
replacements and activation requests, and zero standard definition POSTs.
They also cover partial/failed/missing results, invalid parameters, cleanup
exclusions, and unchanged source files. Adversarial-review regressions reject
activation-metadata substitutions and chained key-value/text rules before any
definition import, activation, or cleanup, while allowing inactive/nonmatching
text rules and valid key-value replacement scoped to library variables.

The bulk payload retains the Report's `datasetReference.byPath`; it does not
perform standard publishing's `byConnection` rewrite. The plan puts the
Semantic Model before the Report, but live Test must still verify the Report
binding and Lakehouse-to-Ontology / Ontology-to-DataAgent relationships across
imports. Mocked client success is not service-side binding, capacity, connection,
active-value-set, or ETL evidence. Use an approved disposable cold-start target
and a warm repeat; never clear a shared workspace.

## 1.4.0 Release Applicability

All fabric-cicd workflows and [requirements-dev.txt](requirements-dev.txt) use
`fabric-cicd>=1.4.0,<1.5.0`; the bulk adapter rejects incompatible versions.
Actions remain on Python 3.12. The exact 1.4.0 lower boundary is tested.

| Release change | Treatment here |
|---|---|
| Bulk dynamic variables and early syntax validation | Exercise actual fabric-cicd replacements and reject invalid syntax before definition writes; test missing resources separately. |
| Removed `contains_param_vars` attribute | Remove the old reporting dependency; item-variable presence is not proof of fallback. |
| GraphModel and CosmosDBDatabase support | No standalone items of those types exist here. Do not expand publish/cleanup scope or remove Ontology setup caveats. |
| Python 3.14 support | Inherited upstream capability, not a reason to change this repository's Actions runtime. |
| KQLQueryset, PaginatedReport, and Activator fixes | Inherit the fixes; these item types are not in this inventory. `Report` is not `PaginatedReport`. |
| Semantic Model connection trailing-slash fix | Applies to fabric-cicd `bindConnection` requests; no `semantic_model_binding` is configured here. Do not claim all connection setup is solved. |
| `$ENV:` name handling | No such rules here; the raw REST `$environment` placeholder is a different DSL. |
| jsonpath-ng regression bound | Respect fabric-cicd's `>=1.7.0,<1.8.0` transitive constraint; no redundant direct pin. No active `key_value_replace` rules are added. |
| New end-to-end tutorial | Reference material, not a replacement for the repository's architecture. |

See the [versioned changelog](https://microsoft.github.io/fabric-cicd/1.4.0/changelog/#v140-october-07-2026)
and [bulk limitations](https://microsoft.github.io/fabric-cicd/1.4.0/how_to/optional_feature/#bulk-publish).

## Workflows and Scripts

The files below implement the **non-bulk plan route**. For the bulk counterpart
and all other workflow families, use the
[shared workflow reference](fabric-hybrid-cicd-guide.md#github-actions-workflows).

| File | Role |
|---|---|
| [deploy-test-fabric-cicd-plan.yml](.github/workflows/deploy-test-fabric-cicd-plan.yml) | Deploys on qualifying pushes to `test`; also supports manual runs on `test` |
| [deploy-prod-fabric-cicd-plan.yml](.github/workflows/deploy-prod-fabric-cicd-plan.yml) | Deploys on qualifying pushes to `main`, using the protected `Prod` environment |
| [reusable-deploy-fabric-cicd-plan.yml](.github/workflows/reusable-deploy-fabric-cicd-plan.yml) | Installs dependencies, previews the schedule, and runs [deploy_fabric_cicd_non_bulk_plan.py](scripts/deploy_fabric_cicd_non_bulk_plan.py) |
| [deploy_fabric_cicd_non_bulk_plan.py](scripts/deploy_fabric_cicd_non_bulk_plan.py) | Authenticates with `ClientSecretCredential` and orchestrates public fabric-cicd calls |
| [deployment_plan.py](scripts/deployment_plan.py) | Validates the supported plan format and calculates the declared order and remainder |

[deploy-test-fabric-cicd-plan.yml](.github/workflows/deploy-test-fabric-cicd-plan.yml)
and [deploy-prod-fabric-cicd-plan.yml](.github/workflows/deploy-prod-fabric-cicd-plan.yml)
use the same environment-scoped secrets and seven-type scope as the standard
method. No additional source-workspace credential is needed. The existing
[etl-test.yml](.github/workflows/etl-test.yml) and
[etl-prod.yml](.github/workflows/etl-prod.yml) listeners recognize the new
workflow names; [deploy_fabric_cicd_non_bulk_plan.py](scripts/deploy_fabric_cicd_non_bulk_plan.py)
does not run ETL itself.

## Enable the Method

This section enables **`fabric-cicd-plan`**, not fabric-cicd bulk. For
`fabric-cicd-bulk`, follow [Enable and Preview Bulk](#enable-and-preview-bulk).

Complete the [Setup Guide](SETUP.md) first. Keep the existing method selected
while promoting
[deploy-test-fabric-cicd-plan.yml](.github/workflows/deploy-test-fabric-cicd-plan.yml),
[deploy-prod-fabric-cicd-plan.yml](.github/workflows/deploy-prod-fabric-cicd-plan.yml),
and [reusable-deploy-fabric-cicd-plan.yml](.github/workflows/reusable-deploy-fabric-cicd-plan.yml)
through `dev -> test -> main`.
GitHub reads `workflow_run` listeners from the default branch, and a manually
dispatched workflow must exist there too. Changing the selector before that
rollout can leave Test without its automatic ETL follow-up.

In repository Settings > Secrets and variables > Actions > Variables, set:

| Variable | Value |
|---|---|
| `DEPLOYMENT_PLAN_PATH` | [`data/fabric/DeploymentPlan.DeploymentPlan/plan.yml`](data/fabric/DeploymentPlan.DeploymentPlan/plan.yml) |
| `DEPLOY_METHOD` | `fabric-cicd-plan` |

Then:

1. Ensure no deployment from the previous method is still running.
2. In Actions, choose `Deploy to Test (fabric-cicd Plan)` and run it with branch
   `test`, or merge a qualifying change into `test`.
3. Review the schedule, deployment, and ETL results using the checks below.
4. Promote to `main` after Test passes. The existing `Prod` approval gate applies.

A manual [deploy-test-fabric-cicd-plan.yml](.github/workflows/deploy-test-fabric-cicd-plan.yml)
run on another branch is skipped.
[deploy-test-fabric-cicd-plan.yml](.github/workflows/deploy-test-fabric-cicd-plan.yml)
and [deploy-prod-fabric-cicd-plan.yml](.github/workflows/deploy-prod-fabric-cicd-plan.yml)
do not cancel an already-running plan deployment; concurrency is controlled
separately for Test and Prod. This does not coordinate a run from another
deployment method.

[deploy-test-fabric-cicd-plan.yml](.github/workflows/deploy-test-fabric-cicd-plan.yml)
and [deploy-prod-fabric-cicd-plan.yml](.github/workflows/deploy-prod-fabric-cicd-plan.yml)
trigger for changes to Fabric definitions, `deployment-plans/`, the new scripts,
requirements, and workflow files. If a customer stores the plan elsewhere, add
that directory to the `paths` list in both files.

## Preview and Customize

The command below previews **non-bulk ordering**. The
[bulk preview](#enable-and-preview-bulk) reports ready batches instead of a
sequential group list.

From the repository root, after installing [requirements-dev.txt](requirements-dev.txt):

The command invokes
[deploy_fabric_cicd_non_bulk_plan.py](scripts/deploy_fabric_cicd_non_bulk_plan.py) with the
committed [plan.yml](data/fabric/DeploymentPlan.DeploymentPlan/plan.yml).

```powershell
python scripts\deploy_fabric_cicd_non_bulk_plan.py --plan data\fabric\DeploymentPlan.DeploymentPlan\plan.yml --dry-run
```

The JSON output lists `groups` in execution order, `remainingItems`,
`itemTypesInScope`, and `cleanupItemTypes`. Dry-run requires no Azure credentials
and makes no Fabric calls. It validates local metadata and the authored graph;
it does not verify tenant permissions, live bindings, or data readiness.

To customize:

- Edit and commit the plan in Fabric, or select another committed plan with
  `DEPLOYMENT_PLAN_PATH`. Paths are relative to the repository checkout.
- Declare the items whose placement matters, including prerequisites of those
  items. [deploy_fabric_cicd_non_bulk_plan.py](scripts/deploy_fabric_cicd_non_bulk_plan.py)
  publishes unlisted items after all declared groups.
- Keep Before/After sections empty. They run jobs in native Fabric execution;
  they are not lists of items to deploy next.
- Keep every item's logical ID nonzero, stable, and unique, including unlisted
  items. Fabric Git integration supplies these portable identifiers.
- Adjust the item-type scope in
  [deploy-test-fabric-cicd-plan.yml](.github/workflows/deploy-test-fabric-cicd-plan.yml)
  and [deploy-prod-fabric-cicd-plan.yml](.github/workflows/deploy-prod-fabric-cicd-plan.yml)
  when adding supported workload types. A group outside that scope is an error,
  not an implicit scope expansion.

The report need not have its own group here because its Semantic Model is
deployed before the remainder. A 500-item repository can likewise use a short
plan for its ordering-critical items; it does not need one group for every item.
Dependencies hidden in code or missing from the plan are not discovered.
Customers own the completeness of the declared dependency graph; fabric-cicd
does not validate that selective calls include every prerequisite.

## Configuration and Failure Boundaries

This section describes **fabric-cicd non-bulk + client-read plan** behavior. fabric-cicd bulk's additional mode,
response, and Variable Library guards are documented under
[fabric-cicd Replacements and Strict Success](#fabric-cicd-replacements-and-strict-success).

fabric-cicd still applies [parameter.yml](data/fabric/parameter.yml), resolves
physical IDs, and selects the Variable Library value set for `Test` or `Prod`.
Keep source IDs and replacement rules aligned, and restore Dev bindings before
promotion as described in the [Development Process](fabric-development-process.md).
Reading a plan does not replace parameterization.
Environment/value-set names must match exactly. fabric-cicd warns and falls
back to the default value set if no name matches; keep the committed `Test`
and `Prod` sets and verify the active set after deployment.

[deployment_plan.py](scripts/deployment_plan.py) rejects missing items,
ambiguous names/IDs, cycles, unsupported schema versions, and nonempty actions
or group options. It supports the 1.0.0 ordering format, at most 1,000 groups,
and plan files up to 1 MiB. More declared groups mean more sequential library
calls and workspace discovery.

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
not attach or execute the plan. The standard runner and the non-bulk plan logic
remain unchanged; library bulk now has its own isolated ordering adapter.

## Verify Before Production

Use an approved Test target and check:

- The log names the installed fabric-cicd version and the selected standard or
  strict bulk publishing mode.
- All four declared items and five remaining items deploy without duplication.
- Targeted Notebook and Semantic Model fields and the Variable Library
  Lakehouse ID contain the expected replacements. Intentional Dev defaults
  overridden by active value sets need not disappear from every file.
- For bulk, verify the Report/model and logical-ID bindings across imports;
  do not infer them from the client request tests.
- The correct value set is active before the existing ETL workflow runs once.
- A second deployment updates the same item IDs rather than creating duplicates.
- Cleanup affects only the expected orphaned items and types.

The [clean-workspace caveats](fabric-hybrid-cicd-guide.md#initial-deployment-to-a-clean-workspace)
still apply, including Ontology/Graph Model initialization. Deploying a notebook
does not populate tables; ordering alone does not replace ETL or connection setup.
Offline tests cover scheduling and fabric-cicd parameterization with a mocked transport;
they are not evidence of a successful live deployment in your tenant.

## Relationship to Native Deployment Plans

Native Fabric execution combines plan relationships with detected lineage and
can execute actions.
[deploy_fabric_cicd_non_bulk_plan.py](scripts/deploy_fabric_cicd_non_bulk_plan.py) enforces only
declared ordering through non-bulk fabric-cicd;
[deploy_fabric_cicd_bulk.py](scripts/deploy_fabric_cicd_bulk.py) does so through
grouped bulk calls. Neither attaches a plan or executes native Before/After
actions. The DeploymentPlan control item is not imported or orphan-cleaned.

Fabric REST accepts `options.deploymentPlan`, but fabric-cicd 1.4.0 does not
expose it in its public publishing API. Keep the isolated bulk adapter a bridge
that can be replaced when suitable native fabric-cicd bulk integration is released and
verified. That does not imply native non-bulk support or retire the independent
non-bulk example.

Retest fabric-cicd upgrades. When migrating bulk to native plan execution, reassess
unlisted items, actions, permissions, failure handling, and parameterization:
Fabric combines the native plan with lineage/standard ordering, whereas these
adapters deliberately deploy unlisted items after the authored groups.

References: [Fabric plan automation](https://learn.microsoft.com/fabric/cicd/deployment-plan/deployment-plan-automation),
[plan semantics and limitations](https://learn.microsoft.com/fabric/cicd/deployment-plan/deployment-plan-overview),
and [fabric-cicd item inclusion](https://microsoft.github.io/fabric-cicd/1.4.0/how_to/optional_feature/#item-level-filtering).
