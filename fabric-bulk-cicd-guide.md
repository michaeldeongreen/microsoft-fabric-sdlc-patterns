# Bulk CI/CD Implementation Guide

This is the **raw REST bulk — custom Python caller** route (`DEPLOY_METHOD=bulk`), not fabric-cicd bulk.
For fabric-cicd bulk with library-managed replacements, use the
[Deployment Plan guide](fabric-deployment-plan-guide.md#isolated-bulk-adapter-14x).
Compare all four implementations in the [README matrix](README.md#choose-a-deployment-method).

This repository implements an alternative deployment path for Microsoft Fabric using the **[Bulk Import Item Definitions API](https://learn.microsoft.com/en-us/rest/api/fabric/core/items/bulk-import-item-definitions)** (Preview). The default implementation is documented in the [fabric-cicd Non-Bulk CI/CD Guide](fabric-hybrid-cicd-guide.md). This raw REST example publishes the same workload definitions (DataPipelines, Notebooks, Lakehouses, Variable Libraries, Semantic Models, Reports, Ontologies, Data Agents) using GitHub Actions and the Fabric REST API directly.

For the strategic comparison between fabric-cicd and the Bulk APIs (and the recommendation), see [fabric-cicd-release-options.md](fabric-cicd-release-options.md#tooling-within-option-3-fabric-cicd-vs-bulk-apis).

> **Important framing.** The Bulk Import API itself has known gaps (no parameterization, no value-set activation, no delete). This repo implements caller-side workarounds for the first two — they are not platform fixes or proof of live route parity. If you choose raw REST bulk, you own that caller-side work. **fabric-cicd non-bulk is this repository's default and recommended starting point**, not a universal ranking.
>
> An earlier three-activity feature prototype succeeded under a user invoker with Workspace Identity activity credentials. The current explicit-OneLake-path validation revision is only offline-validated; Git sync/Branch Out binding resolution, CI service-principal publishing/start, and Test/Prod end-to-end execution remain live checks.

---

## Table of Contents

- [Architecture Overview](#architecture-overview)
- [Repository Structure](#repository-structure)
- [Deployment Flow](#deployment-flow)
- [GitHub Actions Workflows](#github-actions-workflows)
- [Configuration Strategy](#configuration-strategy)
- [The Staged-Deploy Decision](#the-staged-deploy-decision)
- [Prerequisites & Setup](#prerequisites--setup)
- [Initial Deployment to a Clean Workspace](#initial-deployment-to-a-clean-workspace)
- [Gotchas & Key Decisions](#gotchas--key-decisions)
- [Extending the Bulk Implementation](#extending-the-bulk-implementation)
- [Limitations Not Bridged](#limitations-not-bridged)
- [References](#references)

---

## Architecture Overview

```
Git repo (dev branch)
  │
  │  PR merge → test branch
  ▼
┌─────────────────────────────────────────────────────┐
│  deploy-test-bulk.yml (orchestrator)                │
│                                                     │
│  deploy-bulk                                        │
│    └─ reusable-deploy-bulk.yml                      │
│       └─ scripts/deploy_fabric_rest_bulk.py         │
│          (Phase 1: POST dependencies                │
│           — Lakehouse + Ontology)                   │
│          (Phase 2: POST non-pipeline dependents)    │
│          (Phase 3: substitute target model ID,      │
│           POST DataPipeline)                        │
│          (Post-deploy: PATCH VariableLibrary        │
│           active value set)                         │
└─────────────────────────────────────────────────────┘
                     │ needs: deploy-bulk
                     ▼
┌─────────────────────────────────────────────────────┐
│  deploy-test-bulk.yml: run-etl (same revision)       │
│    └─ reusable-fabric-etl.yml                       │
│       └─ Fabric REST API: run DataPipeline + wait   │
└─────────────────────────────────────────────────────┘
                     │ Fabric activity dependencies
                     ▼
    Import_Patterns_Data → Validate_Patterns_Data
       → native refresh of Patterns_Semantic_Model
```

The same pattern applies to Prod: `deploy-prod-bulk.yml` owns its dependent
pipeline job, triggered on push to `main`.

Like the [default fabric-cicd non-bulk route](fabric-hybrid-cicd-guide.md#architecture-overview),
raw REST first creates items whose IDs dependents need. It now has a third
DataPipeline batch because native refresh needs the Semantic Model ID returned
from phase 2. The default SDK route also uses a third publish call for this
sample, discovering notebook/model IDs from fresh workspace state after the
dependent definitions have been published.
Raw REST captures IDs from earlier response bodies instead. Plan routes derive
their selections from the authored graph. Publication phases do not run ETL.

| Concept | fabric-cicd non-bulk (default) | Raw REST bulk |
|---|---|---|
| Calls per phase | One library call (`publish_all_items()`) per phase, which makes many per-item REST calls internally | One bulk POST per phase carrying the full batch |
| Substitution | fabric-cicd library applies `parameter.yml` rules transparently | `scripts/deploy_fabric_rest_bulk.py` reads `bulk-parameter.yml` and rewrites payloads between phases |
| Value-set activation | Library handles automatically when `environment` is passed | Caller makes a separate `PATCH /variableLibraries/{id}` call |
| Orphan cleanup | `unpublish_all_orphan_items()` built in | Not implemented |

> Other deploy routes use fabric-cicd non-bulk, fabric-cicd non-bulk + client-read plan, or fabric-cicd bulk + client-read plan. Select a route with `DEPLOY_METHOD`; fabric-cicd non-bulk is this repository's recommended starting point. See the [method matrix](README.md#choose-a-deployment-method) and [fabric-cicd Non-Bulk CI/CD Guide](fabric-hybrid-cicd-guide.md).

**Do not conflate raw REST bulk with fabric-cicd bulk.** In 1.4.0, fabric-cicd bulk supports the
filtered dynamic replacements in [parameter.yml](data/fabric/parameter.yml).
The [isolated fabric-cicd bulk adapter](scripts/deploy_fabric_cicd_bulk.py) delegates
replacement to fabric-cicd and reads an ordering plan; it does not use
[bulk-parameter.yml](data/fabric/bulk-parameter.yml) or this guide's custom
find/replace engine. We retain that engine here for comparison.

Direct REST supports native plan attachment. The current fabric-cicd adapter does not:
it makes plan-ordered bulk selections and rejects fallback or failed/partial
item results. See the [Deployment Plan guide](fabric-deployment-plan-guide.md#isolated-bulk-adapter-14x)
for configuration and live-binding validation boundaries.

### Branches & Workspaces

| Branch | Workspace | Deployment Method |
|---|---|---|
| `dev` | Dev (microsoft-fabric-sdlc-patterns-dev) | Git-connected via Fabric Git integration |
| `test` | Test (microsoft-fabric-sdlc-patterns-test) | Bulk Import API via GitHub Actions |
| `main` | Prod (microsoft-fabric-sdlc-patterns-prod) | Bulk Import API via GitHub Actions |

- **Dev** workspace is the only Git-connected workspace. Developers branch out from Dev for isolated feature work.
- **Test** and **Prod** workspaces are NOT Git-connected. With the bulk path active, they receive deployments through `scripts/deploy_fabric_rest_bulk.py`.

---

## Repository Structure

```
microsoft-fabric-sdlc-patterns/
├── .github/
│   └── workflows/
│       ├── deploy-test-bulk.yml             # Orchestrator: push to test → bulk deploy
│       ├── deploy-prod-bulk.yml             # Orchestrator: push to main → bulk deploy
│       ├── etl-test.yml                     # Manual Test pipeline recovery
│       ├── etl-prod.yml                     # Manual Prod pipeline recovery
│       ├── reusable-deploy-bulk.yml         # Template: Bulk Import API deployment
│       ├── reusable-fabric-etl.yml          # Template: start/poll one Fabric job
│       ├── check-pr-ready.yml               # PR check: blocks feature IDs from merging to dev
│       ├── run-tests.yml                    # PR check: runs pytest when scripts/tests change
│       └── enforce-promotion-path.yml       # PR check: enforces dev→test→main source-branch promotion
├── data/
│   └── fabric/                              # Fabric item definitions (repository_directory)
│       ├── bulk-parameter.yml               # Bulk path's parameterization (independent format)
│       ├── parameter.yml                    # fabric-cicd parameterization (ignored by bulk)
│       ├── PatternsLakehouse.Lakehouse/
│       ├── Patterns_Ontology.Ontology/
│       ├── Patterns_Variables.VariableLibrary/
│       ├── Import_Patterns_Data.Notebook/
│       ├── Validate_Patterns_Data.Notebook/
│       ├── Patterns_Load_Validate_And_Refresh.DataPipeline/
│       ├── Patterns_Patients_Data.Notebook/
│       ├── Patterns_Demo.Notebook/
│       ├── Patterns_Semantic_Model.SemanticModel/
│       ├── Patterns_Report.Report/
│       └── Patterns_Data_Agent.DataAgent/
├── scripts/
│   ├── deploy_fabric_rest_bulk.py           # Bulk Import API deploy (invoked by reusable-deploy-bulk.yml)
│   ├── deploy_fabric_cicd_non_bulk.py       # fabric-cicd deploy (alternative path)
│   ├── run_fabric_etl.py                    # Start/poll Notebook or DataPipeline jobs
│   └── workspace_swap.py                    # Bootstrap/reset feature branch workspace bindings
├── tests/
│   └── test_deploy_fabric_rest_bulk.py      # Unit tests for the bulk script
└── ... (other docs, see README)
```

All four method families live in [.github/workflows/](.github/workflows/).
`DEPLOY_METHOD` selects their deployment jobs; the
[shared workflow reference](fabric-hybrid-cicd-guide.md#github-actions-workflows)
maps every caller and template.

---

## Deployment Flow

### What Triggers What

| Event | Workflow Triggered | What It Does |
|---|---|---|
| Push to `test` (Fabric definitions or workflow changes), `DEPLOY_METHOD=bulk` | `deploy-test-bulk.yml` | Imports workload definitions to Test, excluding DeploymentPlan control items |
| `deploy-test-bulk.yml` deployment job succeeds | Its dependent `run-etl` job | Starts/polls `Patterns_Load_Validate_And_Refresh` in Test, using the same revision |
| Push to `main` (Fabric definitions or workflow changes), `DEPLOY_METHOD=bulk` | `deploy-prod-bulk.yml` | Imports workload definitions to Prod, excluding DeploymentPlan control items |
| `deploy-prod-bulk.yml` deployment job succeeds | Its dependent `run-etl` job | Starts/polls the same pipeline in Prod through configured protections |

Set `DEPLOY_METHOD=bulk` for this route. For other values and their capabilities,
use the [README method matrix](README.md#choose-a-deployment-method). Unselected
jobs may appear as skipped workflow runs; changing the selector alone does
not initiate a deployment.

### The Bulk Deploy Job

Each deploy workflow calls `reusable-deploy-bulk.yml`, which invokes `scripts/deploy_fabric_rest_bulk.py`. The script:

1. Acquires an Entra ID bearer token using the SPN's client credentials.
2. Walks `data/fabric/` and builds a `definitionParts[]` array — one entry per file, with the path and base64-encoded content.
3. Loads `bulk-parameter.yml` to get the substitution rules and value-set activation config.
4. Validates target connection GUIDs before publishing and stages dynamic-ID
   dependencies, with DataPipelines deferred until their model IDs are known.
5. POSTs to `https://api.fabric.microsoft.com/v1/workspaces/{ws}/items/bulkImportDefinitions?beta=true`
   in the required batches: three for this sample.
6. PATCHes the deployed VariableLibrary to set the active value set.

The Bulk Import API can return `200 OK` with the result body inline, or `202 Accepted` with a Long-Running Operation (LRO). The script handles both transparently — see [Gotchas](#lro-polling).

The dependent ETL job starts the pipeline only after deployment succeeds. Fabric
then owns load → validation → native refresh. A failed activity prevents its
success dependents; GitHub does not perform an external refresh.

---

## GitHub Actions Workflows

Use the [shared reference](fabric-hybrid-cicd-guide.md#github-actions-workflows)
for all workflow triggers, selectors, and runners. The templates below are
the raw route's local implementation details.

### Reusable Templates (called via `workflow_call`)

| Template | Purpose |
|---|---|
| `reusable-deploy-bulk.yml` | Acquires a token (via the SPN secrets), checks out the repo, installs `requests` + `PyYAML`, and invokes `scripts/deploy_fabric_rest_bulk.py` with the workspace ID, repository directory, and target environment as env vars. |
| `reusable-fabric-etl.yml` | Resolves a Fabric item by **name/type**, starts and polls its job, and reports failures. All four methods select the DataPipeline; Fabric owns validation and refresh. |

Test and Prod configure `item_type: DataPipeline`, `job_type: Pipeline`, and
an optional `run_label` passed through `RUN_LABEL` to the JSON job parameters.
The runner still supports unparameterized Notebook jobs, but no external
refresh input or fallback remains. See the
[shared pipeline contract](fabric-hybrid-cicd-guide.md#post-etl-semantic-model-refresh)
for Direct Lake framing, completion/failure criteria, and the live-validation boundary.

### Why Reusable Workflows (Not Composite Actions)

Reusable workflows support the `environment:` keyword at the job level, which enables:

- **GitHub Environment protection rules** (required reviewers, branch restrictions on Prod)
- **Environment-scoped secrets** (each environment has its own `FABRIC_WORKSPACE_ID`)
- `secrets: inherit` forwards all environment secrets without enumeration

### Manual Re-runs via `workflow_dispatch`

`etl-test.yml` and `etl-prod.yml` are manual recovery workflows. Automatic ETL
is a dependent job in the deployment workflow, so it uses that branch's
revision rather than a default-branch listener. Dispatch recovery from `test`
for Test or `main` for Prod; it does not republish definitions.

---

## Configuration Strategy

Three complementary mechanisms handle environment-specific configuration in the bulk path. The first two mirror the [fabric-cicd path's strategy](fabric-hybrid-cicd-guide.md#configuration-strategy); the third is bulk-specific because the API itself doesn't activate value sets.

### 1. Variable Libraries (Runtime)

Notebooks call `notebookutils.variableLibrary.getLibrary("Patterns_Variables")` at execution time to resolve workspace IDs, lakehouse names, and other values. The Variable Library has **value sets** per environment:

| Variable | Default (Dev) | Test | Prod |
|---|---|---|---|
| `target_workspace_id` | Dev workspace ID | Test workspace ID | Prod workspace ID |
| `target_workspace_name` | `microsoft-fabric-sdlc-patterns-dev` | `microsoft-fabric-sdlc-patterns-test` | `microsoft-fabric-sdlc-patterns-prod` |
| `target_lakehouse_name` | `PatternsLakehouse` | *(default)* | *(default)* |
| `target_lakehouse_id` | Dev lakehouse ID | Dev lakehouse ID* | Dev lakehouse ID* |
| `minimum_patient_count` (Integer) | `5` | `5` | `5` |

\* Test/Prod inherit `target_lakehouse_id` from the base [variables.json](data/fabric/Patterns_Variables.VariableLibrary/variables.json); they do not override it in their value-set files. The raw caller applies [bulk-parameter.yml](data/fabric/bulk-parameter.yml) to replace that base placeholder with the deployed Lakehouse ID.

The pipeline binds the active Library's positive patient minimum to the
validation notebook's base parameter. Validation uses that passed value;
`run_label` is an independent String pipeline parameter, not another Library
policy or a hardcoded fixture count.

### 2. `bulk-parameter.yml` (Deploy-time)

This is the bulk path's equivalent of fabric-cicd's `parameter.yml`. The format is intentionally distinct — bulk implements a narrow subset of fabric-cicd's DSL, only what this repo's deploys need.

These illustrate the Lakehouse/workspace rules in
[bulk-parameter.yml](data/fabric/bulk-parameter.yml); the full file also contains
the DataPipeline model and runtime-connection replacements:

```yaml
substitutions:
  - find: "c185283c-9dd9-4e40-a17c-aa6303e3a2e9"            # dev lakehouse ID
    replace_with: "$items.Lakehouse.PatternsLakehouse.$id"
    item_types: [VariableLibrary, SemanticModel, Notebook]

  - find: "d7270f11-feba-4990-baa6-d45e47f23737"            # dev workspace ID
    replace_with: "$workspace.$id"
    item_types: [SemanticModel, Notebook, DataPipeline]

variable_library:
  active_value_set: "$environment"
```

**Schema:**

| Top-level key | Purpose |
|---|---|
| `substitutions` | List of find/replace rules. Each rule has `find` (the literal string), `replace_with` (the replacement, with optional placeholders), and `item_types` (list of item types this rule applies to). |
| `variable_library` | Per-VariableLibrary settings. Currently just `active_value_set`. |

**Placeholder reference:**

| Placeholder | Resolved to |
|---|---|
| `$workspace.$id` | The target workspace ID (from the `FABRIC_WORKSPACE_ID` env var) |
| `$items.<Type>.<Name>.$id` | The target item ID captured from an earlier bulk response: Lakehouse/Ontology in phase 1, Semantic Model in phase 2. |
| `$environment` | The value of the `ENVIRONMENT` env var passed to the deploy step (`Test` or `Prod`). |

**`item_types` filter:** A rule only fires for files whose item type is in the rule's `item_types` list. The script extracts the item type from the path convention `<DisplayName>.<Type>/<file>`. Files outside the listed types pass through unchanged.

The native model reference uses
`$items.SemanticModel.Patterns_Semantic_Model.$id`, not the Dev physical ID.
The caller also resolves the source connection markers from the target's
`NOTEBOOK_CONNECTION_ID` and `SEMANTIC_MODEL_REFRESH_CONNECTION_ID`
[Environment variables](SETUP.md#environment-variables). GUID preflight and
replacement do not create connections or prove their Workspace Identity access.

**Why a separate file from `parameter.yml`:** The two formats coexist deliberately. fabric-cicd uses `parameter.yml`; bulk uses `bulk-parameter.yml`. Keeping them separate means bulk doesn't have to silently ignore (or break on) fabric-cicd-only features (`key_value_replace`, `spark_pool`, `semantic_model_binding`). Both files live at the root of `data/fabric/` and both are excluded from the bulk request payload by `scripts/deploy_fabric_rest_bulk.py`.

### 3. VariableLibrary Value-Set Activation (Post-deploy)

The Bulk Import API uploads the VariableLibrary's value-set files but does NOT set which one is active in the deployed workspace. fabric-cicd makes that selection automatically via its `environment` parameter; with the bulk API, the caller must do it.

`scripts/deploy_fabric_rest_bulk.py` makes the call after the bulk POSTs complete:

```
PATCH /v1/workspaces/{workspace_id}/variableLibraries/{library_id}
Content-Type: application/json

{
  "properties": {
    "activeValueSetName": "Test"
  }
}
```

The activation is gated on `bulk-parameter.yml`'s `variable_library.active_value_set` being non-null. The placeholder `$environment` resolves to the target environment name (`Test` or `Prod`). If you set the field to a literal string instead, that exact value is used.

Reference: [Update Variable Library](https://learn.microsoft.com/en-us/rest/api/fabric/variablelibrary/items/update-variable-library).

---

<a id="the-two-deploy-decision"></a>

## The Staged-Deploy Decision

Dynamic `$items.<Type>.<Name>.$id` rules require earlier target IDs before
dependent payloads can be substituted. This sample uses **three publication
batches**: Lakehouse/Ontology, their non-pipeline dependents, then DataPipeline
with the model ID created in phase 2. Other inventories can need fewer batches.

### Single-deploy flow (no `$items.*` references, or no config at all)

```
1. apply_substitutions(parts, rules, workspace_id, item_id_map={})
2. POST all items at once
3. PATCH VariableLibrary if value-set activation is configured
```

`$workspace.$id`-only rules are applied in this flow because the workspace ID is known up front from the env var.
This is the no-dynamic-dependency case, not this sample's pipeline deployment.

<a id="two-deploy-flow-rules-reference-items"></a>

### Staged flow (dynamic IDs; third pipeline batch)

```
1. separate foundations, non-pipeline dependents, and DataPipeline items
2. POST Lakehouse + Ontology; capture target IDs       Phase 1
3. substitute foundation IDs into non-pipeline items
4. POST those items; capture target Semantic Model ID Phase 2
5. substitute model/workspace/connection IDs in DataPipeline
6. POST the deferred DataPipeline definition          Phase 3
7. PATCH VariableLibrary only after all imports succeed
```

`DEPENDENCY_TYPES` identifies the phase 1 foundations, currently Lakehouse and
Ontology. The Semantic Model has a Lakehouse prerequisite and therefore stays
in phase 2; DataPipeline is deferred until its physical model ID is available.
Moving every `$items` target into phase 1 would break this dependency chain.

Phase 2 excludes deferred DataPipeline definitions and captures the model ID
from its response. Phase 3 resolves the pipeline's actual model reference only
after that import succeeds. The default SDK route likewise isolates pipeline
publication in a third call, but resolves references through fresh fabric-cicd
workspace discovery rather than this raw response-ID map.

### When the script fails fast

The script raises a clear error in two situations:

- **Substitution rules reference `$items.<Type>.<Name>.$id`, but no items of dependency types are found in the repo.** The deploy can't satisfy the placeholder.
- **A rule references an item the script can't find by `(Type, Name)`.** The placeholder won't resolve. Common cause: typo in `bulk-parameter.yml`.

Invalid connection GUIDs fail before the first definition POST. Missing
dynamic references fail before their dependent request; a later failure does
not undo already-imported items. Never treat partial publication as success.

---

## Prerequisites & Setup

### 1. Fabric Capacity

A Fabric or Power BI Premium capacity is required for all workspaces.

### 2. Fabric Workspaces

Three workspaces are needed:

- **microsoft-fabric-sdlc-patterns-dev** — connected to the `dev` branch via Fabric Git integration
- **microsoft-fabric-sdlc-patterns-test** — not Git-connected, receives deployments via the Bulk Import API
- **microsoft-fabric-sdlc-patterns-prod** — not Git-connected, receives deployments via the Bulk Import API

### 3. Service Principal

Create a Service Principal for CI/CD automation:

```bash
az ad sp create-for-rbac --name "SPN-Microsoft-Fabric-SDLC-Patterns" \
  --query "{tenantId:tenant, clientId:appId, clientSecret:password}" -o json
```

- Add the SPN as **Contributor** on both Test and Prod workspaces (Workspace → Manage access → Add people or groups).
- Contributor is the minimum required role per the [Fabric Create Item API](https://learn.microsoft.com/en-us/rest/api/fabric/core/items/create-item) documentation.
- **Critical for bulk:** every item type in your repo must support service principals. The Bulk Import API enforces SPN coverage at the request level — a single unsupported item type fails the whole call. See the [comparison table in release-options](fabric-cicd-release-options.md#tooling-within-option-3-fabric-cicd-vs-bulk-apis) for context.

> **Important:** A Fabric Admin must enable service principal access to Fabric APIs in the Fabric Admin portal under Developer settings, scoped to a security group containing only your CI/CD SPs. See [developer tenant settings](https://learn.microsoft.com/en-us/fabric/admin/service-admin-portal-developer) and the [Governance Considerations](fabric-cicd-governance-considerations.md) for details.

### 4. GitHub Environments

Create two GitHub Environments in the repository settings (Settings → Environments):

| Environment | Protection Rules |
|---|---|
| `Test` | None (deploy flows automatically on merge) |
| `Prod` | Required reviewers, deployment branch restriction to `main` only |

> **Note:** The environment name is also used as the value substituted for `$environment` in `bulk-parameter.yml`'s `active_value_set` placeholder. So the GitHub Environment names must match the Variable Library value-set names (`Test`, `Prod`) exactly.

### 5. GitHub Environment Secrets

Add these secrets to **both** `Test` and `Prod` environments:

| Secret | Description |
|---|---|
| `AZURE_TENANT_ID` | Entra ID tenant ID |
| `AZURE_CLIENT_ID` | Service Principal client/app ID |
| `AZURE_CLIENT_SECRET` | Service Principal client secret |
| `FABRIC_WORKSPACE_ID` | Target workspace ID (different per environment) |

The first three secrets are identical across environments (single SPN). `FABRIC_WORKSPACE_ID` differs:

- Test: the Test workspace ID
- Prod: the Prod workspace ID

These credentials authenticate publication/job submission, not activity runtime.
The explicit provisioning action creates/shares the target WI pair and saves
its two environment GUID variables. Publishers consume them read-only before
substitution. The setup contract is described in [Setup](SETUP.md#environment-variables); verify
[runtime/model/source permissions](SETUP.md#post-etl-refresh-permissions).
Successful raw publishing does not prove activity or consumer authorization.

### 6. Set the `DEPLOY_METHOD` Repository Variable

Set `DEPLOY_METHOD=bulk` in Settings → Secrets and variables → Actions →
Variables for this raw deployment job. Unset selects standard `fabric-cicd`;
other selectors follow the [README matrix](README.md#choose-a-deployment-method).

---

## Initial Deployment to a Clean Workspace

This walkthrough uses the raw REST route. Follow these steps for a clean target.
Subsequent publication, ETL, and model refresh are automated, subject to
configured approvals; required release validation and any changed prerequisite
configuration remain separate.

### Step 1: Trigger the Deployment

With `DEPLOY_METHOD=bulk`, merge a qualifying `dev -> test` or `test -> main`
PR containing Fabric definition or workflow changes. Configured deployment
approvals apply. The raw deployment job executes:

- **Phase 1 (if needed):** POST Lakehouse + Ontology
- **Phase 2:** Substitute phase 1 IDs and POST non-pipeline dependents, capturing
  the target Semantic Model ID
- **Phase 3:** Substitute that model ID and target connection GUIDs, then POST
  `Patterns_Load_Validate_And_Refresh`
- **Post-deploy:** PATCH the VariableLibrary to set the active value set for the environment

### Step 2: ETL Populates the Lakehouse, Then Refreshes the Model

After successful deployment, the ETL workflow starts/polls one DataPipeline.
The unchanged loader populates `doctors`, `patients`, and `appointments`; the
read-only validation notebook checks schemas, keys, references, source date
types, and the active Library minimum. Only then does native refresh frame
`Patterns_Semantic_Model` and wait for completion. GitHub performs no second
refresh, and publication phases do not execute these activities.

### Step 3: Configure Graph Model Data Source (Manual)

The Ontology is deployed as a definition only — its Graph Model does not have a data source binding until you configure it manually.

1. Open the **Ontology** item in the Fabric UI and navigate to the **Graph Model**.
2. Select **Get data** to bind the Graph Model to the lakehouse tables.

### Step 4: Activate the Ontology (Manual Workaround)

After configuring the data source, the Ontology may remain stuck on *"Setting up your ontology — We are preparing the ontology overview for the first time."* This is a known Fabric platform behavior on initial deployment.

**Workaround:** Select any Entity Type in the Ontology, rename it to something temporary, then rename it back to its original name. This triggers Fabric to finish initializing the Ontology overview.

### Step 5: Verify End-to-End

Confirm all items are functional in the target workspace:

- **Lakehouse** — tables populated with data
- **Ontology** — overview loads, entity types and relationships visible
- **Variable Library** — active value set matches the target environment (`Test` or `Prod`)
- **DataPipeline** — correct physical model/connection references, intended
  Workspace Identity credentials, parameter forwarding, and terminal success
- **Semantic Model** — post-ETL refresh completed; verify the local Lakehouse connection, model-owner/source permissions, required fields, and calculations (configure a supported connection if required on first deploy)
- **Report** — renders with data from the Semantic Model
- **Data Agent** — references the Ontology and responds to queries

> **Note:** Steps 3–4 (Ontology activation) are platform behaviors, not bulk-specific. The fabric-cicd path requires the same manual steps on first deploy.

Pipeline validation and refresh completion do not replace these consumer checks or the
[required release evidence](fabric-cicd-quality-gates-and-release-controls.md).

---

## Gotchas & Key Decisions

<a id="two-deploy-chicken-and-egg"></a>

### Staged-Deploy Chicken-and-Egg

The Variable Library, Semantic Model, and notebooks reference the lakehouse ID for each environment, but the lakehouse doesn't exist in Test/Prod until the first deployment creates it. With the bulk API, there's no library-side resolution of these references — the script must POST the dependency items first, read their IDs from the response, then substitute into the remaining items before the second POST.

**Solution:** [Staged deployment](#the-staged-deploy-decision). Phase 1 creates
Lakehouse/Ontology; phase 2 imports non-pipeline dependents; phase 3 resolves the
captured model ID for the DataPipeline. These raw definition POSTs are distinct
from the default SDK runner's three library calls and the single workload run.

### Per-Request Service Principal Coverage

The Bulk Import API requires that **every** item type in the request payload supports service principals. If even one type doesn't, the entire request fails with an authorization error — there's no graceful degradation.

Standard fabric-cicd uses per-item requests; fabric-cicd bulk also requires
support for every submitted item type and operation. Selecting fabric-cicd
does not grant permissions or fall back to a user identity.

**Solution:** Verify SPN coverage for every submitted item type and operation.
The scope now includes `DataPipeline` as the eighth workload type. User API
create/export and feature activity success are not evidence of CI
service-principal raw bulk publication/start. Validate the selected route in
an approved nonproduction target before promotion; do not infer end-to-end
support from the UI or offline contracts.

### LRO Polling

The Bulk Import API can return either:

- **`200 OK`** with the full result body (`importItemDefinitionsDetails[]`) inline — synchronous case
- **`202 Accepted`** with an `x-ms-operation-id` header and a `Retry-After` header — asynchronous, caller polls a Long-Running Operation

`scripts/deploy_fabric_rest_bulk.py` handles both transparently. For the LRO case, it polls `GET /v1/operations/{id}` until the operation reaches `Succeeded`, `Failed`, or `Undefined`, then fetches `GET /v1/operations/{id}/result` for the same `importItemDefinitionsDetails[]` shape the sync case returns inline.

### Retry-After Clamping

The script clamps the `Retry-After` header to `[5s, 600s]` and falls back to 30s on missing or unparseable values. Without the upper bound, a pathological `Retry-After` could cause a single sleep longer than the global polling timeout (20 minutes), making the timeout meaningless. Without the input validation, a non-integer value would crash the script with an unhandled `ValueError`.

### Bearer Token Is Not Echoed to Logs

An earlier version of the script emitted `::add-mask::<token>` to register a workflow log mask. That line itself emitted the token to stdout in cleartext, defeating the mask's purpose (the runner only redacts subsequent output). The current script never prints the token. The SPN secret is masked by GitHub automatically because it comes from `secrets.AZURE_CLIENT_SECRET`.

### `bulk-parameter.yml` Is Excluded from the Request Payload

The script lists `bulk-parameter.yml`, `parameter.yml`, and `.gitkeep` in `EXCLUDED_FILES` so they're never sent to Fabric as part of the bulk request. The structural rule "files at the root of `repository_directory` are not item definitions" already excludes them, but the explicit list documents intent.

Git-synced `*.DeploymentPlan` item folders are also excluded. This raw Bulk
example does not attach a native plan to its request; the
[plan-driven adapter](fabric-deployment-plan-guide.md) is a separate method.

### `workflow_run` Quirk: Re-runs Use the Frozen Workflow File

This heading is retained for older links. The old automatic listener design
has been replaced with a same-workflow `needs` chain. An old run still uses its
original revision; rerunning it is not a way to test new code. Use a new
deployment dispatch or the manual recovery workflow on the intended branch.
The renamed `Deploy and Run Pipeline` callers also avoid matching legacy
default-branch listeners during rollout, preventing duplicate automatic ETLs.

### `?beta=true` Required Today

The bulk endpoint URL is currently `POST /v1/workspaces/{ws}/items/bulkImportDefinitions?beta=true`. When the API graduates from Preview, drop the query parameter. The TODO is noted in the script's module docstring and in `reusable-deploy-bulk.yml`.

### Microsoft Tutorial's URL Is Wrong

The Microsoft Learn [Bulk Import tutorial](https://learn.microsoft.com/en-us/fabric/cicd/tutorial-bulkapi-cicd) uses `/importItemDefinitions` (singular) — that endpoint produces `404`. The correct path is `/items/bulkImportDefinitions` per the [API reference page](https://learn.microsoft.com/en-us/rest/api/fabric/core/items/bulk-import-item-definitions). Verified against a live workspace.

---

## Extending the Bulk Implementation

The script is structured so common extension cases are localized. Here's the shape of each.

### Adding a new substitution rule

Edit `data/fabric/bulk-parameter.yml`:

```yaml
substitutions:
  # ... existing rules ...
  - find: "<old-string>"
    replace_with: "<new-string-or-placeholder>"
    item_types: [Notebook, SemanticModel]
```

No code change required. The new rule is picked up automatically on the next deploy.

If the new rule references `$items.<Type>.<Name>.$id` for a new item type, also extend `DEPENDENCY_TYPES` in `scripts/deploy_fabric_rest_bulk.py` so that type deploys in Phase 1.

### Adding a new placeholder type

To add e.g. `$secrets.<name>` resolving to a CI secret, modify `scripts/deploy_fabric_rest_bulk.py`:

1. Add a constant `_SECRETS_PLACEHOLDER = re.compile(r"\$secrets\.([^.\s]+)")`.
2. In `resolve_dynamic_value()`, add a `_SECRETS_PLACEHOLDER.sub(...)` call.
3. Add a corresponding env var (e.g. `BULK_SECRETS_JSON`) and read it in `main()`.
4. Add tests for the new resolver.

The pattern follows what `$workspace.$id` and `$items.<Type>.<Name>.$id` already do.

### Adding a new dependency type

If a new item type becomes a target of `$items.<Type>.*` substitutions (e.g. a new Warehouse that other items depend on):

```python
DEPENDENCY_TYPES = ("Lakehouse", "Ontology", "Warehouse")
```

For a foundation type this extends phase 1. If the new type has prerequisites
of its own, define a later batch and regression tests instead of moving it
ahead of those prerequisites. The pipeline/model chain is the existing example.

### Adding a new post-deploy hook

The VariableLibrary value-set activation is the existing example. To add another (e.g. creating a Lakehouse Shortcut after the deploy):

1. Add a new helper, e.g. `create_shortcut(workspace_id, lakehouse_id, shortcut_config, headers)` that wraps the appropriate Fabric REST API call.
2. Add a corresponding config block to `BulkConfig` (e.g. `shortcuts: tuple[ShortcutConfig, ...]`).
3. Extend `load_bulk_config()` to parse the new block from `bulk-parameter.yml`.
4. Wire the hook in `main()` after the deploy, alongside the existing value-set activation.
5. Add unit tests for the helper and the config parsing.

The pattern is intentionally repeatable — every post-deploy step is "config block in YAML → dataclass field → helper function → call site in `main()`."

### Adding a new bulk-config block

The shipped config has `substitutions` and `variable_library`. To add a third block (e.g. `shortcuts` per above):

1. Add a new `@dataclass(frozen=True)` for the block's contents (e.g. `ShortcutConfig`).
2. Add it as a field on `BulkConfig` with a sensible default.
3. Extend `load_bulk_config()` to parse the new block, with explicit error messages for malformed input.
4. Add tests covering the happy path, missing-block fallback, and each documented error case.

The existing `VariableLibraryConfig` is a working example.

---

## Limitations Not Bridged

This repo's bulk path implements substitution and value-set activation but does NOT bridge the following. If you choose the bulk path in your own project, you'll need to implement these or accept their absence.

| Limitation | What's missing | Workaround if you need it |
|---|---|---|
| **Orphan cleanup** | Bulk Import API only supports Create/Update — no Delete. Items removed from the repo stay in the workspace. | Maintain a separate per-item `DELETE` loop after the bulk POST. |
| **`key_value_replace`** | fabric-cicd's JSONPath-based key replacement (e.g., connection IDs in pipeline JSON). | Extend `apply_substitutions()` to support a JSONPath-style replacement step in addition to literal find/replace. |
| **`spark_pool` substitution** | fabric-cicd's per-environment Spark pool swapping. | Add a config block + post-deploy API call (similar to value-set activation). |
| **`semantic_model_binding`** | fabric-cicd's auto-binding of semantic models to data source connections. | Add a post-deploy API call against the Semantic Model. |
| **Per-item SPN graceful degradation** | Bulk fails the whole request if any item type is unsupported by SPNs. | Pre-flight check: list item types in the request, validate against a known-supported set. |
| **Multi-VariableLibrary handling** | `find_variable_library_id()` raises if multiple VariableLibraries are present (the activation step targets one). | Refactor the activation flow to take a per-library config and iterate. |
| **`item_type_in_scope` filter** | The script deploys everything in `repository_directory`. No way to scope a deploy to a subset. | Add an env var read in `main()` and filter parts before the POST. |

These are deliberate non-goals for this demo repo. They can be added incrementally using the [extension patterns](#extending-the-bulk-implementation) above.

---

## References

- [fabric-cicd-release-options.md](fabric-cicd-release-options.md) — Strategy doc with the fabric-cicd vs Bulk APIs comparison
- [fabric-cicd Non-Bulk CI/CD Guide](fabric-hybrid-cicd-guide.md) — Default non-bulk implementation and shared workflow reference
- [fabric-cicd-governance-considerations.md](fabric-cicd-governance-considerations.md) — Identity, RBAC, branch protection, approval gates
- [Fabric Bulk Import Item Definitions API (Preview)](https://learn.microsoft.com/en-us/rest/api/fabric/core/items/bulk-import-item-definitions) — Endpoint reference
- [Fabric Long-Running Operations](https://learn.microsoft.com/en-us/rest/api/fabric/articles/long-running-operation) — `?async=true` semantics, polling pattern
- [Fabric Update Variable Library](https://learn.microsoft.com/en-us/rest/api/fabric/variablelibrary/items/update-variable-library) — PATCH endpoint used by value-set activation
- [Microsoft Bulk Import tutorial](https://learn.microsoft.com/en-us/fabric/cicd/tutorial-bulkapi-cicd) — Microsoft's walkthrough (note the URL discrepancy called out under [Gotchas](#microsoft-tutorials-url-is-wrong))
- [Fabric Create Item API — Permissions](https://learn.microsoft.com/en-us/rest/api/fabric/core/items/create-item) — Contributor role requirement
- [GitHub Reusable Workflows](https://docs.github.com/en/actions/sharing-automations/reusing-workflows) — `workflow_call`, inputs, secrets
