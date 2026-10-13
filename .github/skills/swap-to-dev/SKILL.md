---
name: swap-to-dev
description: 'Return a Fabric feature branch to Dev: import trusted Actions-created IDs only if uninitialized, then restore references and verify readiness; no local SPN credentials and repeated returns stay offline.'
disable-model-invocation: true
---

# Swap to Dev

Use this one skill after feature work, including the first pipeline migration.
It imports trusted Dev metadata when needed, restores local references, and
checks readiness. GitHub Actions owns Dev connection setup and SPN credentials;
the local skill never calls Fabric or requests those credentials.

An explicit `/swap-to-dev` invocation or request to restore dev IDs is
authorization to obtain first-time Actions metadata when needed and apply the
local swap. Do
not ask for an additional `YES` or `NO`. For a preview request, follow the
[dry-run procedure](../swap-to-dev-dryrun/SKILL.md) instead; do not perform live
setup or automatically apply a preview.

## Procedure

1. Confirm the intended feature checkout, not `dev`, `test`, `main`, or
   detached HEAD. For the native pipeline, inspect the non-secret
   [Dev manifest](../../../data/fabric-dev-bindings.json):
   - An absent manifest or schemaVersion 1 with the expected resource keys
     and all resource IDs null means first-time metadata import is needed.
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
3. Only for an uninitialized Dev baseline, obtain the bootstrap metadata and
   swap through the existing combined CLI option:
   - Use the developer's authenticated GitHub CLI access. If authentication is
     missing, explain the required `gh` sign-in; never request a GitHub token
     or SPN secret in chat. Azure login and local Azure credential variables
     are not needed for this direction.
   - The reviewed [Dev bootstrap Action](../../workflows/bootstrap-dev.yml)
     must already be available on Dev. It creates connections with the Dev
     Environment's SPN credentials and uploads only non-secret IDs/provenance.
     For this repository's initial migration, a facilitator merges the
     bootstrap-only infrastructure PR first. If that prerequisite is missing,
     report it and stop; do not bypass PR checks or fall back to local setup.
   - Run the appropriate command:

     PowerShell:
     ```powershell
     python scripts\prepare_fabric_workspace.py --dev --swap-to-dev
     ```

     Bash:
     ```bash
     python scripts/prepare_fabric_workspace.py --dev --swap-to-dev
     ```

     The helper selects a trusted reviewed Dev run, waits if necessary, or
     dispatches the registered Dev bootstrap when no run exists. It validates
     repository/workflow/ref/commit/run provenance and the local target before
     importing metadata, aligning both parameter files, and invoking the
     existing swap. SPN credentials are never downloaded.
   - If an Environment reviewer approval is required, report the run URL and
     approval state without approving it. A failed, expired, or mismatched
     artifact is an error, not permission to use stale values or an arbitrary
     older run. Do not invoke the swap a second time after this command.
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
