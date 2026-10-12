---
name: swap-to-dev-dryrun
description: 'Preview returning a Fabric feature branch to Dev locally: show known baseline swaps or explain first-time setup, without login, Fabric API calls, provisioning, or file writes.'
---

# Preview Swap to Dev

Preview the workflow of `/swap-to-dev` without running live setup. No login,
Fabric API calls, provisioning, credential loading, or file writes are allowed.

When requested, execute the preview directly. Do not ask for confirmation or
automatically follow it with the write-enabled swap.

## Procedure

1. Inspect the intended feature checkout and the non-secret
   [Dev manifest](../../../data/fabric-dev-bindings.json). Do not inspect or
   load Azure secrets.
2. If the manifest has initialized resource IDs, preview the ordinary offline
   restoration:

   PowerShell:
   ```powershell
   python scripts\workspace_swap.py --swap-to-dev --dry-run
   ```

   Bash:
   ```bash
   python scripts/workspace_swap.py --swap-to-dev --dry-run
   ```

   The script validates the manifest. Invalid JSON/schema/keys/GUIDs or Dev
   workspace mismatches are errors, not reasons to bootstrap automatically.
   A repository without the native pipeline also uses this ordinary preview.
3. Only if the manifest is absent or schemaVersion 1 with expected resource
   keys has all resource IDs null, describe first-time preparation using local
   validation only:

   PowerShell:
   ```powershell
   python scripts\prepare_fabric_workspace.py --dev --dry-run
   ```

   Bash:
   ```bash
   python scripts/prepare_fabric_workspace.py --dev --dry-run
   ```

   Do not run the ordinary swap preview against missing baseline IDs.
   Explain which setup and restoration steps would be needed, but say that
   real connection/model GUIDs and exact replacements are unknown until live
   preparation. Do not present templates or invented GUIDs as runnable Dev
   bindings.
4. Report the command output, the known changes, and any unavailable exact
   diff. A malformed or partially initialized manifest or local-template
   error must be reported as a failure, not a successful setup preview.

This is a preview only; no files are modified. It is optional, not a confirmation
gate for `/swap-to-dev`. Never proceed to the live skill afterward or claim
remote connection/permission verification. See the
[guided development process](../../../fabric-development-process.md).
