---
name: swap-to-dev
description: 'Restore tracked Fabric files to dev workspace IDs and remove the current branch feature value set before opening a PR.'
---

# Swap to Dev

Run this after feature work to restore dev IDs before opening a pull request.

## Procedure

1. From the repository root, run `python scripts/workspace_swap.py --swap-to-dev`.
2. Report the complete command output and summarize what changed.
3. Remind the user to commit and push the changes before opening a PR to `dev`.

The script reads the feature IDs from the existing value set on disk. It does
not consult `.env`.
