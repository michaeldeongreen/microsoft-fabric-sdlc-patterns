"""Tests for scripts/run_fabric_etl.py.

Covers the pure helpers extracted from the ETL runner: item lookup by display
name and poll-response interpretation. The orchestration in main() and the
real polling loop are not unit-tested here — those are validated end-to-end
via the ETL workflows.
"""

from __future__ import annotations

import pytest

from run_fabric_etl import find_item_id_by_name, interpret_poll_response, pipeline_job_body


# ---------- find_item_id_by_name ----------


def test_find_item_id_by_name_happy_path() -> None:
    items = [
        {"id": "111", "displayName": "Other"},
        {"id": "222", "displayName": "Target"},
    ]
    assert find_item_id_by_name(items, "Target") == "222"


def test_find_item_id_by_name_not_found_exits(capsys: pytest.CaptureFixture) -> None:
    items = [{"id": "111", "displayName": "Other"}]
    with pytest.raises(SystemExit):
        find_item_id_by_name(items, "Missing")
    captured = capsys.readouterr().out
    assert "Item not found: Missing" in captured
    assert "Other" in captured  # available items listed


def test_find_item_id_by_name_empty_list_exits() -> None:
    with pytest.raises(SystemExit):
        find_item_id_by_name([], "Any")


def test_find_item_id_by_name_rejects_duplicates() -> None:
    items = [
        {"id": "first", "displayName": "Same"},
        {"id": "second", "displayName": "Same"},
    ]
    with pytest.raises(SystemExit, match="Multiple items"):
        find_item_id_by_name(items, "Same")


# ---------- interpret_poll_response ----------


def test_interpret_poll_response_completed() -> None:
    body = {"status": "Completed"}
    assert interpret_poll_response(200, body, {}) == ("completed",)


def test_interpret_poll_response_failed_with_reason() -> None:
    body = {"status": "Failed", "failureReason": "out of memory"}
    assert interpret_poll_response(200, body, {}) == ("failed", "Failed", "out of memory")


def test_interpret_poll_response_failed_without_reason() -> None:
    """When failureReason is missing, fall back to a sentinel string."""
    body = {"status": "Failed"}
    assert interpret_poll_response(200, body, {}) == (
        "failed",
        "Failed",
        "No failure reason provided",
    )


def test_interpret_poll_response_cancelled_treated_as_failed() -> None:
    body = {"status": "Cancelled"}
    action = interpret_poll_response(200, body, {})
    assert action[0] == "failed"
    assert action[1] == "Cancelled"


def test_interpret_poll_response_deduped_treated_as_failed() -> None:
    body = {"status": "Deduped"}
    action = interpret_poll_response(200, body, {})
    assert action[0] == "failed"
    assert action[1] == "Deduped"


def test_interpret_poll_response_in_progress_200() -> None:
    """200 with a non-terminal status means keep polling at default interval."""
    body = {"status": "InProgress"}
    assert interpret_poll_response(200, body, {}) == ("still_running", 30)


def test_interpret_poll_response_202_with_retry_after() -> None:
    """202 means keep polling; honor Retry-After if present."""
    headers = {"Retry-After": "45"}
    assert interpret_poll_response(202, {}, headers) == ("still_running", 45)


def test_interpret_poll_response_202_default_retry_after() -> None:
    """Missing Retry-After falls back to 30 seconds."""
    assert interpret_poll_response(202, {}, {}) == ("still_running", 30)


def test_interpret_poll_response_unexpected_status() -> None:
    assert interpret_poll_response(500, {}, {}) == ("unexpected", 500)


def test_pipeline_parameters_use_verified_execution_data_shape() -> None:
    assert pipeline_job_body("DataPipeline", "Pipeline", "Test-123") == {
        "executionData": {"parameters": {"run_label": "Test-123"}}
    }


def test_no_parameter_notebook_and_pipeline_calls_remain_unchanged() -> None:
    assert pipeline_job_body("Notebook", "RunNotebook", "") is None
    assert pipeline_job_body("DataPipeline", "Pipeline", "") is None


@pytest.mark.parametrize("label", ["a" * 65, "invalid label", "label\n", " label", "quote'"])
def test_invalid_pipeline_run_labels_fail(label: str) -> None:
    with pytest.raises(ValueError, match="RUN_LABEL"):
        pipeline_job_body("DataPipeline", "Pipeline", label)


def test_wrong_job_type_and_notebook_parameter_fail() -> None:
    with pytest.raises(ValueError, match="JOB_TYPE"):
        pipeline_job_body("DataPipeline", "RunNotebook", "valid")
    with pytest.raises(ValueError, match="RUN_LABEL"):
        pipeline_job_body("Notebook", "RunNotebook", "valid")


def test_unknown_job_status_fails_instead_of_successful_polling() -> None:
    assert interpret_poll_response(200, {"status": "Unknown"}, {}) == ("unexpected", 200)
