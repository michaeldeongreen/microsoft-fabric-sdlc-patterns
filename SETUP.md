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
- A workspace administrator who can provision each required Workspace Identity
  and grant access to its runtime connections.
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

### Post-ETL Refresh Permissions

The CI service principal publishes definitions and starts/polls the Fabric
pipeline job. **It is not automatically the activity identity.** Both Notebook
activities and the native Semantic model refresh activity use separately
configured connections with authorization kind **Workspace Identity**.

Before running in each environment:

1. Provision that workspace's own Workspace Identity in **Workspace settings**.
   Permit the identity through the applicable tenant service-principal settings
   and grant it **Contributor** on the workload workspace. Do not reuse the
   feature workspace's identity in Test or Prod.
2. Create a **Notebook** connection and a **Power BI datasets** connection using
   Workspace Identity authorization. Select the Notebook connection for both
   load and validation; select the Power BI connection for native refresh.
   Verify connection access and tests rather than switching to person-bound
   OAuth to bypass a failure. See [Notebook activity identity setup](https://learn.microsoft.com/en-us/fabric/data-factory/notebook-activity)
   and [native refresh settings](https://learn.microsoft.com/en-us/fabric/data-factory/semantic-model-refresh-activity).
3. Give the CI deployment principal **User** access to both connections.
   Connection sharing grants use; it does not change their activity credentials.
   Verify that the runtime identity can run the notebooks and refresh the
   actual target model on the active capacity.
4. Record each target's connection GUIDs in the two
   [GitHub Environment variables](#environment-variables) below. Connections
   and credentials are runtime prerequisites, not items published from Git.

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
4. Check `Patterns_Load_Validate_And_Refresh` references the local notebooks,
   library, workspace, and model. The native activity embeds a physical model
   ID; record the fork's Dev model ID for the replacement rules below.

Save the Fabric items, then use the Dev workspace `Source control` pane to
commit them to `dev`. Do not change any `.platform` `logicalId` values.

Pull that commit locally. In `data/fabric/parameter.yml`, replace every
reference-environment `find_value` with the corresponding Dev ID you recorded:
use the Dev Lakehouse ID for Lakehouse rules and the Dev workspace ID for
workspace rules, and the Dev model ID for the DataPipeline model rule.
Keep the [workspace-swap pipeline baselines](scripts/pipeline_bindings.py)
aligned with the fork's Dev bindings too; `.env` supplies feature IDs, not a
replacement Dev baseline.
Retain the source connection markers `11111111-1111-4111-8111-111111111111`
(Notebook) and `22222222-2222-4222-8222-222222222222` (refresh): deployments
replace these with target connection variables. They are not usable connections.
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

Before a manual Dev pipeline run, configure its local runtime connections and
select the local model in the Fabric UI. Git synchronization can restore source
connection markers, so recheck bindings after **Update from Git**; an inert
marker is not a ready-to-run Dev connection. Retain the canonical markers in
reviewed source when exporting changes.

Run `Patterns_Load_Validate_And_Refresh` only after those bindings are correct,
wait for all three activities, then query the model's required date fields and
check the report. The loader remains independently runnable for diagnostics;
running it alone does not execute validation or model refresh.

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

### Shared ETL Follow-up

Both ETL callers select `Patterns_Load_Validate_And_Refresh` with
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

In **Settings > Environments > Test / Prod > Environment variables**, add:

| Variable | Value in each environment |
|---|---|
| `NOTEBOOK_CONNECTION_ID` | That workspace's Workspace Identity Notebook connection GUID |
| `SEMANTIC_MODEL_REFRESH_CONNECTION_ID` | That workspace's Workspace Identity Power BI datasets connection GUID |

These are non-secret **Environment variables**, not repository-wide variables
or additional secrets. The deployment runners validate their GUIDs before
publishing and replace source markers. The fabric-cicd routes use the exact
`$ENV:NOTEBOOK_CONNECTION_ID` and `$ENV:SEMANTIC_MODEL_REFRESH_CONNECTION_ID`
syntax with environment replacement enabled by the runners; keep fabric-cicd
at `>=1.4.0,<1.5.0`. The raw REST route applies its corresponding
`bulk-parameter.yml` substitutions. Neither mechanism creates the connections
or proves their authorization.

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

- Use the four [environment secrets above](#environment-secrets) and both [connection variables](#environment-variables); `FABRIC_WORKSPACE_ID` must identify the corresponding Test or Prod target.
- Use [parameter.yml](data/fabric/parameter.yml) for fabric-cicd replacements. `DEPLOY_METHOD=bulk` and [bulk-parameter.yml](data/fabric/bulk-parameter.yml) belong to the separate raw REST route.
- No extra GitHub bulk-feature flag is needed: the runner enables the required fabric-cicd feature flags.
- The shipped callers supply `ENVIRONMENT` (`Test`/`Prod`), `REPOSITORY_DIRECTORY` (`data/fabric`), and the eight-type `ITEM_TYPE_IN_SCOPE`, including `DataPipeline`. You do not create additional repository variables for these; customize the workflow inputs if needed.
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
2. Wait for the Test pipeline's load, validation, and native refresh to complete,
   then verify Test before continuing. These completions are not a full release
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

During rollout, GitHub reads `workflow_run` listeners from the default branch
(`main` here). Until the new caller/template reaches main, an automatic Test
listener can still use the old notebook-only definition. After old automatic
runs finish, manually dispatch **ETL - Test** with branch **test** to validate
the reviewed revision. Rerunning an old main run does not select that revision.
Moving deployment and ETL into one stage with `needs` is a separate follow-up;
the Fabric pipeline does not fix this listener coupling.

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
| Connection preflight fails | Set both target Environment variables to real connection GUIDs. Source markers and a feature connection are not Test/Prod prerequisites. Verify sharing with the CI principal and the connection's Workspace Identity credentials. |
| Validation fails | Inspect the active Library minimum, notebook parameter input, schema/key/reference assertions, and source date types. Do not lower an agreed quality threshold merely to turn the job green. |
| Model is missing or refresh targets another workspace | Check the native activity's physical model/workspace IDs and the deployed replacements. Do not copy a Dev model's physical ID into Test/Prod. |
| Authentication or `401`/`403` failure | Separate CI publication/job-start access from activity connection access. Check the tenant allow-list, Workspace Identity permissions, model ownership/source access, and effective connection identity; user success does not prove CI authorization. |
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
