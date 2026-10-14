# Fabric CI/CD Governance Considerations

> Reference implementation: https://github.com/michaeldeongreen/microsoft-fabric-sdlc-patterns

Considerations for partners and customers designing governance around CI/CD pipelines for Microsoft Fabric. The topics below are scoped to the CI/CD pipeline itself — workspace setup, identities used by the pipeline, branch protection, deployment gating, and audit. Adjacent controls that sit outside the CI/CD pipeline (network controls, data classification, encryption, runtime data-access policies) are listed at the end under "Adjacent controls owned outside the CI/CD pipeline" — they are part of any mature production Fabric deployment but owned by your platform / security team rather than the CI/CD pipeline owner.

This guide layers governance controls on top of the implemented
[Release Process](fabric-release-process.md). Read that guide first if you do
not already understand the selected Test/Prod job.

For practical validation, release evidence, staged approval, and rollback examples, see [Fabric CI/CD Quality Gates and Release Controls](fabric-cicd-quality-gates-and-release-controls.md). It complements the governance controls here rather than replacing them.

The recommendations below are not all configured by the repository. Fork
owners create branch rules, required checks, Environment reviewers, and
identity permissions. The shipped workflows use client-secret authentication;
OIDC and additional release demonstrations are planned enhancements.

## Identity model

Confusing the orchestrator, credentials, runtime identity, and human
administrator is a common source of over-permissioned deployments.

| Actor or credential | Shipped responsibility | Managed by |
|---|---|---|
| GitHub Actions | Runs the reviewed job graph; it is not an identity | Repository administrator |
| Deployment service principal | Ensures Test/Prod connections, manages their connection ACLs, publishes items, and submits DataPipeline jobs | Entra application administrator; workspace administrator grants Contributor |
| GitHub Environment-variable PAT | Reads/creates the two connection-ID variables during preflight/persistence | Repository administrator and named rotation owner |
| Fabric Workspace Identity | Authenticates Notebook and semantic-model refresh activities | Fabric workspace administrator; Fabric manages the credential |
| Connections-admin group | Receives verified Owner on both stage connections | Entra group administrator |
| Feature workspace/connection administrator | Creates the feature Workspace Identity, grants its resource access, and creates its connection pair | Fabric/connection administrator |
| Feature developer | Own Git identity, Branch Out, local swaps, feature validation, and feature-to-Dev PR | The user's organization |
| Dev workspace operator | Updates Git-connected Dev, inspects bindings, and runs the Dev DataPipeline | Named workspace operator |
| Runtime workload UAMI | Optional identity for external Azure workloads calling Fabric; not used by this repository's release | Platform administrator |

The current workflows use a client secret for the deployment service
principal. OIDC can replace that stored secret, but it does not remove Fabric
permissions, the GitHub variable credential, runtime Workspace Identity, or
release approval. The planned
[OIDC demonstration](https://github.com/michaeldeongreen/microsoft-fabric-sdlc-patterns/issues/84)
is not implemented.

## Automated connection setup: the sample's privilege trade-off

Connections have tenant-level ACLs and are not Git-synced items. Workspace
Admin does not automatically confer connection visibility or use.

The shipped connection lifecycle is:

| Stage | Connection operation |
|---|---|
| Feature | A human creates the Workspace Identity pair |
| Dev | A repository administrator manually runs **Provision Fabric Connections** |
| Test/Prod | The selected release job creates or reuses the pair before publication |

For Test and Prod, the selected job:

1. uses the PAT to validate GitHub Environment access and saved IDs;
2. uses the deployment service principal to create/reuse the two Workspace
   Identity connections;
3. grants/upgrades and verifies the configured group as Owner;
4. uses the PAT to create missing ID variables without overwriting conflicts;
5. passes current-run IDs to the publisher;
6. publishes and submits the DataPipeline job.

The publisher subprocess fixes `FABRIC_CONNECTION_MODE=existing` and
`FABRIC_RUNTIME_AUTHENTICATION=WorkspaceIdentity`; it validates and consumes
the pair read-only. That does not make the containing deployment job read-only.

Humans create each Workspace Identity and grant workspace/resource permissions
first. The service principal does not provision identities, assign workspace
roles, change tenant settings, create groups, or manage membership.

Sharing one deployment service principal and one connections-admin group
across stages is a sample compromise, not environment isolation. An
Environment-specific `FABRIC_CONNECTION_ADMINS_GROUP_ID` can select a
stage-specific group. Developers normally need User on Dev/feature
dependencies, not Owner of Test/Prod connections.

The repository-scoped PAT has Contents read/write and Environments read/write.
It is on every selected Test/Prod release path, isolated to GitHub preflight
and persistence. Environments write is broader than two variable names and can
include other Environment-management operations. Use expiration and a named
rotation owner, or a separately scoped GitHub App, for production. Never expose
the token to feature code or developers who do not administer the repository.

The Fabric administrator must authorize the deployment principal through the
service-principal tenant settings, scoped to an approved service-principal
group. Fabric Git settings apply to the users performing Git operations; do
not use the service-principal allowlist as a substitute for an approved Git-user
scope. Workspace roles do not override tenant policy.

An enterprise alternative is to separate responsibilities:

| Responsibility | Typical permission boundary |
|---|---|
| Approved bootstrap identity | Connection-management authority; Workspace Admin when provisioning a Workspace Identity and appropriate permission-grant authority |
| Routine deployment identity | Contributor in its target workspace and User access to preprovisioned connections |
| Separate runtime principal or Workspace Identity | Only the notebook, model, and OneLake permissions required by the workload; do not automatically inherit the publisher's authority |

That enterprise separation is a recommended adaptation, not the shipped
Test/Prod job. The sample deliberately couples connection management and
publication in one protected job so a cold stage can fail closed before
publication rather than require a separate manual bootstrap.

Connection GUIDs are non-secret references; access tokens, credentials, and
Git provider tokens must stay outside Git.

A GitHub Environment's **required reviewer** is a useful approval gate before
privileged setup. Approval releases the job; it does **not** grant or elevate
Fabric permissions. If temporary elevation is required, use the organization's
approved privilege-management process or a separate privileged identity.
This sample does not implement PIM, silently grant the deploying principal
Admin, or claim that an Actions approval is an RBAC operation.

See [the setup and permission contract](SETUP.md#post-etl-refresh-permissions)
and the official [Create Connection](https://learn.microsoft.com/en-us/rest/api/fabric/core/connections/create-connection),
[Provision Identity](https://learn.microsoft.com/en-us/rest/api/fabric/core/workspaces/provision-identity),
and [developer tenant settings](https://learn.microsoft.com/en-us/fabric/admin/service-admin-portal-developer)
documentation.

## Security across workspaces

Environment isolation, RBAC, and identity boundaries.

| Concern area | Guidance |
|---|---|
| Environment isolation | <ul><li>One Fabric workspace and one GitHub Environment per stage (`Dev`, `Test`, `Prod`), each with its own workspace ID and scoped secrets</li><li>Branch-gated deploys keep environments siloed: `dev` maps to Dev, `test` to Test, and `main` to Prod</li><li>Deployment filters vary by method; plan routes also watch their code, dependencies, and plan paths. Tests run on every PR. See the [shared workflow reference](fabric-release-process.md#github-actions-workflows)</li></ul> |
| Tenant settings (Fabric admin) | <ul><li>Scope service-principal API and connection-creation settings to a dedicated group containing the approved deployment SPs, never the entire organization ([developer tenant settings](https://learn.microsoft.com/en-us/fabric/admin/service-admin-portal-developer))</li><li>Scope Fabric Git/GitHub integration settings to the users who perform Git operations ([Git integration tenant settings](https://learn.microsoft.com/en-us/fabric/admin/git-integration-admin-settings))</li><li>Do not reuse the SP allowlist as a substitute for the Git-user scope; they authorize different actors</li></ul> |
| Access control (RBAC) | <ul><li>The deployment SP gets Contributor on Dev/Test/Prod for connection management, publication, and job submission; it does not receive workload activity permissions or create Workspace Identities ([workspace roles](https://learn.microsoft.com/en-us/fabric/fundamentals/roles-workspaces#-workspace-roles))</li><li>A Fabric workspace administrator creates each Workspace Identity and grants the Notebook/model/OneLake rights required by the workload</li><li>The named Dev workspace operator updates Git-connected Dev and runs its DataPipeline; selected Test/Prod jobs ensure connections, publish, and submit the DataPipeline</li></ul> |
| CI/CD identity (deploys artifacts) | <ul><li>One Service Principal per environment in production (the demo uses one shared SP for simplicity)</li><li>Each SP scoped to Contributor on only its own workspace — Test compromise cannot touch Prod</li><li>SP secrets live in the matching GitHub Environment; `secrets: inherit` resolves the right values per env</li><li>Third-party actions pinned to full commit SHAs — supply-chain hardening</li></ul> |
| Runtime workload identity (Container Apps / Functions / AKS calling Fabric) | <ul><li>Use a user-assigned managed identity (UAMI), one per workload, per environment. UAMI is the [Microsoft-recommended default for Microsoft services](https://learn.microsoft.com/en-us/entra/identity/managed-identities-azure-resources/overview#managed-identity-types)</li><li>Multiple Azure services in the same environment get **separate UAMIs** unless they're replicated instances of the *same* workload (e.g., HA replicas of one service). Different workloads (ingestion Function vs. reporting Container App) should not share a UAMI — different permission needs and shared blast radius ([replicated-resources guidance](https://learn.microsoft.com/en-us/entra/identity/managed-identities-azure-resources/managed-identity-best-practice-recommendations#choosing-system-or-user-assigned-managed-identities))</li><li>UAMI lifecycle is decoupled from compute — admin can pre-create the UAMI and grant Fabric workspace access *before* the resource exists ([best practices](https://learn.microsoft.com/en-us/entra/identity/managed-identities-azure-resources/managed-identity-best-practice-recommendations#choosing-system-or-user-assigned-managed-identities))</li><li>Grant least privilege on the target workspace — typically Viewer + item-level (e.g., `ReadAll` on a specific Lakehouse), not Contributor</li><li>Use system-assigned identity (SAMI) only when you need per-resource audit attribution, or you require permissions to be auto-revoked when the resource is deleted</li><li>Caveat: anyone who can deploy/run code on a resource with a UAMI inherits all its permissions — one UAMI per workload keeps the blast radius small ([best practice warning](https://learn.microsoft.com/en-us/entra/identity/managed-identities-azure-resources/managed-identity-best-practice-recommendations#consider-the-effect-of-assigning-managed-identities-to-azure-resources-andor-granting-assign-permissions-to-a-user))</li></ul> |

## Manual approvals and revision processes

GitHub-native gates: code-review approval before merge (PR / branch protection), deploy-time approval before the workflow runs (Environment protection), and an audit trail across both.

| Concern area | Guidance |
|---|---|
| PR checks for revisions (gate before merge) | <ul><li>Require PRs into `dev`, `test`, and `main` — no direct pushes</li><li>Enforce a promotion path with source-branch restrictions: PRs into `test` must come from `dev`; PRs into `main` must come from `test`. PRs into `dev` are unrestricted (feature branches PR in)</li><li>Require the branch-specific status-check names listed in [Setup](SETUP.md#5-configure-github)</li><li>Require approving review(s) and code-owner review where configured; dismiss stale approvals when new commits are pushed</li><li>"Require conversation resolution before merging" forces reviewers' comments to be addressed</li><li>Require linear history / signed commits if compliance demands it</li><li>Restrict who can push to or bypass protection on the target branch</li><li>Configure these in Repository Settings → Rules → Rulesets ([branch protection rulesets](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-rulesets/about-rulesets)). Require the [promotion-path workflow's](.github/workflows/enforce-promotion-path.yml) status check on `test` and `main`; fork owners configure the policy separately</li><li>A PR author cannot supply their own required approving review. A single-developer fork must choose an appropriate review policy; deployment-approval self-review is a separate Environment setting</li></ul> |
| Deploy-time approval (gate before the workflow runs) | <ul><li>Configure GitHub Environment protection rules per environment (Settings → Environments → `Test` / `Prod`)</li><li>Add required reviewers — designated approvers must click "Approve and deploy" before the job starts; the run pauses in "Waiting" status until they do</li><li>Optional wait timer (e.g., 10 min) gives a window to abort an unintended deploy</li><li>Deployment branch restriction: e.g., only `main` can deploy to Prod — even if someone pushes the workflow file from a feature branch, it cannot target Prod</li><li>Approver set is independent from PR reviewers — supports separation of duties (devs approve code, Ops/Release approves Prod deploy)</li></ul> |
| Audit trail and revision history | <ul><li>Every PR, review, merge, and deploy approval is recorded in GitHub with actor, timestamp, and commit SHA</li><li>GitHub Actions run history shows who triggered, who approved, what ran, exit status, and full logs — exportable for audit</li><li>Git history is the revision log for definitions captured in the repository: require reviewed PRs for those changes; `git blame` / `git log` answers "who changed this and why"</li><li>Check Git and deployment-route support independently. Capture definitions/configuration where possible, including items unsupported by the chosen publisher; retain approvals and alternate-route evidence for items managed outside Git</li><li>Roll back versioned definitions by reverting the commit and merging — the same gates apply to the revert PR, so these rollbacks are also reviewed and approved</li></ul> |
| Rollback strategy (think about it before you need it) | <ul><li>Code rollback is the easy half: revert the commit and merge — the same PR gates apply, so the rollback is reviewed and audited like any other change</li><li>Data effects are harder and very company-specific. Things to think through with your team:<ul><li>Snapshotting / point-in-time-restore for Lakehouses and Warehouses before risky deploys</li><li>Whether downstream consumers (reports, agents, embedded apps) need a coordinated rollback or just the code revert</li><li>How to communicate downtime windows to business users</li><li>Which item types need a custom backout plan beyond `git revert` — anything that mutates data, not just definitions</li></ul></li><li>Test your rollback path in Test before you need it in Prod. A rollback you've never exercised is a hope, not a plan</li></ul> |

## Governance and compliance

Mapping the controls above to the three governance asks: audit, separation of duties, and enterprise standards.

| Concern area | Guidance |
|---|---|
| Audit requirements | <ul><li>Git history records changes to versioned definitions/configuration; require reviewed, signed-off commits. For definitions or settings that cannot be versioned, retain the approved procedure, actor, target, and release evidence separately</li><li>GitHub Actions run history captures who triggered each deploy, who approved it (Environment protection), exit status, and full logs — retained per org policy</li><li>PR conversations, review approvals, and merge events are timestamped and auditable (subject to your org's retention and governance settings)</li><li>This covers the CI/CD pipeline audit trail. Workspace-level activity audit (who *accessed* the workspace and what they did inside it) is owned outside the pipeline — see Adjacent controls below</li></ul> |
| Separation of duties | <ul><li>Code authors cannot approve their own PRs when required approvals are configured</li><li>PR reviewers and deploy approvers can be different people or teams</li><li>Use a privileged administrator for workspace/resource grants; the Contributor deployment SP cannot grant workspace roles</li><li>The sample separates deployment SP, GitHub PAT, Workspace Identity, and human connection administrator; production can further use per-environment instances</li><li>Dev uses a user's Fabric Git connection. Publishers and connection setup do not write commits or push to the repository</li></ul> |
| Enterprise governance standards | <ul><li>Promotion path is enforced by branch policy: nothing reaches Prod without going through `dev` → `test` → `main` with reviews and deploy approvals at each stage</li><li>Environment protection rules can require approvers from a specific GitHub team (e.g., `@release-managers`), giving the change-management function a hard gate</li><li>Optional deployment wait timer creates an abort window before Prod changes go live</li><li>Where code-owner reviews are required, CODEOWNERS routes sensitive paths to designated reviewers</li><li>Keep CODEOWNERS in version control if used. Branch rules and Environment protection are external GitHub settings that owners configure and audit separately; cloning workflow YAML does not establish them</li></ul> |

## Adjacent controls owned outside the CI/CD pipeline

These controls go beyond the CI/CD pipeline but are part of any mature Fabric production deployment. The right mix depends on your risk profile, regulatory posture, and licensing — some controls (e.g., Microsoft Purview, Customer-Managed Keys, Private Links) require specific Fabric / Microsoft 365 / Entra ID SKUs and may not be available in every tenant. They're listed separately because they sit with your platform / security / information-protection teams rather than the CI/CD pipeline owner. Surface them early in the conversation so the right specialists can scope and own them before you go to Prod.

| Area | What to raise with the owning team |
|---|---|
| Network controls | Tenant-level access can be hardened with [Microsoft Entra Conditional Access for Fabric](https://learn.microsoft.com/en-us/fabric/security/security-conditional-access) (MFA, IP, device compliance) and [Private Links](https://learn.microsoft.com/en-us/fabric/security/security-private-links-overview) to block public access. For firewalled ADLS Gen2, see [Trusted Workspace Access](https://learn.microsoft.com/en-us/fabric/security/security-trusted-workspace-access). |
| Encryption & data residency | OneLake [encrypts data at rest by default](https://learn.microsoft.com/en-us/fabric/security/security-fundamentals#data-at-rest). For regulated workloads, evaluate [workspace customer-managed keys](https://learn.microsoft.com/en-us/fabric/security/workspace-customer-managed-keys) and [multi-geo capacities](https://learn.microsoft.com/en-us/fabric/admin/service-admin-premium-multi-geo). Customer Lockbox is also listed in the [Fabric security capabilities](https://learn.microsoft.com/en-us/fabric/security/security-overview#capabilities) — confirm scope with your security team. |
| Workspace-level audit | Fabric workspace activity (item access, sharing changes, role assignments) is captured in the M365 unified audit log, surfaced via the Microsoft Purview portal. Retention and API access depend on your M365 / Audit licensing tier ([track user activities](https://learn.microsoft.com/en-us/fabric/admin/track-user-activities)). Engage your compliance / information-protection team to confirm what's enabled in your tenant. |
| Data classification & DLP | [Sensitivity labels](https://learn.microsoft.com/en-us/fabric/governance/information-protection), [DLP policies](https://learn.microsoft.com/en-us/power-bi/enterprise/service-security-dlp-policies-for-power-bi-overview), and [Insider Risk Management indicators for Fabric](https://learn.microsoft.com/en-us/purview/insider-risk-management-settings-policy-indicators#microsoft-fabric-indicators) are configured in [Microsoft Purview](https://learn.microsoft.com/en-us/fabric/governance/microsoft-purview-fabric) by your information-protection team. One CI/CD-relevant gotcha worth flagging: sensitivity labels are stripped on Git export ([reference](https://learn.microsoft.com/en-us/fabric/admin/git-integration-admin-settings#users-can-export-workspace-items-with-applied-sensitivity-labels-to-git-repositories)). |
| Fine-grained data access | Workspace roles are not the whole story — also configure [OneLake security](https://learn.microsoft.com/en-us/fabric/onelake/security/get-started-onelake-security) (table/folder grants) and [row-level / column-level / object-level security](https://learn.microsoft.com/en-us/fabric/security/permission-model#compute-permissions) on warehouses and semantic models. These are owned by data engineers, not the CI/CD pipeline. Note that deploying an item definition can overwrite security rules embedded in that item. |
| Repo & supply-chain hardening | Standard hygiene for any repo that holds deployment credentials and scripts: [GitHub Secret Scanning + push protection](https://docs.github.com/en/code-security/secret-scanning/introduction/about-secret-scanning), [CodeQL code scanning](https://docs.github.com/en/code-security/code-scanning/introduction-to-code-scanning/about-code-scanning), [Dependabot](https://docs.github.com/en/code-security/dependabot/dependabot-alerts/about-dependabot-alerts), and [Dependency Review on PRs](https://docs.github.com/en/code-security/supply-chain-security/understanding-your-software-supply-chain/about-dependency-review). Configure at the org or repo level. |

## Related Microsoft references

- [Fabric security overview](https://learn.microsoft.com/en-us/fabric/security/security-overview)
- [Fabric permission model](https://learn.microsoft.com/en-us/fabric/security/permission-model)
- [Fabric CI/CD overview](https://learn.microsoft.com/en-us/fabric/cicd/cicd-overview) and [choose the best CI/CD workflow](https://learn.microsoft.com/en-us/fabric/cicd/manage-deployment) (this repo implements [Git-based deployments with a build environment](fabric-cicd-release-options.md#option-3--git-based-with-build-environments))
- [Azure Well-Architected: Identity and access management](https://learn.microsoft.com/en-us/azure/well-architected/security/identity-access)
- [Managed identity best practices (UAMI vs SAMI)](https://learn.microsoft.com/en-us/entra/identity/managed-identities-azure-resources/managed-identity-best-practice-recommendations)
- [GitHub OIDC in Azure](https://docs.github.com/en/actions/deployment/security-hardening-your-deployments/configuring-openid-connect-in-azure)
- [fabric-cicd library](https://microsoft.github.io/fabric-cicd)
