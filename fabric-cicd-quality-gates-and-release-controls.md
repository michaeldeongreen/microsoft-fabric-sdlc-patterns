# Fabric CI/CD Quality Gates and Release Controls

A recommended control baseline for releasing Fabric workloads, informed by the public guidance linked below. It is not a mandatory Microsoft checklist or a built-in validator for every item.

Use Development -> Test -> Production as lifecycle roles. An organization might call Test "Certification," "UAT," or "Staging." Choose supported Git, native Deployment Pipeline, or API/library routes for the workload; native pipelines and Deployment Plans are not universal requirements.

- Automated checks: CI executes assertions, retains results, and blocks on failure.
- Manual verification: a person performs a required check that cannot use approved automation.
- Approval: an accountable owner authorizes a reviewed change or release; CI can enforce that decision, not replace it.
- Exceptions: record the owner, affected scope, risk, mitigation, and expiry. Missing evidence, skipped checks, or authentication failures are not passing tests.

## Contents

- [Gates by stage](#1-quality-gates-by-stage)
- [Per-artifact checks](#2-per-artifact-checks)
- [Essential automated tests](#3-essential-automated-tests)
- [Approvals and release controls](#4-approvals-and-release-controls)
- [Support inventory and exceptions](#5-support-inventory-and-exceptions)
- [Failure handling and recovery](#6-failure-handling-and-recovery)
- [Enterprise patterns and references](#7-enterprise-patterns-and-references)

## 1. Quality gates by stage

Apply controls to the changed workload and its dependencies. Agree expected results and blocking thresholds before the release; do not infer readiness from publication alone.

### At pull request / source review

- Automated checks: validate versioned definitions, permitted environment references, code quality, and applicable unit tests; scan for credentials committed to source.
- Manual review: assess business logic, dependencies, permission changes, and destructive schema/data changes. Require the relevant reviewers through branch protection.
- Exit gate: required checks and PR reviews pass. PR approval is not Production deployment authorization.

### Before deploying to each target

- Automated checks: inventory items and confirm route/version/identity support; verify the target workspace, capacity, prerequisite resources, connections, and effective environment configuration.
- Manual verification: resolve checks without supported automation. Platform owners approve prerequisite access/setup; material removals or breaking changes need risk review.
- Exit gate: the intended scope, target, dependencies, and configuration are valid. Re-run preflight for Production; do not recreate existing resources merely to validate them.

### After Test deployment, before Production promotion

- Automated checks: confirm publication and configuration completed successfully, then execute critical workload paths and schema, data-quality, business-result, and consumer-access tests.
- Manual verification: perform necessary consumer-path checks without compliant automation. Business owners provide UAT/acceptance evidence for material behavior changes.
- Exit gate: results belong to this candidate release, not an older definition. Failed deployment, runtime checks, or missing required acceptance evidence block promotion.

### Before and during Production deployment

- Automated checks: verify the approved candidate and Production preflight; enforce protected deployment access and the [release controls](#4-approvals-and-release-controls).
- Automated checks: validate deployed bindings before enabling new/changed writers or schedules.
- Manual approval: the designated release owner reviews Test evidence, scope, risk, and recovery readiness. Add specialist signoff or a separate activation approval when risk warrants it.
- Exit gate: authorization covers this candidate and target; all required publication/configuration operations succeed. The release is not yet complete.

### After Production deployment

- Automated checks: verify actual bindings, connections, active configuration, required data readiness, and critical consumer paths. Use existing approved data and read-only smoke assertions; never seed business tables for validation.
- Manual verification: provide recorded evidence for essential checks that cannot use approved automation.
- Exit gate: record the successful Production baseline only after required smoke checks pass. Otherwise keep the release incomplete and invoke the failure/recovery decision.

## 2. Per-artifact checks

At PR, inspect source definitions/code. After publication, inspect effective target configuration. Execute workload tests in Test and an appropriate smoke subset in Production. Automate where the API and identity support it; retain manual evidence or an approved exception for gaps.

### Variable Libraries

- Verify the active value set and values resolved by a consumer point to approved workspace/item IDs. Check literal bindings too: a value set does not rewrite every definition.
- A native deployment into an empty stage activates `Default`. Configure and validate the intended active set before execution; do not assume Git/deployment comparison carries that workspace setting. [Lifecycle guidance](https://learn.microsoft.com/en-us/fabric/cicd/variable-library/variable-library-cicd).

### Data Pipelines

- Validate definition structure, connections, parameters, and dependency references against the target configuration.
- Run critical paths on controlled Test input; check terminal execution, failure handling, and expected outputs. Verify the runtime source/destination identity, not just the deployer's access. [Connections](https://learn.microsoft.com/en-us/fabric/data-factory/data-source-management).

### Notebooks and Spark environments

- Lint source and unit-test reusable logic; verify the lakehouse reference, parameters, published runtime, and libraries.
- Execute in Test and assert expected tables/files/results. Inspect resolved bindings rather than rewriting every GUID; logical binding can be supported. [Notebook lifecycle](https://learn.microsoft.com/en-us/fabric/data-engineering/notebook-source-control-deployment).

### Lakehouses

- After the intended ingestion/transformation, read existing outputs to verify required tables, column types, keys, shortcuts, counts, and reconciled totals.
- Git tracks metadata, not physical table schemas/data. Version the expected schema and workload that creates it; do not add columns or alter data solely for validation. [Lakehouse lifecycle](https://learn.microsoft.com/en-us/fabric/data-engineering/lakehouse-git-deployment-pipelines).

### Warehouses

- Validate SQL/object dependencies and compare deployed schema with the reviewed contract. Build/compare a SQL project when that is the chosen workflow.
- Test critical views/procedures with controlled input in Test; Production smoke queries remain read-only. Missing objects, invalid references, or incorrect results fail the check. [Development and deployment](https://learn.microsoft.com/en-us/fabric/data-warehouse/development-deployment).

### Semantic models and reports

- Check structure, connections, relationships, and critical measures; review changed visuals and metrics. Static-check examples use tools such as Tabular Editor Best Practice Analyzer and PBI Inspector, not a universal Fabric validator. [Validation example](https://learn.microsoft.com/en-us/power-bi/developer/projects/projects-build-pipelines).
- For Import models, wait for successful refresh before asserting results. For Direct Lake, wait for required [framing](https://learn.microsoft.com/en-us/fabric/fundamentals/direct-lake-how-it-works#framing) after source ETL, then query the intended current data. Framing is not another ETL/data copy and its success does not validate DAX or consumer access. Test calculations and security with the supported consumer identities described below. [Refresh API](https://learn.microsoft.com/en-us/rest/api/power-bi/datasets/refresh-dataset-in-group).

### Dataflows Gen2

- Ensure the candidate definition is published using the supported CI/CD route before refreshing; refreshing an older definition does not validate this release.
- Wait for refresh completion and check destination types, counts, required values, and relevant errors/warnings. Confirm item/API identity support. [Lifecycle](https://learn.microsoft.com/en-us/fabric/data-factory/dataflow-gen2-cicd-and-git-integration) and [job APIs](https://learn.microsoft.com/en-us/fabric/data-factory/dataflow-gen2-public-apis).

### Fabric Data Agents

- Verify approved sources and Ontology relationships when used. Evaluate the published agent in Test using supported consumer-level access.
- Require critical known-answer and access-denial cases individually to pass; inspect generated queries. A publish result or favorable average AI score alone is insufficient. Evaluation tooling is preview: validate its version and identity support. [Evaluation guidance](https://learn.microsoft.com/en-us/fabric/data-science/evaluate-data-agent).

## 3. Essential automated tests

Source-only tests run at PR. Integration, data, and consumer tests run after Test deployment, before Production promotion; smoke tests verify the Production result.

- Baseline suite: definition/reference checks, schema compatibility, critical end-to-end execution, independent expected business/data results, effective configuration, and permitted/denied consumer access.
- Unit tests: cover changed reusable code, invalid inputs, boundaries, and regressions; they complement rather than replace Fabric-runtime tests.
- Replay tests: for writers, repeat controlled Test input and require the intended idempotent result without duplicates.
- Performance tests: for affected critical queries, refreshes, or ETL, compare agreed targets/baselines under representative nonproduction data/capacity conditions.
- Consumer tests: use the intended user's approved authentication. Model RLS is bypassed by workspace Admin/Member/Contributor roles; the deployment identity is not a substitute. [RLS behavior](https://learn.microsoft.com/en-us/fabric/security/service-admin-row-level-security).
- Access boundaries: verify allowed/denied results on each relevant model/report, SQL, OneLake, and agent path. Model RLS alone does not secure direct data access; a failed login or timeout is not a passing denial test. [Permission model](https://learn.microsoft.com/en-us/fabric/security/permission-model).
- Power BI Execute Queries cannot use service principals for RLS- or SSO-enabled models. Use a supported user-based route or recorded manual verification; never weaken MFA/Conditional Access to make automation work. [API limitations](https://learn.microsoft.com/en-us/rest/api/power-bi/datasets/execute-queries).
- Harness checks: wait for operation/job/refresh-specific terminal success and inspect per-item outcomes and response-body errors. Fail CI on failed or missing required outcomes, cancellation, timeout, or unmet assertions; accepting a request, logging errors, or skipping checks is not a pass. [Jobs API](https://learn.microsoft.com/en-us/rest/api/fabric/core/job-scheduler/run-on-demand-item-job).

## 4. Approvals and release controls

### Human authorization

- Enforce deployment approvals through protected [GitHub Environments](https://docs.github.com/en/actions/how-tos/deploy/configure-and-manage-deployments/manage-environments) or [Azure DevOps resource checks](https://learn.microsoft.com/en-us/azure/devops/pipelines/process/approvals?view=azure-devops), outside editable deployment logic. Verify feature availability and restrict self-approval/bypass.
- Assign approval owners according to risk; architecture, business, or security review is not required for every routine change.
- Multiple listed GitHub environment reviewers require only one approval. If policy requires multiple independent signoffs, configure additional enforceable controls.

### Candidate identity and evidence

- Bind approval to the exact source snapshot, selected items, target, Test results, and reviewed environment substitutions. A changed candidate invalidates earlier evidence/authorization.
- For file-based releases, retain the tested definitions bundle, source commit, tool version, and package checksum before substitution. Production consumes that same bundle and verifies its identity; do not rebuild from a newer checkout.
- For native pipelines, freeze/review the source-stage content and retain source/target inventory, the [deployment operation record](https://learn.microsoft.com/en-us/rest/api/fabric/core/deployment-pipelines/get-deployment-pipeline-operation) with per-item outcomes, and test results. Record the synced Git SHA when applicable. Operation history is not a package hash or definition backup.
- Use protected, versioned release tags where applicable, not PR labels or a moving `prod` tag. Verify recorded SHAs; retain known-good definitions and evidence beyond CI artifact expiry.

### Execution and completion

- In this repository's [shared Test/Prod follow-up](fabric-hybrid-cicd-guide.md#post-etl-semantic-model-refresh), a green ETL workflow requires the existing notebook job and the configured `Patterns_Semantic_Model` refresh to complete successfully, in that order. Missing/ambiguous models, authorization errors, refresh failure, and timeout block success. This implemented orchestration gate is not the full business-result or consumer-validation suite.
- A refresh polling timeout is not server-side cancellation. Check the specific request's status/history before retriggering; a failed workflow can leave a service operation running.
- Share a lock/concurrency policy across all routes targeting the same workspace; hold it through deployment, required workload execution, and smoke checks. Do not interrupt an in-progress release with a competing one.
- Limit Production writes to approved deployment/operational identities. Keep secrets outside code; separate deployment, runtime, and consumer access. See [Governance Considerations](fabric-cicd-governance-considerations.md) for identity controls.
- Prefer OIDC/workload identity federation for CI where supported; constrain trust and deployment branch policies and verify Fabric permissions. This repository currently uses client-secret authentication; the [OIDC example is planned](https://github.com/michaeldeongreen/microsoft-fabric-sdlc-patterns/issues/84).
- Retain approvals, target configuration, per-item outcomes, job/refresh/test IDs, deletions, and run links with restricted access and masked results. Keep failed/partial attempts separate from the last fully validated Production release.

## 5. Support inventory and exceptions

Support depends on the deployment route, item subtype, tool version, identity, and preview status. REST API availability alone does not prove an item supports definition deployment.

- Automated inventory: enumerate the live workspace using [List Items](https://learn.microsoft.com/en-us/rest/api/fabric/core/items/list-items), follow every continuation page, and reconcile items with source definitions or approved exceptions. Git folders alone miss items not exported by Git.
- Confirm inventory visibility and supplement it with workload-specific APIs when needed. Authentication/permission failures, incomplete inventory, and `403` responses are not evidence of unsupported items.
- Maintain a reviewed type/subtype support table using the [Git](https://learn.microsoft.com/en-us/fabric/cicd/git-integration/intro-to-git-integration#supported-items), [native pipeline](https://learn.microsoft.com/en-us/fabric/cicd/deployment-pipelines/intro-to-deployment-pipelines#supported-items), and [fabric-cicd](https://microsoft.github.io/fabric-cicd/latest/) lists. Record tested tool versions, identities, and the chosen route; review on upgrades/type changes.
- Automated gate: require an approved route for each in-scope item, not support through all three mechanisms. Block unknown types, missing prerequisites, and expired/unapproved exceptions.
- Manual exception: name the alternate route, owner, required evidence, and expiry. An item unsupported by one route is not necessarily unusable in Fabric; never silently omit it.

## 6. Failure handling and recovery

- Stop further promotion on failed required checks; record partial state and alert the owner. Fabric deployment is not a workspace-wide transaction, and rejecting a later approval does not undo published changes.
- Definition rollback: authorize selective redeployment of retained known-good content/configuration. Check compatibility with current data/schema and review deletion behavior; today's Test content is not necessarily the previous Production release. [Lifecycle recovery guidance](https://learn.microsoft.com/en-us/fabric/cicd/best-practices-cicd).
- Data recovery: Git/definition rollback does not restore data. Before risky changes, record recoverable Delta versions or Warehouse restore points and relevant ingestion/source positions (watermarks); verify recovery retention.
- [Delta restore](https://learn.microsoft.com/en-us/fabric/data-engineering/delta-lake-restore) uses Spark, not the SQL analytics endpoint; [Warehouse restore](https://learn.microsoft.com/en-us/fabric/data-warehouse/restore-in-place-portal) overwrites current state.
- Destructive recovery needs explicit authorization. Check retention, pause affected writers, coordinate dependent tables, and reconcile/replay legitimate later data before resuming consumers.
- Rehearse recovery in Test; measure recovery-time/data-loss objectives and revalidate configuration, calculations, and consumer isolation before recording success.

## 7. Enterprise patterns and references

- Version supported definitions, configuration, and validation contracts; use feature branches and required PR checks/review.
- Separate environment workspaces and choose one deployment owner/route per item. Capacity isolation is a separate decision: nonproduction load tests must not degrade Production.
- Tutorials are starting points, not certification of production readiness.

| Public reference | Use it for |
|---|---|
| [Fabric CI/CD overview](https://learn.microsoft.com/en-us/fabric/cicd/cicd-overview) | Deployment-route choices and a CI/CD reference architecture. |
| [Plan CI/CD for Fabric solutions](https://learn.microsoft.com/en-us/fabric/fundamentals/understand-best-practices-fabric-cicd) | Source control, environment design, and automation planning. |
| [Lifecycle best practices](https://learn.microsoft.com/en-us/fabric/cicd/best-practices-cicd) | Development/Test/Production responsibilities and recovery limits. |
| [Choose a Fabric deployment pattern](https://learn.microsoft.com/en-us/azure/architecture/data-guide/technology-choices/fabric-deployment-patterns) | Tenant, capacity, and workspace topology trade-offs. |
| [Fabric Well-Architected](https://learn.microsoft.com/en-us/azure/well-architected/microsoft-fabric/overview) | Reliability, security, performance, cost, and operational readiness. |
| [fabric-cicd / Azure DevOps tutorial](https://learn.microsoft.com/en-us/fabric/cicd/tutorial-fabric-cicd-azure-devops) | A file-based automation example to extend with these release controls. |
| [Native pipeline automation example](https://github.com/microsoft/fabric-toolbox/tree/main/accelerators/CICD/Deploy-using-Fabric-deployment-pipelines) | An alternative native-route starting point, subject to item/identity support. |
