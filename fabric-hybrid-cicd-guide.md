**English** | [Español](translations/es/fabric-hybrid-cicd-guide.md)

<a id="hybrid-cicd-implementation-guide"></a>

# fabric-cicd Non-Bulk CI/CD Guide

This guide describes fabric-cicd non-bulk, this repository's default deployment
method and recommended starting point. It owns the publisher-specific mechanics:
three publication phases, `parameter.yml`, eligible orphan cleanup, and
clean-target behavior.

[Release Process](fabric-release-process.md) owns behavior shared by all four
methods: promotion, connection ensure, workflow selection, the same-revision
Fabric DataPipeline handoff, recovery, and verification status.

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
│  selected release prelude                           │
│    └─ ensure WI connections + persist IDs           │
│  deploy-fabric-cicd                                 │
│    └─ reusable-deploy-fabric-cicd.yml               │
│       └─ fabric-cicd: publish_all_items()           │
│          (Phase 1: Lakehouse + Ontology)            │
│          (Phase 2: non-pipeline dependents)         │
│          (Phase 3: DataPipeline; fresh state)       │
└─────────────────────────────────────────────────────┘
                     │ needs: deploy-fabric-cicd
                     ▼
┌─────────────────────────────────────────────────────┐
│  deploy-test.yml: run-etl (same revision)            │
│    └─ reusable-fabric-etl.yml                       │
│       └─ Fabric REST API: run DataPipeline + wait   │
└─────────────────────────────────────────────────────┘
                     │ Fabric activity dependencies
                     ▼
    Import_Patterns_Data → Validate_Patterns_Data
       → native refresh of Patterns_Semantic_Model
```

The same publication mechanics apply to Prod. See the
[shared Test/Prod contract](fabric-release-process.md#dev-to-test) for the
complete job sequence and branch mapping.

GitHub publishes definitions and starts/polls one
`Patterns_Load_Validate_And_Refresh` job. Fabric owns validation and the only
refresh; no GitHub Power BI refresh step or runtime fallback remains. This
Fabric DataPipeline orchestrates work, whereas native Fabric Deployment
Pipelines promote content and DeploymentPlan orders publication.

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
| `test` | Test (microsoft-fabric-sdlc-patterns-test) | Selected API publisher; this guide covers fabric-cicd |
| `main` | Prod (microsoft-fabric-sdlc-patterns-prod) | Selected API publisher; this guide covers fabric-cicd |

- Dev is the only Git-connected shared workspace. Developers Branch Out from
  Dev for isolated feature work.
- Test and Prod are not Git-connected. They receive API-based publication.

---

## Repository Structure

```
microsoft-fabric-sdlc-patterns/
├── .github/workflows/
│   ├── deploy-test.yml
│   ├── deploy-prod.yml
│   └── reusable-deploy-fabric-cicd.yml
├── data/fabric/
│   ├── parameter.yml
│   ├── PatternsLakehouse.Lakehouse/
│   ├── Patterns_Ontology.Ontology/
│   ├── Patterns_Variables.VariableLibrary/
│   ├── *.Notebook/
│   ├── *.SemanticModel/
│   ├── *.Report/
│   ├── *.DataAgent/
│   └── *.DataPipeline/
├── scripts/
│   └── deploy_fabric_cicd_non_bulk.py
├── fabric-release-process.md
└── fabric-hybrid-cicd-guide.md
```

The complete workflow inventory is in
[Release Process](fabric-release-process.md#github-actions-workflows).

---

## Deployment Flow

### What Triggers What

This shared section moved to
[Release Process: What triggers what](fabric-release-process.md#what-triggers-what).
The heading remains here so existing links continue to resolve.

### Deploy Job

After the shared
[connection prelude](fabric-release-process.md#dev-to-test), the selected
workflow calls `reusable-deploy-fabric-cicd.yml`. With a DataPipeline in scope,
the standard runner makes three publish calls: Lakehouse +
Ontology; non-pipeline dependents (Variable Library, Notebooks, Semantic Model,
Report, Data Agent); then DataPipeline. fabric-cicd caches workspace state
within a call, so item order alone does not make newly created notebook/model
IDs available to pipeline references. The third call uses fresh discovery.
Without a DataPipeline, the runner retains its two-phase behavior.
Item types remain explicitly scoped via `item_type_in_scope`.

The dependent ETL job starts after publication succeeds. The shared handoff is
documented in
[Release Process](fabric-release-process.md#etl-callers-and-handoff).

<a id="strict-plan-driven-sdk-bulk-14x"></a>

### fabric-cicd Bulk with a Client-Read Plan (1.4.x)

This guide no longer owns the plan adapters. See
[Deployment Plan CI/CD Guide](fabric-deployment-plan-guide.md#isolated-bulk-adapter-14x)
for fabric-cicd bulk behavior and its validation boundary. This anchor remains
for compatibility with existing links.

---

## GitHub Actions Workflows

The shared workflow reference moved to
[Release Process: GitHub Actions workflows](fabric-release-process.md#github-actions-workflows).
The compatibility headings below preserve existing deep links without
maintaining a second copy of the release contract.

### Pull-Request Checks

See [Release Process: Pull-request checks](fabric-release-process.md#pull-request-checks).

### Deployment Callers

See [Release Process: Deployment callers](fabric-release-process.md#deployment-callers).

### Reusable Templates (called via `workflow_call`)

See
[Release Process: Reusable templates](fabric-release-process.md#reusable-templates-called-via-workflow_call).

### ETL Callers and Handoff

See
[Release Process: ETL callers and handoff](fabric-release-process.md#etl-callers-and-handoff).

#### Post-ETL Semantic Model Refresh

See
[Release Process: Post-ETL semantic model refresh](fabric-release-process.md#post-etl-semantic-model-refresh).

### Why Reusable Workflows (Not Composite Actions)

See
[Release Process: Why reusable workflows](fabric-release-process.md#why-reusable-workflows-not-composite-actions).

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
canonical Dev connections. Target model replacement uses
`$items.SemanticModel.Patterns_Semantic_Model.$id`; connection replacement uses
the exact `$ENV:NOTEBOOK_CONNECTION_ID` and
`$ENV:SEMANTIC_MODEL_REFRESH_CONNECTION_ID` names. The runners enable
environment-variable replacement and validate both connection GUIDs before
definition publication. The `>=1.4.0,<1.5.0` library range is required.
The selected release's connection prelude, not the publisher subprocess or
parameter replacement, owns Test/Prod connection creation and sharing. Source
preflight checks actual fields and parameter baselines so stale feature IDs
cannot silently miss a literal replacement.

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

The deployment's dependent ETL job starts the DataPipeline
after successful deployment. Its loader creates/populates `doctors`, `patients`,
and `appointments`; validation must succeed before native model refresh.
The selected deployment job ensures the target WI pair before the publisher
validates and consumes it read-only. See the
[pipeline contract](fabric-release-process.md#post-etl-semantic-model-refresh);
the unchanged loader does not refresh the model itself.

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

Standard deployment callers watch Fabric definitions and workflow files. Plan
callers also watch their plan/code/dependency paths; see the
[shared trigger reference](fabric-release-process.md#deployment-callers).
Documentation-only commits do not trigger these deployments.

---

## References

- [Release Process](fabric-release-process.md) — Shared promotion, connection, workflow, and DataPipeline contract
- [Setup](SETUP.md) — Fresh-fork prerequisites and configuration
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
