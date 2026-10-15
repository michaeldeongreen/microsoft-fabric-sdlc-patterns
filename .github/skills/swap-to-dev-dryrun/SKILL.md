---
name: swap-to-dev-dryrun
description: 'Preview the offline Dev restoration from committed parameter rules, without login, provisioning, workflow dispatch, artifacts, or file writes.'
---

# Preview Swap to Dev

Run the requested preview directly:

```powershell
python scripts\workspace_swap.py --swap-to-dev --dry-run
```

Validate the committed parameter-rule baseline. Missing, invalid, mismatched,
or placeholder configuration is an explicit setup error, not permission to
create resources or fall back to guessed IDs.

Report the output and known diff. Do not authenticate, dispatch/download from
Actions, call Fabric, read secrets, write files, or follow with the live swap.
This optional preview is not a mandatory confirmation gate.
