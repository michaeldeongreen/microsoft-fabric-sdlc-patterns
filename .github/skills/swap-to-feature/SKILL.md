---
name: swap-to-feature
description: 'Switch to a Fabric feature workspace: prepare a new target using Azure CLI device-code authentication when needed, then apply the local ID swap without another confirmation.'
disable-model-invocation: true
---

# Swap to Feature

After Branch Out, use this one skill to prepare the feature target when needed
and switch tracked Fabric items to it. The Python scripts remain separate:
[prepare_fabric_workspace.py](../../../scripts/prepare_fabric_workspace.py)
owns read-only API validation; [workspace_swap.py](../../../scripts/workspace_swap.py) owns
local rewriting and the feature value set.

An explicit `/swap-to-feature` invocation or request to apply the swap is
authorization for the preparation and swap described here. Do not ask for
another `YES` or `NO`. Missing target/tenant information is a configuration
question, not a confirmation prompt. Do not execute merely because the user
mentions the skill or asks for an explanation.

For a preview request, use the
[dry-run procedure](../swap-to-feature-dryrun/SKILL.md) instead. Never follow a
preview with live preparation or a swap.

## Procedure

1. Confirm the current checkout is the intended feature branch, not `dev`,
   `test`, `main`, or detached HEAD. Read only the required feature keys in the
   ignored `.env`; do not print unrelated configuration or credentials.
   Require an explicitly selected, nonzero feature workspace GUID different
   from Dev. Ask for the GUID if missing; never guess by workspace name.
2. For a new Branch Out workspace or uninitialized feature bindings, prepare
   before swapping:
   - The human must first create the workspace WI and its two WI connections,
     grant the required workspace permissions, and supply both connection IDs.
     Preparation never provisions those resources. Missing IDs are a setup
     prerequisite, not authorization to create connections implicitly.
   - Start with fresh feature values from [.env.sample](../../../.env.sample)
     for a different workspace. Do not carry previous connection IDs into the
     new target; preserve unrelated local settings.
   - Preserve valid connection IDs intentionally supplied for the same target.
     Do not clear working configuration on a repeat invocation.
   - Use the intended Azure CLI user identity. Reuse a valid session in the
     approved tenant; if login is needed, prefer device code. A token-free
     authentication check is:

     ```powershell
     az account get-access-token --resource https://api.fabric.microsoft.com --query expiresOn --output tsv
     ```

     Substitute the validated tenant GUID before running a required login:

     ```powershell
     az login --tenant "<approved-tenant-guid>" --allow-no-subscriptions --scope https://api.fabric.microsoft.com/.default --use-device-code --output none
     ```

     Let the user complete sign-in. Do not display access tokens or complete
     credential responses, guess the tenant, or switch identities silently.
   - Run preparation in the active shell:

     PowerShell:
     ```powershell
     python scripts\prepare_fabric_workspace.py --feature --use-azure-cli
     ```

     Bash:
     ```bash
     python scripts/prepare_fabric_workspace.py --feature --use-azure-cli
     ```

     Preparation validates the existing feature WI connections and discovers
     item IDs into `.env`. On any authentication, permission, dependency, or
     preparation error, report it and stop before the swap. Do not start a
     capacity or change tenant policy to bypass a failure.

   If the user is resuming the same known prepared workspace with complete,
   valid local bindings, skip preparation and authentication. The offline
   script still validates its inputs; this path does not certify remote
   connections or permissions.
3. Only after successful preparation, or the known prepared-workspace path,
   run the local swap non-interactively:

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
4. Report the preparation output when performed and the complete swap output.
   If a command fails, report the error and stop;
   do not invent missing configuration or claim success.
5. After a successful swap, summarize what changed and remind the user to
   review, commit/push, sync the feature workspace from Git, and activate its
   feature value set. A separate preparation skill invocation is not required.

Do not run the script without piping `YES`: it would wait for terminal input.
Run `/swap-to-feature-dryrun` only when a preview is requested; it is not a
mandatory confirmation step. Do not commit, push, or sync Fabric unless separately
requested. See the [guided development process](../../../fabric-development-process.md).
