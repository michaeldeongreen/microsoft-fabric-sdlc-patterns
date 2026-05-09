"""Deploy supported Fabric items via the Bulk Import Item Definitions API (Preview).

Alternative to deploy_fabric_cicd.py. Uses the Fabric REST API's bulk import
endpoint instead of the fabric-cicd Python library.

Invoked by .github/workflows/reusable-deploy-bulk.yml. Selected at orchestrator
level via the DEPLOY_METHOD repository variable.

Required environment variables:
    AZURE_TENANT_ID, AZURE_CLIENT_ID, AZURE_CLIENT_SECRET,
    FABRIC_WORKSPACE_ID, REPOSITORY_DIRECTORY

Known gaps vs deploy_fabric_cicd.py (intentional, documented):
- No parameter.yml find_replace / key_value_replace substitution
- No orphan cleanup (Bulk Import API only supports Create/Update, not Delete)
- No item_type_in_scope filter (deploys everything in repository_directory)

API references:
- Bulk import:     https://learn.microsoft.com/en-us/rest/api/fabric/core/items/bulk-import-item-definitions(beta)
- Long running ops: https://learn.microsoft.com/en-us/rest/api/fabric/articles/long-running-operation

TODO: When the Bulk Import API graduates from Preview, drop the ?beta=true
query parameter and re-verify the endpoint URL.
"""

from __future__ import annotations

import base64
import json
import os
import pathlib
import sys
import time
from dataclasses import dataclass, field

import requests
import yaml

# Polling configuration
POLL_FALLBACK_SECONDS = 30
POLL_FLOOR_SECONDS = 5
POLL_TIMEOUT_SECONDS = 20 * 60
TOKEN_REFRESH_EVERY_N_POLLS = 20

# Files to skip when building definitionParts[]. Two layers of exclusion:
# 1. Named files: known files that should never be sent (parameter.yml is
#    fabric-cicd config; bulk-parameter.yml is bulk's own config;
#    .gitkeep is a Git placeholder).
# 2. Structural rule: item definitions always live inside *.<Type>/ folders,
#    so any file directly under repository_directory is excluded by
#    construction (handled in build_definition_parts).
EXCLUDED_FILES = {"parameter.yml", "bulk-parameter.yml", ".gitkeep"}

# Bulk-specific config file at the root of repository_directory. Read by
# load_bulk_config() to drive substitutions and VariableLibrary value-set
# activation. See data/fabric/bulk-parameter.yml for the schema.
BULK_PARAMETER_FILENAME = "bulk-parameter.yml"


@dataclass(frozen=True)
class SubstitutionRule:
    """A single find/replace rule scoped to one or more item types.

    ``replace_with`` may contain dynamic placeholders that are resolved at
    deploy time against the target workspace ID and Phase 1 item IDs:
        $workspace.$id
        $items.<Type>.<Name>.$id
    """

    find: str
    replace_with: str
    item_types: frozenset[str]


@dataclass(frozen=True)
class BulkConfig:
    """Parsed contents of bulk-parameter.yml.

    ``variable_library_active_value_set`` is None when the config has no
    ``variable_library`` block or when its ``active_value_set`` is null. In
    that case the deploy skips the value-set activation step.
    """

    substitutions: tuple[SubstitutionRule, ...] = field(default_factory=tuple)
    variable_library_active_value_set: str | None = None


def load_bulk_config(path: pathlib.Path) -> BulkConfig:
    """Parse bulk-parameter.yml into a typed BulkConfig.

    A missing file is not an error — the bulk path remains usable for repos
    that don't need substitutions or value-set activation. In that case an
    empty BulkConfig is returned and the caller's behavior is unchanged from
    the pre-Phase-2 implementation (single POST, no post-deploy steps).

    Raises ValueError on a present-but-malformed file so that misconfigured
    repos fail loudly rather than silently skipping rules.
    """
    if not path.exists():
        return BulkConfig()

    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if raw is None:
        # Empty file is treated the same as missing.
        return BulkConfig()
    if not isinstance(raw, dict):
        raise ValueError(
            f"{path.name} must contain a YAML mapping at the top level, "
            f"got {type(raw).__name__}"
        )

    substitutions: list[SubstitutionRule] = []
    for index, entry in enumerate(raw.get("substitutions") or []):
        if not isinstance(entry, dict):
            raise ValueError(
                f"{path.name}: substitutions[{index}] must be a mapping"
            )
        try:
            find = entry["find"]
            replace_with = entry["replace_with"]
            item_types = entry["item_types"]
        except KeyError as exc:
            raise ValueError(
                f"{path.name}: substitutions[{index}] missing required key {exc.args[0]!r}"
            ) from None
        if not isinstance(item_types, list) or not all(isinstance(t, str) for t in item_types):
            raise ValueError(
                f"{path.name}: substitutions[{index}].item_types must be a list of strings"
            )
        substitutions.append(
            SubstitutionRule(
                find=str(find),
                replace_with=str(replace_with),
                item_types=frozenset(item_types),
            )
        )

    variable_library_block = raw.get("variable_library") or {}
    if not isinstance(variable_library_block, dict):
        raise ValueError(
            f"{path.name}: variable_library must be a mapping if present"
        )
    active_value_set = variable_library_block.get("active_value_set")
    if active_value_set is not None and not isinstance(active_value_set, str):
        raise ValueError(
            f"{path.name}: variable_library.active_value_set must be a string or null"
        )

    return BulkConfig(
        substitutions=tuple(substitutions),
        variable_library_active_value_set=active_value_set,
    )


def acquire_token(tenant_id: str, client_id: str, client_secret: str) -> str:
    token_url = f"https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token"
    resp = requests.post(
        token_url,
        data={
            "grant_type": "client_credentials",
            "client_id": client_id,
            "client_secret": client_secret,
            "scope": "https://api.fabric.microsoft.com/.default",
        },
        timeout=30,
    )
    if resp.status_code != 200:
        sys.exit(f"::error::Token acquisition failed: HTTP {resp.status_code} {resp.text}")
    token = resp.json()["access_token"]
    # Mask the token in workflow logs
    print(f"::add-mask::{token}")
    return token


def build_definition_parts(repo_dir: pathlib.Path) -> list[dict]:
    if not repo_dir.is_dir():
        sys.exit(f"::error::Repository directory not found: {repo_dir}")
    parts: list[dict] = []
    for f in sorted(repo_dir.rglob("*")):
        if not f.is_file():
            continue
        if f.name in EXCLUDED_FILES:
            continue
        # Item definitions live inside *.<Type>/ subfolders; anything at
        # the root of repository_directory cannot belong to an item.
        if f.parent == repo_dir:
            continue
        rel = "/" + f.relative_to(repo_dir).as_posix()
        parts.append({
            "path": rel,
            "payload": base64.b64encode(f.read_bytes()).decode("ascii"),
            "payloadType": "InlineBase64",
        })
    if not parts:
        sys.exit(f"::error::No item definition files found under {repo_dir}")
    return parts


def poll_lro(
    operation_id: str,
    headers: dict,
    initial_retry_after: int,
    tenant_id: str,
    client_id: str,
    client_secret: str,
) -> None:
    base = "https://api.fabric.microsoft.com/v1/operations"
    retry_after = max(initial_retry_after or POLL_FALLBACK_SECONDS, POLL_FLOOR_SECONDS)
    started = time.monotonic()
    poll_count = 0

    while True:
        elapsed = time.monotonic() - started
        if elapsed > POLL_TIMEOUT_SECONDS:
            sys.exit(
                f"::error::LRO polling timed out after {POLL_TIMEOUT_SECONDS}s "
                f"(operation {operation_id})"
            )

        time.sleep(retry_after)
        poll_count += 1

        # Refresh token periodically for long-running operations
        # (mirrors the pattern in run_fabric_etl.py).
        if poll_count > 0 and poll_count % TOKEN_REFRESH_EVERY_N_POLLS == 0:
            headers["Authorization"] = f"Bearer {acquire_token(tenant_id, client_id, client_secret)}"

        resp = requests.get(f"{base}/{operation_id}", headers=headers, timeout=30)
        if resp.status_code != 200:
            sys.exit(f"::error::Poll request failed: HTTP {resp.status_code} {resp.text}")

        body = resp.json()
        status = body.get("status", "Unknown")
        print(f"Poll {poll_count} (t+{int(elapsed)}s): status={status}")

        if status == "Succeeded":
            return
        if status in ("Failed", "Undefined"):
            print(json.dumps(body, indent=2))
            sys.exit(f"::error::LRO ended with status: {status}")

        # NotStarted or Running — keep polling. Honor Retry-After if present.
        retry_after = max(
            int(resp.headers.get("Retry-After", POLL_FALLBACK_SECONDS)),
            POLL_FLOOR_SECONDS,
        )


def check_per_item_status(result: dict) -> None:
    details = result.get("importItemDefinitionsDetails", [])
    print(json.dumps(result, indent=2))
    if not details:
        sys.exit("::error::Result body has no importItemDefinitionsDetails")

    failures = [
        d for d in details
        if d.get("operationStatus") in ("Failed", "SucceededDespiteFailures")
    ]
    if failures:
        summary = "\n".join(
            f"  - {d.get('itemDisplayName')} ({d.get('itemType')}): "
            f"{d.get('operationStatus')}"
            for d in failures
        )
        sys.exit(f"::error::{len(failures)} item(s) failed:\n{summary}")

    print(f"All {len(details)} items deployed successfully.")


def interpret_post_response(
    status_code: int,
    body: dict,
    headers: dict,
) -> tuple[str, ...]:
    """Pure decision function for a bulk-import POST response.

    Returns a tuple whose first element is the action to take. Callers branch
    on the action and use the rest of the tuple for action-specific data.

    Returned actions:

    - ``("sync", body)`` — 200 OK, the result body contains
      ``importItemDefinitionsDetails`` directly
    - ``("async", operation_id, retry_after)`` — 202 Accepted, caller must
      poll the LRO. ``retry_after`` is from the ``Retry-After`` header
    - ``("missing_op_id",)`` — 202 Accepted but no ``x-ms-operation-id``
      header (malformed response from the service)
    - ``("error", status_code)`` — unexpected status code, caller should fail
    """
    if status_code == 200:
        return ("sync", body)
    if status_code == 202:
        operation_id = headers.get("x-ms-operation-id")
        if not operation_id:
            return ("missing_op_id",)
        retry_after = int(headers.get("Retry-After", POLL_FALLBACK_SECONDS))
        return ("async", operation_id, retry_after)
    return ("error", status_code)


def main() -> None:
    tenant_id = os.environ["AZURE_TENANT_ID"]
    client_id = os.environ["AZURE_CLIENT_ID"]
    client_secret = os.environ["AZURE_CLIENT_SECRET"]
    workspace_id = os.environ["FABRIC_WORKSPACE_ID"]
    repo_dir = pathlib.Path(os.environ["REPOSITORY_DIRECTORY"]).resolve()

    token = acquire_token(tenant_id, client_id, client_secret)
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

    parts = build_definition_parts(repo_dir)
    print(f"Built request body with {len(parts)} definition parts from {repo_dir}")

    request_body = {
        "definitionParts": parts,
        "options": {"allowPairingByName": False},
    }

    # Endpoint URL per the API reference page (the tutorial's URL is wrong).
    # https://learn.microsoft.com/en-us/rest/api/fabric/core/items/bulk-import-item-definitions(beta)
    api_url = (
        f"https://api.fabric.microsoft.com/v1/workspaces/{workspace_id}"
        f"/items/bulkImportDefinitions?beta=true"
    )
    print(f"POST {api_url}")

    post_resp = requests.post(api_url, headers=headers, json=request_body, timeout=120)
    body = post_resp.json() if post_resp.status_code == 200 else {}
    action = interpret_post_response(post_resp.status_code, body, post_resp.headers)

    if action[0] == "sync":
        # Result is in the response body directly.
        check_per_item_status(action[1])
        sys.exit(0)

    if action[0] == "async":
        _, operation_id, initial_retry = action
        print(f"202 Accepted, operation_id={operation_id}, initial Retry-After={initial_retry}s")

        poll_lro(operation_id, headers, initial_retry, tenant_id, client_id, client_secret)

        result_resp = requests.get(
            f"https://api.fabric.microsoft.com/v1/operations/{operation_id}/result",
            headers=headers,
            timeout=30,
        )
        if result_resp.status_code != 200:
            sys.exit(
                f"::error::Failed to fetch operation result: "
                f"HTTP {result_resp.status_code} {result_resp.text}"
            )
        check_per_item_status(result_resp.json())
        sys.exit(0)

    if action[0] == "missing_op_id":
        sys.exit("::error::202 response missing x-ms-operation-id header")

    sys.exit(
        f"::error::Bulk import POST failed: HTTP {post_resp.status_code} {post_resp.text}"
    )


if __name__ == "__main__":
    main()
