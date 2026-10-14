# Set Up This Repository

An ordered path from a fresh fork to `dev -> test -> main`, using
**fabric-cicd non-bulk**, the default deployment method. See the
[implementation guide](fabric-hybrid-cicd-guide.md) and
[method comparison](README.md#choose-a-deployment-method) for alternatives.

## What You Will Build

| Branch | Workspace | Updates |
|---|---|---|
| `dev` | Dev | Human Fabric Git Update all |
| `test` | Test | GitHub Actions deployment and pipeline run |
| `main` | Prod | Approved GitHub Actions deployment and pipeline run |

Each workspace has its own Workspace Identity (WI) and two WI-authenticated
connections: Notebook and Semantic Model refresh. Connections are tenant-level
resources with separate permissions, not items copied by Git.

The native `Patterns_Load_Validate_And_Refresh` pipeline loads demonstration
data, validates it, then refreshes the model. Use dedicated sample workspaces,
never business Production data.

### Setup checklist and responsibility

| Step | Who |
|---|---|
| Fork, create workspaces/SP/group, configure WI and secrets | Repository owner/platform administrator |
| Create/reuse connections, grant group Owner, save GUID variables | Explicit provisioning action |
| Establish real Dev references, connect/sync Git, run Dev | Repository owner |
| Branch Out, prepare private feature workspace, swap references | Developer using their own account |
| Deploy and run Test/Prod | Existing deployment actions |

> Earlier user-invoked feature prototypes completed all three activities with
> WI. That is not proof of the current CI caller, fresh Branch Out, or every
> deployment method. Use the normal feature/Dev/Test runs to verify results;
> report actual permission/binding failures rather than creating prototypes.

## Before You Start

### GitHub

- Administration rights on your fork and Actions enabled.
- A new fine-grained PAT restricted to the fork: **Contents read/write** for
  Fabric Git and **Environments read/write** for saving connection-ID variables.
  Enter it securely in your Fabric Git account and the provisioning secrets.
  Do not put it in source, `.env`, artifacts, logs, or chat.
- Set an expiration and plan renewal. The reference demonstration deliberately
  uses a non-expiring PAT; **that is not best practice**. Token reuse couples
  Fabric Git and variable-storage availability. GitHub Environments write also
  authorizes other environment-management/secret-write operations.
- Each developer configures their **own** Fabric Git credentials. Do not
  distribute the repository owner's PAT. A GitHub App/separate expiring credential
  is a production alternative, not required for this sample.

### Azure and Fabric

- One existing or newly registered deployment service principal (SPN).
- A capacity and permission to create/administer the sample workspaces.
- Tenant approvals for Git/GitHub integration, **Service principals can call
  Fabric public APIs**, and **Service principals can create workspaces,
  connections, and deployment pipelines**, limited to approved principals.
- Permission to create a security-enabled Entra connections-administrators
  group and manage its membership.

## 1. Fork the Repository

1. Fork/clone the repository; establish `dev`, `test`, and `main` from the same
   completed sample revision if the fork contains only `main`.
2. Enable Actions. Finish initial Dev baseline commits before imposing branch
   rules that prohibit the repository owner's one-time initialization.
3. Install the existing local tools:

   ```powershell
   pip install -r requirements-dev.txt
   ```

   Swaps read the YAML parameter files using PyYAML. No local Azure SP secret
   or provisioning PAT is required by local developer scripts.

## 2. Create the Service Principal and Workspaces

Use one deployment SP for the sample; no second Azure SP is needed to write
GitHub variables. GitHub writes use the PAT, not an Azure credential.
If creating an application, save its initial secret securely:

```powershell
az ad sp create-for-rbac --name "SPN-Fabric-SDLC-Patterns"
```

Create Dev, Test, and Prod workspaces and record the IDs **Fabric assigns**.
Only Dev will be Git-connected. Give the deployment SP **Contributor** on
each target workspace, preserving any stronger approved assignment.

In each workspace, a human Admin opens **Workspace settings -> Workspace
identity**, creates WI if absent, and grants that identity **Contributor**
through **Manage access** for this same-workspace Notebook workload.
The identity also needs the required model/OneLake resource access.

Create a trusted Entra **Connections-Admins** security group and add the
connection administrator(s). It will receive **Owner** on both connections in each stage.
This does not grant its members workspace Admin.

### Post-ETL Refresh Permissions

| Actor | Workspace/resource rights | Connection rights |
|---|---|---|
| Human setup administrator | Admin to create WI; appropriate item access | Group Owner for management |
| Deployment SP | Contributor to publish and submit jobs | Owns the resources it provisions; publishers only read/use them |
| Workspace Identity | Required Notebook/model/OneLake rights; Contributor is the Notebook baseline | Runtime authentication selected by the activity |
| Developer | Member/Contributor on shared Dev | User on Dev dependencies, shared by an Owner |

Git update validates connection use. Workspace Admin or item ownership alone
does not grant connection access. Share individual developers as **User** in
**Settings -> Manage connections and gateways -> Connections -> Manage users**;
do not put all developers in the all-environment administrator group.

The job submitter is still the SP, but WI-authenticated activities do not use
its secret as their runtime credential. The SP is not elevated to provision
WIs or inspect/change workspace ACLs. See
[Notebook WI permissions](https://learn.microsoft.com/en-us/fabric/data-factory/notebook-activity#using-fabric-workspace-identity-wi-in-the-notebook-activity)
and [governance](fabric-cicd-governance-considerations.md#automated-connection-setup-the-samples-privilege-trade-off).

<a id="5-configure-github"></a>

## 3. Configure GitHub

### Environment Secrets

Create GitHub Environments `Dev`, `Test`, and `Prod`, restricted to `dev`,
`test`, and `main` respectively. Require a reviewer for Prod. Add to **each**:

| Secret | Value |
|---|---|
| `AZURE_TENANT_ID` | Entra tenant ID |
| `AZURE_CLIENT_ID` | Deployment application's client ID |
| `AZURE_CLIENT_SECRET` | Deployment application's secret |
| `FABRIC_WORKSPACE_ID` | This environment's workspace GUID |
| `GH_ENV_VARIABLES_TOKEN` | PAT with Environments write, used only by provisioning |

The built-in `GITHUB_TOKEN` cannot acquire environment-administration rights
through `permissions: actions: write`. The PAT is deliberately confined to
the standalone provisioning workflow, not ordinary publishers or PR jobs.
Never copy Azure/GitHub secret values to developer configuration.

### Environment Variables

Set **one repository variable** manually:

| Variable | Value |
|---|---|
| `FABRIC_CONNECTION_ADMINS_GROUP_ID` | Your trusted security group's Object ID |

One common group is a sample simplification. Real deployments should generally
use environment-specific administration groups; an Environment variable with
the same name can supply that stage's group. Do not use the sample tenant's ID.

Provisioning automatically creates these **two variables per environment**:

| Variable | Value |
|---|---|
| `NOTEBOOK_CONNECTION_ID` | Target workspace's Notebook connection GUID |
| `SEMANTIC_MODEL_REFRESH_CONNECTION_ID` | Target workspace's refresh connection GUID |

Existing values must match validated resources. Missing referents, incorrect
authentication, or mismatches fail explicitly; no silent overwrite or replacement.
Publishers consume the pair with `existing`/`WorkspaceIdentity`, validate it
read-only, and substitute the GUIDs through the existing parameter rules.
Neither connection names nor the SP's identity select IDs automatically.

### Deployment Method Variables

Choose one repository-level selector; leave the default until Test works:

| Method | `DEPLOY_METHOD` | `DEPLOYMENT_PLAN_PATH` |
|---|---|---|
| fabric-cicd non-bulk (recommended) | `fabric-cicd` or unset | Not used |
| fabric-cicd non-bulk + plan | `fabric-cicd-plan` | `data/fabric/DeploymentPlan.DeploymentPlan/plan.yml` |
| fabric-cicd bulk + plan | `fabric-cicd-bulk` | Same plan path |
| Raw REST bulk | `bulk` | Not used |

### fabric-cicd-bulk Settings

The bulk SDK uses `parameter.yml`; raw REST uses `bulk-parameter.yml`. All four
methods consume the same environment connection variables and native pipeline.
No extra bulk feature-flag variable is needed. See the
[plan/preview guide](fabric-deployment-plan-guide.md#enable-and-preview-bulk).

### Before Switching Methods

Wait for in-flight deployments and promote shared workflow changes normally.
The selector affects Test and Prod; methods are alternatives, not concurrent
jobs. Client-secret deployment authentication remains the sample default;
OIDC is a separate production enhancement.

### Shared ETL Follow-up

Each deployment's same-revision `needs` job starts the one native DataPipeline.
Load must succeed before validation, then refresh. `run_label` is an independent
String; the positive Integer patient threshold comes from the active Variable
Library. There is no second ETL or external model-refresh owner.

## 4. Provision Connections

### First-Time Dev Bootstrap

The historical file [bootstrap-dev.yml](.github/workflows/bootstrap-dev.yml)
now appears as **Provision Fabric Connections** in Actions. It is manual,
not a Dev-push listener and not part of routine deployment.

1. Select **Run workflow**, branch `dev`, operation `provision`.
2. It checks GitHub access/configuration, requires the preexisting target WI,
   and creates/reuses Notebook and PowerBIDatasets WI connections. No model or
   pipeline needs to exist.
3. It grants your group **Owner on both**, verifies readback, and then writes/
   verifies both environment variables with the PAT.
4. Repeat using branch `test` for Test and `main` for Prod. Environment approvals
   still apply. Fresh forks of the completed main revision contain this workflow.

Names follow `Patterns-<Dev|Test|Prod|Feature>-<Purpose>-<full-workspace-GUID>`.
The GUID avoids collisions between forks in one tenant. Explicit existing IDs
can retain intentional names; names are labels, not workspace security scopes.

Read-access preflight cannot prove every PAT write permission. A denied write
fails visibly; created connections/confirmed grants may remain and are reused
on retry. Partial variable saves are also reconciled without overwriting.
Current-job steps use outputs, not an assumed refresh of the `vars` context.

This action never loads data, runs a pipeline, modifies workspace roles/WI,
publishes items, or changes capacity.

<a id="3-initialize-the-dev-workspace"></a>
<a id="4-replace-the-reference-environment"></a>

## 5. Initialize Dev and Replace the Reference Environment

The sample's physical workspace/model/connection IDs are not your fork's IDs.
Ordinary Fabric **Update all** syncs the entire Git branch; do not rely on
selecting the native pipeline out of the first import.

1. Before first connecting empty Dev, stage its pipeline outside `data/fabric`:

   ```powershell
   python scripts\prepare_fabric_workspace.py --stage-initial-pipeline
   ```

   Review/commit/push the resulting `data/fabric-initialization` move on your
   initial Dev revision. Logical item identities are preserved; this is not a
   prototype pipeline or another recurring bootstrap PR.
2. In Fabric **Workspace settings -> Git integration**, add your own GitHub
   account/PAT, select your fork, branch `dev`, folder `data/fabric`, and connect/
   sync the canonical base items. The pipeline is deliberately absent.
3. Record the new `PatternsLakehouse` and `Patterns_Semantic_Model` physical IDs.
   Configure `Patterns_Variables`: Default Dev workspace/Lakehouse IDs and names,
   Test and Prod workspace IDs; keep the positive Integer threshold at its
   agreed value (sample `5`). Keep Default active in Dev.
4. Attach the loader to Dev's Lakehouse and set the model's Direct Lake source
   to that Lakehouse. Validation uses explicit Library-based OneLake paths, not
   an attached Lakehouse. Save/commit these canonical items through Fabric,
   then pull locally. Do not change `.platform` logical IDs.
5. Replace reference workspace/Lakehouse source GUIDs in **both** parameter
   files with the actual Dev IDs. Keep their target expressions unchanged.
6. Copy [.env.sample](.env.sample) to `.env`, then set `DEV_WORKSPACE_ID`,
   `DEV_SEMANTIC_MODEL_ID`, `DEV_NOTEBOOK_CONNECTION_ID`, and
   `DEV_REFRESH_CONNECTION_ID` using the real model and provisioned Dev pair.

   ```powershell
   python scripts\prepare_fabric_workspace.py --dev --replace-dev-bindings
   python scripts\prepare_fabric_workspace.py --restore-initial-pipeline
   python scripts\workspace_swap.py --check-ready
   ```

   The first command aligns both parameter files and the staged pipeline. It
   is an explicit reviewed baseline cutover, not permission to accept malformed
   or disagreeing rules. No cloud calls, artifacts, or extra binding JSON.
7. Review/commit/push the full canonical revision, then Update all in Dev.
   Run the native pipeline only after the real references are in place.

Test/Prod Lakehouse and model GUIDs are resolved during deployment. `.env` is
local input; Fabric does not read it, and CI reads committed parameter rules.
An initialized ordinary `/swap-to-dev` needs no local Dev credentials/IDs and
never dispatches provisioning.

### Manual Dev Update and Validation

After feature work: `/swap-to-dev`, review/commit/push, checked PR/merge, Fabric
**Update all**, then run the native pipeline. Verify all three activities and
the model's date fields/report. No automatic Dev Git sync, additional SP Git
PAT, or recurring UI rebinding. Do not sync Dev-restored definitions into a
private feature workspace.

### Branch Rules

After baseline setup, require reviewed PRs and block force pushes/deletions:

| Target | Source | Required checks |
|---|---|---|
| `dev` | Feature | `Check for non-dev IDs in Fabric items`, `Run unit tests` |
| `test` | `dev` | `Enforce promotion path`, `Run unit tests` |
| `main` | `test` | `Enforce promotion path`, `Run unit tests` |

## 6. Deploy Test and Production

Merge a qualifying Dev -> Test PR. The selected publisher validates/uses the
Test WI pair, deploys items, then runs/polls the native pipeline. Verify Test
before Test -> main promotion and the protected Prod deployment.

Documentation-only changes need not trigger deployment; manual recovery runs
must select the correct stage branch. Do not rerun an old revision to test new
code. See [workflow details](fabric-hybrid-cicd-guide.md#github-actions-workflows).

On initial target deployment, configure the Ontology Graph Model's local
Lakehouse binding as described in
[clean-workspace setup](fabric-hybrid-cicd-guide.md#initial-deployment-to-a-clean-workspace).

## 7. Verify the Setup

- Humans in the admin group can see/manage both connections for each stage.
- Each stage has its own WI; both connection types report WI authentication.
- Saved connection GUIDs match the stage; no publisher credential/role writes.
- Dev Git is synced, Library/Notebook/model targets are local, and all native
  activities complete before reporting success.
- Normal Branch Out/feature work uses its own manually prepared WI/pair and
  restores the committed Dev baseline before the PR.

## Troubleshooting Post-ETL Refresh

| Symptom | Check |
|---|---|
| Update all says no connection access | Exact incoming GUIDs and connection sharing, not just workspace Admin or a similarly named connection |
| Cannot see an SP-created connection | Group Owner must be granted/read back. Membership/visibility can require a fresh sign-in |
| No WI or cannot obtain WI token | Human WI setup, WI resource rights, invoking SP workspace Contributor, tenant API/Conditional Access policies |
| Provisioning stops before ID save | Mandatory group GUID, supported WI connector type, actual Owner readback, PAT repository/Environments scope |
| Existing ID/authentication mismatch | Deliberate reviewed migration; no credential conversion or silent variable overwrite |
| Source-baseline disagreement | Align both parameter files and Library, then run local preparation/readiness |
| Native validation/refresh fails | Inspect the failed activity, Library parameters, source/model permissions, capacity, and actual completed refresh history |

For an existing repository's obsolete SP-runtime Dev pair, the same provisioning
workflow has **share-existing**, restricted to `dev` with two explicit legacy
IDs. It only grants group Owner; it does not convert credentials, overwrite
variables, or delete resources. Keep the feature WI pair where it belongs,
cut over source references to the intended Dev WI pair, and retire obsolete
IDs only after acceptance/reference review and explicit deletion approval.

If an affected Environment's two ID variables still name legacy SP-runtime
connections, provisioning correctly rejects them instead of converting those
connections. During an approved cutover, first record the old GUIDs for rollback,
pause deployments, and remove only those stale **variable entries** in GitHub.
Then provision the WI successors and save their IDs. Retain the actual old
connections until the later approved cleanup; deleting a variable is not
permission to delete its Fabric resource. Run only the reviewed WI-consuming
publisher revision after the cutover.
