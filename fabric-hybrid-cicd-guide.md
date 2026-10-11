<a id="hybrid-cicd-implementation-guide"></a>

# fabric-cicd Non-Bulk CI/CD Guide

This guide describes **fabric-cicd non-bulk**, this repository's default deployment method and recommended starting point. It demonstrates how to deploy Fabric workspace items (DataPipelines, Notebooks, Lakehouses, Variable Libraries, Semantic Models, Reports, Ontologies, Data Agents) across environments using GitHub Actions.

This page also owns the [shared workflow reference](#github-actions-workflows) for all four methods.
Dev uses Fabric Git integration; Test/Prod receive API-based deployments.
Using Git for development does not add a second publisher to the default route.
An optional hybrid architecture can combine publishers when a workload requires
it; native Fabric Deployment Pipelines are not used by these workflows.

For the release option comparison and [optional extensions for unsupported items](fabric-cicd-release-options.md#optional-extensions-for-unsupported-items), see [CI/CD Release Options](fabric-cicd-release-options.md).

The existing filename is retained to preserve links to this guide.

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
│          (Phase 2: non-pipeline dependents)         │
│          (Phase 3: DataPipeline; fresh state)       │
└─────────────────────────────────────────────────────┘
                     │ workflow_run (on success)
                     ▼
┌─────────────────────────────────────────────────────┐
│  etl-test.yml                                       │
│    └─ reusable-fabric-etl.yml                       │
│       └─ Fabric REST API: run DataPipeline + wait   │
└─────────────────────────────────────────────────────┘
                     │ Fabric activity dependencies
                     ▼
    Import_Patterns_Data → Validate_Patterns_Data
       → native refresh of Patterns_Semantic_Model
```

The same pattern applies to Prod (`deploy-prod.yml` → `etl-prod.yml`), triggered on push to `main`.

GitHub publishes definitions and starts/polls one
`Patterns_Load_Validate_And_Refresh` job. Fabric owns validation and the only
refresh; no GitHub Power BI refresh step or runtime fallback remains. This
**DataPipeline** orchestrates work, whereas native **Deployment Pipelines**
promote content and **DeploymentPlan** orders publication.

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
- **Test** and **Prod** workspaces are NOT Git-connected. They receive API-based deployments through the selected GitHub route.

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
│       ├── reusable-fabric-etl.yml               # Template: start/poll one Fabric job
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
│       ├── Validate_Patterns_Data.Notebook/ # Read-only source checks with base parameters
│       ├── Patterns_Load_Validate_And_Refresh.DataPipeline/
│       ├── Patterns_Patients_Data.Notebook/
│       ├── Patterns_Demo.Notebook/
│       ├── Patterns_Semantic_Model.SemanticModel/
│       ├── Patterns_Report.Report/
│       └── Patterns_Data_Agent.DataAgent/
├── scripts/
│   ├── workspace_swap.py                    # Bootstrap/reset feature branch workspace bindings
│   ├── deploy_fabric_cicd_non_bulk.py       # fabric-cicd deploy (invoked by reusable-deploy-fabric-cicd.yml)
│   ├── deploy_fabric_rest_bulk.py           # Bulk Import API deploy (invoked by reusable-deploy-bulk.yml)
│   └── run_fabric_etl.py                    # Start/poll Notebook or DataPipeline jobs
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

Each deploy workflow calls `reusable-deploy-fabric-cicd.yml`. With a DataPipeline
in scope, the standard runner makes **three publish calls**: Lakehouse +
Ontology; non-pipeline dependents (Variable Library, Notebooks, Semantic Model,
Report, Data Agent); then DataPipeline. fabric-cicd caches workspace state
within a call, so item order alone does not make newly created notebook/model
IDs available to pipeline references. The third call uses fresh discovery.
Without a DataPipeline, the runner retains its two-phase behavior.
Item types remain explicitly scoped via `item_type_in_scope`.

The ETL workflow triggers automatically after the deploy workflow completes successfully. If the deploy fails, ETL does not run.

<a id="strict-plan-driven-sdk-bulk-14x"></a>

### fabric-cicd Bulk with a Client-Read Plan (1.4.x)

Selecting `DEPLOY_METHOD=fabric-cicd-bulk` runs
[deploy_fabric_cicd_bulk.py](scripts/deploy_fabric_cicd_bulk.py), not the standard
fixed-phase runner or the raw REST substitution engine. It requires
`DEPLOYMENT_PLAN_PATH` and an explicit, nonempty bulk-eligible type scope.
[deployment_plan_bulk.py](scripts/deployment_plan_bulk.py) independently reads
and validates the plan; it does not reuse the non-bulk plan modules.

The authored plan places the library, required notebooks, and Semantic Model
before the DataPipeline, alongside the Lakehouse/Ontology/Data Agent dependency
chains. The pipeline has explicit dependencies on `Patterns_Variables`,
`Import_Patterns_Data`, `Validate_Patterns_Data`, and `Patterns_Semantic_Model`.
Independent ready groups share one fabric-cicd selection, not parallel
requests. The current 11-item sample has declared batch sizes `[1, 5, 2]` and a
three-item remainder (Report and two demo notebooks): four library selections.
See the [offline schedule and transport boundaries](fabric-deployment-plan-guide.md#isolated-bulk-adapter-14x);
preview again after plan/inventory changes rather than assuming a fixed count.
Only successful outcomes release the next selection. Plan dependencies order
publication, not ETL execution.

fabric-cicd 1.4.0 applies the existing filtered dynamic replacements from
[parameter.yml](data/fabric/parameter.yml) while using bulk. Its own dependency
batching remains active within each call. The adapter rejects known fallback
conditions, checks actual bulk mode and complete per-item success, and performs
the existing eligible orphan cleanup once after successful publishing.
The actual-mode check runs after fabric-cicd publishing returns; an unexpected fallback
can fail the run but cannot undo any standard writes already performed.

Actual fabric-cicd/mocked-HTTP tests exercise bulk definitions, parameterization,
and complete item outcomes without standard definition POSTs. This proves
client contracts and transport, not live service bindings or the CI identity.
The bulk Report payload retains `byPath`; verify its binding to the model
published in an earlier selection during live Test validation. Keep the initial
Ontology/Graph Model, connection, and ETL caveats below until tested otherwise.

All fabric-cicd workflows use `>=1.4.0,<1.5.0`; bulk, item inclusion, and the ordering
adapter remain experimental. fabric-cicd non-bulk remains the recommended starting point.

> **Optional extension, not implemented here:** If the selected publisher cannot deploy an item, first verify another route's support for that item and execution identity. Where native Fabric Deployment Pipelines support it, a multi-job "sandwich" can publish independent items, promote the extra items, then publish their dependents. Lack of Git integration support alone does not require this architecture. See [Optional Extensions for Unsupported Items](fabric-cicd-release-options.md#optional-extensions-for-unsupported-items).

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
| [reusable-fabric-etl.yml](.github/workflows/reusable-fabric-etl.yml) | [run_fabric_etl.py](scripts/run_fabric_etl.py) | Resolve an item by display name, start and poll its job, and report failures. The pipeline owns activity execution and refresh. |

### ETL Callers and Handoff

| Workflow | Trigger | Purpose |
|---|---|---|
| [etl-test.yml](.github/workflows/etl-test.yml) | Completed Test deploy workflow or manual run | Starts `Patterns_Load_Validate_And_Refresh` in Test and waits for the pipeline job. |
| [etl-prod.yml](.github/workflows/etl-prod.yml) | Completed Prod deploy workflow or manual run | Starts the same pipeline in Prod through the shared template and configured Prod protections. |

The automated ETL job requires upstream conclusion `success`; manual ETL runs
are also permitted. Each listener recognizes all four deployment workflow
names. Keep the listeners on the default branch before switching methods,
because GitHub loads `workflow_run` listeners there.

While the changed caller/template has not reached `main`, automatic Test ETL
can still load the old notebook-only listener. After older automatic runs
finish, manually dispatch **ETL - Test** from **test** to validate that branch.
Rerunning an old main run does not pick up the new Test definition. A same-stage
deploy → ETL chain with `needs` needs separate design and migration; adopting a
DataPipeline does not remove the default-branch coupling.

#### Post-ETL Semantic Model Refresh

Both callers select `item_type: DataPipeline` and `job_type: Pipeline`. The
runner resolves the pipeline by name in `FABRIC_WORKSPACE_ID`, starts it, and
polls that specific job. The shared runner still supports ordinary Notebook
jobs without parameters; the shipped follow-up does not run a standalone loader
in addition to the pipeline.

| Activity | Contract |
|---|---|
| `Import_Patterns_Data` | Existing unchanged loader; writes the sample Delta tables |
| `Validate_Patterns_Data` | Read-only schema/source-date-type, non-null/unique-key, appointment-reference, and patient-minimum checks; runs only after load succeeds |
| Native refresh of `Patterns_Semantic_Model` | Runs only after validation succeeds; full refresh, **Transactional**, **Wait on completion** enabled |

Like `Patterns_Demo`, the validation notebook reads `target_workspace_id` and
`target_lakehouse_id` from the active `Patterns_Variables` value set, validates
the GUIDs, and loads Delta tables using explicit OneLake
`abfss://.../Tables/dbo/...` paths. It does not use an attached Lakehouse or
Spark catalog table names. The quality threshold still comes from the pipeline
base parameter; reading target IDs does not bypass that parameter example.

The pipeline is the **only refresh owner**. The previous GitHub refresh
script, step, and model-name input are retired, not retained behind a switch.
Refresh failure fails the pipeline; a failed validation prevents refresh.
Job acceptance alone is not success. The pipeline job wait is bounded at
60 minutes; activity limits are 20 minutes for load, 10 for validation, and
10 for refresh, with the native refresh server timeout also set to 10 minutes.
On failure the runner reports job/activity diagnostics where available.
A GitHub polling timeout does not cancel work in Fabric; inspect the specific
pipeline run and refresh history before retrying.

**Two parameter examples:**

- `minimum_patient_count` is a positive **Integer** in the active
  `Patterns_Variables` value set, baseline `5` in Default/Test/Prod. The pipeline
  Library binding supplies it to the validation notebook's base parameter.
  Validation uses that passed value rather than rereading the threshold.
  Runtime checks do not require exact fixture counts.
- `run_label` is an independent **String** pipeline parameter, default
  `manual`, forwarded to validation. The optional reusable-workflow input
  supplies `RUN_LABEL`; CI uses a non-secret stage/run label. The runner builds
  the JSON job body under `executionData.parameters`. Invalid input is not
  silently replaced by a successful-looking default.

Both Notebook activities and refresh use **Workspace Identity** connections.
The user who authors a pipeline, CI service principal that publishes/starts
it, connection runtime identity, model owner, and consumer are separate actors.
Create target connections and share use with CI before publishing; set
`NOTEBOOK_CONNECTION_ID` and `SEMANTIC_MODEL_REFRESH_CONNECTION_ID` as
[GitHub Environment variables](SETUP.md#environment-variables).
Connections are not deployed from Git, and physical model/connection references
need target substitutions. Direct Lake separately checks the model owner's
source access. See [required permissions](SETUP.md#post-etl-refresh-permissions).

**Reference evidence and boundary:** Earlier feature-prototype run
`01607220-ed7d-4ae0-aeb3-4b37fbc9eaec` completed load → validation → native
refresh; validation received minimum `5` and API-supplied label
`feature-api-verification`, and refresh reported `Completed`. Both connection
types used `WorkspaceIdentity` credentials, without an OAuth fallback.
The pipeline was created and exported from Fabric; user-authenticated
Create DataPipeline, GetDefinition, UpdateDefinition, and Pipeline job-start
requests were exercised in that feature workspace. Preserve the exported
logical IDs; none of those API successes proves publisher/identity parity.
Authoring and pipeline invocation used a **user** identity. The current
validation revision uses explicit OneLake paths and is only offline-validated;
the prototype run is not live evidence for that revision. Git sync/Branch Out
resolution of the exported pipeline references, CI service-principal
publication/start, a service-principal-deployed model's ownership compatibility,
and Test/Prod end-to-end routes still require live verification.

For this **Direct Lake on OneLake** model, refresh frames Delta references.
It does not copy data again, convert storage mode, or wait for a SQL analytics
endpoint. Source checks and refresh completion do not prove model date-field
queries, DAX/business results, or consumer access. Those remain separate
[release checks](fabric-cicd-quality-gates-and-release-controls.md).

### Why Reusable Workflows (Not Composite Actions)

Reusable workflows support the `environment:` keyword at the job level, which enables:
- **GitHub Environment protection rules** (required reviewers, branch restrictions on Prod)
- **Environment-scoped secrets** (each environment has its own `FABRIC_WORKSPACE_ID`)
- `secrets: inherit` forwards all environment secrets without enumeration

---

## Configuration Strategy

Two complementary mechanisms handle environment-specific configuration:

### 1. Variable Libraries (Runtime)

The loader and validation notebook call `notebookutils.variableLibrary.getLibrary("Patterns_Variables")`
at execution time for workspace/lakehouse configuration. The pipeline also
binds the active Library's patient minimum to validation's base parameter.
The Variable Library has **value sets** per environment:

| Variable | Default (Dev) | Test | Prod |
|---|---|---|---|
| `target_workspace_id` | Dev workspace ID | Test workspace ID | Prod workspace ID |
| `target_workspace_name` | `microsoft-fabric-sdlc-patterns-dev` | `microsoft-fabric-sdlc-patterns-test` | `microsoft-fabric-sdlc-patterns-prod` |
| `target_lakehouse_name` | `PatternsLakehouse` | *(default)* | *(default)* |
| `target_lakehouse_id` | Dev lakehouse ID | Dev lakehouse ID* | Dev lakehouse ID* |
| `minimum_patient_count` (Integer) | `5` | `5` | `5` |

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

DataPipeline rules also replace physical workspace/model IDs and source
connection markers. Target model replacement uses
`$items.SemanticModel.Patterns_Semantic_Model.$id`; connection replacement uses
the exact `$ENV:NOTEBOOK_CONNECTION_ID` and
`$ENV:SEMANTIC_MODEL_REFRESH_CONNECTION_ID` names. The runners enable
environment-variable replacement and validate both connection GUIDs before
definition publication. The `>=1.4.0,<1.5.0` library range is required.
Substituting a GUID does not create or authorize its runtime connection.

---

## Prerequisites & Setup

Follow the [Setup Guide](SETUP.md) to configure a fork, create the Fabric
workspaces, replace the reference environment IDs, configure GitHub, and perform
the first promotion. This implementation guide assumes that setup is complete.

---

## Initial Deployment to a Clean Workspace

This walkthrough uses the standard `fabric-cicd` route. Follow these steps for
the first deployment to a clean target. Subsequent publication, ETL, and model
refresh are automated, subject to configured approvals; required release
validation and any changed prerequisite configuration remain separate.

### Step 1: Trigger the Deployment

With `DEPLOY_METHOD=fabric-cicd` or unset, merge a qualifying `dev -> test` or
`test -> main` PR containing Fabric definition or workflow changes. Configured
deployment approvals apply. For this sample, the standard deploy job executes
three publication phases:

- **Phase 1:** Deploys Lakehouse (empty shell) and Ontology definition
- **Phase 2:** Deploys non-pipeline dependents (Variable Library, Notebooks,
  Semantic Model, Report, Data Agent) with target substitutions.
- **Phase 3:** Publishes the DataPipeline using fresh workspace state so its
  notebook/model references can resolve IDs created in phase 2.

### Step 2: ETL Populates the Lakehouse, Then Refreshes the Model

The ETL workflow (`etl-test.yml` or `etl-prod.yml`) starts the DataPipeline
after successful deployment. Its loader creates/populates `doctors`, `patients`,
and `appointments`; validation must succeed before native model refresh.
Configure target Workspace Identity connections before this first execution.
See the [pipeline contract](#post-etl-semantic-model-refresh); the unchanged
loader does not refresh the model itself.

### Step 3: Configure Graph Model Data Source (Manual)

The Ontology is deployed as a definition only — its Graph Model does not have a data source binding until you configure it manually.

1. Open the **Ontology** item in the Fabric UI and navigate to the **Graph Model**
2. Select **Get data** to bind the Graph Model to the lakehouse tables

### Step 4: Activate the Ontology (Manual Workaround)

After configuring the data source, the Ontology may remain stuck on *"Setting up your ontology — We are preparing the ontology overview for the first time."* This is a known Fabric platform behavior on initial deployment.

**Workaround:** Select any Entity Type in the Ontology, rename it to something temporary, then rename it back to its original name. This triggers Fabric to finish initializing the Ontology overview.

### Step 5: Verify End-to-End

Confirm all items are functional in the target workspace:

- **Lakehouse** — tables populated and read-only source validation passed
- **DataPipeline** — target connections/model bindings verified and all three
  activities completed under the intended activity credentials
- **Ontology** — overview loads, entity types and relationships visible
- **Semantic Model** — verify the deployed Direct Lake target, refresh completion, and required owner/connection/source permissions; configure a supported connection if the first deployment needs it, then check fields such as `appointment_date` and `date_of_birth` and the required calculations
- **Report** — renders with data from the Semantic Model
- **Data Agent** — references the Ontology and responds to queries

> **Note:** The Ontology steps above address initial clean-target setup. Subsequent publication/ETL/model-refresh automation does not replace the verification in step 5 or the workload-specific [release checks](fabric-cicd-quality-gates-and-release-controls.md).

---

## Gotchas & Key Decisions

### Chicken-and-Egg: Lakehouse ID

For the default fabric-cicd non-bulk route, the Variable Library and Semantic Model need a Lakehouse ID that does not exist until the first deployment creates it. `$items` replacements resolve against the target inventory, so a dependent item cannot resolve an undeployed prerequisite. fabric-cicd bulk also has its own staged dependency handling; the caller behavior below describes the default non-bulk route.

**Solution:** Phase 1 publishes Lakehouse + Ontology. A fresh phase 2 call can
resolve their IDs for the library, notebooks, model, report, and Data Agent.
The same state-cache boundary applies to the new pipeline: phase 3 publishes
DataPipeline after fresh discovery of its phase 2 notebook/model dependencies.
Each phase must succeed before the next starts; cleanup follows successful
publication. These are publication calls, not three workload executions.
If no DataPipeline exists, the third call is omitted.

### Item Type Scoping

When `item_type_in_scope` is omitted, fabric-cicd attempts to deploy all item types and may count non-item files (e.g., Report theme resources) as separate items, leading to incorrect item counts.

**Solution:** Explicitly set `item_type_in_scope` in the deploy workflows: `["Lakehouse", "Ontology", "VariableLibrary", "Notebook", "SemanticModel", "Report", "DataAgent", "DataPipeline"]`. This keeps workload types in scope without publishing DeploymentPlan control items.

### Chicken-and-Egg: ETL Notebook ID

The follow-up now starts a DataPipeline rather than a standalone notebook, but
the runtime lookup problem is the same: physical item IDs differ by workspace.

**Solution:** Resolve `Patterns_Load_Validate_And_Refresh` by **display name**
and item type using the [Fabric List Items API](https://learn.microsoft.com/en-us/rest/api/fabric/core/items/list-items).
That lookup does not repair activity bindings inside the definition; deployment
substitutions and connection setup must already target the correct environment.

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

- [Fabric CI/CD Release Options](fabric-cicd-release-options.md) — Release option comparison, recommended non-bulk starting point, and optional hybrid extensions
- [fabric-cicd Python Library](https://microsoft.github.io/fabric-cicd) — Docs, getting started, supported item types
- [fabric-cicd Parameterization](https://microsoft.github.io/fabric-cicd/latest/how_to/parameterization/) — `parameter.yml` reference with `find_replace`, `$items` dynamic replacement
- [fabric-cicd Item Types](https://microsoft.github.io/fabric-cicd/latest/reference/item_types/) — Per-item-type notes including Variable Library active value set behavior
- [fabric-cicd Authentication Examples](https://microsoft.github.io/fabric-cicd/latest/example/authentication/) — GitHub Actions credential patterns
- [Fabric Create Item API — Permissions](https://learn.microsoft.com/en-us/rest/api/fabric/core/items/create-item) — Contributor role requirement
- [Fabric Permission Model](https://learn.microsoft.com/en-us/fabric/security/permission-model) — Workspace roles (Admin, Member, Contributor, Viewer)
- [Power BI Refresh API](https://learn.microsoft.com/en-us/rest/api/power-bi/datasets/refresh-dataset-in-group) — Start an enhanced semantic model refresh
- [Power BI Dataset Inventory](https://learn.microsoft.com/en-us/rest/api/power-bi/datasets/get-datasets-in-group) — Resolve the model in its target workspace
- [Power BI Refresh Execution Details](https://learn.microsoft.com/en-us/rest/api/power-bi/datasets/get-refresh-execution-details-in-group) — Track the specific refresh request
- [Direct Lake Framing](https://learn.microsoft.com/en-us/fabric/fundamentals/direct-lake-how-it-works#framing) — Refresh behavior for Direct Lake tables
- [Direct Lake Owner Permissions](https://learn.microsoft.com/en-us/fabric/fundamentals/direct-lake-security-integration#direct-lake-owners) — Owner source authorization is checked regardless of who refreshes
- [Variable Library CI/CD](https://learn.microsoft.com/en-us/fabric/cicd/variable-library/variable-library-cicd) — Value sets, active set behavior, Git integration
- [GitHub Reusable Workflows](https://docs.github.com/en/actions/sharing-automations/reusing-workflows) — `workflow_call`, inputs, secrets
- [GitHub Environment Protection Rules](https://docs.github.com/en/actions/managing-workflow-runs-and-deployments/managing-deployments/managing-environments-for-deployment) — Required reviewers, deployment branch restrictions
- [GitHub Actions Helper — Custom Instructions](https://docs.github.com/en/copilot/tutorials/customization-library/custom-instructions/github-actions-helper) — Official Copilot instructions for Actions workflows
