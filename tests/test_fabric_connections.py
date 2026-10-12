"""Offline tests for bounded Fabric REST transport and native WI connection setup."""

from __future__ import annotations

import io
import json
import traceback
from collections.abc import Callable
from copy import deepcopy
from email.message import Message
from typing import Any, cast
from unittest.mock import Mock
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlsplit
from urllib.request import Request

import pytest

from scripts import fabric_connections as fabric

WORKSPACE = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
APPLICATION = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"
PRINCIPAL = "cccccccc-cccc-4ccc-8ccc-cccccccccccc"
NOTEBOOK = "dddddddd-dddd-4ddd-8ddd-dddddddddddd"
REFRESH = "eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee"
ASSIGNMENT = "ffffffff-ffff-4fff-8fff-ffffffffffff"
OTHER = "12345678-1234-4123-8123-123456789012"
OPERATION = "01234567-89ab-4cde-8f01-23456789abcd"
BEARER = "offline-bearer-that-must-not-appear"
BODY_SECRET = "offline-body-secret-that-must-not-appear"
IDENTITY: dict[str, object] = {"applicationId": APPLICATION, "servicePrincipalId": PRINCIPAL}
SP_CREDENTIALS = {
    "tenantId": "99999999-9999-4999-8999-999999999999",
    "servicePrincipalClientId": APPLICATION,
    "servicePrincipalSecret": BODY_SECRET,
}
EXPECTED = {
    "NOTEBOOK_CONNECTION_ID": NOTEBOOK,
    "SEMANTIC_MODEL_REFRESH_CONNECTION_ID": REFRESH,
}


class FakeResponse:
    def __init__(
        self, status: int = 200, body: object = None,
        headers: dict[str, str] | None = None,
    ) -> None:
        self.status = status
        self.headers = Message()
        for key, value in (headers or {}).items():
            self.headers[key] = value
        self._stream = io.BytesIO(
            body if isinstance(body, bytes)
            else b"" if body is None else json.dumps(body).encode("utf-8")
        )

    def read(self, count: int = -1) -> bytes:
        return self._stream.read(count)

    def __enter__(self) -> FakeResponse:
        return self

    def __exit__(self, *args: object) -> None:
        self._stream.close()


class Clock:
    def __init__(self) -> None:
        self.now = 0.0
        self.sleeps: list[float] = []

    def monotonic(self) -> float:
        return self.now

    def sleep(self, delay: float) -> None:
        self.sleeps.append(delay)
        self.now += delay


class ScriptedOpener:
    def __init__(self, responses: list[FakeResponse | Exception]) -> None:
        self.responses = list(responses)
        self.calls: list[tuple[Request, float]] = []

    def open(self, request: Request, *, timeout: float) -> FakeResponse:
        self.calls.append((request, timeout))
        assert self.responses, "Unexpected HTTP call; real network is forbidden"
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


def http_error(
    status: int, *, code: str = "UnknownError",
    headers: dict[str, str] | None = None,
) -> HTTPError:
    message = Message()
    for key, value in (headers or {}).items():
        message[key] = value
    body = json.dumps({
        "errorCode": code, "message": f"{BEARER} {BODY_SECRET}",
        "details": {"secret": BODY_SECRET},
    }).encode("utf-8")
    return HTTPError(f"{fabric.FABRIC_API_ROOT}/connections", status, BODY_SECRET, message, io.BytesIO(body))


@pytest.fixture(autouse=True)
def forbid_real_network(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        fabric, "build_opener",
        Mock(side_effect=AssertionError("Tests must install a fake opener")),
    )


@pytest.fixture
def clock(monkeypatch: pytest.MonkeyPatch) -> Clock:
    clock = Clock()
    monkeypatch.setattr(fabric, "time", clock)
    return clock


@pytest.fixture
def client_factory(
    monkeypatch: pytest.MonkeyPatch, clock: Clock,
) -> Callable[..., tuple[fabric.FabricRestClient, ScriptedOpener]]:
    def make(
        responses: list[FakeResponse | Exception], *, token_provider: Callable[[], str] | None = None,
        **options: Any,
    ) -> tuple[fabric.FabricRestClient, ScriptedOpener]:
        opener = ScriptedOpener(responses)
        monkeypatch.setattr(fabric, "build_opener", Mock(return_value=opener))
        client = fabric.FabricRestClient(token_provider or (lambda: BEARER), **options)
        return client, opener

    return make


def connection(
    kind: str, *, connection_id: str | None = None,
    name: str | None = None,
    authentication: str = "WorkspaceIdentity",
) -> dict[str, object]:
    suffix = "Notebook" if kind == "Notebook" else "SemanticModelRefresh"
    return {
        "id": connection_id or (NOTEBOOK if kind == "Notebook" else REFRESH),
        "displayName": name or f"Patterns-{WORKSPACE}-{suffix}",
        "connectivityType": "ShareableCloud",
        "connectionDetails": {"type": kind, "path": ""},
        "credentialDetails": {"credentialType": authentication},
    }


def capabilities() -> list[dict[str, object]]:
    return [
        {
            "type": kind,
            "creationMethods": [{"name": f"{kind}.Actions", "parameters": []}],
            "supportedCredentialTypes": ["ServicePrincipal", "WorkspaceIdentity"],
            "supportsSkipTestConnection": True,
        }
        for kind in ("Notebook", "PowerBIDatasets")
    ]


def role(role: str = "Contributor", *, principal_id: str = PRINCIPAL) -> dict[str, object]:
    return {
        "id": ASSIGNMENT,
        "principal": {"id": principal_id, "type": "ServicePrincipal"},
        "role": role,
    }


class MemoryFabric:
    """Stateful Core API double; all ensure calls stay in memory."""

    def __init__(self, *, cold: bool = False, authentication: str = "WorkspaceIdentity") -> None:
        self.authentication = authentication
        self.workspace: dict[str, object] = {"id": WORKSPACE}
        if not cold:
            self.workspace["workspaceIdentity"] = deepcopy(IDENTITY)
        self.connections = [] if cold else [
            connection("Notebook", authentication=authentication),
            connection("PowerBIDatasets", authentication=authentication),
        ]
        self.roles = [] if cold else [role()]
        self.metadata = capabilities()
        self.calls: list[tuple[str, str, dict[str, object] | None]] = []
        self.failures: dict[str, fabric.FabricRestError] = {}
        self.create_error: fabric.FabricRestError | None = None
        self.patch_error: fabric.FabricRestError | None = None
        self.stored_credentials: dict[str, dict[str, object]] = {}
        self.race: str | None = None
        self.provision_result = deepcopy(IDENTITY)

    def list(self, path: str) -> list[dict[str, object]]:
        self.calls.append(("LIST", path, None))
        if path in self.failures:
            raise self.failures[path]
        values = {
            "/connections": self.connections,
            "/connections/supportedConnectionTypes?showAllCreationMethods=true": self.metadata,
            f"/workspaces/{WORKSPACE}/roleAssignments": self.roles,
        }
        assert path in values, f"Unexpected collection: {path}"
        return deepcopy(values[path])

    def request(
        self, method: str, path: str, body: dict[str, object] | None = None,
        *, wait_for_result: bool = True,
    ) -> dict[str, object]:
        self.calls.append((method, path, deepcopy(body)))
        if path in self.failures:
            raise self.failures[path]
        if method == "GET" and path == f"/workspaces/{WORKSPACE}":
            return deepcopy(self.workspace)
        if method == "GET" and path.startswith("/connections/"):
            matches = [item for item in self.connections if item["id"] == path.rsplit("/", 1)[1]]
            if not matches:
                raise fabric.FabricRestError("Missing connection", status_code=404, error_code="EntityNotFound")
            return deepcopy(matches[0])
        if method == "POST" and path.endswith("/provisionIdentity"):
            self.workspace["workspaceIdentity"] = deepcopy(self.provision_result)
            return deepcopy(self.provision_result)
        if method == "POST" and path.endswith("/roleAssignments"):
            assert body is not None
            added = {"id": ASSIGNMENT, **deepcopy(body)}
            self.roles.append(added)
            return deepcopy(added)
        if method == "PATCH" and path.endswith(f"/roleAssignments/{ASSIGNMENT}"):
            assert body is not None
            self.roles[0]["role"] = body["role"]
            return deepcopy(self.roles[0])
        if method == "PATCH" and path.startswith("/connections/"):
            if self.patch_error is not None:
                raise self.patch_error
            assert body is not None
            connection_id = path.rsplit("/", 1)[1]
            matches = [item for item in self.connections if item["id"] == connection_id]
            assert len(matches) == 1
            details = cast(dict[str, object], body["credentialDetails"])
            credentials = cast(dict[str, object], details["credentials"])
            self.stored_credentials[connection_id] = deepcopy(credentials)
            matches[0]["credentialDetails"] = {
                "credentialType": credentials["credentialType"],
                **{key: value for key, value in details.items() if key != "credentials"},
            }
            return deepcopy(matches[0])
        if method == "POST" and path == "/connections":
            if self.create_error is not None:
                raise self.create_error
            assert body is not None
            details = cast(dict[str, object], body["connectionDetails"])
            kind = cast(str, details["type"])
            credential_details = cast(dict[str, object], body["credentialDetails"])
            credentials = cast(dict[str, object], credential_details["credentials"])
            created = connection(
                kind, name=cast(str, body["displayName"]),
                authentication=cast(str, credentials["credentialType"]),
            )
            if kind == "Notebook" and self.race is not None:
                if self.race != "hidden":
                    if self.race == "incompatible":
                        created["credentialDetails"] = {"credentialType": "Basic"}
                    self.connections.append(created)
                    if self.race == "duplicates":
                        self.connections.append(connection(kind, connection_id=OTHER))
                raise fabric.FabricRestError(
                    "Connection name exists", status_code=409, error_code="DuplicateConnectionName",
                )
            self.connections.append(created)
            self.stored_credentials[cast(str, created["id"])] = deepcopy(credentials)
            return deepcopy(created)
        raise AssertionError(f"Unexpected request: {method} {path}")

    def ensure(self, **options: Any) -> dict[str, str]:
        options.setdefault("authentication", self.authentication)
        return fabric.ensure_pipeline_connections(cast(fabric.FabricRestClient, self), WORKSPACE, **options)

    @property
    def writes(self) -> list[tuple[str, str, dict[str, object] | None]]:
        return [call for call in self.calls if call[0] not in ("GET", "LIST")]


@pytest.mark.parametrize("bad", [
    None, 1, "", "not-a-guid", BODY_SECRET, f" {WORKSPACE}", f"{WORKSPACE}\n",
    WORKSPACE.replace("-", ""), f"{{{WORKSPACE}}}", "00000000-0000-0000-0000-000000000000",
])
def test_guid_validation_does_not_echo_input(bad: object) -> None:
    with pytest.raises(fabric.FabricConnectionError) as caught:
        fabric.validate_guid(bad)
    assert BODY_SECRET not in str(caught.value)


def test_guid_normalizes_case() -> None:
    assert fabric.validate_guid(WORKSPACE.upper()) == WORKSPACE


@pytest.mark.parametrize("options", [
    {"mode": "unknown"}, {"mode": "existing"},
    {"mode": "existing", "notebook_connection_id": NOTEBOOK},
    {"notebook_connection_id": ""},
    {"refresh_connection_id": "00000000-0000-0000-0000-000000000000"},
    {"notebook_connection_id": "11111111-1111-4111-8111-111111111111"},
    {"refresh_connection_id": "22222222-2222-4222-8222-222222222222"},
    {"notebook_connection_id": NOTEBOOK, "refresh_connection_id": NOTEBOOK.upper()},
])
def test_config_errors_precede_any_client_call(options: dict[str, Any]) -> None:
    client = Mock(spec=fabric.FabricRestClient)
    with pytest.raises(fabric.FabricConnectionError):
        fabric.ensure_pipeline_connections(client, WORKSPACE, **options)
    assert client.mock_calls == []


def test_pure_preflight_requires_no_client_or_token() -> None:
    assert fabric.validate_connection_configuration(
        WORKSPACE, mode="existing", notebook_connection_id=NOTEBOOK, refresh_connection_id=REFRESH,
    ) is None


@pytest.mark.parametrize("status", [200, 201, 204])
def test_empty_success_returns_object(
    client_factory: Callable[..., tuple[fabric.FabricRestClient, ScriptedOpener]], status: int,
) -> None:
    client, opener = client_factory([FakeResponse(status, b" \n")])
    assert client.request("POST", "/connections") == {}
    assert len(opener.calls) == 1


def test_json_request_uses_callback_timeout_and_utf8(
    client_factory: Callable[..., tuple[fabric.FabricRestClient, ScriptedOpener]],
) -> None:
    callback = Mock(return_value=BEARER)
    client, opener = client_factory([FakeResponse(body={"ok": True})], token_provider=callback, timeout=7, operation_timeout=3)
    assert client.request("post", "/connections", {"displayName": "données"}) == {"ok": True}
    request, timeout = opener.calls[0]
    assert request.full_url == f"{fabric.FABRIC_API_ROOT}/connections"
    assert json.loads(cast(bytes, request.data).decode("utf-8")) == {"displayName": "données"}
    assert request.get_header("Authorization") == f"Bearer {BEARER}"
    assert timeout == 3
    callback.assert_called_once_with()
    assert BEARER not in repr(client)


@pytest.mark.parametrize("path", [
    "http://api.fabric.microsoft.com/v1/connections",
    "https://attacker.invalid/v1/connections",
    "https://api.fabric.microsoft.com.attacker.invalid/v1/connections",
    "https://user@api.fabric.microsoft.com/v1/connections",
    "https://api.fabric.microsoft.com:443/v1/connections",
    "//attacker.invalid/v1/connections", "/connections#fragment",
    "/connections/../workspaces", "/connections/%2e%2e/workspaces",
    "/connections%2fworkspaces", "/connections\\workspaces",
    "/connections\n", "/connections//another", "https://api.fabric.microsoft.com/connections",
])
def test_unsafe_endpoints_rejected_before_token(
    client_factory: Callable[..., tuple[fabric.FabricRestClient, ScriptedOpener]], path: str,
) -> None:
    callback = Mock(return_value=BEARER)
    client, opener = client_factory([], token_provider=callback)
    with pytest.raises(fabric.FabricRestError):
        client.request("GET", path)
    callback.assert_not_called()
    assert opener.calls == []


@pytest.mark.parametrize("options", [
    {"timeout": 0}, {"timeout": True}, {"timeout": float("nan")},
    {"operation_timeout": float("inf")}, {"max_retries": -1},
    {"max_polls": 0}, {"max_pages": 0}, {"max_pages": 1.5},
])
def test_client_rejects_unbounded_invalid_configuration(
    client_factory: Callable[..., tuple[fabric.FabricRestClient, ScriptedOpener]],
    options: dict[str, object],
) -> None:
    with pytest.raises(ValueError):
        client_factory([], **options)


@pytest.mark.parametrize("token", ["", "bad\nheader", "trailing ", "é", None])
def test_invalid_bearer_never_reaches_transport(
    client_factory: Callable[..., tuple[fabric.FabricRestClient, ScriptedOpener]], token: object,
) -> None:
    client, opener = client_factory([], token_provider=Mock(return_value=token))
    with pytest.raises(fabric.FabricRestError):
        client.request("GET", "/connections")
    assert opener.calls == []


def test_callback_exception_is_redacted(
    client_factory: Callable[..., tuple[fabric.FabricRestClient, ScriptedOpener]],
) -> None:
    client, opener = client_factory([], token_provider=Mock(side_effect=RuntimeError(f"{BEARER} {BODY_SECRET}")))
    with pytest.raises(fabric.FabricRestError) as caught:
        client.request("GET", "/connections")
    trace = "".join(traceback.format_exception(caught.value))
    assert BEARER not in trace and BODY_SECRET not in trace
    assert opener.calls == []


@pytest.mark.parametrize("body", [b"{invalid", b"\xff", b"[1]", b"null", b'"secret"'])
def test_malformed_success_json_is_redacted(
    client_factory: Callable[..., tuple[fabric.FabricRestClient, ScriptedOpener]], body: bytes,
) -> None:
    client, _ = client_factory([FakeResponse(body=body)])
    with pytest.raises(fabric.FabricRestError) as caught:
        client.request("GET", "/connections")
    assert "secret" not in str(caught.value)


def test_body_json_error_does_not_acquire_token_or_expose_body(
    client_factory: Callable[..., tuple[fabric.FabricRestClient, ScriptedOpener]],
) -> None:
    callback = Mock(return_value=BEARER)
    client, opener = client_factory([], token_provider=callback)
    with pytest.raises(fabric.FabricRestError):
        client.request("POST", "/connections", {"secret": BODY_SECRET, "invalid": object()})
    callback.assert_not_called()
    assert opener.calls == []


def test_response_size_is_bounded(
    client_factory: Callable[..., tuple[fabric.FabricRestClient, ScriptedOpener]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(fabric, "_MAX_RESPONSE_BYTES", 10)
    client, _ = client_factory([FakeResponse(body=b"x" * 11)])
    with pytest.raises(fabric.FabricRestError, match="size limit"):
        client.request("GET", "/connections")


@pytest.mark.parametrize("status", [401, 403, 404, 409, 302])
def test_http_failures_are_actionable_and_redacted(
    client_factory: Callable[..., tuple[fabric.FabricRestClient, ScriptedOpener]], status: int,
) -> None:
    client, opener = client_factory([http_error(status, code="InsufficientPrivileges")])
    with pytest.raises(fabric.FabricRestError) as caught:
        client.request("POST", "/connections", {"secret": BODY_SECRET})
    error = caught.value
    assert error.status_code == status
    assert error.error_code == "InsufficientPrivileges"
    assert f"HTTP {status}" in str(error)
    trace = "".join(traceback.format_exception(error))
    assert BEARER not in trace and BODY_SECRET not in trace
    assert len(opener.calls) == 1


def test_unknown_server_error_code_cannot_echo_credentials(
    client_factory: Callable[..., tuple[fabric.FabricRestClient, ScriptedOpener]],
) -> None:
    client, _ = client_factory([http_error(400, code=BODY_SECRET)])
    with pytest.raises(fabric.FabricRestError) as caught:
        client.request("POST", "/connections")
    assert caught.value.error_code is None
    assert BODY_SECRET not in str(caught.value)


def test_redirect_handler_does_not_forward_authorization() -> None:
    handler = fabric._RejectRedirects()
    assert handler.redirect_request(
        Request(fabric.FABRIC_API_ROOT), None, 302, "", {}, "https://attacker.invalid",
    ) is None


def test_safe_get_retries_are_bounded(
    client_factory: Callable[..., tuple[fabric.FabricRestClient, ScriptedOpener]], clock: Clock,
) -> None:
    client, opener = client_factory([http_error(503) for _ in range(3)], max_retries=2)
    with pytest.raises(fabric.FabricRestError, match="HTTP 503"):
        client.request("GET", "/connections")
    assert len(opener.calls) == 3
    assert clock.sleeps == [1, 2]


def test_get_transport_failure_can_retry(
    client_factory: Callable[..., tuple[fabric.FabricRestClient, ScriptedOpener]],
) -> None:
    client, opener = client_factory([URLError(BODY_SECRET), FakeResponse(body={"value": []})])
    assert client.request("GET", "/connections") == {"value": []}
    assert len(opener.calls) == 2


@pytest.mark.parametrize("method", ["POST", "PATCH", "PUT", "DELETE"])
@pytest.mark.parametrize("failure", ["network", "timeout", "server"])
def test_ambiguous_writes_are_not_replayed(
    client_factory: Callable[..., tuple[fabric.FabricRestClient, ScriptedOpener]],
    method: str, failure: str,
) -> None:
    error = {
        "network": URLError(BODY_SECRET), "timeout": TimeoutError(BEARER),
        "server": http_error(503),
    }[failure]
    client, opener = client_factory([error, FakeResponse(body={"unexpected": True})], max_retries=3)
    with pytest.raises(fabric.FabricRestError) as caught:
        client.request(method, "/connections", {"secret": BODY_SECRET})
    assert len(opener.calls) == 1
    assert BEARER not in str(caught.value) and BODY_SECRET not in str(caught.value)


def test_explicit_429_refusal_can_retry_post_with_fresh_token(
    client_factory: Callable[..., tuple[fabric.FabricRestClient, ScriptedOpener]], clock: Clock,
) -> None:
    callback = Mock(side_effect=["first-offline-token", "second-offline-token"])
    client, opener = client_factory([
        http_error(429, headers={"Retry-After": "2"}),
        FakeResponse(201, {"id": NOTEBOOK}),
    ], token_provider=callback)
    assert client.request("POST", "/connections") == {"id": NOTEBOOK}
    assert clock.sleeps == [2]
    assert [request.get_header("Authorization") for request, _ in opener.calls] == [
        "Bearer first-offline-token", "Bearer second-offline-token",
    ]


@pytest.mark.parametrize("retry_after", ["-1", "NaN", "1.5", "tomorrow", "9" * 100])
def test_malformed_retry_after_fails_without_replay(
    client_factory: Callable[..., tuple[fabric.FabricRestClient, ScriptedOpener]], retry_after: str,
) -> None:
    client, opener = client_factory([http_error(429, headers={"Retry-After": retry_after})])
    with pytest.raises(fabric.FabricRestError, match="Retry-After"):
        client.request("POST", "/connections")
    assert len(opener.calls) == 1


def test_retry_after_cannot_exceed_time_budget(
    client_factory: Callable[..., tuple[fabric.FabricRestClient, ScriptedOpener]], clock: Clock,
) -> None:
    client, opener = client_factory([http_error(429, headers={"Retry-After": "10"})], operation_timeout=3)
    with pytest.raises(fabric.FabricRestError, match="budget"):
        client.request("GET", "/connections")
    assert len(opener.calls) == 1
    assert clock.sleeps == []


def test_core_lro_waits_for_completion_and_returns_identity(
    client_factory: Callable[..., tuple[fabric.FabricRestClient, ScriptedOpener]], clock: Clock,
) -> None:
    client, opener = client_factory([
        FakeResponse(202, headers={"X-MS-Operation-ID": OPERATION.upper(), "Retry-After": "2"}),
        FakeResponse(body={"status": "NotStarted"}, headers={"Retry-After": "1"}),
        FakeResponse(body={"status": "Running"}, headers={"Retry-After": "3"}),
        FakeResponse(
            body={"status": "Succeeded"},
            headers={"Location": f"https://api.fabric.microsoft.com/operations/{OPERATION}/result"},
        ),
        FakeResponse(body=IDENTITY),
    ])
    assert client.request("POST", f"/workspaces/{WORKSPACE}/provisionIdentity") == IDENTITY
    assert clock.sleeps == [2, 1, 3]
    assert [request.get_method() for request, _ in opener.calls] == ["POST", "GET", "GET", "GET", "GET"]
    assert opener.calls[-1][0].full_url == f"{fabric.FABRIC_API_ROOT}/operations/{OPERATION}/result"


def test_lro_can_use_location_without_operation_header(
    client_factory: Callable[..., tuple[fabric.FabricRestClient, ScriptedOpener]],
) -> None:
    client, _ = client_factory([
        FakeResponse(202, headers={"Location": f"/operations/{OPERATION}"}),
        FakeResponse(body={"status": "Succeeded"}),
    ])
    assert client.request("POST", "/workspaces", wait_for_result=False) == {}


def test_no_result_lro_never_requests_result_even_with_result_location(
    client_factory: Callable[..., tuple[fabric.FabricRestClient, ScriptedOpener]],
) -> None:
    client, opener = client_factory([
        FakeResponse(202, headers={"x-ms-operation-id": OPERATION}),
        FakeResponse(body={"status": "Succeeded"}, headers={"Location": f"/operations/{OPERATION}/result"}),
    ])
    assert client.request("POST", "/workspaces", wait_for_result=False) == {}
    assert len(opener.calls) == 2
    assert not any(request.full_url.endswith("/result") for request, _ in opener.calls)


@pytest.mark.parametrize("headers", [
    {}, {"x-ms-operation-id": "not-a-guid"},
    {"x-ms-operation-id": "00000000-0000-0000-0000-000000000000"},
    {"x-ms-operation-id": OPERATION, "Location": f"/operations/{OTHER}"},
    {"Location": f"/operations/{OPERATION}/result"},
    {"Location": f"https://attacker.invalid/v1/operations/{OPERATION}"},
    {"Location": f"/connections/{OPERATION}"},
    {"Location": f"/operations/{OPERATION}?redirect=elsewhere"},
])
def test_invalid_lro_endpoints_do_not_poll(
    client_factory: Callable[..., tuple[fabric.FabricRestClient, ScriptedOpener]],
    headers: dict[str, str],
) -> None:
    client, opener = client_factory([FakeResponse(202, headers=headers)])
    with pytest.raises((fabric.FabricRestError, fabric.FabricConnectionError)):
        client.request("POST", "/connections")
    assert len(opener.calls) == 1


@pytest.mark.parametrize("headers", [
    {"Location": f"https://attacker.invalid/v1/operations/{OPERATION}/result"},
    {"Location": f"/operations/{OTHER}/result"}, {"x-ms-operation-id": OTHER},
    {"Location": f"/workspaces/{WORKSPACE}"},
])
def test_poll_endpoint_validation_cannot_be_bypassed_on_success(
    client_factory: Callable[..., tuple[fabric.FabricRestClient, ScriptedOpener]],
    headers: dict[str, str],
) -> None:
    client, opener = client_factory([
        FakeResponse(202, headers={"x-ms-operation-id": OPERATION}),
        FakeResponse(body={"status": "Succeeded"}, headers=headers),
    ])
    with pytest.raises(fabric.FabricRestError):
        client.request("POST", "/connections")
    assert len(opener.calls) == 2


@pytest.mark.parametrize("status", ["Failed", "Cancelled", "Canceled", "unknown", None])
def test_lro_failure_and_unknown_state_are_not_success(
    client_factory: Callable[..., tuple[fabric.FabricRestClient, ScriptedOpener]], status: str | None,
) -> None:
    client, opener = client_factory([
        FakeResponse(202, headers={"x-ms-operation-id": OPERATION}),
        FakeResponse(body={"status": status, "error": {"errorCode": "InsufficientPrivileges", "message": BODY_SECRET}}),
    ])
    with pytest.raises(fabric.FabricRestError) as caught:
        client.request("POST", "/connections")
    assert BODY_SECRET not in str(caught.value)
    assert len(opener.calls) == 2


def test_pending_result_is_not_treated_as_success(
    client_factory: Callable[..., tuple[fabric.FabricRestClient, ScriptedOpener]],
) -> None:
    client, _ = client_factory([
        FakeResponse(202, headers={"x-ms-operation-id": OPERATION}),
        FakeResponse(body={"status": "Succeeded"}),
        FakeResponse(202),
    ])
    with pytest.raises(fabric.FabricRestError, match="202"):
        client.request("POST", "/connections")


def test_lro_poll_count_is_bounded_even_with_zero_delays(
    client_factory: Callable[..., tuple[fabric.FabricRestClient, ScriptedOpener]],
) -> None:
    client, opener = client_factory([
        FakeResponse(202, headers={"x-ms-operation-id": OPERATION, "Retry-After": "0"}),
        FakeResponse(body={"status": "Running"}, headers={"Retry-After": "0"}),
        FakeResponse(body={"status": "Running"}, headers={"Retry-After": "0"}),
    ], max_polls=2)
    with pytest.raises(fabric.FabricRestError, match="polling limit"):
        client.request("POST", "/connections")
    assert len(opener.calls) == 3


def test_lro_wall_clock_budget_applies_to_poll_requests(
    client_factory: Callable[..., tuple[fabric.FabricRestClient, ScriptedOpener]],
) -> None:
    client, opener = client_factory([
        FakeResponse(202, headers={"x-ms-operation-id": OPERATION, "Retry-After": "2"}),
        FakeResponse(body={"status": "Running"}, headers={"Retry-After": "1"}),
    ], timeout=10, operation_timeout=3)
    with pytest.raises(fabric.FabricRestError, match="budget"):
        client.request("POST", "/connections")
    assert [timeout for _, timeout in opener.calls] == [3, 1]


def test_pagination_keeps_discovery_query_and_encodes_token(
    client_factory: Callable[..., tuple[fabric.FabricRestClient, ScriptedOpener]],
) -> None:
    client, opener = client_factory([
        FakeResponse(body={"value": [{"type": "Notebook"}], "continuationToken": "opaque+/="}),
        FakeResponse(body={"value": [{"type": "PowerBIDatasets"}]}),
    ])
    assert client.list("/connections/supportedConnectionTypes?showAllCreationMethods=true") == [
        {"type": "Notebook"}, {"type": "PowerBIDatasets"},
    ]
    assert parse_qs(urlsplit(opener.calls[1][0].full_url).query) == {
        "showAllCreationMethods": ["true"], "continuationToken": ["opaque+/="],
    }


def test_pagination_can_use_safe_uri_token(
    client_factory: Callable[..., tuple[fabric.FabricRestClient, ScriptedOpener]],
) -> None:
    client, opener = client_factory([
        FakeResponse(body={"value": [], "continuationUri": f"{fabric.FABRIC_API_ROOT}/connections?continuationToken=next"}),
        FakeResponse(body={"value": []}),
    ])
    assert client.list("/connections") == []
    assert opener.calls[1][0].full_url.endswith("/connections?continuationToken=next")


@pytest.mark.parametrize("uri", [
    "https://attacker.invalid/v1/connections?continuationToken=next",
    "http://api.fabric.microsoft.com/v1/connections?continuationToken=next",
    f"{fabric.FABRIC_API_ROOT}/workspaces?continuationToken=next",
    f"{fabric.FABRIC_API_ROOT}/connections/../workspaces?continuationToken=next",
    f"{fabric.FABRIC_API_ROOT}/connections%2fother?continuationToken=next",
])
def test_unsafe_pagination_uri_is_rejected_even_when_token_present(
    client_factory: Callable[..., tuple[fabric.FabricRestClient, ScriptedOpener]], uri: str,
) -> None:
    client, opener = client_factory([FakeResponse(body={
        "value": [], "continuationUri": uri, "continuationToken": "next",
    })])
    with pytest.raises(fabric.FabricRestError):
        client.list("/connections")
    assert len(opener.calls) == 1


def test_pagination_cycles_and_page_limits_are_bounded(
    client_factory: Callable[..., tuple[fabric.FabricRestClient, ScriptedOpener]],
) -> None:
    client, opener = client_factory([
        FakeResponse(body={"value": [], "continuationToken": "same"}),
        FakeResponse(body={"value": [], "continuationToken": "same"}),
    ])
    with pytest.raises(fabric.FabricRestError, match="repeated"):
        client.list("/connections")
    assert len(opener.calls) == 2
    client, opener = client_factory([FakeResponse(body={"value": [], "continuationToken": "next"})], max_pages=1)
    with pytest.raises(fabric.FabricRestError, match="pagination limit"):
        client.list("/connections")
    assert len(opener.calls) == 1


@pytest.mark.parametrize("body", [
    {}, {"value": {}}, {"value": ["invalid"]},
    {"value": [], "continuationToken": 3}, {"value": [], "continuationUri": {}},
    {"value": [], "continuationUri": f"{fabric.FABRIC_API_ROOT}/connections"},
])
def test_malformed_pagination_metadata_is_rejected(
    client_factory: Callable[..., tuple[fabric.FabricRestClient, ScriptedOpener]], body: dict[str, object],
) -> None:
    client, _ = client_factory([FakeResponse(body=body)])
    with pytest.raises((fabric.FabricConnectionError, fabric.FabricRestError)):
        client.list("/connections")


def test_cold_then_repeat_ensure_is_idempotent() -> None:
    memory = MemoryFabric(cold=True)
    assert memory.ensure() == EXPECTED
    assert [method for method, _, _ in memory.writes] == ["POST"] * 4
    role_body = memory.writes[1][2]
    assert role_body == {"principal": {"id": PRINCIPAL, "type": "ServicePrincipal"}, "role": "Contributor"}
    bodies = [body for _, path, body in memory.writes if path == "/connections"]
    assert len(bodies) == 2
    for kind, body in zip(("Notebook", "PowerBIDatasets"), bodies):
        assert body is not None
        details = cast(dict[str, object], body["connectionDetails"])
        credentials = cast(dict[str, object], body["credentialDetails"])
        assert details == {"type": kind, "creationMethod": f"{kind}.Actions", "parameters": []}
        assert credentials == {"credentials": {"credentialType": "WorkspaceIdentity"}, "skipTestConnection": True}
        assert WORKSPACE in cast(str, body["displayName"])
        assert "allowUsageInUserControlledCode" not in body
    original_writes = deepcopy(memory.writes)
    assert memory.ensure() == EXPECTED
    assert memory.writes == original_writes
    assert sum(path.endswith("/provisionIdentity") for _, path, _ in memory.writes) == 1


def test_cold_ensure_integrates_real_client_identity_lro(
    client_factory: Callable[..., tuple[fabric.FabricRestClient, ScriptedOpener]],
) -> None:
    client, opener = client_factory([
        FakeResponse(body={"id": WORKSPACE}),
        FakeResponse(body={"value": capabilities()}),
        FakeResponse(body={"value": []}),
        FakeResponse(body={"value": []}),
        FakeResponse(202, headers={"x-ms-operation-id": OPERATION}),
        FakeResponse(body={"status": "Running"}),
        FakeResponse(body={"status": "Succeeded"}),
        FakeResponse(body=IDENTITY),
        FakeResponse(201, role()),
        FakeResponse(201, connection("Notebook")),
        FakeResponse(201, connection("PowerBIDatasets")),
    ])
    assert fabric.ensure_pipeline_connections(client, WORKSPACE, authentication="WorkspaceIdentity") == EXPECTED
    posts = [request for request, _ in opener.calls if request.get_method() == "POST"]
    assert len(posts) == 4
    assert json.loads(cast(bytes, posts[1].data))["principal"]["id"] == PRINCIPAL


@pytest.mark.parametrize("workspace_role", ["Contributor", "Member", "Admin"])
def test_stronger_wi_roles_are_preserved(workspace_role: str) -> None:
    memory = MemoryFabric()
    memory.roles = [role(workspace_role)]
    assert memory.ensure() == EXPECTED
    assert memory.writes == []


def test_viewer_wi_is_upgraded_by_assignment_id() -> None:
    memory = MemoryFabric()
    memory.roles = [role("Viewer")]
    assert memory.ensure() == EXPECTED
    assert memory.writes == [
        ("PATCH", f"/workspaces/{WORKSPACE}/roleAssignments/{ASSIGNMENT}", {"role": "Contributor"}),
    ]


def test_application_id_role_does_not_replace_wi_service_principal_assignment() -> None:
    memory = MemoryFabric()
    memory.roles = [role("Admin", principal_id=APPLICATION)]
    assert memory.ensure() == EXPECTED
    assert memory.writes[0][2] == {"principal": {"id": PRINCIPAL, "type": "ServicePrincipal"}, "role": "Contributor"}


def test_existing_mode_never_lists_roles_or_creates_resources() -> None:
    memory = MemoryFabric()
    memory.roles = []
    memory.failures[f"/workspaces/{WORKSPACE}/roleAssignments"] = fabric.FabricRestError("No Member permission", status_code=403)
    memory.failures["/connections/supportedConnectionTypes?showAllCreationMethods=true"] = fabric.FabricRestError("No discovery", status_code=403)
    assert memory.ensure(
        mode="existing", notebook_connection_id=NOTEBOOK, refresh_connection_id=REFRESH,
    ) == EXPECTED
    assert memory.writes == []
    assert [method for method, _, _ in memory.calls] == ["GET", "GET", "GET"]


def test_existing_mode_requires_identity_without_provisioning() -> None:
    memory = MemoryFabric()
    memory.workspace.pop("workspaceIdentity")
    with pytest.raises(fabric.FabricConnectionError, match="already provisioned"):
        memory.ensure(mode="existing", notebook_connection_id=NOTEBOOK, refresh_connection_id=REFRESH)
    assert memory.writes == []


def test_existing_missing_canonical_connection_is_never_replaced() -> None:
    memory = MemoryFabric()
    memory.connections = []
    with pytest.raises(fabric.FabricRestError) as caught:
        memory.ensure(mode="existing", notebook_connection_id=NOTEBOOK, refresh_connection_id=REFRESH)
    assert caught.value.status_code == 404
    assert memory.writes == []


def test_auto_overrides_are_validated_before_any_writes() -> None:
    memory = MemoryFabric(cold=True)
    bad = connection("Notebook")
    bad["credentialDetails"] = {"credentialType": "Basic"}
    memory.connections = [bad]
    with pytest.raises(fabric.FabricConnectionError, match="WorkspaceIdentity"):
        memory.ensure(notebook_connection_id=NOTEBOOK)
    assert memory.writes == []
    assert len(memory.calls) == 1


def test_auto_accepts_explicit_connections_with_other_names() -> None:
    memory = MemoryFabric()
    memory.connections = [connection("Notebook", name="Approved notebook"), connection("PowerBIDatasets", name="Approved refresh")]
    assert memory.ensure(notebook_connection_id=NOTEBOOK, refresh_connection_id=REFRESH) == EXPECTED
    assert memory.writes == []
    assert not any(method == "LIST" and path == "/connections" for method, path, _ in memory.calls)


def test_auto_one_override_and_one_managed_connection_are_reused() -> None:
    memory = MemoryFabric()
    memory.connections[0]["displayName"] = "Approved notebook"
    assert memory.ensure(notebook_connection_id=NOTEBOOK) == EXPECTED
    assert memory.writes == []


@pytest.mark.parametrize("field", ["id", "connectivityType", "connectionDetails", "credentialDetails", "creationMethod"])
def test_incompatible_managed_connection_fails_before_writes(field: str) -> None:
    memory = MemoryFabric()
    if field == "id":
        memory.connections[0][field] = "malformed"
    elif field == "connectivityType":
        memory.connections[0][field] = "PersonalCloud"
    elif field == "connectionDetails":
        memory.connections[0][field] = {"type": "Unrelated"}
    elif field == "credentialDetails":
        memory.connections[0][field] = {"credentialType": "ServicePrincipal"}
    else:
        memory.connections[0]["connectionDetails"] = {"type": "Notebook", "creationMethod": "Notebook.Contents"}
    with pytest.raises(fabric.FabricConnectionError):
        memory.ensure()
    assert memory.writes == []


def test_duplicate_managed_names_are_not_repaired() -> None:
    memory = MemoryFabric()
    memory.connections.append(connection("Notebook", connection_id=OTHER))
    with pytest.raises(fabric.FabricConnectionError, match="Multiple"):
        memory.ensure()
    assert memory.writes == []


def test_different_connections_cannot_return_same_id() -> None:
    memory = MemoryFabric()
    memory.connections[1]["id"] = NOTEBOOK
    with pytest.raises(fabric.FabricConnectionError, match="same ID"):
        memory.ensure()
    assert memory.writes == []


@pytest.mark.parametrize("problem", [
    "missing-type", "duplicate-type", "unsupported-credential", "malformed-credentials",
    "missing-method", "duplicate-method", "malformed-methods", "required-parameter",
    "malformed-parameter", "malformed-skip-test",
])
def test_unsupported_or_malformed_discovery_fails_before_writes(problem: str) -> None:
    memory = MemoryFabric(cold=True)
    first = memory.metadata[0]
    if problem == "missing-type":
        memory.metadata.pop(0)
    elif problem == "duplicate-type":
        memory.metadata.append(deepcopy(first))
    elif problem == "unsupported-credential":
        first["supportedCredentialTypes"] = ["ServicePrincipal"]
    elif problem == "malformed-credentials":
        first["supportedCredentialTypes"] = "WorkspaceIdentity"
    elif problem == "missing-method":
        first["creationMethods"] = [{"name": "Notebook.Unknown", "parameters": []}]
    elif problem == "duplicate-method":
        first["creationMethods"] = [
            {"name": "Notebook.Actions", "parameters": []},
            {"name": "Notebook.Actions", "parameters": []},
        ]
    elif problem == "malformed-methods":
        first["creationMethods"] = "Notebook.Actions"
    elif problem in ("required-parameter", "malformed-parameter"):
        first["creationMethods"] = [{
            "name": "Notebook.Actions", "parameters": [{
                "name": "workspace", "dataType": "Text",
                "required": True if problem == "required-parameter" else "false",
            }],
        }]
    else:
        first["supportsSkipTestConnection"] = "true"
    with pytest.raises(fabric.FabricConnectionError):
        memory.ensure()
    assert memory.writes == []


def test_optional_connector_parameters_are_omitted_not_guessed() -> None:
    memory = MemoryFabric(cold=True)
    memory.metadata[0]["creationMethods"] = [{
        "name": "Notebook.Actions", "parameters": [{"name": "optional", "dataType": "Text", "required": False}],
    }]
    memory.metadata[0]["supportsSkipTestConnection"] = False
    assert memory.ensure() == EXPECTED
    body = next(body for _, path, body in memory.writes if path == "/connections")
    assert body is not None
    assert cast(dict[str, object], body["connectionDetails"])["parameters"] == []
    assert "skipTestConnection" not in cast(dict[str, object], body["credentialDetails"])


@pytest.mark.parametrize("field", ["applicationId", "servicePrincipalId"])
def test_invalid_identity_metadata_prevents_role_and_connection_writes(field: str) -> None:
    memory = MemoryFabric(cold=True)
    memory.provision_result[field] = "invalid"
    with pytest.raises(fabric.FabricConnectionError):
        memory.ensure()
    assert len(memory.writes) == 1
    assert memory.writes[0][1].endswith("/provisionIdentity")


def test_malformed_present_identity_is_not_reprovisioned() -> None:
    memory = MemoryFabric()
    memory.workspace["workspaceIdentity"] = {}
    with pytest.raises(fabric.FabricConnectionError):
        memory.ensure()
    assert memory.writes == []


def test_workspace_mismatch_is_rejected_before_writes() -> None:
    memory = MemoryFabric(cold=True)
    memory.workspace["id"] = OTHER
    with pytest.raises(fabric.FabricConnectionError, match="different workspace"):
        memory.ensure()
    assert memory.writes == []


@pytest.mark.parametrize("problem", ["invalid-principal", "invalid-role", "duplicate-direct", "invalid-assignment"])
def test_bad_role_metadata_is_not_repaired(problem: str) -> None:
    memory = MemoryFabric()
    if problem == "invalid-principal":
        memory.roles[0]["principal"] = {"id": "invalid", "type": "ServicePrincipal"}
    elif problem == "invalid-role":
        memory.roles[0]["role"] = "Owner"
    elif problem == "duplicate-direct":
        memory.roles.append(role("Admin"))
    else:
        memory.roles[0]["id"] = "invalid"
    with pytest.raises(fabric.FabricConnectionError):
        memory.ensure()
    assert memory.writes == []


@pytest.mark.parametrize("path", [
    "/connections/supportedConnectionTypes?showAllCreationMethods=true",
    "/connections", f"/workspaces/{WORKSPACE}/roleAssignments",
])
def test_permission_denied_read_preflight_does_not_trigger_provisioning(path: str) -> None:
    memory = MemoryFabric(cold=True)
    memory.failures[path] = fabric.FabricRestError(
        "Permission denied", status_code=403, error_code="InsufficientPrivileges",
    )
    with pytest.raises(fabric.FabricRestError) as caught:
        memory.ensure()
    assert caught.value.status_code == 403
    assert memory.writes == []


def test_documented_connection_name_race_reuses_winner() -> None:
    memory = MemoryFabric()
    memory.connections = []
    memory.race = "compatible"
    assert memory.ensure() == EXPECTED
    assert sum(path == "/connections" and method == "POST" for method, path, _ in memory.calls) == 2
    assert sum(path == "/connections" and method == "LIST" for method, path, _ in memory.calls) == 2


@pytest.mark.parametrize("race", ["hidden", "incompatible", "duplicates"])
def test_connection_name_race_does_not_adopt_hidden_or_incompatible_resources(race: str) -> None:
    memory = MemoryFabric()
    memory.connections = []
    memory.race = race
    with pytest.raises(fabric.FabricConnectionError):
        memory.ensure()
    assert len(memory.writes) == 1


@pytest.mark.parametrize("code", ["InsufficientPrivileges", "UnknownError"])
def test_other_connection_errors_are_not_treated_as_name_races(code: str) -> None:
    memory = MemoryFabric()
    memory.connections = []
    memory.create_error = fabric.FabricRestError("Failure", status_code=403, error_code=code)
    with pytest.raises(fabric.FabricRestError) as caught:
        memory.ensure()
    assert caught.value.status_code == 403
    assert caught.value.error_code == code
    assert len(memory.writes) == 1
    assert sum(path == "/connections" and method == "LIST" for method, path, _ in memory.calls) == 1


def test_explicit_connection_response_id_must_match_requested_id(
    client_factory: Callable[..., tuple[fabric.FabricRestClient, ScriptedOpener]],
) -> None:
    client, opener = client_factory([FakeResponse(body=connection("Notebook", connection_id=OTHER))])
    with pytest.raises(fabric.FabricConnectionError, match="different from the requested ID"):
        fabric.ensure_pipeline_connections(
            client, WORKSPACE, notebook_connection_id=NOTEBOOK, authentication="WorkspaceIdentity",
        )
    assert len(opener.calls) == 1
    assert opener.calls[0][0].get_method() == "GET"


@pytest.mark.parametrize("principal_type", ["unknown", "User", None])
def test_invalid_wi_principal_type_is_not_repaired(principal_type: str | None) -> None:
    memory = MemoryFabric()
    memory.roles[0]["principal"] = {"id": PRINCIPAL, "type": principal_type}
    with pytest.raises(fabric.FabricConnectionError):
        memory.ensure()
    assert memory.writes == []


@pytest.mark.parametrize("options", [
    {"method": "invalid"}, {"method": "GET", "body": []},
    {"method": "GET", "wait_for_result": "yes"},
])
def test_request_preflight_rejects_invalid_contract_before_token(
    client_factory: Callable[..., tuple[fabric.FabricRestClient, ScriptedOpener]],
    options: dict[str, Any],
) -> None:
    callback = Mock(return_value=BEARER)
    client, opener = client_factory([], token_provider=callback)
    with pytest.raises(fabric.FabricRestError):
        client.request(path="/connections", **options)
    callback.assert_not_called()
    assert opener.calls == []


def test_default_sp_auto_requires_credentials_before_any_client_call() -> None:
    client = Mock(spec=fabric.FabricRestClient)
    with pytest.raises(fabric.FabricConnectionError, match="Auto ServicePrincipal"):
        fabric.ensure_pipeline_connections(client, WORKSPACE)
    assert client.mock_calls == []


@pytest.mark.parametrize("credentials", [
    {}, {"tenantId": BODY_SECRET}, {**SP_CREDENTIALS, "tenantId": "bad"},
    {**SP_CREDENTIALS, "servicePrincipalClientId": "bad"},
    {**SP_CREDENTIALS, "servicePrincipalSecret": ""},
    {**SP_CREDENTIALS, "servicePrincipalSecret": "   "},
    {**SP_CREDENTIALS, "servicePrincipalSecret": None}, "not-a-mapping",
])
def test_sp_credential_preflight_is_pure_and_redacted(credentials: Any) -> None:
    client = Mock(spec=fabric.FabricRestClient)
    with pytest.raises(fabric.FabricConnectionError) as caught:
        fabric.ensure_pipeline_connections(client, WORKSPACE, credentials=credentials)
    assert client.mock_calls == []
    assert BODY_SECRET not in str(caught.value)


@pytest.mark.parametrize("authentication", ["Unknown", "", None])
def test_unknown_authentication_is_rejected_before_network(authentication: Any) -> None:
    client = Mock(spec=fabric.FabricRestClient)
    with pytest.raises(fabric.FabricConnectionError, match="Authentication"):
        fabric.ensure_pipeline_connections(
            client, WORKSPACE, authentication=authentication, credentials=SP_CREDENTIALS,
        )
    assert client.mock_calls == []


def test_wi_does_not_accept_sp_secret_configuration() -> None:
    memory = MemoryFabric()
    with pytest.raises(fabric.FabricConnectionError, match="do not accept SP"):
        memory.ensure(authentication="WorkspaceIdentity", credentials=SP_CREDENTIALS)
    assert memory.calls == []


def test_sp_default_cold_then_repeat_ensures_no_wi_and_rotates_credentials() -> None:
    memory = MemoryFabric(cold=True, authentication="ServicePrincipal")
    memory.failures[f"/workspaces/{WORKSPACE}/roleAssignments"] = fabric.FabricRestError("No Member permission", status_code=403)
    before = deepcopy(SP_CREDENTIALS)
    assert fabric.ensure_pipeline_connections(
        cast(fabric.FabricRestClient, memory), WORKSPACE, credentials=SP_CREDENTIALS,
    ) == EXPECTED
    assert [method for method, _, _ in memory.writes] == ["POST", "POST"]
    for _, path, body in memory.writes:
        assert path == "/connections" and body is not None
        assert body["credentialDetails"] == {
            "credentials": {"credentialType": "ServicePrincipal", **SP_CREDENTIALS},
            "skipTestConnection": True,
        }
    memory.calls.clear()
    rotated = {**SP_CREDENTIALS, "servicePrincipalSecret": "offline-rotated-secret"}
    assert memory.ensure(credentials=rotated) == EXPECTED
    assert [method for method, _, _ in memory.writes] == ["PATCH", "PATCH"]
    for connection_id in (NOTEBOOK, REFRESH):
        assert memory.stored_credentials[connection_id] == {"credentialType": "ServicePrincipal", **rotated}
    assert SP_CREDENTIALS == before
    assert "workspaceIdentity" not in memory.workspace
    assert not any("/roleAssignments" in path or "/provisionIdentity" in path for _, path, _ in memory.calls)
    memory.calls.clear()
    assert memory.ensure(credentials=rotated) == EXPECTED
    assert [method for method, _, _ in memory.writes] == ["PATCH", "PATCH"]


def test_sp_ignores_unrelated_malformed_workspace_identity() -> None:
    memory = MemoryFabric(authentication="ServicePrincipal")
    memory.workspace["workspaceIdentity"] = {"irrelevant": "malformed"}
    assert memory.ensure(credentials=SP_CREDENTIALS) == EXPECTED
    assert [method for method, _, _ in memory.writes] == ["PATCH", "PATCH"]
    assert not any("/roleAssignments" in path for _, path, _ in memory.calls)


def test_sp_existing_without_credentials_is_read_only_and_needs_no_wi() -> None:
    memory = MemoryFabric(authentication="ServicePrincipal")
    memory.workspace.pop("workspaceIdentity")
    assert memory.ensure(
        mode="existing", notebook_connection_id=NOTEBOOK, refresh_connection_id=REFRESH,
    ) == EXPECTED
    assert [method for method, _, _ in memory.calls] == ["GET", "GET", "GET"]
    assert memory.writes == []


def test_sp_existing_with_credentials_reconciles_canonical_ids_without_resource_creation() -> None:
    memory = MemoryFabric(authentication="ServicePrincipal")
    memory.workspace.pop("workspaceIdentity")
    assert memory.ensure(
        mode="existing", notebook_connection_id=NOTEBOOK, refresh_connection_id=REFRESH,
        credentials=SP_CREDENTIALS,
    ) == EXPECTED
    assert [method for method, _, _ in memory.writes] == ["PATCH", "PATCH"]
    assert [path for _, path, _ in memory.writes] == [
        f"/connections/{NOTEBOOK}", f"/connections/{REFRESH}",
    ]
    assert not any(method == "LIST" for method, _, _ in memory.calls)
    for _, _, body in memory.writes:
        assert body == {
            "connectivityType": "ShareableCloud",
            "credentialDetails": {"credentials": {"credentialType": "ServicePrincipal", **SP_CREDENTIALS}},
        }


def test_sp_existing_preserves_current_skip_test_flag() -> None:
    memory = MemoryFabric(authentication="ServicePrincipal")
    for item in memory.connections:
        item["credentialDetails"] = {"credentialType": "ServicePrincipal", "skipTestConnection": True}
    assert memory.ensure(
        mode="existing", notebook_connection_id=NOTEBOOK, refresh_connection_id=REFRESH,
        credentials=SP_CREDENTIALS,
    ) == EXPECTED
    for _, _, body in memory.writes:
        assert body is not None
        assert cast(dict[str, object], body["credentialDetails"])["skipTestConnection"] is True


def test_sp_existing_validates_both_connections_before_first_secret_patch() -> None:
    memory = MemoryFabric(authentication="ServicePrincipal")
    memory.connections[1]["credentialDetails"] = {"credentialType": "ServicePrincipal", "skipTestConnection": "true"}
    with pytest.raises(fabric.FabricConnectionError, match="skip-test"):
        memory.ensure(
            mode="existing", notebook_connection_id=NOTEBOOK, refresh_connection_id=REFRESH,
            credentials=SP_CREDENTIALS,
        )
    assert memory.writes == []


@pytest.mark.parametrize("mode", ["auto", "existing"])
def test_sp_never_converts_or_replaces_working_wi_connections(mode: str) -> None:
    memory = MemoryFabric()
    options: dict[str, Any] = {
        "mode": mode, "authentication": "ServicePrincipal", "credentials": SP_CREDENTIALS,
    }
    if mode == "existing":
        options.update(notebook_connection_id=NOTEBOOK, refresh_connection_id=REFRESH)
    with pytest.raises(fabric.FabricConnectionError, match="ServicePrincipal"):
        memory.ensure(**options)
    assert memory.writes == []
    assert all(
        cast(dict[str, object], item["credentialDetails"])["credentialType"] == "WorkspaceIdentity"
        for item in memory.connections
    )


def test_sp_missing_canonical_id_is_not_recreated_or_replaced() -> None:
    memory = MemoryFabric(cold=True, authentication="ServicePrincipal")
    with pytest.raises(fabric.FabricRestError) as caught:
        memory.ensure(
            mode="existing", notebook_connection_id=NOTEBOOK, refresh_connection_id=REFRESH,
            credentials=SP_CREDENTIALS,
        )
    assert caught.value.status_code == 404
    assert memory.writes == []


def test_sp_auto_explicit_ids_are_reconciled_not_duplicated() -> None:
    memory = MemoryFabric(authentication="ServicePrincipal")
    memory.connections[0]["displayName"] = "Explicit SP notebook"
    memory.connections[1]["displayName"] = "Explicit SP refresh"
    assert memory.ensure(
        notebook_connection_id=NOTEBOOK, refresh_connection_id=REFRESH, credentials=SP_CREDENTIALS,
    ) == EXPECTED
    assert [method for method, _, _ in memory.writes] == ["PATCH", "PATCH"]
    assert not any(method == "LIST" and path == "/connections" for method, path, _ in memory.calls)


def test_sp_duplicate_name_race_reconciles_winner_before_using_it() -> None:
    memory = MemoryFabric(authentication="ServicePrincipal")
    memory.connections = []
    memory.race = "compatible"
    assert memory.ensure(credentials=SP_CREDENTIALS) == EXPECTED
    assert [method for method, _, _ in memory.writes] == ["POST", "PATCH", "POST"]
    assert memory.stored_credentials[NOTEBOOK] == {"credentialType": "ServicePrincipal", **SP_CREDENTIALS}


@pytest.mark.parametrize("kind", ["Notebook", "PowerBIDatasets"])
def test_sp_unsupported_capability_is_rejected_without_any_writes(kind: str) -> None:
    memory = MemoryFabric(cold=True, authentication="ServicePrincipal")
    next(item for item in memory.metadata if item["type"] == kind)["supportedCredentialTypes"] = ["WorkspaceIdentity"]
    with pytest.raises(fabric.FabricConnectionError, match="does not advertise ServicePrincipal"):
        memory.ensure(credentials=SP_CREDENTIALS)
    assert memory.writes == []


def test_sp_rotation_permission_failure_is_not_ignored_or_retried() -> None:
    memory = MemoryFabric(authentication="ServicePrincipal")
    memory.patch_error = fabric.FabricRestError(
        "No management permission", status_code=403, error_code="InsufficientPermissionsToManageConnection",
    )
    with pytest.raises(fabric.FabricRestError) as caught:
        memory.ensure(credentials=SP_CREDENTIALS)
    assert caught.value.error_code == "InsufficientPermissionsToManageConnection"
    assert len(memory.writes) == 1


@pytest.mark.parametrize("code", ["InsufficientPermissionsToManageConnection", "IncorrectCredentials"])
def test_sp_rotation_http_errors_are_redacted_and_actionable(
    client_factory: Callable[..., tuple[fabric.FabricRestClient, ScriptedOpener]], code: str,
) -> None:
    client, opener = client_factory([http_error(403, code=code)])
    with pytest.raises(fabric.FabricRestError) as caught:
        client.request(
            "PATCH", f"/connections/{NOTEBOOK}",
            {"connectivityType": "ShareableCloud", "credentialDetails": {"credentials": SP_CREDENTIALS}},
        )
    assert caught.value.error_code == code
    assert BODY_SECRET not in "".join(traceback.format_exception(caught.value))
    assert BEARER not in "".join(traceback.format_exception(caught.value))
    assert len(opener.calls) == 1


def test_pure_sp_preflight_accepts_documented_credential_fields_without_mutating_them() -> None:
    before = deepcopy(SP_CREDENTIALS)
    assert fabric.validate_connection_configuration(WORKSPACE, credentials=SP_CREDENTIALS) is None
    assert SP_CREDENTIALS == before
