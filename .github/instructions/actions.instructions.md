---
applyTo: ".github/workflows/**/*.yml"
---

When generating or improving GitHub Actions workflows in this repository:

## Security First
- Use GitHub secrets for sensitive data, never hardcode credentials
- Pin third-party actions to specific commit SHAs (e.g., `uses: actions/checkout@de0fac2e4500dabe0009e67214ff5f5447ce83dd`)
- Configure minimal `permissions` for `GITHUB_TOKEN` — default to `contents: read`
- Use GitHub Environments (`test`, `prod`) with environment-scoped secrets for stage isolation

## Performance
- Add `timeout-minutes` to all jobs to prevent hung workflows
- Cache dependencies with `actions/cache` or built-in cache options when beneficial

## Best Practices
- Use descriptive `name:` values for workflows, jobs, and steps
- Use reusable workflows (`workflow_call`) for shared logic across environments — not composite actions
- Pass `environment` as an input to reusable workflows and set `environment:` at the job level to enable protection rules and scoped secrets
- Use `secrets: inherit` in caller workflows to forward environment secrets
- Use `needs:` for sequential job dependencies within a workflow
- Use `workflow_run` to trigger follow-up workflows (e.g., ETL after deploy)
- Add path filters (e.g., `paths: ["data/fabric/**"]`) to avoid unnecessary runs on doc-only changes
- Add `if: always()` for cleanup steps that must run regardless of failure

## fabric-cicd Specific
- Always use `ClientSecretCredential` from `azure-identity` — `DefaultAzureCredential` is deprecated by fabric-cicd
- Inline Python for fabric-cicd calls (~10 lines) instead of separate script files
- The `FabricWorkspace` constructor accepts `item_type_in_scope` as a list of strings to limit which item types are deployed
- The `environment` parameter on `FabricWorkspace` must match the keys in `parameter.yml` (e.g., `test`, `prod`)
- After `publish_all_items`, call `unpublish_all_orphan_items` to clean up items removed from the repo

## Current Action Versions (pinned to SHA)
- `actions/checkout@v6` → `de0fac2e4500dabe0009e67214ff5f5447ce83dd`
- `actions/setup-python@v6` → `a309ff8b426b58ec0e2a45f0f869d46889d02405`
