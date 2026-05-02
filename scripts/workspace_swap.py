"""
Manage feature-branch workspace bindings for Fabric.

Swap to feature workspace (rewrite tracked files for local feature dev):
    python scripts/workspace_swap.py
    python scripts/workspace_swap.py --dry-run

Swap back to dev (revert tracked files before opening a PR):
    python scripts/workspace_swap.py --swap-to-dev
    python scripts/workspace_swap.py --swap-to-dev --dry-run

Check the branch is PR-ready (CI gate; confirms dev IDs are present):
    python scripts/workspace_swap.py --check-ready

No arguments required — reads the current git branch automatically.

Feature workspace IDs (one-time setup):
    Copy .env.sample to .env at the repo root and fill in the two GUIDs.
    The script reads them on first swap-to-feature, then caches them in
    the branch's value set file so subsequent runs need no input.

Future enhancement (intentionally not implemented):
    The script could auto-discover feature workspace IDs by calling the
    Fabric REST API and matching on workspace display name. That path was
    removed because substring matching can silently pick the wrong
    workspace (e.g. matching the dev workspace itself), causing the swap
    to abort with no value set written. If you re-introduce it, require
    an exact naming convention and exclude the dev workspace explicitly.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Callable

# ── Paths (relative to repo root) ──────────────────────────────────────────
REPO_ROOT = Path(subprocess.run(
    ["git", "rev-parse", "--show-toplevel"],
    capture_output=True, text=True, check=True,
).stdout.strip())

FABRIC_DIR = REPO_ROOT / "data" / "fabric"
VARIABLES_FILE = FABRIC_DIR / "Patterns_Variables.VariableLibrary" / "variables.json"
SETTINGS_FILE = FABRIC_DIR / "Patterns_Variables.VariableLibrary" / "settings.json"
VALUE_SETS_DIR = FABRIC_DIR / "Patterns_Variables.VariableLibrary" / "valueSets"
ENV_FILE = REPO_ROOT / ".env"
ALLOWED_VALUE_SETS = {"Test", "Prod"}

# ── Item type registry ─────────────────────────────────────────────────────
# Each entry declares how a Fabric item type participates in branch-env
# management.  Generic functions iterate this list instead of hard-coding
# per-type logic, so adding a new item type is a single dict addition.
#
#   name           – display name for logging
#   file_patterns  – globs resolved against FABRIC_DIR
#   needs_rewrite  – True → dev↔feature ID replacement during bootstrap/reset
#   id_keys        – which dev IDs to validate ("workspace", "lakehouse", or both)
#   content_filter – optional predicate on file text; None means process all
ITEM_TYPES: list[dict[str, str | list[str] | bool | list[str] | Callable[[str], bool] | None]] = [
    {
        "name": "SemanticModel",
        "file_patterns": ["*.SemanticModel/definition/expressions.tmdl"],
        "needs_rewrite": True,
        "id_keys": ["workspace", "lakehouse"],
        "content_filter": None,
    },
    {
        "name": "Notebook",
        "file_patterns": ["*.Notebook/notebook-content.py"],
        "needs_rewrite": True,
        "id_keys": ["workspace", "lakehouse"],
        "content_filter": lambda text: "default_lakehouse" in text,
    },
    {
        "name": "Ontology",
        "file_patterns": [
            "*.Ontology/**/DataBindings/*.json",
            "*.Ontology/**/Contextualizations/*.json",
        ],
        "needs_rewrite": False,
        "id_keys": ["lakehouse"],
        "content_filter": None,
    },
    {
        "name": "DataAgent",
        "file_patterns": ["*.DataAgent/**/datasource.json"],
        "needs_rewrite": False,
        "id_keys": [],
        "content_filter": None,
    },
]


def get_current_branch() -> str:
    result = subprocess.run(
        ["git", "rev-parse", "--abbrev-ref", "HEAD"],
        capture_output=True, text=True, check=True,
    )
    return result.stdout.strip()


def sanitize_branch_name(branch: str) -> str:
    """Turn branch name into a safe filename (e.g. feature/login-fix → feature-login-fix)."""
    return re.sub(r"[^a-zA-Z0-9_-]", "-", branch)


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def save_json(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def _read_env_file(path: Path) -> dict[str, str]:
    """
    Minimal .env parser (KEY=VALUE per line).

    Skips blank lines and lines starting with '#'. Strips surrounding
    whitespace and matching single/double quotes from values. Splits each
    line on the first '=' only, so values may contain '='. If a key appears
    multiple times, the last occurrence wins.

    Stdlib-only by design — avoids the python-dotenv dependency to keep
    this script frictionless to run.
    """
    if not path.exists():
        return {}
    env: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        value = value.strip()
        # Strip a single matching pair of surrounding quotes
        if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
            value = value[1:-1]
        env[key.strip()] = value
    return env


def get_dev_ids() -> tuple[str, str]:
    """Extract baseline (dev) workspace and lakehouse IDs from variables.json."""
    variables = load_json(VARIABLES_FILE)["variables"]
    lookup = {v["name"]: v["value"] for v in variables}
    return lookup["target_workspace_id"], lookup["target_lakehouse_id"]


def resolve_feature_ids(branch: str, value_set_path: Path) -> tuple[str, str]:
    """
    Resolve workspace and lakehouse IDs for the feature environment.

    Priority:
      1. Existing value set file for this branch (already bootstrapped).
      2. .env file at repo root (FEATURE_WORKSPACE_ID, FEATURE_LAKEHOUSE_ID).
      3. Interactive prompt as fallback.
    """
    # 1. Reuse existing value set
    if value_set_path.exists():
        overrides = load_json(value_set_path)["variableOverrides"]
        lookup = {o["name"]: o["value"] for o in overrides}
        ws_id = lookup.get("target_workspace_id")
        lh_id = lookup.get("target_lakehouse_id")
        if ws_id and lh_id:
            print(f"  Reusing IDs from existing value set: {value_set_path.name}")
            return ws_id, lh_id

    # 2. Try .env file at the repo root
    env = _read_env_file(ENV_FILE)
    ws_id = env.get("FEATURE_WORKSPACE_ID", "").strip()
    lh_id = env.get("FEATURE_LAKEHOUSE_ID", "").strip()
    if ws_id and lh_id:
        _validate_guid(ws_id, "FEATURE_WORKSPACE_ID")
        _validate_guid(lh_id, "FEATURE_LAKEHOUSE_ID")
        print(f"  Loaded feature IDs from {ENV_FILE.name}")
        return ws_id, lh_id

    # 3. Interactive fallback
    print(f"\nNo feature IDs found for branch '{branch}'.")
    print("Tip: copy .env.sample to .env and fill in the GUIDs to skip this prompt.")
    ws_id = input("  FEATURE_WORKSPACE_ID : ").strip()
    lh_id = input("  FEATURE_LAKEHOUSE_ID : ").strip()
    _validate_guid(ws_id, "FEATURE_WORKSPACE_ID")
    _validate_guid(lh_id, "FEATURE_LAKEHOUSE_ID")
    return ws_id, lh_id


def _validate_guid(value: str, name: str) -> None:
    pattern = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")
    if not pattern.match(value):
        sys.exit(f"ERROR: '{value}' is not a valid GUID for {name}")


def create_or_update_value_set(value_set_path: Path, branch_label: str,
                                ws_id: str, lh_id: str, *, dry_run: bool) -> bool:
    data = {
        "$schema": "https://developer.microsoft.com/json-schemas/fabric/item/variableLibrary/definition/valueSet/1.0.0/schema.json",
        "name": branch_label,
        "variableOverrides": [
            {"name": "target_workspace_id", "value": ws_id},
            {"name": "target_lakehouse_id", "value": lh_id},
        ],
    }
    rel = value_set_path.relative_to(REPO_ROOT)
    if dry_run:
        print(f"  [dry-run] Would write value set: {rel}")
        return True
    save_json(value_set_path, data)
    print(f"  Value set written: {rel}")
    return True


def update_settings(branch_label: str, *, dry_run: bool) -> bool:
    settings = load_json(SETTINGS_FILE)
    if branch_label not in settings["valueSetsOrder"]:
        if dry_run:
            print(f"  [dry-run] Would add '{branch_label}' to settings.json valueSetsOrder")
            return True
        settings["valueSetsOrder"].append(branch_label)
        save_json(SETTINGS_FILE, settings)
        print(f"  Added '{branch_label}' to settings.json valueSetsOrder")
        return True
    return False


def repoint_items(dev_ws_id: str, dev_lh_id: str,
                  new_ws_id: str, new_lh_id: str, *, dry_run: bool) -> list[str]:
    """Replace dev IDs with new IDs in all registered item types that need rewriting."""
    changed: list[str] = []
    for item_type in ITEM_TYPES:
        if not item_type["needs_rewrite"]:
            continue
        for pattern in item_type["file_patterns"]:
            for path in sorted(FABRIC_DIR.glob(pattern)):
                text = path.read_text(encoding="utf-8")
                if item_type["content_filter"] and not item_type["content_filter"](text):
                    continue
                updated = text.replace(dev_ws_id, new_ws_id).replace(dev_lh_id, new_lh_id)
                if updated != text:
                    rel = path.relative_to(REPO_ROOT)
                    if dry_run:
                        print(f"  [dry-run] Would repoint ({item_type['name']}): {rel}")
                    else:
                        path.write_text(updated, encoding="utf-8")
                        print(f"  Repointed ({item_type['name']}): {rel}")
                    changed.append(str(rel))
    if not changed:
        print("  No files with target IDs found.")
    return changed


def validate_no_ids(ws_id: str, lh_id: str, *, label: str = "target") -> list[str]:
    """Scan all registered item types for leftover IDs that should not be present."""
    id_map = {"workspace": ws_id, "lakehouse": lh_id}
    warnings: list[str] = []
    for item_type in ITEM_TYPES:
        for pattern in item_type["file_patterns"]:
            for path in sorted(FABRIC_DIR.glob(pattern)):
                if not path.exists():
                    continue
                text = path.read_text(encoding="utf-8")
                if item_type["content_filter"] and not item_type["content_filter"](text):
                    continue
                for key in item_type["id_keys"]:
                    if id_map[key] in text:
                        warnings.append(
                            f"  {path.relative_to(REPO_ROOT)}: still contains {label} {key} ID"
                        )
    return warnings


def validate_dev_ids_present(dev_ws_id: str, dev_lh_id: str) -> list[str]:
    """Confirm that files which need rewriting DO contain dev IDs (for --check-ready mode)."""
    id_map = {"workspace": dev_ws_id, "lakehouse": dev_lh_id}
    errors: list[str] = []
    for item_type in ITEM_TYPES:
        if not item_type["needs_rewrite"]:
            continue
        for pattern in item_type["file_patterns"]:
            for path in sorted(FABRIC_DIR.glob(pattern)):
                if not path.exists():
                    continue
                text = path.read_text(encoding="utf-8")
                if item_type["content_filter"] and not item_type["content_filter"](text):
                    continue
                for key in item_type["id_keys"]:
                    if id_map[key] not in text:
                        errors.append(
                            f"  {path.relative_to(REPO_ROOT)}: missing dev {key} ID ({item_type['name']})"
                        )
    return errors


def validate_no_stray_value_sets() -> list[str]:
    """Check for value set files that are not in the allowed set."""
    errors: list[str] = []
    for vs_file in sorted(VALUE_SETS_DIR.glob("*.json")):
        basename = vs_file.stem
        if basename not in ALLOWED_VALUE_SETS:
            errors.append(
                f"  {vs_file.relative_to(REPO_ROOT)}: feature branch value set '{basename}' must be removed"
            )
    return errors


def remove_value_set(value_set_path: Path, *, dry_run: bool) -> bool:
    if not value_set_path.exists():
        print("  Value set already removed.")
        return False
    rel = value_set_path.relative_to(REPO_ROOT)
    if dry_run:
        print(f"  [dry-run] Would delete: {rel}")
        return True
    value_set_path.unlink()
    print(f"  Deleted: {rel}")
    return True


def remove_from_settings(branch_label: str, *, dry_run: bool) -> bool:
    settings = load_json(SETTINGS_FILE)
    if branch_label in settings["valueSetsOrder"]:
        if dry_run:
            print(f"  [dry-run] Would remove '{branch_label}' from settings.json valueSetsOrder")
            return True
        settings["valueSetsOrder"].remove(branch_label)
        save_json(SETTINGS_FILE, settings)
        print(f"  Removed '{branch_label}' from settings.json valueSetsOrder")
        return True
    return False


def main() -> None:
    parser = argparse.ArgumentParser(description="Manage feature-branch Fabric workspace bindings.")
    parser.add_argument("--dry-run", action="store_true", help="Show what would change without writing files.")
    parser.add_argument("--swap-to-dev", action="store_true", help="Revert feature IDs back to dev and remove the feature value set.")
    parser.add_argument("--check-ready", action="store_true", help="CI check: confirm dev IDs present and no stray value sets.")
    args = parser.parse_args()
    dry_run: bool = args.dry_run
    swap_to_dev: bool = args.swap_to_dev
    check_ready: bool = args.check_ready

    if check_ready:
        _run_check_ready()
        return

    if dry_run:
        print("=== DRY RUN — no files will be modified ===\n")

    branch = get_current_branch()
    print(f"Branch: {branch}")

    if branch in ("main", "dev"):
        sys.exit("ERROR: This script is for feature branches only, not main/dev.")

    branch_label = sanitize_branch_name(branch)
    value_set_path = VALUE_SETS_DIR / f"{branch_label}.json"

    print("\n1. Loading dev baseline IDs...")
    dev_ws_id, dev_lh_id = get_dev_ids()
    print(f"  Dev workspace : {dev_ws_id}")
    print(f"  Dev lakehouse : {dev_lh_id}")

    if swap_to_dev:
        _run_swap_to_dev(branch, branch_label, value_set_path, dev_ws_id, dev_lh_id, dry_run=dry_run)
    else:
        _run_swap_to_feature(branch, branch_label, value_set_path, dev_ws_id, dev_lh_id, dry_run=dry_run)


def _run_swap_to_feature(branch: str, branch_label: str, value_set_path: Path,
                          dev_ws_id: str, dev_lh_id: str, *, dry_run: bool) -> None:
    print("\n2. Resolving feature environment IDs...")
    new_ws_id, new_lh_id = resolve_feature_ids(branch, value_set_path)
    print(f"  Feature workspace : {new_ws_id}")
    print(f"  Feature lakehouse : {new_lh_id}")

    if new_ws_id == dev_ws_id and new_lh_id == dev_lh_id:
        sys.exit("ERROR: Feature IDs are identical to dev IDs. Nothing to do.")

    changes: list[str] = []

    print("\n3. Creating/updating value set...")
    if create_or_update_value_set(value_set_path, branch_label, new_ws_id, new_lh_id, dry_run=dry_run):
        changes.append(f"Value set: {value_set_path.relative_to(REPO_ROOT)}")
    if update_settings(branch_label, dry_run=dry_run):
        changes.append(f"Settings:  {SETTINGS_FILE.relative_to(REPO_ROOT)}")

    print("\n4. Repointing items...")
    repointed = repoint_items(dev_ws_id, dev_lh_id, new_ws_id, new_lh_id, dry_run=dry_run)
    for r in repointed:
        changes.append(f"Repointed: {r}")

    print("\n5. Validating...")
    if dry_run:
        print("  [dry-run] Skipping validation (files unchanged).")
    else:
        warnings = validate_no_ids(dev_ws_id, dev_lh_id, label="dev")
        if warnings:
            print("  WARNINGS — dev IDs still found:")
            for w in warnings:
                print(w)
        else:
            print("  Clean — no dev IDs in critical files.")

    _print_summary(branch, dev_ws_id, dev_lh_id, new_ws_id, new_lh_id, changes, dry_run=dry_run)


def _run_swap_to_dev(branch: str, branch_label: str, value_set_path: Path,
                      dev_ws_id: str, dev_lh_id: str, *, dry_run: bool) -> None:
    print("\n2. Loading feature IDs from value set...")
    if not value_set_path.exists():
        sys.exit(f"ERROR: No value set found at {value_set_path.relative_to(REPO_ROOT)}. Nothing to revert.")

    overrides = load_json(value_set_path)["variableOverrides"]
    lookup = {o["name"]: o["value"] for o in overrides}
    feature_ws_id = lookup["target_workspace_id"]
    feature_lh_id = lookup["target_lakehouse_id"]
    print(f"  Feature workspace : {feature_ws_id}")
    print(f"  Feature lakehouse : {feature_lh_id}")

    changes: list[str] = []

    print("\n3. Reverting items to dev...")
    reverted = repoint_items(feature_ws_id, feature_lh_id, dev_ws_id, dev_lh_id, dry_run=dry_run)
    for r in reverted:
        changes.append(f"Reverted:  {r}")

    print("\n4. Removing feature value set...")
    if remove_value_set(value_set_path, dry_run=dry_run):
        changes.append(f"Deleted:   {value_set_path.relative_to(REPO_ROOT)}")
    if remove_from_settings(branch_label, dry_run=dry_run):
        changes.append(f"Settings:  {SETTINGS_FILE.relative_to(REPO_ROOT)}")

    print("\n5. Validating...")
    if dry_run:
        print("  [dry-run] Skipping validation (files unchanged).")
    else:
        warnings = validate_no_ids(feature_ws_id, feature_lh_id, label="feature")
        if warnings:
            print("  WARNINGS — feature IDs still found:")
            for w in warnings:
                print(w)
        else:
            print("  Clean — no feature IDs in critical files.")

    _print_summary(branch, feature_ws_id, feature_lh_id, dev_ws_id, dev_lh_id, changes, dry_run=dry_run, swap_to_dev=True)


def _run_check_ready() -> None:
    """CI check: confirm dev IDs are present in rewritable files and no stray value sets exist."""
    print("Check PR ready: confirming repo state is safe to merge...\n")

    dev_ws_id, dev_lh_id = get_dev_ids()
    print(f"  Dev workspace : {dev_ws_id}")
    print(f"  Dev lakehouse : {dev_lh_id}")

    errors: list[str] = []

    print("\n1. Checking rewritable files contain dev IDs...")
    missing = validate_dev_ids_present(dev_ws_id, dev_lh_id)
    errors.extend(missing)
    for m in missing:
        print(m)
    if not missing:
        print("  OK — all rewritable files contain dev IDs.")

    print("\n2. Checking for stray feature branch value sets...")
    stray = validate_no_stray_value_sets()
    errors.extend(stray)
    for s in stray:
        print(s)
    if not stray:
        print("  OK — no stray value sets.")

    if errors:
        print(f"\nCHECK FAILED — {len(errors)} error(s) found.")
        print("Run 'python scripts/workspace_swap.py --swap-to-dev' to fix.")
        sys.exit(1)
    else:
        print("\nCHECK PASSED — repo is ready for merge.")


def _print_summary(branch: str, old_ws_id: str, old_lh_id: str,
                   new_ws_id: str, new_lh_id: str, changes: list[str],
                   *, dry_run: bool, swap_to_dev: bool = False) -> None:
    mode = "SWAP-TO-DEV" if swap_to_dev else "SWAP-TO-FEATURE"
    print(f"\n── Summary ({mode}) ──────────────────────────────")
    print(f"  Branch:            {branch}")
    print(f"  Workspace ID:      {old_ws_id} → {new_ws_id}")
    print(f"  Lakehouse ID:      {old_lh_id} → {new_lh_id}")
    print(f"  Files {'that would change' if dry_run else 'changed'}:")
    for c in changes:
        print(f"    {c}")
    if not changes:
        print("    (none)")
    if dry_run:
        print("\nRe-run without --dry-run to apply changes.")
    else:
        print("\nDone. Review changes with 'git diff', then commit if desired.")


if __name__ == "__main__":
    main()
