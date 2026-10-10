---
name: swap-to-feature
description: 'Apply the configured dev-to-feature Fabric ID swap when requested, without an additional confirmation prompt.'
disable-model-invocation: true
---

# Swap to Feature

Switch tracked Fabric items to the feature workspace for branch development.
The operation rewrites tracked Fabric files, creates a feature value set, and
updates `settings.json`.

An explicit `/swap-to-feature` invocation or request to apply the swap is
authorization to execute it. Do not ask for `YES`, `NO`, or another confirmation.
Do not apply a swap merely because the user mentions the skill or asks for an
explanation or preview.

## Procedure

1. From the repository root, run the script non-interactively using the command
   for the active shell:

   PowerShell:
   ```powershell
   Write-Output 'YES' | python scripts\workspace_swap.py
   ```

   Bash:
   ```bash
   printf 'YES\n' | python scripts/workspace_swap.py
   ```

   The piped value satisfies the CLI's existing terminal prompt automatically.
   The script reads `.env`, resolves the branch, validates the IDs, and reports
   the planned changes; do not duplicate those steps in separate tool calls.
2. Report the complete command output. If it fails, report the error and stop;
   do not invent missing configuration or claim success.
3. After a successful swap, summarize what changed and remind the user to
   commit and push the changes, then sync the workspace from the Fabric UI.

Do not run the script without piping `YES`: it would wait for terminal input.
Run `/swap-to-feature-dryrun` only when a preview is requested; it is not a
mandatory confirmation step. Do not commit, push, or sync Fabric unless separately
requested.
