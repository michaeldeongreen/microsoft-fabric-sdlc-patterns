# Set Up This Repository

This guide takes an independent fork from empty workspaces to a working
`dev -> test -> main` promotion flow. It assumes familiarity with Azure and
GitHub, but no prior Microsoft Fabric setup experience.

The steps below use **fabric-cicd non-bulk**, this repository's default route.
[fabric-cicd](https://microsoft.github.io/fabric-cicd) is the Python library
that publishes the items. After the default route works,
use the [four-method comparison](README.md#choose-a-deployment-method) to choose
an alternative. The [shared workflow reference](fabric-hybrid-cicd-guide.md#github-actions-workflows)
explains each caller, trigger, template, and runner.

## What You Will Build

| Branch | Fabric workspace | Update method |
|---|---|---|
| `dev` | Development | Fabric Git integration |
| `test` | Test | GitHub Actions and fabric-cicd |
| `main` | Production | GitHub Actions and fabric-cicd |

Only the Dev workspace is connected to Git. Test and Production receive
deployments after pull requests are merged through `dev -> test -> main`.

## Before You Start

### GitHub

- Permission to fork the repository and administer the fork.
- A fine-grained personal access token (PAT) scoped to the fork with
  `Contents: Read and write`. Fabric uses this user-specific token for Git
  integration. Do not store it in the repository or as a GitHub Actions secret.
- GitHub Actions enabled on the fork.

### Azure

- Permission to create an Entra application and service principal, or an
  existing service principal for CI/CD.
- Access to the tenant ID, client ID, and client secret.
- A Fabric capacity to host three workspaces.

### Fabric

- Permission to create workspaces and assign them to the capacity.
- A Fabric administrator who can enable Git integration, GitHub integration,
  and service-principal access to Fabric APIs for the appropriate security
  groups. See [Fabric tenant settings](https://learn.microsoft.com/fabric/admin/about-tenant-settings).

## 1. Fork the Repository

1. Fork the repository and clone the fork.
2. Confirm that `dev`, `test`, and `main` exist. If the fork contains only
   `main`, create `test` and `dev` from the same commit.
3. Enable GitHub Actions on the fork.
4. Do not protect the branches yet. Fabric must first commit the fork's Dev
   bindings to `dev`.

## 2. Create the Service Principal and Workspaces

Create a service principal for GitHub Actions. This command creates credentials
but does not grant Fabric workspace access:

```bash
az ad sp create-for-rbac --name "SPN-Fabric-SDLC-Patterns" \
  --query "{tenantId:tenant, clientId:appId, clientSecret:password}" -o json
```

Store the output securely. The client secret is shown only when it is created.

Create three Fabric workspaces on the Fabric capacity. The names below are
recommended, not required:

| Workspace | Git-connected? | Service principal role |
|---|---|---|
| `microsoft-fabric-sdlc-patterns-dev` | Yes, to `dev` | None required |
| `microsoft-fabric-sdlc-patterns-test` | No | Contributor |
| `microsoft-fabric-sdlc-patterns-prod` | No | Contributor |

Open each workspace and copy its ID from the browser URL. In a URL such as
`https://app.fabric.microsoft.com/groups/<workspace-id>/...`, the GUID after
`/groups/` is the workspace ID. See
[Find your Microsoft Fabric workspace ID](https://learn.microsoft.com/fabric/data-factory/upgrade-pipelines-how-to-find-your-fabric-workspace-id).

In the Test and Production workspaces, open `Manage access`, add the service
principal by its name or application/client ID, and assign the `Contributor`
role.

## 3. Initialize the Dev Workspace

In the empty Dev workspace:

1. Open `Workspace settings > Git integration` and select GitHub.
2. Add your GitHub account using the fine-grained PAT.
3. Select the fork, branch `dev`, and folder `data/fabric`.
4. Select `Connect and sync`. Because the workspace is empty, update it from
   Git.
5. Open `PatternsLakehouse` and copy the two GUIDs from the browser URL:
   `https://app.fabric.microsoft.com/groups/<workspace-id>/lakehouses/<lakehouse-id>`.
   The GUID after `/groups/` is the Dev workspace ID, and the GUID after
   `/lakehouses/` is the Lakehouse item ID. If your URL does not expose the
   Lakehouse ID, list the workspace's Lakehouses with the
   [Fabric REST API](https://learn.microsoft.com/rest/api/fabric/lakehouse/items/list-lakehouses)
   and use the `id` of the item whose `displayName` is `PatternsLakehouse`.

The initial import preserves the reference repository's definitions and makes
the Variable Library's `Default` value set (the base variables stored in
`variables.json`) active. The next step replaces the reference environment with
your Dev baseline.

## 4. Replace the Reference Environment

> The committed IDs belong to the reference environment. Every independent
> fork must replace them before running notebooks or deploying.

Create one baseline commit with these changes:

1. Open `Patterns_Variables` and make the following changes:

   | Value set | Variable | Value |
   |---|---|---|
   | `Default` | `target_workspace_id` | Dev workspace ID |
   | `Default` | `target_workspace_name` | Dev workspace name |
   | `Default` | `target_lakehouse_id` | Dev `PatternsLakehouse` item ID |
   | `Default` | `target_lakehouse_name` | `PatternsLakehouse` |
   | `Test` | `target_workspace_id` | Test workspace ID |
   | `Prod` | `target_workspace_id` | Production workspace ID |

   Keep `Default` active in the Dev workspace. The other sample variables can
   retain their existing values or be customized for your organization.
2. Open `Import_Patterns_Data`, select `Lakehouse` in the notebook toolbar, and
   set the default Lakehouse to the Dev `PatternsLakehouse`.
3. Open `Patterns_Semantic_Model`, edit its Direct Lake connection, and select
   the Dev `PatternsLakehouse`.

Save the Fabric items, then use the Dev workspace `Source control` pane to
commit them to `dev`. Do not change any `.platform` `logicalId` values.

Pull that commit locally. In `data/fabric/parameter.yml`, replace every
reference-environment `find_value` with the corresponding Dev ID you recorded:
use the Dev Lakehouse ID for Lakehouse rules and the Dev workspace ID for
workspace rules. If you intend to evaluate the raw Bulk API path, make the
equivalent changes in `data/fabric/bulk-parameter.yml`.

Commit and push the parameter-file changes to `dev`. Search `data/fabric` for
the original IDs from the current `find_value` entries and confirm that no
unintended references remain. Do not replace `.platform` `logicalId` values;
they are portable item references, not environment IDs.

The Test and Production value sets do not define Lakehouse IDs. They inherit the
Dev Lakehouse ID from the base variables as a placeholder. During deployment,
`parameter.yml` replaces it with the ID of the `PatternsLakehouse` created in
the target workspace.

## 5. Configure GitHub

### Environment Secrets

In **Settings > Environments**, create environments named exactly `Test` and
`Prod`. Add these environment-scoped secrets to both; these are not repository
variables:

| Secret | Value |
|---|---|
| `AZURE_TENANT_ID` | Entra tenant ID |
| `AZURE_CLIENT_ID` | Service-principal application/client ID |
| `AZURE_CLIENT_SECRET` | Service-principal client secret |
| `FABRIC_WORKSPACE_ID` | Test ID in `Test`; Production ID in `Prod` |

For `Prod`, require a deployment reviewer and restrict deployments to `main`.

These workflows use client-secret authentication. OIDC is a recommended
production option to evaluate, not the authentication implemented by this
setup; see [Governance](fabric-cicd-governance-considerations.md).

### Deployment Method Variables

In **Settings > Secrets and variables > Actions > Variables**, use **New
repository variable** for the nonsecret settings below. Choose one method:

| Method | `DEPLOY_METHOD` | `DEPLOYMENT_PLAN_PATH` |
|---|---|---|
| fabric-cicd non-bulk — repository default | `fabric-cicd`, or leave unset | Not used |
| fabric-cicd non-bulk + client-read plan | `fabric-cicd-plan` | `data/fabric/DeploymentPlan.DeploymentPlan/plan.yml` |
| fabric-cicd bulk + client-read plan | `fabric-cicd-bulk` | `data/fabric/DeploymentPlan.DeploymentPlan/plan.yml` |
| Raw REST bulk — custom Python caller | `bulk` | Not used |

Both plan routes use the committed [sample plan](data/fabric/DeploymentPlan.DeploymentPlan/plan.yml)
unless you configure another checkout-relative plan path. Their adapters read
it client-side; they do not pass it to fabric-cicd or the REST API. See the
[Deployment Plan guide](fabric-deployment-plan-guide.md) for supported ordering
and experimental boundaries.

### fabric-cicd-bulk Settings

For **fabric-cicd bulk + client-read plan**, enter these two repository variables exactly:

| Repository variable | Value |
|---|---|
| `DEPLOY_METHOD` | `fabric-cicd-bulk` |
| `DEPLOYMENT_PLAN_PATH` | `data/fabric/DeploymentPlan.DeploymentPlan/plan.yml` |

- Use the four [environment secrets above](#environment-secrets); `FABRIC_WORKSPACE_ID` must identify the corresponding Test or Prod target.
- Use [parameter.yml](data/fabric/parameter.yml) for fabric-cicd replacements. `DEPLOY_METHOD=bulk` and [bulk-parameter.yml](data/fabric/bulk-parameter.yml) belong to the separate raw REST route.
- No extra GitHub bulk-feature flag is needed: the runner enables the required fabric-cicd feature flags.
- The shipped callers supply `ENVIRONMENT` (`Test`/`Prod`), `REPOSITORY_DIRECTORY` (`data/fabric`), and the seven-type `ITEM_TYPE_IN_SCOPE`. You do not create additional repository variables for these; customize the workflow inputs if needed.
- For a credentials-free schedule check, use the [bulk preview instructions](fabric-deployment-plan-guide.md#enable-and-preview-bulk).

### Before Switching Methods

Promote the selected workflows and their ETL listeners to the default branch
before switching methods, and wait for in-flight deployments to finish.
The selector applies to both Test and Prod; the routes are alternatives, not
concurrent deployment jobs. Evaluate fabric-cicd bulk in an approved nonproduction
target and configure Production protections before any Production promotion.

### Branch Rules

After the Dev baseline commits are complete, protect the branches with GitHub
rulesets:

| Branch | Required pull-request source | Required checks |
|---|---|---|
| `dev` | Feature branch | `Check for non-dev IDs in Fabric items`, `Run unit tests` |
| `test` | `dev` | `Enforce promotion path`, `Run unit tests` |
| `main` | `test` | `Enforce promotion path`, `Run unit tests` |

Require pull requests and block force pushes and deletions. Keep merge commits
as the only merge method only if that is your organization's preferred policy;
the included promotion workflows do not require it. The detailed control
rationale is in
[CI/CD Governance Considerations](fabric-cicd-governance-considerations.md).

## 6. Deploy Test and Production

1. Open a pull request from `dev` to `test` with a qualifying definition or
   workflow change and merge it. The selected Test deployment runs, followed
   by its ETL listener on successful completion.
2. Verify Test before continuing. Notebook completion is not a full release
   validation suite; use the [Quality Gates guide](fabric-cicd-quality-gates-and-release-controls.md)
   to define the evidence required for your workload.
3. Open a pull request from `test` to `main` and merge it. The Production
   workflow then waits for a `Prod` environment reviewer to approve the
   deployment.

Deployment path filters differ by method; documentation-only changes do not
start these deployments. Only the non-bulk-plan Test caller supports a manual
deployment run. Both ETL callers support manual runs. See the
[workflow reference](fabric-hybrid-cicd-guide.md#github-actions-workflows) before
trying to rerun a stage.

On the first deployment, open the Ontology in each target workspace and bind its
Graph Model to the local Lakehouse tables. See
[Initial Deployment to a Clean Workspace](fabric-hybrid-cicd-guide.md#initial-deployment-to-a-clean-workspace)
for that one-time Fabric UI step and its current workaround.

## 7. Verify the Setup

- Dev Source control reports branch `dev` and no pending changes.
- `Patterns_Variables` resolves the local values in each workspace.
- `Import_Patterns_Data` is bound to the local `PatternsLakehouse`.
- Test and Production are not Git-connected.
- Test and Production contain the `doctors`, `patients`, and `appointments`
  Lakehouse tables after ETL.
- The Semantic Model, report, Ontology, and Data Agent load in each environment.
- Pull requests can promote only through `dev -> test -> main`.

The platform is now ready for feature development. Continue with the
[Development Process](fabric-development-process.md) for Branch Out,
`workspace_swap.py`, and pull-request readiness checks.
