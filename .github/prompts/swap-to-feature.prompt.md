---
description: Swap the repo's IDs to your feature workspace and create the value set for the current branch.
mode: agent
---
The script `scripts/workspace_swap.py` rewrites tracked Fabric files (semantic model, notebooks) so they point at your feature workspace instead of dev, creates a feature value set, and updates settings.json. It reads `FEATURE_WORKSPACE_ID` and `FEATURE_LAKEHOUSE_ID` from `.env` at the repo root and asks for a `YES` confirmation before applying. When invoked through this prompt, that confirmation must happen here in chat — never in the terminal — to avoid live-prompt handling problems.

Follow this exact sequence:

1. Read `.env` at the repo root and read the dev workspace + lakehouse IDs from `data/fabric/Patterns_Variables.VariableLibrary/variables.json`.
2. Show me the planned swap in chat (current branch, dev → feature workspace ID, dev → feature lakehouse ID).
3. Use the chat UI to ask me a single question with two options: `YES` and `NO` (uppercase, exact). Do not proceed until I answer.
4. If I answer `YES`, run `echo "YES" | python scripts/workspace_swap.py`. The piped `YES` satisfies the script's confirmation gate non-interactively, so the terminal never blocks. Report the full output.
5. If I answer `NO`, do nothing further and confirm in chat that the swap was not applied.
6. After a successful run only, summarize what changed and remind me to commit and push the changes, then sync the workspace from the Fabric UI.

Do not run the script directly without piping `YES` (it will block on the terminal prompt). Do not skip the chat confirmation — the in-script confirmation is bypassed by the pipe and the chat dialog is the gate.
