"""Run a Fabric Notebook or Data Pipeline via the Fabric REST API.

After items are deployed to a workspace, this script triggers an ETL job
(e.g., the Import_Patterns_Data notebook) to ingest and transform data. The
item is resolved by name at runtime via the Fabric List Items API, avoiding
the need to know item IDs ahead of time (which differ per workspace). The
Fabric Jobs API is asynchronous — this script starts the job, then polls the
specific job instance until it completes, fails, or times out. A Location
response supplies only the job ID; polling uses the canonical Fabric API host.

Invoked by .github/workflows/reusable-fabric-etl.yml.

Required environment variables:
    AZURE_TENANT_ID, AZURE_CLIENT_ID, AZURE_CLIENT_SECRET,
    FABRIC_WORKSPACE_ID, ITEM_NAME, ITEM_TYPE, JOB_TYPE
Optional:
    RUN_LABEL — forwarded to DataPipeline executionData.parameters only

API references:
- List items: https://learn.microsoft.com/en-us/rest/api/fabric/core/items/list-items
- Run job:    https://learn.microsoft.com/en-us/rest/api/fabric/core/job-scheduler/run-on-demand-item-job
"""

from __future__ import annotations

import os
import re
import sys
import time
from datetime import datetime, timezone
from typing import Literal, TypedDict
from urllib.parse import urlsplit
from uuid import UUID

import requests
from azure.identity import ClientSecretCredential
from azure.core.exceptions import ClientAuthenticationError, ServiceRequestError


# ----- TypedDicts for the Fabric Items + Jobs API surface --------------------
#
# Document the response shapes the script consumes. Not enforced at runtime
# (TypedDict is purely a type hint) but gives Pylance/mypy the information
# needed to catch field-name typos.


class FabricItem(TypedDict, total=False):
    """One element of the List Items API ``value`` array.

    Marked ``total=False`` because the API returns additional fields
    (description, workspaceId, etc.) we don't consume here.
    """

    id: str
    displayName: str
    type: str


class JobStatusBody(TypedDict, total=False):
    """Body of a Fabric Jobs API status poll response."""

    status: str
    failureReason: str | dict[str, object]
    startTimeUtc: str


REQUEST_TIMEOUT_SECONDS = 30
JOB_TIMEOUT_SECONDS = 3600
RUN_LABEL_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}")


def pipeline_job_body(item_type: str, job_type: str, run_label: str) -> dict[str, object] | None:
    """Forward per-run input using the verified DataPipeline executionData shape."""
    if item_type != "DataPipeline":
        if run_label:
            raise ValueError("RUN_LABEL is only supported for DataPipeline jobs.")
        return None
    if job_type != "Pipeline":
        raise ValueError("DataPipeline requires JOB_TYPE=Pipeline.")
    if not run_label:
        return None
    if RUN_LABEL_PATTERN.fullmatch(run_label) is None:
        raise ValueError("RUN_LABEL must be 1-64 letters, digits, periods, underscores, or hyphens.")
    return {"executionData": {"parameters": {"run_label": run_label}}}


def _guid(value: str, label: str) -> str:
    try:
        guid = UUID(value)
    except ValueError as exc:
        raise ValueError(f"{label} must be a GUID.") from exc
    if value.lower() != str(guid) or guid.int == 0:
        raise ValueError(f"{label} must be a nonzero GUID in hyphenated form.")
    return str(guid)


def _remaining(deadline: float) -> float:
    seconds = deadline - time.monotonic()
    if seconds <= 0:
        raise ValueError(f"ETL job timed out after {JOB_TIMEOUT_SECONDS}s; the remote job was not cancelled.")
    return seconds


def _request_timeout(deadline: float) -> float:
    return min(REQUEST_TIMEOUT_SECONDS, _remaining(deadline))


def _retry_after(headers: dict, default: int = 30) -> int:
    try:
        seconds = int(headers.get("Retry-After", str(default)))
    except (ValueError, TypeError) as exc:
        raise ValueError("Job response has an invalid Retry-After header.") from exc
    if seconds < 0:
        raise ValueError("Job response has a negative Retry-After header.")
    return max(1, seconds)


def find_item_id_by_name(items: list[FabricItem], item_name: str) -> str:
    """Return the ID of the item whose displayName matches item_name.

    Exits with code 1 for missing or ambiguous names, printing the available
    item names to aid debugging.
    """
    matched = [i for i in items if i["displayName"] == item_name]
    if not matched:
        print(f"Item not found: {item_name}")
        print(f"Available items: {[i['displayName'] for i in items]}")
        sys.exit(1)
    if len(matched) != 1:
        sys.exit(f"::error::Multiple items named {item_name}; refusing an ambiguous ETL invocation.")
    return matched[0]["id"]


def interpret_poll_response(
    status_code: int,
    body: JobStatusBody,
    headers: dict,
) -> (
    tuple[Literal["completed"]]
    | tuple[Literal["failed"], str, str | dict[str, object]]
    | tuple[Literal["still_running"], int]
    | tuple[Literal["unexpected"], int]
):
    """Pure decision function for a job-status poll response.

    Returns a tuple whose first element is the action to take. Callers branch
    on the action and ignore the rest of the tuple for actions that don't
    carry extra data.

    Returned actions:

    - ``("completed",)`` — job finished successfully (status_code 200, status
      "Completed")
    - ``("failed", final_status, failure_reason)`` — job ended in a terminal
      failure state (status_code 200, status in {"Failed", "Cancelled",
      "Deduped"})
    - ``("still_running", retry_after)`` — keep polling. ``retry_after`` is the
      number of seconds to wait before the next poll, taken from the
      ``Retry-After`` header when present (defaults to 30)
    - ``("unexpected", status_code)`` — unrecognized response, caller should
      fail the run
    """
    if status_code == 200:
        status = body.get("status", "Unknown")
        if status == "Completed":
            return ("completed",)
        if status in ("Failed", "Cancelled", "Deduped"):
            return ("failed", status, body.get("failureReason") or "No failure reason provided")
        if status not in ("NotStarted", "InProgress"):
            return ("unexpected", status_code)
        return ("still_running", 30)
    if status_code == 202:
        return ("still_running", _retry_after(headers))
    return ("unexpected", status_code)


def main() -> None:
    deadline = time.monotonic() + JOB_TIMEOUT_SECONDS
    workspace_id = _guid(os.environ["FABRIC_WORKSPACE_ID"], "FABRIC_WORKSPACE_ID")
    item_name = os.environ["ITEM_NAME"]
    item_type = os.environ["ITEM_TYPE"]
    job_type = os.environ["JOB_TYPE"]
    if item_type not in {"Notebook", "DataPipeline"}:
        raise ValueError("ITEM_TYPE must be Notebook or DataPipeline.")
    if item_type == "Notebook" and job_type != "RunNotebook":
        raise ValueError("Notebook requires JOB_TYPE=RunNotebook.")
    if not item_name or item_name != item_name.strip():
        raise ValueError("ITEM_NAME must be a nonempty name without surrounding whitespace.")
    job_body = pipeline_job_body(item_type, job_type, os.environ.get("RUN_LABEL", ""))
    credential = ClientSecretCredential(
        tenant_id=os.environ["AZURE_TENANT_ID"],
        client_id=os.environ["AZURE_CLIENT_ID"],
        client_secret=os.environ["AZURE_CLIENT_SECRET"],
    )

    token = credential.get_token("https://api.fabric.microsoft.com/.default").token
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

    # Resolve item ID by name using the List Items API
    list_url = f"https://api.fabric.microsoft.com/v1/workspaces/{workspace_id}/items?type={item_type}"
    list_response = requests.get(
        list_url, headers=headers, timeout=_request_timeout(deadline), allow_redirects=False,
    )
    _remaining(deadline)

    if list_response.status_code != 200:
        print(f"Failed to list items: {list_response.status_code} {list_response.text}")
        sys.exit(1)

    items: list[FabricItem] = []
    seen_tokens: set[str] = set()
    while True:
        page = list_response.json()
        if not isinstance(page, dict) or not isinstance(page.get("value"), list):
            raise ValueError("List Items response must contain a value array.")
        for item in page["value"]:
            if not isinstance(item, dict) or not isinstance(item.get("displayName"), str) or not isinstance(item.get("id"), str):
                raise ValueError("List Items response contains an invalid item.")
            items.append(item)
        continuation = page.get("continuationToken")
        if continuation is None:
            break
        if not isinstance(continuation, str) or not continuation or continuation in seen_tokens:
            raise ValueError("List Items response contains an invalid or repeated continuation token.")
        seen_tokens.add(continuation)
        list_response = requests.get(
            list_url, headers=headers, params={"continuationToken": continuation},
            timeout=_request_timeout(deadline), allow_redirects=False,
        )
        _remaining(deadline)
        if list_response.status_code != 200:
            raise ValueError(f"List Items continuation failed: HTTP {list_response.status_code}")
    item_id = find_item_id_by_name(items, item_name)
    item_id = _guid(item_id, "ETL item ID")
    print(f"Resolved {item_name} -> {item_id}")

    # Start the job — returns 202 Accepted with a Location header for polling
    jobs_url = (
        f"https://api.fabric.microsoft.com/v1/workspaces/{workspace_id}"
        f"/items/{item_id}/jobs/instances"
    )
    url = f"{jobs_url}?jobType={job_type}"
    response = requests.post(
        url, headers=headers, json=job_body,
        timeout=_request_timeout(deadline), allow_redirects=False,
    )
    _remaining(deadline)

    if response.status_code not in (200, 202):
        print(f"Failed to start job: {response.status_code} {response.text}")
        sys.exit(1)

    location = response.headers.get("Location")
    if not location:
        sys.exit("::error::Job accepted without a Location identifying the job instance.")
    instance_id = _guid(urlsplit(location).path.rstrip("/").rsplit("/", 1)[-1], "Job instance ID")
    location = f"{jobs_url}/{instance_id}"
    retry_after = _retry_after(response.headers)
    print(f"Job {instance_id} started. Polling for completion...")

    # Poll for completion — respects Retry-After header from the API.
    # The elapsed-time deadline also bounds a long Retry-After.
    i = 0
    while time.monotonic() < deadline:
        time.sleep(min(retry_after, _remaining(deadline)))
        _remaining(deadline)

        # Re-acquire token in case of long-running jobs
        if i > 0 and i % 20 == 0:
            token = credential.get_token("https://api.fabric.microsoft.com/.default").token
            headers["Authorization"] = f"Bearer {token}"

        poll_response = requests.get(
            location, headers=headers,
            timeout=_request_timeout(deadline), allow_redirects=False,
        )
        _remaining(deadline)
        body = poll_response.json() if poll_response.status_code == 200 else {}
        if not isinstance(body, dict):
            raise ValueError("Job status response must be a JSON object.")
        if poll_response.status_code == 200:
            if not isinstance(body.get("status"), str):
                raise ValueError("Job status response must contain a status string.")
            reason = body.get("failureReason")
            if reason is not None and not isinstance(reason, (str, dict)):
                raise ValueError("Job failureReason must be an object, string, or null.")
        action = interpret_poll_response(poll_response.status_code, body, poll_response.headers)

        if action[0] == "completed":
            print(f"Poll {i + 1}: status=Completed")
            print("Job completed successfully.")
            sys.exit(0)
        elif action[0] == "failed":
            _, final_status, failure_reason = action
            print(f"Poll {i + 1}: status={final_status}")
            print(f"Job ended with status: {final_status}")
            print(f"Failure reason: {failure_reason}")
            if item_type == "DataPipeline":
                details_url = (
                    f"https://api.fabric.microsoft.com/v1/workspaces/{workspace_id}"
                    f"/datapipelines/pipelineruns/{instance_id}/queryactivityruns"
                )
                details = requests.post(
                    details_url, headers=headers,
                    json={
                        "filters": [],
                        "lastUpdatedAfter": body.get("startTimeUtc", "1970-01-01T00:00:00Z"),
                        "lastUpdatedBefore": datetime.now(timezone.utc).isoformat(),
                    },
                    timeout=_request_timeout(deadline), allow_redirects=False,
                )
                if details.status_code == 200:
                    for activity in details.json()["value"]:
                        if activity.get("status") == "Failed":
                            print(f"Activity {activity.get('activityName')} failed: {activity.get('error')}")
                else:
                    print(f"Could not read failed activity details: HTTP {details.status_code}")
            sys.exit(1)
        elif action[0] == "still_running":
            retry_after = action[1]
            print(f"Poll {i + 1}: still running...")
        else:
            print(f"Unexpected poll response: {poll_response.status_code} {poll_response.text}")
            sys.exit(1)
        i += 1

    raise ValueError(f"ETL job timed out after {JOB_TIMEOUT_SECONDS}s; the remote job was not cancelled.")


if __name__ == "__main__":
    try:
        main()
    except (ValueError, KeyError, requests.RequestException, ClientAuthenticationError, ServiceRequestError) as exc:
        print(f"::error::ETL job failed: {exc}", file=sys.stderr)
        sys.exit(1)
