---
name: swap-to-feature-dryrun
description: 'Preview swapping Fabric item IDs and settings to the configured feature workspace without writing files; run before /swap-to-feature.'
---

# Preview Swap to Feature

Preview the changes that would be made when switching tracked Fabric files to
the configured feature workspace.

## Procedure

1. From the repository root, run `python scripts/workspace_swap.py --dry-run`.
2. Report the command output and summarize the changes that would be made.

This is a preview only; no files are modified. Use it before `/swap-to-feature`
to verify the planned changes.
