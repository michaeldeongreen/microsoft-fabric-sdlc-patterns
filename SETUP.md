# Set Up This Repository

This guide takes a new fork from an unconfigured repository to a working
Dev -> Test -> Prod path. Start with `fabric-cicd`, the default non-bulk
deployment method. The other methods use the same setup and release lifecycle
but have additional validation boundaries.

Use dedicated sample workspaces and nonproduction data while learning the
pattern.

## What you will build

| Git branch | Fabric stage | Update mechanism |
|---|---|---|
| `dev` | Dev workspace | A named Dev workspace operator selects **Update all** |
| `test` | Test workspace | The selected GitHub Actions deployment method |
| `main` | Prod workspace | The selected GitHub Actions deployment method |

Each workspace has:

- one Fabric Workspace Identity;
- one Notebook connection authenticated with that Workspace Identity;
- one Power BI datasets refresh connection authenticated with that Workspace
  Identity; and
- a stage-specific Variable Library value set and physical item bindings.

The sample Fabric DataPipeline loads demonstration data, validates it, and
performs the only semantic-model refresh.

## Who performs each step

| Actor | Setup responsibility |
|---|---|
| GitHub repository administrator | Fork, branches, Actions, Environments, rulesets, secrets, variables, PAT lifecycle, and deployment-method selection |
| Entra identity/group administrator | Deployment application and service principal, client-secret lifecycle, service-principal allowlist group, and connections-admin group |
| Fabric tenant administrator | Required Git integration and service-principal tenant settings, scoped to the correct groups |
| Fabric workspace administrator | Capacity, Dev/Test/Prod workspaces, Workspace Identities, workspace roles, and Workspace Identity resource access |
| Feature workspace administrator / connection administrator | Feature Workspace Identity, its resource access, and its two connections |
| Feature developer | Own Git credential, Branch Out, local `.env`, swaps, feature testing, and feature-to-Dev PR |
| Dev workspace operator | Dev Fabric Git update, binding inspection, and manual Dev DataPipeline run |
| GitHub Actions | Selected Test/Prod connection ensure, publication, and Fabric DataPipeline execution |
| Release verifier or Prod reviewer | Test acceptance and Prod authorization where protection is configured |

The deployment service principal and a Workspace Identity have different jobs.
The service principal publishes definitions and submits jobs. The Workspace
Identity authenticates Notebook and semantic-model refresh activities.
One person can hold several human roles in a sample fork, but the required
authority and responsibility remain explicit.

## Before you start

### Local tools

Install:

- Git;
- Python 3.10 or later;
- `pip` and a Python virtual environment;
- Azure CLI for feature-workspace discovery and validation; and
- PowerShell if you want to use the commands exactly as shown.

From the repository root:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements-dev.txt
```

The local scripts do not need the deployment service principal's secret or the
GitHub Environment-variable PAT.

### Required access

Confirm that named administrators can:

- register an Entra application, create its service principal and credential,
  and manage security-group membership;
- configure Fabric tenant settings;
- assign capacity and create/administer Fabric workspaces;
- create a Workspace Identity and grant workspace/resource access;
- administer the fork, GitHub Actions, Environments, variables, secrets, and
  rulesets; and
- create and manage Fabric connections.

For the raw REST bulk method, importing Fabric item types requires an F SKU or
Fabric Trial. Verify the current capacity requirement for any other route and
item types you add.

### Values to record

Keep this inventory outside source control until each value has a documented
destination:

| Value | Where it is used |
|---|---|
| Entra tenant ID | GitHub Environment secret |
| Deployment application client ID and secret | GitHub Environment secrets |
| Dev/Test/Prod workspace GUIDs | GitHub Environment secrets and setup inputs |
| Dev/Test/Prod Workspace Identity object IDs | Permission verification |
| Connections-admin group object ID | Repository or Environment variable |
| Repository-scoped GitHub PAT | GitHub Environment secret |
| Dev Lakehouse, semantic-model, and connection GUIDs | One-time Dev baseline and local `.env` |
| Feature workspace and connection GUIDs | Developer's gitignored `.env` |

GUIDs are identifiers, not credentials, but validate their source before using
them. Never put credentials, access tokens, or PATs in `.env`, source, logs,
artifacts, or chat.

## 1. Fork and seed the branches

1. Fork the completed repository revision and clone your fork.
2. Leave GitHub Actions disabled until `dev`, `test`, and the GitHub
   Environments exist. This prevents branch creation from looking like a Test
   or Prod release.
3. Create `dev` and `test` from the same reviewed `main` commit:

   ```powershell
   git checkout main
   git pull --ff-only
   git branch dev
   git branch test
   git push origin main
   git push origin dev
   git push origin test
   ```

4. Record the starting commit:

   ```powershell
   git rev-parse HEAD
   ```

Use the repository's promotion path after initialization:

- feature branch -> `dev`
- `dev` -> `test`
- `test` -> `main`

## 2. Create identities, groups, and workspaces

### Deployment service principal and groups

Create or select one deployment service principal for the sample. If you
create it with Azure CLI, capture its output securely:

```powershell
az ad sp create-for-rbac --name "SPN-Fabric-SDLC-Patterns"
```

Do not grant unrelated Azure subscription roles merely because
`create-for-rbac` can do so. The required Fabric workspace role is configured
in Fabric.

Use separate security groups for separate responsibilities:

| Group | Members | Purpose |
|---|---|---|
| Fabric CI/CD service principals | Deployment service principal | Scope service-principal Fabric tenant settings |
| Fabric Git users | Users who connect Fabric workspaces to Git | Scope Git integration tenant settings when your tenant restricts them |
| Connections-Admins | Trusted human connection administrators | Receive Owner on the two connections in each stage |

Do not add developers to an all-environment connection Owner group merely to
let them use Dev. Share only the required Dev dependencies with User access.

### Fabric tenant settings

The Fabric tenant administrator must verify the current settings and scope
them to the intended groups. This sample requires:

- GitHub/Fabric Git integration for the users who connect Dev and feature
  workspaces;
- **Service principals can call Fabric public APIs**; and
- **Service principals can create workspaces, connections, and deployment
  pipelines** for the approved deployment service principal group.

Workspace roles do not override a tenant setting. The repository does not
change tenant settings or group membership.

See the current
[Fabric developer tenant settings](https://learn.microsoft.com/en-us/fabric/admin/service-admin-portal-developer)
before applying tenant-wide changes.

### Workspaces and Workspace Identities

Create Dev, Test, and Prod workspaces on an appropriate capacity. Record the
workspace GUID Fabric assigns to each.

For every workspace:

1. Grant the deployment service principal Contributor, preserving any stronger
   approved assignment.
2. Open **Workspace settings -> Workspace identity** and create the Workspace
   Identity if it does not exist.
3. Open **Manage access** and grant that Workspace Identity the workspace and
   resource access required by the Notebook and semantic-model refresh
   activities. Contributor is the Notebook baseline for this same-workspace
   sample.
4. Record the Workspace Identity object ID and verify the assignment.

Creating a Workspace Identity does not create its connections. Connection
creation happens later and differs by stage.

### Post-ETL refresh permissions

<a id="post-etl-refresh-permissions"></a>

| Actor or identity | Required access | Does not imply |
|---|---|---|
| Fabric workspace administrator | Admin to create the Workspace Identity and assign access | Connection access for every workspace user |
| Deployment service principal | Contributor in each target; approved tenant API scope | Activity runtime authentication or workspace Admin |
| Workspace Identity | Notebook, model, OneLake, and other workload rights required by the stage | Publication authority or GitHub access |
| Connections-Admins group | Owner on the two stage connections | Workspace Admin or runtime identity |
| User or developer | Contributor/member as required in Dev/feature; User on dependencies they execute | Test/Prod connection Owner |
| Semantic-model owner | Source authorization and model ownership/takeover where required | Deployment or activity rights |

Connection access is separate from workspace access. A successful publication
does not prove model ownership, source authorization, report access, or
consumer permissions.

## 3. Configure GitHub

<a id="5-configure-github"></a>

### Create GitHub Environments

Create:

| GitHub Environment | Allowed deployment branch | Fabric target |
|---|---|---|
| `Dev` | `dev` | Dev workspace |
| `Test` | `test` | Test workspace |
| `Prod` | `main` | Prod workspace |

Configure a required reviewer and deployment-branch policy for Prod before the
first Prod release. The workflow files do not create or prove those controls.

### Environment secrets

Add these secrets to each Environment:

| Secret | Value |
|---|---|
| `AZURE_TENANT_ID` | Entra tenant ID |
| `AZURE_CLIENT_ID` | Deployment application client ID |
| `AZURE_CLIENT_SECRET` | Deployment application credential |
| `FABRIC_WORKSPACE_ID` | That Environment's workspace GUID |
| `GH_ENV_VARIABLES_TOKEN` | Repository-scoped PAT with Contents read/write and Environments read/write |

The PAT is on every selected Test/Prod release path. It is restricted to
GitHub preflight and connection-ID persistence steps; it does not authenticate
to Fabric. The deployment service principal is used for Fabric operations.

The reference sample can use one fine-grained PAT for Fabric Git and GitHub
Environment-variable writes, but that couples their availability and grants
broader Environment-management authority than two variable names. For a
production fork, prefer an expiring credential with a named rotation owner or
an appropriately scoped GitHub App. Each developer uses their own Fabric Git
credential.

### Environment and repository variables

<a id="environment-variables"></a>

Set the connections-admin group once as a repository variable:

| Variable | Value |
|---|---|
| `FABRIC_CONNECTION_ADMINS_GROUP_ID` | Connections-Admins group object ID |

An Environment variable with the same name can override it for stage-specific
groups.

Do not manually invent these Environment variables:

| Variable | Created by | Meaning |
|---|---|---|
| `NOTEBOOK_CONNECTION_ID` | Dev provisioning action or selected Test/Prod release | Stage Notebook connection GUID |
| `SEMANTIC_MODEL_REFRESH_CONNECTION_ID` | Dev provisioning action or selected Test/Prod release | Stage Power BI datasets refresh connection GUID |

Missing values are created and verified. A different existing value fails
closed and is never overwritten.

### Deployment method variables

<a id="deployment-method-variables"></a>

Start with the default:

| Method | `DEPLOY_METHOD` | `DEPLOYMENT_PLAN_PATH` | Initial status |
|---|---|---|---|
| fabric-cicd non-bulk | unset or `fabric-cicd` | Not used | Recommended; default Test live-verified |
| fabric-cicd non-bulk with client-read plan | `fabric-cicd-plan` | `data/fabric/DeploymentPlan.DeploymentPlan/plan.yml` | Experimental; not live-verified |
| fabric-cicd bulk with client-read plan | `fabric-cicd-bulk` | Same plan path | Experimental; not live-verified |
| Raw REST bulk | `bulk` | Not used | Revalidate current API/capacity behavior; not live-verified |

<a id="fabric-cicd-bulk-settings"></a>

The fabric-cicd methods use `parameter.yml`. Raw REST uses
`bulk-parameter.yml`. All four share the connection prelude and the same
Fabric DataPipeline handoff.

<a id="before-switching-methods"></a>

Before switching methods:

1. Wait for in-flight Test and Prod releases.
2. Promote any required workflow/runner changes normally.
3. Change `DEPLOY_METHOD`.
4. Manually dispatch from `test` or `main`, or wait for the next qualifying
   promotion. Changing the variable alone does not start a run.
5. Treat the new route as unverified until its own cold and repeat Test
   evidence is accepted.

### Branch rules

After the one-time Dev baseline is committed, require PRs, block force pushes
and branch deletion, and configure:

| Target | Allowed source | Required checks |
|---|---|---|
| `dev` | Feature branch | `Check for non-dev IDs in Fabric items`, `Run unit tests` |
| `test` | `dev` | `Enforce promotion path`, `Run unit tests` |
| `main` | `test` | `Enforce promotion path`, `Run unit tests` |

For a single-person sample fork, decide explicitly who can approve or bypass
initialization. Remove temporary bypass authority after setup.

Enable GitHub Actions only after the branches, Environments, secrets, variables,
and intended deployment selector are in place.

## 4. Provision Dev connections

<a id="first-time-dev-bootstrap"></a>

The workflow file `.github/workflows/bootstrap-dev.yml` appears in Actions as
**Provision Fabric Connections**.

For the normal setup path, run it only for Dev:

1. Open GitHub Actions and select **Provision Fabric Connections**.
2. Select branch `dev`.
3. Select operation `provision`.
4. Confirm the target is the `Dev` GitHub Environment and run the workflow.
5. Verify that it:
   - validates the pre-existing Dev Workspace Identity;
   - creates or reuses distinct Notebook and Power BI datasets connections
     using Workspace Identity authentication;
   - grants or upgrades Connections-Admins to Owner and reads the role back;
   - creates and verifies both Dev connection-ID variables; and
   - reports no workspace-role, item-publication, or pipeline activity.

Names use
`Patterns-<Dev|Test|Prod|Feature>-<Purpose>-<full-workspace-GUID>`.
The GUID prevents name collisions between forks in one tenant.

Copy the Dev pair from **Repository Settings -> Environments -> Dev ->
Environment variables**. Cross-check each value in Fabric under
**Settings -> Manage connections and gateways -> Connections**: open the exact
Dev connection, confirm its connector/authentication/workspace, and compare the
GUID in its details URL. Do not choose a similarly named connection.

Do not repeat this manual step for Test or Prod in the normal path. The first
selected Test/Prod release performs the same connection ensure automatically.
A manual Test/Prod run is for recovery, migration, or diagnostics.

## 5. Initialize Dev and replace sample references

<a id="3-initialize-the-dev-workspace"></a>
<a id="4-replace-the-reference-environment"></a>

The repository contains real physical references from its source Dev
workspace. Replace them once with your fork's canonical Dev references before
ordinary feature work.

### Stage the DataPipeline out of the first Git import

From `dev`:

```powershell
python scripts\prepare_fabric_workspace.py --stage-initial-pipeline
```

Review the move from `data/fabric` to `data/fabric-initialization`, then commit
and push it. This prevents the first whole-branch Fabric Git import from
creating a DataPipeline whose physical model and connection IDs still point to
the source repository's tenant.

### Connect and configure Dev

1. In Dev, open **Workspace settings -> Git integration**.
2. Use your own GitHub identity, select the fork, branch `dev`, and folder
   `data/fabric`.
3. Connect and synchronize the base items. Review the warning that a whole
   branch update can replace workspace content.
4. Open each item and record the GUID from its Fabric URL:
   - `PatternsLakehouse`
   - `Patterns_Semantic_Model`
   Verify that the URL's workspace segment is the Dev workspace GUID.
5. Configure `Patterns_Variables`:

   | Value set | Variable | Expected value |
   |---|---|---|
   | Default | `target_workspace_id` | Dev workspace GUID |
   | Default | `target_workspace_name` | Dev workspace name |
   | Default | `target_lakehouse_id` | Dev `PatternsLakehouse` GUID |
   | Default | `target_lakehouse_name` | `PatternsLakehouse` |
   | Default | `minimum_patient_count` | Positive Integer; sample baseline `5` |
   | Test | `target_workspace_id` override | Test workspace GUID |
   | Prod | `target_workspace_id` override | Prod workspace GUID |

   Keep Default active in Dev. The deploy-time rules replace the inherited
   Lakehouse ID for Test/Prod.
6. Open `Import_Patterns_Data`, use its Lakehouse pane to add the existing Dev
   `PatternsLakehouse`, and save the Notebook.
7. Open `Patterns_Semantic_Model` in the Fabric web model editor and confirm
   that its Direct Lake source is the Dev Lakehouse. The stored OneLake
   connection expression must contain the Dev workspace and Lakehouse GUIDs.
   See [Direct Lake web modeling](https://learn.microsoft.com/en-us/fabric/fundamentals/direct-lake-web-modeling).
8. Confirm the semantic-model owner has source authorization. Take over the
   model only through your approved ownership process; see
   [Direct Lake owner permissions](https://learn.microsoft.com/en-us/fabric/fundamentals/direct-lake-security-integration#direct-lake-owners).
9. Save and commit the canonical Fabric changes, then pull them locally.
   Preserve every `.platform` logical ID.

### Record the canonical Dev bindings

Copy [.env.sample](.env.sample) to the gitignored `.env` and set:

- `DEV_WORKSPACE_ID`
- `DEV_SEMANTIC_MODEL_ID`
- `DEV_NOTEBOOK_CONNECTION_ID`
- `DEV_REFRESH_CONNECTION_ID`

Use the real Dev model and the verified Dev connection pair. Then run:

```powershell
python scripts\prepare_fabric_workspace.py --dev --replace-dev-bindings
python scripts\prepare_fabric_workspace.py --restore-initial-pipeline
python scripts\workspace_swap.py --check-ready
```

The first command updates the two parameter-rule baselines and the staged
DataPipeline together. It does not call Fabric. Review the exact GUID-only
changes; do not accept malformed or disagreeing parameter rules.

Commit and push the complete canonical Dev revision. In Fabric, select
**Update all**, inspect the resolved bindings, and run
`Patterns_Load_Validate_And_Refresh`.

The Dev gate is complete when:

- load, validation, and native refresh all finish successfully;
- the active value set and physical targets belong to Dev;
- the required model date fields and report work under the intended owner; and
- `python scripts\workspace_swap.py --check-ready` passes.

## 6. Complete one feature cycle

Follow [Development Process](fabric-development-process.md). The short path is:

1. Branch Out from Dev with all items.
2. Create the feature Workspace Identity and its two Workspace
   Identity-authenticated connections.
3. Populate the feature values in `.env`.
4. Run `/swap-to-feature`, commit, push, and update the feature workspace.
5. Activate the feature value set and run the Fabric DataPipeline.
6. Run `/swap-to-dev`, review the restoration, and open the PR to `dev`.
7. After merge, update Dev manually and run the Dev DataPipeline again.

Do not use fabric-cicd to publish into a Git-connected feature workspace.

## 7. Run the first Test release

Do not manually create the Test connection pair. Before promotion, confirm:

- the Test workspace and Workspace Identity exist;
- the Workspace Identity has its required workspace/resource access;
- the deployment service principal is Contributor;
- the Test GitHub Environment has all five secrets;
- the connections-admin group variable is correct; and
- `DEPLOY_METHOD` is unset or `fabric-cicd`.

Open and review a `dev` to `test` PR. After merge, the selected Test workflow:

1. validates the Test branch/Environment and GitHub PAT access;
2. ensures the Test Workspace Identity connection pair;
3. verifies Connections-Admins Owner;
4. saves missing ID variables without replacing different values;
5. publishes with fabric-cicd;
6. starts and polls the same-revision Fabric DataPipeline.

All other method workflows can appear with skipped jobs. Verify that the
selected workflow, not merely a skipped workflow, completed.

For a clean target, configure the Ontology Graph Model's local Lakehouse
binding if Fabric requires it, then verify the workload:

- expected Lakehouse tables and validation results;
- target DataPipeline connections and model binding;
- semantic-model refresh, ownership/source access, date fields, and required
  calculations;
- report rendering;
- Ontology entity/relationship behavior; and
- Data Agent behavior and consumer access required by your release.

The shared sequence and current evidence are documented in
[Release Process](fabric-release-process.md).

## 8. Run the first Prod release

Before promotion:

1. Configure the Prod Environment reviewer and deployment-branch policy.
2. Confirm Prod workspace, Workspace Identity, permissions, secrets, and group
   configuration.
3. Attach the accepted Test evidence to the release decision.
4. Open and review a `test` to `main` PR.

After merge and approval, the selected Prod job uses the same automatic
connection ensure, publication, and DataPipeline sequence with Prod-scoped
configuration.

Prod has not been live-verified by this repository revision. Treat the first
promotion as a controlled release with an explicit recovery point and recorded
post-deployment evidence.

## Verify the setup

| Check | Expected result |
|---|---|
| Actor separation | Users, GitHub Actions, deployment SP, PAT, Workspace Identity, and connection-admin group have distinct documented responsibilities |
| Connections | Two different WI-authenticated connections per stage; Owner verified for the intended group |
| Dev | Git-connected, canonical local references, manual update and DataPipeline |
| Feature | Pair created by the feature workspace/connection administrator, feature-only physical targets, feature value set active |
| Test/Prod | Selected release ensures connections before publishing and uses the same revision for the DataPipeline |
| Persistence | Missing connection-ID variables are created; conflicting values fail |
| Runtime | Load -> validation -> native refresh, with no second refresh owner |
| Protection | Required PR checks and configured Prod Environment approval |

## Troubleshooting

| Symptom | Owner and first check |
|---|---|
| No deployment ran | Repository administrator: selected branch, `DEPLOY_METHOD`, path filters, and whether the selected job was skipped |
| Waiting for approval | Prod reviewer: GitHub Environment protection and authorized branch |
| PAT preflight or persistence failed | Repository administrator: token expiry and repository Contents/Environments permissions |
| Workspace Identity missing or token unavailable | Fabric workspace/tenant administrator: WI creation, capacity, tenant policy, and resource rights |
| Cannot see or use a connection | Connection administrator: exact GUID, authentication type, Owner/User sharing, and fresh sign-in |
| Existing ID conflicts with ensured resource | Repository administrator: stop and review the intended migration; do not overwrite |
| Feature preparation reports missing connections | Feature workspace administrator: create both feature connections first and copy their exact GUIDs |
| Dev baseline disagreement | Repository administrator: compare both parameter files, `.env`, and the canonical Dev items; rerun the explicit baseline command |
| Publication failed | Release operator: selected publisher's item-level result; ETL should not have started |
| GitHub timed out while Fabric still runs | Release operator: inspect the exact Fabric run before retrying |
| DataPipeline failed | Workload owner: failed activity, active value set, bindings, source/model permissions, capacity, and refresh history |
| Report or calculations are wrong after a green run | Semantic-model owner/business tester: source authorization, ownership, DAX/calculations, and consumer access |

## Existing forks and legacy connections

The **Provision Fabric Connections** workflow also has a Dev-only
`share-existing` operation for an approved legacy pair. It grants the
connections-admin group Owner; it does not convert credentials, overwrite
variables, publish items, or delete resources.

For a reviewed migration:

1. Record the old GUIDs and their references.
2. Remove only stale GitHub variable entries when explicitly approved.
3. Provision the Workspace Identity successors.
4. update the canonical Dev source references through review;
5. run Dev and the normal Test promotion; and
6. retain old connections until the promoted `main` revision is accepted in
   Prod and a separate deletion approval is recorded.

Deleting a variable is not permission to delete its Fabric resource.

## Cleanup

After a feature is merged and the updated Dev workspace is accepted:

| Order | Actor | Action |
|---|---|---|
| 1 | Feature developer | Record the workspace, Workspace Identity, branch, and exact connection GUIDs; prove no active source/pipeline references remain |
| 2 | Release/repository owner | Retain required evidence and approve the named resources for deletion |
| 3 | Connection administrator | Delete the two tenant-level feature connections while their workspace/identity context is still available |
| 4 | Fabric workspace administrator | Delete the feature workspace and record the resulting Workspace Identity lifecycle/capacity release |
| 5 | GitHub repository administrator | Delete the feature branch when recovery policy permits |
| 6 | Feature developer | Clear all five feature values from local `.env` |

Workspace deletion is not proof that tenant-level connections were removed.
Source cleanup performed by `/swap-to-dev` is not deletion approval.

For full sample teardown:

| Order | Actor | Action |
|---|---|---|
| 1 | GitHub repository administrator | Disable scheduled/manual release entry points, wait for active runs, and record current Environment variables |
| 2 | Release owner | Retain the accepted commit, run URLs, resource inventory, and any required definition/data recovery points |
| 3 | Connection administrator | Verify no pipeline uses the Dev/Test/Prod connection GUIDs, then delete the approved connection pairs |
| 4 | Fabric workspace administrator | Remove workloads/workspaces and record the lifecycle of each Workspace Identity; release dedicated capacity assignments |
| 5 | GitHub repository administrator | Remove connection-ID variables, secrets, Environments, rulesets, and the repository-scoped PAT after they are no longer needed |
| 6 | Entra/Fabric tenant administrator | Remove workspace roles, revoke the deployment credential, remove the SP from tenant-setting groups, and delete the app/groups only when no other workload uses them |
| 7 | Each developer | Delete the local `.env` and any cached credentials for this sample |

Do not use publisher orphan cleanup as a substitute for environment teardown.
