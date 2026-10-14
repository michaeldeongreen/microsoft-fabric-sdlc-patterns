---
name: prepare-dev-workspace
description: 'Explicitly record non-secret Dev IDs from local .env in the committed parameter rules; offline, with no SP credentials, artifacts, or implicit resource provisioning.'
disable-model-invocation: true
---

# Record Dev Baseline

This advanced setup tool is not required for ordinary `/swap-to-dev`.
Provisioning is an explicit facilitator action, not a side effect of this skill.

1. Use the intended checkout and existing `.env` Dev keys documented in
   [.env.sample](../../../.env.sample). Do not read or request secrets.
2. For a requested preview:

   ```powershell
   python scripts\prepare_fabric_workspace.py --dev --dry-run
   ```

   Do not follow a preview with writes.
3. For explicitly requested baseline recording:

   ```powershell
   python scripts\prepare_fabric_workspace.py --dev
   ```

   The script aligns the two parameter files and native pipeline fields.
   It does not remove a feature value set or replace other feature references.
4. A different canonical ID requires the user to explicitly request a
   reviewed cutover before using `--replace-dev-bindings`. Never add it merely
   to get a failing command to pass. Malformed/disagreeing rules remain errors.
5. Report output and changes. If ending feature work, use the normal Dev swap
   and readiness process afterward.

No GitHub/Fabric calls, artifact imports, credential loading, commits, pushes,
Git sync, capacity changes, or pipeline runs. See [Setup](../../../SETUP.md).
