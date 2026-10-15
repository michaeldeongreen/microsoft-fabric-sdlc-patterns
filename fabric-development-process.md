**English** | [Español](translations/es/fabric-development-process.md)

# Development Process

This guide owns the developer workflow from Dev Branch Out through the
feature-to-Dev handoff. Dev-to-Test and Test-to-`main`/Prod promotion belongs
in [Release Process](fabric-release-process.md).

This repository uses Git-connected Branch Out workspaces for feature
development. It does not publish into those workspaces with fabric-cicd.

## The developer workflow

The normal Copilot-assisted cycle uses two skills:

> After Branch Out:
> [`/swap-to-feature`](.github/skills/swap-to-feature/SKILL.md); before the PR
> to Dev: [`/swap-to-dev`](.github/skills/swap-to-dev/SKILL.md).

Without Copilot, follow the [Standalone CLI](#standalone-cli) workflow.

The complete flow is:

1. Start from an updated Dev workspace and current `dev` branch.
2. Branch Out to a feature branch and workspace.
3. A workspace administrator creates the feature Workspace Identity and two
   Workspace Identity-authenticated connections.
4. Record the workspace and connection GUIDs in the developer's `.env`.
5. Run `/swap-to-feature`. It validates the existing resources, discovers the
   feature Lakehouse/model IDs, and rewrites local physical references.
6. Commit/push, update the feature workspace from Git, activate its Variable
   Library value set, and test.
7. Run `/swap-to-dev`. It restores canonical Dev references offline and runs
   readiness checks.
8. Commit/push and open the PR to `dev`.
9. After merge, the named Dev workspace operator selects **Update all** and
   runs the Dev Fabric DataPipeline manually.

Neither skill commits, pushes, updates Fabric, activates a value set, or runs
the DataPipeline.

## Prerequisites

The developer needs:

- a local clone with Python 3.10 or later and the development requirements;
- their own GitHub/Fabric Git credential;
- Azure CLI access to the approved tenant for feature-resource validation;
- permission to Branch Out and create or use the feature workspace;
- Contributor or the required item permissions in the feature workspace;
- a feature Workspace Identity with the required workspace/resource access;
  and
- User access to the feature connections if the developer did not create them.

The feature workspace administrator needs permission to create the Workspace
Identity and its connections. Developers do not need the deployment service
principal's credentials or the GitHub Environment-variable PAT.

## 1. Branch Out from Dev

Use Fabric's current
[Branch-out operation](https://learn.microsoft.com/en-us/fabric/cicd/git-integration/branched-workspace#branch-out-operation):

1. Confirm Dev is updated from Git and contains no pending workspace changes.
2. In the Dev **Source control** pane, select **Branch out**.
3. Create a feature branch from `dev` and a dedicated feature workspace.
4. Include all repository items for this workflow. Do not use selective
   branching unless you have reviewed every dependency.
5. Do not choose a native Deployment Plan for the branch operation. The
   committed plan in this repository is read by optional API publisher
   adapters; it is not the Branch Out mechanism.
6. Review the warning for existing target workspaces: uncommitted items can be
   deleted.
7. Complete Branch Out and wait for the feature workspace to synchronize.

The workspace is now Git-connected to the feature branch. Git synchronization
copies supported definitions, but it does not create the feature Workspace
Identity, connections, permissions, or capacity assignment.

See the current
[Branch Out limitations](https://learn.microsoft.com/en-us/fabric/cicd/git-integration/branched-workspace#branching-out-limitations)
before changing workspace settings or using a pre-existing workspace.

## 2. Create the feature runtime connections

This step is human-owned. `/swap-to-feature` does not create connections or
grant roles.

In the feature workspace:

1. Open **Workspace settings -> Workspace identity** and create the Workspace
   Identity if it does not exist.
2. Open **Manage access** and grant it the Notebook, semantic-model, OneLake,
   and other resource rights required by the feature workload.
3. Open `Patterns_Load_Validate_And_Refresh` in edit mode.
4. For the Notebook activities, create or select one Notebook connection using
   **Workspace Identity** authentication. Both Notebook activities use this
   connection.
5. For the native semantic-model refresh activity, create or select a separate
   Power BI datasets connection using **Workspace Identity** authentication.
6. Save the DataPipeline.
7. Open **Settings -> Manage connections and gateways -> Connections** and
   verify both records:
   - distinct GUIDs;
   - the intended feature workspace;
   - connector types Notebook and Power BI datasets;
   - Workspace Identity authentication; and
   - the required User/Owner sharing.
8. Copy each connection GUID from the connection details/URL into `.env`.

The repository does not guess connections by display-name substring. If your
Fabric UI labels differ, use the connector type, Workspace Identity
authentication, workspace association, and GUID as the acceptance criteria.

## 3. Configure the local feature target

Copy [.env.sample](.env.sample) to `.env` if necessary. `.env` is gitignored.
For the selected feature workspace, set:

| Key | Value |
|---|---|
| `FEATURE_WORKSPACE_ID` | Branch Out workspace GUID |
| `FEATURE_NOTEBOOK_CONNECTION_ID` | Existing Notebook connection GUID |
| `FEATURE_REFRESH_CONNECTION_ID` | Existing Power BI datasets refresh connection GUID |

Clear feature Lakehouse/model values left from another workspace. The
preparation step discovers and records:

| Key | Discovered item |
|---|---|
| `FEATURE_LAKEHOUSE_ID` | `PatternsLakehouse` physical item GUID |
| `FEATURE_SEMANTIC_MODEL_ID` | `Patterns_Semantic_Model` physical item GUID |

Do not substitute `.platform` logical IDs for physical GUIDs.

## 4. Swap to the feature workspace

Check out and update the feature branch:

```powershell
git fetch origin
git checkout <feature-branch>
git pull --ff-only
```

Run [`/swap-to-feature`](.github/skills/swap-to-feature/SKILL.md). Without
Copilot, follow the [standalone feature sequence](#standalone-cli).

For a new feature target, the skill:

1. uses the approved Azure CLI user identity;
2. validates the explicit workspace and both existing connection GUIDs;
3. discovers the exact Lakehouse and semantic model by name;
4. writes the discovered item IDs to `.env`;
5. stops before local rewrites if preparation fails; and
6. runs the offline swap after preparation succeeds.

Preparation uses `mode="existing"`. It performs no connection creation,
permission change, Git operation, or other cloud write.

The offline swap:

- creates a feature value set and adds it to `settings.json`;
- rewrites the semantic model Direct Lake workspace/Lakehouse URL;
- rewrites Notebook META Lakehouse dependencies where present;
- rewrites registered DataPipeline workspace, model, and connection fields;
- retains portable logical IDs;
- detects stale IDs from an earlier feature target; and
- verifies that critical Dev physical IDs are no longer present.

Review the exact diff before committing:

```powershell
git add -A
git commit -m "Swap references to feature workspace"
git push
```

## 5. Update and test the feature workspace

1. In the feature workspace's **Source control** pane, update from Git.
2. Open `Patterns_Variables` and activate the feature value set.
3. Inspect the DataPipeline:
   - both Notebook activities use the feature Notebook connection;
   - the refresh activity uses the feature refresh connection;
   - physical workspace/model IDs belong to the feature workspace.
4. Inspect the semantic model and attached-Notebook Lakehouse bindings.
5. Run `Patterns_Load_Validate_And_Refresh`.
6. Confirm:
   - load completed;
   - read-only validation completed;
   - native refresh completed;
   - required date fields and calculations behave as expected;
   - the report renders; and
   - any required Ontology, Data Agent, and consumer checks pass.

`minimum_patient_count` comes from the active Variable Library as a positive
Integer. `run_label` is an independent String with default `manual`.
Validation success is not proof of DAX, model ownership, report access, or
consumer authorization.

## 6. Restore Dev before the PR

Run [`/swap-to-dev`](.github/skills/swap-to-dev/SKILL.md). CLI:
`python scripts\workspace_swap.py --swap-to-dev`. The operation is offline:

- no Azure or GitHub authentication;
- no Actions artifacts;
- no provisioning workflow dispatch;
- no connection or permission changes; and
- no Fabric update.

It removes the feature value set, restores canonical Dev workspace/Lakehouse/
model/connection references, and runs the same readiness checks used by CI.
The skill checks readiness automatically. CLI users also run
`python scripts\workspace_swap.py --check-ready`.

Review the result:

```powershell
git diff
git add -A
git commit -m "Restore Dev references before merge"
git push
```

Open a PR to `dev`. Configure these required checks:

- `Check for non-dev IDs in Fabric items`
- `Run unit tests`

The readiness check verifies:

- canonical Dev workspace/Lakehouse/model/connection references;
- no feature value-set files;
- no known feature physical IDs in registered files; and
- consistent parameter-rule baselines.

## 7. Update and validate Dev

After the PR merges:

1. In Dev, open **Source control**.
2. Review the incoming definitions and select **Update all**.
3. Wait for synchronization to complete.
4. Inspect the canonical Dev DataPipeline and semantic-model bindings.
5. Run `Patterns_Load_Validate_And_Refresh`.
6. Review the three activities, model fields/calculations, report, and any
   required workload acceptance evidence.

Dev is intentionally manual. A merge does not update the workspace or run the
DataPipeline.

The next step is a reviewed `dev` to `test` promotion. Follow
[Release Process](fabric-release-process.md#dev-to-test).

## Copilot skills

The repository ships:

| Skill | Purpose |
|---|---|
| [/swap-to-feature](.github/skills/swap-to-feature/SKILL.md) | Validate/record a known feature target, then apply the local feature swap |
| [/swap-to-dev](.github/skills/swap-to-dev/SKILL.md) | Restore canonical Dev references offline and check readiness |
| [/swap-to-feature-dryrun](.github/skills/swap-to-feature-dryrun/SKILL.md) | Preview known feature swaps without authentication or writes |
| [/swap-to-dev-dryrun](.github/skills/swap-to-dev-dryrun/SKILL.md) | Preview Dev restoration without authentication or writes |
| [/prepare-feature-workspace](.github/skills/prepare-feature-workspace/SKILL.md) | Run preparation/validation without applying the swap |
| [/prepare-dev-workspace](.github/skills/prepare-dev-workspace/SKILL.md) | Record an approved Dev baseline cutover |

The dry-run skills do not create missing resources or apply the swap. A skill
invocation is the request to run it; normal validation failures remain visible.

## Standalone CLI

The scripts remain usable without Copilot.

Prepare and swap a new feature target:

```powershell
az login --tenant <tenant-guid> --use-device-code
az account show --query tenantId --output tsv
python scripts\prepare_fabric_workspace.py --feature --use-azure-cli
python scripts\workspace_swap.py
```

Confirm that the reported tenant is the approved tenant. Do not print or copy
access tokens. The direct swap displays the planned changes and waits for
literal `YES`.

Restore Dev:

```powershell
python scripts\workspace_swap.py --swap-to-dev
python scripts\workspace_swap.py --check-ready
```

Record a deliberate Dev resource cutover:

```powershell
python scripts\prepare_fabric_workspace.py --dev --replace-dev-bindings
```

This command is for initial setup or an approved canonical-resource change,
not an ordinary return from feature work.

## Why the swap is required

Branch Out copies Git-supported definitions into the feature workspace. Some
definitions contain physical environment references that remain pointed at
Dev:

- semantic model Direct Lake workspace/Lakehouse URLs;
- Notebook META Lakehouse dependencies; and
- DataPipeline workspace, model, and connection GUIDs.

A feature pipeline must never refresh Dev. `workspace_swap.py` rewrites only
registered physical references and creates/removes the feature Variable
Library value set.

Portable `.platform` logical IDs, such as Ontology-to-Lakehouse and Data
Agent-to-Ontology references, are resolved in the current workspace and do not
need a physical-ID swap.

## Why fabric-cicd is not used for feature workspaces

This repository uses two different update models:

| Workspace | Source of definitions |
|---|---|
| Dev and feature | Fabric Git |
| Test and Prod | Selected API publisher |

Publishing with fabric-cicd into a Git-connected feature workspace can create
drift between Fabric and Git. The next Git update can overwrite the API
publication or produce conflicts.

A non-Git-connected short-lived feature workspace deployed by CI is a valid
alternative architecture, but it is not the workflow implemented here.

## Metadata registry

The swap script uses an item-type registry. Add a registry entry for a new
item type when existing rewrite strategies cover its physical fields. New
physical reference shapes also require baseline/configuration mappings and
regression tests.

| Item type | Physical or logical references | Swap behavior |
|---|---|---|
| SemanticModel | Physical workspace/Lakehouse URL | Rewritten and restored |
| Notebook with attached Lakehouse | Physical workspace/Lakehouse META fields | Rewritten and restored |
| DataPipeline | Physical workspace/model/connection fields plus portable logical notebook references | Registered physical fields rewritten and restored |
| VariableLibrary | Stage/feature value sets | Feature value set created/removed |
| Ontology | Portable Lakehouse logical ID | Validated, not rewritten |
| DataAgent | Portable Ontology logical ID | Validated, not rewritten |
| DeploymentPlan | Portable item logical IDs | Not rewritten |

Key implementation files:

| File | Role |
|---|---|
| [workspace_swap.py](scripts/workspace_swap.py) | Offline physical-reference swap and readiness check |
| [prepare_fabric_workspace.py](scripts/prepare_fabric_workspace.py) | Feature validation/discovery and explicit Dev baseline recording |
| [pipeline_bindings.py](scripts/pipeline_bindings.py) | Registered DataPipeline physical fields |
| [parameter.yml](data/fabric/parameter.yml) | fabric-cicd target substitutions and canonical Dev baselines |
| [bulk-parameter.yml](data/fabric/bulk-parameter.yml) | Raw REST substitutions and canonical Dev baselines |

## Feature cleanup

After the feature PR is merged and updated Dev is accepted:

1. The feature developer records the feature workspace, Workspace Identity,
   and exact connection GUIDs, then confirms no source definition, variable, or
   active pipeline references them.
2. Retain the required evidence and obtain deletion approval.
3. The connection administrator deletes the two tenant-level feature
   connections while their workspace/identity context can still be verified.
4. The workspace administrator deletes the feature workspace and records the
   resulting Workspace Identity lifecycle. Do not assume workspace deletion
   cleans up tenant-level connections.
5. The repository administrator deletes the feature branch when retention and
   recovery policy permit it.
6. The developer clears the five feature values from local `.env` before
   selecting another workspace.

Source cleanup performed by `/swap-to-dev` is not permission to delete Fabric
resources. See [Setup: Cleanup](SETUP.md#cleanup) for full sample teardown.

## References

- [fabric-cicd Git flow](https://microsoft.github.io/fabric-cicd/latest/how_to/deployment_overview/#git-flow)
- [Fabric Branch-out operation](https://learn.microsoft.com/en-us/fabric/cicd/git-integration/branched-workspace#branch-out-operation)
- [Fabric Branch Out limitations](https://learn.microsoft.com/en-us/fabric/cicd/git-integration/branched-workspace#branching-out-limitations)
- [Fabric Git integration best practices](https://learn.microsoft.com/en-us/fabric/cicd/best-practices-cicd)
- [Notebook activity with Workspace Identity](https://learn.microsoft.com/en-us/fabric/data-factory/notebook-activity#using-fabric-workspace-identity-wi-in-the-notebook-activity)
- [Manage Fabric connections](https://learn.microsoft.com/en-us/fabric/data-factory/data-source-management)
