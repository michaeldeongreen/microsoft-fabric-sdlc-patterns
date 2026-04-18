# Microsoft Fabric SDLC Patterns

A reference implementation for CI/CD in Microsoft Fabric, demonstrating how to version-control, deploy, and manage Fabric workspace items across dev, test, and production environments using GitHub Actions and the [fabric-cicd](https://microsoft.github.io/fabric-cicd) Python library.

---

## Who is this for?

Teams and engineers who need to establish a reliable software development lifecycle (SDLC) for Microsoft Fabric — including automated deployments, environment-specific configuration, and Git-based version control for Fabric items.

---

## Architecture

```
Git repo (dev branch)
  │
  │  PR merge → test branch
  ▼
┌──────────────────────────────────────────────┐
│  deploy-test.yml                             │
│    └─ fabric-cicd: publish_all_items()       │
│                    ↓ on success               │
│  etl-test.yml                                │
│    └─ Fabric REST API: run notebook          │
└──────────────────────────────────────────────┘
  │
  │  PR merge → main branch
  ▼
┌──────────────────────────────────────────────┐
│  deploy-prod.yml                             │
│    └─ fabric-cicd: publish_all_items()       │
│                    ↓ on success               │
│  etl-prod.yml                                │
│    └─ Fabric REST API: run notebook          │
└──────────────────────────────────────────────┘
```

![Hybrid Recommendation Flow](assets/hybrid-recommendation-flow.svg)

---

## Documentation

| Document | Description |
|---|---|
| [Fabric CI/CD Release Options](fabric-cicd-release-options.md) | Evaluates all CI/CD release options for Fabric (Deployment Pipelines, Git-based, Build-based, Hybrid) and recommends the Hybrid approach. **Start here** if you're deciding on a strategy. |
| [Hybrid CI/CD Implementation Guide](hybrid-cicd-implementation-guide.md) | Deep dive into the implementation: workflow structure, sandwich pattern, configuration strategy, prerequisites, setup steps, and gotchas. |

---

## Quick Start

### Prerequisites

1. **Fabric Capacity** — A Fabric or Power BI Premium capacity for all workspaces
2. **Three Fabric Workspaces** — Dev (Git-connected), Test, and Prod
3. **Service Principal** — With Contributor role on Test and Prod workspaces
4. **GitHub Environments** — `Test` and `Prod` with environment-scoped secrets
5. **Fabric Admin Setting** — "Service principals can use Fabric APIs" enabled

### Setup

1. Create a Service Principal and add it as Contributor on Test and Prod workspaces
2. Create GitHub Environments (`Test`, `Prod`) with secrets: `AZURE_TENANT_ID`, `AZURE_CLIENT_ID`, `AZURE_CLIENT_SECRET`, `FABRIC_WORKSPACE_ID`
3. Connect the Dev workspace to the `dev` branch via Fabric Git integration (folder: `data/fabric/`)
4. Create `dev`, `test`, and `main` branches
5. Develop on `dev`, merge to `test` (triggers Test deploy), merge to `main` (triggers Prod deploy)

For detailed setup instructions, see the [Implementation Guide](hybrid-cicd-implementation-guide.md#prerequisites--setup).

---

## References

- [fabric-cicd Python Library](https://microsoft.github.io/fabric-cicd) — Docs, getting started, supported item types
- [Fabric Git Integration](https://learn.microsoft.com/en-us/fabric/cicd/git-integration/intro-to-git-integration) — Official documentation
- [GitHub Actions Reusable Workflows](https://docs.github.com/en/actions/sharing-automations/reusing-workflows) — `workflow_call`, inputs, secrets
