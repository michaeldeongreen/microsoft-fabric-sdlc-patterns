# Project Guidelines

## Overview

Reference implementation for CI/CD in Microsoft Fabric. Demonstrates version control, deployment, and environment-specific configuration for Fabric workspace items using GitHub Actions and [fabric-cicd](https://microsoft.github.io/fabric-cicd).

## Project Layout

```
scripts/              Python CLI scripts (stdlib-only, Python 3.10+)
tests/                pytest unit tests
data/fabric/          Fabric item definitions (git-synced from Fabric workspaces)
.github/workflows/    GitHub Actions CI/CD pipelines
.github/instructions/ Path-specific Copilot instructions (Python, Actions)
```

## Build and Test

```bash
pip install -r requirements-dev.txt
python -m pytest tests/ -v
```

No build step — scripts are standalone CLI tools, not an installable package. `pyproject.toml` configures pytest only (`pythonpath = ["scripts"]`).

## Key Scripts

- `scripts/branch_env.py` — Manages feature branch workspace bindings (bootstrap, reset, validate). Uses an **item type registry** pattern — new Fabric item types are added as config entries, not new functions.
- `scripts/branch_env.py --validate` — CI check for PR readiness (dev IDs present, no stray value sets).

## Fabric Item Types

Items fall into two categories based on how they reference environment resources:

- **Actual IDs** (SemanticModel, Notebook): Embed real workspace/lakehouse GUIDs. Must be rewritten by `branch_env.py` for feature branches and reverted before PR.
- **Logical IDs** (Ontology, DataAgent): Reference items via `.platform` `logicalId`, resolved by Fabric at runtime. Portable across Branch Out workspaces — no rewriting needed.

## CI/CD Configuration

- `data/fabric/parameter.yml` — Deploy-time `find_replace` rules for fabric-cicd. Maps dev IDs to dynamic placeholders (`$workspace.$id`, `$items.Lakehouse.*.$id`).
- `data/fabric/Patterns_Variables.VariableLibrary/` — Runtime configuration via value sets (Test, Prod, feature branches).

## Conventions

- Path-specific instructions in `.github/instructions/` govern Python and Actions code style — follow them.
- Never commit notebook META blocks containing internal metadata (security).
- Validate GUIDs from external sources before using them.
- Pin GitHub Actions to commit SHAs, not version tags.
- All file I/O must specify `encoding="utf-8"`.

## Workflows

| Workflow | Trigger | Purpose |
|----------|---------|---------|
| `validate-branch-env.yml` | PR to `dev` | Blocks merge if dev IDs not restored |
| `run-tests.yml` | PR (any branch) | Runs pytest when scripts/tests change |

## Documentation

See `fabric-development-process.md` for the Branch Out workflow, item type reference table, and step-by-step bootstrap/reset guides. See `fabric-hybrid-cicd-guide.md` for the deployment architecture.
