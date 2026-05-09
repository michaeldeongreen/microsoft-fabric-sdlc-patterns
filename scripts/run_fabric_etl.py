"""Run a Fabric Notebook or Data Pipeline via the Fabric REST API.

After items are deployed to a workspace, this script triggers an ETL job
(e.g., the Import_Patterns_Data notebook) to ingest and transform data. The
item is resolved by name at runtime via the Fabric List Items API, avoiding
the need to know item IDs ahead of time (which differ per workspace). The
Fabric Jobs API is asynchronous — this script starts the job, then polls the
Location header URL until the job completes, fails, or times out.

Invoked by .github/workflows/reusable-fabric-etl.yml.

Required environment variables:
    AZURE_TENANT_ID, AZURE_CLIENT_ID, AZURE_CLIENT_SECRET,
    FABRIC_WORKSPACE_ID, ITEM_NAME, ITEM_TYPE, JOB_TYPE

API references:
- List items: https://learn.microsoft.com/en-us/rest/api/fabric/core/items/list-items
- Run job:    https://learn.microsoft.com/en-us/rest/api/fabric/core/job-scheduler/run-on-demand-item-job
"""

from __future__ import annotations

import os
import sys
import time

import requests
from azure.identity import ClientSecretCredential


def find_item_id_by_name(items: list[dict], item_name: str) -> str:
    """Return the ID of the item whose displayName matches item_name.

    Exits with code 1 if no match is found, printing the available item names
    to aid debugging. If multiple items have the same display name, the first
    one returned by the List Items API is used (Fabric does not enforce display
    name uniqueness within a workspace).
    """
    matched = [i for i in items if i["displayName"] == item_name]
    if not matched:
        print(f"Item not found: {item_name}")
        print(f"Available items: {[i['displayName'] for i in items]}")
        sys.exit(1)
    return matched[0]["id"]


def interpret_poll_response(
    status_code: int,
    body: dict,
    headers: dict,
) -> tuple[str, ...]:
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
            return ("failed", status, body.get("failureReason", "No failure reason provided"))
        return ("still_running", 30)
    if status_code == 202:
        return ("still_running", int(headers.get("Retry-After", "30")))
    return ("unexpected", status_code)


def main() -> None:
    credential = ClientSecretCredential(
        tenant_id=os.environ["AZURE_TENANT_ID"],
        client_id=os.environ["AZURE_CLIENT_ID"],
        client_secret=os.environ["AZURE_CLIENT_SECRET"],
    )

    token = credential.get_token("https://api.fabric.microsoft.com/.default").token
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

    workspace_id = os.environ["FABRIC_WORKSPACE_ID"]
    item_name = os.environ["ITEM_NAME"]
    item_type = os.environ["ITEM_TYPE"]
    job_type = os.environ["JOB_TYPE"]

    # Resolve item ID by name using the List Items API
    list_url = f"https://api.fabric.microsoft.com/v1/workspaces/{workspace_id}/items?type={item_type}"
    list_response = requests.get(list_url, headers=headers)

    if list_response.status_code != 200:
        print(f"Failed to list items: {list_response.status_code} {list_response.text}")
        sys.exit(1)

    items = list_response.json().get("value", [])
    item_id = find_item_id_by_name(items, item_name)
    print(f"Resolved {item_name} -> {item_id}")

    # Start the job — returns 202 Accepted with a Location header for polling
    url = (
        f"https://api.fabric.microsoft.com/v1/workspaces/{workspace_id}"
        f"/items/{item_id}/jobs/instances?jobType={job_type}"
    )
    response = requests.post(url, headers=headers)

    if response.status_code not in (200, 202):
        print(f"Failed to start job: {response.status_code} {response.text}")
        sys.exit(1)

    location = response.headers.get("Location")
    retry_after = int(response.headers.get("Retry-After", "30"))
    print("Job started. Polling for completion...")

    # Poll for completion — respects Retry-After header from the API.
    # max_polls * retry_after = maximum wait time (default: 120 * 30s = 60 min)
    max_polls = 120
    for i in range(max_polls):
        time.sleep(retry_after)

        # Re-acquire token in case of long-running jobs
        if i > 0 and i % 20 == 0:
            token = credential.get_token("https://api.fabric.microsoft.com/.default").token
            headers["Authorization"] = f"Bearer {token}"

        poll_response = requests.get(location, headers=headers)
        body = poll_response.json() if poll_response.status_code == 200 else {}
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
            sys.exit(1)
        elif action[0] == "still_running":
            retry_after = action[1]
            print(f"Poll {i + 1}: still running...")
        else:
            print(f"Unexpected poll response: {poll_response.status_code} {poll_response.text}")
            sys.exit(1)

    print("Timed out waiting for job to complete.")
    sys.exit(1)


if __name__ == "__main__":
    main()
