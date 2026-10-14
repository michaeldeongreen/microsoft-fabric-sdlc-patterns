"""Ensure WI connections before release publication or explicit Dev setup.

The workflow uses the deployment SP only for Fabric management and a GitHub
PAT only for environment-variable writes. No model/pipeline prerequisite,
runtime SP secret, token export, or automatic Dev Git synchronization.
azure-identity is the existing dependency for SP API authentication.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from collections.abc import Mapping
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import HTTPRedirectHandler, Request, build_opener

from fabric_connections import (
    FabricRestClient,
    NOTEBOOK_CONNECTION_ENV, REFRESH_CONNECTION_ENV,
    ensure_pipeline_connections, grant_connection_group_owner,
    provision_wi_connections, validate_guid,
)

GROUP_ENV = "FABRIC_CONNECTION_ADMINS_GROUP_ID"
TOKEN_ENV = "GH_ENV_VARIABLES_TOKEN"
CONNECTION_KEYS = (NOTEBOOK_CONNECTION_ENV, REFRESH_CONNECTION_ENV)
ENVIRONMENTS = {"refs/heads/dev": "Dev", "refs/heads/test": "Test", "refs/heads/main": "Prod"}
FABRIC_SCOPE = "https://api.fabric.microsoft.com/.default"


class BootstrapError(ValueError):
    """An explicit setup failure; no token or credential values are included."""


class GitHubVariableError(BootstrapError):
    def __init__(self, message: str, status: int | None = None) -> None:
        super().__init__(message)
        self.status = status


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(
        self, req: Request, fp: object, code: int, msg: str,
        headers: Mapping[str, str], newurl: str,
    ) -> None:
        return None


class GitHubVariables:
    def __init__(self, repository: str, environment: str, token: str) -> None:
        if re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository) is None:
            raise BootstrapError("GITHUB_REPOSITORY must identify one owner/repository.")
        if environment not in ENVIRONMENTS.values() or re.fullmatch(r"[A-Za-z0-9_.-]{1,2048}", token) is None:
            raise BootstrapError("A supported environment and GH_ENV_VARIABLES_TOKEN are required.")
        self.base = f"https://api.github.com/repos/{repository}/environments/{quote(environment, safe='')}"
        self.environment = environment
        self.token = token
        self.opener = build_opener(_NoRedirect())

    def request(self, method: str, suffix: str = "", body: dict[str, str] | None = None) -> dict[str, object]:
        if method not in {"GET", "POST"} or (method == "POST" and (
            suffix != "/variables" or body is None or set(body) != {"name", "value"}
            or body["name"] not in CONNECTION_KEYS
        )):
            raise BootstrapError("GitHub requests are restricted to reading and creating connection-ID variables.")
        if method == "POST" and body is not None:
            validate_guid(body["value"], body["name"])
        if suffix and suffix != "/variables" and suffix not in {f"/variables/{key}" for key in CONNECTION_KEYS}:
            raise BootstrapError("GitHub persistence is restricted to the two connection variables.")
        payload = json.dumps(body).encode("utf-8") if body is not None else None
        request = Request(self.base + suffix, data=payload, method=method, headers={
            "Authorization": f"Bearer {self.token}", "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28", "Content-Type": "application/json",
            "User-Agent": "fabric-sdlc-connection-setup",
        })
        for attempt in range(3):
            try:
                with self.opener.open(request, timeout=30) as response:
                    content = response.read(256 * 1024 + 1)
                if len(content) > 256 * 1024:
                    raise BootstrapError("GitHub variable response exceeds the size limit.")
                document = json.loads(content.decode("utf-8")) if content else {}
                if not isinstance(document, dict):
                    raise BootstrapError("GitHub returned malformed variable metadata.")
                return document
            except HTTPError as exc:
                status = exc.code
                retry_after = exc.headers.get("Retry-After", "1") if exc.headers else "1"
                exc.close()
                if method == "GET" and status in {429, 500, 502, 503, 504} and attempt < 2:
                    time.sleep(min(10, int(retry_after)) if retry_after.isdecimal() else 1)
                    continue
                raise GitHubVariableError(
                    f"GitHub environment-variable request failed (HTTP {status}); verify repository scope and Environments permission.",
                    status,
                ) from None
            except URLError:
                raise GitHubVariableError("GitHub environment-variable request failed; retry setup to reconcile partial progress.") from None
            except (UnicodeError, json.JSONDecodeError):
                raise BootstrapError("GitHub returned invalid UTF-8 variable metadata.") from None
        raise BootstrapError("GitHub request exceeded its retry limit.")

    def existing(self, key: str) -> str | None:
        if key not in CONNECTION_KEYS:
            raise BootstrapError("Only connection-ID variables can be managed.")
        try:
            document = self.request("GET", f"/variables/{key}")
        except GitHubVariableError as exc:
            if exc.status == 404:
                return None
            raise
        if document.get("name") != key:
            raise BootstrapError("GitHub returned an unexpected variable name.")
        return validate_guid(document.get("value"), key)

    def preflight(self) -> dict[str, str]:
        metadata = self.request("GET")
        name = metadata.get("name")
        if not isinstance(name, str) or name.lower() != self.environment.lower():
            raise BootstrapError("GitHub returned a different or malformed Environment.")
        values = {key: value for key in CONNECTION_KEYS if (value := self.existing(key)) is not None}
        if len(set(values.values())) != len(values):
            raise BootstrapError("Notebook and refresh variable IDs must be distinct.")
        return values

    def persist(self, values: Mapping[str, str]) -> None:
        if set(values) != set(CONNECTION_KEYS):
            raise BootstrapError("Both connection-ID values are required.")
        validated = {key: validate_guid(values[key], key) for key in CONNECTION_KEYS}
        if len(set(validated.values())) != 2:
            raise BootstrapError("Notebook and refresh connections must be distinct.")
        current = self.preflight()
        for key, value in validated.items():
            if key in current and current[key] != value:
                raise BootstrapError(f"{key} already names a different connection; no value was overwritten.")
        for key, value in validated.items():
            if key not in current:
                try:
                    self.request("POST", "/variables", {"name": key, "value": value})
                except GitHubVariableError as exc:
                    if exc.status not in {409, 422}:
                        raise
            if self.existing(key) != value:
                raise BootstrapError(f"{key} persistence was not confirmed; inspect partial progress before retrying.")


def actions_client(environ: Mapping[str, str]) -> FabricRestClient:
    try:
        from azure.core.exceptions import ClientAuthenticationError
        from azure.identity import ClientSecretCredential
    except ImportError as exc:
        raise BootstrapError("Provisioning authentication requires azure-identity.") from exc
    for key in ("AZURE_TENANT_ID", "AZURE_CLIENT_ID"):
        validate_guid(environ.get(key), key)
    if not environ.get("AZURE_CLIENT_SECRET", "").strip():
        raise BootstrapError("AZURE_CLIENT_SECRET is required inside the provisioning Environment.")
    credential = ClientSecretCredential(
        tenant_id=environ["AZURE_TENANT_ID"], client_id=environ["AZURE_CLIENT_ID"],
        client_secret=environ["AZURE_CLIENT_SECRET"],
    )

    def token_provider() -> str:
        try:
            return credential.get_token(FABRIC_SCOPE).token
        except ClientAuthenticationError:
            raise BootstrapError("Fabric SP authentication failed; token/credential details are suppressed.") from None

    return FabricRestClient(token_provider)


def output_values(values: Mapping[str, str], output_file: str | None) -> None:
    if output_file:
        with Path(output_file).open("a", encoding="utf-8") as stream:
            for key, value in values.items():
                stream.write(f"{key}={validate_guid(value, key)}\n")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--operation", required=True, choices=("preflight", "provision", "persist", "share-existing"))
    args = parser.parse_args(argv)
    try:
        if os.environ.get("GITHUB_ACTIONS") != "true":
            raise BootstrapError("This trusted provisioning command runs only in GitHub Actions.")
        environment = ENVIRONMENTS.get(os.environ.get("GITHUB_REF", ""))
        if environment is None:
            raise BootstrapError("Provision only from the reviewed dev, test, or main branch.")
        if "ENVIRONMENT" in os.environ and os.environ["ENVIRONMENT"] != environment:
            raise BootstrapError("The selected Environment must match the reviewed branch's target.")
        workspace = validate_guid(os.environ.get("FABRIC_WORKSPACE_ID"), "FABRIC_WORKSPACE_ID")
        group = validate_guid(os.environ.get(GROUP_ENV), GROUP_ENV)
        if group == workspace:
            raise BootstrapError("The admin group must not be the workspace ID.")
        if args.operation in {"preflight", "persist"}:
            github = GitHubVariables(os.environ.get("GITHUB_REPOSITORY", ""), environment, os.environ.get(TOKEN_ENV, ""))
            if args.operation == "preflight":
                output_values(github.preflight(), os.environ.get("GITHUB_OUTPUT"))
                print("GitHub environment and existing ID values validated before Fabric writes.")
                return
            values = {key: os.environ.get(key, "") for key in CONNECTION_KEYS}
            github.persist(values)
            print(f"Both {environment} connection IDs saved and verified; no existing value overwritten.")
            return
        supplied = {key: os.environ.get(key) or None for key in CONNECTION_KEYS}
        if args.operation == "share-existing":
            if environment != "Dev":
                raise BootstrapError("Legacy ownership recovery is restricted to Dev.")
            supplied = {
                NOTEBOOK_CONNECTION_ENV: validate_guid(os.environ.get("LEGACY_NOTEBOOK_CONNECTION_ID"), "Legacy Notebook ID"),
                REFRESH_CONNECTION_ENV: validate_guid(os.environ.get("LEGACY_REFRESH_CONNECTION_ID"), "Legacy refresh ID"),
            }
        for key, value in supplied.items():
            if value is not None:
                validate_guid(value, key)
        ids = [value for value in supplied.values() if value is not None]
        if len(set(ids)) != len(ids) or group in ids or workspace in ids:
            raise BootstrapError("Connection, workspace, and group IDs must be distinct.")
        client = actions_client(os.environ)
        if args.operation == "share-existing":
            values = ensure_pipeline_connections(
                client, workspace, mode="existing", authentication="ServicePrincipal",
                notebook_connection_id=supplied[NOTEBOOK_CONNECTION_ENV],
                refresh_connection_id=supplied[REFRESH_CONNECTION_ENV], credentials=None,
            )
        else:
            values = provision_wi_connections(
                client, workspace, environment,
                notebook_connection_id=supplied[NOTEBOOK_CONNECTION_ENV],
                refresh_connection_id=supplied[REFRESH_CONNECTION_ENV],
            )
        grant_connection_group_owner(client, list(values.values()), group)
        if args.operation == "provision":
            output_values(values, os.environ.get("GITHUB_OUTPUT"))
        summary = f"### {environment} connections\n\nAdmin group `{group}` has verified **Owner** access on both connections.\n"
        for key, value in values.items():
            summary += f"\n- `{key}`: `{value}`"
        if args.operation == "share-existing":
            summary += "\n\nLegacy credentials and environment variables were not changed. Deletion is deferred.\n"
        if os.environ.get("GITHUB_STEP_SUMMARY"):
            with Path(os.environ["GITHUB_STEP_SUMMARY"]).open("a", encoding="utf-8") as stream:
                stream.write(summary + "\n")
        print(summary)
    except (OSError, ValueError, RuntimeError) as exc:
        print(f"::error::{exc}", file=sys.stderr)
        print("Setup failed. Existing progress may remain; retry reuses validated resources. No rollback or deletion was attempted.", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
