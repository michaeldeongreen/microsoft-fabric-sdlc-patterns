# Release Process

This guide explains how a reviewed change moves from Dev to Test and then to
the `main` branch and Prod. It applies to all four deployment methods shipped
by this repository.

Use:

- [Setup](SETUP.md) to configure a new fork and its environments.
- [Development Process](fabric-development-process.md) for Branch Out,
  feature testing, return to Dev, and the manual Dev update.
- The method guides for publisher-specific behavior:
  [fabric-cicd non-bulk](fabric-hybrid-cicd-guide.md),
  [Deployment Plan adapters](fabric-deployment-plan-guide.md), and
  [raw REST bulk](fabric-bulk-cicd-guide.md).

## Branch, workspace, and Environment mapping

| Git branch | Fabric stage | GitHub Environment | How definitions arrive |
|---|---|---|---|
| `dev` | Dev workspace | `Dev` | A named Dev workspace operator selects **Update all** |
| `test` | Test workspace | `Test` | The selected GitHub Actions deployment method |
| `main` | Prod workspace | `Prod` | The selected GitHub Actions deployment method |

The `main` branch targets Prod; the branch itself is not a Fabric environment.
Only Dev is Git-connected. Test and Prod receive API-based publication.

## Who is responsible

| Actor | Responsibility |
|---|---|
| GitHub repository administrator | Rulesets, Environments, secrets/variables, deployment-method selection, PAT lifecycle, and manual Dev provisioning dispatch |
| Dev workspace operator | Dev update from Git, binding inspection, and manual DataPipeline run |
| GitHub Actions | Runs the reviewed release revision and enforces the job dependency order |
| Deployment service principal | Ensures Test/Prod connections, manages their connection ACLs, publishes definitions, and submits Fabric jobs |
| GitHub Environment-variable PAT | Reads and creates the two connection-ID variables during release preflight and persistence |
| Fabric Workspace Identity | Authenticates Notebook and semantic-model refresh activities at runtime |
| Connections-admin group | Receives verified Owner access to the two stage connections |
| Release verifier and Prod reviewer | Accepts Test evidence and authorizes Prod where Environment protection is configured |

One person can hold several human roles in a sample fork. [Setup](SETUP.md)
owns the complete administrator/prerequisite model; this table covers release
operation.

GitHub Actions is the orchestrator, not an identity. Its Fabric calls use the
deployment service principal. Its GitHub Environment-variable calls use the
PAT. Fabric activities use the target workspace's Workspace Identity.

## Lifecycle at a glance

1. A developer Branches Out from Dev. A feature workspace administrator creates
   the Workspace Identity and connections; the developer swaps references and
   validates the workspace.
2. Before the PR, the developer restores canonical Dev references and passes
   the readiness check.
3. After the feature PR merges to `dev`, the named Dev workspace operator
   updates from Git and runs `Patterns_Load_Validate_And_Refresh` manually.
4. A reviewed `dev` to `test` PR merges. The selected Test job ensures the
   Test connection pair, publishes definitions, and runs the same-revision
   Fabric DataPipeline.
5. The team validates Test. A green publication job is necessary but does not
   replace workload, model, report, and consumer acceptance.
6. A reviewed `test` to `main` PR merges. The selected Prod job uses the same
   technical sequence with Prod-scoped configuration and any configured
   protection.

## Feature work and the Dev handoff

The complete feature workflow belongs in
[Development Process](fabric-development-process.md). Its release handoff is:

1. Run [`/swap-to-dev`](.github/skills/swap-to-dev/SKILL.md). CLI:
   `python scripts\workspace_swap.py --swap-to-dev`.
2. Review the exact changes. The skill checks readiness automatically; CLI
   users also run `python scripts\workspace_swap.py --check-ready`.
3. Commit and push the restored feature branch.
4. Open a PR to `dev`.
5. Require `Check for non-dev IDs in Fabric items` and `Run unit tests`.
6. After merge, update Dev manually from Fabric Git.
7. Run the Dev Fabric DataPipeline and review its results.

There is no push-triggered Dev publication or automatic Dev DataPipeline run.
Dev connection provisioning is also a separate manual setup action.

## Dev to Test

Before opening the promotion PR:

- Dev must contain the reviewed definitions that were actually updated and
  exercised in the Dev workspace.
- `DEPLOY_METHOD` must be unset for the default publisher or set to a supported
  value.
- The Test workspace, Workspace Identity, resource permissions, GitHub
  Environment, deployment credentials, PAT, and connections-admin group must
  already be configured.
- No other Test or Prod release should be using a selector or shared
  configuration that is being changed.

Open a PR from `dev` to `test`. GitHub runs:

- `Enforce promotion path`
- `Run unit tests`

After merge, all four Test caller workflows can appear in Actions, but only the
workflow matching `DEPLOY_METHOD` runs its deployment job. The others are
expected to show skipped jobs.

The selected job performs this sequence:

1. Validate the selected stage/ref, required configuration, GitHub Environment
   access, and any saved connection IDs.
2. Authenticate to Fabric with the deployment service principal.
3. Validate the pre-existing Test Workspace Identity.
4. Create or reuse the Test Notebook and Power BI datasets refresh connections
   with Workspace Identity authentication.
5. Grant or upgrade the configured connections-admin group to Owner on both
   connections and verify the role by reading it back.
6. Create missing `NOTEBOOK_CONNECTION_ID` and
   `SEMANTIC_MODEL_REFRESH_CONNECTION_ID` Environment variables, then verify
   them. A different existing value is an error and is never overwritten.
7. Pass the current run's resolved IDs directly to the publisher. The
   publisher revalidates and consumes the pair in
   `existing`/`WorkspaceIdentity` mode.
8. Publish with the selected deployment method.
9. If publication succeeds, start and poll the same revision's
   `Patterns_Load_Validate_And_Refresh` Fabric DataPipeline.

The complete deployment job is not read-only: its connection prelude can
create connections, change connection-role assignments, and create GitHub
Environment variables. Only the publisher substep treats connections as
existing read-only dependencies.

## Test to `main` and Prod

Open a PR from `test` to `main` only after the Test candidate has the required
technical and business evidence. The same promotion-path and unit-test checks
run before merge.

The Prod release follows the same technical contract as Test:

1. Prod-scoped preflight
2. Prod connection ensure and Owner verification
3. Create-only Prod ID persistence
4. Selected publication method
5. Same-revision Prod Fabric DataPipeline

The differences are the source/target branch, GitHub Environment, workspace,
Workspace Identity, connections, secrets, run label, and any configured Prod
reviewers or deployment-branch rules.

The repository does not create GitHub Environment protection. Configure the
Prod reviewer and deployment branch policy before the first Prod promotion.
Do not describe a recommendation as an already configured control.

## Connection lifecycle by stage

| Stage | Who creates the Workspace Identity and grants resource access | Who creates the connections | How definitions arrive |
|---|---|---|---|
| Feature | A Fabric workspace administrator | A feature workspace/connection administrator creates the pair; preparation only validates it | Fabric Git in the Branch Out workspace |
| Dev | A Fabric workspace administrator | A GitHub repository administrator manually runs **Provision Fabric Connections** | The named Dev workspace operator selects **Update all** |
| Test | A Fabric workspace administrator | The selected Test deployment job ensures the pair | Selected API publisher |
| Prod | A Fabric workspace administrator | The selected Prod deployment job ensures the pair | Selected API publisher |

Automatic connection ensuring does not:

- create or provision a Workspace Identity;
- assign workspace, model, or OneLake permissions;
- create groups or manage group membership;
- change tenant settings or Conditional Access;
- create credentials;
- approve a release; or
- delete legacy connections.

Manual Test/Prod runs of **Provision Fabric Connections** are recovery,
migration, or diagnostic tools. They are not required in the normal first
release path.

## GitHub Actions workflows

### What triggers what

| Event | Result |
|---|---|
| PR to `dev` | Dev-reference readiness and unit tests |
| PR to `test` or `main` | Promotion-path enforcement and unit tests |
| Push to `test` | Test callers evaluate `DEPLOY_METHOD`; one selected method deploys and then runs the DataPipeline |
| Push to `main` | Prod callers evaluate `DEPLOY_METHOD`; one selected method deploys and then runs the DataPipeline |
| Manual Test dispatch | Must use branch `test` |
| Manual Prod dispatch | Must use branch `main` and any configured Prod protection |
| Change only `DEPLOY_METHOD` | No deployment until a qualifying push or manual dispatch occurs |
| Documentation-only change | No deployment unless a watched implementation path also changed |

An unknown nonempty `DEPLOY_METHOD` value selects no deployment job. Do not use
that behavior as an undocumented release control.

### Pull-request checks

| Workflow | Trigger | Purpose |
|---|---|---|
| [check-pr-ready.yml](.github/workflows/check-pr-ready.yml) | PR into `dev` | Requires canonical Dev references and no stray feature value sets |
| [run-tests.yml](.github/workflows/run-tests.yml) | Every PR | Runs the pytest suite |
| [enforce-promotion-path.yml](.github/workflows/enforce-promotion-path.yml) | PR into `test` or `main` | Requires `dev` to `test` and `test` to `main` |

Rulesets must require these checks. Workflow YAML does not prevent an
administrator from merging without a configured branch rule.

### Deployment callers

| `DEPLOY_METHOD` | Test caller | Prod caller |
|---|---|---|
| unset or `fabric-cicd` | [deploy-test.yml](.github/workflows/deploy-test.yml) | [deploy-prod.yml](.github/workflows/deploy-prod.yml) |
| `fabric-cicd-plan` | [deploy-test-fabric-cicd-plan.yml](.github/workflows/deploy-test-fabric-cicd-plan.yml) | [deploy-prod-fabric-cicd-plan.yml](.github/workflows/deploy-prod-fabric-cicd-plan.yml) |
| `fabric-cicd-bulk` | [deploy-test-fabric-cicd-bulk.yml](.github/workflows/deploy-test-fabric-cicd-bulk.yml) | [deploy-prod-fabric-cicd-bulk.yml](.github/workflows/deploy-prod-fabric-cicd-bulk.yml) |
| `bulk` | [deploy-test-bulk.yml](.github/workflows/deploy-test-bulk.yml) | [deploy-prod-bulk.yml](.github/workflows/deploy-prod-bulk.yml) |

Callers watch their publisher, shared connection/preparation helpers, Fabric
definitions, parameter rules, and workflow files. Plan callers also watch the
plan readers and their configured plan paths.

### Reusable templates called via `workflow_call`

| Template | Runner | Publisher-specific role |
|---|---|---|
| [reusable-deploy-fabric-cicd.yml](.github/workflows/reusable-deploy-fabric-cicd.yml) | [deploy_fabric_cicd_non_bulk.py](scripts/deploy_fabric_cicd_non_bulk.py) | Default non-bulk phases and eligible orphan cleanup |
| [reusable-deploy-fabric-cicd-plan.yml](.github/workflows/reusable-deploy-fabric-cicd-plan.yml) | [deploy_fabric_cicd_non_bulk_plan.py](scripts/deploy_fabric_cicd_non_bulk_plan.py) | Sequential client-read plan groups, remaining items, and eligible orphan cleanup |
| [reusable-deploy-fabric-cicd-bulk.yml](.github/workflows/reusable-deploy-fabric-cicd-bulk.yml) | [deploy_fabric_cicd_bulk.py](scripts/deploy_fabric_cicd_bulk.py) | Grouped strict bulk selections and eligible orphan cleanup |
| [reusable-deploy-bulk.yml](.github/workflows/reusable-deploy-bulk.yml) | [deploy_fabric_rest_bulk.py](scripts/deploy_fabric_rest_bulk.py) | Direct REST payloads, polling, and value-set activation; no orphan cleanup |
| [reusable-fabric-etl.yml](.github/workflows/reusable-fabric-etl.yml) | [run_fabric_etl.py](scripts/run_fabric_etl.py) | Resolve, start, and poll one Fabric job |

### Why reusable workflows, not composite actions

The reusable deployment templates own the target GitHub Environment. That
keeps Environment secrets, optional reviewer gates, concurrency, connection
preflight, publication, and the dependent DataPipeline in one visible job
graph. Composite actions cannot replace workflow-level Environment and job
dependency controls.

### ETL callers and handoff

| Workflow | Trigger | Purpose |
|---|---|---|
| Selected deployment caller's `run-etl` job | Successful deployment job through `needs` | Runs the DataPipeline from the same branch revision |
| [etl-test.yml](.github/workflows/etl-test.yml) | Manual, branch `test` | Test recovery without republishing |
| [etl-prod.yml](.github/workflows/etl-prod.yml) | Manual, branch `main` | Prod recovery using the Prod Environment and any configured protection |

The automatic handoff is not a `workflow_run` listener loaded from another
branch. Publication and ETL remain in the same workflow graph and revision.
Stage concurrency covers both jobs. A failed publication prevents ETL.

### Post-ETL semantic model refresh

The reusable ETL job starts `Patterns_Load_Validate_And_Refresh` as a Fabric
DataPipeline and waits for its terminal state:

1. `Import_Patterns_Data` writes the sample Delta tables.
2. `Validate_Patterns_Data` performs read-only schema, key, reference,
   source-date-type, and configured patient-minimum checks.
3. The native semantic-model refresh runs only after validation succeeds, with
   transactional execution and wait-on-completion enabled.

The Fabric DataPipeline is the only refresh owner. GitHub does not perform a
second semantic-model refresh.

`minimum_patient_count` is a positive Integer supplied from the active
`Patterns_Variables` value set. `run_label` is an independent String supplied
by the caller when required. Invalid input is not replaced with a
success-shaped default.

The deployment service principal submits the DataPipeline job. Its Notebook
and refresh activities authenticate through the stage's Workspace Identity
connections. Deployment success does not prove model ownership, source access,
DAX results, report rendering, or consumer access.

## Failure and retry boundaries

| Failure point | Behavior and safe response |
|---|---|
| Stage/ref or configuration preflight | Fails before Fabric writes; correct the selected branch, Environment, secrets, or variables |
| Connection ensure | Can leave a correctly created connection or verified role behind; fix the error and rerun because names and IDs are reconciled |
| ID persistence | Never overwrites a different existing value; review the intended resource before removing or changing a variable |
| Publication | ETL does not start; inspect the selected publisher's item-level result |
| DataPipeline start or terminal failure | Publication remains complete; inspect the exact Fabric run and activity diagnostics |
| GitHub polling timeout | Does not cancel Fabric work; inspect Fabric before retrying |
| Manual ETL recovery | Uses the current branch revision and existing published definitions; it does not repair a failed publication |

Do not rerun an old revision to test a newer workflow. If a connection was
created before a later step failed, reuse and verify it rather than creating
another similarly named resource.

## Verification status

The table distinguishes checked-in implementation from live evidence.

| Path | Checked-in contract | Live evidence for this revision |
|---|---|---|
| Default `fabric-cicd`, Test | Connection prelude, three publication phases, same-revision DataPipeline | Verified on 2026-10-14 by [run 38581072000](https://github.com/michaeldeongreen/microsoft-fabric-sdlc-patterns/actions/runs/38581072000) |
| `fabric-cicd-plan`, Test | Same connection prelude, sequential plan groups, same-revision DataPipeline | Not yet live-verified |
| `fabric-cicd-bulk`, Test | Same connection prelude, strict grouped bulk, same-revision DataPipeline | Not yet live-verified |
| Raw REST `bulk`, Test | Same connection prelude, three REST batches, same-revision DataPipeline | Not yet live-verified |
| Any Prod route | Prod-scoped equivalent of its Test route | Not yet live-verified |
| Current feature Branch Out revision | Human feature pair, preparation, swap, Fabric Git update, manual DataPipeline | Not yet live-verified as a complete current-revision cycle |

Run `38581072000` completed GitHub preflight, WI connection ensure,
connections-admin Owner verification, ID persistence, default publication, and
the same-revision Fabric DataPipeline. It does not certify the three
alternative methods, Prod, cold-versus-reuse behavior, or workload-specific
model/report/consumer acceptance.

## Release evidence

Before Prod promotion, retain evidence that identifies the candidate revision
and target:

- required PR checks and reviews;
- selected `DEPLOY_METHOD`;
- Test deployment and DataPipeline run URLs;
- item publication results;
- active Variable Library value set and physical binding checks;
- expected table, model, report, Ontology, and Data Agent results;
- semantic-model ownership/source access and consumer checks;
- accepted exceptions and their owners; and
- a recovery point or corrective-forward plan.

See [Quality Gates and Release Controls](fabric-cicd-quality-gates-and-release-controls.md)
for a broader control baseline and
[Governance Considerations](fabric-cicd-governance-considerations.md) for
identity and approval boundaries.
