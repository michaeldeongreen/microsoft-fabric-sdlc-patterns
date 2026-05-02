---
description: Swap the repo's IDs to your feature workspace and create the value set for the current branch.
mode: agent
---
Run `python scripts/workspace_swap.py` from the repo root and report the output to me. The script will rewrite tracked Fabric files (semantic model, notebooks) so they point at your feature workspace instead of dev, create a feature value set, and update settings.json. It reads the feature workspace and lakehouse GUIDs from `.env` at the repo root — if `.env` is missing or empty, it will fall back to an interactive prompt.

After the script finishes, summarize what changed and remind me to commit and push the changes, then sync the workspace from the Fabric UI.
