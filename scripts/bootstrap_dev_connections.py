"""Bootstrap Dev activity connections in GitHub Actions and export only metadata.

The target comes from the Dev Environment, not reference IDs in Fabric source.
This can run before the DataPipeline is merged. It never publishes definitions,
syncs Git, runs ETL, or writes credentials to its artifact.

azure-identity is the existing runtime dependency for unattended SP authentication.
Local developers consume the artifact through prepare_fabric_workspace.py;
they do not supply the application's credentials.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from fabric_connections import (
    NOTEBOOK_CONNECTION_ENV,
    REFRESH_CONNECTION_ENV,
    FabricRestClient,
    ensure_pipeline_connections,
    validate_connection_configuration,
    validate_guid,
)
from pipeline_bindings import DevPipelineBindings

FABRIC_SCOPE = "https://api.fabric.microsoft.com/.default"
BOOTSTRAP_WORKFLOW = ".github/workflows/bootstrap-dev.yml"
BOOTSTRAP_ARTIFACT = "fabric-dev-bindings"
BOOTSTRAP_FILENAME = "dev-bindings.json"
DEFAULT_MODEL_NAME = "Patterns_Semantic_Model"
_REPOSITORY = re.compile(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+")
_COMMIT = re.compile(r"[0-9a-f]{40}")
_RUN_ID = re.compile(r"[1-9][0-9]*")


class BootstrapMetadataError(ValueError):
    """Invalid non-secret bootstrap metadata or configuration."""


@dataclass(frozen=True)
class BootstrapProvenance:
    repository: str
    run_id: str
    run_attempt: int
    head_sha: str
    ref: str
    event: str
    model_name: str

    def document(self) -> dict[str, str | int]:
        return {
            "repository": self.repository,
            "workflowPath": BOOTSTRAP_WORKFLOW,
            "runId": self.run_id,
            "runAttempt": self.run_attempt,
            "headSha": self.head_sha,
            "ref": self.ref,
            "event": self.event,
            "semanticModelName": self.model_name,
        }


@dataclass(frozen=True)
class BootstrapArtifact:
    bindings: DevPipelineBindings
    provenance: BootstrapProvenance

    def document(self) -> dict[str, object]:
        return {
            "schemaVersion": 1,
            "bindings": self.bindings.document(),
            "provenance": self.provenance.document(),
        }


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value or value.strip() != value:
        raise BootstrapMetadataError(f"{label} must be a nonempty, unpadded string.")
    return value


def _model_name(value: object) -> str:
    name = _text(value, "Semantic Model name")
    if len(name) > 200 or any(ord(char) < 32 for char in name):
        raise BootstrapMetadataError("Semantic Model name is invalid.")
    return name


def parse_provenance(provenance: object) -> BootstrapProvenance:
    expected = {
        "repository", "workflowPath", "runId", "runAttempt", "headSha",
        "ref", "event", "semanticModelName",
    }
    if not isinstance(provenance, dict) or set(provenance) != expected:
        raise BootstrapMetadataError("Bootstrap provenance has unexpected or missing fields.")
    repository = _text(provenance["repository"], "Repository")
    run_id = _text(provenance["runId"], "Run ID")
    sha = _text(provenance["headSha"], "Source commit")
    if _REPOSITORY.fullmatch(repository) is None or any(part in {".", ".."} for part in repository.split("/")):
        raise BootstrapMetadataError("Bootstrap repository must be owner/repository.")
    if _RUN_ID.fullmatch(run_id) is None or _COMMIT.fullmatch(sha) is None:
        raise BootstrapMetadataError("Bootstrap run ID or source commit is invalid.")
    attempt = provenance["runAttempt"]
    if type(attempt) is not int or attempt < 1:
        raise BootstrapMetadataError("Bootstrap run attempt must be a positive integer.")
    if provenance["workflowPath"] != BOOTSTRAP_WORKFLOW or provenance["ref"] != "refs/heads/dev":
        raise BootstrapMetadataError("Bootstrap must originate from the approved workflow on Dev.")
    event = _text(provenance["event"], "Bootstrap event")
    if event not in {"push", "workflow_dispatch"}:
        raise BootstrapMetadataError("Bootstrap must originate from a push or explicit dispatch, not a PR.")
    model_name = _model_name(provenance["semanticModelName"])
    return BootstrapProvenance(
        repository, run_id, attempt, sha, "refs/heads/dev", event, model_name,
    )


def parse_bootstrap_artifact(document: object) -> BootstrapArtifact:
    """Validate the complete, secret-free artifact shape at the import boundary."""
    if not isinstance(document, dict) or set(document) != {"schemaVersion", "bindings", "provenance"}:
        raise BootstrapMetadataError("Bootstrap artifact has unexpected or missing fields.")
    if type(document["schemaVersion"]) is not int or document["schemaVersion"] != 1:
        raise BootstrapMetadataError("Bootstrap artifact must use schemaVersion 1.")
    values = document["bindings"]
    keys = ("workspaceId", "semanticModelId", "notebookConnectionId", "semanticModelRefreshConnectionId")
    if not isinstance(values, dict) or set(values) != {"schemaVersion", *keys}:
        raise BootstrapMetadataError("Bootstrap bindings have unexpected or missing fields.")
    if type(values["schemaVersion"]) is not int or values["schemaVersion"] != 1:
        raise BootstrapMetadataError("Bootstrap bindings must use schemaVersion 1.")
    ids = {key: validate_guid(values[key], key) for key in keys}
    if len(set(ids.values())) != len(ids):
        raise BootstrapMetadataError("Bootstrap resource IDs must be distinct.")
    validate_connection_configuration(
        ids["workspaceId"], mode="existing",
        notebook_connection_id=ids["notebookConnectionId"],
        refresh_connection_id=ids["semanticModelRefreshConnectionId"],
        authentication="ServicePrincipal",
    )
    return BootstrapArtifact(
        DevPipelineBindings(
            ids["workspaceId"], ids["semanticModelId"],
            ids["notebookConnectionId"], ids["semanticModelRefreshConnectionId"],
        ),
        parse_provenance(document["provenance"]),
    )


def provenance_from_environment(
    environ: Mapping[str, str], model_name: str,
) -> BootstrapProvenance:
    repository = environ.get("GITHUB_REPOSITORY", "")
    if environ.get("GITHUB_WORKFLOW_REF") != f"{repository}/{BOOTSTRAP_WORKFLOW}@refs/heads/dev":
        raise BootstrapMetadataError("Bootstrap must execute the reviewed Dev workflow.")
    try:
        attempt = int(environ.get("GITHUB_RUN_ATTEMPT", ""))
    except ValueError as exc:
        raise BootstrapMetadataError("GITHUB_RUN_ATTEMPT must be a positive integer.") from exc
    provenance = BootstrapProvenance(
        repository, environ.get("GITHUB_RUN_ID", ""), attempt,
        environ.get("GITHUB_SHA", ""), environ.get("GITHUB_REF", ""),
        environ.get("GITHUB_EVENT_NAME", ""), _model_name(model_name),
    )
    return parse_provenance(provenance.document())


def collect_bindings(
    client: FabricRestClient, workspace_id: str, model_name: str,
    credentials: Mapping[str, str], *,
    notebook_connection_id: str | None = None,
    refresh_connection_id: str | None = None,
) -> DevPipelineBindings:
    workspace_id = validate_guid(workspace_id, "Dev workspace ID")
    model_name = _model_name(model_name)
    validate_connection_configuration(
        workspace_id, credentials=credentials,
        notebook_connection_id=notebook_connection_id,
        refresh_connection_id=refresh_connection_id,
    )
    models = client.list(f"/workspaces/{workspace_id}/items?type=SemanticModel")
    matches = [
        item for item in models
        if item.get("type") == "SemanticModel" and item.get("displayName") == model_name
    ]
    if len(matches) != 1:
        raise BootstrapMetadataError(
            f"Dev must already contain exactly one Semantic Model named {model_name!r}; "
            f"found {len(matches)}. No connections were created."
        )
    model_id = validate_guid(matches[0].get("id"), "Dev Semantic Model ID")
    if model_id == workspace_id:
        raise BootstrapMetadataError("Dev model and workspace IDs must be distinct.")
    connections = ensure_pipeline_connections(
        client, workspace_id, authentication="ServicePrincipal", credentials=credentials,
        notebook_connection_id=notebook_connection_id,
        refresh_connection_id=refresh_connection_id,
    )
    bindings = DevPipelineBindings(
        workspace_id, model_id, connections[NOTEBOOK_CONNECTION_ENV], connections[REFRESH_CONNECTION_ENV],
    )
    return bindings


def actions_client(environ: Mapping[str, str]) -> FabricRestClient:
    try:
        from azure.core.exceptions import ClientAuthenticationError
        from azure.identity import ClientSecretCredential
    except ImportError as exc:
        raise BootstrapMetadataError("Bootstrap authentication requires azure-identity>=1.15.") from exc
    credential = ClientSecretCredential(
        tenant_id=environ["AZURE_TENANT_ID"], client_id=environ["AZURE_CLIENT_ID"],
        client_secret=environ["AZURE_CLIENT_SECRET"],
    )

    def token_provider() -> str:
        try:
            return credential.get_token(FABRIC_SCOPE).token
        except ClientAuthenticationError:
            raise BootstrapMetadataError(
                "Dev SP authentication failed. Verify the Dev Environment credentials; "
                "credential and token values are suppressed."
            ) from None

    return FabricRestClient(token_provider)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--model-name", default=os.environ.get("SEMANTIC_MODEL_NAME") or DEFAULT_MODEL_NAME)
    args = parser.parse_args(argv)
    try:
        if os.environ.get("GITHUB_ACTIONS") != "true":
            raise BootstrapMetadataError(
                "Run the Dev bootstrap in GitHub Actions. Local preparation imports its metadata, "
                "not the application's credentials."
            )
        provenance = provenance_from_environment(os.environ, args.model_name)
        missing = [
            name for name in ("AZURE_TENANT_ID", "AZURE_CLIENT_ID", "AZURE_CLIENT_SECRET", "FABRIC_WORKSPACE_ID")
            if not os.environ.get(name)
        ]
        if missing:
            raise BootstrapMetadataError(f"Missing Dev Environment secrets: {', '.join(missing)}.")
        credentials = {
            "tenantId": validate_guid(os.environ["AZURE_TENANT_ID"], "AZURE_TENANT_ID"),
            "servicePrincipalClientId": validate_guid(os.environ["AZURE_CLIENT_ID"], "AZURE_CLIENT_ID"),
            "servicePrincipalSecret": os.environ["AZURE_CLIENT_SECRET"],
        }
        workspace_id = validate_guid(os.environ["FABRIC_WORKSPACE_ID"], "FABRIC_WORKSPACE_ID")
        notebook_id = os.environ.get(NOTEBOOK_CONNECTION_ENV) or None
        refresh_id = os.environ.get(REFRESH_CONNECTION_ENV) or None
        validate_connection_configuration(
            workspace_id, credentials=credentials,
            notebook_connection_id=notebook_id, refresh_connection_id=refresh_id,
        )
        bindings = collect_bindings(
            actions_client(os.environ), workspace_id, args.model_name, credentials,
            notebook_connection_id=notebook_id, refresh_connection_id=refresh_id,
        )
        artifact = BootstrapArtifact(bindings, provenance)
        parse_bootstrap_artifact(artifact.document())
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(artifact.document(), indent=2) + "\n", encoding="utf-8")
        print("Dev connections created or reused; non-secret binding metadata written for artifact upload.")
        print("No workload definitions, Git state, data, or pipeline jobs were changed.")
    except (OSError, KeyError, ValueError, RuntimeError) as exc:
        print(f"::error::{exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
