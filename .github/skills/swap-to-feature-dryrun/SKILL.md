---
name: swap-to-feature-dryrun
description: 'Preview swapping Fabric item IDs and settings to the configured feature workspace without writing files or requesting confirmation.'
---

# Preview Swap to Feature

Preview the changes that would be made when switching tracked Fabric files to
the configured feature workspace.

When requested, execute the preview directly. Do not ask for confirmation or
automatically follow it with the write-enabled swap.

## Procedure

1. From the repository root, run `python scripts/workspace_swap.py --dry-run`.
2. Report the command output and summarize the changes that would be made.

This is a preview only; no files are modified. It is available before
`/swap-to-feature` to inspect planned changes, but is not required to authorize
that skill. Report errors explicitly rather than claiming a successful preview.
