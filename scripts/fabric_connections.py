"""Ensure native pipeline connections using the public Fabric Core REST APIs.

Authentication is supplied by the caller; no tokens, credentials, or bindings
are written to disk. The ServicePrincipal default reuses the deployment SP's
approved identity and reconciles supplied secrets on existing connections.
WorkspaceIdentity is an explicit alternative that manages a workspace identity
and its direct Contributor assignment; tenant trust must be established separately.
Existing mode never creates resources. Without SP credentials it is read-only;
with them it explicitly updates credentials on the supplied connection IDs.

Connection Get/List responses do not normally expose their creation method.
Check it when returned, and discover the advertised method before creation.
WorkspaceIdentityCredentials has no workspaceId field; do not invent one.
"""

from __future__ import annotations

import json
import math
import re
import time
from collections.abc import Callable, Mapping
from typing import NamedTuple, cast
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

FABRIC_API_ROOT = "https://api.fabric.microsoft.com/v1"
NOTEBOOK_CONNECTION_ENV = "NOTEBOOK_CONNECTION_ID"
REFRESH_CONNECTION_ENV = "SEMANTIC_MODEL_REFRESH_CONNECTION_ID"

_GUID_PATTERN = r"[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}"
_GUID = re.compile(_GUID_PATTERN)
_OPERATION_PATH = re.compile(rf"/(?:v1/)?operations/({_GUID_PATTERN})(/result)?")
_PLACEHOLDERS = {
    "11111111-1111-4111-8111-111111111111",
    "22222222-2222-4222-8222-222222222222",
}
_MAX_RESPONSE_BYTES = 32 * 1024 * 1024
_READ_METHODS = {"GET", "HEAD"}
_RETRYABLE_READ_STATUS = {408, 429, 500, 502, 503, 504}
_ERROR_CODES = {
    "UnknownError", "BadRequest", "InvalidRequest", "InvalidParameter",
    "DuplicateConnectionName", "InvalidConnectionDetails", "InvalidCredentialDetails",
    "ConnectionNotFound", "EntityNotFound", "InsufficientPrivileges",
    "InsufficientPermissionsToManageConnection", "IncorrectCredentials",
    "PrincipalTypeNotSupported", "WorkspaceNotFound", "WorkspaceIdentityNotFound",
    "WorkspaceHasNoCapacityAssigned", "WorkspacePreviousOperationInProgress",
    "WorkspaceHeadMismatch", "WorkspaceNotConnectedToGit", "ConnectionMismatch",
    "MissingDependency", "OperationNotCompleted", "OperationNotFound",
}


class FabricConnectionError(ValueError):
    """Invalid configuration or resource metadata; no secret values are included."""


class FabricRestError(RuntimeError):
    """Redacted transport/service failure with a safe, recognized Fabric error code."""

    def __init__(
        self, message: str, *, status_code: int | None = None,
        error_code: str | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.error_code = error_code


def validate_guid(value: object, label: str = "ID") -> str:
    """Return a lowercase, nonzero, bare GUID without echoing invalid input."""
    if not isinstance(value, str) or _GUID.fullmatch(value) is None:
        raise FabricConnectionError(f"{label} must be a bare, hyphenated GUID.")
    normalized = value.lower()
    if normalized == "00000000-0000-0000-0000-000000000000":
        raise FabricConnectionError(f"{label} must not be the all-zero GUID.")
    return normalized


def _credential_values(
    authentication: str, credentials: Mapping[str, str] | None,
) -> dict[str, object] | None:
    if authentication not in ("ServicePrincipal", "WorkspaceIdentity"):
        raise FabricConnectionError("Authentication must be 'ServicePrincipal' or 'WorkspaceIdentity'.")
    if authentication == "WorkspaceIdentity":
        if credentials is not None:
            raise FabricConnectionError("WorkspaceIdentity connections do not accept SP connection credentials.")
        return {"credentialType": "WorkspaceIdentity"}
    if credentials is None:
        return None
    if not isinstance(credentials, Mapping):
        raise FabricConnectionError("ServicePrincipal credentials must be a mapping of documented REST fields.")
    tenant_id = validate_guid(credentials.get("tenantId"), "Service principal tenant ID")
    client_id = validate_guid(credentials.get("servicePrincipalClientId"), "Service principal client ID")
    secret = credentials.get("servicePrincipalSecret")
    if not isinstance(secret, str) or not secret.strip():
        raise FabricConnectionError("ServicePrincipal credentials require a nonempty servicePrincipalSecret.")
    return {
        "credentialType": "ServicePrincipal", "tenantId": tenant_id,
        "servicePrincipalClientId": client_id, "servicePrincipalSecret": secret,
    }


def validate_connection_configuration(
    workspace_id: str, *, mode: str = "auto",
    notebook_connection_id: str | None = None,
    refresh_connection_id: str | None = None,
    authentication: str = "ServicePrincipal",
    credentials: Mapping[str, str] | None = None,
) -> None:
    """Pure preflight, suitable for use before acquiring an Azure credential."""
    validate_guid(workspace_id, "Workspace ID")
    if mode not in ("auto", "existing"):
        raise FabricConnectionError("Connection mode must be 'auto' or 'existing'.")
    if mode == "existing" and (
        notebook_connection_id is None or refresh_connection_id is None
    ):
        raise FabricConnectionError("Existing mode requires both connection IDs.")
    ids = [
        validate_guid(value, label)
        for value, label in (
            (notebook_connection_id, "Notebook connection ID"),
            (refresh_connection_id, "Refresh connection ID"),
        )
        if value is not None
    ]
    if any(value in _PLACEHOLDERS for value in ids):
        raise FabricConnectionError("Connection IDs must be real resources, not source placeholders.")
    if len(ids) != len(set(ids)):
        raise FabricConnectionError("Notebook and refresh connections must have different IDs.")
    credential_values = _credential_values(authentication, credentials)
    if mode == "auto" and credential_values is None:
        raise FabricConnectionError(
            "Auto ServicePrincipal mode requires tenantId, servicePrincipalClientId, and servicePrincipalSecret."
        )


class _RejectRedirects(HTTPRedirectHandler):
    def redirect_request(
        self, req: Request, fp: object, code: int, msg: str,
        headers: Mapping[str, str], newurl: str,
    ) -> None:
        return None


class _Response(NamedTuple):
    status: int
    headers: dict[str, str]
    body: dict[str, object]


def _object(value: object, label: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise FabricConnectionError(f"Fabric returned malformed {label}; expected an object.")
    return cast(dict[str, object], value)


def _objects(value: object, label: str) -> list[dict[str, object]]:
    if not isinstance(value, list) or any(not isinstance(item, dict) for item in value):
        raise FabricConnectionError(f"Fabric returned malformed {label}; expected a list of objects.")
    return cast(list[dict[str, object]], value)


def _decode_body(raw: bytes, *, strict: bool = True) -> dict[str, object]:
    if not raw.strip():
        return {}
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeError, ValueError, RecursionError):
        if not strict:
            return {}
        raise FabricRestError("Fabric returned invalid UTF-8 JSON; response content is suppressed.") from None
    if not isinstance(value, dict):
        if not strict:
            return {}
        raise FabricRestError("Fabric returned a non-object JSON response; content is suppressed.")
    return cast(dict[str, object], value)


def _error_code(body: dict[str, object]) -> str | None:
    details = body.get("error")
    source = details if isinstance(details, dict) else body
    value = source.get("errorCode")
    return value if isinstance(value, str) and value in _ERROR_CODES else None


class FabricRestClient:
    """Bounded, non-redirecting Core API client using a fresh callback token per attempt.

    Only reads and explicit HTTP 429 refusals are retried. Ambiguous write
    failures are never replayed. Timeouts bound socket waits and operation
    polling; max_pages/max_polls also bound zero-delay or cyclic responses.
    """

    def __init__(
        self, token_provider: Callable[[], str], *, timeout: float = 30,
        operation_timeout: float = 600, max_retries: int = 3,
        max_polls: int = 120, max_pages: int = 100,
    ) -> None:
        if not callable(token_provider):
            raise ValueError("A callable Fabric token provider is required.")
        for name, value in (("timeout", timeout), ("operation_timeout", operation_timeout)):
            if (
                isinstance(value, bool) or not isinstance(value, (int, float))
                or not math.isfinite(value) or value <= 0
            ):
                raise ValueError(f"{name} must be a positive finite number.")
        for name, value, minimum in (
            ("max_retries", max_retries, 0), ("max_polls", max_polls, 1),
            ("max_pages", max_pages, 1),
        ):
            if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
                raise ValueError(f"{name} must be an integer of at least {minimum}.")
        self._token_provider = token_provider
        self._timeout = float(timeout)
        self._operation_timeout = float(operation_timeout)
        self._max_retries = max_retries
        self._max_polls = max_polls
        self._max_pages = max_pages
        self._opener = build_opener(_RejectRedirects())

    def _url(self, path: str) -> str:
        if (
            not isinstance(path, str) or not path or "\\" in path
            or any(ord(char) <= 32 or ord(char) >= 127 for char in path)
        ):
            raise FabricRestError("Fabric endpoint must be a canonical API path or URL.")
        try:
            parts = urlsplit(path)
        except ValueError:
            raise FabricRestError("Fabric endpoint is malformed.") from None
        if parts.fragment or "#" in path:
            raise FabricRestError("Fabric endpoints must not contain fragments.")
        if parts.scheme or parts.netloc:
            if parts.scheme != "https" or parts.netloc.lower() != "api.fabric.microsoft.com":
                raise FabricRestError("Fabric endpoint must use HTTPS on api.fabric.microsoft.com without credentials or a port.")
            route = parts.path
            # Core operation Location examples also use the unversioned path.
            if _OPERATION_PATH.fullmatch(route) and not route.startswith("/v1/"):
                route = f"/v1{route}"
        else:
            route = parts.path if parts.path.startswith("/v1/") else f"/v1/{parts.path.lstrip('/')}"
        segments = route.split("/")[1:]
        if (
            not route.startswith("/v1/") or any(
                not segment or segment in (".", "..")
                or re.fullmatch(r"[A-Za-z0-9._~-]+", segment) is None
                for segment in segments
            )
        ):
            raise FabricRestError("Fabric endpoint contains an unsafe or noncanonical API path.")
        return urlunsplit(("https", "api.fabric.microsoft.com", route, parts.query, ""))

    def _remaining(self, deadline: float) -> float:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise FabricRestError("Fabric request/operation exceeded its time budget; a previously accepted write may still complete.")
        return remaining

    def _pause(self, delay: float, deadline: float) -> None:
        if delay >= self._remaining(deadline):
            raise FabricRestError("Fabric Retry-After exceeds the remaining time budget; retry later without assuming a write was cancelled.")
        if delay:
            time.sleep(delay)

    @staticmethod
    def _delay(headers: Mapping[str, str], attempt: int = 0) -> float:
        value = headers.get("retry-after")
        if value is None:
            return min(2 ** attempt, 30)
        if re.fullmatch(r"[0-9]{1,10}", value.strip()) is None:
            raise FabricRestError("Fabric returned malformed Retry-After; expected nonnegative integer seconds.")
        return float(value.strip())

    @staticmethod
    def _failure(
        method: str, status: int, headers: Mapping[str, str], body: dict[str, object],
    ) -> FabricRestError:
        code = _error_code(body)
        hint = {
            401: "Check Azure credentials, tenant, and the Fabric token audience.",
            403: "Check tenant SP API/connection-creation policies, workspace roles, and connection access.",
            404: "The resource is missing or inaccessible; explicit/canonical IDs must not be silently replaced.",
            409: "Check resource-name conflicts or another operation in progress.",
            429: "Throttling retry limit reached; retry after the service's requested delay.",
        }.get(status, "Check Fabric service availability and permissions; response content is suppressed.")
        if 300 <= status < 400:
            hint = "Redirects are not followed; use the documented Fabric Core endpoint."
        if code == "InsufficientPermissionsToManageConnection":
            hint = "Credential reconciliation requires permission to manage the connection; use its owning bootstrap principal or omit credentials for read-only existing mode."
        elif code == "IncorrectCredentials":
            hint = "Check the configured SP tenant/client IDs and current Azure secret; credential values are suppressed."
        request_id = headers.get("x-ms-request-id") or body.get("requestId")
        suffix = ""
        if isinstance(request_id, str) and _GUID.fullmatch(request_id):
            suffix = f" Request ID: {request_id.lower()}."
        return FabricRestError(
            f"Fabric {method} failed (HTTP {status}{f', {code}' if code else ''}). {hint}{suffix}",
            status_code=status, error_code=code,
        )

    def _token(self) -> str:
        try:
            token = self._token_provider()
        except Exception:
            # Authentication callbacks may include credentials in exception text.
            raise FabricRestError("Fabric token acquisition failed; check the caller's Azure credential setup.") from None
        if not isinstance(token, str) or not token or any(
            ord(char) <= 32 or ord(char) >= 127 for char in token
        ):
            raise FabricRestError("Fabric token provider must return a nonempty, header-safe bearer token.")
        return token

    def _send(
        self, method: str, url: str, body: dict[str, object] | None, deadline: float,
    ) -> _Response:
        url = self._url(url)
        try:
            data = None if body is None else json.dumps(body, allow_nan=False).encode("utf-8")
        except (TypeError, ValueError, UnicodeError, RecursionError):
            raise FabricRestError("Fabric request body is not valid JSON; body content is suppressed.") from None
        for attempt in range(self._max_retries + 1):
            self._remaining(deadline)
            request = Request(
                url, data=data, method=method,
                headers={"Authorization": f"Bearer {self._token()}", "Content-Type": "application/json"},
            )
            try:
                with self._opener.open(request, timeout=min(self._timeout, self._remaining(deadline))) as response:
                    status = response.status
                    headers = {key.lower(): value for key, value in response.headers.items()}
                    raw = response.read(_MAX_RESPONSE_BYTES + 1)
                if len(raw) > _MAX_RESPONSE_BYTES:
                    raise FabricRestError("Fabric response exceeded the client size limit; content is suppressed.")
                if status not in (200, 201, 202, 204):
                    raise self._failure(method, status, headers, _decode_body(raw, strict=False))
                return _Response(status, headers, _decode_body(raw))
            except HTTPError as error:
                status = error.code
                headers = {key.lower(): value for key, value in error.headers.items()}
                try:
                    raw = error.read(_MAX_RESPONSE_BYTES + 1)
                except (OSError, URLError):
                    raw = b""
                finally:
                    error.close()
                payload = _decode_body(raw, strict=False) if len(raw) <= _MAX_RESPONSE_BYTES else {}
                retryable = status == 429 or (
                    method in _READ_METHODS and status in _RETRYABLE_READ_STATUS
                )
                if retryable and attempt < self._max_retries:
                    self._pause(self._delay(headers, attempt), deadline)
                    continue
                raise self._failure(method, status, headers, payload) from None
            except (OSError, URLError):
                if method in _READ_METHODS and attempt < self._max_retries:
                    self._pause(self._delay({}, attempt), deadline)
                    continue
                hint = (
                    "Safe read retries are exhausted; check Fabric availability and retry later."
                    if method in _READ_METHODS
                    else "Writes are not replayed after ambiguous failures; inspect resource/operation state before retrying."
                )
                raise FabricRestError(
                    f"Fabric {method} transport failed. {hint}"
                ) from None
        raise FabricRestError("Fabric request exhausted its retry limit.")

    def _operation_location(self, location: str, operation_id: str | None = None) -> tuple[str, bool]:
        url = self._url(location)
        parts = urlsplit(url)
        match = _OPERATION_PATH.fullmatch(parts.path)
        if match is None or parts.query:
            raise FabricRestError("Fabric returned an unsafe Core operation Location.")
        located_id = validate_guid(match[1], "Operation ID")
        if operation_id is not None and located_id != operation_id:
            raise FabricRestError("Fabric returned inconsistent operation IDs.")
        return located_id, match[2] is not None

    def _wait(
        self, response: _Response, deadline: float, *, wait_for_result: bool,
    ) -> dict[str, object]:
        raw_id = response.headers.get("x-ms-operation-id")
        operation_id = validate_guid(raw_id, "Operation ID") if raw_id is not None else None
        location = response.headers.get("location")
        if location is not None:
            located_id, is_result = self._operation_location(location, operation_id)
            operation_id = located_id
            if is_result:
                raise FabricRestError("Fabric accepted a write but did not provide a Core operation state endpoint.")
        if operation_id is None:
            raise FabricRestError("Fabric returned HTTP 202 without a valid Core operation ID or Location.")
        state_url = f"{FABRIC_API_ROOT}/operations/{operation_id}"
        for _ in range(self._max_polls):
            self._pause(self._delay(response.headers), deadline)
            response = self._send("GET", state_url, None, deadline)
            reported_id = response.headers.get("x-ms-operation-id")
            if reported_id is not None and validate_guid(reported_id, "Operation ID") != operation_id:
                raise FabricRestError("Fabric returned inconsistent operation IDs while polling.")
            location = response.headers.get("location")
            is_result = False
            if location is not None:
                _, is_result = self._operation_location(location, operation_id)
            status = response.body.get("status")
            if status == "Succeeded":
                if not wait_for_result:
                    return {}
                result = self._send("GET", f"{state_url}/result", None, deadline)
                if result.status == 202:
                    raise FabricRestError("Fabric operation result is still pending; HTTP 202 is not completion.")
                return result.body
            if status in ("Failed", "Cancelled", "Canceled"):
                code = _error_code(response.body)
                raise FabricRestError(
                    f"Fabric operation {operation_id} did not succeed"
                    f"{f' ({code})' if code else ''}; check Fabric operation diagnostics and permissions.",
                    error_code=code,
                )
            if status not in ("NotStarted", "Running") or is_result:
                raise FabricRestError("Fabric returned malformed or unsupported operation-state metadata.")
        raise FabricRestError(f"Fabric operation {operation_id} exceeded the polling limit; it may still be running.")

    def request(
        self, method: str, path: str, body: dict[str, object] | None = None,
        *, wait_for_result: bool = True,
    ) -> dict[str, object]:
        """Send JSON and wait for Core HTTP 202 operations, never just acceptance.

        True declares that the API documents an operation result (for example,
        provisionIdentity), fetched by validated operation ID after success.
        Pass False for no-result operations, such as Git updates: they still
        wait for success, return {}, and never request a nonexistent /result.
        """
        if not isinstance(method, str) or method.upper() not in (
            "GET", "HEAD", "POST", "PATCH", "PUT", "DELETE",
        ):
            raise FabricRestError("Fabric request method is unsupported.")
        if body is not None and not isinstance(body, dict):
            raise FabricRestError("Fabric request body must be an object or None.")
        if not isinstance(wait_for_result, bool):
            raise FabricRestError("wait_for_result must be a boolean.")
        url = self._url(path)
        deadline = time.monotonic() + self._operation_timeout
        response = self._send(method.upper(), url, body, deadline)
        return self._wait(response, deadline, wait_for_result=wait_for_result) if response.status == 202 else response.body

    def list(self, path: str) -> list[dict[str, object]]:
        """Enumerate a Core collection without following cross-host/path continuations."""
        first_url = self._url(path)
        first = urlsplit(first_url)
        query = [(key, value) for key, value in parse_qsl(first.query) if key != "continuationToken"]
        url = first_url
        seen: set[str] = set()
        items: list[dict[str, object]] = []
        for _ in range(self._max_pages):
            if url in seen:
                raise FabricRestError("Fabric collection pagination repeated a continuation.")
            seen.add(url)
            page = self.request("GET", url)
            items.extend(_objects(page.get("value"), "collection entries"))
            token, uri = page.get("continuationToken"), page.get("continuationUri")
            if token is not None and not isinstance(token, str):
                raise FabricRestError("Fabric returned malformed continuationToken metadata.")
            if uri is not None and not isinstance(uri, str):
                raise FabricRestError("Fabric returned malformed continuationUri metadata.")
            if uri:
                continued = urlsplit(self._url(uri))
                if continued.path != first.path:
                    raise FabricRestError("Fabric continuation must stay on the original collection path.")
                if not token:
                    tokens = [value for key, value in parse_qsl(continued.query) if key == "continuationToken"]
                    if len(tokens) != 1:
                        raise FabricRestError("Fabric continuation URI must contain one continuation token.")
                    token = tokens[0]
            if not token:
                if uri:
                    raise FabricRestError("Fabric continuation token must not be empty.")
                return items
            url = urlunsplit((first.scheme, first.netloc, first.path, urlencode([*query, ("continuationToken", token)]), ""))
        raise FabricRestError("Fabric collection exceeded the pagination limit.")


class _Connector(NamedTuple):
    environment_key: str
    type: str
    method: str
    suffix: str


_CONNECTORS = (
    _Connector(NOTEBOOK_CONNECTION_ENV, "Notebook", "Notebook.Actions", "Notebook"),
    _Connector(REFRESH_CONNECTION_ENV, "PowerBIDatasets", "PowerBIDatasets.Actions", "SemanticModelRefresh"),
)


def _connection_id(
    connection: dict[str, object], connector: _Connector, *, expected_id: str | None = None,
    expected_name: str | None = None,
    authentication: str,
) -> str:
    connection_id = validate_guid(connection.get("id"), "Returned connection ID")
    if connection_id in _PLACEHOLDERS:
        raise FabricConnectionError("Fabric returned a source-placeholder connection ID.")
    if expected_id is not None and connection_id != expected_id:
        raise FabricConnectionError("Fabric returned a connection different from the requested ID.")
    if expected_name is not None and connection.get("displayName") != expected_name:
        raise FabricConnectionError("Fabric returned a different managed connection name.")
    details = _object(connection.get("connectionDetails"), "connection details")
    credentials = _object(connection.get("credentialDetails"), "connection credential metadata")
    if (
        connection.get("connectivityType") != "ShareableCloud"
        or details.get("type") != connector.type
        or credentials.get("credentialType") != authentication
    ):
        raise FabricConnectionError(
            f"{connector.type} connection must be ShareableCloud with {authentication} credentials; "
            "unrelated connections are never repaired or replaced."
        )
    if "skipTestConnection" in credentials and not isinstance(credentials["skipTestConnection"], bool):
        raise FabricConnectionError("Fabric returned malformed connection skip-test metadata.")
    if "creationMethod" in details and details["creationMethod"] != connector.method:
        raise FabricConnectionError(f"{connector.type} connection has a different creation method.")
    if authentication == "WorkspaceIdentity" and connection.get("allowUsageInUserControlledCode", False) is not False:
        raise FabricConnectionError("Activity WI connections must not expose credentials to user-controlled code.")
    return connection_id


def _creation_body(
    metadata: list[dict[str, object]], connector: _Connector, name: str,
    *, authentication: str, credential_values: dict[str, object],
) -> dict[str, object]:
    matches = [item for item in metadata if item.get("type") == connector.type]
    if len(matches) != 1:
        raise FabricConnectionError(f"Expected one supported {connector.type} connector; it is missing or duplicated.")
    item = matches[0]
    credentials = item.get("supportedCredentialTypes")
    if not isinstance(credentials, list) or any(not isinstance(value, str) for value in credentials):
        raise FabricConnectionError(f"Fabric returned malformed {connector.type} credential capability metadata.")
    if authentication not in credentials:
        raise FabricConnectionError(f"{connector.type} does not advertise {authentication} credentials; use supported pre-provisioned connections.")
    methods = _objects(item.get("creationMethods"), "connector creation methods")
    matches = [method for method in methods if method.get("name") == connector.method]
    if len(matches) != 1:
        raise FabricConnectionError(f"Expected one supported {connector.method} creation method.")
    parameters = _objects(matches[0].get("parameters"), "connector creation parameters")
    names: set[str] = set()
    for parameter in parameters:
        parameter_name = parameter.get("name")
        if (
            not isinstance(parameter_name, str) or not parameter_name or parameter_name in names
            or not isinstance(parameter.get("dataType"), str)
            or not isinstance(parameter.get("required"), bool)
        ):
            raise FabricConnectionError("Fabric returned malformed connector creation parameter metadata.")
        names.add(parameter_name)
        if parameter["required"]:
            raise FabricConnectionError(
                f"{connector.method} requires unsupported creation parameters; use existing mode instead of guessing values."
            )
    skip_test = item.get("supportsSkipTestConnection", False)
    if not isinstance(skip_test, bool):
        raise FabricConnectionError("Fabric returned malformed skip-test capability metadata.")
    credential_details: dict[str, object] = {"credentials": dict(credential_values)}
    if skip_test:
        credential_details["skipTestConnection"] = True
    return {
        "displayName": name, "connectivityType": "ShareableCloud",
        "connectionDetails": {"type": connector.type, "creationMethod": connector.method, "parameters": []},
        "credentialDetails": credential_details,
    }


def _named_connection(
    connections: list[dict[str, object]], name: str, connector: _Connector,
    *, authentication: str,
) -> str | None:
    for connection in connections:
        validate_guid(connection.get("id"), "Listed connection ID")
        if not isinstance(connection.get("displayName"), str):
            raise FabricConnectionError("Fabric returned malformed connection-name metadata.")
    matches = [connection for connection in connections if connection["displayName"] == name]
    if len(matches) > 1:
        raise FabricConnectionError(f"Multiple managed {connector.type} connections have the expected name; resolve duplicates explicitly.")
    return _connection_id(
        matches[0], connector, expected_name=name, authentication=authentication,
    ) if matches else None


def _reconcile_credentials(
    client: FabricRestClient, connection_id: str, connector: _Connector,
    credential_details: dict[str, object],
) -> None:
    updated = client.request(
        "PATCH", f"/connections/{connection_id}",
        {"connectivityType": "ShareableCloud", "credentialDetails": credential_details},
    )
    if updated:
        _connection_id(
            updated, connector, expected_id=connection_id, authentication="ServicePrincipal",
        )


def _identity(value: object) -> str:
    identity = _object(value, "workspace identity")
    validate_guid(identity.get("applicationId"), "Workspace identity application ID")
    return validate_guid(identity.get("servicePrincipalId"), "Workspace identity service principal ID")


def _identity_assignment(
    assignments: list[dict[str, object]], principal_id: str | None,
) -> dict[str, object] | None:
    matches: list[dict[str, object]] = []
    for assignment in assignments:
        principal = _object(assignment.get("principal"), "workspace role principal")
        assigned_id = validate_guid(principal.get("id"), "Workspace role principal ID")
        if principal.get("type") not in (
            "User", "Group", "ServicePrincipal", "ServicePrincipalProfile", "EntireTenant",
        ) or assignment.get("role") not in (
            "Viewer", "Contributor", "Member", "Admin",
        ):
            raise FabricConnectionError("Fabric returned malformed workspace role metadata.")
        if assigned_id == principal_id and principal["type"] != "ServicePrincipal":
            raise FabricConnectionError("Fabric returned an incompatible workspace identity principal type.")
        if assigned_id == principal_id and principal["type"] == "ServicePrincipal":
            validate_guid(assignment.get("id"), "Workspace role assignment ID")
            matches.append(assignment)
    if len(matches) > 1:
        raise FabricConnectionError("Fabric returned duplicate direct workspace identity role assignments.")
    return matches[0] if matches else None


def ensure_pipeline_connections(
    client: FabricRestClient, workspace_id: str, *, mode: str = "auto",
    notebook_connection_id: str | None = None,
    refresh_connection_id: str | None = None,
    authentication: str = "ServicePrincipal",
    credentials: Mapping[str, str] | None = None,
) -> dict[str, str]:
    """Return runtime connection variables without changing source or persisting tokens.

    Supply credentials using tenantId, servicePrincipalClientId, and
    servicePrincipalSecret (mapped from the existing Azure credential triple).
    SP auto mode creates missing connections and PATCHes existing credentials on
    every ensure, without comparisons or hashes. Existing mode with credentials
    performs the same explicit reconciliation but never creates/replaces IDs.
    Existing mode without credentials remains read-only.

    Auto mode performs read preflight before any writes. An explicit WI needs
    Member+ for role inspection; provisioning or upgrading an existing Viewer
    assignment requires Admin. SP mode never provisions or inspects WI/ACLs.
    """
    validate_connection_configuration(
        workspace_id, mode=mode, notebook_connection_id=notebook_connection_id,
        refresh_connection_id=refresh_connection_id,
        authentication=authentication, credentials=credentials,
    )
    credential_values = _credential_values(authentication, credentials)
    workspace_id = validate_guid(workspace_id, "Workspace ID")
    result: dict[str, str] = {}
    explicit_connections: dict[str, dict[str, object]] = {}
    for connector, override in zip(_CONNECTORS, (notebook_connection_id, refresh_connection_id)):
        if override is not None:
            override = validate_guid(override, "Connection ID")
            connection = client.request("GET", f"/connections/{override}")
            result[connector.environment_key] = _connection_id(
                connection, connector, expected_id=override, authentication=authentication,
            )
            explicit_connections[connector.environment_key] = connection
    workspace_path = f"/workspaces/{workspace_id}"
    workspace = client.request("GET", workspace_path)
    if validate_guid(workspace.get("id"), "Returned workspace ID") != workspace_id:
        raise FabricConnectionError("Fabric returned a different workspace.")
    principal_id = None
    if authentication == "WorkspaceIdentity":
        identity = workspace.get("workspaceIdentity")
        principal_id = _identity(identity) if identity is not None else None
    if mode == "existing":
        if authentication == "WorkspaceIdentity" and principal_id is None:
            raise FabricConnectionError("Existing mode requires an already provisioned workspace identity; ask the bootstrap administrator.")
        if authentication == "ServicePrincipal" and credential_values is not None:
            for connector in _CONNECTORS:
                current = explicit_connections[connector.environment_key]
                details = _object(current["credentialDetails"], "connection credential metadata")
                credential_details: dict[str, object] = {"credentials": dict(credential_values)}
                if "skipTestConnection" in details:
                    credential_details["skipTestConnection"] = details["skipTestConnection"]
                _reconcile_credentials(
                    client, result[connector.environment_key], connector, credential_details,
                )
        return result

    assert credential_values is not None
    metadata = client.list("/connections/supportedConnectionTypes?showAllCreationMethods=true")
    names = {connector.environment_key: f"Patterns-{workspace_id}-{connector.suffix}" for connector in _CONNECTORS}
    bodies = {
        connector.environment_key: _creation_body(
            metadata, connector, names[connector.environment_key],
            authentication=authentication, credential_values=credential_values,
        )
        for connector in _CONNECTORS
    }
    connections = client.list("/connections") if len(result) < len(_CONNECTORS) else []
    for connector in _CONNECTORS:
        if connector.environment_key not in result:
            existing_id = _named_connection(connections, names[connector.environment_key], connector, authentication=authentication)
            if existing_id is not None:
                result[connector.environment_key] = existing_id
    if len(set(result.values())) != len(result):
        raise FabricConnectionError("Fabric returned the same ID for different pipeline connections.")
    if authentication == "WorkspaceIdentity":
        assignments = client.list(f"{workspace_path}/roleAssignments")
        assignment = _identity_assignment(assignments, principal_id)
        if principal_id is None:
            principal_id = _identity(client.request("POST", f"{workspace_path}/provisionIdentity"))
            assignment = _identity_assignment(assignments, principal_id)
        if assignment is None:
            client.request("POST", f"{workspace_path}/roleAssignments", {
                "principal": {"id": principal_id, "type": "ServicePrincipal"}, "role": "Contributor",
            })
        elif assignment["role"] == "Viewer":
            assignment_id = validate_guid(assignment["id"], "Workspace role assignment ID")
            client.request("PATCH", f"{workspace_path}/roleAssignments/{assignment_id}", {"role": "Contributor"})
    for connector in _CONNECTORS:
        if connector.environment_key in result:
            if authentication == "ServicePrincipal":
                _reconcile_credentials(
                    client, result[connector.environment_key], connector,
                    _object(bodies[connector.environment_key]["credentialDetails"], "connection credentials"),
                )
            continue
        try:
            created = client.request("POST", "/connections", bodies[connector.environment_key])
            connection_id = _connection_id(
                created, connector, expected_name=names[connector.environment_key], authentication=authentication,
            )
        except FabricRestError as error:
            if error.error_code != "DuplicateConnectionName":
                raise
            connection_id = _named_connection(
                client.list("/connections"), names[connector.environment_key], connector, authentication=authentication,
            )
            if connection_id is None:
                raise FabricConnectionError("The managed connection name exists but is not accessible; ask its Owner for access.") from None
            if authentication == "ServicePrincipal":
                _reconcile_credentials(
                    client, connection_id, connector,
                    _object(bodies[connector.environment_key]["credentialDetails"], "connection credentials"),
                )
        if connection_id in result.values():
            raise FabricConnectionError("Fabric returned the same ID for different pipeline connections.")
        result[connector.environment_key] = connection_id
    return result


def provision_wi_connections(
    client: FabricRestClient, workspace_id: str, environment: str, *,
    notebook_connection_id: str | None = None,
    refresh_connection_id: str | None = None,
) -> dict[str, str]:
    """Provision only connections; WI creation and workspace roles are human setup."""
    workspace_id = validate_guid(workspace_id, "Workspace ID")
    if environment not in {"Dev", "Test", "Prod", "Feature"}:
        raise FabricConnectionError("Connection environment must be Dev, Test, Prod, or Feature.")
    validate_connection_configuration(
        workspace_id, authentication="WorkspaceIdentity",
        notebook_connection_id=notebook_connection_id, refresh_connection_id=refresh_connection_id,
    )
    workspace = client.request("GET", f"/workspaces/{workspace_id}")
    if validate_guid(workspace.get("id"), "Returned workspace ID") != workspace_id:
        raise FabricConnectionError("Fabric returned a different workspace.")
    if workspace.get("workspaceIdentity") is None:
        raise FabricConnectionError("Create the target Workspace Identity and grant its access before provisioning connections.")
    _identity(workspace["workspaceIdentity"])
    result: dict[str, str] = {}
    for connector, override in zip(_CONNECTORS, (notebook_connection_id, refresh_connection_id)):
        if override:
            override = validate_guid(override, "Existing connection ID")
            result[connector.environment_key] = _connection_id(
                client.request("GET", f"/connections/{override}"), connector,
                expected_id=override, authentication="WorkspaceIdentity",
            )
    names = {connector.environment_key: f"Patterns-{environment}-{connector.suffix}-{workspace_id}" for connector in _CONNECTORS}
    listed = client.list("/connections") if len(result) != 2 else []
    for connector in _CONNECTORS:
        if connector.environment_key not in result:
            existing = _named_connection(listed, names[connector.environment_key], connector, authentication="WorkspaceIdentity")
            if existing:
                result[connector.environment_key] = existing
    if len(set(result.values())) != len(result):
        raise FabricConnectionError("Notebook and refresh connections must be distinct.")
    missing = [connector for connector in _CONNECTORS if connector.environment_key not in result]
    if missing:
        metadata = client.list("/connections/supportedConnectionTypes?showAllCreationMethods=true")
        bodies = {
            connector.environment_key: _creation_body(
                metadata, connector, names[connector.environment_key],
                authentication="WorkspaceIdentity", credential_values={"credentialType": "WorkspaceIdentity"},
            )
            for connector in missing
        }
        for connector in missing:
            body = {**bodies[connector.environment_key], "allowUsageInUserControlledCode": False}
            try:
                created = client.request("POST", "/connections", body)
                connection_id = _connection_id(
                    created, connector, expected_name=names[connector.environment_key], authentication="WorkspaceIdentity",
                )
            except FabricRestError as exc:
                if exc.error_code != "DuplicateConnectionName":
                    raise
                connection_id = _named_connection(
                    client.list("/connections"), names[connector.environment_key], connector,
                    authentication="WorkspaceIdentity",
                )
                if connection_id is None:
                    raise FabricConnectionError("Managed connection name exists but is inaccessible; ask its Owner for access.") from None
            if connection_id in result.values():
                raise FabricConnectionError("Fabric returned the same ID for different connection types.")
            result[connector.environment_key] = connection_id
    return result


def grant_connection_group_owner(client: FabricRestClient, connection_ids: list[str], group_id: str) -> None:
    """Grant an explicitly trusted group Owner, verifying every role by readback."""
    group_id = validate_guid(group_id, "FABRIC_CONNECTION_ADMINS_GROUP_ID")
    ids = [validate_guid(value, "Connection ID") for value in connection_ids]
    if len(ids) != 2 or len(set(ids)) != 2 or group_id in ids:
        raise FabricConnectionError("Group ownership requires two distinct connection IDs and a distinct group ID.")

    def assignment(connection_id: str) -> dict[str, object] | None:
        matches: list[dict[str, object]] = []
        for role in client.list(f"/connections/{connection_id}/roleAssignments"):
            principal = _object(role.get("principal"), "connection principal")
            principal_id = validate_guid(principal.get("id"), "Connection principal ID")
            if principal.get("type") not in {"User", "Group", "ServicePrincipal", "ServicePrincipalProfile", "EntireTenant"}:
                raise FabricConnectionError("Malformed connection principal type.")
            if role.get("role") not in {"User", "UserWithReshare", "Owner"}:
                raise FabricConnectionError("Malformed connection role.")
            if principal_id == group_id:
                if principal["type"] != "Group":
                    raise FabricConnectionError("Configured admin ID is not a Group in connection role metadata.")
                validate_guid(role.get("id"), "Connection role assignment ID")
                matches.append(role)
        if len(matches) > 1:
            raise FabricConnectionError("Duplicate admin-group connection roles require explicit correction.")
        return matches[0] if matches else None

    before = {connection_id: assignment(connection_id) for connection_id in ids}
    for connection_id, current in before.items():
        if current is not None and current["role"] == "Owner":
            continue
        if current is None:
            client.request("POST", f"/connections/{connection_id}/roleAssignments", {
                "principal": {"id": group_id, "type": "Group"}, "role": "Owner",
            })
        else:
            client.request("PATCH", f"/connections/{connection_id}/roleAssignments/{current['id']}", {"role": "Owner"})
        for attempt in range(3):
            confirmed = assignment(connection_id)
            if confirmed is not None and confirmed["role"] == "Owner":
                break
            if attempt < 2:
                time.sleep(1)
        else:
            raise FabricConnectionError("Admin group Owner assignment was not confirmed; do not use or publish these bindings.")
