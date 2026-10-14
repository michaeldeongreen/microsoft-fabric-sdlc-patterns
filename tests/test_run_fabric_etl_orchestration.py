"""Mocked HTTP tests for the real runner; no Fabric access is required."""

from __future__ import annotations

import json
from unittest.mock import Mock

import pytest
import requests
from azure.core.credentials import AccessToken

import run_fabric_etl as runner

WORKSPACE = "11111111-1111-4111-8111-111111111111"
ITEM = "22222222-2222-4222-8222-222222222222"
JOB = "33333333-3333-4333-8333-333333333333"
ITEMS_URL = f"https://api.fabric.microsoft.com/v1/workspaces/{WORKSPACE}/items?type=DataPipeline"
JOBS_URL = f"https://api.fabric.microsoft.com/v1/workspaces/{WORKSPACE}/items/{ITEM}/jobs/instances"
POLL_URL = f"{JOBS_URL}/{JOB}"


def response(status: int, body: object = None, headers: dict[str, str] | None = None) -> requests.Response:
    result = requests.Response()
    result.status_code = status
    result._content = json.dumps(body).encode("utf-8")
    if headers:
        result.headers.update(headers)
    return result


@pytest.fixture
def execution(monkeypatch: pytest.MonkeyPatch) -> tuple[Mock, Mock, list[float]]:
    for name, value in {
        "FABRIC_WORKSPACE_ID": WORKSPACE,
        "AZURE_TENANT_ID": WORKSPACE,
        "AZURE_CLIENT_ID": ITEM,
        "AZURE_CLIENT_SECRET": "unit-test-only",
        "ITEM_NAME": "Pipeline",
        "ITEM_TYPE": "DataPipeline",
        "JOB_TYPE": "Pipeline",
        "RUN_LABEL": "Test-123",
    }.items():
        monkeypatch.setenv(name, value)
    credential = Mock()
    credential.get_token.return_value = AccessToken("unit-test-token", 2000000000)
    monkeypatch.setattr(runner, "ClientSecretCredential", Mock(return_value=credential))
    get, post = Mock(), Mock()
    monkeypatch.setattr(runner.requests, "get", get)
    monkeypatch.setattr(runner.requests, "post", post)
    clock = [0.0]
    monkeypatch.setattr(runner.time, "monotonic", lambda: clock[0])
    monkeypatch.setattr(runner.time, "sleep", lambda delay: clock.__setitem__(0, clock[0] + delay))
    get.side_effect = [
        response(200, {"value": [{"id": ITEM, "displayName": "Pipeline"}]}),
        response(200, {"status": "Completed"}),
    ]
    post.return_value = response(202, headers={"Location": POLL_URL, "Retry-After": "1"})
    return get, post, clock


def test_pipeline_execution_tracks_canonical_job_and_forwards_run_label(
    execution: tuple[Mock, Mock, list[float]], capsys: pytest.CaptureFixture[str],
) -> None:
    get, post, _ = execution
    with pytest.raises(SystemExit) as result:
        runner.main()
    assert result.value.code == 0
    assert post.call_args.args == (f"{JOBS_URL}?jobType=Pipeline",)
    assert post.call_args.kwargs["json"] == {"executionData": {"parameters": {"run_label": "Test-123"}}}
    assert get.call_args_list[0].args == (ITEMS_URL,)
    assert get.call_args_list[1].args == (POLL_URL,)
    for call in [*get.call_args_list, *post.call_args_list]:
        assert call.kwargs["allow_redirects"] is False
        assert 0 < call.kwargs["timeout"] <= 30
    assert JOB in capsys.readouterr().out


def test_notebook_run_still_sends_no_parameter_body(
    execution: tuple[Mock, Mock, list[float]], monkeypatch: pytest.MonkeyPatch,
) -> None:
    get, post, _ = execution
    monkeypatch.setenv("ITEM_TYPE", "Notebook")
    monkeypatch.setenv("JOB_TYPE", "RunNotebook")
    monkeypatch.delenv("RUN_LABEL")
    with pytest.raises(SystemExit) as result:
        runner.main()
    assert result.value.code == 0
    assert post.call_args.kwargs["json"] is None
    assert get.call_args_list[0].args[0].endswith("?type=Notebook")


@pytest.mark.parametrize("location", [
    POLL_URL, POLL_URL.replace("api.fabric.microsoft.com", "regional.example.test"),
    f"/jobs/instances/{JOB}", f"{POLL_URL}?routing=example",
])
def test_location_only_supplies_job_id_not_credential_destination(
    execution: tuple[Mock, Mock, list[float]], location: str,
) -> None:
    get, post, _ = execution
    post.return_value = response(202, headers={"Location": location})
    with pytest.raises(SystemExit) as result:
        runner.main()
    assert result.value.code == 0
    assert get.call_args.args == (POLL_URL,)


@pytest.mark.parametrize("location", [None, "", "/jobs/not-a-guid"])
def test_missing_or_invalid_job_identity_does_not_poll(
    execution: tuple[Mock, Mock, list[float]], location: str | None,
) -> None:
    get, post, _ = execution
    post.return_value = response(202, headers={"Location": location} if location else {})
    with pytest.raises((SystemExit, ValueError)):
        runner.main()
    assert get.call_count == 1
    assert post.call_count == 1


def test_lookup_checks_all_pages_for_ambiguous_names(execution: tuple[Mock, Mock, list[float]]) -> None:
    get, post, _ = execution
    get.side_effect = [
        response(200, {"value": [{"id": ITEM, "displayName": "Pipeline"}], "continuationToken": "page2"}),
        response(200, {"value": [{"id": JOB, "displayName": "Pipeline"}]}),
    ]
    with pytest.raises(SystemExit, match="Multiple items"):
        runner.main()
    assert get.call_args.kwargs["params"] == {"continuationToken": "page2"}
    post.assert_not_called()


@pytest.mark.parametrize("body", [{}, [], {"value": None}, {"value": [{}]}])
def test_malformed_inventory_does_not_start_job(
    execution: tuple[Mock, Mock, list[float]], body: object,
) -> None:
    get, post, _ = execution
    get.return_value = response(200, body)
    get.side_effect = None
    with pytest.raises(ValueError, match="List Items"):
        runner.main()
    post.assert_not_called()


def test_repeated_continuation_token_fails(execution: tuple[Mock, Mock, list[float]]) -> None:
    get, post, _ = execution
    get.side_effect = [
        response(200, {"value": [], "continuationToken": "repeat"}),
        response(200, {"value": [], "continuationToken": "repeat"}),
    ]
    with pytest.raises(ValueError, match="repeated continuation"):
        runner.main()
    post.assert_not_called()


def test_failed_pipeline_surfaces_native_activity_failure(
    execution: tuple[Mock, Mock, list[float]], capsys: pytest.CaptureFixture[str],
) -> None:
    get, post, _ = execution
    get.side_effect = [
        response(200, {"value": [{"id": ITEM, "displayName": "Pipeline"}]}),
        response(200, {
            "status": "Failed", "startTimeUtc": "2026-10-11T00:00:00Z",
            "failureReason": {"errorCode": "ActivityFailed", "message": "Validation failed"},
        }),
    ]
    post.side_effect = [
        response(202, headers={"Location": POLL_URL}),
        response(200, {"value": [{
            "activityName": "Validate_Patterns_Data", "status": "Failed",
            "error": {"message": "patient count below threshold"},
        }]}),
    ]
    with pytest.raises(SystemExit) as result:
        runner.main()
    assert result.value.code == 1
    assert "patient count below threshold" in capsys.readouterr().out
    assert post.call_args.args[0].endswith(f"/datapipelines/pipelineruns/{JOB}/queryactivityruns")


def test_long_retry_after_does_not_escape_deadline(
    execution: tuple[Mock, Mock, list[float]], monkeypatch: pytest.MonkeyPatch,
) -> None:
    get, post, clock = execution
    monkeypatch.setattr(runner, "JOB_TIMEOUT_SECONDS", 10)
    post.return_value = response(202, headers={"Location": POLL_URL, "Retry-After": "9999"})
    with pytest.raises(ValueError, match="timed out"):
        runner.main()
    assert clock[0] == 10
    assert get.call_count == 1


def test_completed_response_after_deadline_is_not_success(
    execution: tuple[Mock, Mock, list[float]], monkeypatch: pytest.MonkeyPatch,
) -> None:
    get, _, clock = execution
    monkeypatch.setattr(runner, "JOB_TIMEOUT_SECONDS", 10)
    values = iter([
        response(200, {"value": [{"id": ITEM, "displayName": "Pipeline"}]}),
        response(200, {"status": "Completed"}),
    ])

    def delayed(url: str, **kwargs: object) -> requests.Response:
        if url == POLL_URL:
            clock[0] += 10
        return next(values)

    get.side_effect = delayed
    with pytest.raises(ValueError, match="timed out"):
        runner.main()


def test_post_timeout_is_not_resubmitted(execution: tuple[Mock, Mock, list[float]]) -> None:
    _, post, _ = execution
    post.side_effect = requests.Timeout("Network timeout")
    with pytest.raises(requests.Timeout):
        runner.main()
    post.assert_called_once()
