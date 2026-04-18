# Fabulous One — Fabric CI/CD Implementation

This repository implements the **Hybrid CI/CD recommendation** for Microsoft Fabric using **fabric-cicd** and **Fabric Deployment Pipelines**. It demonstrates how to deploy Fabric workspace items (Notebooks, Lakehouses, Variable Libraries) across environments using GitHub Actions, with the sandwich pattern for unsupported items.

For the full CI/CD strategy, release option comparison, and recommendation rationale, see [best-practices-with-fabric-cicd-overview.md](best-practices-with-fabric-cicd-overview.md).

---

## Table of Contents

- [Architecture Overview](#architecture-overview)
- [Repository Structure](#repository-structure)
- [Deployment Flow](#deployment-flow)
- [GitHub Actions Workflows](#github-actions-workflows)
- [Configuration Strategy](#configuration-strategy)
- [Prerequisites & Setup](#prerequisites--setup)
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
│  Job 1: deploy-supported                            │
│    └─ reusable-deploy-supported.yml                 │
│       └─ fabric-cicd: publish_all_items()           │
│                    ↓ needs                           │
│  Job 2: promote-unsupported (skeleton)              │
│    └─ reusable-deploy-unsupported.yml               │
│       └─ TODO: Deployment Pipeline API              │
│                    ↓ needs                           │
│  Job 3: deploy-supported-dependent (skeleton)       │
│    └─ reusable-deploy-supported-dependent-on-       │
│       unsupported.yml                               │
│       └─ TODO: fabric-cicd for dependent items      │
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
| `dev` | Dev (fabulous-one-dev) | Git-connected via Fabric Git integration |
| `test` | Test (fabulous-one-test) | fabric-cicd via GitHub Actions |
| `main` | Prod (fabulous-one-prod) | fabric-cicd via GitHub Actions |

- **Dev** workspace is the only Git-connected workspace. Developers branch out from Dev for isolated feature work.
- **Test** and **Prod** workspaces are NOT Git-connected. They receive deployments exclusively through fabric-cicd and Deployment Pipelines.

---

## Repository Structure

```
fabulous-one/
├── .github/
│   ├── instructions/
│   │   └── actions.instructions.md          # Copilot instructions for workflow authoring
│   └── workflows/
│       ├── deploy-test.yml                  # Orchestrator: push to test → 3-job sandwich
│       ├── deploy-prod.yml                  # Orchestrator: push to main → 3-job sandwich
│       ├── etl-test.yml                     # Triggers after deploy-test succeeds
│       ├── etl-prod.yml                     # Triggers after deploy-prod succeeds
│       ├── reusable-deploy-supported.yml    # Template: fabric-cicd deployment
│       ├── reusable-deploy-unsupported.yml  # Template: SKELETON (Deployment Pipeline)
│       ├── reusable-deploy-supported-       # Template: SKELETON (dependent items)
│       │   dependent-on-unsupported.yml
│       └── reusable-fabric-etl.yml          # Template: run Notebook via Fabric REST API
├── data/
│   └── fabric/                              # Fabric item definitions (repository_directory)
│       ├── parameter.yml                    # fabric-cicd deploy-time parameterization
│       ├── FabulousLakehouse.Lakehouse/     # Lakehouse definition
│       ├── Fabulous_One_Variables.          # Variable Library with value sets
│       │   VariableLibrary/
│       │   ├── variables.json              # Default (Dev) variable values
│       │   ├── settings.json               # Value set ordering
│       │   └── valueSets/
│       │       ├── Test.json               # Test environment overrides
│       │       └── Prod.json               # Prod environment overrides
│       ├── Import_Fabulous_One_Data.        # ETL notebook (creates Delta tables)
│       │   Notebook/
│       └── Patients_Data.Notebook/          # Query notebook (reads patients table)
├── assets/                                  # Architecture diagrams (SVG)
├── best-practices-with-fabric-cicd-         # Full CI/CD strategy document
│   overview.md
└── README.md                                # This file
```

---

## Deployment Flow

### What Triggers What

| Event | Workflow Triggered | What It Does |
|---|---|---|
| Push to `test` branch (changes in `data/fabric/**`) | `deploy-test.yml` | Runs the 3-job sandwich deploying to the Test workspace |
| `deploy-test.yml` completes successfully | `etl-test.yml` | Runs the `Import_Fabulous_One_Data` notebook in the Test workspace |
| Push to `main` branch (changes in `data/fabric/**`) | `deploy-prod.yml` | Runs the 3-job sandwich deploying to the Prod workspace |
| `deploy-prod.yml` completes successfully | `etl-prod.yml` | Runs the `Import_Fabulous_One_Data` notebook in the Prod workspace |

### The Sandwich Pattern (3 Jobs)

Each deploy workflow orchestrates three sequential jobs via `needs:`:

1. **deploy-supported** — fabric-cicd publishes all supported items (Lakehouse, Variable Library, Notebooks, Semantic Model, Report) from Git to the target workspace. Item types are explicitly scoped via `item_type_in_scope` to ensure correct deployment ordering (Lakehouse before Variable Library and Semantic Model).
2. **promote-unsupported** *(skeleton)* — Will promote unsupported items (e.g., Ontologies) from the previous stage via the Fabric Deployment Pipelines REST API. Currently prints a TODO message.
3. **deploy-supported-dependent** *(skeleton)* — Will deploy supported items that depend on unsupported items via fabric-cicd. Currently prints a TODO message.

The ETL workflow only triggers after **all 3 jobs** complete successfully. If any job fails, the entire deploy workflow is marked as failed and ETL does not run.

### Future Simplification

When Ontologies (and other unsupported items) gain Git integration and fabric-cicd support, the skeleton jobs can be removed — simplifying the flow to a single fabric-cicd deploy followed by ETL.

---

## GitHub Actions Workflows

### Reusable Templates (called via `workflow_call`)

| Template | Purpose |
|---|---|
| `reusable-deploy-supported.yml` | Ensures Lakehouses exist in the target workspace via the Fabric REST API (first-deploy workaround), then uses fabric-cicd to `publish_all_items()` and `unpublish_all_orphan_items()`. Accepts `environment`, `repository_directory`, and optional `item_type_in_scope` inputs. |
| `reusable-deploy-unsupported.yml` | **SKELETON** — Placeholder for Deployment Pipeline promotion. Prints a TODO message. |
| `reusable-deploy-supported-dependent-on-unsupported.yml` | **SKELETON** — Placeholder for deploying dependent supported items. Prints a TODO message. |
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

Notebooks call `notebookutils.variableLibrary.getLibrary("Fabulous_One_Variables")` at execution time to resolve workspace IDs, lakehouse names, and other values. The Variable Library has **value sets** per environment:

| Variable | Default (Dev) | Test | Prod |
|---|---|---|---|
| `target_workspace_id` | Dev workspace ID | Test workspace ID | Prod workspace ID |
| `target_workspace_name` | `fabulous-one-dev` | `fabulous-one-test` | `fabulous-one-prod` |
| `target_lakehouse_name` | `FabulousLakehouse` | *(default)* | *(default)* |
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
          _ALL_: "$items.Lakehouse.FabulousLakehouse.$id"  # Resolved at deploy time
      item_type: "VariableLibrary"
```

**How it works:** fabric-cicd deploys items in dependency order — the Lakehouse is created before the Variable Library. When processing Variable Library files, `$items.Lakehouse.FabulousLakehouse.$id` resolves to the actual lakehouse GUID in the target workspace. The `_ALL_` key means this applies to every environment.

---

## Prerequisites & Setup

### 1. Fabric Capacity

A Fabric or Power BI Premium capacity is required for all workspaces.

### 2. Fabric Workspaces

Three workspaces are needed:
- **fabulous-one-dev** — connected to the `dev` branch via Fabric Git integration
- **fabulous-one-test** — not Git-connected, receives deployments via fabric-cicd
- **fabulous-one-prod** — not Git-connected, receives deployments via fabric-cicd

### 3. Service Principal

Create a Service Principal for CI/CD automation:

```bash
az ad sp create-for-rbac --name "SPN-Fabulous-One-CICD" \
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

## Gotchas & Key Decisions

### Chicken-and-Egg: Lakehouse ID

The Variable Library and Semantic Model need the lakehouse ID for each environment, but the lakehouse doesn't exist in Test/Prod until the first deployment creates it. fabric-cicd's `$items` dynamic variables (e.g., `$items.Lakehouse.FabulousLakehouse.$id`) resolve by querying the **live target workspace** during parameterization — before items are published. On the first deployment to an empty workspace, this query returns nothing and parameterization fails.

**Solution:** The `reusable-deploy-supported.yml` workflow uses a **two-phase deployment** approach. Phase 1 calls `publish_all_items()` with `item_type_in_scope=["Lakehouse"]` to create the Lakehouse first via fabric-cicd (using the full definition files from the repo). Phase 2 calls `publish_all_items()` with the remaining item types. By the time Phase 2 runs, the Lakehouse exists in the target workspace and `$items.Lakehouse.FabulousLakehouse.$id` resolves correctly. On subsequent deployments, Phase 1 simply updates the existing Lakehouse (idempotent).

### Item Type Scoping

When `item_type_in_scope` is omitted, fabric-cicd attempts to deploy all item types and may count non-item files (e.g., Report theme resources) as separate items, leading to incorrect item counts.

**Solution:** Explicitly set `item_type_in_scope` in the deploy workflows: `["Lakehouse", "VariableLibrary", "Notebook", "SemanticModel", "Report"]`. This ensures only valid item types are deployed.

### Chicken-and-Egg: ETL Notebook ID

The ETL workflow needs to run a notebook, but the notebook ID differs per workspace and isn't known until after deployment.

**Solution:** The ETL workflow resolves the notebook by **display name** at runtime via the [Fabric List Items API](https://learn.microsoft.com/en-us/rest/api/fabric/core/items/list-items), not by ID. The notebook name (`Import_Fabulous_One_Data`) is consistent across environments because it comes from the Git repo.

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

- [Best Practices with Fabric CI/CD Overview](best-practices-with-fabric-cicd-overview.md) — Full strategy document with release option comparison and hybrid recommendation
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
