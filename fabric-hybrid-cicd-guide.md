# Microsoft Fabric SDLC Patterns — CI/CD Implementation

This repository implements the **Hybrid CI/CD recommendation** for Microsoft Fabric using **fabric-cicd**. It demonstrates how to deploy Fabric workspace items (Notebooks, Lakehouses, Variable Libraries, Semantic Models, Reports, Ontologies, Data Agents) across environments using GitHub Actions.

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
│  deploy-supported                                   │
│    └─ reusable-deploy-supported.yml                 │
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
│       ├── deploy-test.yml                  # Orchestrator: push to test → deploy + ETL
│       ├── deploy-prod.yml                  # Orchestrator: push to main → deploy + ETL
│       ├── etl-test.yml                     # Triggers after deploy-test succeeds
│       ├── etl-prod.yml                     # Triggers after deploy-prod succeeds
│       ├── reusable-deploy-supported.yml    # Template: fabric-cicd deployment
│       ├── reusable-fabric-etl.yml          # Template: run Notebook via Fabric REST API
│       └── validate-branch-env.yml          # PR check: blocks feature IDs from merging to dev
├── data/
│   └── fabric/                              # Fabric item definitions (repository_directory)
│       ├── parameter.yml                    # fabric-cicd deploy-time parameterization
│       ├── PatternsLakehouse.Lakehouse/     # Lakehouse definition
│       ├── Patterns_Variables.             # Variable Library with value sets
│       │   VariableLibrary/
│       │   ├── variables.json              # Default (Dev) variable values
│       │   ├── settings.json               # Value set ordering
│       │   └── valueSets/
│       │       ├── Test.json               # Test environment overrides
│       │       └── Prod.json               # Prod environment overrides
│       ├── Import_Patterns_Data.            # ETL notebook (creates Delta tables)
│       │   Notebook/
│       └── Patterns_Patients_Data.Notebook/ # Query notebook (reads patients table)
├── scripts/
│   └── branch_env.py                       # Bootstrap/reset feature branch workspace bindings
├── assets/                                  # Architecture diagrams (SVG)
├── fabric-cicd-release-options.md           # CI/CD strategy and release option comparison
├── fabric-hybrid-cicd-guide.md               # This file
├── fabric-development-process.md             # Development process
└── README.md                                # Repository landing page
```

---

## Deployment Flow

### What Triggers What

| Event | Workflow Triggered | What It Does |
|---|---|---|
| Push to `test` branch (changes in `data/fabric/**`) | `deploy-test.yml` | Deploys all supported items to the Test workspace |
| `deploy-test.yml` completes successfully | `etl-test.yml` | Runs the `Import_Patterns_Data` notebook in the Test workspace |
| Push to `main` branch (changes in `data/fabric/**`) | `deploy-prod.yml` | Deploys all supported items to the Prod workspace |
| `deploy-prod.yml` completes successfully | `etl-prod.yml` | Runs the `Import_Patterns_Data` notebook in the Prod workspace |

### Deploy Job

Each deploy workflow calls `reusable-deploy-supported.yml`, which publishes all supported items from Git to the target workspace using fabric-cicd. It uses a two-phase approach: Phase 1 deploys Lakehouse + Ontology, Phase 2 deploys all remaining items (Variable Library, Notebooks, Semantic Model, Report, Data Agent). Item types are explicitly scoped via `item_type_in_scope`.

The ETL workflow triggers automatically after the deploy workflow completes successfully. If the deploy fails, ETL does not run.

> **Note:** If your workspace includes item types not yet supported by fabric-cicd, you can extend this to a multi-job "sandwich" pattern: (1) deploy supported items, (2) promote unsupported items via the [Fabric Deployment Pipelines REST API](https://learn.microsoft.com/en-us/rest/api/fabric/core/deployment-pipelines/deploy-stage-content), (3) deploy supported items that depend on the unsupported items. See [fabric-cicd-release-options.md](fabric-cicd-release-options.md) for details.

---

## GitHub Actions Workflows

### Reusable Templates (called via `workflow_call`)

| Template | Purpose |
|---|---|
| `reusable-deploy-supported.yml` | Two-phase fabric-cicd deployment: Phase 1 deploys Lakehouse + Ontology, Phase 2 deploys all remaining items via `publish_all_items()` and `unpublish_all_orphan_items()`. Accepts `environment`, `repository_directory`, and optional `item_type_in_scope` inputs. |
| `reusable-fabric-etl.yml` | Resolves a Fabric item by **name** (not ID) via the List Items API, then starts a job (RunNotebook) and polls until completion. No item IDs need to be known ahead of time. |

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

\* The `target_lakehouse_id` uses the Dev GUID as a placeholder in the value set files. At deploy time, `parameter.yml` replaces it with the actual lakehouse ID in the target workspace (see below).

**Active value set binding:** fabric-cicd automatically sets the active value set based on the `environment` parameter passed to `FabricWorkspace`. When `environment="Test"`, the `Test` value set becomes active. This happens on every deployment — no manual intervention needed.

> Citation: [fabric-cicd Item Types — Variable Library](https://microsoft.github.io/fabric-cicd/latest/how_to/item_types/#variable-library): *"The active value set of the variable library is defined by the `environment` field passed into the `FabricWorkspace` object."*

### 2. parameter.yml (Deploy-time)

The `parameter.yml` file in `data/fabric/` uses fabric-cicd's `find_replace` with **dynamic replacement** to resolve the lakehouse ID at deploy time:

```yaml
find_replace:
    - find_value: "7694ebac-deb9-4a40-a846-0782b36b3bda"  # Dev lakehouse ID
      replace_value:
          _ALL_: "$items.Lakehouse.PatternsLakehouse.$id"  # Resolved at deploy time
      item_type: "VariableLibrary"
```

**How it works:** fabric-cicd deploys items in dependency order — the Lakehouse is created before the Variable Library. When processing Variable Library files, `$items.Lakehouse.PatternsLakehouse.$id` resolves to the actual lakehouse GUID in the target workspace. The `_ALL_` key means this applies to every environment.

---

## Prerequisites & Setup

### 1. Fabric Capacity

A Fabric or Power BI Premium capacity is required for all workspaces.

### 2. Fabric Workspaces

Three workspaces are needed:
- **microsoft-fabric-sdlc-patterns-dev** — connected to the `dev` branch via Fabric Git integration
- **microsoft-fabric-sdlc-patterns-test** — not Git-connected, receives deployments via fabric-cicd
- **microsoft-fabric-sdlc-patterns-prod** — not Git-connected, receives deployments via fabric-cicd

### 3. Service Principal

Create a Service Principal for CI/CD automation:

```bash
az ad sp create-for-rbac --name "SPN-Microsoft-Fabric-SDLC-Patterns" \
  --query "{tenantId:tenant, clientId:appId, clientSecret:password}" -o json
```

- Add the SPN as **Contributor** on both Test and Prod workspaces (Workspace → Manage access → Add people or groups)
- Contributor is the minimum required role per the [Fabric Create Item API](https://learn.microsoft.com/en-us/rest/api/fabric/core/items/create-item) documentation

> **Important:** A Fabric Admin must enable **"Service principals can use Fabric APIs"** in the Fabric Admin portal → Tenant settings → Developer settings.

### 4. GitHub Environments

Create two GitHub Environments in the repository settings (Settings → Environments):

| Environment | Protection Rules |
|---|---|
| `Test` | None (deploy flows automatically on merge) |
| `Prod` | Required reviewers, deployment branch restriction to `main` only |

> **Note:** GitHub Environment names are case-insensitive, but the names must match the Variable Library value set names (`Test`, `Prod`) because fabric-cicd uses the `environment` value to set the active value set.

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

### 6. Copilot Instructions

The `.github/instructions/actions.instructions.md` file provides path-specific Copilot instructions for authoring GitHub Actions workflows. It applies automatically when editing any `.yml` file under `.github/workflows/` and covers security (pin actions to SHA, minimal permissions), performance (`timeout-minutes`), and fabric-cicd best practices.

---

## Initial Deployment to a Clean Workspace

When deploying to a workspace for the first time (e.g., a newly created Test or Prod workspace), follow these steps in order. Subsequent deployments are fully automated — only the first deployment requires manual intervention.

### Step 1: Trigger the Deployment

Push to the target branch (`test` or `main`). The deploy workflow triggers automatically and executes two phases:

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
- **Semantic Model** — connected to the lakehouse (may require manual connection config on first deploy; see [Gotchas](#semantic-model-initial-connection))
- **Report** — renders with data from the Semantic Model
- **Data Agent** — references the Ontology and responds to queries

> **Note:** On subsequent deployments, all steps are automated. The manual Ontology steps (3–4) are only required on the first deployment to a clean workspace.

---

## Gotchas & Key Decisions

### Chicken-and-Egg: Lakehouse ID

The Variable Library and Semantic Model need the lakehouse ID for each environment, but the lakehouse doesn't exist in Test/Prod until the first deployment creates it. fabric-cicd's `$items` dynamic variables (e.g., `$items.Lakehouse.PatternsLakehouse.$id`) resolve by querying the **live target workspace** during parameterization — before items are published. On the first deployment to an empty workspace, this query returns nothing and parameterization fails.

**Solution:** The `reusable-deploy-supported.yml` workflow uses a **two-phase deployment** approach. Phase 1 calls `publish_all_items()` with `item_type_in_scope=["Lakehouse", "Ontology"]` to create the Lakehouse and Ontology first. The Lakehouse must exist so that `$items.Lakehouse.PatternsLakehouse.$id` resolves for parameter.yml rules. The Ontology must exist so that the Data Agent's logicalId reference resolves (fabric-cicd caches workspace state once per `publish_all_items()` call, so items deployed within the same call aren't visible to later items' logicalId resolution). Phase 2 calls `publish_all_items()` with the remaining item types. On subsequent deployments, both phases are idempotent.

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

fabric-cicd does not calculate diffs between commits. Every item in scope is published on each run. This is by design — it ensures the workspace always matches the Git repo exactly.

### DefaultAzureCredential is Deprecated

fabric-cicd has deprecated `DefaultAzureCredential`. All workflows use `ClientSecretCredential` explicitly, per the [fabric-cicd authentication docs](https://microsoft.github.io/fabric-cicd/latest/example/authentication/).

### Path Filter Prevents Unnecessary Runs

Deploy workflows only trigger when files under `data/fabric/**` change. Documentation-only commits (e.g., editing this README) do not trigger a deployment.

---

## References

- [Fabric CI/CD Release Options](fabric-cicd-release-options.md) — Full strategy document with release option comparison and hybrid recommendation
- [fabric-cicd Python Library](https://microsoft.github.io/fabric-cicd) — Docs, getting started, supported item types
- [fabric-cicd Parameterization](https://microsoft.github.io/fabric-cicd/latest/how_to/parameterization/) — `parameter.yml` reference with `find_replace`, `$items` dynamic replacement
- [fabric-cicd Item Types](https://microsoft.github.io/fabric-cicd/latest/how_to/item_types/) — Per-item-type notes including Variable Library active value set behavior
- [fabric-cicd Authentication Examples](https://microsoft.github.io/fabric-cicd/latest/example/authentication/) — GitHub Actions credential patterns
- [Fabric Create Item API — Permissions](https://learn.microsoft.com/en-us/rest/api/fabric/core/items/create-item) — Contributor role requirement
- [Fabric Permission Model](https://learn.microsoft.com/en-us/fabric/security/permission-model) — Workspace roles (Admin, Member, Contributor, Viewer)
- [Variable Library CI/CD](https://learn.microsoft.com/en-us/fabric/cicd/variable-library/variable-library-cicd) — Value sets, active set behavior, Git integration
- [GitHub Reusable Workflows](https://docs.github.com/en/actions/sharing-automations/reusing-workflows) — `workflow_call`, inputs, secrets
- [GitHub Environment Protection Rules](https://docs.github.com/en/actions/managing-workflow-runs-and-deployments/managing-deployments/managing-environments-for-deployment) — Required reviewers, deployment branch restrictions
- [GitHub Actions Helper — Custom Instructions](https://docs.github.com/en/copilot/tutorials/customization-library/custom-instructions/github-actions-helper) — Official Copilot instructions for Actions workflows
