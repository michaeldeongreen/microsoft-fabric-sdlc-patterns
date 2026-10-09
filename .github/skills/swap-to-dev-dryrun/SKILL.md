---
name: swap-to-dev-dryrun
description: 'Preview reverting Fabric item IDs and feature settings to dev without modifying files; run before applying /swap-to-dev.'
---

# Preview Swap to Dev

Preview the changes that would be made when restoring dev workspace IDs.

## Procedure

1. From the repository root, run
   `python scripts/workspace_swap.py --swap-to-dev --dry-run`.
2. Report the command output and summarize the files and values that would
   change.

This is a preview only; no files are modified.
