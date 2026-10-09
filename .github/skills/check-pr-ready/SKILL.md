---
name: check-pr-ready
description: 'Check whether a Fabric branch is ready for a pull request by validating that dev workspace IDs are restored and no feature value sets remain.'
---

# Check PR Readiness

Run the same CI readiness check used by the `check-pr-ready.yml` workflow.

## Procedure

1. From the repository root, run `python scripts/workspace_swap.py --check-ready`.
2. Report the complete command output and whether the check passed.
3. If it fails, identify the files that still contain feature IDs. Recommend
   `/swap-to-dev` to restore dev IDs and remove the feature value set.

This check does not modify files.
