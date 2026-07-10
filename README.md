# Microsoft Fabric SDLC Patterns

A reference implementation and solution accelerator for the developer workflow and CI/CD pipeline in Microsoft Fabric, demonstrating how to choose a release strategy, implement deployments, work day-to-day on feature branches, and govern the pipeline for dev, test, and production using GitHub Actions and the [fabric-cicd](https://microsoft.github.io/fabric-cicd) Python library. Both the developer workflow and the deployment pipeline are fully implemented end-to-end so the repo runs as a complete reference, not isolated examples.

*Based on field experience with Microsoft Fabric customers and partners. Opinions expressed here are my own and do not represent Microsoft's official guidance.*

---

## Who is this for?

Engineers and platform teams responsible for getting Microsoft Fabric workloads from a developer's laptop to production safely and repeatably — covering the developer workflow, the deployment pipeline itself, and the governance layered on top.

Architects and decision-makers evaluating Fabric will also find the [CI/CD Release Options](fabric-cicd-release-options.md) and [Governance Considerations](fabric-cicd-governance-considerations.md) useful for understanding the operating model before committing.

---

## Architecture

```
Feature branch (feature/*)
  │
  │  PR → dev branch
  ▼
Git repo (dev branch)
  │
  │  PR merge → test branch (source must be dev)
  ▼
┌──────────────────────────────────────────────┐
│  deploy-test.yml                             │
│    └─ fabric-cicd: publish_all_items()       │
│                    ↓ on success               │
│  etl-test.yml                                │
│    └─ Fabric REST API: run notebook          │
└──────────────────────────────────────────────┘
  │
  │  PR merge → main branch (source must be test)
  ▼
┌──────────────────────────────────────────────┐
│  deploy-prod.yml                             │
│    └─ fabric-cicd: publish_all_items()       │
│                    ↓ on success               │
│  etl-prod.yml                                │
│    └─ Fabric REST API: run notebook          │
└──────────────────────────────────────────────┘
```

Branch protection (PR required, source-branch restrictions, status checks) is enforced by GitHub branch rulesets and the [enforce-promotion-path.yml](.github/workflows/enforce-promotion-path.yml) workflow — see the [Governance Considerations](fabric-cicd-governance-considerations.md).

![Hybrid Recommendation Flow](assets/hybrid-recommendation-flow.svg)

> This repository demonstrates fabric-cicd (the default, recommended GA Python library) alongside a parallel set of Bulk Import / Export API workflows (Preview) for evaluation and side-by-side comparison. Selection is controlled by the `DEPLOY_METHOD` repository variable — see [Quick Start](#quick-start) for all methods and how to switch, and [CI/CD Release Options](fabric-cicd-release-options.md#tooling-within-option-3-fabric-cicd-vs-bulk-apis) for the full comparison.

---

## Documentation

| Document | Description |
|---|---|
| [CI/CD Release Options](fabric-cicd-release-options.md) | Evaluates all CI/CD release options for Fabric (Deployment Pipelines, Git-based, Build-based, Hybrid) and recommends the Hybrid approach. Includes a [comparison of fabric-cicd vs the new Bulk Import / Export APIs](fabric-cicd-release-options.md#tooling-within-option-3-fabric-cicd-vs-bulk-apis) (Preview) within Option 3. **Start here** if you're deciding on a strategy. |
| [Hybrid CI/CD Implementation Guide](fabric-hybrid-cicd-guide.md) | Deep dive into the recommended fabric-cicd implementation: workflow structure, configuration strategy, prerequisites, setup steps, and gotchas. |
| [Bulk CI/CD Implementation Guide](fabric-bulk-cicd-guide.md) | Implementation guide for the alternative Bulk Import API (Preview) deploy path. Covers the gap-bridging workarounds (substitution, value-set activation), the two-deploy decision, extension patterns, and limitations not bridged. |
| [Development Process](fabric-development-process.md) | How developers work day-to-day: branch-out workflow, the workspace swap script, and PR readiness check. |
| [CI/CD Governance Considerations](fabric-cicd-governance-considerations.md) | Considerations on identities, RBAC, branch protection, and approval gates for the CI/CD pipeline. Includes pointers to adjacent controls owned outside the pipeline (security/compliance topics). |

---

## Key Concepts

Before choosing a CI/CD approach or development workflow, understand these two realities about Fabric items.

### Item Tracking Categories

Not all Fabric items can be managed the same way. From a lifecycle management perspective, items fall into three categories:

| Category | Description | Examples |
|---|---|---|
| **Git-tracked** | Items supported by [Fabric Git integration](https://learn.microsoft.com/en-us/fabric/cicd/git-integration/intro-to-git-integration#supported-items). Their definitions are serialized to files in the repo, enabling version control, branching, and code-review workflows. | Notebooks, Semantic Models, Lakehouses, Reports, Variable Libraries, Data Pipelines, Environments |
| **Deployment Pipeline–only** | Items not supported by Git integration or fabric-cicd but supported by [Fabric Deployment Pipelines](https://learn.microsoft.com/en-us/fabric/cicd/deployment-pipelines/intro-to-deployment-pipelines#supported-items). They can be promoted workspace-to-workspace but cannot be version-controlled in Git. | Check the official supported items lists — this category changes as Microsoft adds capabilities |
| **Manual** | Items supported by neither Git integration nor Deployment Pipelines. These must be created and configured manually in each workspace. | Varies as Microsoft continues adding support — always check the official supported items lists |

> **Important:** Both supported items lists evolve as Microsoft adds capabilities. Always verify against the official documentation before assuming an item falls into a particular category.

This categorization directly impacts your CI/CD strategy. The [Hybrid CI/CD Implementation Guide](fabric-hybrid-cicd-guide.md) describes how to handle the gap between git-tracked and deployment-pipeline-only items if your workspace includes unsupported types. Currently, all items in this repository are deployed via fabric-cicd.

### Variable Libraries: Dynamic vs Static Metadata

Some Fabric items resolve environment-specific values **at runtime** through [Variable Libraries](https://learn.microsoft.com/en-us/fabric/cicd/variable-library/variable-library-cicd), while others have environment-specific IDs **hardcoded in their definitions**.

| Type | How it works | Examples |
|---|---|---|
| **Dynamic (Variable Library)** | The item reads IDs from the Variable Library at runtime. Changing the active value set automatically switches the environment context — no file changes needed. | Notebooks using `notebookutils.variableLibrary.getLibrary()` |
| **Static (hardcoded)** | The item definition contains literal workspace/lakehouse GUIDs that must be rewritten per environment — either at deploy time (via `parameter.yml`) or via script (`workspace_swap.py`). | Semantic Model Direct Lake URL (`expressions.tmdl`), Notebook META dependency blocks (`default_lakehouse`, `default_lakehouse_workspace_id`) |

When designing your development and CI/CD processes, identify which items in your workspace are dynamic vs static. Static items need either deploy-time parameterization (`parameter.yml` for CI/CD) or script-based rewriting (`workspace_swap.py` for feature branches). The [Development Process](fabric-development-process.md) doc covers how this repo handles both.

---

## Quick Start

### Prerequisites

1. **Fabric Capacity** — A Fabric or Power BI Premium capacity for all workspaces
2. **Three Fabric Workspaces** — Dev (Git-connected), Test, and Prod
3. **Service Principal** — With Contributor role on Test and Prod workspaces
4. **GitHub Environments** — `Test` and `Prod` with environment-scoped secrets
5. **Fabric Admin Setting** — Service principal access to Fabric APIs enabled in the Fabric Admin portal under Developer settings (see [developer tenant settings](https://learn.microsoft.com/en-us/fabric/admin/service-admin-portal-developer))

### Setup

1. Create a Service Principal and add it as Contributor on Test and Prod workspaces
2. Create GitHub Environments (`Test`, `Prod`) with secrets: `AZURE_TENANT_ID`, `AZURE_CLIENT_ID`, `AZURE_CLIENT_SECRET`, `FABRIC_WORKSPACE_ID` *(this demo uses a client secret for simplicity; for production, evaluate [GitHub OIDC federation](fabric-cicd-governance-considerations.md#identity-model--pick-the-right-identity-for-the-job) to remove the stored secret)*
3. Connect the Dev workspace to the `dev` branch via Fabric Git integration (folder: `data/fabric/`)
4. Create `dev`, `test`, and `main` branches
5. Develop on `dev`, merge to `test` (triggers Test deploy), merge to `main` (triggers Prod deploy)

### Selecting the deployment method

This repo ships three deploy methods. Set the `DEPLOY_METHOD` repository variable (Settings → Secrets and variables → Actions → Variables) to choose which one runs:

| `DEPLOY_METHOD` value | Behavior |
|---|---|
| `fabric-cicd` *(or unset)* | Existing fabric-cicd workflows run — the default and recommended path |
| `fabric-cicd-bulk` | fabric-cicd workflows run with bulk publish enabled. For this repo it always falls back to standard per-item publish, because `parameter.yml` uses `$items`/`$workspace` variables — included to demonstrate the library's experimental bulk mode |
| `bulk` | Bulk Import API workflows run instead (Preview) |
| any other value | All deploy workflows skip (safe default) |

Whichever method runs, the ETL workflow chains afterward via `workflow_run`. See [CI/CD Release Options](fabric-cicd-release-options.md#tooling-within-option-3-fabric-cicd-vs-bulk-apis) for the trade-offs between fabric-cicd and the Bulk APIs.

For detailed setup instructions, see the [Implementation Guide](fabric-hybrid-cicd-guide.md#prerequisites--setup). For branch-protection rulesets, deploy-time approvals, and the source-branch promotion path enforced in this repo, see the [Governance Considerations](fabric-cicd-governance-considerations.md).

---

## References

- [fabric-cicd Python Library](https://microsoft.github.io/fabric-cicd) — Docs, getting started, supported item types
- [Fabric Git Integration](https://learn.microsoft.com/en-us/fabric/cicd/git-integration/intro-to-git-integration) — Official documentation
- [GitHub Actions Reusable Workflows](https://docs.github.com/en/actions/sharing-automations/reusing-workflows) — `workflow_call`, inputs, secrets
