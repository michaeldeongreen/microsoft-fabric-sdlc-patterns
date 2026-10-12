---
name: prepare-dev-workspace
description: 'Prepare canonical Fabric Dev pipeline bindings: create or reuse Dev activity connections, discover the model, record real baseline IDs, and align parameter files without swapping feature source.'
disable-model-invocation: true
---

# Prepare Dev Workspace

Run the Dev mode of [prepare_fabric_workspace.py](../../../scripts/prepare_fabric_workspace.py)
for deliberate standalone setup or troubleshooting. The everyday
`/swap-to-dev` skill already handles first-time preparation before restoring
source. Normally, there is no need to invoke this preparation-only skill.

An explicit invocation authorizes preparation. Do not ask for another `YES` or
`NO`, or execute merely because the user asks for an explanation.
Preparation changes Dev runtime resources, the tracked
[Dev manifest](../../../data/fabric-dev-bindings.json), and both parameter
files. It does not switch the active feature definitions to Dev.

## Procedure

1. For a requested preview, run the script with `--dev --dry-run` and report
   the result. Skip credentials and live preparation. Do not perform setup
   after the preview; it does not prove remote resources or permissions.
2. Use the user's approved Azure CLI identity for local Fabric API calls.
   Reuse a valid session; otherwise sign in through device code as described
   below. For default ServicePrincipal activity credentials, the local
   process still needs `AZURE_TENANT_ID`, `AZURE_CLIENT_ID`, and
   `AZURE_CLIENT_SECRET`. GitHub Environment secrets are not automatically
   downloaded to a local shell. Check presence without printing values;
   if missing, report the names and stop. Never request a secret in chat.
3. From the repository root, run preparation only:

   PowerShell:
   ```powershell
   python scripts\prepare_fabric_workspace.py --dev --use-azure-cli
   ```

   Bash:
   ```bash
   python scripts/prepare_fabric_workspace.py --dev --use-azure-cli
   ```

   The script reads the explicit Dev workspace from the Variable Library,
   discovers its existing model, ensures its connections, records real
   non-secret IDs, and aligns both parameter files. It reuses recorded IDs
   rather than silently replacing a deleted canonical connection.
4. Report the command output and generated source-configuration changes.
   On failure, report the error and stop; never claim the branch is PR-ready
   just because resource preparation succeeded.
5. After success, explain that `/swap-to-dev` restores the tracked references
   and removes the feature value set. It verifies local readiness itself; no
   separate readiness skill invocation is required.

Do not add `--swap-to-dev` automatically: this skill is preparation-only.
Do not add `--replace-dev-bindings` without an explicit request to regenerate
canonical resources. Do not commit, push, sync Git, run the pipeline, or start
a capacity unless separately requested.

## Local device-code authentication

Use `--use-azure-cli` by default. If the user session needs authentication,
use device-code login with a validated approved tenant:

```powershell
az login --tenant "<approved-tenant-guid>" --allow-no-subscriptions --scope https://api.fabric.microsoft.com/.default --use-device-code --output none
```

These are separate operations: do not log in again when the correct user session
is already valid. Never display an access token or full credential response.
Device-code user sign-in does not authenticate the Actions SPN or replace its
runtime connection credentials. For default ServicePrincipal connections,
the Azure SPN credential values are still required. User-created connections
also need the Actions SPN's appropriate management access for automatic
credential reconciliation. Explain this prerequisite rather than claiming
that user sign-in gives the SPN permission to manage those connections.
Unattended Actions continues using the SPN; do not introduce a device-code
prompt into CI or switch local identities silently.

See the [first-time and recurring development steps](../../../fabric-development-process.md)
and [setup/permission contract](../../../SETUP.md#post-etl-refresh-permissions).
