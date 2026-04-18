"""
Manage feature-branch workspace bindings for Fabric.

Bootstrap (repoint dev → feature):
    python scripts/branch_env.py
    python scripts/branch_env.py --dry-run

Reset (revert feature → dev, before PR):
    python scripts/branch_env.py --reset
    python scripts/branch_env.py --reset --dry-run

No arguments required — reads the current git branch automatically.
"""

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

# ── Paths (relative to repo root) ──────────────────────────────────────────
REPO_ROOT = Path(subprocess.run(
    ["git", "rev-parse", "--show-toplevel"],
    capture_output=True, text=True, check=True,
).stdout.strip())

FABRIC_DIR = REPO_ROOT / "data" / "fabric"
VARIABLES_FILE = FABRIC_DIR / "Patterns_Variables.VariableLibrary" / "variables.json"
SETTINGS_FILE = FABRIC_DIR / "Patterns_Variables.VariableLibrary" / "settings.json"
VALUE_SETS_DIR = FABRIC_DIR / "Patterns_Variables.VariableLibrary" / "valueSets"
EXPRESSIONS_FILE = FABRIC_DIR / "Patterns_Semantic_Model.SemanticModel" / "definition" / "expressions.tmdl"


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
      2. Fabric REST API lookup (if azure-identity is available).
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

    # 2. Try Fabric REST API
    ids = _try_fabric_api_lookup(branch)
    if ids:
        return ids

    # 3. Interactive fallback
    print(f"\nCould not auto-discover IDs for branch '{branch}'.")
    print("Enter the feature workspace and lakehouse IDs manually.")
    ws_id = input("  target_workspace_id : ").strip()
    lh_id = input("  target_lakehouse_id : ").strip()
    _validate_guid(ws_id, "target_workspace_id")
    _validate_guid(lh_id, "target_lakehouse_id")
    return ws_id, lh_id


def _try_fabric_api_lookup(branch: str) -> tuple[str, str] | None:
    """
    Optional: look up workspace by naming convention and lakehouse by name.
    Requires azure-identity and requests.
    """
    try:
        from azure.identity import DefaultAzureCredential
        import requests
    except ImportError:
        return None

    try:
        token = DefaultAzureCredential().get_token("https://api.fabric.microsoft.com/.default").token
        headers = {"Authorization": f"Bearer {token}"}

        # Look for workspace matching repo-name + branch convention
        resp = requests.get(
            "https://api.fabric.microsoft.com/v1/workspaces",
            headers=headers, timeout=30,
        )
        resp.raise_for_status()
        workspaces = resp.json().get("value", [])

        # Match by branch name appearing in workspace displayName
        sanitized = sanitize_branch_name(branch).lower()
        ws = next((w for w in workspaces if sanitized in w["displayName"].lower()), None)
        if not ws:
            return None

        ws_id = ws["id"]
        print(f"  Found workspace: {ws['displayName']} ({ws_id})")

        # Find lakehouse by name inside that workspace
        resp = requests.get(
            f"https://api.fabric.microsoft.com/v1/workspaces/{ws_id}/lakehouses",
            headers=headers, timeout=30,
        )
        resp.raise_for_status()
        lakehouses = resp.json().get("value", [])
        lh = next((l for l in lakehouses if l["displayName"] == "PatternsLakehouse"), None)
        if not lh:
            return None

        lh_id = lh["id"]
        print(f"  Found lakehouse: {lh['displayName']} ({lh_id})")
        return ws_id, lh_id

    except requests.RequestException as exc:
        print(f"  API lookup skipped: {exc}")
        return None


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


def repoint_semantic_model(dev_ws_id: str, dev_lh_id: str,
                           new_ws_id: str, new_lh_id: str, *, dry_run: bool) -> bool:
    content = EXPRESSIONS_FILE.read_text(encoding="utf-8")
    original = content
    content = content.replace(dev_ws_id, new_ws_id)
    content = content.replace(dev_lh_id, new_lh_id)
    if content != original:
        rel = EXPRESSIONS_FILE.relative_to(REPO_ROOT)
        if dry_run:
            print(f"  [dry-run] Would repoint: {rel}")
            return True
        EXPRESSIONS_FILE.write_text(content, encoding="utf-8")
        print(f"  Repointed: {rel}")
        return True
    print("  Semantic model already repointed (no dev IDs found).")
    return False


def repoint_notebooks(dev_ws_id: str, dev_lh_id: str,
                      new_ws_id: str, new_lh_id: str, *, dry_run: bool) -> list[str]:
    """Replace dev IDs in all notebook META dependency blocks."""
    changed = []
    for nb_file in FABRIC_DIR.glob("*.Notebook/notebook-content.py"):
        content = nb_file.read_text(encoding="utf-8")
        original = content
        content = content.replace(dev_ws_id, new_ws_id)
        content = content.replace(dev_lh_id, new_lh_id)
        if content != original:
            rel = nb_file.relative_to(REPO_ROOT)
            if dry_run:
                print(f"  [dry-run] Would repoint: {rel}")
            else:
                nb_file.write_text(content, encoding="utf-8")
                print(f"  Repointed: {rel}")
            changed.append(str(rel))
    if not changed:
        print("  No notebooks with dev IDs found.")
    return changed


def validate_no_dev_ids(dev_ws_id: str, dev_lh_id: str) -> list[str]:
    """Scan rewritten files for leftover dev IDs."""
    critical_files = [
        EXPRESSIONS_FILE,
        *FABRIC_DIR.glob("*.Notebook/notebook-content.py"),
    ]
    warnings = []
    for f in critical_files:
        if not f.exists():
            continue
        text = f.read_text(encoding="utf-8")
        for label, dev_id in [("workspace", dev_ws_id), ("lakehouse", dev_lh_id)]:
            if dev_id in text:
                warnings.append(f"  {f.relative_to(REPO_ROOT)}: still contains dev {label} ID")
    return warnings


def validate_no_feature_ids(feature_ws_id: str, feature_lh_id: str) -> list[str]:
    """Scan rewritten files for leftover feature IDs after reset."""
    critical_files = [
        EXPRESSIONS_FILE,
        *FABRIC_DIR.glob("*.Notebook/notebook-content.py"),
    ]
    warnings = []
    for f in critical_files:
        if not f.exists():
            continue
        text = f.read_text(encoding="utf-8")
        for label, fid in [("workspace", feature_ws_id), ("lakehouse", feature_lh_id)]:
            if fid in text:
                warnings.append(f"  {f.relative_to(REPO_ROOT)}: still contains feature {label} ID")
    return warnings


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
    parser.add_argument("--reset", action="store_true", help="Revert feature IDs back to dev and remove value set.")
    args = parser.parse_args()
    dry_run: bool = args.dry_run
    reset: bool = args.reset

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

    if reset:
        _run_reset(branch, branch_label, value_set_path, dev_ws_id, dev_lh_id, dry_run=dry_run)
    else:
        _run_bootstrap(branch, branch_label, value_set_path, dev_ws_id, dev_lh_id, dry_run=dry_run)


def _run_bootstrap(branch: str, branch_label: str, value_set_path: Path,
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

    print("\n4. Repointing semantic model...")
    if repoint_semantic_model(dev_ws_id, dev_lh_id, new_ws_id, new_lh_id, dry_run=dry_run):
        changes.append(f"Repointed: {EXPRESSIONS_FILE.relative_to(REPO_ROOT)}")

    print("\n5. Repointing notebooks...")
    repointed_nbs = repoint_notebooks(dev_ws_id, dev_lh_id, new_ws_id, new_lh_id, dry_run=dry_run)
    for nb in repointed_nbs:
        changes.append(f"Repointed: {nb}")

    print("\n6. Validating...")
    if dry_run:
        print("  [dry-run] Skipping validation (files unchanged).")
    else:
        warnings = validate_no_dev_ids(dev_ws_id, dev_lh_id)
        if warnings:
            print("  WARNINGS — dev IDs still found:")
            for w in warnings:
                print(w)
        else:
            print("  Clean — no dev IDs in critical files.")

    _print_summary(branch, dev_ws_id, dev_lh_id, new_ws_id, new_lh_id, changes, dry_run=dry_run)


def _run_reset(branch: str, branch_label: str, value_set_path: Path,
               dev_ws_id: str, dev_lh_id: str, *, dry_run: bool) -> None:
    print("\n2. Loading feature IDs from value set...")
    if not value_set_path.exists():
        sys.exit(f"ERROR: No value set found at {value_set_path.relative_to(REPO_ROOT)}. Nothing to reset.")

    overrides = load_json(value_set_path)["variableOverrides"]
    lookup = {o["name"]: o["value"] for o in overrides}
    feature_ws_id = lookup["target_workspace_id"]
    feature_lh_id = lookup["target_lakehouse_id"]
    print(f"  Feature workspace : {feature_ws_id}")
    print(f"  Feature lakehouse : {feature_lh_id}")

    changes: list[str] = []

    print("\n3. Reverting semantic model to dev...")
    if repoint_semantic_model(feature_ws_id, feature_lh_id, dev_ws_id, dev_lh_id, dry_run=dry_run):
        changes.append(f"Reverted:  {EXPRESSIONS_FILE.relative_to(REPO_ROOT)}")

    print("\n4. Reverting notebooks to dev...")
    reverted_nbs = repoint_notebooks(feature_ws_id, feature_lh_id, dev_ws_id, dev_lh_id, dry_run=dry_run)
    for nb in reverted_nbs:
        changes.append(f"Reverted:  {nb}")

    print("\n5. Removing feature value set...")
    if remove_value_set(value_set_path, dry_run=dry_run):
        changes.append(f"Deleted:   {value_set_path.relative_to(REPO_ROOT)}")
    if remove_from_settings(branch_label, dry_run=dry_run):
        changes.append(f"Settings:  {SETTINGS_FILE.relative_to(REPO_ROOT)}")

    print("\n6. Validating...")
    if dry_run:
        print("  [dry-run] Skipping validation (files unchanged).")
    else:
        warnings = validate_no_feature_ids(feature_ws_id, feature_lh_id)
        if warnings:
            print("  WARNINGS — feature IDs still found:")
            for w in warnings:
                print(w)
        else:
            print("  Clean — no feature IDs in critical files.")

    _print_summary(branch, feature_ws_id, feature_lh_id, dev_ws_id, dev_lh_id, changes, dry_run=dry_run, reset=True)


def _print_summary(branch: str, old_ws_id: str, old_lh_id: str,
                   new_ws_id: str, new_lh_id: str, changes: list[str],
                   *, dry_run: bool, reset: bool = False) -> None:
    mode = "RESET" if reset else "BOOTSTRAP"
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
