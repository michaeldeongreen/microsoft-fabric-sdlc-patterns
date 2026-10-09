# Hybrid CI/CD Implementation Guide

This repository implements the **Hybrid CI/CD recommendation** for Microsoft Fabric using **fabric-cicd**. It demonstrates how to deploy Fabric workspace items (Notebooks, Lakehouses, Variable Libraries, Semantic Models, Reports, Ontologies, Data Agents) across environments using GitHub Actions.

This page explains the default fabric-cicd non-bulk route and owns the
[shared workflow reference](#github-actions-workflows) for all four methods.
Dev uses Fabric Git integration; Test/Prod receive API-based deployments.
The native Deployment Pipelines extension in the strategic recommendation is
not implemented by these workflows.

For the full CI/CD strategy, release option comparison, and recommendation rationale, see [fabric-cicd-release-options.md](fabric-cicd-release-options.md).

---

## Table of Contents

- [Architecture Overview](#architecture-overview)
- [Repository Structure](#repository-structure)
- [Deployment Flow](#deployment-flow)
- [GitHub Actions Workflows](#github-actions-workflows)
- [Configuration Strategy](#configuration-strategy)
- [Prerequisites & Setup](#prerequisites--setup)
- [Initial Deployment to a Clean Workspace](#initial-deployment-to-a-clean-workspace)
- [Gotchas & Key Decisions](#gotchas--key-decisions)
- [References](#references)

---

## Architecture Overview

```
Git repo (dev branch)
  │
  │  PR merge → test branch
  ▼
┌─────────────────────────────────────────────────────┐
│  deploy-test.yml (orchestrator)                     │
│                                                     │
│  deploy-fabric-cicd                                 │
│    └─ reusable-deploy-fabric-cicd.yml               │
│       └─ fabric-cicd: publish_all_items()           │
│          (Phase 1: Lakehouse + Ontology)            │
│          (Phase 2: all remaining items)             │
└─────────────────────────────────────────────────────┘
                     │ workflow_run (on success)
                     ▼
┌─────────────────────────────────────────────────────┐
│  etl-test.yml                                       │
│    └─ reusable-fabric-etl.yml                       │
│       └─ Fabric REST API: run notebook by name      │
└─────────────────────────────────────────────────────┘
```

The same pattern applies to Prod (`deploy-prod.yml` → `etl-prod.yml`), triggered on push to `main`.

> Alternative deploy paths exist alongside this default fabric-cicd non-bulk route — raw REST bulk and two fabric-cicd routes with client-read plans — all selected by `DEPLOY_METHOD`. This repository recommends the default non-bulk route as the starting point; see the [method matrix](README.md#choose-a-deployment-method) and the [raw REST guide](fabric-bulk-cicd-guide.md).

For configurable ordering without changing this default path, see the
[Deployment Plan CI/CD Guide](fabric-deployment-plan-guide.md). The independent
`fabric-cicd-plan` and `fabric-cicd-bulk` adapters use the committed plan instead
of fixed phases: sequential standard calls or grouped strict bulk calls,
respectively. Neither executes a native Deployment Plan.

### Branches & Workspaces

| Branch | Workspace | Deployment Method |
|---|---|---|
| `dev` | Dev (microsoft-fabric-sdlc-patterns-dev) | Git-connected via Fabric Git integration |
| `test` | Test (microsoft-fabric-sdlc-patterns-test) | fabric-cicd via GitHub Actions |
| `main` | Prod (microsoft-fabric-sdlc-patterns-prod) | fabric-cicd via GitHub Actions |

- **Dev** workspace is the only Git-connected workspace. Developers branch out from Dev for isolated feature work.
- **Test** and **Prod** workspaces are NOT Git-connected. They receive deployments exclusively through fabric-cicd.

---

## Repository Structure

```
microsoft-fabric-sdlc-patterns/
├── .github/
│   ├── instructions/
│   │   ├── actions.instructions.md          # Copilot instructions for workflow authoring
│   │   └── python.instructions.md           # Copilot instructions for Python scripts
│   └── workflows/
│       ├── deploy-test.yml                       # Orchestrator: push to test → fabric-cicd deploy
│       ├── deploy-prod.yml                       # Orchestrator: push to main → fabric-cicd deploy
│       ├── deploy-test-bulk.yml                  # Alternative orchestrator: bulk API deploy on push to test
│       ├── deploy-prod-bulk.yml                  # Alternative orchestrator: bulk API deploy on push to main
│       ├── etl-test.yml                          # Triggers after any deploy-test* workflow succeeds
│       ├── etl-prod.yml                          # Triggers after any deploy-prod* workflow succeeds
│       ├── reusable-deploy-fabric-cicd.yml       # Template: fabric-cicd deployment
│       ├── reusable-deploy-bulk.yml              # Template: Bulk Import API deployment (Preview)
│       ├── reusable-fabric-etl.yml               # Template: run Notebook via Fabric REST API
│       ├── check-pr-ready.yml                    # PR check: blocks feature IDs from merging to dev
│       ├── run-tests.yml                         # PR check: runs pytest on every PR
│       └── enforce-promotion-path.yml            # PR check: enforces dev→test→main source-branch promotion
├── data/
│   └── fabric/                              # Fabric item definitions (repository_directory)
│       ├── parameter.yml                    # fabric-cicd deploy-time parameterization
│       ├── bulk-parameter.yml               # Bulk path's parameterization (independent format)
│       ├── PatternsLakehouse.Lakehouse/
│       ├── Patterns_Ontology.Ontology/
│       ├── Patterns_Variables.VariableLibrary/
│       │   ├── variables.json
│       │   ├── settings.json
│       │   └── valueSets/
│       │       ├── Test.json
│       │       └── Prod.json
│       ├── Import_Patterns_Data.Notebook/   # ETL notebook (creates Delta tables)
│       ├── Patterns_Patients_Data.Notebook/
│       ├── Patterns_Demo.Notebook/
│       ├── Patterns_Semantic_Model.SemanticModel/
│       ├── Patterns_Report.Report/
│       └── Patterns_Data_Agent.DataAgent/
├── scripts/
│   ├── workspace_swap.py                    # Bootstrap/reset feature branch workspace bindings
│   ├── deploy_fabric_cicd_non_bulk.py       # fabric-cicd deploy (invoked by reusable-deploy-fabric-cicd.yml)
│   ├── deploy_fabric_rest_bulk.py           # Bulk Import API deploy (invoked by reusable-deploy-bulk.yml)
│   └── run_fabric_etl.py                    # Run a Fabric Notebook job (invoked by reusable-fabric-etl.yml)
├── assets/                                  # Architecture diagrams (SVG)
├── fabric-cicd-release-options.md           # CI/CD strategy and release option comparison
├── fabric-hybrid-cicd-guide.md               # This file
├── fabric-development-process.md             # Development process
└── README.md                                # Repository landing page
```

---

## Deployment Flow

### What Triggers What

For the default `fabric-cicd` selector, a qualifying push to `test` runs the
[Test caller](.github/workflows/deploy-test.yml); a qualifying push to `main`
runs the [Prod caller](.github/workflows/deploy-prod.yml). Both watch Fabric
definitions and workflow files. The complete trigger and route map is in the
[shared workflow reference](#github-actions-workflows).

### Deploy Job

Each deploy workflow calls `reusable-deploy-fabric-cicd.yml`, which publishes all supported items from Git to the target workspace using fabric-cicd. It uses a two-phase approach: Phase 1 deploys Lakehouse + Ontology, Phase 2 deploys all remaining items (Variable Library, Notebooks, Semantic Model, Report, Data Agent). Item types are explicitly scoped via `item_type_in_scope`.

The ETL workflow triggers automatically after the deploy workflow completes successfully. If the deploy fails, ETL does not run.

<a id="strict-plan-driven-sdk-bulk-14x"></a>

### fabric-cicd Bulk with a Client-Read Plan (1.4.x)

Selecting `DEPLOY_METHOD=fabric-cicd-bulk` runs
[deploy_fabric_cicd_bulk.py](scripts/deploy_fabric_cicd_bulk.py), not the standard
two-phase runner or the raw REST substitution engine. It requires
`DEPLOYMENT_PLAN_PATH` and an explicit, nonempty bulk-eligible type scope.
[deployment_plan_bulk.py](scripts/deployment_plan_bulk.py) independently reads
and validates the plan; it does not reuse the non-bulk plan modules.

The current plan yields Lakehouse; Semantic Model + Ontology; Data Agent;
then the Report, Variable Library, and three Notebooks. Independent ready groups
share one fabric-cicd selection, not parallel requests. Only successful outcomes release
the next selection. These are plan-derived batches, not new hardcoded phases.

fabric-cicd 1.4.0 applies the existing filtered dynamic replacements from
[parameter.yml](data/fabric/parameter.yml) while using bulk. Its own dependency
batching remains active within each call. The adapter rejects known fallback
conditions, checks actual bulk mode and complete per-item success, and performs
the existing eligible orphan cleanup once after successful publishing.
The actual-mode check runs after fabric-cicd publishing returns; an unexpected fallback
can fail the run but cannot undo any standard writes already performed.

Actual fabric-cicd/mocked-HTTP cold/warm Test/Prod tests observe four bulk definition
imports per fixture with counts `[1, 2, 1, 5]` and no standard definition POSTs.
This proves client parameterization and transport, not live service bindings.
The bulk Report payload retains `byPath`; verify its binding to the model
published in an earlier selection during live Test validation. Keep the initial
Ontology/Graph Model, connection, and ETL caveats below until tested otherwise.

All fabric-cicd workflows use `>=1.4.0,<1.5.0`; bulk, item inclusion, and the ordering
adapter remain experimental. fabric-cicd non-bulk remains the recommended starting point.

> **Note:** If your workspace includes item types not yet supported by fabric-cicd, you can extend this to a multi-job "sandwich" pattern: (1) deploy supported items, (2) promote unsupported items via the [Fabric Deployment Pipelines REST API](https://learn.microsoft.com/en-us/rest/api/fabric/core/deployment-pipelines/deploy-stage-content), (3) deploy supported items that depend on the unsupported items. See [fabric-cicd-release-options.md](fabric-cicd-release-options.md) for details.

---

## GitHub Actions Workflows

This is the shared reference for all implementations, not only the standard
route. A caller decides when and where to run; a reusable template sets up
the environment and invokes a runner. `DEPLOY_METHOD` selects the deployment
job, so unselected workflow runs may still appear as skipped jobs in Actions.

### Pull-Request Checks

| Workflow | Trigger | Purpose |
|---|---|---|
| [check-pr-ready.yml](.github/workflows/check-pr-ready.yml) | PR into `dev` | Runs `workspace_swap.py --check-ready`: dev IDs restored and no stray feature value sets. |
| [run-tests.yml](.github/workflows/run-tests.yml) | Every PR, any target branch | Installs development dependencies and runs the pytest suite. No path filter. |
| [enforce-promotion-path.yml](.github/workflows/enforce-promotion-path.yml) | PR into `test` or `main` | Requires `dev -> test` and `test -> main` source branches. |

Configure required status checks and branch protection using the names in
[Setup](SETUP.md#5-configure-github); YAML alone does not require a passing
check before merge.

### Deployment Callers

All Test callers use pushes to `test`; all Prod callers use pushes to `main`.
Each pair selects the same method for the corresponding Fabric workspace.

| `DEPLOY_METHOD` | Test caller | Prod caller |
|---|---|---|
| `fabric-cicd` or unset | [deploy-test.yml](.github/workflows/deploy-test.yml) | [deploy-prod.yml](.github/workflows/deploy-prod.yml) |
| `fabric-cicd-plan` | [deploy-test-fabric-cicd-plan.yml](.github/workflows/deploy-test-fabric-cicd-plan.yml) | [deploy-prod-fabric-cicd-plan.yml](.github/workflows/deploy-prod-fabric-cicd-plan.yml) |
| `fabric-cicd-bulk` | [deploy-test-fabric-cicd-bulk.yml](.github/workflows/deploy-test-fabric-cicd-bulk.yml) | [deploy-prod-fabric-cicd-bulk.yml](.github/workflows/deploy-prod-fabric-cicd-bulk.yml) |
| `bulk` | [deploy-test-bulk.yml](.github/workflows/deploy-test-bulk.yml) | [deploy-prod-bulk.yml](.github/workflows/deploy-prod-bulk.yml) |

- Standard and raw REST callers watch `data/fabric/**` and `.github/workflows/**`.
- Both plan routes additionally watch `deployment-plans/**`, their own runner/reader, and `requirements-dev.txt`. Add any custom plan location to the applicable caller filters.
- Only [non-bulk-plan Test](.github/workflows/deploy-test-fabric-cicd-plan.yml) supports `workflow_dispatch` for deployment, and only on branch `test`.
- An unknown selector skips all deployment jobs. Changing the variable alone does not trigger a deployment.

### Reusable Templates (called via `workflow_call`)

These are invoked by callers, not standalone push or manually dispatched
workflows. Deployment templates use the caller's `Test`/`Prod` environment and
its scoped secrets; reviewers apply only if the owner configured protection.

| Template | Runner | Role |
|---|---|---|
| [reusable-deploy-fabric-cicd.yml](.github/workflows/reusable-deploy-fabric-cicd.yml) | [deploy_fabric_cicd_non_bulk.py](scripts/deploy_fabric_cicd_non_bulk.py) | Default fabric-cicd non-bulk: fixed phases and orphan cleanup. |
| [reusable-deploy-fabric-cicd-plan.yml](.github/workflows/reusable-deploy-fabric-cicd-plan.yml) | [deploy_fabric_cicd_non_bulk_plan.py](scripts/deploy_fabric_cicd_non_bulk_plan.py) | Preview an authored plan, publish individual groups then remaining items, and clean up eligible orphans. |
| [reusable-deploy-fabric-cicd-bulk.yml](.github/workflows/reusable-deploy-fabric-cicd-bulk.yml) | [deploy_fabric_cicd_bulk.py](scripts/deploy_fabric_cicd_bulk.py) | Preview grouped plan selections, require bulk mode/item outcomes, and clean up eligible orphans. |
| [reusable-deploy-bulk.yml](.github/workflows/reusable-deploy-bulk.yml) | [deploy_fabric_rest_bulk.py](scripts/deploy_fabric_rest_bulk.py) | Build/substitute raw bulk payloads, poll imports, and activate the value set. No orphan cleanup. |
| [reusable-fabric-etl.yml](.github/workflows/reusable-fabric-etl.yml) | [run_fabric_etl.py](scripts/run_fabric_etl.py) | Resolve an item by display name, start its job, and poll until completion or failure. |

### ETL Callers and Handoff

| Workflow | Trigger | Purpose |
|---|---|---|
| [etl-test.yml](.github/workflows/etl-test.yml) | Completed Test deploy workflow or manual run | Runs `Import_Patterns_Data` in Test through the reusable ETL template. |
| [etl-prod.yml](.github/workflows/etl-prod.yml) | Completed Prod deploy workflow or manual run | Runs `Import_Patterns_Data` in Prod through the same template and configured Prod protections. |

The automated ETL job requires upstream conclusion `success`; manual ETL runs
are also permitted. Each listener recognizes all four deployment workflow
names. Keep the listeners on the default branch before switching methods,
because GitHub loads `workflow_run` listeners there.

Notebook/job completion is not a complete schema, data-quality, consumer-access,
or release-readiness suite. Design those checks using the
[Quality Gates guide](fabric-cicd-quality-gates-and-release-controls.md).

### Why Reusable Workflows (Not Composite Actions)

Reusable workflows support the `environment:` keyword at the job level, which enables:
- **GitHub Environment protection rules** (required reviewers, branch restrictions on Prod)
- **Environment-scoped secrets** (each environment has its own `FABRIC_WORKSPACE_ID`)
- `secrets: inherit` forwards all environment secrets without enumeration

---

## Configuration Strategy

Two complementary mechanisms handle environment-specific configuration:

### 1. Variable Libraries (Runtime)

Notebooks call `notebookutils.variableLibrary.getLibrary("Patterns_Variables")` at execution time to resolve workspace IDs, lakehouse names, and other values. The Variable Library has **value sets** per environment:

| Variable | Default (Dev) | Test | Prod |
|---|---|---|---|
| `target_workspace_id` | Dev workspace ID | Test workspace ID | Prod workspace ID |
| `target_workspace_name` | `microsoft-fabric-sdlc-patterns-dev` | `microsoft-fabric-sdlc-patterns-test` | `microsoft-fabric-sdlc-patterns-prod` |
| `target_lakehouse_name` | `PatternsLakehouse` | *(default)* | *(default)* |
| `target_lakehouse_id` | Dev lakehouse ID | Dev lakehouse ID* | Dev lakehouse ID* |

\* Test/Prod inherit `target_lakehouse_id` from the base [variables.json](data/fabric/Patterns_Variables.VariableLibrary/variables.json); their value-set files do not override it. At deploy time, [parameter.yml](data/fabric/parameter.yml) replaces that base placeholder with the target Lakehouse ID. fabric-cicd bulk keeps settings/value-set control files literal; see its [replacement safety boundary](fabric-deployment-plan-guide.md#fabric-cicd-replacements-and-strict-success).

**Active value set binding:** fabric-cicd automatically sets the active value set based on the `environment` parameter passed to `FabricWorkspace`. When `environment="Test"`, the `Test` value set becomes active. This happens on every deployment — no manual intervention needed.

> Citation: [fabric-cicd Item Types — Variable Library](https://microsoft.github.io/fabric-cicd/latest/reference/item_types/): *"The active value set of the variable library is defined by the `environment` field passed into the `FabricWorkspace` object."*

### 2. parameter.yml (Deploy-time)

The `parameter.yml` file in `data/fabric/` uses fabric-cicd's `find_replace` with **dynamic replacement** to resolve the lakehouse ID at deploy time:

```yaml
find_replace:
    - find_value: "<DEV_LAKEHOUSE_ID>"
      replace_value:
          _ALL_: "$items.Lakehouse.PatternsLakehouse.$id"  # Resolved at deploy time
      item_type: "VariableLibrary"
```

**How it works:** fabric-cicd deploys items in dependency order — the Lakehouse is created before the Variable Library. When processing Variable Library files, `$items.Lakehouse.PatternsLakehouse.$id` resolves to the actual lakehouse GUID in the target workspace. The `_ALL_` key means this applies to every environment.

---

## Prerequisites & Setup

Follow the [Setup Guide](SETUP.md) to configure a fork, create the Fabric
workspaces, replace the reference environment IDs, configure GitHub, and perform
the first promotion. This implementation guide assumes that setup is complete.

---

## Initial Deployment to a Clean Workspace

This walkthrough uses the standard `fabric-cicd` route. Follow these steps for
the first deployment to a clean target. Subsequent publication and ETL are
automated, subject to configured approvals; required release validation and
any changed prerequisite configuration remain separate.

### Step 1: Trigger the Deployment

With `DEPLOY_METHOD=fabric-cicd` or unset, merge a qualifying `dev -> test` or
`test -> main` PR containing Fabric definition or workflow changes. Configured
deployment approvals apply. The standard deploy job executes two phases:

- **Phase 1:** Deploys Lakehouse (empty shell) and Ontology definition
- **Phase 2:** Deploys all remaining items (Variable Library, Notebooks, Semantic Model, Report, Data Agent) with parameterized lakehouse/workspace IDs

### Step 2: ETL Populates the Lakehouse

The ETL workflow (`etl-test.yml` or `etl-prod.yml`) triggers automatically after a successful deployment. It runs the `Import_Patterns_Data` notebook, which creates and populates the Delta tables (`doctors`, `patients`, `appointments`) in the Lakehouse.

### Step 3: Configure Graph Model Data Source (Manual)

The Ontology is deployed as a definition only — its Graph Model does not have a data source binding until you configure it manually.

1. Open the **Ontology** item in the Fabric UI and navigate to the **Graph Model**
2. Select **Get data** to bind the Graph Model to the lakehouse tables

### Step 4: Activate the Ontology (Manual Workaround)

After configuring the data source, the Ontology may remain stuck on *"Setting up your ontology — We are preparing the ontology overview for the first time."* This is a known Fabric platform behavior on initial deployment.

**Workaround:** Select any Entity Type in the Ontology, rename it to something temporary, then rename it back to its original name. This triggers Fabric to finish initializing the Ontology overview.

### Step 5: Verify End-to-End

Confirm all items are functional in the target workspace:

- **Lakehouse** — tables populated with data
- **Ontology** — overview loads, entity types and relationships visible
- **Semantic Model** — verify the deployed Direct Lake target and required connection permissions; configure the supported connection if the first deployment needs it
- **Report** — renders with data from the Semantic Model
- **Data Agent** — references the Ontology and responds to queries

> **Note:** The Ontology steps above address initial clean-target setup. Subsequent publication/ETL automation does not replace the verification in step 5 or the workload-specific [release checks](fabric-cicd-quality-gates-and-release-controls.md).

---

## Gotchas & Key Decisions

### Chicken-and-Egg: Lakehouse ID

For the default fabric-cicd non-bulk route, the Variable Library and Semantic Model need a Lakehouse ID that does not exist until the first deployment creates it. `$items` replacements resolve against the target inventory, so a dependent item cannot resolve an undeployed prerequisite. fabric-cicd bulk also has its own staged dependency handling; the caller behavior below describes the default non-bulk route.

**Solution:** The `reusable-deploy-fabric-cicd.yml` workflow uses a **two-phase deployment** approach. Phase 1 calls `publish_all_items()` with `item_type_in_scope=["Lakehouse", "Ontology"]` to create the Lakehouse and Ontology first. The Lakehouse must exist so that `$items.Lakehouse.PatternsLakehouse.$id` resolves for parameter.yml rules. The Ontology must exist so that the Data Agent's logicalId reference resolves (fabric-cicd caches workspace state once per `publish_all_items()` call, so items deployed within the same call aren't visible to later items' logicalId resolution). Phase 2 calls `publish_all_items()` with the remaining item types. On subsequent deployments, both phases are idempotent.

### Item Type Scoping

When `item_type_in_scope` is omitted, fabric-cicd attempts to deploy all item types and may count non-item files (e.g., Report theme resources) as separate items, leading to incorrect item counts.

**Solution:** Explicitly set `item_type_in_scope` in the deploy workflows: `["Lakehouse", "Ontology", "VariableLibrary", "Notebook", "SemanticModel", "Report", "DataAgent"]`. This ensures only valid item types are deployed.

### Chicken-and-Egg: ETL Notebook ID

The ETL workflow needs to run a notebook, but the notebook ID differs per workspace and isn't known until after deployment.

**Solution:** The ETL workflow resolves the notebook by **display name** at runtime via the [Fabric List Items API](https://learn.microsoft.com/en-us/rest/api/fabric/core/items/list-items), not by ID. The notebook name (`Import_Patterns_Data`) is consistent across environments because it comes from the Git repo.

### Environment Names Must Match Value Set Names

The `environment` parameter passed to fabric-cicd's `FabricWorkspace` is used to set the active value set on the Variable Library. The value set files are named `Test.json` and `Prod.json`, so the environment values must be `Test` and `Prod` (capitalized). GitHub Environments are case-insensitive, so `Test` resolves to the `Test` environment correctly.

### SPN Role: Contributor (Not Admin)

The Fabric [Create Item API](https://learn.microsoft.com/en-us/rest/api/fabric/core/items/create-item) requires the **Contributor** workspace role. This is the minimum required — Member and Admin also work but violate least-privilege.

### Actions Pinned to Commit SHA

Per [GitHub's official guidance](https://docs.github.com/en/copilot/tutorials/customization-library/custom-instructions/github-actions-helper), third-party actions are pinned to full commit SHAs (not version tags) to prevent supply-chain attacks:

- `actions/checkout@de0fac2e4500dabe0009e67214ff5f5447ce83dd` (v6)
- `actions/setup-python@a309ff8b426b58ec0e2a45f0f869d46889d02405` (v6)

### Full Deployment Every Time

The default route publishes every item in its selected scope, not only files changed in the last commit. Definition publication does not by itself reconcile data, connections, permissions, or other external state.

### DefaultAzureCredential is Deprecated

fabric-cicd has deprecated `DefaultAzureCredential`. All workflows use `ClientSecretCredential` explicitly, per the [fabric-cicd authentication docs](https://microsoft.github.io/fabric-cicd/latest/example/authentication/).

### Path Filter Prevents Unnecessary Runs

Standard deployment callers watch Fabric definitions and workflow files. Plan callers also watch their plan/code/dependency paths; see the [shared trigger reference](#deployment-callers). Documentation-only commits do not trigger these deployments.

---

## References

- [Fabric CI/CD Release Options](fabric-cicd-release-options.md) — Full strategy document with release option comparison and hybrid recommendation
- [fabric-cicd Python Library](https://microsoft.github.io/fabric-cicd) — Docs, getting started, supported item types
- [fabric-cicd Parameterization](https://microsoft.github.io/fabric-cicd/latest/how_to/parameterization/) — `parameter.yml` reference with `find_replace`, `$items` dynamic replacement
- [fabric-cicd Item Types](https://microsoft.github.io/fabric-cicd/latest/reference/item_types/) — Per-item-type notes including Variable Library active value set behavior
- [fabric-cicd Authentication Examples](https://microsoft.github.io/fabric-cicd/latest/example/authentication/) — GitHub Actions credential patterns
- [Fabric Create Item API — Permissions](https://learn.microsoft.com/en-us/rest/api/fabric/core/items/create-item) — Contributor role requirement
- [Fabric Permission Model](https://learn.microsoft.com/en-us/fabric/security/permission-model) — Workspace roles (Admin, Member, Contributor, Viewer)
- [Variable Library CI/CD](https://learn.microsoft.com/en-us/fabric/cicd/variable-library/variable-library-cicd) — Value sets, active set behavior, Git integration
- [GitHub Reusable Workflows](https://docs.github.com/en/actions/sharing-automations/reusing-workflows) — `workflow_call`, inputs, secrets
- [GitHub Environment Protection Rules](https://docs.github.com/en/actions/managing-workflow-runs-and-deployments/managing-deployments/managing-environments-for-deployment) — Required reviewers, deployment branch restrictions
- [GitHub Actions Helper — Custom Instructions](https://docs.github.com/en/copilot/tutorials/customization-library/custom-instructions/github-actions-helper) — Official Copilot instructions for Actions workflows
