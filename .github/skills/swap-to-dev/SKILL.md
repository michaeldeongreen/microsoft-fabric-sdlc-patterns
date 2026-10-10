---
name: swap-to-dev
description: 'Restore tracked Fabric files to dev workspace IDs and remove the current branch feature value set before opening a PR.'
disable-model-invocation: true
---

# Swap to Dev

Run this after feature work to restore dev IDs before opening a pull request.

An explicit `/swap-to-dev` invocation or request to restore dev IDs is
authorization to execute it. Do not ask for additional confirmation or apply
the swap merely because the user asks for an explanation or preview.

## Procedure

1. From the repository root, run `python scripts/workspace_swap.py --swap-to-dev`.
2. Report the complete command output and summarize what changed.
3. Remind the user to commit and push the changes before opening a PR to `dev`.

The script reads the feature IDs from the existing value set on disk. It does
not consult `.env` or request terminal input. If it fails, report the error and
stop. Run the dry-run skill only when a preview is requested; do not commit or
push unless separately requested.
