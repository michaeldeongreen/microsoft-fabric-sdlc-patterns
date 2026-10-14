"""
Shared bindings and committed parameter-rule baselines for the native pipeline.

Patterns_Load_Validate_And_Refresh carries three environment-specific GUIDs
that the item registry in workspace_swap.py can't rewrite by value:

    Semantic model        ``datasetId`` of the native refresh activity
    Notebook connection   ``connection`` of every notebook activity
    Refresh connection    ``connection`` of the native refresh activity

The committed values are the baseline:

    - Semantic model: the Dev workspace's real model ID.
    - The constants below describe the initial, unconfigured source templates.
    - Local Dev preparation records real IDs in both parameter files.
    - Swaps and readiness read those committed rules offline. Unconfigured connection
      templates are never accepted as runnable Dev bindings.

Used by workspace_swap.py (swap and readiness check) and by the deploy scripts,
which validate canonical source fields before automated connection setup.

Fork setup: provision connections explicitly, record the resulting IDs in
.env, then run prepare_fabric_workspace.py --dev for a reviewed baseline cutover.
PyYAML is needed to read the existing parameter files; no cloud calls occur.
"""

from __future__ import annotations

import json
import os
import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, NamedTuple, TypedDict

PIPELINE_FILE_PATTERN = "*.DataPipeline/pipeline-content.json"
NOTEBOOK_ACTIVITY_TYPE = "TridentNotebook"
REFRESH_ACTIVITY_TYPE = "PBISemanticModelRefresh"

ZERO_GUID = "00000000-0000-0000-0000-000000000000"

# Dev's real Patterns_Semantic_Model ID (read once from Dev workspace metadata).
SEMANTIC_MODEL_BASELINE_ID = "62112b80-9cb4-4d65-befa-a8e9e6271ef0"
# Source TEMPLATES, not real connections. Never present them as Dev connections.
NOTEBOOK_CONNECTION_PLACEHOLDER_ID = "11111111-1111-4111-8111-111111111111"
REFRESH_CONNECTION_PLACEHOLDER_ID = "22222222-2222-4222-8222-222222222222"

# CI variables (GitHub Environment variables) that replace the connection templates.
NOTEBOOK_CONNECTION_ENV = "NOTEBOOK_CONNECTION_ID"
REFRESH_CONNECTION_ENV = "SEMANTIC_MODEL_REFRESH_CONNECTION_ID"


class PipelineBindingError(ValueError):
    """Pipeline binding configuration or content is invalid."""


class DevBindingsNotInitialized(PipelineBindingError):
    """The committed parameter rules still contain unconfigured templates."""


@dataclass(frozen=True)
class DevPipelineBindings:
    workspace_id: str
    semantic_model_id: str
    notebook_connection_id: str
    refresh_connection_id: str

    @property
    def values(self) -> dict[str, str]:
        return {
            "Semantic model": self.semantic_model_id,
            "Notebook connection": self.notebook_connection_id,
            "Refresh connection": self.refresh_connection_id,
        }

    def document(self) -> dict[str, str | int]:
        return {
            "schemaVersion": 1,
            "workspaceId": self.workspace_id,
            "semanticModelId": self.semantic_model_id,
            "notebookConnectionId": self.notebook_connection_id,
            "semanticModelRefreshConnectionId": self.refresh_connection_id,
        }


@dataclass(frozen=True)
class ParameterSources:
    path: Path
    text: str
    values: dict[str, str]
    model_name: str


def parameter_sources(repo_dir: Path, *, bulk: bool) -> ParameterSources:
    try:
        import yaml
    except ImportError as exc:
        raise PipelineBindingError("Install requirements-dev.txt; committed parameter rules need PyYAML.") from exc
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
            if any(not isinstance(key, str) for key in replacement):
                raise PipelineBindingError(f"{path.name}: pipeline environment names must be strings.")
            if "_ALL_" not in replacement and not {"Test", "Prod"}.issubset(replacement):
                raise PipelineBindingError(f"{path.name}: pipeline replacement must cover _ALL_ or both Test and Prod.")
            if any(not isinstance(value, str) for value in replacement.values()):
                raise PipelineBindingError(f"{path.name}: pipeline target expressions must be strings.")
            replacements = set(replacement.values())
            if len(replacements) != 1:
                raise PipelineBindingError(f"{path.name}: sample rules require one target expression.")
            replacement = next(iter(replacements))
        if not isinstance(replacement, str):
            raise PipelineBindingError(f"{path.name}: pipeline replacement must be a string.")
        model_match = re.fullmatch(r"\$items\.SemanticModel\.([^$]+?)\.\$id", replacement)
        if model_match:
            label = "Semantic model"
            model_names.add(model_match.group(1))
        else:
            label = {
                f"$ENV:{NOTEBOOK_CONNECTION_ENV}": "Notebook connection",
                f"$ENV:{REFRESH_CONNECTION_ENV}": "Refresh connection",
                "$workspace.$id": "Refresh workspace",
            }.get(replacement, "")
        if not label:
            continue
        value = rule.get("find" if bulk else "find_value")
        if not isinstance(value, str):
            raise PipelineBindingError(f"{path.name}: {label} find value must be a GUID.")
        problem = guid_problem(value, label)
        if problem:
            raise PipelineBindingError(f"{path.name}: {problem}")
        if label in values:
            raise PipelineBindingError(f"{path.name}: duplicate {label} replacement.")
        values[label] = value
    if set(values) != {*BASELINE_VALUES, "Refresh workspace"} or len(model_names) != 1:
        raise PipelineBindingError(f"{path.name}: expected exactly the four native pipeline binding rules.")
    if len({value.lower() for value in values.values()}) != 4:
        raise PipelineBindingError(f"{path.name}: source binding GUIDs must be distinct.")
    model_name = next(iter(model_names))
    model_path = (repo_dir / f"{model_name}.SemanticModel" / ".platform").resolve()
    if model_path.parent.parent != repo_dir.resolve() or not model_path.is_file():
        raise PipelineBindingError(f"{path.name}: referenced Semantic Model is not in the repository.")
    return ParameterSources(path, text, values, model_name)


def load_dev_bindings(repo_dir: str | os.PathLike[str]) -> DevPipelineBindings:
    """Read the shared baseline from both parameter files, not a private .env."""
    directory = Path(repo_dir)
    standard = parameter_sources(directory, bulk=False)
    bulk = parameter_sources(directory, bulk=True)
    if standard.values != bulk.values or standard.model_name != bulk.model_name:
        raise PipelineBindingError("Both parameter files must agree on the canonical Dev baseline.")
    values = standard.values
    if values["Refresh workspace"].lower() != dev_workspace_id(directory).lower():
        raise PipelineBindingError("Parameter rules do not match the Variable Library's Dev workspace.")
    if {NOTEBOOK_CONNECTION_PLACEHOLDER_ID, REFRESH_CONNECTION_PLACEHOLDER_ID}.intersection(values.values()):
        raise DevBindingsNotInitialized("Dev connection rules are uninitialized; record real IDs from local .env.")
    return DevPipelineBindings(
        values["Refresh workspace"], values["Semantic model"],
        values["Notebook connection"], values["Refresh connection"],
    )


def dev_workspace_id(repo_dir: str | os.PathLike[str]) -> str:
    """The Variable Library's default workspace is the explicit Dev target."""
    path = Path(repo_dir) / "Patterns_Variables.VariableLibrary" / "variables.json"
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise PipelineBindingError(f"{path}: invalid Variable Library JSON.") from exc
    variables = document.get("variables") if isinstance(document, dict) else None
    if not isinstance(variables, list):
        raise PipelineBindingError(f"{path}: variables must be a list.")
    matches = [
        entry.get("value") for entry in variables
        if isinstance(entry, dict) and entry.get("name") == "target_workspace_id"
    ]
    if len(matches) != 1 or not isinstance(matches[0], str):
        raise PipelineBindingError(f"{path}: expected one target_workspace_id GUID.")
    problem = guid_problem(matches[0], "target_workspace_id")
    if problem:
        raise PipelineBindingError(f"{path}: {problem}")
    return matches[0]


class PipelineBinding(TypedDict):
    """One environment-specific GUID inside the pipeline.

    name             – display name; also the key of the value mappings below
    activity_type    – pipeline activity type that owns the field
    field            – JSON key holding the GUID inside that activity
    baseline         – value committed on dev/main
    feature_env_key  – .env key workspace_swap.py reads for a feature workspace
    deploy_env_key   – CI variable that replaces the baseline at deploy time;
                       None when deployment resolves it from the target workspace
    """

    name: str
    activity_type: str
    field: str
    baseline: str
    feature_env_key: str
    deploy_env_key: str | None


PIPELINE_BINDINGS: tuple[PipelineBinding, ...] = (
    {
        "name": "Semantic model",
        "activity_type": REFRESH_ACTIVITY_TYPE,
        "field": "datasetId",
        "baseline": SEMANTIC_MODEL_BASELINE_ID,
        "feature_env_key": "FEATURE_SEMANTIC_MODEL_ID",
        "deploy_env_key": None,
    },
    {
        "name": "Notebook connection",
        "activity_type": NOTEBOOK_ACTIVITY_TYPE,
        "field": "connection",
        "baseline": NOTEBOOK_CONNECTION_PLACEHOLDER_ID,
        "feature_env_key": "FEATURE_NOTEBOOK_CONNECTION_ID",
        "deploy_env_key": NOTEBOOK_CONNECTION_ENV,
    },
    {
        "name": "Refresh connection",
        "activity_type": REFRESH_ACTIVITY_TYPE,
        "field": "connection",
        "baseline": REFRESH_CONNECTION_PLACEHOLDER_ID,
        "feature_env_key": "FEATURE_REFRESH_CONNECTION_ID",
        "deploy_env_key": REFRESH_CONNECTION_ENV,
    },
)
BASELINE_VALUES: dict[str, str] = {b["name"]: b["baseline"] for b in PIPELINE_BINDINGS}

_GUID = re.compile(r"[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}")


class BoundField(NamedTuple):
    """A bound GUID located in a pipeline definition (offsets index its value)."""

    binding: str
    activity: str
    start: int
    end: int
    value: str


def is_guid(value: str) -> bool:
    """True for a bare, hyphenated GUID (no braces, whitespace or newline)."""
    return _GUID.fullmatch(value) is not None


def guid_problem(value: str, label: str) -> str | None:
    """Why ``value`` can't be ``label`` (not a bare hyphenated GUID, or all zeros)."""
    if not is_guid(value):
        return f"{label} must be a hyphenated GUID (got {value[:64]!r})"
    if value == ZERO_GUID:
        return f"{label} is the all-zero GUID"
    return None


def read_binding_values(
    source: Mapping[str, str], key_field: Literal["feature_env_key", "deploy_env_key"],
    *, baseline_values: Mapping[str, str] | None = None, require_all: bool = True,
) -> tuple[dict[str, str], list[str]]:
    """Read and validate the value each binding takes from ``source``.

    ``source`` is os.environ or a parsed .env. ``feature_env_key`` selects the
    .env keys a feature workspace needs; ``deploy_env_key`` selects the CI
    variables. Bindings without that key are skipped. A value is rejected when
    it is missing, not a bare hyphenated GUID, all zeros, a committed baseline
    (a placeholder or Dev's model is never the real value for another
    environment) or reused by another binding.

    Returns ({binding name: value}, problems).
    """
    baselines = {b["baseline"].lower(): b["name"] for b in PIPELINE_BINDINGS}
    if baseline_values is not None:
        baselines.update({value.lower(): name for name, value in baseline_values.items()})
    values: dict[str, str] = {}
    owners: dict[str, str] = {}
    problems: list[str] = []
    for binding in PIPELINE_BINDINGS:
        key = binding[key_field]
        if key is None:
            continue
        value = source.get(key, "")
        if not value and not require_all:
            continue
        problem = guid_problem(value, key) if value else f"{key} is not set or empty"
        if problem is None and value.lower() in baselines:
            problem = (
                f"{key} is the committed {baselines[value.lower()]} baseline, "
                "not a real value for this environment"
            )
        if problem is None and value.lower() in owners:
            problem = f"{key} repeats the value of {owners[value.lower()]}"
        if problem is None:
            values[binding["name"]] = value
            owners[value.lower()] = key
        else:
            problems.append(problem)
    return values, problems


def pipeline_files(repo_dir: str | os.PathLike[str]) -> list[Path]:
    """Pipeline definitions under ``repo_dir`` (a Fabric item directory such as data/fabric)."""
    return sorted(path for path in Path(repo_dir).glob(PIPELINE_FILE_PATTERN) if path.is_file())


def require_pipeline_connections(
    repo_dir: str | os.PathLike[str], environ: Mapping[str, str] | None = None
) -> dict[str, str]:
    """Validate the CI connection variables when ``repo_dir`` holds a DataPipeline.

    Returns {variable name: GUID} (the names the ``$ENV:`` rules reference), or
    {} when there is no DataPipeline so older fixtures need no variables.
    Raises PipelineBindingError, listing every problem, so callers fail before
    anything is published. Values must be bare hyphenated, non-zero GUIDs and
    must not be the committed placeholders; whitespace is rejected rather than
    trimmed because fabric-cicd substitutes the raw variable value.
    """
    if not pipeline_files(repo_dir):
        return {}
    values, problems = read_binding_values(os.environ if environ is None else environ, "deploy_env_key")
    if problems:
        raise PipelineBindingError(
            "Pipeline connection variables are invalid; set them as GitHub Environment "
            "variables before deploying:\n- " + "\n- ".join(problems)
        )
    return {b["deploy_env_key"]: values[b["name"]] for b in PIPELINE_BINDINGS if b["deploy_env_key"]}


def _object_spans(text: str) -> list[tuple[int, int]]:
    """Offsets of every JSON object in ``text`` (balanced braces outside strings)."""
    spans: list[tuple[int, int]] = []
    opened: list[int] = []
    in_string = escaped = False
    for index, char in enumerate(text):
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
        elif char == '"':
            in_string = True
        elif char == "{":
            opened.append(index)
        elif char == "}":
            spans.append((opened.pop(), index + 1))
    return spans


def locate_fields(text: str) -> list[BoundField]:
    """Locate every bound GUID in a pipeline definition, in file order.

    Raises PipelineBindingError unless the text is valid JSON with exactly one
    native refresh activity, and each bound field of that activity and of every
    notebook activity appears once with a GUID value (so nothing is guessed
    from an expression or a duplicate key).
    """
    try:
        json.loads(text)
    except json.JSONDecodeError as exc:
        raise PipelineBindingError(f"not valid JSON ({exc})") from exc

    activities: dict[str, list[tuple[int, int, str]]] = {}
    for start, end in _object_spans(text):
        activity = json.loads(text[start:end])
        kind = activity.get("type")
        if kind in (NOTEBOOK_ACTIVITY_TYPE, REFRESH_ACTIVITY_TYPE):
            activities.setdefault(kind, []).append((start, end, str(activity.get("name", ""))))

    problems: list[str] = []
    refreshes = len(activities.get(REFRESH_ACTIVITY_TYPE, []))
    if refreshes != 1:
        problems.append(f"expected exactly one {REFRESH_ACTIVITY_TYPE} activity, found {refreshes}")

    fields: list[BoundField] = []
    for binding in PIPELINE_BINDINGS:
        field = binding["field"]
        pattern = re.compile(rf'"{re.escape(field)}"\s*:\s*"([^"\\]*)"')
        for start, end, name in sorted(activities.get(binding["activity_type"], [])):
            found = list(pattern.finditer(text, start, end))
            label = f"{binding['activity_type']} activity {name!r}"
            if len(found) != 1:
                problems.append(f"{label} has {len(found)} {field} values, expected exactly one")
            elif not is_guid(found[0].group(1)):
                problems.append(f"{label} {field} is {found[0].group(1)!r}, not a GUID")
            else:
                fields.append(
                    BoundField(binding["name"], name, found[0].start(1), found[0].end(1), found[0].group(1))
                )
    if problems:
        raise PipelineBindingError("; ".join(problems))
    return sorted(fields, key=lambda located: located.start)


def rewrite(text: str, values: Mapping[str, str]) -> str:
    """Set every bound field to ``values[binding name]``, leaving all other bytes untouched."""
    fields = locate_fields(text)
    if "Refresh workspace" in values:
        fields.append(locate_refresh_workspace(text))
    problems = [f"no value for {name}" for name in sorted({f.binding for f in fields} - values.keys())]
    problems += [f"{name} value {value!r} is not a GUID" for name, value in values.items() if not is_guid(value)]
    if problems:
        raise PipelineBindingError("; ".join(problems))
    for located in sorted(fields, key=lambda f: f.start, reverse=True):
        text = text[: located.start] + values[located.binding] + text[located.end :]
    return text


def mismatches(text: str, expected: Mapping[str, str]) -> list[str]:
    """Describe each bound field that doesn't hold its ``expected`` value."""
    fields = locate_fields(text)
    if "Refresh workspace" in expected:
        fields.append(locate_refresh_workspace(text))
    return [
        f"{located.binding} ({located.activity}) is {located.value}, expected {expected[located.binding]}"
        for located in fields
        if located.value != expected[located.binding]
    ]


def locate_refresh_workspace(text: str) -> BoundField:
    """Locate the native refresh's own groupId, not a GUID elsewhere in the file."""
    locate_fields(text)
    for start, end in _object_spans(text):
        activity = json.loads(text[start:end])
        if activity.get("type") != REFRESH_ACTIVITY_TYPE:
            continue
        properties = activity.get("typeProperties")
        workspace = properties.get("groupId") if isinstance(properties, dict) else None
        matches = list(re.finditer(r'"groupId"\s*:\s*"([^"\\]*)"', text[start:end]))
        if not isinstance(workspace, str) or not is_guid(workspace) or len(matches) != 1:
            raise PipelineBindingError(
                f"{REFRESH_ACTIVITY_TYPE} activity {activity.get('name')!r} "
                "must have exactly one typeProperties.groupId GUID"
            )
        match = matches[0]
        return BoundField(
            "Refresh workspace", str(activity.get("name", "")),
            start + match.start(1), start + match.end(1), workspace,
        )
    raise PipelineBindingError(f"expected exactly one {REFRESH_ACTIVITY_TYPE} activity")


def validate_pipeline_source(
    repo_dir: str | os.PathLike[str], workspace_id: str, expected: Mapping[str, str],
) -> None:
    """Reject source bindings that literal deployment replacements would miss."""
    problem = guid_problem(workspace_id, "Dev workspace ID")
    if problem:
        raise PipelineBindingError(problem)
    problems: list[str] = []
    for path in pipeline_files(repo_dir):
        try:
            differences = mismatches(
                path.read_text(encoding="utf-8"),
                {**expected, "Refresh workspace": workspace_id},
            )
        except PipelineBindingError as exc:
            problems.append(f"{path.parent.name}: {exc}")
        else:
            problems.extend(f"{path.parent.name}: {difference}" for difference in differences)
    if problems:
        raise PipelineBindingError(
            "Pipeline source is not at the Dev baseline:\n- " + "\n- ".join(problems)
            + "\nPrepare the Dev bindings and run workspace_swap.py --swap-to-dev "
            "before publishing. No deployment has started."
        )
