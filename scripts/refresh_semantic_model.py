"""Refresh a deployed Semantic Model after ETL and wait for completion.

For Direct Lake, refresh frames the latest Delta table versions; it does not
run ETL again. Called by reusable-fabric-etl.yml when a model name is supplied.
The standalone notebook loader is unchanged.

Required environment variables: AZURE_TENANT_ID, AZURE_CLIENT_ID,
AZURE_CLIENT_SECRET, FABRIC_WORKSPACE_ID, SEMANTIC_MODEL_NAME.

requests and azure-identity are required for HTTP and service-principal
authentication; their minimum versions are in requirements-dev.txt. The Power
BI API needs its own token, not the Fabric API token used by the notebook runner.

API references:
- https://learn.microsoft.com/en-us/rest/api/power-bi/datasets/get-datasets-in-group
- https://learn.microsoft.com/en-us/rest/api/power-bi/datasets/refresh-dataset-in-group
- https://learn.microsoft.com/en-us/rest/api/power-bi/datasets/get-refresh-execution-details-in-group
"""

from __future__ import annotations

import json
import math
import os
import sys
import time
from email.utils import parsedate_to_datetime
from typing import Literal
from urllib.parse import urlsplit
from uuid import UUID

try:
    import requests
    from azure.core.credentials import TokenCredential
    from azure.core.exceptions import ClientAuthenticationError, ServiceRequestError, ServiceResponseError
    from azure.identity import ClientSecretCredential
except ImportError:
    sys.exit("::error::Install requests>=2.31 and azure-identity>=1.15 to refresh Semantic Models.")

POWER_BI_SCOPE = "https://analysis.windows.net/powerbi/api/.default"
POWER_BI_BASE_URL = "https://api.powerbi.com/v1.0/myorg"
REQUEST_TIMEOUT_SECONDS = 30
REFRESH_TIMEOUT_SECONDS = 600
POLL_INTERVAL_SECONDS = 10
THROTTLE_INTERVAL_SECONDS = 30


class SemanticModelRefreshError(RuntimeError):
    """An invalid configuration, API response, or unsuccessful refresh."""


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value or value != value.strip() or "\n" in value or "\r" in value:
        raise SemanticModelRefreshError(f"{label} must be a nonempty string without surrounding whitespace.")
    return value


def _guid(value: object, label: str) -> str:
    text = _text(value, label)
    try:
        guid = UUID(text)
    except ValueError as exc:
        raise SemanticModelRefreshError(f"{label} must be a GUID.") from exc
    if text.lower() != str(guid) or guid.int == 0:
        raise SemanticModelRefreshError(f"{label} must be a nonzero GUID in hyphenated form.")
    return str(guid)


def _json_object(response: requests.Response, label: str) -> dict[str, object]:
    try:
        body: object = response.json()
    except ValueError as exc:
        raise SemanticModelRefreshError(f"{label} returned invalid JSON.") from exc
    if not isinstance(body, dict):
        raise SemanticModelRefreshError(f"{label} must return a JSON object.")
    return body


def find_semantic_model_id(body: dict[str, object], model_name: str) -> str:
    """Require exactly one named model; do not choose the first duplicate."""
    models = body.get("value")
    if not isinstance(models, list):
        raise SemanticModelRefreshError("List Semantic Models response must contain a value array.")
    matches: list[str] = []
    for model in models:
        if not isinstance(model, dict):
            raise SemanticModelRefreshError("List Semantic Models returned an invalid model entry.")
        name = _text(model.get("name"), "Semantic Model name")
        if name == model_name:
            matches.append(_guid(model.get("id"), "Semantic Model ID"))
    if not matches:
        raise SemanticModelRefreshError(f"Semantic Model not found: {model_name}")
    if len(matches) != 1:
        raise SemanticModelRefreshError(f"Multiple Semantic Models named {model_name}; refusing an ambiguous refresh.")
    return matches[0]


def refresh_operation_url(location: str | None, model_url: str, request_id: str | None = None) -> str:
    """Validate Location before sending a credential to the polling endpoint."""
    if not location:
        raise SemanticModelRefreshError("Refresh accepted without a Location identifying the refresh operation.")
    try:
        parts = urlsplit(location)
    except ValueError as exc:
        raise SemanticModelRefreshError("Refresh Location is not a valid URL.") from exc
    prefix = f"{urlsplit(model_url).path}/refreshes/"
    if (
        parts.scheme != "https"
        or parts.netloc.lower() != "api.powerbi.com"
        or parts.query
        or parts.fragment
        or not parts.path.startswith(prefix)
    ):
        raise SemanticModelRefreshError("Refresh Location does not match the target workspace and Semantic Model.")
    refresh_id = _guid(parts.path[len(prefix):], "Refresh request ID")
    if request_id is not None and _guid(request_id, "Refresh request ID header") != refresh_id:
        raise SemanticModelRefreshError("Refresh Location and x-ms-request-id identify different operations.")
    return f"{model_url}/refreshes/{refresh_id}"


def retry_after_seconds(raw: str | None, default: int) -> float:
    """Honor numeric and HTTP-date Retry-After values within the overall budget."""
    if raw is None:
        return default
    try:
        delay = float(int(raw))
    except (ValueError, OverflowError):
        try:
            timestamp = parsedate_to_datetime(raw)
            if timestamp.tzinfo is None:
                raise ValueError("Retry-After date must include a timezone.")
            delay = max(0.0, timestamp.timestamp() - time.time())
        except (ValueError, TypeError, OverflowError) as exc:
            raise SemanticModelRefreshError("Invalid Retry-After header.") from exc
    if delay < 0:
        raise SemanticModelRefreshError("Retry-After must not be negative.")
    return max(1.0, delay)


def refresh_semantic_model(
    credential: TokenCredential,
    workspace_id: str,
    model_name: str,
    timeout_seconds: float = REFRESH_TIMEOUT_SECONDS,
) -> None:
    """Resolve, submit, and poll one model refresh with a bounded deadline."""
    workspace_id = _guid(workspace_id, "FABRIC_WORKSPACE_ID")
    model_name = _text(model_name, "SEMANTIC_MODEL_NAME")
    if not math.isfinite(timeout_seconds) or timeout_seconds <= 0:
        raise SemanticModelRefreshError("Refresh timeout must be finite and positive.")
    deadline = time.monotonic() + timeout_seconds
    tokens: set[str] = set()

    def remaining() -> float:
        budget = deadline - time.monotonic()
        if budget <= 0:
            raise SemanticModelRefreshError(f"Semantic Model refresh timed out after {timeout_seconds:g}s.")
        return budget

    def wait(delay: float) -> None:
        time.sleep(min(delay, remaining()))
        remaining()

    def details(body: dict[str, object]) -> str:
        fields = (
            "error", "status", "extendedStatus", "objects", "messages",
            "serviceExceptionJson", "refreshAttempts",
        )
        text = json.dumps({key: body[key] for key in fields if key in body}, ensure_ascii=True)
        for token in tokens:
            text = text.replace(token, "[REDACTED]")
        return text

    def request(
        method: Literal["GET", "POST"],
        url: str,
        label: str,
        payload: dict[str, str] | None = None,
        expected_statuses: tuple[int, ...] = (200,),
    ) -> requests.Response:
        while True:
            remaining()
            token = _text(credential.get_token(POWER_BI_SCOPE).token, "Power BI access token")
            tokens.add(token)
            try:
                response = requests.request(
                    method,
                    url,
                    headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
                    json=payload,
                    timeout=min(REQUEST_TIMEOUT_SECONDS, remaining()),
                    allow_redirects=False,
                )
            except requests.RequestException as exc:
                # A POST might already be accepted; do not submit a second refresh.
                raise SemanticModelRefreshError(f"{label} request failed ({type(exc).__name__}).") from exc
            remaining()
            if response.status_code == 429 or (
                method == "GET" and response.status_code in (500, 502, 503, 504)
            ):
                print(f"{label}: HTTP {response.status_code}; retrying within the refresh deadline.")
                wait(retry_after_seconds(response.headers.get("Retry-After"), THROTTLE_INTERVAL_SECONDS))
                continue
            if response.status_code not in expected_statuses:
                try:
                    body = _json_object(response, label)
                    error = details(body)
                except SemanticModelRefreshError:
                    error = "No JSON error details returned."
                raise SemanticModelRefreshError(f"{label}: HTTP {response.status_code}. {error}")
            return response

    models_url = f"{POWER_BI_BASE_URL}/groups/{workspace_id}/datasets"
    model_response = request("GET", models_url, "List Semantic Models")
    model_id = find_semantic_model_id(_json_object(model_response, "List Semantic Models"), model_name)
    print(f"Resolved Semantic Model {model_name} -> {model_id} in workspace {workspace_id}.")
    model_url = f"{models_url}/{model_id}"
    response = request(
        "POST", f"{model_url}/refreshes", "Start Semantic Model refresh",
        {"type": "full", "commitMode": "transactional"},
        expected_statuses=(202,),
    )
    operation_url = refresh_operation_url(
        response.headers.get("Location"), model_url, response.headers.get("x-ms-request-id"),
    )
    refresh_id = operation_url.rsplit("/", 1)[1]
    print(f"Semantic Model refresh {refresh_id} accepted; waiting for completion.")
    delay = retry_after_seconds(response.headers.get("Retry-After"), POLL_INTERVAL_SECONDS)

    while True:
        wait(delay)
        response = request("GET", operation_url, "Poll Semantic Model refresh", expected_statuses=(200, 202))
        body = _json_object(response, "Poll Semantic Model refresh")
        status = _text(body.get("status"), "Refresh status")
        extended = body.get("extendedStatus", "")
        if not isinstance(extended, str):
            raise SemanticModelRefreshError("Refresh extendedStatus must be a string.")
        failures = ("Failed", "Cancelled", "TimedOut", "Disabled")
        if status in failures or extended in failures:
            raise SemanticModelRefreshError(f"Semantic Model refresh {refresh_id} failed. {details(body)}")
        if status == "Completed":
            if response.status_code != 200 or extended not in ("", "Completed"):
                raise SemanticModelRefreshError("Refresh completion response has inconsistent status.")
            print(f"Semantic Model {model_name} refreshed successfully (request {refresh_id}).")
            return
        if status not in ("Unknown", "NotStarted", "InProgress") or extended not in ("", "Unknown", "NotStarted", "InProgress"):
            raise SemanticModelRefreshError(f"Unexpected Semantic Model refresh state. {details(body)}")
        print(f"Semantic Model refresh {refresh_id}: status={status}, extendedStatus={extended or 'not supplied'}.")
        delay = retry_after_seconds(response.headers.get("Retry-After"), POLL_INTERVAL_SECONDS)


def main() -> None:
    secret = os.environ.get("AZURE_CLIENT_SECRET", "")
    try:
        tenant_id = _guid(os.environ.get("AZURE_TENANT_ID"), "AZURE_TENANT_ID")
        client_id = _guid(os.environ.get("AZURE_CLIENT_ID"), "AZURE_CLIENT_ID")
        workspace_id = _guid(os.environ.get("FABRIC_WORKSPACE_ID"), "FABRIC_WORKSPACE_ID")
        model_name = _text(os.environ.get("SEMANTIC_MODEL_NAME"), "SEMANTIC_MODEL_NAME")
        if not secret or not secret.strip():
            raise SemanticModelRefreshError("AZURE_CLIENT_SECRET must be set.")
        with ClientSecretCredential(
            tenant_id=tenant_id,
            client_id=client_id,
            client_secret=secret,
            connection_timeout=REQUEST_TIMEOUT_SECONDS,
            read_timeout=REQUEST_TIMEOUT_SECONDS,
        ) as credential:
            refresh_semantic_model(credential, workspace_id, model_name)
    except (SemanticModelRefreshError, ClientAuthenticationError, ServiceRequestError, ServiceResponseError) as exc:
        message = str(exc).replace(secret, "[REDACTED]") if secret else str(exc)
        print(f"::error::{message}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
