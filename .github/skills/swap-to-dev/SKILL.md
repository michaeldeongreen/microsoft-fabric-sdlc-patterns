---
name: swap-to-dev
description: 'Restore committed Dev references from parameter rules and verify local readiness; offline, with no connection provisioning, login, Actions dispatch, or artifacts.'
disable-model-invocation: true
---

# Swap to Dev

An explicit invocation authorizes the local restoration and readiness check.
Do not ask for another YES/NO. A preview request uses the
[dry-run skill](../swap-to-dev-dryrun/SKILL.md), never the write-enabled path.

1. Confirm the intended feature checkout, not dev/test/main or detached HEAD.
2. Use the committed baseline in both parameter files. Invalid, mismatched,
   or template IDs are errors: stop and explain the facilitator's explicit
   setup/cutover prerequisite. Never dispatch provisioning or regenerate IDs.
3. If the branch feature value set exists, run:

   ```powershell
   python scripts\workspace_swap.py --swap-to-dev
   ```

   If already restored, skip that write and go to readiness.
4. Verify automatically:

   ```powershell
   python scripts\workspace_swap.py --check-ready
   ```

5. Report complete output and local changes; errors stop the workflow.
   Remind the user to review/commit/push and create the PR to Dev.

No Azure/GitHub authentication, local SP secrets, connection setup, artifacts,
commits, pushes, Git sync, pipeline execution, or capacity changes are authorized.
Readiness verifies source state, not live Fabric permissions. After merge,
the human updates Dev in Fabric and runs the native pipeline.

See the [development process](../../../fabric-development-process.md).
