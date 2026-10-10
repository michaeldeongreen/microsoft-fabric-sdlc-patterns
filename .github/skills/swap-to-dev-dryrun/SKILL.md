---
name: swap-to-dev-dryrun
description: 'Preview reverting Fabric item IDs and feature settings to dev without modifying files or requesting confirmation.'
---

# Preview Swap to Dev

Preview the changes that would be made when restoring dev workspace IDs.

When requested, execute the preview directly. Do not ask for confirmation or
automatically follow it with the write-enabled swap.

## Procedure

1. From the repository root, run
   `python scripts/workspace_swap.py --swap-to-dev --dry-run`.
2. Report the command output and summarize the files and values that would
   change.

This is a preview only; no files are modified. It is optional, not a confirmation
gate for `/swap-to-dev`. Report errors explicitly rather than claiming success.
