---
description: Run the CI-style readiness check locally — verifies dev IDs are restored and no stray feature value sets remain.
mode: agent
---
Run `python scripts/workspace_swap.py --check-ready` from the repo root and report the output to me. This is the same check the `check-pr-ready.yml` GitHub Actions workflow runs on every PR to `dev`. It does not modify any files.

If the check fails, the output will tell you which files still contain feature IDs. The fix is usually to run `/swap-to-dev`.
