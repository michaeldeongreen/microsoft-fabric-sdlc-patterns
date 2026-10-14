---
name: swap-to-feature-dryrun
description: 'Preview the feature preparation-and-swap workflow locally: show exact swaps only for known feature IDs, explain uninitialized resources, and never authenticate, call Fabric, or write files.'
---

# Preview Swap to Feature

Preview the workflow of `/swap-to-feature`, including whether preparation is
needed. This is strictly local: no authentication, Fabric API calls, resource
provisioning, credential loading, or file writes.

When requested, execute the preview directly. Do not ask for confirmation or
automatically follow it with the write-enabled swap.

## Procedure

1. Inspect the intended feature checkout and only the relevant local feature
   keys. Do not create/edit `.env`, guess a workspace, or display credentials.
2. Preview the preparation phase without logging in:

   PowerShell:
   ```powershell
   python scripts\prepare_fabric_workspace.py --feature --dry-run
   ```

   Bash:
   ```bash
   python scripts/prepare_fabric_workspace.py --feature --dry-run
   ```

   This validates the local template and describes setup, not remote resource
   existence or permissions. Report a validation error explicitly and stop.
3. If the target and required local feature IDs are initialized for the
   intended workspace, preview the exact local swap:

   PowerShell:
   ```powershell
   python scripts\workspace_swap.py --dry-run
   ```

   Bash:
   ```bash
   python scripts/workspace_swap.py --dry-run
   ```

   The script validates the configured values. Report failures as failures,
   rather than treating malformed or stale configuration as a successful diff.
4. If the configuration is absent or required IDs are empty/all-zero, do not
   call a live preparation command or invent replacements. Explain that the
   live skill must prepare/discover the resources before an exact diff can
   be calculated. Clearly label the result as a workflow preview with unknown
   IDs, not an exact preview or a verified remote setup.
5. Report the available command output, known local changes, and anything
   that cannot yet be determined. If Dev is uninitialized, identify initial
   source templates as templates, never as verified Dev connections.
   Do not ask for confirmation or follow this preview with a write-enabled
   command.

This is a preview only; no files are modified. It is available before
`/swap-to-feature` to inspect planned changes, but is not required to authorize
that skill. No tenant/connection/CI permission checks are performed.
See the [guided process](../../../fabric-development-process.md).
