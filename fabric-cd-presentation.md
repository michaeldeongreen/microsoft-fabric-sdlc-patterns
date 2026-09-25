# Continuous Delivery in Microsoft Fabric

<div align="center">

## Why it is difficult, the options available, and a working GitHub implementation

<br/>

**Michael Green**<br/>
*[Role / Team / Organization]*<br/>
October 2026

<br/>

[Reference implementation](https://github.com/michaeldeongreen/microsoft-fabric-sdlc-patterns) · [Begin](#section-1-content)

</div>

<!-- Replace the role/team/organization placeholder before presenting. -->
<!-- Top-level details share a name so modern GitHub and VS Code previews keep one section open at a time. -->

> Official Microsoft documentation is the source of truth for current Fabric capabilities. This repository is an opinionated GitHub Actions implementation based on field experience.

---

## Part I — Continuous delivery in Fabric

<details name="cd-presentation" open>
<summary id="section-1-why-fabric-cd-matters"><strong>1. Why continuous delivery matters in Fabric</strong></summary>

<br/>
<div id="section-1-content"></div>

A Fabric workspace is both a development surface and a live environment. Notebooks, pipelines, semantic models, reports, lakehouses, ontologies, and agents can all participate in one business solution—and many of them can be edited directly in the browser.

That flexibility creates a delivery problem:

> **How do we reproduce a working Fabric solution in Test and Prod without rebuilding it by hand or letting each workspace drift into a different truth?**

### What a reliable Fabric release must preserve

| Release concern | What must be true after deployment |
|---|---|
| **Definitions** | The intended notebooks, models, reports, pipelines, and other supported items exist at the approved version |
| **Dependencies** | Items point to the correct target-workspace items and connections |
| **Environment configuration** | Test uses Test resources; Prod uses Prod resources |
| **Data readiness** | Required ingestion, refresh, and transformation have completed |
| **Security** | The deployment identity can change only the intended target |
| **Evidence** | The team can connect the deployed state to an approved source revision |

### What CD prevents

- Manual recreation of workspace items.
- Hardcoded Dev IDs leaking into Test or Prod.
- Unreviewed production edits.
- “It worked in Dev” releases with missing data or broken bindings.
- Workspaces whose state cannot be tied back to Git.
- Rollbacks that depend on remembering what somebody clicked.

Fabric CD is therefore not just file movement:

```text
Approved definitions
  + target configuration
  + dependency resolution
  + data orchestration
  + deployment controls
  = a usable Fabric environment
```

<div align="center">

[Next: Why Fabric CD is challenging ↓](#section-2-content)

</div>

</details>

<details name="cd-presentation">
<summary id="section-2-fabric-cd-challenges"><strong>2. Why continuous delivery in Fabric is challenging</strong></summary>

<br/>
<div id="section-2-content"></div>

Fabric solutions do not behave like one compiled application artifact. Different item types participate in source control, dependency binding, deployment, and runtime configuration in different ways.

| Fabric reality | Delivery consequence |
|---|---|
| **Support differs by item type** | Git integration, Deployment Pipelines, `fabric-cicd`, and REST APIs do not always support the same items |
| **Support changes over time** | A design based on today's support matrix must be revisited as Fabric evolves |
| **References are not uniform** | Some dependencies use portable logical references; others embed physical workspace or item IDs |
| **A clean workspace has no target IDs yet** | Foundational items may need to be created before dependent definitions can be parameterized |
| **Configuration lives in several places** | Variable Libraries, item metadata, connections, deployment rules, and secrets solve different parts of the problem |
| **Git stores definitions—not all state** | Data, credentials, permissions, schedules, and some bindings need separate treatment |
| **The workspace can have competing writers** | Mixing Git sync, API deployment, and direct edits can create drift |
| **Automation identity support varies** | Service-principal support can differ by workload and by API |

### One Fabric solution, several lifecycle categories

| Category | Lifecycle behavior |
|---|---|
| **Git-tracked** | Definition files can be versioned, reviewed, and promoted from a repository |
| **Deployable through another Fabric surface** | The item may move through Deployment Pipelines or an API even when it is not part of the Git flow |
| **Manual or separately configured** | The item or setting must be recreated, bound, or governed outside the main content pipeline |

Always verify the current official supported-item lists. A workspace is deployable only when every required item and setting has an explicit lifecycle plan.

<details>
<summary><strong>Example — logical references versus physical IDs</strong></summary>

<br/>

This repository contains both models:

- The Report uses a relative `byPath` reference to its Semantic Model in [`definition.pbir`](data/fabric/Patterns_Report.Report/definition.pbir).
- The Ontology's [`doctors` data binding](data/fabric/Patterns_Ontology.Ontology/EntityTypes/2525121373138/DataBindings/6e4524f9-ea6d-4535-ab49-a72f73fc08a0.json) uses the Lakehouse logical ID declared in the Lakehouse [`.platform` file](data/fabric/PatternsLakehouse.Lakehouse/.platform).
- The Data Agent's [`datasource.json`](data/fabric/Patterns_Data_Agent.DataAgent/Files/Config/draft/ontology-Patterns_Ontology/datasource.json) uses the Ontology logical ID declared in the Ontology [`.platform` file](data/fabric/Patterns_Ontology.Ontology/.platform).
- The Direct Lake Semantic Model contains a physical OneLake workspace/lakehouse path in [`expressions.tmdl`](data/fabric/Patterns_Semantic_Model.SemanticModel/definition/expressions.tmdl).
- Notebook metadata contains physical default workspace and lakehouse IDs in [`notebook-content.py`](data/fabric/Import_Patterns_Data.Notebook/notebook-content.py).

The first two are comparatively portable. The latter two require deployment-time replacement for each environment.

Git dependency binding, Deployment Pipeline autobinding, and build-time parameterization can all help, but they are different mechanisms with different support boundaries.

</details>

<details>
<summary><strong>Example — why the first deployment is different</strong></summary>

<br/>

On the first deployment to an empty workspace:

1. The target Lakehouse does not have an ID.
2. Other definitions need that ID.
3. The Lakehouse must be created first.
4. The deployment must query the new ID.
5. Dependent items can then be rewritten and uploaded.

This is why both deployment implementations in this repository can use two phases.

Some workloads can also require one-time post-deployment binding or initialization. “Definition deployed” does not always mean “solution operational.”

</details>

<details>
<summary><strong>The one-writer principle</strong></summary>

<br/>

Choose which mechanism owns each workspace:

- A Git-connected workspace should normally be updated through Git.
- An API-deployed workspace should normally be updated through its delivery pipeline.
- Direct production edits create state that may be overwritten or never represented in source control.

This repository uses Fabric Git integration for Dev and API-driven deployment for Test and Prod.

</details>

<details>
<summary><strong>Infrastructure provisioning is a different layer</strong></summary>

<br/>

Bicep and Terraform can provision parts of the Fabric control plane, but provisioning a capacity or workspace is not the same as promoting a tested set of item definitions.

- Bicep covers Fabric capacity resources.
- The Microsoft Fabric Terraform provider covers a broader set of control-plane resources and can create item resources.
- Content promotion still needs an operating model for parameterization, UI edits, drift, dependencies, and stage-to-stage release.

Use infrastructure tooling to create the environment. Use a Fabric delivery mechanism to promote the solution that runs inside it.

</details>

<div align="center">

[Next: Fabric deployment options ↓](#section-3-content)

</div>

</details>

<details name="cd-presentation">
<summary id="section-3-fabric-deployment-options"><strong>3. Continuous delivery options in Fabric</strong></summary>

<br/>
<div id="section-3-content"></div>

Fabric provides three practical release models. Each puts source-of-truth, configuration, operational ownership, and deployment evidence in a different place.

<details name="fabric-release-option" open>
<summary><strong>Option 1 — Fabric Deployment Pipelines</strong></summary>

<br/>

Git is typically connected to Dev. Fabric promotes content workspace-to-workspace through pipeline stages.

<p align="center"><img src="assets/fabric-deployment-pipelines-flow.svg" alt="Fabric Deployment Pipelines flow"></p>

**Strengths**

- Lowest setup cost.
- Fabric-native visual comparison and deployment history.
- Full or selective deployment through the UI.
- Deployment rules and workload-specific autobinding.
- Familiar operating model for Fabric administrators.

**Trade-offs**

- Git is not necessarily the direct source for Test and Prod.
- The stage topology is linear.
- Deployment rules do not cover every environment-specific value.
- API-driven selective deployment requires explicit item and dependency planning.
- Recovery depends on both source control and the state of the staged workspaces.

**Best fit:** teams prioritizing a Fabric-native operating experience and minimal custom automation.

</details>

<details name="fabric-release-option">
<summary><strong>Option 2 — Fabric Git integration for every stage</strong></summary>

<br/>

Each long-lived branch is connected to a workspace. Promotion is a branch merge followed by Update from Git.

<p align="center"><img src="assets/git-based-deployments-flow.svg" alt="Git integration deployment flow"></p>

**Strengths**

- Git is the direct definition source for every stage.
- The same branch and pull-request model governs development and promotion.
- Supported definitions can be reconstructed from the stage branch.
- No separate content-deployment library is required.

**Trade-offs**

- Every stage—including Prod—participates in Fabric Git integration.
- Multiple long-lived branches increase merge and hotfix complexity.
- Environment-specific transformation is less flexible than a build step.
- Teams must manage workspace/Git drift and competing writers carefully.
- Deployment evidence is Git-centric rather than Fabric Deployment Pipeline-centric.

**Best fit:** teams comfortable operating every stage through Git integration and maintaining a branch-per-stage model.

</details>

<details name="fabric-release-option">
<summary><strong>Option 3 — Git plus a build environment and Fabric APIs</strong></summary>

<br/>

A CI/CD runner checks out the stage branch, applies target configuration, authenticates to Fabric, and uploads definitions through `fabric-cicd` or REST APIs.

<p align="center"><img src="assets/git-build-deployments-flow.svg" alt="Git-based deployment with build environments"></p>

**Strengths**

- Git remains the source for supported definitions across stages.
- Build-time parameterization can rewrite target-specific metadata.
- Test and Prod do not need Fabric Git integration.
- GitHub or Azure DevOps can provide approvals, secrets, policy, and run history.
- Deployment, ETL, validation, and post-deployment operations can be orchestrated together.

**Trade-offs**

- Highest engineering and maintenance cost.
- The team owns workflow behavior, identity, diagnostics, and failure handling.
- Tool and API support still varies by item type.
- Full-state deployment can take longer than a small diff.
- Incorrect scope or reconciliation logic can create or remove unintended items.

**Best fit:** teams that need configuration control, repeatability, and CI/CD-platform governance—and are prepared to own the automation.

</details>

### Side-by-side

| | Deployment Pipelines | Git per stage | Build environment / APIs |
|---|---|---|---|
| Source for Test/Prod | Prior workspace stage | Stage branch | Stage branch plus deployment config |
| Native Fabric comparison | **Yes** | No | No |
| Build-time transformation | Limited to supported rules | No | **Yes** |
| Test/Prod Git connection | No | **Yes** | No |
| Delivery engineering effort | Low | Medium | High |
| Operational owner | Fabric operators | Git/Fabric operators | Platform/CI/CD team |

<details>
<summary><strong>When one option does not support the whole workspace</strong></summary>

<br/>

Deployment methods can be combined around dependency boundaries:

<p align="center"><img src="assets/hybrid-recommendation-flow.svg" alt="Hybrid deployment recommendation"></p>

1. Deploy supported foundational items.
2. Move unsupported items through another supported Fabric surface.
3. Deploy supported items that depend on them.

The advantage is broader automation. The cost is a release whose ordering, audit evidence, and recovery span more than one deployment system.

</details>

<div align="center">

[Next: `fabric-cicd` and Bulk APIs ↓](#section-4-content)

</div>

</details>

<details name="cd-presentation">
<summary id="section-4-fabric-cicd-and-bulk"><strong>4. Inside Option 3 — `fabric-cicd` and the Bulk APIs</strong></summary>

<br/>
<div id="section-4-content"></div>

The tooling decision inside Option 3 is not only about transport speed. It determines how much environment configuration, reconciliation, and operational behavior the caller must implement.

| Concern | Standard `fabric-cicd` | `fabric-cicd` bulk requested | Direct Bulk Import API |
|---|---|---|---|
| Abstraction | Deployment library | Deployment library with bulk optimization requested | REST API |
| Parameterization | Full `parameter.yml` feature set | Same, but dynamic variables can force fallback | Caller preprocessing |
| Orphan cleanup | Built in | Built in | Separate DELETE logic required |
| Dependency handling | Caller chooses phases | Caller chooses phases | Service import plus any caller preprocessing phases |
| Long-running operations | Hidden by library | Hidden by library | Caller polls and interprets results |
| Custom code ownership | Low | Low | High |
| Behavior in this repository | Per-item publish | Falls back to per-item publish | Two bulk imports plus post-deploy configuration |

### Standard `fabric-cicd`

`fabric-cicd` is the recommended path in this repository because it already provides:

- declarative environment parameterization;
- dynamic `$workspace` and `$items` replacement;
- item-type scoping;
- Variable Library environment activation;
- orphan cleanup;
- a maintained abstraction over item-level Fabric APIs.

Its important trade-offs are full-state deployment and the need to plan dependency phases where target IDs must exist before other items can be parameterized.

### `fabric-cicd` with bulk requested

The library can request its experimental bulk-publish path. In this repository, `parameter.yml` contains dynamic `$workspace` and `$items` references, so the library falls back to standard per-item publishing.

That fallback demonstrates a key point:

> A faster upload primitive is useful only when it remains compatible with the configuration model the solution requires.

### Direct Bulk Import API

The direct API path can send a workspace definition payload through a smaller number of requests, but the API does not remove the surrounding delivery responsibilities.

This repository's [`deploy_bulk.py`](scripts/deploy_bulk.py) must add:

- definition discovery and Base64 packaging;
- target workspace and item-ID substitution;
- phased imports when newly created IDs are required;
- long-running-operation polling and token refresh;
- Variable Library value-set activation;
- per-item result reporting.

It intentionally does not add full `parameter.yml` compatibility, item-type filtering, or orphan deletion.

> Official Bulk documentation is in transition. This repository currently calls the beta-qualified endpoint; verify the current REST reference and supported-item behavior before selecting it for production.

### Selection guidance

Choose **standard `fabric-cicd`** when configuration and reconciliation features are more valuable than minimizing API calls.

Consider **direct Bulk APIs** when the solution is already portable through logical IDs and runtime configuration, or when the team intentionally wants to own the lower-level deployment implementation.

<div align="center">

[Next: What this repository implements ↓](#section-5-content)

</div>

</details>

<details name="cd-presentation">
<summary id="section-5-repository-implementation"><strong>5. What this repository implements</strong></summary>

<br/>
<div id="section-5-content"></div>

This repository chooses Option 3 for Test and Prod while keeping Dev connected to Git.

<p align="center"><img src="assets/git-build-deployments-flow.svg" alt="Git-based deployment with build environments"></p>

```text
feature/* → dev → test → main
              │      │      │
              │      │      └─ GitHub Actions → Prod workspace → Prod ETL
              │      └──────── GitHub Actions → Test workspace → Test ETL
              └─────────────── Fabric Git integration → Dev workspace
```

| Branch | Workspace | Delivery mechanism |
|---|---|---|
| `dev` | Dev | Fabric Git integration |
| `test` | Test | GitHub Actions |
| `main` | Prod | GitHub Actions |

### Why the sample exercises real Fabric delivery problems

| Item | Delivery characteristic |
|---|---|
| Lakehouse | Must exist before its target ID can be used elsewhere |
| Variable Library | Carries runtime values and environment-specific value sets |
| Notebooks | Include ETL logic and physical default-lakehouse metadata |
| Semantic Model | Includes a physical Direct Lake workspace/lakehouse path |
| Report | Uses a portable relative model reference |
| Ontology | Uses a logical item reference but requires operational data binding |
| Data Agent | Depends on the deployed Ontology |

### Two configuration mechanisms

| | Variable Libraries | `parameter.yml` |
|---|---|---|
| Applied | At runtime | Before upload |
| Handles | Values the workload can resolve dynamically | Physical IDs and metadata the workload cannot defer |
| Examples | Workspace/lakehouse values read by notebooks | Notebook META IDs and Direct Lake paths |

### Dependency-aware deployment

```text
Phase 1
  Lakehouse + Ontology
        ↓
  target IDs and logical dependencies now exist
        ↓
Phase 2
  Variable Library + Notebooks + Semantic Model + Report + Data Agent
        ↓
  orphan cleanup
        ↓
  ETL / data population
```

This is a full-state deployment, not a commit-diff deployment. The standard path publishes every in-scope definition and removes items it owns that are no longer represented in Git.

### Three selectable implementations

| `DEPLOY_METHOD` | Result |
|---|---|
| unset or `fabric-cicd` | Recommended standard `fabric-cicd` path |
| `fabric-cicd-bulk` | Requests library-managed bulk; this repository falls back to standard publish |
| `bulk` | Direct Bulk Import API implementation |
| any other value | All deploy workflows skip |

Regardless of the selected path, successful deployment is followed by the same ETL workflow.

<details>
<summary><strong>First deployment to a clean workspace</strong></summary>

<br/>

The two-phase workflow solves target-ID bootstrap, but some solution state can still require one-time setup:

- bind the Ontology Graph Model to its target data;
- complete workload-specific initialization;
- confirm the Semantic Model connection;
- run ETL and validate all dependent items.

Subsequent releases are automated, but a production plan must distinguish repeatable deployment from first-environment provisioning.

</details>

<div align="center">

[Next: Live GitHub walkthrough ↓](#section-6-content)

</div>

</details>

---

## Part II — From `main` to Prod

<details name="cd-presentation">
<summary id="section-6-live-github-walkthrough"><strong>6. Live walkthrough — follow one release through GitHub and Fabric</strong></summary>

<br/>
<div id="section-6-content"></div>

```text
PR: test → main
  ↓
branch rules + promotion-path check
  ↓
merge creates a push to main
  ↓
DEPLOY_METHOD selects one Prod orchestrator
  ↓
Prod GitHub Environment supplies target identity and workspace
  ↓
reusable workflow deploys and reconciles definitions
  ↓
successful deployment triggers Prod ETL
  ↓
Git + Actions + Fabric provide the evidence chain
```

<details name="github-walkthrough-step" open>
<summary><strong>1 — Promotion into `main`</strong></summary>

<br/>

[`enforce-promotion-path.yml`](.github/workflows/enforce-promotion-path.yml) requires a pull request into `main` to originate from `test`.

Branch rulesets protect `dev`, `test`, and `main` from deletion and non-fast-forward updates, require pull requests, and attach stage-appropriate status checks.

This is the first governance boundary:

- the source revision is reviewed before it becomes eligible for Prod;
- the promotion path prevents an arbitrary feature branch from skipping stages;
- Git records the change, discussion, approvals, and merge SHA.

</details>

<details name="github-walkthrough-step">
<summary><strong>2 — Route the Prod deployment</strong></summary>

<br/>

The Prod orchestrators all respond to the same event:

```yaml
on:
  push:
    branches: [main]
    paths: ["data/fabric/**", ".github/workflows/**"]
```

The repository variable selects the implementation:

```yaml
if: vars.DEPLOY_METHOD == '' || vars.DEPLOY_METHOD == 'fabric-cicd'
```

- [`deploy-prod.yml`](.github/workflows/deploy-prod.yml) selects standard `fabric-cicd`.
- [`deploy-prod-fabric-cicd-bulk.yml`](.github/workflows/deploy-prod-fabric-cicd-bulk.yml) requests library-managed bulk.
- [`deploy-prod-bulk.yml`](.github/workflows/deploy-prod-bulk.yml) selects the direct Bulk API.

Documentation-only changes do not deploy. A Fabric definition or workflow change does.

</details>

<details name="github-walkthrough-step">
<summary><strong>3 — Cross the Prod environment boundary</strong></summary>

<br/>

The reusable job declares the target environment:

```yaml
environment: ${{ inputs.environment }}
```

For Prod, that environment supplies:

- tenant ID;
- client/application ID;
- client secret;
- target Fabric workspace ID.

The deployment service principal needs Contributor on the target workspace. It does not need repository write access, and the workflow token is limited to `contents: read`.

For production:

- use a separate deployment identity per environment where practical;
- scope each identity to only its target workspace;
- restrict Prod deployment to `main`;
- add required Prod reviewers when deploy-time approval is part of the control model;
- evaluate GitHub OIDC to replace the stored client secret with short-lived federation.

The Fabric Workspace Identity is not the CI/CD deployment identity. It serves a different purpose: outbound authentication from the workspace.

</details>

<details name="github-walkthrough-step">
<summary><strong>4 — Deploy and reconcile Fabric definitions</strong></summary>

<br/>

[`reusable-deploy-fabric-cicd.yml`](.github/workflows/reusable-deploy-fabric-cicd.yml):

1. checks out the source revision;
2. sets up Python;
3. installs `fabric-cicd` and `azure-identity`;
4. passes the environment-scoped values to [`deploy_fabric_cicd.py`](scripts/deploy_fabric_cicd.py).

The script:

- creates foundational items in Phase 1;
- resolves target IDs and deploys dependent definitions in Phase 2;
- applies [`parameter.yml`](data/fabric/parameter.yml);
- activates the correct Variable Library environment;
- removes orphaned items in the standard path.

The alternative reusable workflows preserve the same environment and surrounding controls while changing the deployment primitive.

</details>

<details name="github-walkthrough-step">
<summary><strong>5 — Populate data only after deployment succeeds</strong></summary>

<br/>

[`etl-prod.yml`](.github/workflows/etl-prod.yml) listens for successful completion of all three Prod deployment workflows.

It then calls [`reusable-fabric-etl.yml`](.github/workflows/reusable-fabric-etl.yml), which:

- resolves `Import_Patterns_Data` by display name;
- starts the notebook job through the Fabric REST API;
- polls until completion, failure, or timeout.

The notebook ID can differ in every workspace. Display-name resolution avoids another hardcoded target ID.

The ETL workflow can also be run manually without redeploying definitions.

</details>

<details name="github-walkthrough-step">
<summary><strong>6 — Follow the audit evidence</strong></summary>

<br/>

| Question | Evidence |
|---|---|
| What changed and why? | Git diff, commit, and pull request |
| Who reviewed and promoted it? | PR and branch-rule history |
| What revision deployed? | Actions run commit SHA |
| Who authorized deployment? | GitHub Environment review, when enabled |
| What did automation do? | Workflow and script logs |
| Did data preparation succeed? | ETL workflow result |
| What happened inside Fabric? | Fabric activity and organizational audit sources |

The commit SHA is the thread connecting intent, execution, and validation.

GitHub Actions supplies deployment evidence, but it does not replace Fabric workspace auditing, data-quality validation, or organizational retention policy.

</details>

<details>
<summary><strong>Demonstration repository posture versus a production posture</strong></summary>

<br/>

As inspected on 2026-09-25:

| Control | Demonstration repository | Production discussion |
|---|---|---|
| Branch rulesets | Active for `dev`, `test`, and `main` | Retain and review required checks |
| Required PR approvals | Zero | Require reviewers if review is a stated control |
| Deployment route | `DEPLOY_METHOD=fabric-cicd-bulk` | Select the intended path deliberately; standard `fabric-cicd` is the repository recommendation |
| Prod Environment protection | Not configured | Add required reviewers and a `main` deployment policy where appropriate |
| Deployment credential | Client secret | Evaluate GitHub OIDC |
| Workflow token | Read-only | Retain least privilege |
| Actions policy | All Actions allowed; SHA policy not enforced | Consider an allowlist and enforced SHA pinning; workflows already pin Actions manually |

The workflow structure supports these controls, but repository settings determine whether they are actually enforced.

</details>

<div align="center">

[Next: Rollback and recovery ↓](#section-7-content)

</div>

</details>

<details name="cd-presentation">
<summary id="section-7-rollback-and-recovery"><strong>7. Rollback and recovery</strong></summary>

<br/>
<div id="section-7-content"></div>

There is no separate rollback deployment model.

### Definition rollback

```text
identify the bad change
  → create a git revert commit
  → review and promote it
  → run the same deployment path
  → validate the target
```

The revert moves Git forward and preserves the audit trail. The existing Action reconciles the target workspace to the reverted definitions.

### Data recovery is different

Git cannot reverse:

- changed or deleted lakehouse data;
- downstream side effects;
- refresh state;
- writes to external systems.

Data recovery requires workload-specific planning: reprocessing, snapshots, retention, point-in-time capabilities, or a coordinated backout procedure.

### Deployment-method implications

| Method | Recovery behavior |
|---|---|
| Deployment Pipelines | A prior stage can be promoted forward again; Fabric retains pipeline history |
| Git per stage | Revert the stage branch and update the workspace from Git |
| Standard `fabric-cicd` | Revert and redeploy; orphan cleanup restores the Git-owned definition shape |
| Direct Bulk path in this repo | Revert and re-import, but removed source items remain until separately deleted |

A production hotfix can start from `main`, but it must be merged back into `test` and `dev` so the normal promotion path does not reintroduce the defect.

For this presentation, rollback is a design discussion—not a separate Action demo. A future resilience exercise can demonstrate a failed release, revert PR, redeployment, and data recovery end to end.

<div align="center">

[Next: Closing perspective ↓](#section-8-content)

</div>

</details>

<details name="cd-presentation">
<summary id="section-8-closing"><strong>8. Closing perspective</strong></summary>

<br/>
<div id="section-8-content"></div>

### The Fabric CD problem

The difficult part is not uploading files. It is reproducing a working solution across item types whose definitions, dependencies, environment bindings, data, and automation support do not behave uniformly.

### The choice

- Use **Deployment Pipelines** for a Fabric-native staged operating model.
- Use **Git per stage** when every workspace should follow its own branch.
- Use a **build environment and APIs** when the team needs stronger transformation and CI/CD-platform control.
- Inside the build option, choose between a deployment library and lower-level Bulk APIs based on how much orchestration the team wants to own.

### This repository

- Dev is Git-connected.
- Test and Prod are deployed through GitHub Actions.
- Standard `fabric-cicd` is the recommended path.
- Bulk variants demonstrate lower-level behavior and compatibility trade-offs.
- Runtime values and deployment-time metadata use different configuration mechanisms.
- Deployment is dependency-aware and followed by ETL.
- Branch rules, GitHub Environments, identities, logs, and Fabric audit sources form the governance story.

### Go deeper

| Resource | Purpose |
|---|---|
| [`fabric-cicd-release-options.md`](fabric-cicd-release-options.md) | Detailed strategy and option comparison |
| [`fabric-hybrid-cicd-guide.md`](fabric-hybrid-cicd-guide.md) | Standard `fabric-cicd` implementation |
| [`fabric-bulk-cicd-guide.md`](fabric-bulk-cicd-guide.md) | Direct Bulk API implementation |
| [`fabric-cicd-governance-considerations.md`](fabric-cicd-governance-considerations.md) | Identity, approvals, audit, and adjacent controls |
| [`fabric-development-process.md`](fabric-development-process.md) | Branch Out and feature-workspace development |
| [Official Fabric CI/CD overview](https://learn.microsoft.com/en-us/fabric/cicd/cicd-overview) | Current Microsoft guidance |
| [Choose a Fabric CI/CD workflow](https://learn.microsoft.com/en-us/fabric/cicd/manage-deployment) | Current platform option guidance |

<div align="center">

**Questions**

[Back to the beginning](#section-1-content) · [Repository](https://github.com/michaeldeongreen/microsoft-fabric-sdlc-patterns)

</div>

</details>
