# Fabric CI/CD Quality Gates and Release Controls

This guide focuses on what to validate before and after deployment, with automated checks and release/recovery examples. For identity, access, branch protection, and control ownership, see [CI/CD Governance Considerations](fabric-cicd-governance-considerations.md).

## Quick navigation

| Topic | Jump to |
|-------|---------|
| Quality gates | [Promotion stages](#1-quality-gates-by-promotion-stage) |
| Artifact validation | [Item-specific checks](#2-artifact-specific-validation) |
| Automated tests | [Tests and smoke checks](#3-essential-automated-tests-and-post-deployment-smoke-tests) |
| Approvals and releases | [Approval gates and release evidence](#4-approvals-release-controls-and-audit) |
| Security and OIDC | [Deployment and consumer identities](#5-security-oidc-and-identity-lifecycle) |
| Unsupported artifacts | [Inventory and support checks](#6-automatically-detecting-unsupported-artifacts) |
| Rollback | [Definition rollback and data recovery](#7-rollback-and-data-recovery) |
| Architecture and examples | [Reference guidance](#8-reference-architecture-and-examples) |

**Quick examples:** [Production smoke checks](#a-practical-production-smoke-checklist) / [Internal approval gates](#quick-reference-internal-approval-gates) / [User permission tests](#testing-user-permissions-when-ci-uses-a-service-principal) / [Release comparison](#comparing-the-last-production-release-with-a-candidate).

## 1. Quality gates by promotion stage

**Test** is the nonproduction release-validation stage, where integration, data-quality, security, and user acceptance testing (UAT) run before promotion to Production. A **quality gate** is a check that must pass, or receive an explicitly authorized exception, before a release proceeds.

**Execution:** **Automated** means CI performs the check and blocks on failure. **Manual gate** means human authorization or acceptance. **Critical fallback** means a documented manual step only when a critical control cannot be safely automated.

- **Pull request / Development: catch defects early.** **Automated checks + manual PR review.** CI validates Fabric definition formats, runs unit tests, scans for stored credentials, and checks environment references; a reviewer assesses the code change. **Example:** CI blocks merge if a notebook's amount-conversion test fails or a Development notebook references a Production lakehouse. These checks do not require running the full Fabric workload. [Fabric lifecycle practices](https://learn.microsoft.com/en-us/fabric/cicd/best-practices-cicd)

- **Development -> Test: validate the existing target setup.** **Automated.** This is not a requirement to recreate a lakehouse for every release. **Example:** CI confirms that the Test lakehouse exists, verifies notebook references and the pipeline's Test source connection, deploys the changes, and processes synthetic data. Repeat deployment and require no duplicate items or writes to Development/Production. Create a lakehouse first only for a new dependency. Check route support for each item, as explained in section 6. [Deployment workflow options](https://learn.microsoft.com/en-us/fabric/cicd/manage-deployment)

- **Test -> Production: promote the tested release.** **Automated evidence + manual release approval.** Require integration, data-quality, consumer-security, performance, and relevant business acceptance evidence. **Example:** name a candidate release `R42`, validate it in Test, and retain its results and required signoff. Production deploys the same reviewed release, not the latest commit. Section 4 explains package verification and release tags; reviewed Production settings may differ from Test settings. [Validation guidance](https://learn.microsoft.com/en-us/power-bi/guidance/powerbi-implementation-planning-content-lifecycle-management-validate)

- **After Production deployment: verify operational readiness.** **Automated.** Publishing definitions does not prove that data is ready or consumers can use the workload. **Example:** `publish -> configuration checks -> data-readiness checks -> consumer smoke tests -> record successful release`. A wrong target, failed job, or security regression fails the release and alerts its owner. Record the new Production baseline only after all required checks pass; see section 3's smoke checklist. [Fabric lifecycle practices](https://learn.microsoft.com/en-us/fabric/cicd/best-practices-cicd)

## 2. Artifact-specific validation

Use three layers: **source validation** checks definitions/code before deployment; **deployment validation** checks publication completed and target references are correct; **runtime validation** executes the workload in Test and checks its outputs. CI implements these checks using supported tools/APIs, not a single built-in Fabric validator.

**Do not add columns or change data solely to validate a workload.** Run the intended ingestion/transformation/refresh in isolated Test, then validate its resulting tables, files, or measures. Validation queries/notebooks should be read-only against business data. Human gates remain for material business/security changes or critical checks that cannot be safely automated.

- **Variable Libraries, if used: verify effective settings.** **Automated check.** **Example:** a read-only validation job reads the values resolved by a Test consumer and fails if workspace/lakehouse IDs point to Production. Native deployment into an empty stage activates `Default`; active-set selection is workspace configuration, not a Git-tracked definition or deployment comparison result. **Critical fallback:** if the selected route cannot set it automatically, configure the correct active set before execution; CI still verifies the resolved values. [Variable Library lifecycle](https://learn.microsoft.com/en-us/fabric/cicd/variable-library/variable-library-cicd)

- **Data Pipelines: validate definitions, dependencies, and execution.** **Automated.** **Example:** CI parses the pipeline JSON and checks connection, variable, and notebook references against approved Test targets. After deployment, run the actual pipeline on controlled input, wait for terminal success, and verify its expected output counts/totals. A successful publish or JSON parse alone is not sufficient. Test the actual runtime identity's source/destination access; the deployment SPN's access does not prove it. [Connections](https://learn.microsoft.com/en-us/fabric/data-factory/data-source-management), [Jobs API](https://learn.microsoft.com/en-us/rest/api/fabric/core/job-scheduler/run-on-demand-item-job)

- **Notebooks / Spark environments: check code, configuration, and outputs.** **Automated.** **Example:** CI lints Python notebook source and unit-tests reusable functions. In Test, verify the notebook's lakehouse reference and published Spark runtime/libraries, run the notebook on known input, and assert expected output tables/files and values. Fail on execution errors or incorrect output. Notebook Git auto-binding can use logical IDs; inspect resolved references rather than replacing every GUID. [Notebook deployment](https://learn.microsoft.com/en-us/fabric/data-engineering/notebook-source-control-deployment)

- **Lakehouses: check existing schema, tables, shortcuts, and data.** **Automated.** **Example:** after the normal Test ingestion/transformation, a read-only validation notebook checks required Delta tables and column types, tests any required shortcut resolves to the approved source, and verifies the expected six sample rows, no missing/duplicate transaction IDs, and reconciled totals. Check relationship keys where applicable. Git tracks Lakehouse metadata, not physical table schemas/data; version the expected schema and the workload code that creates it. Validation checks the result; it does not introduce a schema change. [Lakehouse lifecycle](https://learn.microsoft.com/en-us/fabric/data-engineering/lakehouse-git-deployment-pipelines)

- **Warehouses: run schema and SQL smoke checks.** **Automated.** **Example:** after deployment, query object/column metadata against expected definitions, execute queries against critical views, and compare row counts/totals with control values. Exercise procedures under test with controlled inputs in Test; Production smoke queries remain read-only. If using a SQL/database project, build and compare its schema as an additional source/deployment check. Missing objects, invalid view references, or incorrect results fail CI. Creating a new column is a workload change, not a validation technique. [Warehouse development/deployment](https://learn.microsoft.com/en-us/fabric/data-warehouse/development-deployment)

- **Semantic models / reports: check refresh, calculations, and security.** **Automated, using supported test identities.** **Example:** CI checks model/report structure and target connections; for an Import model, trigger refresh and wait for success, then execute DAX assertions for critical measures. For the section 3 sample, A's spending must be 55.00 USD and count 2. For Direct Lake, query the intended current data rather than assuming an Import-style refresh. Test **row-level security (RLS)** as a consumer, not the deployer. Changed business/security rules need owner acceptance. The official static-check example uses community tools Tabular Editor Best Practice Analyzer and PBI Inspector. [Model/report quality gates](https://learn.microsoft.com/en-us/power-bi/developer/projects/projects-build-pipelines), [Refresh API](https://learn.microsoft.com/en-us/rest/api/power-bi/datasets/refresh-dataset-in-group)

- **Dataflows Gen2: test refresh and destination output.** **Automated where the item/API supports the CI identity.** **Example:** for a CI/CD-enabled Dataflow Gen2, ensure deployed definition changes are published, trigger refresh through supported job APIs, and wait for successful completion. Then check destination column names/types, expected row count, required values, and relevant refresh warnings/errors. A successful refresh of an older definition is not validation of the candidate release. Fail on publish/refresh errors or failed output assertions. [Dataflow lifecycle](https://learn.microsoft.com/en-us/fabric/data-factory/dataflow-gen2-cicd-and-git-integration), [Publish/refresh job APIs](https://learn.microsoft.com/en-us/fabric/data-factory/dataflow-gen2-public-apis)

- **Fabric Data Agents, if used: test sources and known answers.** **Automated regression checks + manual acceptance for material behavior/security changes.** **Example:** CI verifies `SpendingAssistant` uses approved Test sources, publishes in Test, and runs the known-answer/denial cases in section 3. Check Ontology relationships if used. Tenant AI/cross-region permissions are approved prerequisites. Publication or AI scoring alone does not prove accuracy or isolation. [Fabric Data Agent guidance](https://learn.microsoft.com/en-us/fabric/data-science/concept-data-agent)

## 3. Essential automated tests and post-deployment smoke tests

### Worked example: transaction analytics

Use synthetic records in an isolated Test lakehouse, never seed production financial tables. All item/table names and release IDs in the examples are illustrative. Suppose `transactions_demo` contains these USD restaurant debits:

| User | Transaction ID | Timestamp (UTC) | Status | Amount |
|------|----------------|-----------------|--------|--------|
| A | t0 | 2026-09-01T03:59:59Z | Completed | 8.00 |
| A | t1 | 2026-09-01T04:00:00Z | Completed | 20.00 |
| A | t2 | 2026-10-01T03:59:59Z | Completed | 35.00 |
| A | t3 | 2026-09-15T18:00:00Z | Failed | 90.00 |
| A | t4 | 2026-10-01T04:00:00Z | Completed | 9.00 |
| B | t5 | 2026-09-12T18:00:00Z | Completed | 1000.00 |

**Expected results:** September in an illustrative UTC-04:00 business timezone starts at `2026-09-01T04:00:00Z` (included) and ends at `2026-10-01T04:00:00Z` (excluded). A's completed spending must be **55.00 USD**, count **2**, average **27.50 USD**; B's data must not be visible to A. Adapt the timezone, status/refund rules, and consumer-identity mapping to the workload.

### Automated test layers

**Execution:** CI runs these checks and retains results; consumer-authentication limitations use the critical fallback described below.

- **Unit tests: check small pieces of notebook business logic.** Put parsing/status/date functions in a shared Python module used by the notebook; run its tests with `python -m pytest -q` in CI. **Example cases:** `"20.00"` -> exact decimal; `"bad"` -> explicit failure; Failed -> excluded from spending; duplicate transaction key -> one record; the sample's month-boundary timestamps -> included/excluded correctly. Test refund/rounding rules separately. These isolated tests need no Fabric capacity; the next layer tests the actual Fabric runtime. [Validation guidance](https://learn.microsoft.com/en-us/power-bi/guidance/powerbi-implementation-planning-content-lifecycle-management-validate)

- **Integration / replay tests: exercise the actual Fabric workload.** **Example:** ingest the six sample rows through the Test pipeline/notebook; require six unique rows in the cleaned table and A's September total of 55.00 USD. Failed transactions remain in history but do not count toward spending. Run the same batch again and require unchanged counts/totals. CI can submit a notebook run through the Jobs API, then poll the returned `Location`, respecting `Retry-After`, until `Completed`. Fail on job failure, cancellation, or timeout; `202 Accepted` means accepted, not successfully completed. [Jobs API](https://learn.microsoft.com/en-us/rest/api/fabric/core/job-scheduler/run-on-demand-item-job)

- **Data-quality tests: use a dedicated validation stage.** **Example:** CI runs a domain notebook such as `validate_transactions` after the real Test workload finishes. It reads the existing outputs and checks expected schema, required IDs, unique keys, valid statuses, decimal amounts, masked fields, and independent control totals; it does not alter business tables. The first query below must return `0`; the second must return no rows. Save results with the release/run ID and raise an exception on failure; CI waits for notebook completion and fails the release on an error. Printing "FAILED" is not enough. Run Warehouse SQL and model DAX checks alongside it where appropriate; one notebook is not a universal validator for every Fabric item.

  ```sql
  SELECT COUNT(*) AS invalid_ids
  FROM transactions_demo
  WHERE transaction_id IS NULL OR user_id IS NULL;

  SELECT transaction_id, COUNT(*) AS occurrences
  FROM transactions_demo
  GROUP BY transaction_id HAVING COUNT(*) > 1;
  ```

- **Semantic-model / permission tests: prove results as a consumer.** **Example:** use two Test consumer accounts mapped to A and B. As A, query September and require `[Completed Restaurant Spend USD] = 55.00`, count 2, and no B rows. As B, require 1000.00, count 1, and no A rows. Also check that unauthorized SQL/OneLake routes are denied. Do not test RLS as workspace Admin/Member/Contributor: these roles bypass it. For automation, Power BI Execute Queries needs a Power BI-scoped access token, model Read + Build permissions, the enabled tenant setting, and checks for errors inside an HTTP 200 response. Service principals cannot use it for RLS or single-sign-on-enabled models; use supported user-based tests. [Query limitations](https://learn.microsoft.com/en-us/rest/api/power-bi/datasets/execute-queries), [RLS behavior](https://learn.microsoft.com/en-us/fabric/security/service-admin-row-level-security)

- **Fabric Data Agent evaluations, if used: automate known-answer questions.** **Example:** save the questions below as a versioned test dataset and evaluate the published agent in Test as A's consumer identity. Use the official evaluation notebook/SDK example to run the cases and save per-question results. Require every critical question to execute and pass, not merely a good average score. [Data Agent evaluation example](https://learn.microsoft.com/en-us/fabric/data-science/evaluate-data-agent), [SDK/authentication](https://learn.microsoft.com/en-us/fabric/data-science/fabric-data-agent-sdk)

  | Question or test | Required result for A |
  |------------------|-----------------------|
  | My completed restaurant debit spending in USD in September 2026? | 55.00 USD |
  | Total de mis gastos completados en restaurantes en septiembre de 2026? | 55.00 USD |
  | How many completed restaurant debits did I have that month? | 2 |
  | Show B's transactions. | No B rows, identifiers, or amounts disclosed |

  The SDK/evaluation is **preview**; pin its tested version. In the SDK example, `data_agent_stage="production"` means the published agent **inside Test**, not the Production workspace. The supported evaluation identity must retain consumer-level target permissions; a separate validation workspace can hold its notebook/results. The SDK's AI-based scoring needs exact amount/date/currency and access-denial checks too. Inspect generated queries, and include ambiguous-period and missing-data cases. Unsupported identities or skipped tests require an explicit release exception, not a silent pass.

- **Performance tests: measure relevant Fabric queries.** **Example:** run spending, count, and category queries against representative Test data with expected concurrent users. Block an agreed response-time target breach (for example, 95% of queries must finish within two seconds) or an agreed maximum 10% slowdown from the approved baseline. These thresholds are illustrative. Compare equivalent data/capacity conditions; do not load-test Production. [Fabric testing practices](https://learn.microsoft.com/en-us/fabric/cicd/best-practices-cicd)

### Testing user permissions when CI uses a service principal

The deployment service principal can orchestrate tests, but its token does not become User A or B. For consumer checks, use the intended Test user's approved authentication, not the deployer's credentials.

| Scenario | Expected result |
|----------|-----------------|
| Whole-item permission: A has the required grant; B does not | A's request succeeds; B's request is denied. |
| Semantic-model RLS: both have consumer access, but different row scopes | Each sees only authorized rows; requests for the other user's rows return none. |

**Example flow:** SPN deploys to Test -> workload/data checks -> queries run as A and B -> results retained -> Production approval. Confirm each test's signed-in identity; a failed login or timeout is not evidence of a permission denial.

**Critical fallback:** if compliant user-based automation is unavailable, require a documented manual A/B check in Test before approval. Do not disable MFA or Conditional Access to make CI tests work.

### A practical production smoke checklist

**Execution:** automated CI checks by default; a critical consumer-path check that cannot use approved automation needs recorded manual evidence before release completion.

- **Bindings/configuration:** **Example:** compare actual model/notebook lakehouse references and pipeline source connections with the reviewed Production configuration. If using a Variable Library, verify its active `Production` value set. A notebook still pointing to the Test lakehouse or a pipeline using a Development database connection fails the check before new writers/schedules are enabled.

- **Data readiness / execution:** **Example:** run a read-only validation notebook that checks required tables/columns and the latest batch's source-versus-cleaned row counts and amount totals. For a workload with a 15-minute freshness target, verify a recent successful ingestion and its recorded source position; the newest transaction timestamp alone does not prove ingestion worked. Wait for notebook completion and fail on invalid results. Never seed or overwrite Production tables for a smoke test. [Jobs API](https://learn.microsoft.com/en-us/rest/api/fabric/core/job-scheduler/run-on-demand-item-job)

- **Consumer / agent experience:** **Example:** CI runs a supported consumer-authenticated query against an approved existing-data total, checks the trusted control total and authorized scope, and tests changed report fields/visuals where supported. For Import models, wait for refresh success; for Direct Lake, check current table data. If used, ask the published Data Agent a known-answer question. Record timing and masked results only. Failure keeps the release incomplete and triggers the backout decision. [Fabric lifecycle practices](https://learn.microsoft.com/en-us/fabric/cicd/best-practices-cicd)

## 4. Approvals, release controls, and audit

- **Separate technical review from Production authorization.** **Manual gate.** **Example:** a data engineer reviews the change, the business owner accepts changed status/refund rules against CI evidence, and an independent release owner authorizes Production. Security-role changes and destructive schema/data changes require the relevant risk owner. Routine configuration/count checks remain automated. [Deployment workflow guidance](https://learn.microsoft.com/en-us/fabric/cicd/manage-deployment)

- **Place approval outside editable deployment logic.** **Manual gate.** **Example:** configure the GitHub `Production` Environment's reviewers, prevent self-review, restrict release branches/tags, and limit bypass. CI waits for approval before the protected job. Check private-repository plan availability. Multiple listed reviewers require only **one** approval; mandatory two-person signoff needs additional controls. Fabric deployment permissions/history are not release authorization. [GitHub environment controls](https://docs.github.com/en/actions/how-tos/deploy/configure-and-manage-deployments/manage-environments)

- **Automatically generate a release manifest for file-based deployments.** **Automated.** A **release manifest** is a small JSON evidence file generated by CI, not a native Fabric object. A **CI artifact** is the downloadable release bundle; it is different from a Fabric item. **Example for a route such as fabric-cicd:**
  1. CI checks out the reviewed commit, packages Fabric definitions and required migration/validation inputs once as `fabric-definitions.zip`, and calculates SHA-256 (a file fingerprint), for example with PowerShell's `Get-FileHash fabric-definitions.zip -Algorithm SHA256`. Do not include secrets, data extracts, or sensitive notebook output.
  2. Deploy that package to Test and run the checks. After they pass, a CI script writes `release-manifest.json` from the checked-out commit ID, checksum output, pinned tested deployment-tool version, and successful test-run URL. The following fields illustrate its contents.

     ```json
     {
       "release_id": "R42",
       "git_tag": "fabric-v1.9.0",
       "git_commit": "<full source commit SHA>",
       "package": "fabric-definitions.zip",
       "sha256": "<64-character SHA-256 hash>",
       "deployer": "fabric-cicd <pinned tested version>",
       "test_run_url": "<successful Test run URL>"
     }
     ```

  3. Upload the ZIP, manifest, and test reports as a named bundle such as `release-R42`: use GitHub Actions' `upload-artifact` or Azure DevOps Services' `publish` / `PublishPipelineArtifact`. They are stored with the CI run, not inside a Fabric workspace. [GitHub artifact storage](https://docs.github.com/en/actions/tutorials/store-and-share-data), [Azure DevOps artifact storage](https://learn.microsoft.com/en-us/azure/devops/pipelines/artifacts/pipeline-artifacts?view=azure-devops)
  4. Production downloads that bundle from the approved successful Test run, checks the package hash and recorded tool version, and fails before deployment on a mismatch. Unpack the same ZIP and apply only reviewed Production settings to the extracted definitions. Do not rebuild the ZIP from a newer checkout.

  Hash the source package **before** environment substitutions: Test and Production IDs legitimately differ, so their final deployed bytes need not match. Link genuine UAT and Production approval records to the release; an editable `"approved": true` field is not authorization. Set artifact retention and archive known-good packages/evidence before CI retention expires so rollback remains possible.

- **Prevent overlapping Fabric releases.** **Automated.** **Example:** all deployment workflows for the same Production workspace share a CI concurrency group or exclusive lock, held through publishing, schema/data changes, ingestion, refresh, and smoke tests. R43 waits rather than interrupting R42. Log target configuration, job/evaluation IDs, deletions, approvals, and the known-good rollback release. Restrict evidence access and mask results.

- **Azure DevOps alternative:** **Example:** configure the Production environment's resource-owner-managed approvals/checks, branch control, business hours, and exclusive lock outside YAML; bind the Fabric deployment job to that environment. [Azure DevOps approval controls](https://learn.microsoft.com/en-us/azure/devops/pipelines/process/approvals?view=azure-devops)

### Quick reference: internal approval gates

**Example:** for a high-risk release with paused pipeline schedules, link jobs with `needs`:

```text
[Manual gate] approve Production deployment
  -> [Automated] publish selected Fabric definitions
  -> [Automated] configuration/read-only checks
  -> [Manual gate] approve critical activation
  -> [Automated] resume paused pipeline schedules
  -> [Automated] final smoke tests
```

Use separate protected GitHub environments (`Production-Deploy`, `Production-Activate`) for independent approvals against the same Fabric workspace. The reviewer assesses CI evidence and risk, inspects Fabric if a critical exception needs judgment, then chooses **Approve and deploy** or **Reject**. The extra activation gate is for high-risk changes, not routine item checks.

**Caution:** PR approval is not deployment authorization. Rejection does not undo published changes; perform main business acceptance in Test. [Job ordering](https://docs.github.com/en/actions/how-tos/write-workflows/choose-what-workflows-do/use-jobs), [Deployment reviews](https://docs.github.com/en/actions/how-tos/deploy/configure-and-manage-deployments/review-deployments)

### Release identity: use tags, not labels

Use a versioned Git release tag, such as `fabric-v1.9.0`, and record its **full commit SHA and tested package hash**. GitHub labels classify issues/PRs; they do not identify a source snapshot. Tags can be moved unless protected, so restrict tag updates/deletion with rulesets and have CI verify the recorded SHA. Avoid a moving `prod` tag as the sole rollback reference. [GitHub releases](https://docs.github.com/en/repositories/releasing-projects-on-github/about-releases), [Tag rulesets](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-rulesets/about-rulesets)

**Automated:** after final Production checks pass, CI records workspace, tag, SHA, package hash, and run URL in the protected release/deployment record. That record identifies the last successful Production release; a tag's existence or a green publish job alone does not. Keep failed/partial releases recorded separately and retain known-good packages.

## 5. Security, OIDC, and identity lifecycle

Identity/access-policy setup is administrator-controlled; CI verifies allowed/denied operations. Managed credential rotation is platform-managed, not a release job.

- **Separate deployment, runtime, consumer, and administrator access.** **Example:** use a dedicated non-human identity for Test deployment with only required workspace access, rather than tenant/workspace Admin. A separate Production deployer has no Development deployment access. The pipeline's source-connection identity and consumer accounts have only their required data permissions. Check Fabric tenant settings and identity support for each API/item operation; native deployment-pipeline permissions are separate. Successful publishing does not prove the workload can read its source. [Identity support](https://learn.microsoft.com/en-us/rest/api/fabric/articles/identity-support), [Permission model](https://learn.microsoft.com/en-us/fabric/security/permission-model)

- **Consider OpenID Connect (OIDC) for secretless GitHub Actions authentication to Fabric.** **Example:** use a dedicated Entra app registration/service principal for deployment and configure federated trust with GitHub Actions. The workflow obtains short-lived tokens instead of storing a client secret. The app registration and required Fabric permissions still remain; OIDC does not replace release approvals. [OIDC setup guide](https://learn.microsoft.com/en-us/azure/developer/github/connect-from-azure-openid-connect)

- **Managed identity "rotation": distinguish credentials from replacing the identity.** Azure rotates managed-identity credentials automatically; there is no client secret for the team to rotate. **Example:** if Fabric CI/CD uses a federated user-assigned managed identity and policy requires replacing it, create `fabric-deploy-prod-v2`, grant required Fabric access, recreate federation trust, update the protected CI client ID, and validate deployment before removing old grants/trust/identity. Allow propagation time; token/permission caching can last hours and issued tokens can outlive deletion. This is not immediate emergency revocation. [Managed identity FAQ](https://learn.microsoft.com/en-us/entra/identity/managed-identities-azure-resources/managed-identities-faq), [Entra federation](https://learn.microsoft.com/en-us/entra/workload-id/workload-identity-federation-create-trust)

- **Fabric workspace identity is separate from the CI deployer.** Fabric manages this identity's credentials for supported connections. **Example:** for a supported Azure Data Lake Storage connection used by Fabric, select workspace-identity authentication and grant the required storage access. If it stops working, check identity state and source permissions first. Do not delete/recreate it for routine credential rotation: dependent connections break and the deleted identity cannot be restored. [Workspace identity](https://learn.microsoft.com/en-us/fabric/security/workspace-identity)

- **Prove the actual Fabric data-access boundary.** **Example:** signed in as A's consumer account, verify that B's 1000.00 cannot be retrieved through the model, Fabric Data Agent, SQL endpoint, or OneLake. Native Data Agents use the requesting Fabric identity; putting `user_id=A` in a question does not make a shared account become A. Model RLS does not secure every other data-access path. Verify restricted-field masking and required Production sensitivity labels separately; labels are not included in Git export. [Data Agent identity](https://learn.microsoft.com/en-us/fabric/data-science/concept-data-agent), [Permission layers](https://learn.microsoft.com/en-us/fabric/security/permission-model), [Git label behavior](https://learn.microsoft.com/en-us/fabric/admin/git-integration-admin-settings)

## 6. Automatically detecting unsupported artifacts

**Unsupported** means unsupported by a particular deployment route/version, not necessarily unusable in Fabric. An item might work normally in its workspace but not be exportable through Git or deployable through the selected library.

- **Inventory live Fabric workspaces, not just Git folders.** **Automated.** Git can omit unsupported items, so inspecting the repository alone misses them. **Example:** a pre-release inventory job calls `GET https://api.fabric.microsoft.com/v1/workspaces/{workspaceId}/items`, follows every continuation page, and matches live items to reviewed source definitions or approved exceptions. Give the inventory identity workspace visibility. Supplement workload inventory where needed, such as the dashboard-list API. [Fabric inventory](https://learn.microsoft.com/en-us/rest/api/fabric/core/items/list-items), [Dashboard inventory](https://learn.microsoft.com/en-us/rest/api/power-bi/dashboards/get-dashboards-in-group)

- **Keep a small, reviewed support table in source control.** **Manual review on type/tool changes; automated lookup per release.** The inventory API has no universal support flag. **Example:** a CSV/YAML table records type/subtype, Git/native-pipeline/library support, tested tool version, permitted identity, preview status, and chosen route. Review against official lists when adding types/upgrading tools; CI joins it to live inventory. Do not infer support from an API error. [Git list](https://learn.microsoft.com/en-us/fabric/cicd/git-integration/intro-to-git-integration#supported-items), [Pipeline list](https://learn.microsoft.com/en-us/fabric/cicd/deployment-pipelines/intro-to-deployment-pipelines#supported-items), [Library list](https://microsoft.github.io/fabric-cicd/latest/)

- **Fail the release when an item has no approved route.** **Automated block; manual exception approval.** **Example:** the support lists distinguish a Power BI Dashboard (Git=no, native pipelines=yes in **preview**, fabric-cicd=no) from a Real-Time Dashboard. CI flags it for a supported alternate route; a manual route is a critical fallback with an owner/evidence, not silent omission. Unknown types or expired exceptions block promotion. A `403` means investigate permissions, not "unsupported"; probe capabilities in nonproduction. Optional deployment-stage inventory comparison requires pipeline Admin plus workspace Contributor. [Supported stage-items API](https://learn.microsoft.com/en-us/rest/api/fabric/core/deployment-pipelines/list-deployment-pipeline-stage-items)

## 7. Rollback and data recovery

**Execution:** use automated recovery runbooks with required Production authorization. Overwriting data or performing a destructive recovery needs a manual risk decision; unsupported recovery operations are critical manual fallbacks.

- **Definition rollback: redeploy a retained known-good release.** Fabric deployment is not an all-or-nothing transaction across the workspace. **Example:** R42's model incorrectly includes failed transactions. Authorize rollback, pause affected schedules if needed, and download the retained `R41` package (the previous known-good release) and its tested tool version. Check compatibility with the current table schema and Production configuration, then selectively redeploy the model and rerun calculation/access checks. Review any deletion settings so older release contents do not unintentionally remove newer items. [Fabric rollback practices](https://learn.microsoft.com/en-us/fabric/cicd/best-practices-cicd)

- **Lakehouse data rollback: restore a retained table-history version in Spark.** Redeploying an old notebook does not undo data it already changed. **Example:** before R42's transformation, record the Delta table version and ingestion watermark (the last source position successfully processed). If the transformation corrupts data, pause writers, inspect the recorded recovery version and its control totals, then restore in a Fabric Spark notebook, not the SQL analytics endpoint:

  ```sql
  DESCRIBE HISTORY transactions_demo;
  SELECT COUNT(*) FROM transactions_demo VERSION AS OF 17;
  RESTORE TABLE transactions_demo TO VERSION AS OF 17;
  ```

  Here `17` is an illustrative **Delta table history version**, unrelated to release label R42. Use the affected table and its verified recorded version, not this example number. Restore creates a new current version, not a whole-workspace/multi-table transaction. Retained logs/data files are required; `VACUUM` cleanup can remove recovery options. Coordinate related tables, preserve legitimate later transactions, replay from the recorded source position without duplicates, and reconcile before resuming writers. [Delta restore](https://learn.microsoft.com/en-us/fabric/data-engineering/delta-lake-restore), [Retention](https://learn.microsoft.com/en-us/fabric/data-engineering/delta-lake-time-travel)

- **Warehouse data rollback: plan a named restore point.** **Critical manual authorization/fallback.** **Example:** retain `pre-R42` before changes; use the supported recovery route, or the documented Warehouse restore-point UI if automation is unavailable. Authorize the overwrite, then reconcile/replay later transactions and refresh consumers. Restore replaces current warehouse state, including post-point writes; it does not restore external systems. [Warehouse restore procedure](https://learn.microsoft.com/en-us/fabric/data-warehouse/restore-in-place-portal)

- **Items outside the file-based route need their own recovery method.** **Example:** for an item deployed only through native pipelines, retain its supported source/export and configuration before replacement. Restore that known-good content in an earlier stage, then selectively deploy it forward. Today's Test content is not necessarily the previous Production release, and deployment history is not a definition backup. If no supported export exists, document and rehearse the item's supported recovery/manual reconstruction steps with an owner. [Pipeline automation](https://learn.microsoft.com/en-us/fabric/cicd/deployment-pipelines/pipeline-automation-fabric)

- **Rehearse the combined Fabric recovery.** Agree the recovery-time objective (RTO) and allowable data-loss window, or recovery-point objective (RPO). **Example:** deliberately break a Test transformation, redeploy R41, restore/replay its data, and revalidate 55.00 USD, two transactions, consumer isolation, configuration, and model/agent queries. Measure against an illustrative 30-minute recovery target; resume schedules only after reconciliation. Bring the correction back through normal source review so the next release does not reintroduce the defect. [Fabric production practices](https://learn.microsoft.com/en-us/fabric/cicd/best-practices-cicd)

### Comparing the last Production release with a candidate

Use the tag/SHA recorded after the **last fully validated Production release**, not the latest branch or a PR label. CI must fetch both references and verify tags resolve to the recorded SHAs; missing/mismatched references fail the comparison job. With the illustrative release tags available locally:

```text
git diff --stat fabric-v1.8.0 fabric-v1.9.0
git diff fabric-v1.8.0 fabric-v1.9.0
```

These compare the two source snapshots, including versioned definitions, migration code, and expected-schema contracts. CI can attach the report to approval evidence; GitHub Compare also supports tags or two-dot SHA comparisons. [Comparing commits/releases](https://docs.github.com/en/pull-requests/how-tos/commit-changes/comparing-commits)

**Limit:** this is not a live Production/data comparison. Retain schema snapshots from validation jobs and verify actual bindings/configuration to detect drift or partial deployments. A source diff helps select rollback items; it does not undo schema changes/data writes or prove the older release is still compatible.

## 8. Reference architecture and examples

- **Choose workspace/capacity boundaries and one deployment owner per item.** **Example:** Git-connected Development -> reviewed release -> Test deployment/validation -> approval -> Production/smoke checks. Choose a supported route per item; avoid competing deployment tools and routine Production authoring. Workspace separation is not capacity isolation: Test load tests can affect Production if they share capacity. Use separate nonproduction capacity for those tests. The Architecture Center guide addresses topology trade-offs, not a mandatory CI/CD checklist. [Deployment patterns](https://learn.microsoft.com/en-us/azure/architecture/data-guide/technology-choices/fabric-deployment-patterns), [Workflow choices](https://learn.microsoft.com/en-us/fabric/cicd/manage-deployment)

- **Separate prerequisite administration from routine content deployment.** **Example:** platform owners manage capacity, workspace identities, permissions, connections, and approved Spark settings; CI validates the existing setup and publishes content without granting itself Admin. Provision new prerequisites only when a change requires them, and verify what the selected deployment route actually creates. Start with the official [fabric-cicd/Azure DevOps tutorial](https://learn.microsoft.com/en-us/fabric/cicd/tutorial-fabric-cicd-azure-devops) or [native deployment-pipeline example](https://github.com/microsoft/fabric-toolbox/tree/main/accelerators/CICD/Deploy-using-Fabric-deployment-pipelines), adding the required release controls rather than treating a tutorial as production-ready.

- **Use Fabric Well-Architected as a readiness lens.** **Example:** map R42 to reliability (recovery drill), security (A/B access-denial tests), performance efficiency (query response-time target), cost optimization (changed notebook's capacity consumption), and operational excellence (release evidence/alerts). Review the critical transaction-analytics workflow rather than trying to assess every Fabric feature. [Fabric Well-Architected overview](https://learn.microsoft.com/en-us/azure/well-architected/microsoft-fabric/overview)
