"""Tests for scripts/deploy_fabric_cicd.py.

Covers the Phase 2 scope-filter logic. The fabric-cicd library calls
themselves are not unit-tested — those are validated end-to-end via the
deploy workflows.
"""

from __future__ import annotations

from deploy_fabric_cicd import PHASE1_TYPES, remaining_types_for_phase2


def test_remaining_types_none_input_returns_none() -> None:
    """When item_type_in_scope is unset, Phase 2 deploys all types."""
    assert remaining_types_for_phase2(None) is None


def test_remaining_types_empty_list_returns_none() -> None:
    """An empty list has the same effect as None."""
    assert remaining_types_for_phase2([]) is None


def test_remaining_types_no_overlap_with_phase1() -> None:
    """When the user lists only non-Phase-1 types, return them unchanged."""
    assert remaining_types_for_phase2(["Notebook", "Report"]) == ["Notebook", "Report"]


def test_remaining_types_partial_overlap_strips_phase1() -> None:
    """Phase 1 types are removed from the user's list."""
    result = remaining_types_for_phase2(
        ["Lakehouse", "Notebook", "Ontology", "Report"]
    )
    assert result == ["Notebook", "Report"]


def test_remaining_types_only_phase1_returns_none() -> None:
    """Documented footgun: listing only Phase 1 types makes Phase 2 deploy all.

    The empty result is converted to None, and FabricWorkspace treats None as
    'all types in scope'. A caller wanting strict scoping must include the
    non-Phase-1 types they actually want.
    """
    assert remaining_types_for_phase2(["Lakehouse", "Ontology"]) is None
    assert remaining_types_for_phase2(["Lakehouse"]) is None


def test_phase1_types_constant_unchanged() -> None:
    """Pin the Phase 1 type list so accidental edits are caught."""
    assert PHASE1_TYPES == ["Lakehouse", "Ontology"]
