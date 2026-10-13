---
name: prepare-feature-workspace
description: 'Prepare a newly branched Fabric feature workspace: discover item IDs, ensure Workspace Identity activity connections, and populate local .env without swapping tracked definitions.'
disable-model-invocation: true
---

# Prepare Feature Workspace

Run the feature mode of [prepare_fabric_workspace.py](../../../scripts/prepare_fabric_workspace.py)
for deliberate standalone setup or troubleshooting. The everyday
`/swap-to-feature` skill already handles preparation for a new Branch Out
workspace before swapping. This skill remains preparation-only.

An explicit invocation authorizes preparation. Do not ask for an additional
`YES` or `NO`, or execute merely because the user asks for an explanation.
Preparation can create connections, provision a Workspace Identity, and ensure
its workspace permissions. It updates the ignored `.env`, not tracked item
definitions.

## Procedure

1. For a requested preview, run the script with `--feature --dry-run` and report
   the result. Skip authentication, configuration writes, and live preparation.
   This is local validation only, not verification of remote permissions.
2. For live preparation, use the explicit `FEATURE_WORKSPACE_ID` in `.env`.
   If it is missing, ask for the intended workspace GUID using the question
   tool. Validate that it is a nonzero, hyphenated GUID and is not Dev.
   Do not guess a workspace by display-name substring.
   - When starting a different feature workspace, use fresh feature values
     from [.env.sample](../../../.env.sample); do not carry over the previous
     workspace's connection IDs. Preserve unrelated local configuration.
   - Existing connection IDs may be retained only when intentionally supplied
     for this feature workspace. Never clear a working workspace's IDs just
     because preparation is being repeated.
3. Use the intended Azure CLI user identity with adequate feature-workspace
   bootstrap permissions. If authentication needs renewing, prefer device code.
   Use the approved tenant ID from local configuration or ask for it; do not
   guess a tenant or switch accounts silently. Check authentication without
   printing a token, for example:

   ```powershell
   az account get-access-token --resource https://api.fabric.microsoft.com --query expiresOn --output tsv
   ```

   When login is needed, substitute the validated tenant GUID before running:

   ```powershell
   az login --tenant "<approved-tenant-guid>" --allow-no-subscriptions --scope https://api.fabric.microsoft.com/.default --use-device-code --output none
   ```

   Allow the user to complete the device-code sign-in. Never print access
   tokens, secrets, or the complete Azure credential response. A permission
   error is not a reason to repeatedly log in or select another identity.
4. From the repository root, run preparation only:

   PowerShell:
   ```powershell
   python scripts\prepare_fabric_workspace.py --feature --use-azure-cli
   ```

   Bash:
   ```bash
   python scripts/prepare_fabric_workspace.py --feature --use-azure-cli
   ```

   The script discovers exact item names and creates/reuses the two supported
   activity connections. Let it validate configuration and resource metadata;
   do not duplicate its API logic.
5. Report the command output and the non-secret configuration changes. On
   failure, report the error and stop; do not invent IDs or silently continue.
6. After success, explain that the next separate step is `/swap-to-feature`,
   followed by the normal reviewed commit/push, feature Git sync, and feature
   value-set activation.

Do not automatically swap, commit, push, sync Git, activate a value set, run
the pipeline, or start a capacity. Dependency or permission failures must be
reported explicitly. Do not ask the user to paste secrets into chat.

See the [guided development process](../../../fabric-development-process.md)
and [runtime permissions](../../../SETUP.md#post-etl-refresh-permissions).
