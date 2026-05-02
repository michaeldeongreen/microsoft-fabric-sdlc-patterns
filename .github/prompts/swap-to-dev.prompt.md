---
description: Swap the IDs back to dev and remove the feature value set (run before opening a PR).
mode: agent
---
Run `python scripts/workspace_swap.py --swap-to-dev` from the repo root and report the output to me. The script will revert tracked Fabric files (semantic model, notebooks) back to the dev workspace IDs, delete the feature value set for the current branch, and remove the feature entry from settings.json. It reads the feature IDs from the existing value set on disk — `.env` is not consulted.

After the script finishes, summarize what changed and remind me to commit and push the changes before opening a PR to `dev`.
