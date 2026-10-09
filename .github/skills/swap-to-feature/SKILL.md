---
name: swap-to-feature
description: 'Swap Fabric workspace and lakehouse IDs to the configured feature workspace, create its value set, and update settings.json after explicit confirmation.'
---

# Swap to Feature

Switch tracked Fabric items to the feature workspace for branch development.
The operation rewrites tracked Fabric files, creates a feature value set, and
updates `settings.json`.

## Procedure

1. Read `FEATURE_WORKSPACE_ID` and `FEATURE_LAKEHOUSE_ID` from `.env` at the
   repository root. Read the dev workspace and lakehouse IDs from
   `data/fabric/Patterns_Variables.VariableLibrary/variables.json`.
2. Show the current branch and the planned dev-to-feature workspace and
   lakehouse ID changes in chat.
3. Ask the user in chat to confirm with exactly `YES` or `NO`. Do not proceed
   without an explicit `YES`.
4. If the user answers `YES`, run `echo "YES" | python scripts/workspace_swap.py`
   from the repository root and report the complete output.
5. If the user answers `NO`, do not run the script and confirm that the swap
   was not applied.
6. After a successful swap, summarize what changed and remind the user to
   commit and push the changes, then sync the workspace from the Fabric UI.

Do not run the script without piping `YES`: it would wait for terminal input.
The chat confirmation is the safety gate; the piped value bypasses the script's
interactive prompt.
