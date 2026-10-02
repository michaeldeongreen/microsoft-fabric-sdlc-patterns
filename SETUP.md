# Set Up This Repository

This guide takes an independent fork from empty workspaces to a working
`dev -> test -> main` promotion flow. It assumes familiarity with Azure and
GitHub, but no prior Microsoft Fabric setup experience.

The default and recommended deployment method is
[fabric-cicd](https://microsoft.github.io/fabric-cicd). The alternative Bulk API
path is documented separately in the [Bulk CI/CD Implementation Guide](fabric-bulk-cicd-guide.md).

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
  **Contents: Read and write**. Fabric uses this user-specific token for Git
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
4. Under **Settings > General > Pull Requests**, allow merge commits and disable
   squash and rebase merges. Promotion pull requests must preserve ancestry.
5. Do not protect the branches yet. Fabric must first commit the fork's Dev
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

Record each workspace ID from **Workspace settings > About**. Add the service
principal as **Contributor** to Test and Production.

## 3. Initialize the Dev Workspace

In the empty Dev workspace:

1. Open **Workspace settings > Git integration** and select GitHub.
2. Add your GitHub account using the fine-grained PAT.
3. Select the fork, branch `dev`, and folder `data/fabric`.
4. Select **Connect and sync**. Because the workspace is empty, update it from
   Git.
5. Open `PatternsLakehouse` and record its Lakehouse ID from the URL or item
   details.

The initial import preserves the reference repository's definitions and makes
the Variable Library's **Default** value set (the base variables stored in
`variables.json`) active. The next step replaces the reference environment with
your Dev baseline.

## 4. Replace the Reference Environment

> The committed IDs belong to the reference environment. Every independent
> fork must replace them before running notebooks or deploying.

Create one baseline commit with these changes:

| Item | Required change |
|---|---|
| `Patterns_Variables` Default value set | Set your Dev workspace ID/name and Lakehouse ID/name |
| `Patterns_Variables` Test value set | Set your Test workspace ID |
| `Patterns_Variables` Prod value set | Set your Production workspace ID |
| `Import_Patterns_Data` notebook | In the notebook UX, bind the default Lakehouse to the Dev `PatternsLakehouse` |
| `Patterns_Semantic_Model` | In the Fabric UX, bind the Direct Lake source to the Dev `PatternsLakehouse` |

Save the Fabric items, then use the Dev workspace **Source control** pane to
commit them to `dev`. Do not change any `.platform` `logicalId` values.

Pull that commit locally and update `data/fabric/parameter.yml`: every
`find_value` for the Dev workspace or Lakehouse must match the new Dev IDs now
stored in the item definitions. If you intend to evaluate the raw Bulk API path,
make the equivalent changes in `data/fabric/bulk-parameter.yml`.

Commit and push the parameter-file changes to `dev`. Search `data/fabric` for
the reference workspace and Lakehouse IDs and confirm that no unintended
references remain.

The Test and Production value sets do not define Lakehouse IDs. They inherit the
Dev Lakehouse ID from the base variables as a placeholder. During deployment,
`parameter.yml` replaces it with the ID of the `PatternsLakehouse` created in
the target workspace.

## 5. Configure GitHub

Create GitHub environments named exactly `Test` and `Prod`. Add these secrets to
both environments:

| Secret | Value |
|---|---|
| `AZURE_TENANT_ID` | Entra tenant ID |
| `AZURE_CLIENT_ID` | Service-principal application/client ID |
| `AZURE_CLIENT_SECRET` | Service-principal client secret |
| `FABRIC_WORKSPACE_ID` | Test ID in `Test`; Production ID in `Prod` |

For `Prod`, require a deployment reviewer and restrict deployments to `main`.
Set the repository variable `DEPLOY_METHOD` to `fabric-cicd`, or leave it unset
to use the same default.

After the Dev baseline commits are complete, protect the branches with GitHub
rulesets:

| Branch | Required pull-request source | Required checks |
|---|---|---|
| `dev` | Feature branch | `Check for non-dev IDs in Fabric items`, `Run unit tests` |
| `test` | `dev` | `Enforce promotion path`, `Run unit tests` |
| `main` | `test` | `Enforce promotion path`, `Run unit tests` |

Require pull requests and block force pushes and deletions. Keep merge commits
as the only merge method. The detailed control rationale is in
[CI/CD Governance Considerations](fabric-cicd-governance-considerations.md).

## 6. Deploy Test and Production

1. Open a pull request from `dev` to `test` and merge it with **Create a merge
   commit**. The Test deployment runs, followed by the ETL workflow.
2. Verify Test before continuing.
3. Open a pull request from `test` to `main` and merge it with **Create a merge
   commit**. The Production workflow then waits for a `Prod` environment
   reviewer to approve the deployment.

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
