"""Prepare native-pipeline runtime resources and source-consistent Dev bindings.

Uses the documented Fabric connection/identity APIs, not Git-synced credentials.
Live setup needs azure-identity (already in requirements-dev.txt); updating YAML
needs the existing PyYAML dependency. Normal workspace swaps remain stdlib-only.

    python scripts/prepare_fabric_workspace.py --dev --swap-to-dev
    python scripts/prepare_fabric_workspace.py --feature --use-azure-cli

Dev setup should authenticate as the same service principal used by Actions,
so it owns the created connections. By default those connections reuse the
approved SP's credentials; WI is an explicit secretless alternative with extra
bootstrap/trust requirements. --use-azure-cli is an explicit alternative for
a developer's feature workspace or an approved administrator. Sharing an
admin-created connection with another publisher remains an authorization task.
No commits, pushes, Git sync, capacity changes, or ETL jobs are performed here.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path

from fabric_connections import FabricRestClient, ensure_pipeline_connections
from pipeline_bindings import (
    BASELINE_VALUES,
    DEV_BINDINGS_FILENAME,
    NOTEBOOK_CONNECTION_ENV,
    REFRESH_CONNECTION_ENV,
    DevBindingsNotInitialized,
    DevPipelineBindings,
    PipelineBindingError,
    dev_bindings_path,
    dev_workspace_id,
    guid_problem,
    load_dev_bindings,
    locate_fields,
    locate_refresh_workspace,
    pipeline_files,
    read_binding_values,
    require_pipeline_connections,
    rewrite,
    validate_pipeline_source,
)

FABRIC_SCOPE = "https://api.fabric.microsoft.com/.default"
REPO_ROOT = Path(__file__).resolve().parents[1]
ENV_FILE = REPO_ROOT / ".env"


@dataclass(frozen=True)
class ParameterSources:
    path: Path
    text: str
    values: dict[str, str]
    model_name: str


def connection_mode(environ: Mapping[str, str] | None = None) -> str:
    source = os.environ if environ is None else environ
    mode = source.get("FABRIC_CONNECTION_MODE", "") or "auto"
    if mode not in {"auto", "existing"}:
        raise PipelineBindingError("FABRIC_CONNECTION_MODE must be auto or existing.")
    supplied = {
        name: value for name in (NOTEBOOK_CONNECTION_ENV, REFRESH_CONNECTION_ENV)
        if (value := source.get(name, ""))
    }
    values, problems = read_binding_values(supplied, "deploy_env_key", require_all=mode == "existing")
    if problems:
        raise PipelineBindingError("Pipeline connection variables are invalid:\n- " + "\n- ".join(problems))
    if mode == "existing" and len(values) != 2:
        raise PipelineBindingError("Existing connection mode requires both connection variables.")
    return mode


def runtime_authentication(environ: Mapping[str, str] | None = None) -> str:
    source = os.environ if environ is None else environ
    authentication = source.get("FABRIC_RUNTIME_AUTHENTICATION", "") or "ServicePrincipal"
    if authentication not in {"ServicePrincipal", "WorkspaceIdentity"}:
        raise PipelineBindingError(
            "FABRIC_RUNTIME_AUTHENTICATION must be ServicePrincipal or WorkspaceIdentity."
        )
    return authentication


def runtime_credentials(authentication: str, *, required: bool = True) -> dict[str, str] | None:
    if authentication == "WorkspaceIdentity" or not required:
        return None
    keys = {
        "tenantId": "AZURE_TENANT_ID",
        "servicePrincipalClientId": "AZURE_CLIENT_ID",
        "servicePrincipalSecret": "AZURE_CLIENT_SECRET",
    }
    missing = [name for name in keys.values() if not os.environ.get(name)]
    if missing:
        raise PipelineBindingError(
            f"ServicePrincipal runtime connections require {', '.join(missing)}; "
            "the sample reuses its existing deployment credentials."
        )
    for name in ("AZURE_TENANT_ID", "AZURE_CLIENT_ID"):
        problem = guid_problem(os.environ[name], name)
        if problem:
            raise PipelineBindingError(problem)
    return {key: os.environ[name] for key, name in keys.items()}


def parameter_sources(repo_dir: Path, *, bulk: bool) -> ParameterSources:
    try:
        import yaml
    except ImportError as exc:
        raise PipelineBindingError("Install requirements-dev.txt; parameter validation needs PyYAML.") from exc
    path = repo_dir / ("bulk-parameter.yml" if bulk else "parameter.yml")
    text = path.read_bytes().decode("utf-8")
    try:
        document = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise PipelineBindingError(f"{path.name}: invalid YAML.") from exc
    rules = document.get("substitutions" if bulk else "find_replace") if isinstance(document, dict) else None
    if not isinstance(rules, list):
        raise PipelineBindingError(f"{path.name}: expected pipeline substitution rules.")
    values: dict[str, str] = {}
    model_names: set[str] = set()
    for rule in rules:
        if not isinstance(rule, dict):
            raise PipelineBindingError(f"{path.name}: each replacement must be an object.")
        item_types = rule.get("item_types" if bulk else "item_type")
        if isinstance(item_types, str):
            item_types = [item_types]
        if not isinstance(item_types, list) or "DataPipeline" not in item_types:
            continue
        replacement = rule.get("replace_with" if bulk else "replace_value")
        if not bulk:
            if not isinstance(replacement, dict) or not replacement:
                raise PipelineBindingError(f"{path.name}: pipeline replace_value must be an environment map.")
            if any(not isinstance(value, str) for value in replacement.values()):
                raise PipelineBindingError(f"{path.name}: pipeline target expressions must be strings.")
            replacements = set(replacement.values())
            if len(replacements) != 1:
                raise PipelineBindingError(f"{path.name}: sample pipeline rules require one target expression.")
            replacement = next(iter(replacements))
        if not isinstance(replacement, str):
            raise PipelineBindingError(f"{path.name}: pipeline replacement must be a string.")
        model_match = re.fullmatch(r"\$items\.SemanticModel\.([^$]+?)\.\$id", replacement)
        labels = {
            f"$ENV:{NOTEBOOK_CONNECTION_ENV}": "Notebook connection",
            f"$ENV:{REFRESH_CONNECTION_ENV}": "Refresh connection",
            "$workspace.$id": "Refresh workspace",
        }
        if model_match:
            label = "Semantic model"
            model_names.add(model_match.group(1))
        else:
            label = labels.get(replacement, "")
        if not label:
            continue
        value = rule.get("find" if bulk else "find_value")
        if not isinstance(value, str):
            raise PipelineBindingError(f"{path.name}: {label} find value must be a GUID.")
        problem = guid_problem(value, f"{path.name} {label}")
        if problem:
            raise PipelineBindingError(problem)
        if label in values:
            raise PipelineBindingError(f"{path.name}: duplicate {label} replacement.")
        values[label] = value
    required = {*BASELINE_VALUES, "Refresh workspace"}
    if set(values) != required or len(model_names) != 1:
        raise PipelineBindingError(f"{path.name}: expected exactly the four native pipeline binding rules.")
    if len(set(values.values())) != 4:
        raise PipelineBindingError(f"{path.name}: source binding GUIDs must be distinct.")
    model_name = next(iter(model_names))
    model_path = (repo_dir / f"{model_name}.SemanticModel" / ".platform").resolve()
    if model_path.parent.parent != repo_dir.resolve() or not model_path.is_file():
        raise PipelineBindingError(f"{path.name}: referenced Semantic Model {model_name!r} is not in the repository.")
    return ParameterSources(path, text, values, model_name)


def validate_deployment_source(
    repo_dir: str | Path, *, bulk: bool = False, target_workspace_id: str | None = None,
) -> DevPipelineBindings:
    directory = Path(repo_dir)
    bindings = load_dev_bindings(directory)
    if target_workspace_id is not None:
        problem = guid_problem(target_workspace_id, "FABRIC_WORKSPACE_ID")
        if problem:
            raise PipelineBindingError(problem)
        if target_workspace_id.lower() == bindings.workspace_id.lower():
            raise PipelineBindingError(
                "Upper-environment publishers must not target Git-synced Dev. "
                "Use the Dev Git-sync workflow instead."
            )
    validate_pipeline_source(directory, bindings.workspace_id, bindings.values)
    sources = parameter_sources(directory, bulk=bulk)
    expected = {**bindings.values, "Refresh workspace": bindings.workspace_id}
    if sources.values != expected:
        raise PipelineBindingError(
            f"{sources.path.name} does not match {DEV_BINDINGS_FILENAME}. "
            "Run automated Dev preparation to align the source and both parameter files."
        )
    return bindings


def prepare_pipeline_connections(
    repo_dir: str | Path, workspace_id: str, token_provider: Callable[[], str],
) -> dict[str, str]:
    """Resolve target connection IDs in memory for all four publishers."""
    if not pipeline_files(repo_dir):
        return {}
    mode = connection_mode()
    authentication = runtime_authentication()
    values = ensure_pipeline_connections(
        FabricRestClient(token_provider), workspace_id, mode=mode,
        notebook_connection_id=os.environ.get(NOTEBOOK_CONNECTION_ENV) or None,
        refresh_connection_id=os.environ.get(REFRESH_CONNECTION_ENV) or None,
        authentication=authentication,
        credentials=runtime_credentials(authentication, required=mode == "auto"),
    )
    if set(values) != {NOTEBOOK_CONNECTION_ENV, REFRESH_CONNECTION_ENV}:
        raise PipelineBindingError("Connection bootstrap did not return both expected connection IDs.")
    _, problems = read_binding_values(values, "deploy_env_key")
    if problems:
        raise PipelineBindingError("Connection bootstrap returned invalid IDs:\n- " + "\n- ".join(problems))
    os.environ.update(values)
    require_pipeline_connections(repo_dir)
    print("Runtime connections resolved automatically; deployment variables are ready.")
    return values


def create_client(*, use_azure_cli: bool = False) -> FabricRestClient:
    if not use_azure_cli:
        missing = [
            name for name in ("AZURE_TENANT_ID", "AZURE_CLIENT_ID", "AZURE_CLIENT_SECRET")
            if not os.environ.get(name)
        ]
        if missing:
            raise PipelineBindingError(
                f"Missing service-principal credentials: {', '.join(missing)}. "
                "Use the Actions principal, or explicitly select --use-azure-cli."
            )
        for name in ("AZURE_TENANT_ID", "AZURE_CLIENT_ID"):
            problem = guid_problem(os.environ[name], name)
            if problem:
                raise PipelineBindingError(problem)
    try:
        from azure.identity import AzureCliCredential, ClientSecretCredential
    except ImportError as exc:
        raise PipelineBindingError("Install requirements-dev.txt; live setup needs azure-identity.") from exc
    if use_azure_cli:
        credential = AzureCliCredential()
    else:
        credential = ClientSecretCredential(
            tenant_id=os.environ["AZURE_TENANT_ID"], client_id=os.environ["AZURE_CLIENT_ID"],
            client_secret=os.environ["AZURE_CLIENT_SECRET"],
        )
    from azure.core.exceptions import ClientAuthenticationError

    def token_provider() -> str:
        try:
            return credential.get_token(FABRIC_SCOPE).token
        except ClientAuthenticationError as exc:
            raise RuntimeError(
                "Fabric authentication failed. Verify the explicitly selected Azure identity "
                "and approved credentials; no token or credential was logged."
            ) from exc

    return FabricRestClient(token_provider)


def item_id(client: FabricRestClient, workspace_id: str, item_type: str, name: str) -> str:
    items = client.list(f"/workspaces/{workspace_id}/items?type={item_type}")
    matches = [item for item in items if item.get("displayName") == name and item.get("type") == item_type]
    if len(matches) != 1:
        raise PipelineBindingError(
            f"Expected one {item_type} named {name!r} in the explicit workspace, found {len(matches)}."
        )
    value = matches[0].get("id")
    if not isinstance(value, str):
        raise PipelineBindingError(f"{name}: API item ID is not a GUID string.")
    problem = guid_problem(value, f"{name} item ID")
    if problem:
        raise PipelineBindingError(problem)
    return value


def _write_updates(updates: Mapping[Path, str]) -> None:
    originals = {path: path.read_bytes() if path.exists() else None for path in updates}
    staged: dict[Path, Path] = {}
    replaced: list[Path] = []
    try:
        for path, text in updates.items():
            with tempfile.NamedTemporaryFile(
                mode="w", encoding="utf-8", newline="", dir=path.parent, delete=False,
            ) as stream:
                temporary = Path(stream.name)
                staged[path] = temporary
                stream.write(text)
            temporary.replace(path)
            replaced.append(path)
    except OSError as exc:
        rollback_errors: list[str] = []
        for path in reversed(replaced):
            try:
                original = originals[path]
                if original is None:
                    path.unlink()
                else:
                    path.write_bytes(original)
            except OSError:
                rollback_errors.append(str(path))
        message = "Could not record Dev bindings; local source changes were rolled back."
        if rollback_errors:
            message = "Could not record Dev bindings; rollback also failed for: " + ", ".join(rollback_errors)
        raise PipelineBindingError(message) from exc
    finally:
        for temporary in staged.values():
            temporary.unlink(missing_ok=True)


def record_dev_bindings(
    repo_dir: Path, bindings: DevPipelineBindings, *, rewrite_source: bool = False,
) -> None:
    sources = [parameter_sources(repo_dir, bulk=bulk) for bulk in (False, True)]
    if sources[0].values != sources[1].values or sources[0].model_name != sources[1].model_name:
        raise PipelineBindingError("Both parameter files must agree before Dev bindings can be recorded.")
    if bindings.workspace_id != dev_workspace_id(repo_dir):
        raise PipelineBindingError("Dev preparation cannot target another workspace.")
    expected = {**bindings.values, "Refresh workspace": bindings.workspace_id}
    for label, value in expected.items():
        problem = guid_problem(value, label)
        if problem:
            raise PipelineBindingError(problem)
    if len(set(expected.values())) != 4:
        raise PipelineBindingError("Dev resource IDs must be distinct.")
    updates: dict[Path, str] = {}
    replacements = {sources[0].values[label]: value for label, value in expected.items()}
    pattern = re.compile("|".join(re.escape(value) for value in replacements))
    for source in sources:
        updates[source.path] = pattern.sub(lambda match: replacements[match.group()], source.text)
    if rewrite_source:
        for path in pipeline_files(repo_dir):
            updates[path] = rewrite(path.read_bytes().decode("utf-8"), expected)
    updates[dev_bindings_path(repo_dir)] = json.dumps(bindings.document(), indent=2) + "\n"
    _write_updates(updates)
    print(f"Recorded canonical Dev resources in {DEV_BINDINGS_FILENAME}; both parameter files are aligned.")


def prepare_dev(
    repo_dir: Path, client: FabricRestClient, *, replace_bindings: bool = False,
    rewrite_source: bool = False,
) -> DevPipelineBindings:
    sources = [parameter_sources(repo_dir, bulk=bulk) for bulk in (False, True)]
    if sources[0].values != sources[1].values or sources[0].model_name != sources[1].model_name:
        raise PipelineBindingError("Both parameter files must agree before any resources are provisioned.")
    for path in pipeline_files(repo_dir):
        locate_fields(path.read_text(encoding="utf-8"))
        locate_refresh_workspace(path.read_text(encoding="utf-8"))
    workspace_id = dev_workspace_id(repo_dir)
    try:
        previous = load_dev_bindings(repo_dir)
    except DevBindingsNotInitialized:
        previous = None
    model_id = item_id(client, workspace_id, "SemanticModel", sources[0].model_name)
    if previous and not replace_bindings and model_id != previous.semantic_model_id:
        raise PipelineBindingError(
            "The canonical Dev model was recreated. Use --replace-dev-bindings deliberately, "
            "then review the generated source changes."
        )
    connections = ensure_pipeline_connections(
        client, workspace_id, mode="auto",
        notebook_connection_id=previous.notebook_connection_id if previous and not replace_bindings else None,
        refresh_connection_id=previous.refresh_connection_id if previous and not replace_bindings else None,
        authentication=runtime_authentication(),
        credentials=runtime_credentials(runtime_authentication()),
    )
    bindings = DevPipelineBindings(
        workspace_id, model_id, connections[NOTEBOOK_CONNECTION_ENV], connections[REFRESH_CONNECTION_ENV],
    )
    record_dev_bindings(repo_dir, bindings, rewrite_source=rewrite_source)
    return bindings


def prepare_feature(repo_dir: Path, client: FabricRestClient, env_file: Path) -> None:
    from workspace_swap import _read_env_file

    environment = _read_env_file(env_file)
    workspace_id = environment.get("FEATURE_WORKSPACE_ID", "")
    problem = guid_problem(workspace_id, "FEATURE_WORKSPACE_ID")
    if problem:
        raise PipelineBindingError(problem)
    if workspace_id.lower() == dev_workspace_id(repo_dir).lower():
        raise PipelineBindingError("A feature workspace must not be the Dev workspace.")
    sources = parameter_sources(repo_dir, bulk=False)
    lines = env_file.read_text(encoding="utf-8").splitlines() if env_file.exists() else []
    keys = (
        "FEATURE_WORKSPACE_ID", "FEATURE_LAKEHOUSE_ID", "FEATURE_SEMANTIC_MODEL_ID",
        "FEATURE_NOTEBOOK_CONNECTION_ID", "FEATURE_REFRESH_CONNECTION_ID",
    )
    for key in keys:
        if sum(line.partition("=")[0].strip() == key for line in lines if not line.lstrip().startswith("#")) > 1:
            raise PipelineBindingError(f"{env_file.name}: duplicate {key}; resolve before preparation.")
    lakehouse_id = item_id(client, workspace_id, "Lakehouse", "PatternsLakehouse")
    model_id = item_id(client, workspace_id, "SemanticModel", sources.model_name)
    connections = ensure_pipeline_connections(
        client, workspace_id,
        authentication="WorkspaceIdentity",
        notebook_connection_id=(
            environment.get("FEATURE_NOTEBOOK_CONNECTION_ID")
            if environment.get("FEATURE_NOTEBOOK_CONNECTION_ID") not in (None, "", "00000000-0000-0000-0000-000000000000")
            else None
        ),
        refresh_connection_id=(
            environment.get("FEATURE_REFRESH_CONNECTION_ID")
            if environment.get("FEATURE_REFRESH_CONNECTION_ID") not in (None, "", "00000000-0000-0000-0000-000000000000")
            else None
        ),
    )
    values = {
        "FEATURE_LAKEHOUSE_ID": lakehouse_id,
        "FEATURE_SEMANTIC_MODEL_ID": model_id,
        "FEATURE_NOTEBOOK_CONNECTION_ID": connections[NOTEBOOK_CONNECTION_ENV],
        "FEATURE_REFRESH_CONNECTION_ID": connections[REFRESH_CONNECTION_ENV],
    }
    for key, value in values.items():
        matches = [i for i, line in enumerate(lines) if line.partition("=")[0].strip() == key]
        if len(matches) > 1:
            raise PipelineBindingError(f"{env_file.name}: duplicate {key}; resolve before preparation.")
        if matches:
            lines[matches[0]] = f"{key}={value}"
        else:
            lines.append(f"{key}={value}")
    _write_updates({env_file: "\n".join(lines) + "\n"})
    print("Feature item and connection IDs discovered; ignored .env updated. No tracked definitions changed.")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument("--dev", action="store_true", help="Record stable Dev IDs automatically.")
    target.add_argument("--feature", action="store_true", help="Discover bindings for .env's explicit feature workspace.")
    parser.add_argument("--repository-directory", type=Path, default=REPO_ROOT / "data" / "fabric")
    parser.add_argument("--use-azure-cli", action="store_true", help="Explicitly use the signed-in Azure CLI identity.")
    parser.add_argument("--swap-to-dev", action="store_true", help="Also restore feature source IDs and remove its value set.")
    parser.add_argument("--replace-dev-bindings", action="store_true", help="Deliberately regenerate a deleted/recreated Dev baseline.")
    parser.add_argument("--dry-run", action="store_true", help="Validate/preview local setup without credentials or Fabric calls.")
    args = parser.parse_args(argv)
    if not args.dev and (args.swap_to_dev or args.replace_dev_bindings):
        parser.error("--swap-to-dev and --replace-dev-bindings require --dev.")
    directory = args.repository_directory.resolve()
    try:
        parameter_sources(directory, bulk=False)
        parameter_sources(directory, bulk=True)
        for path in pipeline_files(directory):
            locate_fields(path.read_text(encoding="utf-8"))
            locate_refresh_workspace(path.read_text(encoding="utf-8"))
        if args.dry_run:
            print("Setup preview: ensure identity/permissions/connections; record non-secret IDs.")
            print("No credentials loaded, no API calls, and no files changed.")
            return
        client = create_client(use_azure_cli=args.use_azure_cli)
        if args.dev:
            prepare_dev(
                directory, client, replace_bindings=args.replace_dev_bindings,
                rewrite_source=args.swap_to_dev,
            )
            if args.swap_to_dev:
                branch = subprocess.run(
                    ["git", "rev-parse", "--abbrev-ref", "HEAD"],
                    check=True, capture_output=True, text=True, encoding="utf-8",
                ).stdout.strip()
                from workspace_swap import sanitize_branch_name

                value_set = directory / "Patterns_Variables.VariableLibrary" / "valueSets" / f"{sanitize_branch_name(branch)}.json"
                flag = "--swap-to-dev" if value_set.exists() else "--check-ready"
                subprocess.run(
                    [sys.executable, str(REPO_ROOT / "scripts" / "workspace_swap.py"), flag], check=True,
                )
        else:
            prepare_feature(directory, client, ENV_FILE)
    except (OSError, ValueError, RuntimeError, subprocess.CalledProcessError) as exc:
        print(f"::error::{exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
