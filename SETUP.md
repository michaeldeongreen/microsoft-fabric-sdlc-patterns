# Set Up This Repository

This guide takes an independent fork from empty workspaces to a working
`dev -> test -> main` promotion flow. It assumes familiarity with Azure and
GitHub, but no prior Microsoft Fabric setup experience.

The steps below use **fabric-cicd non-bulk**, this repository's default and
recommended starting point.
[fabric-cicd](https://microsoft.github.io/fabric-cicd) is the Python library
that publishes the items. Use the
[fabric-cicd Non-Bulk CI/CD Guide](fabric-hybrid-cicd-guide.md) for the default
implementation and the [four-method comparison](README.md#choose-a-deployment-method)
to evaluate alternatives for specific workload requirements. This starting
point does not require native Fabric Deployment Pipelines or a Deployment Plan.
The [shared workflow reference](fabric-hybrid-cicd-guide.md#github-actions-workflows)
explains each caller, trigger, template, and runner.

## What You Will Build

| Branch | Fabric workspace | Update method |
|---|---|---|
| `dev` | Development | Fabric Git integration |
| `test` | Test | GitHub Actions and fabric-cicd non-bulk |
| `main` | Production | GitHub Actions and fabric-cicd non-bulk |

Only the Dev workspace is connected to Git. Test and Production receive
deployments after pull requests are merged through `dev -> test -> main`.

After publication, GitHub starts one `Patterns_Load_Validate_And_Refresh`
DataPipeline: the existing loader → read-only validation → native model refresh.
This workload pipeline is not a native Fabric Deployment Pipeline for promoting
workspace content.

The existing loader writes demonstration tables. Use workspaces dedicated to
this sample; do not run it against business Production data.

> **Verification boundary:** An earlier feature prototype completed all three
> activities and a `run_label` API override with Workspace Identity activity
> credentials under a user invoker. The current explicit-OneLake-path validation
> revision is only offline-validated. Git sync/Branch Out binding resolution, CI
> service-principal publication/start, and Test/Prod end-to-end execution remain
> live checks; complete them in your approved target before promotion.

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
- A workspace administrator who can grant the default SP Contributor access;
  optional Workspace Identity setup needs the additional bootstrap rights.
- A Fabric administrator who can enable Git integration, GitHub integration,
  and service-principal API/connection-creation access for the appropriate security
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
| `microsoft-fabric-sdlc-patterns-dev` | Yes, to `dev` | Contributor for automated Git sync and pipeline execution |
| `microsoft-fabric-sdlc-patterns-test` | No | Contributor |
| `microsoft-fabric-sdlc-patterns-prod` | No | Contributor |

Open each workspace and copy its ID from the browser URL. In a URL such as
`https://app.fabric.microsoft.com/groups/<workspace-id>/...`, the GUID after
`/groups/` is the workspace ID. See
[Find your Microsoft Fabric workspace ID](https://learn.microsoft.com/fabric/data-factory/upgrade-pipelines-how-to-find-your-fabric-workspace-id).

In all three workspaces, open `Manage access`, add the service
principal by its name or application/client ID, and assign the `Contributor`
role.

### Post-ETL Refresh Permissions

The default sample uses the **same approved service principal** for publication,
job submission, and the two activity connections. The API bootstrap discovers
or creates a Notebook connection and a Power BI datasets connection, using
`ServicePrincipal` credentials from the existing Azure environment secrets.
It retains their GUIDs and PATCHes credentials during repeat reconciliation,
so rotating the GitHub client secret does not leave old Fabric credentials.
No manual connection creation, selection, or GUID copying is required.

Authorize the principal through both **Service principals can call Fabric
public APIs** and **Service principals can create workspaces, connections, and
deployment pipelines**, scoped to the approved tenant group. Contributor is
sufficient for this default workspace workload; the principal owns the cloud
connections it creates. It does not grant itself workspace Admin or alter
tenant settings.

This is a **sample simplification, not an enterprise identity recommendation**:
deployment and runtime authority are shared, and Fabric stores a runtime copy
of the client secret. See the [privilege trade-off and enterprise alternatives](fabric-cicd-governance-considerations.md#automated-connection-setup-the-samples-privilege-trade-off).

For an optional secretless activity identity, set
`FABRIC_RUNTIME_AUTHENTICATION=WorkspaceIdentity`. The helper provisions the
workspace's identity if absent and ensures its local Contributor assignment.
Initial provisioning needs Admin; inspecting/granting workspace roles needs
Member or Admin. Applicable tenant trust for the new identity must already be
approved. The existing feature workspace keeps its working Workspace Identity
connections; neither this alternative nor the default changes those resources
unless its preparation command is explicitly invoked.

For a separate bootstrap identity, provision and share the connections with
the routine publisher, then select the read-only
[existing-connections mode](#environment-variables). Connection GUIDs are
non-secret references; tokens and credentials are never written to the Dev
manifest, pipeline JSON, or parameter files. See [Notebook identity setup](https://learn.microsoft.com/en-us/fabric/data-factory/notebook-activity)
and [native refresh settings](https://learn.microsoft.com/en-us/fabric/data-factory/semantic-model-refresh-activity).

Also verify:

- The **model owner** has source access independently of the refresh caller.
  For Direct Lake on OneLake, verify *Read* plus *ReadAll* or the applicable
  OneLake security roles for the source tables. Direct Lake checks owner
  authorization regardless of who initiates refresh. See
  [Direct Lake owners](https://learn.microsoft.com/en-us/fabric/fundamentals/direct-lake-security-integration#direct-lake-owners).
- The model's effective source/connection identity is also authorized.
  Verify the intended SSO or supported fixed-identity configuration; do not
  replace SSO merely to make the workflow pass. See
  [Direct Lake security and connections](https://learn.microsoft.com/en-us/fabric/fundamentals/direct-lake-security-integration).
- The target is on an active capacity that supports enhanced refresh.

The native activity's documentation limits it to models you create yourself.
Verify ownership and permissions for the model **after CI deployment**; the
feature run does not prove the service-principal-deployed model case.
Successful user authoring or job submission does not prove CI publication/start.
Successful refresh is not evidence of
the report user's query permissions.

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

   Keep `Default` active in the Dev workspace. Keep `minimum_patient_count` a
   positive **Integer**; the sample baseline is `5` in Default, Test, and Prod.
   Environment policies need not differ artificially.
2. Open `Import_Patterns_Data`, select `Lakehouse` in its toolbar, and set the
   default to the Dev `PatternsLakehouse`. `Validate_Patterns_Data` does not need
   an attached Lakehouse: like `Patterns_Demo`, it reads the active Variable
   Library's workspace and Lakehouse IDs and loads Delta tables from their
   explicit OneLake `abfss://.../Tables/dbo/...` paths.
3. Open `Patterns_Semantic_Model`, edit its Direct Lake connection, and select
   the Dev `PatternsLakehouse`.
4. Keep the pipeline's portable notebook logical references and library binding.
   Its physical model/connection references are set by the automated Dev
   preparation command below, not by manually selecting connections in the UI.

Save the Fabric items, then use the Dev workspace `Source control` pane to
commit them to `dev`. Do not change any `.platform` `logicalId` values.

Pull that commit locally. In `data/fabric/parameter.yml`, replace every
reference-environment `find_value` with the corresponding Dev ID you recorded:
use the Dev Lakehouse ID for Lakehouse rules and the Dev workspace ID for
workspace rules. When making this migration on a feature branch, invoke
`/swap-to-dev`: it detects the uninitialized Dev baseline, performs API
preparation through your approved Azure CLI user session, and restores the
source references. No separate preparation or readiness skill is needed.

During initial fork setup directly on Dev without a feature value set, use
the existing explicit CLI convenience:

```powershell
python scripts\prepare_fabric_workspace.py --dev --use-azure-cli --swap-to-dev
```

The existing Dev model must be present. The command resolves that model and
both activity connections automatically, records non-secret canonical IDs in
[fabric-dev-bindings.json](data/fabric-dev-bindings.json), aligns both parameter
files, and applies the Dev bindings through the existing swap path. On a
feature branch it also removes the feature value set. On later feature
branches, `/swap-to-dev` uses the saved baseline offline and verifies readiness
automatically. GitHub repeats the check on the PR to Dev; the script's
`--check-ready` option remains available for local diagnostics.
No Python constants, connection GUIDs, or pipeline UI bindings need manual edits.
Use `--dry-run` for an offline preview; it never loads credentials or calls Fabric.
The initial null manifest deliberately fails readiness until setup has run.
Local API setup reuses a valid Azure CLI session or signs in with device code.
The default SPN activity credentials and Actions connection-management rights
are separate prerequisites: user sign-in does not supply them. Do not put a
device-code prompt in unattended Actions.
See the [decision table and guided steps](fabric-development-process.md#the-solution-workspace_swappy)
for when preparation is needed versus an ordinary offline swap.
If you intend to evaluate the raw Bulk API path, make the
equivalent changes in `data/fabric/bulk-parameter.yml`.

Commit and push the parameter-file changes to `dev`. Search `data/fabric` for
the original IDs from the current `find_value` entries and confirm that no
unintended references remain. Do not replace `.platform` `logicalId` values;
they are portable item references, not environment IDs.

The Test and Production value sets do not define Lakehouse IDs. They inherit the
Dev Lakehouse ID from the base variables as a placeholder. During deployment,
`parameter.yml` replaces it with the ID of the `PatternsLakehouse` created in
the target workspace.

After the generated source changes are reviewed and submitted through the
normal Git process, Dev Git sync reapplies real, stable bindings. It does not
evaluate parameter files, provision connections, or require recurring UI
rebinding. A deleted canonical Dev connection fails explicitly; deliberately
regenerate it with `--replace-dev-bindings` and review the corresponding source
change rather than silently introducing workspace/Git drift.

### Automated Dev Sync Policy

[sync-dev.yml](.github/workflows/sync-dev.yml) runs after qualifying merges into
`dev`, using the `Dev` Environment and its own read-only GitHub credential
connection. It validates the committed manifest/source, connected repository,
`dev` branch, folder, and exact triggering SHA. It never reconnects the workspace,
initializes from the wrong direction, commits to Git, or replaces canonical
connection GUIDs.

The sample treats Dev as an **integration workspace**, with authoring in feature
workspaces. Its workflow explicitly selects `source-authoritative` policy:
only definition modifications to the existing, baseline-managed Semantic Model
may be restored. For incoming conflicts it uses the documented remote
resolution; for outgoing-only model changes it re-applies the canonical
definition to the same item ID. Unrelated edits, additions/deletions, or platform
metadata changes fail. This addresses possible refresh-generated model diffs
without a bot commit or an invented metadata-normalization rule.

The final Git status must be clean and both heads must match the target commit
before the pipeline job starts. Whether canonical definition replacement clears
every refresh-generated diff still requires live acceptance; residual drift
fails visibly. For a shared human-authoring Dev workspace, set
`DEV_GIT_SYNC_POLICY=strict`: it refuses all outgoing edits/conflicts instead
of discarding the managed model's edits. Approvals and this policy do not elevate
Fabric permissions.

Run `Patterns_Load_Validate_And_Refresh` only after those bindings are correct,
wait for all three activities, then query the model's required date fields and
check the report. The loader remains independently runnable for diagnostics;
running it alone does not execute validation or model refresh.

## 5. Configure GitHub

### Environment Secrets

In **Settings > Environments**, create environments named exactly `Dev`, `Test`,
and `Prod`. Add these environment-scoped secrets to each; these are not repository
variables:

| Secret | Value |
|---|---|
| `AZURE_TENANT_ID` | Entra tenant ID |
| `AZURE_CLIENT_ID` | Service-principal application/client ID |
| `AZURE_CLIENT_SECRET` | Service-principal client secret |
| `FABRIC_WORKSPACE_ID` | The corresponding Dev, Test, or Production workspace ID |

Dev Git automation additionally needs a repository-scoped, fine-grained PAT
with **Contents: Read**, supplied as `FABRIC_GITHUB_TOKEN` for first-time
Git credential connection creation. The SP uses its own Fabric
`ConfiguredConnection`; it does not inherit the human Git credential.
After creation, that connection can be reused without resupplying a PAT.
An approved precreated connection can instead be supplied through the non-secret
`FABRIC_GIT_CONNECTION_ID` variable. PAT expiry/rotation remains an operational
responsibility. The temporary Actions `GITHUB_TOKEN` is not substituted for the
documented PAT authentication.

For `Prod`, require a deployment reviewer and restrict deployments to `main`.

These workflows use client-secret authentication. OIDC is a recommended
production option to evaluate, not the authentication implemented by this
setup; see [Governance](fabric-cicd-governance-considerations.md).

### Shared ETL Follow-up

Every deployment caller's dependent ETL job selects `Patterns_Load_Validate_And_Refresh` with
`item_type: DataPipeline` and `job_type: Pipeline`. GitHub runs and polls that
job only; native refresh has one owner inside Fabric, with no external refresh
step or runtime fallback.

The optional `run_label` input defaults to `manual`. CI supplies a non-secret
stage/run label through `RUN_LABEL`; the runner serializes it into
`executionData.parameters` without executable-source interpolation. The
pipeline forwards it to validation. `minimum_patient_count` comes separately
from the active Variable Library, not a GitHub secret or per-run label.
All four deployment methods share the
[pipeline contract](fabric-hybrid-cicd-guide.md#post-etl-semantic-model-refresh).

### Environment Variables

The default needs **no connection GUID variables**. Every publisher runs the
same idempotent connection bootstrap before any pipeline publication.
It supplies the following in memory:

| Variable | Value in each environment |
|---|---|
| `NOTEBOOK_CONNECTION_ID` | Automatically resolved target Notebook connection GUID |
| `SEMANTIC_MODEL_REFRESH_CONNECTION_ID` | Automatically resolved target Power BI datasets connection GUID |

For approved preexisting resources, optionally provide those two non-secret
GitHub Environment variables and set `FABRIC_CONNECTION_MODE=existing`.
This path validates accessible metadata and performs no connection/identity/
credential writes; its owner manages permissions and secret rotation.
Set `FABRIC_RUNTIME_AUTHENTICATION` to the connections' authentication method
(`ServicePrincipal`, the default, or `WorkspaceIdentity`). The automatic path
can also use explicit IDs but manages the chosen runtime credentials.

The deployment runners validate GUIDs and exact Dev source fields before
publishing. The fabric-cicd routes use the exact
`$ENV:NOTEBOOK_CONNECTION_ID` and `$ENV:SEMANTIC_MODEL_REFRESH_CONNECTION_ID`
syntax with environment replacement enabled by the runners; keep fabric-cicd
at `>=1.4.0,<1.5.0`. The raw REST route applies its corresponding
`bulk-parameter.yml` substitutions. Connection lifecycle belongs to the shared
bootstrap, not either publisher's parameter engine. Metadata inspection alone
does not certify runtime ACLs or model-owner access.

### Deployment Method Variables

In **Settings > Secrets and variables > Actions > Variables**, use **New
repository variable** for the nonsecret settings below. Choose one method:

| Method | `DEPLOY_METHOD` | `DEPLOYMENT_PLAN_PATH` |
|---|---|---|
| fabric-cicd non-bulk — default and recommended starting point | `fabric-cicd`, or leave unset | Not used |
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

- Use the four [environment secrets above](#environment-secrets); [connection variables](#environment-variables) are optional in auto mode. `FABRIC_WORKSPACE_ID` must identify the corresponding Test or Prod target.
- Use [parameter.yml](data/fabric/parameter.yml) for fabric-cicd replacements. `DEPLOY_METHOD=bulk` and [bulk-parameter.yml](data/fabric/bulk-parameter.yml) belong to the separate raw REST route.
- No extra GitHub bulk-feature flag is needed: the runner enables the required fabric-cicd feature flags.
- The shipped callers supply `ENVIRONMENT` (`Test`/`Prod`), `REPOSITORY_DIRECTORY` (`data/fabric`), and the eight-type `ITEM_TYPE_IN_SCOPE`, including `DataPipeline`. You do not create additional repository variables for these; customize the workflow inputs if needed.
- For a credentials-free schedule check, use the [bulk preview instructions](fabric-deployment-plan-guide.md#enable-and-preview-bulk).

### Before Switching Methods

Promote the selected workflows and their shared templates through the normal
branch path before switching methods, and wait for in-flight deployments to finish.
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
   by its dependent ETL job on successful publication.
2. Wait for the Test pipeline's load, validation, and native refresh to complete,
   then verify Test before continuing. These completions are not a full release
   validation suite; use the [Quality Gates guide](fabric-cicd-quality-gates-and-release-controls.md)
   to define the evidence required for your workload.
3. Open a pull request from `test` to `main` and merge it. The Production
   workflow then waits for a `Prod` environment reviewer to approve the
   deployment.

Deployment path filters differ by method; documentation-only changes do not
start these deployments. All deployment callers support manual runs on their
proper stage branch; both standalone ETL workflows remain manual recovery tools. See the
[workflow reference](fabric-hybrid-cicd-guide.md#github-actions-workflows) before
trying to rerun a stage.

Deployment and ETL now use a same-revision `needs` chain. The renamed
`Deploy and Run Pipeline` workflow names avoid triggering legacy default-branch
listeners while the change is promoted. An old run still uses its old revision:
start a new dispatch to test changed code, rather than rerunning an old run.

On the first deployment, open the Ontology in each target workspace and bind its
Graph Model to the local Lakehouse tables. See
[Initial Deployment to a Clean Workspace](fabric-hybrid-cicd-guide.md#initial-deployment-to-a-clean-workspace)
for that one-time Fabric UI step and its current workaround.

## 7. Verify the Setup

- Dev Source control reports branch `dev` and no pending changes.
- `Patterns_Variables` resolves the local values in each workspace.
- The loader's attached Lakehouse targets the local `PatternsLakehouse`;
  validation reads that same target through active Library IDs and explicit
  OneLake paths, with no attached Lakehouse.
- Each pipeline's physical model/workspace IDs, runtime connections, and
  resolved Library values target that environment, not Dev or a feature workspace.
- Test and Production are not Git-connected.
- Test and Production contain the `doctors`, `patients`, and `appointments`
  Lakehouse tables after ETL.
- Authorized Test/Production verification shows pipeline load → validation →
  native refresh success, with actual refresh completion—not just job acceptance.
- Validation records the intended minimum and run label; model queries and
  consumer checks provide separate evidence.
- The Semantic Model, report, Ontology, and Data Agent load in each environment.
- Pull requests can promote only through `dev -> test -> main`.

After these checks pass, the platform is ready for feature development. Continue
with the
[Development Process](fabric-development-process.md) for Branch Out,
`workspace_swap.py`, and pull-request readiness checks.

## Troubleshooting Post-ETL Refresh

| Symptom | What to check |
|---|---|
| Job fails or an activity is skipped | Inspect the pipeline job and activity-level diagnostics in Actions/Fabric monitoring. Load failure prevents validation; validation failure prevents refresh. Check the actual failed activity and target bindings. |
| Connection preflight fails | Check the canonical Dev manifest and exact source/rule alignment. Auto mode discovers/creates target connections using the approved SP; existing mode requires both approved GUID variables and matching authentication. Do not use fake markers or feature GUIDs as upper-environment configuration. |
| Validation fails | Inspect the active Library minimum, notebook parameter input, schema/key/reference assertions, and source date types. Do not lower an agreed quality threshold merely to turn the job green. |
| Model is missing or refresh targets another workspace | Check the native activity's physical model/workspace IDs and the deployed replacements. Do not copy a Dev model's physical ID into Test/Prod. |
| Authentication or `401`/`403` failure | Check both tenant API/creation approvals, SP workspace/connection rights, runtime authentication, model ownership/source access, and optional WI trust/roles. User success does not prove CI authorization. |
| Refresh fails or times out | Inspect this pipeline run's native activity output and model refresh history. Check capacity and owner/source access; acceptance, an older successful refresh, or browser reload is not completion. |

A GitHub polling timeout fails the workflow but does not cancel the Fabric
pipeline or any refresh still running. Inspect the **specific run/activity**
and refresh history before retriggering to avoid overlapping operations.

If data is present but fields such as `appointment_date` or `date_of_birth`
show errors, check that native refresh completed **after** load and validation.
Refresh addresses Direct Lake framing, not every possible date-field error.
Still query the model's required fields and verify calculations and report
behavior; source Timestamp checks are not model-query evidence.

For this Direct Lake on OneLake model, refresh frames Delta references; do not
add another ETL, convert storage mode, or wait for a SQL analytics endpoint as
a refresh workaround. Earlier prototype activity success is recorded separately
from the current revision's pending live checks described above.
