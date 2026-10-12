---
name: swap-to-dev
description: 'Return a Fabric feature branch to Dev: initialize real Dev bindings only if missing, then restore local references and verify readiness; repeated returns stay offline.'
disable-model-invocation: true
---

# Swap to Dev

Use this one skill after feature work, including the first pipeline migration.
It conditionally prepares Dev, restores local references, and checks readiness.
The preparation and swap scripts remain separate.

An explicit `/swap-to-dev` invocation or request to restore dev IDs is
authorization for first-time preparation when needed and the local swap. Do
not ask for an additional `YES` or `NO`. For a preview request, follow the
[dry-run procedure](../swap-to-dev-dryrun/SKILL.md) instead; do not perform live
setup or automatically apply a preview.

## Procedure

1. Confirm the intended feature checkout, not `dev`, `test`, `main`, or
   detached HEAD. For the native pipeline, inspect the non-secret
   [Dev manifest](../../../data/fabric-dev-bindings.json):
   - An absent manifest or schemaVersion 1 with the expected resource keys
     and all resource IDs null means first-time preparation is needed.
   - A populated manifest means use the ordinary offline path. The swap
     script validates its GUIDs and agreement with the Dev Variable Library.
   - Malformed JSON, missing/unexpected keys, an unknown schema, partially
     initialized IDs, invalid populated values, or workspace mismatches are
     errors. Report them and
     stop; do not treat invalid configuration as permission to regenerate it.
   - A repository without a native refresh pipeline needs no new Dev manifest.
2. When Dev is already initialized, run the existing offline swap:

   PowerShell:
   ```powershell
   python scripts\workspace_swap.py --swap-to-dev
   ```

   Bash:
   ```bash
   python scripts/workspace_swap.py --swap-to-dev
   ```

   No login or Fabric API calls are needed. The script reads the existing
   branch value set, not `.env`. If the feature value set is already absent,
   skip the swap and run the readiness check in step 4 to distinguish an
   already restored branch from inconsistent source.
3. Only for an uninitialized Dev baseline, prepare and swap through the
   existing explicit combined CLI option:
   - Default local authentication is the user's approved Azure CLI session.
     Reuse it if valid. If sign-in is needed, use device code with the validated
     approved tenant:

     ```powershell
     az account get-access-token --resource https://api.fabric.microsoft.com --query expiresOn --output tsv
     az login --tenant "<approved-tenant-guid>" --allow-no-subscriptions --scope https://api.fabric.microsoft.com/.default --use-device-code --output none
     ```

     Run login only when required, allow the user to finish it, and never
     display an access token or full credential response.
   - For default ServicePrincipal runtime connections, the local process
     still needs `AZURE_TENANT_ID`, `AZURE_CLIENT_ID`, and
     `AZURE_CLIENT_SECRET`. These are runtime connection configuration, not
     the user sign-in. Check presence without printing values. If missing,
     report the required names and stop; never request a secret in chat or
     assume GitHub Environment secrets are available locally.
   - User-created connections must give the Actions SPN sufficient management
     access for subsequent credential reconciliation. Device-code login does
     not grant that access. Apply the approved permission contract in
     [Setup](../../../SETUP.md#post-etl-refresh-permissions); do not claim CI
     authorization merely because local source readiness passes.
   - Run the appropriate command:

     PowerShell:
     ```powershell
     python scripts\prepare_fabric_workspace.py --dev --use-azure-cli --swap-to-dev
     ```

     Bash:
     ```bash
     python scripts/prepare_fabric_workspace.py --dev --use-azure-cli --swap-to-dev
     ```

     This records real Dev IDs, aligns both parameter files, and invokes the
     existing swap. Do not invoke the swap a second time afterward.
4. After the selected path succeeds, verify local readiness automatically:

   PowerShell:
   ```powershell
   python scripts\workspace_swap.py --check-ready
   ```

   Bash:
   ```bash
   python scripts/workspace_swap.py --check-ready
   ```

   A separate manual check is not required. GitHub also runs
   this check for a PR targeting Dev; its required-status policy is configured
   separately.
5. Report the complete command output and summarize the source changes or
   already-restored state. A command/check failure stops the workflow and must
   be reported explicitly. Remind the user to review, commit/push, and open the
   PR to `dev`.

Never add `--replace-dev-bindings` automatically or recreate a missing
canonical connection merely to make a deployment succeed. No commits, pushes,
Git sync, pipeline runs, capacity startup, or tenant-policy changes are
authorized by this skill. See the
[guided development process](../../../fabric-development-process.md).
