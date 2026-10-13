---
name: prepare-dev-workspace
description: 'Import canonical non-secret Dev binding metadata from the reviewed GitHub bootstrap Action and align parameter files without swapping feature source or using local SPN credentials.'
disable-model-invocation: true
---

# Import Dev Workspace Bindings

This advanced preparation-only tool is for deliberate setup or troubleshooting.
The everyday `/swap-to-dev` skill already imports the first baseline before
restoring source; normally there is no reason to run this skill separately.

The [Dev bootstrap Action](../../workflows/bootstrap-dev.yml) owns connection
creation using the Dev Environment's SPN secrets. This skill imports only its
non-secret IDs into the tracked [Dev manifest](../../../data/fabric-dev-bindings.json)
and aligns both parameter files. It does not rewrite the active feature
definitions or remove their value set.

An explicit invocation authorizes metadata retrieval, waiting for an approved
run, and dispatching the registered Dev workflow if no run exists. Do not ask
for an additional `YES` or `NO`, or execute when the user only asks for an
explanation.

## Procedure

1. For a preview, use `--dev --dry-run`. This stays completely local: no
   GitHub discovery/dispatch/download, Azure authentication, or file writes.
   Do not perform the import after the preview.
2. Use the developer's authenticated `gh` access to the repository. Do not
   read Azure credential values, request secrets in chat, or use Azure
   device-code login for Dev metadata import.
3. Run the import-only command from the repository root:

   PowerShell:
   ```powershell
   python scripts\prepare_fabric_workspace.py --dev
   ```

   Bash:
   ```bash
   python scripts/prepare_fabric_workspace.py --dev
   ```

   The helper verifies the registered workflow, reviewed Dev source, successful
   run and artifact provenance, then matches its workspace/model against local
   configuration. Unknown or invalid source/resource metadata fails before
   recording IDs.
4. If the bootstrap workflow is not available, explain the facilitator's
   bootstrap-only infrastructure rollout prerequisite and stop. If Environment
   approval is pending, report the canonical run URL; never approve it or
   ignore a failed run. Never fall back to local SPN credentials.
5. Report the import output and generated non-secret configuration changes.
   Preparation alone does not make the branch PR-ready. Explain that the
   ordinary `/swap-to-dev` skill performs restoration and verifies readiness.

Do not automatically add `--swap-to-dev` or `--replace-dev-bindings`, commit,
push, sync Fabric Git, run a pipeline, or start a capacity. A changed canonical
GUID requires deliberate recovery and a reviewed source change.

See the [facilitator and participant steps](../../../fabric-development-process.md)
and [setup contract](../../../SETUP.md).
