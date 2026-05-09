# Bulk CI/CD Implementation Guide

This repository implements a parallel deployment path for Microsoft Fabric using the **[Bulk Import Item Definitions API](https://learn.microsoft.com/en-us/rest/api/fabric/core/items/bulk-import-item-definitions(beta))** (Preview), as an alternative to the [fabric-cicd path](fabric-hybrid-cicd-guide.md). It demonstrates how to deploy the same Fabric workspace items (Notebooks, Lakehouses, Variable Libraries, Semantic Models, Reports, Ontologies, Data Agents) across environments using GitHub Actions and the Fabric REST API directly.

For the strategic comparison between fabric-cicd and the Bulk APIs (and the recommendation), see [fabric-cicd-release-options.md](fabric-cicd-release-options.md#tooling-within-option-3-fabric-cicd-vs-bulk-apis).

> **Important framing.** The Bulk Import API itself has known gaps (no parameterization, no value-set activation, no delete). This repo implements caller-side workarounds for the first two so the demo works end-to-end — they are not platform fixes. If you choose the bulk path in your own project you take on the same caller-side work. fabric-cicd remains the recommended production path; this guide exists so the bulk pattern is documented as a worked example, not an endorsement.

---

## Table of Contents

- [Architecture Overview](#architecture-overview)
- [Repository Structure](#repository-structure)
- [Deployment Flow](#deployment-flow)
- [GitHub Actions Workflows](#github-actions-workflows)
- [Configuration Strategy](#configuration-strategy)
- [The Two-Deploy Decision](#the-two-deploy-decision)
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
│       └─ scripts/deploy_bulk.py                     │
│          (Phase 1: POST dependencies                │
│           — Lakehouse + Ontology)                   │
│          (Phase 2: substitute IDs,                  │
│           POST remaining items)                     │
│          (Post-deploy: PATCH VariableLibrary        │
│           active value set)                         │
└─────────────────────────────────────────────────────┘
                     │ workflow_run (on success)
                     ▼
┌─────────────────────────────────────────────────────┐
│  etl-test.yml                                       │
│    └─ reusable-fabric-etl.yml                       │
│       └─ Fabric REST API: run notebook by name      │
└─────────────────────────────────────────────────────┘
```

The same pattern applies to Prod (`deploy-prod-bulk.yml` → `etl-prod.yml`), triggered on push to `main`.

The shape mirrors the [fabric-cicd path](fabric-hybrid-cicd-guide.md#architecture-overview) deliberately. Both paths split the deploy into two phases for the same reason — the first phase creates items whose IDs the second phase needs to reference. The differences are mechanical:

| Concept | fabric-cicd | bulk |
|---|---|---|
| Calls per phase | One library call (`publish_all_items()`) per phase, which makes many per-item REST calls internally | One bulk POST per phase carrying the full batch |
| Substitution | fabric-cicd library applies `parameter.yml` rules transparently | `scripts/deploy_bulk.py` reads `bulk-parameter.yml` and rewrites payloads between phases |
| Value-set activation | Library handles automatically when `environment` is passed | Caller makes a separate `PATCH /variableLibraries/{id}` call |
| Orphan cleanup | `unpublish_all_orphan_items()` built in | Not implemented |

> An alternative fabric-cicd deploy path exists alongside this bulk path; both are gated by the `DEPLOY_METHOD` repo variable. fabric-cicd is the recommended path — see [fabric-cicd vs Bulk APIs](fabric-cicd-release-options.md#tooling-within-option-3-fabric-cicd-vs-bulk-apis) for the comparison and [fabric-hybrid-cicd-guide.md](fabric-hybrid-cicd-guide.md) for its implementation guide.

### Branches & Workspaces

| Branch | Workspace | Deployment Method |
|---|---|---|
| `dev` | Dev (microsoft-fabric-sdlc-patterns-dev) | Git-connected via Fabric Git integration |
| `test` | Test (microsoft-fabric-sdlc-patterns-test) | Bulk Import API via GitHub Actions |
| `main` | Prod (microsoft-fabric-sdlc-patterns-prod) | Bulk Import API via GitHub Actions |

- **Dev** workspace is the only Git-connected workspace. Developers branch out from Dev for isolated feature work.
- **Test** and **Prod** workspaces are NOT Git-connected. With the bulk path active, they receive deployments through `scripts/deploy_bulk.py`.

---

## Repository Structure

```
microsoft-fabric-sdlc-patterns/
├── .github/
│   └── workflows/
│       ├── deploy-test-bulk.yml             # Orchestrator: push to test → bulk deploy
│       ├── deploy-prod-bulk.yml             # Orchestrator: push to main → bulk deploy
│       ├── etl-test.yml                     # Triggers after either deploy-test* succeeds
│       ├── etl-prod.yml                     # Triggers after either deploy-prod* succeeds
│       ├── reusable-deploy-bulk.yml         # Template: Bulk Import API deployment
│       ├── reusable-fabric-etl.yml          # Template: run Notebook via Fabric REST API
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
│       ├── Patterns_Patients_Data.Notebook/
│       ├── Patterns_Demo.Notebook/
│       ├── Patterns_Semantic_Model.SemanticModel/
│       ├── Patterns_Report.Report/
│       └── Patterns_Data_Agent.DataAgent/
├── scripts/
│   ├── deploy_bulk.py                       # Bulk Import API deploy (invoked by reusable-deploy-bulk.yml)
│   ├── deploy_fabric_cicd.py                # fabric-cicd deploy (alternative path)
│   ├── run_fabric_etl.py                    # Run a Fabric Notebook job (invoked by reusable-fabric-etl.yml)
│   └── workspace_swap.py                    # Bootstrap/reset feature branch workspace bindings
├── tests/
│   └── test_deploy_bulk.py                  # Unit tests for the bulk script
└── ... (other docs, see README)
```

The fabric-cicd workflows (`deploy-test.yml`, `deploy-prod.yml`, `reusable-deploy-fabric-cicd.yml`) coexist with the bulk workflows in the same `.github/workflows/` directory. The `DEPLOY_METHOD` repository variable selects which one runs.

---

## Deployment Flow

### What Triggers What

| Event | Workflow Triggered | What It Does |
|---|---|---|
| Push to `test` branch (changes in `data/fabric/**`) when `DEPLOY_METHOD=bulk` | `deploy-test-bulk.yml` | Deploys all items to the Test workspace via the Bulk Import API |
| `deploy-test-bulk.yml` completes successfully | `etl-test.yml` | Runs the `Import_Patterns_Data` notebook in the Test workspace |
| Push to `main` branch (changes in `data/fabric/**`) when `DEPLOY_METHOD=bulk` | `deploy-prod-bulk.yml` | Deploys all items to the Prod workspace via the Bulk Import API |
| `deploy-prod-bulk.yml` completes successfully | `etl-prod.yml` | Runs the `Import_Patterns_Data` notebook in the Prod workspace |

The `DEPLOY_METHOD` repository variable (Settings → Secrets and variables → Actions → Variables) controls which deploy workflow runs:

| `DEPLOY_METHOD` value | Behavior |
|---|---|
| `fabric-cicd` *(or unset)* | fabric-cicd workflows run; bulk workflows skip |
| `bulk` | Bulk workflows run; fabric-cicd workflows skip |
| any other value | Both deploy workflows skip (safe default) |

### The Bulk Deploy Job

Each deploy workflow calls `reusable-deploy-bulk.yml`, which invokes `scripts/deploy_bulk.py`. The script:

1. Acquires an Entra ID bearer token using the SPN's client credentials.
2. Walks `data/fabric/` and builds a `definitionParts[]` array — one entry per file, with the path and base64-encoded content.
3. Loads `bulk-parameter.yml` to get the substitution rules and value-set activation config.
4. Decides single-deploy vs. two-deploy based on whether any rule references `$items.<Type>.<Name>.$id`.
5. POSTs to `https://api.fabric.microsoft.com/v1/workspaces/{ws}/items/bulkImportDefinitions?beta=true` (one or two times depending on the decision).
6. PATCHes the deployed VariableLibrary to set the active value set.

The Bulk Import API can return `200 OK` with the result body inline, or `202 Accepted` with a Long-Running Operation (LRO). The script handles both transparently — see [Gotchas](#lro-polling).

The ETL workflow triggers automatically after the deploy workflow completes successfully. If the deploy fails, ETL does not run.

---

## GitHub Actions Workflows

### Reusable Templates (called via `workflow_call`)

| Template | Purpose |
|---|---|
| `reusable-deploy-bulk.yml` | Acquires a token (via the SPN secrets), checks out the repo, installs `requests` + `PyYAML`, and invokes `scripts/deploy_bulk.py` with the workspace ID, repository directory, and target environment as env vars. |
| `reusable-fabric-etl.yml` | Resolves a Fabric item by **name** (not ID) via the List Items API, then starts a job (RunNotebook) and polls until completion. Shared with the fabric-cicd path — same template, no changes needed. |

### Why Reusable Workflows (Not Composite Actions)

Reusable workflows support the `environment:` keyword at the job level, which enables:

- **GitHub Environment protection rules** (required reviewers, branch restrictions on Prod)
- **Environment-scoped secrets** (each environment has its own `FABRIC_WORKSPACE_ID`)
- `secrets: inherit` forwards all environment secrets without enumeration

### Manual Re-runs via `workflow_dispatch`

`etl-test.yml` and `etl-prod.yml` both support `workflow_dispatch` so an operator can manually re-trigger the ETL job from the Actions UI without a new deploy. This was added to work around a `workflow_run` quirk: re-running a `workflow_run`-triggered run uses the workflow file frozen at the original trigger time, not the current default branch. For ad-hoc recovery from transient failures or workflow-file fixes that just landed on `main`, the manual dispatch is the path of least friction.

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

\* The `target_lakehouse_id` uses the Dev GUID as a placeholder in the value set files. At deploy time, `bulk-parameter.yml` rewrites it with the actual lakehouse ID in the target workspace (see below).

### 2. `bulk-parameter.yml` (Deploy-time)

This is the bulk path's equivalent of fabric-cicd's `parameter.yml`. The format is intentionally distinct — bulk implements a narrow subset of fabric-cicd's DSL, only what this repo's deploys need.

The shipped file at `data/fabric/bulk-parameter.yml` looks like this:

```yaml
substitutions:
  - find: "c185283c-9dd9-4e40-a17c-aa6303e3a2e9"            # dev lakehouse ID
    replace_with: "$items.Lakehouse.PatternsLakehouse.$id"
    item_types: [VariableLibrary, SemanticModel, Notebook]

  - find: "d7270f11-feba-4990-baa6-d45e47f23737"            # dev workspace ID
    replace_with: "$workspace.$id"
    item_types: [SemanticModel, Notebook]

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
| `$items.<Type>.<Name>.$id` | The deployed item ID for `<Type>/<Name>`. Resolved from Phase 1's bulk POST response. |
| `$environment` | The value of the `ENVIRONMENT` env var passed to the deploy step (`Test` or `Prod`). |

**`item_types` filter:** A rule only fires for files whose item type is in the rule's `item_types` list. The script extracts the item type from the path convention `<DisplayName>.<Type>/<file>`. Files outside the listed types pass through unchanged.

**Why a separate file from `parameter.yml`:** The two formats coexist deliberately. fabric-cicd uses `parameter.yml`; bulk uses `bulk-parameter.yml`. Keeping them separate means bulk doesn't have to silently ignore (or break on) fabric-cicd-only features (`key_value_replace`, `spark_pool`, `semantic_model_binding`). Both files live at the root of `data/fabric/` and both are excluded from the bulk request payload by `scripts/deploy_bulk.py`.

### 3. VariableLibrary Value-Set Activation (Post-deploy)

The Bulk Import API uploads the VariableLibrary's value-set files but does NOT set which one is active in the deployed workspace. fabric-cicd makes that selection automatically via its `environment` parameter; with the bulk API, the caller must do it.

`scripts/deploy_bulk.py` makes the call after the bulk POSTs complete:

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

## The Two-Deploy Decision

The bulk script auto-decides between a single-deploy and two-deploy flow based on what's in `bulk-parameter.yml`. The decision is deterministic:

```python
needs_two_deploy = any("$items." in r.replace_with for r in config.substitutions)
```

If any substitution rule references `$items.<Type>.<Name>.$id`, the deploy must split in two — the script needs the item IDs from Phase 1's response before it can substitute them into Phase 2's payloads.

### Single-deploy flow (no `$items.*` references, or no config at all)

```
1. apply_substitutions(parts, rules, workspace_id, item_id_map={})
2. POST all items at once
3. PATCH VariableLibrary if value-set activation is configured
```

`$workspace.$id`-only rules are applied in this flow because the workspace ID is known up front from the env var.

### Two-deploy flow (rules reference `$items.*`)

```
1. partition_dependencies(parts) → (deps, remaining)
2. POST deps                                  ┐
3. extract_item_ids(deps_response)            │  Phase 1
   → item_id_map = {(Type, Name): item_id}   ┘
4. apply_substitutions(remaining, rules,      ┐
                       workspace_id,          │
                       item_id_map)           │  Phase 2
5. POST remaining                             ┘
6. PATCH VariableLibrary if value-set activation is configured
```

`DEPENDENCY_TYPES` in `scripts/deploy_bulk.py` defines what counts as a dependency. The list is intentionally narrow — only types actually referenced by `$items.<Type>.*` in `bulk-parameter.yml` belong here. For this repo, that's `("Lakehouse", "Ontology")`.

This mirrors the fabric-cicd path's two-phase deploy — see the [hybrid guide's chicken-and-egg gotcha](fabric-hybrid-cicd-guide.md#chicken-and-egg-lakehouse-id) for the same problem framed for fabric-cicd.

### When the script fails fast

The script raises a clear error in two situations:

- **Substitution rules reference `$items.<Type>.<Name>.$id`, but no items of dependency types are found in the repo.** The deploy can't satisfy the placeholder.
- **A rule references an item the script can't find by `(Type, Name)`.** The placeholder won't resolve. Common cause: typo in `bulk-parameter.yml`.

Both cases stop the deploy before any items are POSTed.

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

### 6. Set the `DEPLOY_METHOD` Repository Variable

To activate the bulk path, set `DEPLOY_METHOD=bulk` in Settings → Secrets and variables → Actions → Variables. Without this, the bulk workflows skip and fabric-cicd runs instead.

---

## Initial Deployment to a Clean Workspace

When deploying to a workspace for the first time, follow these steps in order. Subsequent deployments are fully automated — only the first deployment requires manual intervention.

### Step 1: Trigger the Deployment

Push to the target branch (`test` or `main`). The bulk deploy workflow triggers automatically and executes:

- **Phase 1 (if needed):** POST Lakehouse + Ontology
- **Phase 2:** Substitute IDs from Phase 1's response into the remaining items, then POST them
- **Post-deploy:** PATCH the VariableLibrary to set the active value set for the environment

### Step 2: ETL Populates the Lakehouse

The ETL workflow (`etl-test.yml` or `etl-prod.yml`) triggers automatically after a successful deployment. It runs the `Import_Patterns_Data` notebook, which creates and populates the Delta tables (`doctors`, `patients`, `appointments`) in the Lakehouse.

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
- **Semantic Model** — connected to the lakehouse (may require manual connection config on first deploy)
- **Report** — renders with data from the Semantic Model
- **Data Agent** — references the Ontology and responds to queries

> **Note:** Steps 3–4 (Ontology activation) are platform behaviors, not bulk-specific. The fabric-cicd path requires the same manual steps on first deploy.

---

## Gotchas & Key Decisions

### Two-Deploy Chicken-and-Egg

The Variable Library, Semantic Model, and notebooks reference the lakehouse ID for each environment, but the lakehouse doesn't exist in Test/Prod until the first deployment creates it. With the bulk API, there's no library-side resolution of these references — the script must POST the dependency items first, read their IDs from the response, then substitute into the remaining items before the second POST.

**Solution:** [The two-deploy decision](#the-two-deploy-decision). Phase 1 POSTs the dependencies (`DEPENDENCY_TYPES`), the script reads their IDs from the response, then Phase 2 substitutes and POSTs the rest.

### Per-Request Service Principal Coverage

The Bulk Import API requires that **every** item type in the request payload supports service principals. If even one type doesn't, the entire request fails with an authorization error — there's no graceful degradation.

fabric-cicd, by contrast, fails per item — an unsupported item type fails only that item, and the rest of the deploy continues.

**Solution:** Verify SPN coverage for every item type in your repo before adopting the bulk path. As of Phase 2, all 7 types in this repo (Lakehouse, Ontology, VariableLibrary, Notebook, SemanticModel, Report, DataAgent) support SPNs and the deploy works end-to-end. If a future Fabric item type doesn't support SPNs, the bulk path won't be usable until coverage is added.

### LRO Polling

The Bulk Import API can return either:

- **`200 OK`** with the full result body (`importItemDefinitionsDetails[]`) inline — synchronous case
- **`202 Accepted`** with an `x-ms-operation-id` header and a `Retry-After` header — asynchronous, caller polls a Long-Running Operation

`scripts/deploy_bulk.py` handles both transparently. For the LRO case, it polls `GET /v1/operations/{id}` until the operation reaches `Succeeded`, `Failed`, or `Undefined`, then fetches `GET /v1/operations/{id}/result` for the same `importItemDefinitionsDetails[]` shape the sync case returns inline.

### Retry-After Clamping

The script clamps the `Retry-After` header to `[5s, 600s]` and falls back to 30s on missing or unparseable values. Without the upper bound, a pathological `Retry-After` could cause a single sleep longer than the global polling timeout (20 minutes), making the timeout meaningless. Without the input validation, a non-integer value would crash the script with an unhandled `ValueError`.

### Bearer Token Is Not Echoed to Logs

An earlier version of the script emitted `::add-mask::<token>` to register a workflow log mask. That line itself emitted the token to stdout in cleartext, defeating the mask's purpose (the runner only redacts subsequent output). The current script never prints the token. The SPN secret is masked by GitHub automatically because it comes from `secrets.AZURE_CLIENT_SECRET`.

### `bulk-parameter.yml` Is Excluded from the Request Payload

The script lists `bulk-parameter.yml`, `parameter.yml`, and `.gitkeep` in `EXCLUDED_FILES` so they're never sent to Fabric as part of the bulk request. The structural rule "files at the root of `repository_directory` are not item definitions" already excludes them, but the explicit list documents intent.

### `workflow_run` Quirk: Re-runs Use the Frozen Workflow File

Re-running a `workflow_run`-triggered ETL run uses the workflow file frozen at the time the trigger fired, not the current default branch. If a workflow-file fix lands on `main` after the trigger fires, neither the auto-retry nor `gh run rerun` picks it up. To recover from a transient failure or a workflow-file fix, use the `workflow_dispatch` manual trigger added to `etl-test.yml` and `etl-prod.yml`.

### `?beta=true` Required Today

The bulk endpoint URL is currently `POST /v1/workspaces/{ws}/items/bulkImportDefinitions?beta=true`. When the API graduates from Preview, drop the query parameter. The TODO is noted in the script's module docstring and in `reusable-deploy-bulk.yml`.

### Microsoft Tutorial's URL Is Wrong

The Microsoft Learn [Bulk Import tutorial](https://learn.microsoft.com/en-us/fabric/cicd/tutorial-bulkapi-cicd) uses `/importItemDefinitions` (singular) — that endpoint produces `404`. The correct path is `/items/bulkImportDefinitions` per the [API reference page](https://learn.microsoft.com/en-us/rest/api/fabric/core/items/bulk-import-item-definitions(beta)). Verified against a live workspace.

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

If the new rule references `$items.<Type>.<Name>.$id` for a new item type, also extend `DEPENDENCY_TYPES` in `scripts/deploy_bulk.py` so that type deploys in Phase 1.

### Adding a new placeholder type

To add e.g. `$secrets.<name>` resolving to a CI secret, modify `scripts/deploy_bulk.py`:

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

That's the only code change. Phase 1 will start including the new type; Phase 2 substitutions will resolve its IDs.

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
- [fabric-hybrid-cicd-guide.md](fabric-hybrid-cicd-guide.md) — Implementation guide for the fabric-cicd path
- [fabric-cicd-governance-considerations.md](fabric-cicd-governance-considerations.md) — Identity, RBAC, branch protection, approval gates
- [Fabric Bulk Import Item Definitions API (Preview)](https://learn.microsoft.com/en-us/rest/api/fabric/core/items/bulk-import-item-definitions(beta)) — Endpoint reference
- [Fabric Long-Running Operations](https://learn.microsoft.com/en-us/rest/api/fabric/articles/long-running-operation) — `?async=true` semantics, polling pattern
- [Fabric Update Variable Library](https://learn.microsoft.com/en-us/rest/api/fabric/variablelibrary/items/update-variable-library) — PATCH endpoint used by value-set activation
- [Microsoft Bulk Import tutorial](https://learn.microsoft.com/en-us/fabric/cicd/tutorial-bulkapi-cicd) — Microsoft's walkthrough (note the URL discrepancy called out under [Gotchas](#microsofts-tutorial-url-is-wrong))
- [Fabric Create Item API — Permissions](https://learn.microsoft.com/en-us/rest/api/fabric/core/items/create-item) — Contributor role requirement
- [GitHub Reusable Workflows](https://docs.github.com/en/actions/sharing-automations/reusing-workflows) — `workflow_call`, inputs, secrets
