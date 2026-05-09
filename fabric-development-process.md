# Development Process

This document describes the two primary approaches for feature branch development in Microsoft Fabric with Git integration, the tradeoffs of each, and how this repository implements the **Branch Out** pattern.

## Scenario Comparison

### Scenario A: Short-Lived Feature Workspaces (Not Git-Synced)

In this scenario, `dev` is the only workspace connected to Git. Feature workspaces are created independently and are **not** git-synced. Code is deployed into them using [fabric-cicd](https://microsoft.github.io/fabric-cicd/latest/).

**How it works:**

1. Developer creates a feature branch in Git from `dev`.
2. A standalone Fabric workspace is created for the feature (not connected to Git).
3. A CI/CD pipeline uses `fabric-cicd` to deploy items from the feature branch into the workspace.
4. `fabric-cicd` handles metadata replacement (workspace IDs, lakehouse IDs) via `parameter.yml` at deploy time.
5. Developer works in the Fabric UI, then commits changes back to the feature branch.
6. PR is opened to merge the feature branch into `dev`.

**Positive:** You can use `fabric-cicd` to update metadata because the target workspace is not git-synced. Deployed workspaces are only updated through script-based deployments — this is the [recommended flow from fabric-cicd](https://microsoft.github.io/fabric-cicd/latest/how_to/getting_started/#git-flow):

> *"Deployed branches are not connected to workspaces via GIT Sync. Feature branches are connected to workspaces via GIT Sync. Deployed workspaces are only updated through script-based deployments."*
> — [fabric-cicd Getting Started: GIT Flow](https://microsoft.github.io/fabric-cicd/latest/how_to/getting_started/#git-flow)

**Issue:** All development happens in the Fabric UI. Syncing changes back to the feature branch is manual and error-prone, especially for items that cannot be fully tracked in Git.

---

### Scenario B: Branch Out (Git-Synced Feature Workspaces)

In this scenario, you use Fabric's [Branch Out](https://learn.microsoft.com/en-us/fabric/cicd/git-integration/manage-branches#scenario-2---branch-out-to-another-workspace) feature. The feature workspace **is** git-synced to the feature branch.

**How it works:**

1. Developer uses the Fabric UI Source Control panel to **Branch out to another workspace**.
2. Fabric creates a new branch and a new workspace, syncing all items automatically.
3. The workspace is connected to the feature branch via Git Sync.
4. Developer works in the workspace, commits changes directly to the feature branch.
5. PR is opened to merge the feature branch into `dev`.

**Positive:** Fabric moves all supported items to the feature workspace automatically. Development and source control are tightly integrated.

**Issue:** You **cannot** use `fabric-cicd` to deploy into a git-synced workspace. `fabric-cicd` pushes changes directly via Fabric APIs, which creates **workspace drift** — the workspace state diverges from what Git expects. When Git Sync next runs, it can overwrite the `fabric-cicd` changes or produce conflicts, destabilizing the workspace.

This is explicitly documented:

> *"Deployed branches are not connected to workspaces via GIT Sync ... Deployed workspaces are only updated through script-based deployments, such as through the fabric-cicd library."*
> — [fabric-cicd Getting Started: GIT Flow](https://microsoft.github.io/fabric-cicd/latest/how_to/getting_started/#git-flow)

The inverse is also true: **git-synced workspaces should not be targets for `fabric-cicd` deployments.**

Additionally, when branching out, only [Git-supported items](https://learn.microsoft.com/en-us/fabric/cicd/git-integration/intro-to-git-integration#supported-items) are available in the new workspace, and certain workspace settings are not copied:

> *"When branching out, a new branch is created and the settings from the original branch aren't copied. Adjust any settings or definitions to ensure that the new meets your organization's policies."*
> — [Basic concepts in Git integration: Branching out limitations](https://learn.microsoft.com/en-us/fabric/cicd/git-integration/git-integration-process#branching-out-limitations)

---

## How This Repository Implements Branch Out

This repository uses **Scenario B (Branch Out)** for feature development. Since `fabric-cicd` cannot be used on git-synced workspaces, a Python script handles the metadata updates that would normally be done by `fabric-cicd` at deploy time.

### The Problem

When you branch out from `dev`, all Fabric items are copied to the feature workspace. However, several items contain **hardcoded dev workspace and lakehouse IDs**:

- **Semantic Model** (`expressions.tmdl`) — Direct Lake connection URL contains dev workspace and lakehouse GUIDs.
- **Notebooks** (`notebook-content.py`) — META dependency blocks reference dev workspace and lakehouse GUIDs.
- **Variable Library** (`variables.json`) — Default value set contains dev IDs (this is expected and not modified).

Without intervention, the feature workspace semantic model points to the dev lakehouse, and notebooks with hardcoded dependencies attach to dev.

### The Solution: `workspace_swap.py`

A Python script at `scripts/workspace_swap.py` handles the full lifecycle of feature branch environment management.

#### Step-by-Step: Swap to Feature Workspace

![Swap to Feature Flow](assets/development-swap-to-feature-flow.svg)

1. **Branch out** from the Fabric UI Source Control panel.
2. **Clone/pull** the feature branch locally:
   ```
   git fetch origin
   git checkout <feature-branch-name>
   ```
3. **Set up `.env`** (one-time per developer): copy `.env.sample` to `.env` at the repo root and paste in your feature workspace and lakehouse GUIDs. The `.env` file is gitignored.
4. **Run the swap-to-feature script** (preview first with `--dry-run`):
   ```
   python scripts/workspace_swap.py --dry-run
   python scripts/workspace_swap.py
   ```
   The script automatically:
   - Detects the current branch name (no arguments needed).
   - Reads dev IDs from `variables.json` (the default value set).
   - Reads feature workspace/lakehouse IDs from `.env`. If `.env` is missing or has empty/missing keys, the script exits with an error pointing at `.env.sample` — there is no interactive fallback.
   - Displays the planned swap and asks `Type YES (uppercase) to apply, anything else to abort.` Type `YES` (case-sensitive) to proceed; the run is dry only when `--dry-run` is also passed.
   - Creates a feature branch value set (e.g., `valueSets/<branch-name>.json`).
   - Adds the value set to `settings.json`.
   - Rewrites the semantic model Direct Lake connection in `expressions.tmdl`.
   - Rewrites notebook META dependency blocks in all `notebook-content.py` files.
   - Sweeps stale feature IDs from a previous swap if `.env` was changed since the last run (recovery pass).
   - Validates no dev IDs remain in critical files.
5. **Commit and push** the changes to the feature branch:
   ```
   git add -A
   git commit -m "Swap to feature workspace for <branch-name>"
   git push
   ```
6. **Sync** the feature workspace from the Fabric UI (Update from Git).
7. **Activate the feature value set** in the Fabric UI: open the Variable Library → select the feature value set → activate it.
8. **Run the import data notebook** to populate the feature lakehouse.

#### Step-by-Step: Swap to Dev Before PR

![Swap to Dev Flow](assets/development-swap-to-dev-flow.svg)

Before merging back to `dev`, all feature-specific changes must be reverted so dev IDs are restored:

1. **Run the swap-to-dev script** (preview first with `--dry-run`):
   ```
   python scripts/workspace_swap.py --swap-to-dev --dry-run
   python scripts/workspace_swap.py --swap-to-dev
   ```
   The script automatically:
   - Reads feature IDs from the branch value set.
   - Reverts the semantic model connection to dev IDs.
   - Reverts notebook META blocks to dev IDs.
   - Deletes the feature value set file.
   - Removes the feature entry from `settings.json`.
   - Validates no feature IDs remain in critical files.
2. **Commit and push**:
   ```
   git add -A
   git commit -m "Swap to dev for merge"
   git push
   ```
3. **Open a PR** to `dev`.

#### PR Validation

A GitHub Actions workflow (`.github/workflows/check-pr-ready.yml`) runs on every PR targeting `dev`. It verifies:

- The semantic model contains dev workspace and lakehouse IDs.
- Notebooks with lakehouse dependencies contain dev IDs.
- No feature branch value set files exist (only `Test.json` and `Prod.json` are allowed).

If any check fails, the PR is blocked until the developer runs `workspace_swap.py --swap-to-dev`.

#### Running the Script with GitHub Copilot Chat

The repo ships slash commands in `.github/prompts/` that wrap the CLI. In Copilot Chat (Agent mode) you can type:

- `/swap-to-feature` — swap repo IDs to your feature workspace
- `/swap-to-feature-dryrun` — preview the swap without writing files
- `/swap-to-dev` — swap IDs back to dev (run before opening a PR)
- `/swap-to-dev-dryrun` — preview the revert without writing files
- `/check-pr-ready` — run the CI-style readiness check locally

Copilot will execute the script in the VS Code integrated terminal and show you the output. The `/swap-to-feature` slash command moves the `YES` confirmation into the chat UI — you click `YES` or `NO` in chat and Copilot pipes the answer to the script so the terminal never blocks. This is useful when you are already working in Copilot Chat and want to stay in the same workflow without switching to the terminal.

Note: Copilot cannot auto-trigger the script on branch checkout. You still need to invoke a slash command or run it yourself after pulling a feature branch.

### Local `.env` Setup

`workspace_swap.py` reads your feature workspace and lakehouse GUIDs from a `.env` file at the repo root. This file is gitignored — each developer maintains their own.

1. Copy `.env.sample` to `.env`.
2. Open the feature workspace in Fabric. Find:
   - **Workspace ID:** Workspace settings → About → Workspace ID.
   - **Lakehouse ID:** open the lakehouse, copy the GUID from the URL (the segment after `/lakehouses/`).
3. Paste both into `.env`.
4. Run `python scripts/workspace_swap.py` (or `/swap-to-feature` in Copilot Chat).

If `.env` is missing, has empty values, or is missing either key, the script exits with a clear error pointing at `.env.sample`. There is no interactive fallback — `.env` is the single source of truth for swap-to-feature.

For swap-to-feature, the script always reads `.env` (the existing value-set file does not override it). The value set on disk is read by swap-to-dev (to know which feature IDs to revert) and by the recovery pass (to detect previously-applied stale IDs that need rewriting). Before any rewrite happens, the script displays the planned dev → feature change and waits for the user to type literal `YES` to confirm.

The script intentionally does **not** auto-discover IDs via the Fabric REST API. An earlier implementation matched workspaces by display name, which could silently pick the wrong workspace (e.g. matching the dev workspace itself), causing the swap to abort with no value set written. Explicit `.env` config avoids that class of bug.

### Scope of Metadata Rewriting

The script uses an **item type registry** to manage which Fabric item types participate in branch environment management. Each registered type declares its file patterns, whether it needs ID rewriting, and which IDs to validate. Adding a new item type requires only a single registry entry — no other code changes are needed.

Not all item types need rewriting. Fabric items fall into two categories based on how they reference environment-specific resources:

- **Actual IDs** (e.g., Semantic Models, Notebooks): These embed real workspace and lakehouse GUIDs that differ per workspace. They must be rewritten when swapping to a feature workspace and reverted before PR.
- **Logical IDs** (e.g., Ontology, Data Agent): These reference other items via the `.platform` `logicalId`, which Fabric resolves at runtime within the current workspace. These are portable across Branch Out workspaces and need no rewriting.

### Item Type Reference

| Item Type | Files | ID Type | `workspace_swap.py` Rewrites? | `parameter.yml` Handles? | Notes |
|-----------|-------|---------|--------------------------|-------------------------|-------|
| **SemanticModel** | `*.SemanticModel/definition/expressions.tmdl` | Actual workspace + lakehouse IDs | Yes | Yes | Direct Lake connection URL contains real GUIDs |
| **Notebook** | `*.Notebook/notebook-content.py` | Actual workspace + lakehouse IDs | Yes (only if `default_lakehouse` present) | Yes | META dependency blocks reference real GUIDs |
| **Ontology** | `*.Ontology/**/DataBindings/*.json`, `*.Ontology/**/Contextualizations/*.json` | Lakehouse logicalId (`b36b3bda-...`) + zeroed workspaceId | No — logicalIds are portable | Yes — logicalId replaced with `$items.Lakehouse...` for CI/CD | Uses `.platform` logicalId, resolved by Fabric at runtime |
| **DataAgent** | `*.DataAgent/**/datasource.json` | Ontology logicalId (`58a6c8ed-...`) + zeroed workspaceId | No — logicalIds are portable | No — references Ontology by logicalId | Cross-item logicalId reference, no environment-specific IDs |
| **VariableLibrary** | `valueSets/*.json`, `settings.json` | Dev lakehouse ID in default value set | Managed (creates/deletes value sets) | Yes — default value set lakehouse ID replaced | Value set files are created/deleted, not rewritten |

### Files Involved

| File | Role |
|------|------|
| `scripts/workspace_swap.py` | Swap workspace IDs in tracked files between dev and feature; CI readiness check |
| `tests/test_workspace_swap.py` | Unit tests for the branch environment script |
| `data/fabric/Patterns_Variables.VariableLibrary/variables.json` | Default (dev) value set — read-only reference for dev IDs |
| `data/fabric/Patterns_Variables.VariableLibrary/valueSets/` | Per-environment value sets (Test, Prod, feature branches) |
| `data/fabric/Patterns_Variables.VariableLibrary/settings.json` | Value set ordering |
| `data/fabric/Patterns_Semantic_Model.SemanticModel/definition/expressions.tmdl` | Direct Lake connection — rewritten by the script |
| `data/fabric/Import_Patterns_Data.Notebook/notebook-content.py` | Notebook with hardcoded lakehouse dependency — rewritten by the script |
| `data/fabric/Patterns_Ontology.Ontology/EntityTypes/*/DataBindings/*.json` | Ontology data bindings — validated (not rewritten) by the script |
| `data/fabric/Patterns_Ontology.Ontology/RelationshipTypes/*/Contextualizations/*.json` | Ontology contextualizations — validated (not rewritten) by the script |
| `data/fabric/Patterns_Data_Agent.DataAgent/Files/Config/draft/ontology-*/datasource.json` | Data Agent datasource — registered but not scanned (no dev IDs) |
| `.github/workflows/check-pr-ready.yml` | PR check to block feature IDs from merging to dev |
| `.github/workflows/run-tests.yml` | Runs unit tests on PRs when scripts or tests change |
| `data/fabric/parameter.yml` | Deploy-time parameterization for fabric-cicd (used in CI/CD, not by `workspace_swap.py`) |

## References

- [fabric-cicd: Getting Started — GIT Flow](https://microsoft.github.io/fabric-cicd/latest/how_to/getting_started/#git-flow)
- [Microsoft Fabric: Manage branches — Branch out to another workspace](https://learn.microsoft.com/en-us/fabric/cicd/git-integration/manage-branches#scenario-2---branch-out-to-another-workspace)
- [Microsoft Fabric: Basic concepts in Git integration — Branching out limitations](https://learn.microsoft.com/en-us/fabric/cicd/git-integration/git-integration-process#branching-out-limitations)
- [Microsoft Fabric: Git integration best practices](https://learn.microsoft.com/en-us/fabric/cicd/best-practices-cicd)
