"""Offline tests for post-ETL Semantic Model refresh and error propagation."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from unittest.mock import MagicMock, Mock

import pytest
import requests
from azure.core.credentials import AccessToken, TokenCredential
from azure.core.exceptions import ClientAuthenticationError

import refresh_semantic_model as refresh

WORKSPACE_ID = "11111111-1111-4111-8111-111111111111"
MODEL_ID = "22222222-2222-4222-8222-222222222222"
REFRESH_ID = "33333333-3333-4333-8333-333333333333"
OTHER_ID = "44444444-4444-4444-8444-444444444444"
MODEL_NAME = "Patterns_Semantic_Model"
TOKEN = "test-power-bi-token-not-a-real-credential"
MODELS_URL = f"{refresh.POWER_BI_BASE_URL}/groups/{WORKSPACE_ID}/datasets"
MODEL_URL = f"{MODELS_URL}/{MODEL_ID}"
OPERATION_URL = f"{MODEL_URL}/refreshes/{REFRESH_ID}"


class Clock:
    def __init__(self) -> None:
        self.seconds = 0.0

    def monotonic(self) -> float:
        return self.seconds

    def sleep(self, seconds: float) -> None:
        self.seconds += seconds


@pytest.fixture
def clock(monkeypatch: pytest.MonkeyPatch) -> Clock:
    fake = Clock()
    monkeypatch.setattr(refresh.time, "monotonic", fake.monotonic)
    monkeypatch.setattr(refresh.time, "sleep", fake.sleep)
    return fake


@pytest.fixture
def credential() -> Mock:
    result = Mock(spec=TokenCredential)
    result.get_token.return_value = AccessToken(TOKEN, 2000000000)
    return result


@pytest.fixture
def http(monkeypatch: pytest.MonkeyPatch) -> Mock:
    result = Mock(spec=requests.request)
    monkeypatch.setattr(refresh.requests, "request", result)
    return result


def response(
    status: int,
    body: object = None,
    headers: dict[str, str] | None = None,
) -> requests.Response:
    result = requests.Response()
    result.status_code = status
    result._content = json.dumps(body).encode("utf-8")
    if headers:
        result.headers.update(headers)
    return result


def models_response() -> requests.Response:
    return response(200, {"value": [{"name": MODEL_NAME, "id": MODEL_ID, "isRefreshable": False}]})


def accepted_response(headers: dict[str, str] | None = None) -> requests.Response:
    return response(202, headers={"Location": OPERATION_URL, "x-ms-request-id": REFRESH_ID, **(headers or {})})


def completed_response() -> requests.Response:
    return response(200, {"status": "Completed", "extendedStatus": "Completed"})


def test_full_refresh_tracks_its_operation_and_uses_power_bi_token(
    http: Mock, credential: Mock, clock: Clock, capsys: pytest.CaptureFixture,
) -> None:
    http.side_effect = [
        models_response(),
        accepted_response({"Retry-After": "2"}),
        response(202, {"status": "Unknown", "extendedStatus": "NotStarted"}, {"Retry-After": "3"}),
        completed_response(),
    ]
    refresh.refresh_semantic_model(credential, WORKSPACE_ID, MODEL_NAME)
    assert [(call.args[0], call.args[1]) for call in http.call_args_list] == [
        ("GET", MODELS_URL),
        ("POST", f"{MODEL_URL}/refreshes"),
        ("GET", OPERATION_URL),
        ("GET", OPERATION_URL),
    ]
    assert http.call_args_list[1].kwargs["json"] == {"type": "full", "commitMode": "transactional"}
    for call in http.call_args_list:
        assert call.kwargs["headers"]["Authorization"] == f"Bearer {TOKEN}"
        assert call.kwargs["allow_redirects"] is False
        assert 0 < call.kwargs["timeout"] <= 30
    assert all(call.args == (refresh.POWER_BI_SCOPE,) for call in credential.get_token.call_args_list)
    assert credential.get_token.call_count == 4
    assert clock.seconds == 5
    output = capsys.readouterr().out
    assert "refreshed successfully" in output
    assert REFRESH_ID in output
    assert TOKEN not in output


@pytest.mark.parametrize("model_name", ["Missing", MODEL_NAME])
def test_missing_or_duplicate_names_fail_without_starting_refresh(
    http: Mock, credential: Mock, clock: Clock, model_name: str,
) -> None:
    http.return_value = response(200, {"value": [
        {"name": MODEL_NAME, "id": MODEL_ID},
        {"name": MODEL_NAME, "id": OTHER_ID},
    ]})
    with pytest.raises(refresh.SemanticModelRefreshError, match="not found|Multiple"):
        refresh.refresh_semantic_model(credential, WORKSPACE_ID, model_name)
    assert http.call_count == 1


@pytest.mark.parametrize("body", [
    {}, {"value": None}, {"value": {}}, {"value": [None]},
    {"value": [{"id": MODEL_ID}]}, {"value": [{"name": MODEL_NAME, "id": "bad"}]},
])
def test_invalid_model_list_shapes_fail(http: Mock, credential: Mock, clock: Clock, body: dict) -> None:
    http.return_value = response(200, body)
    with pytest.raises(refresh.SemanticModelRefreshError):
        refresh.refresh_semantic_model(credential, WORKSPACE_ID, MODEL_NAME)
    assert http.call_count == 1


@pytest.mark.parametrize("value", [
    None, 123, "", "invalid", "00000000-0000-0000-0000-000000000000",
    f"{{{WORKSPACE_ID}}}", WORKSPACE_ID.replace("-", ""), f" {WORKSPACE_ID}",
])
def test_invalid_workspace_ids_fail_before_authentication(
    http: Mock, credential: Mock, clock: Clock, value: str,
) -> None:
    with pytest.raises(refresh.SemanticModelRefreshError, match="FABRIC_WORKSPACE_ID"):
        refresh.refresh_semantic_model(credential, value, MODEL_NAME)
    http.assert_not_called()
    credential.get_token.assert_not_called()


def test_guid_validation_normalizes_case() -> None:
    guid = "abcdefab-cdef-4abc-8abc-abcdefabcdef"
    assert refresh._guid(guid.upper(), "ID") == guid


@pytest.mark.parametrize("model_name", ["", "  ", f" {MODEL_NAME}", f"{MODEL_NAME}\n", f"{MODEL_NAME}\r"])
def test_invalid_model_names_fail_before_authentication(
    http: Mock, credential: Mock, clock: Clock, model_name: str,
) -> None:
    with pytest.raises(refresh.SemanticModelRefreshError, match="SEMANTIC_MODEL_NAME"):
        refresh.refresh_semantic_model(credential, WORKSPACE_ID, model_name)
    http.assert_not_called()


@pytest.mark.parametrize("timeout", [0, -1, float("inf"), float("nan")])
def test_invalid_timeout_is_rejected(http: Mock, credential: Mock, clock: Clock, timeout: float) -> None:
    with pytest.raises(refresh.SemanticModelRefreshError, match="timeout"):
        refresh.refresh_semantic_model(credential, WORKSPACE_ID, MODEL_NAME, timeout_seconds=timeout)
    http.assert_not_called()


@pytest.mark.parametrize("location", [
    None,
    "https://example.com/refreshes",
    OPERATION_URL.replace("https:", "http:"),
    OPERATION_URL.replace("api.powerbi.com", "api.powerbi.com.example.com"),
    OPERATION_URL.replace("api.powerbi.com", "user@api.powerbi.com"),
    OPERATION_URL.replace("api.powerbi.com", "api.powerbi.com:443"),
    OPERATION_URL.replace(WORKSPACE_ID, OTHER_ID),
    OPERATION_URL.replace(MODEL_ID, OTHER_ID),
    f"{OPERATION_URL}?other=true",
    f"{OPERATION_URL}#fragment",
    OPERATION_URL.replace(REFRESH_ID, "bad-id"),
    OPERATION_URL.replace(REFRESH_ID, "00000000-0000-0000-0000-000000000000"),
    "/refreshes/" + REFRESH_ID,
    "https://[invalid",
])
def test_invalid_location_fails_without_polling(
    http: Mock, credential: Mock, clock: Clock, location: str | None,
) -> None:
    headers = {"Location": location} if location is not None else {}
    http.side_effect = [models_response(), response(202, headers=headers)]
    with pytest.raises(refresh.SemanticModelRefreshError):
        refresh.refresh_semantic_model(credential, WORKSPACE_ID, MODEL_NAME)
    assert http.call_count == 2


@pytest.mark.parametrize("request_id", [OTHER_ID, "not-a-guid"])
def test_request_id_must_match_location(http: Mock, credential: Mock, clock: Clock, request_id: str) -> None:
    http.side_effect = [models_response(), accepted_response({"x-ms-request-id": request_id})]
    with pytest.raises(refresh.SemanticModelRefreshError, match="request ID|different operations"):
        refresh.refresh_semantic_model(credential, WORKSPACE_ID, MODEL_NAME)
    assert http.call_count == 2


def test_location_is_sufficient_when_request_id_header_is_absent(
    http: Mock, credential: Mock, clock: Clock,
) -> None:
    http.side_effect = [
        models_response(), response(202, headers={"Location": OPERATION_URL}), completed_response(),
    ]
    refresh.refresh_semantic_model(credential, WORKSPACE_ID, MODEL_NAME)


@pytest.mark.parametrize("status,extended", [
    ("Failed", "Failed"), ("Cancelled", "Cancelled"), ("Disabled", ""),
    ("TimedOut", ""), ("Unknown", "Failed"), ("Unknown", "Cancelled"),
    ("Unknown", "TimedOut"), ("Unknown", "Disabled"),
])
def test_terminal_failures_surface_date_field_and_partition_details(
    http: Mock, credential: Mock, clock: Clock, status: str, extended: str,
) -> None:
    body = {
        "status": status,
        "extendedStatus": extended,
        "objects": [{"table": "patients", "partition": "patients", "status": "Failed"}],
        "messages": [{"message": "date_of_birth could not be processed", "type": "Error"}],
        "serviceExceptionJson": '{"errorCode":"ProcessingError"}',
    }
    http.side_effect = [models_response(), accepted_response(), response(200, body)]
    with pytest.raises(refresh.SemanticModelRefreshError) as error:
        refresh.refresh_semantic_model(credential, WORKSPACE_ID, MODEL_NAME)
    assert "date_of_birth" in str(error.value)
    assert "patients" in str(error.value)
    assert "ProcessingError" in str(error.value)
    assert REFRESH_ID in str(error.value)


@pytest.mark.parametrize("http_status,body", [
    (202, {"status": "Completed", "extendedStatus": "Completed"}),
    (200, {"status": "Completed", "extendedStatus": "InProgress"}),
    (200, {"status": "Completed", "extendedStatus": "Failed"}),
    (200, {}),
    (202, {"status": 123}),
    (200, {"status": "Unknown", "extendedStatus": None}),
    (200, {"status": "Unexpected"}),
    (202, {"status": "Unknown", "extendedStatus": "Unexpected"}),
])
def test_inconsistent_or_malformed_poll_status_is_not_success(
    http: Mock, credential: Mock, clock: Clock, http_status: int, body: dict,
) -> None:
    http.side_effect = [models_response(), accepted_response(), response(http_status, body)]
    with pytest.raises(refresh.SemanticModelRefreshError):
        refresh.refresh_semantic_model(credential, WORKSPACE_ID, MODEL_NAME)


def test_http_200_alone_does_not_prove_completion(http: Mock, credential: Mock, clock: Clock) -> None:
    http.side_effect = [
        models_response(), accepted_response(),
        response(200, {"status": "Unknown", "extendedStatus": "InProgress"}),
        response(200, {"status": "Completed"}),
    ]
    refresh.refresh_semantic_model(credential, WORKSPACE_ID, MODEL_NAME)
    assert http.call_count == 4


@pytest.mark.parametrize("phase", ["list", "poll"])
@pytest.mark.parametrize("body", [None, [], "invalid JSON"])
def test_invalid_json_and_object_shapes_fail(
    http: Mock, credential: Mock, clock: Clock, phase: str, body: object,
) -> None:
    bad = response(200, body)
    if body == "invalid JSON":
        bad._content = b"invalid JSON"
    http.side_effect = [bad] if phase == "list" else [models_response(), accepted_response(), bad]
    with pytest.raises(refresh.SemanticModelRefreshError, match="JSON"):
        refresh.refresh_semantic_model(credential, WORKSPACE_ID, MODEL_NAME)


@pytest.mark.parametrize("method", ["GET", "POST"])
def test_throttled_requests_are_retried_with_retry_after(
    http: Mock, credential: Mock, clock: Clock, method: str,
) -> None:
    throttled = response(429, {"error": {"code": "Throttled"}}, {"Retry-After": "7"})
    http.side_effect = (
        [throttled, models_response(), accepted_response(), completed_response()]
        if method == "GET" else
        [models_response(), throttled, accepted_response(), completed_response()]
    )
    refresh.refresh_semantic_model(credential, WORKSPACE_ID, MODEL_NAME)
    assert clock.seconds == 7 + refresh.POLL_INTERVAL_SECONDS
    assert [call.args[0] for call in http.call_args_list].count(method) == (3 if method == "GET" else 2)


@pytest.mark.parametrize("status", [500, 502, 503, 504])
def test_get_server_errors_are_retried_within_deadline(
    http: Mock, credential: Mock, clock: Clock, status: int,
) -> None:
    http.side_effect = [
        models_response(), accepted_response(), response(status), completed_response(),
    ]
    refresh.refresh_semantic_model(credential, WORKSPACE_ID, MODEL_NAME)
    assert clock.seconds == refresh.POLL_INTERVAL_SECONDS + refresh.THROTTLE_INTERVAL_SECONDS
    assert [call.args[0] for call in http.call_args_list].count("POST") == 1


@pytest.mark.parametrize("status", [400, 401, 403, 404, 500, 503])
def test_post_errors_do_not_submit_a_second_refresh(
    http: Mock, credential: Mock, clock: Clock, status: int,
) -> None:
    http.side_effect = [
        models_response(), response(status, {"error": {"code": "Denied", "message": "Check model permissions"}}),
    ]
    with pytest.raises(refresh.SemanticModelRefreshError, match=f"HTTP {status}") as error:
        refresh.refresh_semantic_model(credential, WORKSPACE_ID, MODEL_NAME)
    assert "Check model permissions" in str(error.value)
    assert [call.args[0] for call in http.call_args_list].count("POST") == 1


def test_post_network_timeout_is_not_retried(
    http: Mock, credential: Mock, clock: Clock,
) -> None:
    http.side_effect = [models_response(), requests.Timeout(f"Potentially accepted POST with {TOKEN}")]
    with pytest.raises(refresh.SemanticModelRefreshError, match="Timeout") as error:
        refresh.refresh_semantic_model(credential, WORKSPACE_ID, MODEL_NAME)
    assert TOKEN not in str(error.value)
    assert http.call_count == 2


def test_repeated_throttling_times_out_during_discovery(
    http: Mock, credential: Mock, clock: Clock,
) -> None:
    http.return_value = response(429, headers={"Retry-After": "10"})
    with pytest.raises(refresh.SemanticModelRefreshError, match="timed out"):
        refresh.refresh_semantic_model(credential, WORKSPACE_ID, MODEL_NAME, timeout_seconds=25)
    assert clock.seconds == 25
    assert http.call_count == 3
    assert all(call.args[0] == "GET" for call in http.call_args_list)


def test_pending_refresh_times_out_without_an_extra_poll(
    http: Mock, credential: Mock, clock: Clock,
) -> None:
    http.side_effect = [
        models_response(), accepted_response(),
        response(202, {"status": "Unknown", "extendedStatus": "NotStarted"}),
        response(202, {"status": "Unknown", "extendedStatus": "InProgress"}),
    ]
    with pytest.raises(refresh.SemanticModelRefreshError, match="timed out"):
        refresh.refresh_semantic_model(credential, WORKSPACE_ID, MODEL_NAME, timeout_seconds=25)
    assert clock.seconds == 25
    assert http.call_count == 4
    assert max(call.kwargs["timeout"] for call in http.call_args_list) <= 25


def test_retry_after_cannot_extend_the_overall_deadline(
    http: Mock, credential: Mock, clock: Clock,
) -> None:
    http.side_effect = [models_response(), accepted_response({"Retry-After": "99999"})]
    with pytest.raises(refresh.SemanticModelRefreshError, match="timed out"):
        refresh.refresh_semantic_model(credential, WORKSPACE_ID, MODEL_NAME, timeout_seconds=18)
    assert clock.seconds == 18
    assert http.call_count == 2


def test_deadline_includes_authentication(http: Mock, credential: Mock, clock: Clock) -> None:
    def slow_token(*scopes: str) -> AccessToken:
        clock.sleep(30)
        return AccessToken(TOKEN, 2000000000)

    credential.get_token.side_effect = slow_token
    with pytest.raises(refresh.SemanticModelRefreshError, match="timed out"):
        refresh.refresh_semantic_model(credential, WORKSPACE_ID, MODEL_NAME, timeout_seconds=25)
    http.assert_not_called()


def test_late_completed_response_cannot_bypass_deadline(
    http: Mock, credential: Mock, clock: Clock,
) -> None:
    responses = iter([models_response(), accepted_response(), completed_response()])

    def slow_poll(method: str, url: str, **kwargs: object) -> requests.Response:
        if url == OPERATION_URL:
            clock.sleep(20)
        return next(responses)

    http.side_effect = slow_poll
    with pytest.raises(refresh.SemanticModelRefreshError, match="timed out"):
        refresh.refresh_semantic_model(credential, WORKSPACE_ID, MODEL_NAME, timeout_seconds=25)


@pytest.mark.parametrize("raw,expected", [(None, 10), ("0", 1), ("5", 5), (" 7 ", 7)])
def test_numeric_retry_after_and_default(raw: str | None, expected: int) -> None:
    assert refresh.retry_after_seconds(raw, 10) == expected


def test_retry_after_http_date(monkeypatch: pytest.MonkeyPatch) -> None:
    timestamp = datetime(2026, 10, 10, 12, tzinfo=timezone.utc).timestamp()
    monkeypatch.setattr(refresh.time, "time", lambda: timestamp - 7)
    assert refresh.retry_after_seconds("Sat, 10 Oct 2026 12:00:00 GMT", 10) == 7
    monkeypatch.setattr(refresh.time, "time", lambda: timestamp + 7)
    assert refresh.retry_after_seconds("Sat, 10 Oct 2026 12:00:00 GMT", 10) == 1


@pytest.mark.parametrize("raw", ["bad", "-1", "1.5", "Sat, 10 Oct 2026 12:00:00", "9" * 400])
def test_invalid_retry_after_is_not_silently_defaulted(raw: str) -> None:
    with pytest.raises(refresh.SemanticModelRefreshError, match="Retry-After"):
        refresh.retry_after_seconds(raw, 10)


def test_invalid_retry_after_response_fails(http: Mock, credential: Mock, clock: Clock) -> None:
    http.return_value = response(429, headers={"Retry-After": "invalid"})
    with pytest.raises(refresh.SemanticModelRefreshError, match="Retry-After"):
        refresh.refresh_semantic_model(credential, WORKSPACE_ID, MODEL_NAME)


def test_all_acquired_tokens_are_redacted_from_refresh_failure(
    http: Mock, credential: Mock, clock: Clock, capsys: pytest.CaptureFixture,
) -> None:
    tokens = [f"{TOKEN}-{i}" for i in range(3)]
    credential.get_token.side_effect = [AccessToken(token, 2000000000) for token in tokens]
    http.side_effect = [
        models_response(), accepted_response(),
        response(200, {"status": "Failed", "messages": [{"message": " ".join(tokens)}]}),
    ]
    with pytest.raises(refresh.SemanticModelRefreshError) as error:
        refresh.refresh_semantic_model(credential, WORKSPACE_ID, MODEL_NAME)
    output = capsys.readouterr().out
    for token in tokens:
        assert token not in str(error.value)
        assert token not in output
    assert "[REDACTED]" in str(error.value)


def test_empty_access_token_does_not_send_a_request(http: Mock, credential: Mock, clock: Clock) -> None:
    credential.get_token.return_value = AccessToken("", 2000000000)
    with pytest.raises(refresh.SemanticModelRefreshError, match="access token"):
        refresh.refresh_semantic_model(credential, WORKSPACE_ID, MODEL_NAME)
    http.assert_not_called()


@pytest.fixture
def cli_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    for name, value in {
        "AZURE_TENANT_ID": WORKSPACE_ID,
        "AZURE_CLIENT_ID": OTHER_ID,
        "AZURE_CLIENT_SECRET": "test-client-secret-not-a-real-credential",
        "FABRIC_WORKSPACE_ID": WORKSPACE_ID,
        "SEMANTIC_MODEL_NAME": MODEL_NAME,
    }.items():
        monkeypatch.setenv(name, value)


@pytest.mark.parametrize("name", [
    "AZURE_TENANT_ID", "AZURE_CLIENT_ID", "AZURE_CLIENT_SECRET",
    "FABRIC_WORKSPACE_ID", "SEMANTIC_MODEL_NAME",
])
def test_cli_missing_configuration_exits_nonzero(
    monkeypatch: pytest.MonkeyPatch, cli_environment: None, name: str, capsys: pytest.CaptureFixture,
) -> None:
    monkeypatch.delenv(name)
    factory = Mock()
    monkeypatch.setattr(refresh, "ClientSecretCredential", factory)
    with pytest.raises(SystemExit) as error:
        refresh.main()
    assert error.value.code == 1
    assert name in capsys.readouterr().err
    factory.assert_not_called()


def test_cli_refresh_failure_exits_nonzero_and_redacts_client_secret(
    monkeypatch: pytest.MonkeyPatch, cli_environment: None, credential: Mock,
    http: Mock, clock: Clock, capsys: pytest.CaptureFixture,
) -> None:
    context = MagicMock()
    context.__enter__.return_value = credential
    factory = Mock(return_value=context)
    monkeypatch.setattr(refresh, "ClientSecretCredential", factory)
    http.side_effect = [
        models_response(),
        response(403, {"error": {"message": f"Denied: test-client-secret-not-a-real-credential {TOKEN}"}}),
    ]
    with pytest.raises(SystemExit) as error:
        refresh.main()
    assert error.value.code == 1
    output = capsys.readouterr()
    assert "HTTP 403" in output.err
    assert "test-client-secret-not-a-real-credential" not in output.err
    assert TOKEN not in output.err
    context.__exit__.assert_called_once()


def test_cli_authentication_error_is_explicit(
    monkeypatch: pytest.MonkeyPatch, cli_environment: None, capsys: pytest.CaptureFixture,
) -> None:
    factory = Mock(side_effect=ClientAuthenticationError("Service principal authentication failed"))
    monkeypatch.setattr(refresh, "ClientSecretCredential", factory)
    with pytest.raises(SystemExit) as error:
        refresh.main()
    assert error.value.code == 1
    assert "authentication failed" in capsys.readouterr().err


def test_cli_success_uses_existing_credential_configuration(
    monkeypatch: pytest.MonkeyPatch, cli_environment: None, credential: Mock,
    http: Mock, clock: Clock, capsys: pytest.CaptureFixture,
) -> None:
    context = MagicMock()
    context.__enter__.return_value = credential
    factory = Mock(return_value=context)
    monkeypatch.setattr(refresh, "ClientSecretCredential", factory)
    http.side_effect = [models_response(), accepted_response(), completed_response()]
    refresh.main()
    assert factory.call_args.kwargs["tenant_id"] == WORKSPACE_ID
    assert factory.call_args.kwargs["client_id"] == OTHER_ID
    assert factory.call_args.kwargs["connection_timeout"] == refresh.REQUEST_TIMEOUT_SECONDS
    assert "refreshed successfully" in capsys.readouterr().out
    context.__exit__.assert_called_once()
