"""Tests for scripts/deploy_fabric_cicd_bulk.py.

The headline test proves the documented fallback: this repo's parameter.yml
contains ``$items``/``$workspace`` dynamic variables, which is exactly the
condition fabric-cicd uses to fall back from bulk publish to standard per-item
publish. As long as that assertion holds, the fabric-cicd-bulk deploy method
always falls back to standard mode for this repository.

The fabric-cicd library calls themselves are not unit-tested here — those are
validated end-to-end via the deploy workflows.
"""

from __future__ import annotations

import re
from pathlib import Path

import yaml

from deploy_fabric_cicd_bulk import (
    BULK_FEATURE_FLAGS,
    _env_flag,
    print_fallback_proof,
)

# Mirrors fabric-cicd's constants.DYNAMIC_VARIABLES_REGEX. When any parameter
# replacement value matches this, FabricWorkspace.contains_param_vars becomes
# True and bulk publish falls back to standard. Kept in sync intentionally.
DYNAMIC_VARIABLES_REGEX = re.compile(r"^\$(workspace|items)\.")

PARAMETER_FILE = (
    Path(__file__).resolve().parents[1] / "data" / "fabric" / "parameter.yml"
)


def _replace_values(parameter_file: Path) -> list[str]:
    """Return every string replace_value across the find_replace rules."""
    parsed = yaml.safe_load(parameter_file.read_text(encoding="utf-8"))
    values: list[str] = []
    for rule in parsed.get("find_replace", []):
        replace_value = rule.get("replace_value", {})
        values.extend(v for v in replace_value.values() if isinstance(v, str))
    return values


def test_bulk_feature_flags_are_both_required_flags() -> None:
    """Both experimental + bulk flags must be requested, experimental first."""
    assert BULK_FEATURE_FLAGS == [
        "enable_experimental_features",
        "enable_bulk_publish",
    ]


def test_parameter_file_forces_bulk_fallback() -> None:
    """PROOF: parameter.yml uses $items/$workspace, so bulk always falls back.

    fabric-cicd sets contains_param_vars=True when any replacement value matches
    DYNAMIC_VARIABLES_REGEX, which forces standard per-item publish. If this test
    ever fails, parameter.yml stopped using dynamic variables and the
    fabric-cicd-bulk method may genuinely engage the bulk API.
    """
    values = _replace_values(PARAMETER_FILE)
    assert values, "parameter.yml has no find_replace replace values"
    dynamic = [v for v in values if DYNAMIC_VARIABLES_REGEX.match(v)]
    assert dynamic, (
        "Expected at least one $items/$workspace dynamic variable in "
        f"parameter.yml, found none in {values!r}"
    )


def test_parameter_file_uses_both_items_and_workspace() -> None:
    """Stronger proof: both $items and $workspace dynamic variables are present."""
    values = _replace_values(PARAMETER_FILE)
    assert any(v.startswith("$items.") for v in values)
    assert any(v.startswith("$workspace.") for v in values)


def test_env_flag_truthy_values(monkeypatch) -> None:
    """1/true/yes (any case, surrounding whitespace) are treated as truthy."""
    for value in ("1", "true", "YES", "Yes", "  true  "):
        monkeypatch.setenv("FAIL_IF_BULK_USED", value)
        assert _env_flag("FAIL_IF_BULK_USED") is True


def test_env_flag_falsy_values(monkeypatch) -> None:
    """Empty and non-affirmative values are treated as falsy."""
    for value in ("", "0", "false", "no", "maybe"):
        monkeypatch.setenv("FAIL_IF_BULK_USED", value)
        assert _env_flag("FAIL_IF_BULK_USED") is False


def test_env_flag_unset_is_false(monkeypatch) -> None:
    """An unset variable is falsy."""
    monkeypatch.delenv("FAIL_IF_BULK_USED", raising=False)
    assert _env_flag("FAIL_IF_BULK_USED") is False


def test_print_fallback_proof_reports_fallback(capsys) -> None:
    """When no phase used bulk, the banner states the fallback and its reason."""
    print_fallback_proof(
        contains_param_vars=True,
        phase_bulk_results={"phase 1": False, "phase 2": False},
    )
    out = capsys.readouterr().out
    assert "fell back to standard per-item publish for all phases" in out
    assert "contains_param_vars     : True" in out


def test_print_fallback_proof_reports_bulk_used(capsys) -> None:
    """When a phase used bulk, the banner reports that bulk engaged."""
    print_fallback_proof(
        contains_param_vars=False,
        phase_bulk_results={"phase 1": True, "phase 2": True},
    )
    out = capsys.readouterr().out
    assert "bulk import API engaged for at least one phase" in out
