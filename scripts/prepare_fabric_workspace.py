"""Record local Dev IDs or validate existing feature WI connections.

Dev preparation and swaps are offline; PyYAML reads the committed parameter
rules. Feature validation needs azure-identity and an explicit Azure CLI user
sign-in. Connection provisioning is a separate, human-administered workflow.
No local SP secrets, Actions artifacts, or implicit workflow dispatches.
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
import tempfile
from collections.abc import Callable, Mapping
from pathlib import Path

from fabric_connections import FabricRestClient, ensure_pipeline_connections, validate_connection_configuration
from pipeline_bindings import (
    NOTEBOOK_CONNECTION_ENV, REFRESH_CONNECTION_ENV, DevBindingsNotInitialized,
    DevPipelineBindings, PipelineBindingError, dev_workspace_id, guid_problem,
    load_dev_bindings, locate_fields, locate_refresh_workspace, parameter_sources,
    pipeline_files, read_binding_values, require_pipeline_connections, rewrite,
    validate_pipeline_source,
)

FABRIC_SCOPE = "https://api.fabric.microsoft.com/.default"
REPO_ROOT = Path(__file__).resolve().parents[1]
ENV_FILE = REPO_ROOT / ".env"


def connection_mode(environ: Mapping[str, str] | None = None) -> str:
    source = os.environ if environ is None else environ
    mode = source.get("FABRIC_CONNECTION_MODE", "") or "existing"
    if mode != "existing":
        raise PipelineBindingError("FABRIC_CONNECTION_MODE must be existing; provision connections explicitly first.")
    values, problems = read_binding_values(source, "deploy_env_key", require_all=True)
    if problems or len(values) != 2:
        raise PipelineBindingError("Pipeline connection variables are invalid:\n- " + "\n- ".join(problems))
    return mode


def runtime_authentication(environ: Mapping[str, str] | None = None) -> str:
    source = os.environ if environ is None else environ
    authentication = source.get("FABRIC_RUNTIME_AUTHENTICATION", "") or "WorkspaceIdentity"
    if authentication != "WorkspaceIdentity":
        raise PipelineBindingError("FABRIC_RUNTIME_AUTHENTICATION must be WorkspaceIdentity, not deployment credentials.")
    return authentication


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
            raise PipelineBindingError("Upper-environment publishers must not target Git-synced Dev. Use manual Update all.")
    validate_pipeline_source(directory, bindings.workspace_id, bindings.values)
    return bindings


def prepare_pipeline_connections(
    repo_dir: str | Path, workspace_id: str, token_provider: Callable[[], str],
) -> dict[str, str]:
    if not pipeline_files(repo_dir):
        return {}
    values = ensure_pipeline_connections(
        FabricRestClient(token_provider), workspace_id, mode=connection_mode(),
        notebook_connection_id=os.environ.get(NOTEBOOK_CONNECTION_ENV),
        refresh_connection_id=os.environ.get(REFRESH_CONNECTION_ENV),
        authentication=runtime_authentication(), credentials=None,
    )
    if set(values) != {NOTEBOOK_CONNECTION_ENV, REFRESH_CONNECTION_ENV}:
        raise PipelineBindingError("Connection preflight did not return both expected connection IDs.")
    _, problems = read_binding_values(values, "deploy_env_key")
    if problems:
        raise PipelineBindingError("Connection preflight returned invalid IDs:\n- " + "\n- ".join(problems))
    os.environ.update(values)
    require_pipeline_connections(repo_dir)
    print("Existing WI connections validated; no connections, credentials, identities, or roles changed.")
    return values


def create_client(*, use_azure_cli: bool = False) -> FabricRestClient:
    if not use_azure_cli:
        raise PipelineBindingError("Feature validation requires --use-azure-cli; no local SP credentials are accepted.")
    try:
        from azure.identity import AzureCliCredential
        from azure.core.exceptions import ClientAuthenticationError
    except ImportError as exc:
        raise PipelineBindingError("Install requirements-dev.txt; Fabric validation needs azure-identity.") from exc
    credential = AzureCliCredential()

    def token_provider() -> str:
        try:
            return credential.get_token(FABRIC_SCOPE).token
        except ClientAuthenticationError:
            raise RuntimeError("Azure user authentication failed. Use az login --use-device-code; tokens are suppressed.") from None

    return FabricRestClient(token_provider)


def item_id(client: FabricRestClient, workspace_id: str, item_type: str, name: str) -> str:
    matches = [
        item for item in client.list(f"/workspaces/{workspace_id}/items?type={item_type}")
        if item.get("displayName") == name and item.get("type") == item_type
    ]
    if len(matches) != 1:
        raise PipelineBindingError(f"Expected one {item_type} named {name!r}; found {len(matches)}.")
    value = matches[0].get("id")
    problem = guid_problem(value, f"{name} item ID")
    if problem:
        raise PipelineBindingError(problem)
    if not isinstance(value, str):
        raise PipelineBindingError(f"{name}: missing item ID.")
    return value


def _write_updates(updates: Mapping[Path, str]) -> None:
    originals = {path: path.read_bytes() if path.exists() else None for path in updates}
    staged: dict[Path, Path] = {}
    replaced: list[Path] = []
    try:
        for path, text in updates.items():
            with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", newline="", dir=path.parent, delete=False) as stream:
                staged[path] = Path(stream.name)
                stream.write(text)
            staged[path].replace(path)
            replaced.append(path)
    except OSError as exc:
        failures: list[str] = []
        for path in reversed(replaced):
            try:
                original = originals[path]
                if original is None:
                    path.unlink()
                else:
                    path.write_bytes(original)
            except OSError:
                failures.append(str(path))
        message = "Could not record Dev bindings; local updates were rolled back."
        if failures:
            message = "Dev binding rollback failed for: " + ", ".join(failures)
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
    if bindings.workspace_id.lower() != dev_workspace_id(repo_dir).lower():
        raise PipelineBindingError("Dev input must match the Variable Library's Dev workspace.")
    expected = {**bindings.values, "Refresh workspace": bindings.workspace_id}
    for label, value in expected.items():
        problem = guid_problem(value, label)
        if problem:
            raise PipelineBindingError(problem)
    if len({value.lower() for value in expected.values()}) != 4:
        raise PipelineBindingError("Dev resource IDs must be distinct.")
    validate_connection_configuration(
        bindings.workspace_id, mode="existing", authentication="WorkspaceIdentity",
        notebook_connection_id=bindings.notebook_connection_id,
        refresh_connection_id=bindings.refresh_connection_id,
    )
    replacements = {sources[0].values[label]: value for label, value in expected.items()}
    pattern = re.compile("|".join(re.escape(value) for value in replacements))
    updates = {source.path: pattern.sub(lambda match: replacements[match.group()], source.text) for source in sources}
    if rewrite_source:
        paths = pipeline_files(repo_dir)
        staged = repo_dir.parent / "fabric-initialization"
        if staged.is_dir():
            paths += pipeline_files(staged)
        for path in paths:
            updates[path] = rewrite(path.read_bytes().decode("utf-8"), expected)
    _write_updates(updates)
    print("Canonical Dev IDs recorded in both parameter files; no extra binding JSON or cloud writes.")


def prepare_dev(
    repo_dir: Path, bindings: DevPipelineBindings, *, replace_bindings: bool = False,
    rewrite_source: bool = False,
) -> DevPipelineBindings:
    try:
        previous = load_dev_bindings(repo_dir)
    except DevBindingsNotInitialized:
        previous = None
    if previous is not None and previous != bindings and not replace_bindings:
        raise PipelineBindingError("Dev IDs differ from the recorded baseline; use --replace-dev-bindings for a reviewed cutover.")
    record_dev_bindings(repo_dir, bindings, rewrite_source=rewrite_source)
    return bindings


def local_values(env_file: Path, keys: tuple[str, ...]) -> dict[str, str]:
    from workspace_swap import _read_env_file

    lines = env_file.read_text(encoding="utf-8").splitlines()
    for key in keys:
        if sum(line.partition("=")[0].strip() == key for line in lines if not line.lstrip().startswith("#")) > 1:
            raise PipelineBindingError(f"Duplicate {key} in .env.")
    return _read_env_file(env_file)


def local_dev_bindings(env_file: Path) -> DevPipelineBindings:
    keys = ("DEV_WORKSPACE_ID", "DEV_SEMANTIC_MODEL_ID", "DEV_NOTEBOOK_CONNECTION_ID", "DEV_REFRESH_CONNECTION_ID")
    environment = local_values(env_file, keys)
    values = []
    for key in keys:
        value = environment.get(key, "")
        problem = guid_problem(value, key)
        if problem:
            raise PipelineBindingError(problem)
        values.append(value)
    return DevPipelineBindings(*values)


def stage_initial_pipeline(repo_dir: Path, *, restore: bool, dry_run: bool = False) -> None:
    staging = repo_dir.parent / "fabric-initialization"
    source, destination = (staging, repo_dir) if restore else (repo_dir, staging)
    paths = pipeline_files(source)
    if not paths:
        raise PipelineBindingError("No native pipeline is available to restore." if restore else "No pipeline is available to stage.")
    folders = [path.parent for path in paths]
    for folder in folders:
        if folder.is_symlink() or (destination / folder.name).exists():
            raise PipelineBindingError("Initial pipeline staging would overwrite an existing item or follow a symlink.")
        locate_fields((folder / "pipeline-content.json").read_text(encoding="utf-8"))
        locate_refresh_workspace((folder / "pipeline-content.json").read_text(encoding="utf-8"))
    if dry_run:
        print("Preview: move native pipeline definitions outside the Git-sync folder." if not restore else "Preview: restore staged pipeline definitions.")
        return
    destination.mkdir(parents=True, exist_ok=True)
    moved: list[Path] = []
    try:
        for folder in folders:
            folder.rename(destination / folder.name)
            moved.append(folder)
    except OSError:
        for folder in reversed(moved):
            (destination / folder.name).rename(folder)
        raise
    if restore and not any(staging.iterdir()):
        staging.rmdir()
    print("Pipeline definitions restored." if restore else "Pipeline definitions staged outside data/fabric for base-item initialization.")
    print("Review and commit this local change before Git sync. No Git or Fabric operations were performed.")


def prepare_feature(repo_dir: Path, client: FabricRestClient, env_file: Path) -> None:
    environment = local_values(env_file, (
        "FEATURE_WORKSPACE_ID", "FEATURE_LAKEHOUSE_ID", "FEATURE_SEMANTIC_MODEL_ID",
        "FEATURE_NOTEBOOK_CONNECTION_ID", "FEATURE_REFRESH_CONNECTION_ID",
    ))
    workspace_id = environment.get("FEATURE_WORKSPACE_ID", "")
    problem = guid_problem(workspace_id, "FEATURE_WORKSPACE_ID")
    if problem:
        raise PipelineBindingError(problem)
    if workspace_id.lower() == dev_workspace_id(repo_dir).lower():
        raise PipelineBindingError("A feature workspace must not be Dev.")
    supplied = {
        NOTEBOOK_CONNECTION_ENV: environment.get("FEATURE_NOTEBOOK_CONNECTION_ID", ""),
        REFRESH_CONNECTION_ENV: environment.get("FEATURE_REFRESH_CONNECTION_ID", ""),
    }
    _, problems = read_binding_values(supplied, "deploy_env_key", baseline_values=load_dev_bindings(repo_dir).values)
    if problems:
        raise PipelineBindingError("Existing feature IDs are required:\n- " + "\n- ".join(problems))
    source = parameter_sources(repo_dir, bulk=False)
    lakehouse = item_id(client, workspace_id, "Lakehouse", "PatternsLakehouse")
    model = item_id(client, workspace_id, "SemanticModel", source.model_name)
    connections = ensure_pipeline_connections(
        client, workspace_id, mode="existing", authentication="WorkspaceIdentity",
        notebook_connection_id=environment.get("FEATURE_NOTEBOOK_CONNECTION_ID"),
        refresh_connection_id=environment.get("FEATURE_REFRESH_CONNECTION_ID"),
    )
    updates = {
        "FEATURE_LAKEHOUSE_ID": lakehouse, "FEATURE_SEMANTIC_MODEL_ID": model,
        "FEATURE_NOTEBOOK_CONNECTION_ID": connections[NOTEBOOK_CONNECTION_ENV],
        "FEATURE_REFRESH_CONNECTION_ID": connections[REFRESH_CONNECTION_ENV],
    }
    lines = env_file.read_text(encoding="utf-8").splitlines()
    for key, value in updates.items():
        indices = [index for index, line in enumerate(lines) if line.partition("=")[0].strip() == key]
        if len(indices) > 1:
            raise PipelineBindingError(f"Duplicate {key} in .env.")
        if indices:
            lines[indices[0]] = f"{key}={value}"
        else:
            lines.append(f"{key}={value}")
    _write_updates({env_file: "\n".join(lines) + "\n"})
    print("Existing feature WI connections validated and item IDs recorded; no cloud resources changed.")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument("--dev", action="store_true")
    target.add_argument("--feature", action="store_true")
    target.add_argument("--stage-initial-pipeline", action="store_true")
    target.add_argument("--restore-initial-pipeline", action="store_true")
    parser.add_argument("--repository-directory", type=Path, default=REPO_ROOT / "data" / "fabric")
    parser.add_argument("--use-azure-cli", action="store_true")
    parser.add_argument("--swap-to-dev", action="store_true")
    parser.add_argument("--replace-dev-bindings", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    if not args.dev and (args.swap_to_dev or args.replace_dev_bindings):
        parser.error("Dev swap/cutover flags require --dev.")
    if args.use_azure_cli and not args.feature:
        parser.error("--use-azure-cli is only for feature validation.")
    try:
        directory = args.repository_directory.resolve()
        if args.stage_initial_pipeline or args.restore_initial_pipeline:
            stage_initial_pipeline(directory, restore=args.restore_initial_pipeline, dry_run=args.dry_run)
            return
        if args.dry_run:
            if args.dev:
                load_dev_bindings(directory)
                print("Preview: existing committed Dev baseline available for offline restoration.")
            else:
                print("Preview: validate manually prepared feature connections and discover item IDs.")
            print("No login, workflow dispatch, cloud calls, or writes.")
            return
        if args.dev:
            prepare_dev(directory, local_dev_bindings(ENV_FILE), replace_bindings=args.replace_dev_bindings, rewrite_source=True)
            if args.swap_to_dev:
                branch = subprocess.run(["git", "branch", "--show-current"], check=True, capture_output=True, text=True, encoding="utf-8").stdout.strip()
                from workspace_swap import sanitize_branch_name

                value_set = directory / "Patterns_Variables.VariableLibrary" / "valueSets" / f"{sanitize_branch_name(branch)}.json"
                flag = "--swap-to-dev" if value_set.exists() else "--check-ready"
                subprocess.run([sys.executable, str(REPO_ROOT / "scripts" / "workspace_swap.py"), flag], check=True)
        else:
            prepare_feature(directory, create_client(use_azure_cli=args.use_azure_cli), ENV_FILE)
    except (OSError, ValueError, RuntimeError, subprocess.CalledProcessError) as exc:
        print(f"::error::{exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
