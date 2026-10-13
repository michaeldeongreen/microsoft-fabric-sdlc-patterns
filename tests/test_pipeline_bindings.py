"""Unit tests for scripts/pipeline_bindings.py and the files that must agree with it.

The cross-file tests pin the committed baselines to parameter.yml,
bulk-parameter.yml and .env.sample. They deliberately do not assert that the
committed pipeline holds the baselines: on a feature branch it holds the feature
workspace's values, and `workspace_swap.py --check-ready` is the readiness gate
that runs after `--swap-to-dev`.
"""

import ast
import json
import re
from pathlib import Path

import pytest
import yaml

import pipeline_bindings as pb

REPO_ROOT = Path(__file__).resolve().parent.parent
FABRIC_DIR = REPO_ROOT / "data" / "fabric"

DEV_WS_ID = "d7270f11-feba-4990-baa6-d45e47f23737"
NOTEBOOK_LOGICAL_IDS = (
    "3f21b546-f49f-9fef-4881-99b654a6701e",
    "decdcb11-8770-4216-8a28-eadf505d2679",
)
OTHER = {
    "Semantic model": "bbbbbbbb-1111-4111-8111-bbbbbbbbbbbb",
    "Notebook connection": "cccccccc-2222-4222-8222-cccccccccccc",
    "Refresh connection": "dddddddd-3333-4333-8333-dddddddddddd",
}
BYSTANDER = "eeeeeeee-4444-4444-8444-eeeeeeeeeeee"


# ── Builders ──────────────────────────────────────────────────────────────

def notebook_activity(name: str, logical_id: str, connection: str) -> dict:
    return {
        "name": name,
        "type": "TridentNotebook",
        "dependsOn": [],
        "policy": {"timeout": "0.12:00:00", "retry": 0},
        "typeProperties": {"notebookId": logical_id, "workspaceId": pb.ZERO_GUID},
        "externalReferences": {"connection": connection},
    }


def refresh_activity(name: str = "Refresh_Patterns_Semantic_Model", *,
                     model: str, connection: str) -> dict:
    return {
        "name": name,
        "type": "PBISemanticModelRefresh",
        "dependsOn": [],
        "policy": {"timeout": "0.12:00:00", "retry": 0},
        "typeProperties": {
            "method": "post",
            "groupId": DEV_WS_ID,
            "datasetId": model,
            "commitMode": "Transactional",
            "waitOnCompletion": True,
            "operationType": "SemanticModelRefresh",
        },
        "externalReferences": {"connection": connection},
    }


def pipeline_doc(values: dict[str, str] | None = None, extra: tuple[dict, ...] = ()) -> dict:
    values = values or pb.BASELINE_VALUES
    return {
        "properties": {
            "activities": [
                notebook_activity("Import_Patterns_Data", NOTEBOOK_LOGICAL_IDS[0], values["Notebook connection"]),
                notebook_activity("Validate_Patterns_Data", NOTEBOOK_LOGICAL_IDS[1], values["Notebook connection"]),
                refresh_activity(model=values["Semantic model"], connection=values["Refresh connection"]),
                *extra,
            ]
        }
    }


def pipeline_text(values: dict[str, str] | None = None, extra: tuple[dict, ...] = ()) -> str:
    return json.dumps(pipeline_doc(values, extra), indent=2) + "\n"


def swap_oracle(text: str, values: dict[str, str]) -> str:
    """Expected result of rewriting a baseline pipeline: a plain replace of each baseline GUID."""
    for name, baseline in pb.BASELINE_VALUES.items():
        text = text.replace(baseline, values[name])
    return text


# ── Constants ─────────────────────────────────────────────────────────────

class TestBaselines:
    def test_published_values(self):
        # These literals also appear in parameter.yml and bulk-parameter.yml.
        assert pb.SEMANTIC_MODEL_BASELINE_ID == "62112b80-9cb4-4d65-befa-a8e9e6271ef0"
        assert pb.NOTEBOOK_CONNECTION_PLACEHOLDER_ID == "11111111-1111-4111-8111-111111111111"
        assert pb.REFRESH_CONNECTION_PLACEHOLDER_ID == "22222222-2222-4222-8222-222222222222"

    def test_baselines_are_distinct_nonzero_guids(self):
        baselines = [b["baseline"] for b in pb.PIPELINE_BINDINGS]
        assert all(pb.is_guid(b) and b != pb.ZERO_GUID for b in baselines)
        assert len(set(baselines)) == len(baselines)

    def test_binding_names_and_keys_are_unique(self):
        names = [b["name"] for b in pb.PIPELINE_BINDINGS]
        feature_keys = [b["feature_env_key"] for b in pb.PIPELINE_BINDINGS]
        assert len(set(names)) == len(names)
        assert len(set(feature_keys)) == len(feature_keys)
        assert pb.BASELINE_VALUES == {b["name"]: b["baseline"] for b in pb.PIPELINE_BINDINGS}

    def test_ci_variables_are_the_two_connections(self):
        deploy_keys = {b["name"]: b["deploy_env_key"] for b in pb.PIPELINE_BINDINGS}
        assert deploy_keys == {
            "Semantic model": None,  # resolved from the target workspace at deploy time
            "Notebook connection": "NOTEBOOK_CONNECTION_ID",
            "Refresh connection": "SEMANTIC_MODEL_REFRESH_CONNECTION_ID",
        }


class TestGuidHelpers:
    @pytest.mark.parametrize("value", [
        "62112b80-9cb4-4d65-befa-a8e9e6271ef0",
        "62112B80-9CB4-4D65-BEFA-A8E9E6271EF0",
        pb.ZERO_GUID,
    ])
    def test_is_guid_accepts_bare_hyphenated_values(self, value: str):
        assert pb.is_guid(value)

    @pytest.mark.parametrize("value", [
        "",
        " 62112b80-9cb4-4d65-befa-a8e9e6271ef0",
        "62112b80-9cb4-4d65-befa-a8e9e6271ef0 ",
        "62112b80-9cb4-4d65-befa-a8e9e6271ef0\n",
        "{62112b80-9cb4-4d65-befa-a8e9e6271ef0}",
        "62112b809cb44d65befaa8e9e6271ef0",
        "62112b80-9cb4-4d65-befa-a8e9e6271ef",
        "62112b80-9cb4-4d65-befa-a8e9e6271efg",
        "$ENV:NOTEBOOK_CONNECTION_ID",
    ])
    def test_is_guid_rejects_everything_else(self, value: str):
        assert not pb.is_guid(value)

    def test_guid_problem_names_the_label(self):
        assert "MY_ID" in pb.guid_problem("nope", "MY_ID")
        assert "all-zero" in pb.guid_problem(pb.ZERO_GUID, "MY_ID")
        assert pb.guid_problem(OTHER["Semantic model"], "MY_ID") is None


class TestDevManifest:
    @pytest.fixture()
    def repository(self, tmp_path: Path) -> Path:
        directory = tmp_path / "fabric"
        variables = directory / "Patterns_Variables.VariableLibrary" / "variables.json"
        variables.parent.mkdir(parents=True)
        variables.write_text(json.dumps({"variables": [
            {"name": "target_workspace_id", "value": DEV_WS_ID},
        ]}), encoding="utf-8")
        return directory

    def bindings(self) -> pb.DevPipelineBindings:
        return pb.DevPipelineBindings(
            DEV_WS_ID, OTHER["Semantic model"], OTHER["Notebook connection"], OTHER["Refresh connection"],
        )

    def write(self, directory: Path, document: object) -> Path:
        path = pb.dev_bindings_path(directory)
        path.write_text(json.dumps(document), encoding="utf-8")
        return path

    def test_loads_real_non_secret_source_ids(self, repository: Path):
        bindings = self.bindings()
        self.write(repository, bindings.document())
        assert pb.load_dev_bindings(repository) == bindings
        assert pb.dev_bindings_path(repository).parent == repository.parent
        assert not pb.dev_bindings_path(repository).is_relative_to(repository)

    def test_missing_configuration_is_not_a_successful_template_fallback(self, repository: Path):
        with pytest.raises(pb.DevBindingsNotInitialized, match="prepare_fabric_workspace"):
            pb.load_dev_bindings(repository)

    def test_explicit_uninitialized_configuration_fails_readiness(self, repository: Path):
        self.write(repository, {key: (value if key == "schemaVersion" else None)
                                for key, value in self.bindings().document().items()})
        with pytest.raises(pb.DevBindingsNotInitialized, match="uninitialized"):
            pb.load_dev_bindings(repository)

    def test_partial_initialization_is_an_error_not_a_setup_fallback(self, repository: Path):
        self.write(repository, {**self.bindings().document(), "notebookConnectionId": None})
        with pytest.raises(pb.PipelineBindingError, match="partially initialized") as result:
            pb.load_dev_bindings(repository)
        assert not isinstance(result.value, pb.DevBindingsNotInitialized)

    @pytest.mark.parametrize("version", [True, "1", 2, None])
    def test_rejects_unknown_schema(self, repository: Path, version: object):
        self.write(repository, {**self.bindings().document(), "schemaVersion": version})
        with pytest.raises(pb.PipelineBindingError, match="schemaVersion"):
            pb.load_dev_bindings(repository)

    @pytest.mark.parametrize("value", ["not-a-guid", pb.ZERO_GUID, " " + DEV_WS_ID, 42])
    def test_rejects_invalid_external_ids(self, repository: Path, value: object):
        self.write(repository, {**self.bindings().document(), "notebookConnectionId": value})
        with pytest.raises(pb.PipelineBindingError, match="notebookConnectionId"):
            pb.load_dev_bindings(repository)

    def test_rejects_fake_connection_markers(self, repository: Path):
        self.write(repository, {
            **self.bindings().document(), "notebookConnectionId": pb.NOTEBOOK_CONNECTION_PLACEHOLDER_ID,
        })
        with pytest.raises(pb.PipelineBindingError, match="placeholder"):
            pb.load_dev_bindings(repository)

    def test_rejects_connection_reuse_for_different_purposes(self, repository: Path):
        self.write(repository, {
            **self.bindings().document(), "semanticModelRefreshConnectionId": OTHER["Notebook connection"],
        })
        with pytest.raises(pb.PipelineBindingError, match="distinct"):
            pb.load_dev_bindings(repository)

    def test_rejects_another_workspaces_manifest(self, repository: Path):
        self.write(repository, {**self.bindings().document(), "workspaceId": BYSTANDER})
        with pytest.raises(pb.PipelineBindingError, match="Variable Library"):
            pb.load_dev_bindings(repository)

    def test_rejects_unknown_configuration_fields(self, repository: Path):
        self.write(repository, {**self.bindings().document(), "clientSecret": "not-a-real-secret"})
        with pytest.raises(pb.PipelineBindingError, match="exactly"):
            pb.load_dev_bindings(repository)

    def test_real_dev_ids_are_rejected_for_feature_configuration(self, repository: Path):
        bindings = self.bindings()
        self.write(repository, bindings.document())
        values, errors = pb.read_binding_values({
            "FEATURE_SEMANTIC_MODEL_ID": bindings.semantic_model_id,
            "FEATURE_NOTEBOOK_CONNECTION_ID": bindings.notebook_connection_id,
            "FEATURE_REFRESH_CONNECTION_ID": bindings.refresh_connection_id,
        }, "feature_env_key", baseline_values=pb.load_dev_bindings(repository).values)
        assert not values
        assert len(errors) == 3


class TestReadBindingValues:
    def feature_env(self, **overrides: str) -> dict[str, str]:
        env = {b["feature_env_key"]: OTHER[b["name"]] for b in pb.PIPELINE_BINDINGS}
        env.update(overrides)
        return env

    def deploy_env(self, **overrides: str) -> dict[str, str]:
        env = {
            "NOTEBOOK_CONNECTION_ID": OTHER["Notebook connection"],
            "SEMANTIC_MODEL_REFRESH_CONNECTION_ID": OTHER["Refresh connection"],
        }
        env.update(overrides)
        return env

    def test_reads_every_feature_key(self):
        values, problems = pb.read_binding_values(self.feature_env(), "feature_env_key")
        assert problems == []
        assert values == OTHER

    def test_deploy_keys_skip_the_model(self):
        values, problems = pb.read_binding_values(self.deploy_env(), "deploy_env_key")
        assert problems == []
        assert values == {k: v for k, v in OTHER.items() if k != "Semantic model"}

    def test_missing_and_blank_values_are_all_reported(self):
        values, problems = pb.read_binding_values({"NOTEBOOK_CONNECTION_ID": ""}, "deploy_env_key")
        assert values == {}
        assert len(problems) == 2
        assert "NOTEBOOK_CONNECTION_ID is not set or empty" in problems
        assert "SEMANTIC_MODEL_REFRESH_CONNECTION_ID is not set or empty" in problems

    @pytest.mark.parametrize("bad", [
        "not-a-guid",
        " 62112b80-9cb4-4d65-befa-a8e9e6271ef0",
        "62112b80-9cb4-4d65-befa-a8e9e6271ef0\n",
        "{62112b80-9cb4-4d65-befa-a8e9e6271ef0}",
        pb.ZERO_GUID,
    ])
    def test_malformed_or_zero_values_are_rejected(self, bad: str):
        values, problems = pb.read_binding_values(
            self.deploy_env(NOTEBOOK_CONNECTION_ID=bad), "deploy_env_key")
        assert len(problems) == 1
        assert problems[0].startswith("NOTEBOOK_CONNECTION_ID")
        assert "Notebook connection" not in values

    @pytest.mark.parametrize("baseline", [b["baseline"] for b in pb.PIPELINE_BINDINGS])
    def test_every_committed_baseline_is_rejected_as_a_real_value(self, baseline: str):
        _, problems = pb.read_binding_values(
            self.deploy_env(SEMANTIC_MODEL_REFRESH_CONNECTION_ID=baseline), "deploy_env_key")
        assert len(problems) == 1
        assert "baseline" in problems[0]

    def test_baseline_check_ignores_case(self):
        _, problems = pb.read_binding_values(
            self.deploy_env(NOTEBOOK_CONNECTION_ID=pb.NOTEBOOK_CONNECTION_PLACEHOLDER_ID.upper()),
            "deploy_env_key")
        assert any("baseline" in p for p in problems)

    def test_the_same_value_cannot_serve_two_bindings(self):
        _, problems = pb.read_binding_values(
            self.deploy_env(SEMANTIC_MODEL_REFRESH_CONNECTION_ID=OTHER["Notebook connection"].upper()),
            "deploy_env_key")
        assert problems == [
            "SEMANTIC_MODEL_REFRESH_CONNECTION_ID repeats the value of NOTEBOOK_CONNECTION_ID"
        ]


# ── require_pipeline_connections ──────────────────────────────────────────

def add_pipeline(repo_dir: Path, name: str = "Patterns_Load.DataPipeline") -> None:
    pipeline_dir = repo_dir / name
    pipeline_dir.mkdir(parents=True)
    (pipeline_dir / "pipeline-content.json").write_text(pipeline_text(), encoding="utf-8")


class TestRequirePipelineConnections:
    VALID = {
        "NOTEBOOK_CONNECTION_ID": OTHER["Notebook connection"],
        "SEMANTIC_MODEL_REFRESH_CONNECTION_ID": OTHER["Refresh connection"],
    }

    def test_returns_nothing_without_a_pipeline_even_when_unset(self, tmp_path: Path):
        (tmp_path / "Import.Notebook").mkdir()
        assert pb.require_pipeline_connections(tmp_path, {}) == {}

    def test_returns_nothing_for_a_missing_directory(self, tmp_path: Path):
        assert pb.require_pipeline_connections(tmp_path / "absent", {}) == {}

    def test_accepts_str_and_path(self, tmp_path: Path):
        add_pipeline(tmp_path)
        assert pb.require_pipeline_connections(str(tmp_path), self.VALID) == self.VALID
        assert pb.require_pipeline_connections(tmp_path, self.VALID) == self.VALID

    def test_returns_values_keyed_by_variable_name(self, tmp_path: Path):
        add_pipeline(tmp_path)
        env = {**self.VALID, "UNRELATED": "x"}
        assert pb.require_pipeline_connections(tmp_path, env) == self.VALID

    def test_fails_before_publish_listing_every_missing_variable(self, tmp_path: Path):
        add_pipeline(tmp_path)
        with pytest.raises(pb.PipelineBindingError) as exc:
            pb.require_pipeline_connections(tmp_path, {})
        message = str(exc.value)
        assert "NOTEBOOK_CONNECTION_ID is not set or empty" in message
        assert "SEMANTIC_MODEL_REFRESH_CONNECTION_ID is not set or empty" in message

    def test_error_is_a_value_error(self, tmp_path: Path):
        add_pipeline(tmp_path)
        with pytest.raises(ValueError):
            pb.require_pipeline_connections(tmp_path, {})

    @pytest.mark.parametrize("bad", [
        pb.ZERO_GUID,
        "not-a-guid",
        OTHER["Notebook connection"] + "\n",
        " " + OTHER["Notebook connection"],
        pb.NOTEBOOK_CONNECTION_PLACEHOLDER_ID,
        pb.REFRESH_CONNECTION_PLACEHOLDER_ID,
    ])
    def test_rejects_zero_malformed_whitespace_and_placeholders(self, tmp_path: Path, bad: str):
        add_pipeline(tmp_path)
        with pytest.raises(pb.PipelineBindingError, match="NOTEBOOK_CONNECTION_ID"):
            pb.require_pipeline_connections(tmp_path, {**self.VALID, "NOTEBOOK_CONNECTION_ID": bad})

    def test_rejects_one_connection_used_for_both(self, tmp_path: Path):
        add_pipeline(tmp_path)
        env = {**self.VALID, "SEMANTIC_MODEL_REFRESH_CONNECTION_ID": OTHER["Notebook connection"]}
        with pytest.raises(pb.PipelineBindingError, match="repeats"):
            pb.require_pipeline_connections(tmp_path, env)

    def test_reads_the_process_environment_by_default(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        add_pipeline(tmp_path)
        for name, value in self.VALID.items():
            monkeypatch.setenv(name, value)
        assert pb.require_pipeline_connections(tmp_path) == self.VALID
        monkeypatch.delenv("NOTEBOOK_CONNECTION_ID")
        with pytest.raises(pb.PipelineBindingError):
            pb.require_pipeline_connections(tmp_path)

    def test_pipeline_files_finds_only_pipeline_definitions(self, tmp_path: Path):
        add_pipeline(tmp_path, "A.DataPipeline")
        (tmp_path / "B.Notebook").mkdir()
        (tmp_path / "B.Notebook" / "pipeline-content.json").write_text("{}", encoding="utf-8")
        assert [p.parent.name for p in pb.pipeline_files(tmp_path)] == ["A.DataPipeline"]


# ── locate_fields ─────────────────────────────────────────────────────────

class TestLocateFields:
    def test_locates_every_binding_in_file_order(self):
        text = pipeline_text()
        fields = pb.locate_fields(text)
        assert [(f.binding, f.activity) for f in fields] == [
            ("Notebook connection", "Import_Patterns_Data"),
            ("Notebook connection", "Validate_Patterns_Data"),
            ("Semantic model", "Refresh_Patterns_Semantic_Model"),
            ("Refresh connection", "Refresh_Patterns_Semantic_Model"),
        ]
        assert all(text[f.start:f.end] == f.value for f in fields)
        assert {f.binding: f.value for f in fields} == pb.BASELINE_VALUES

    def test_key_order_does_not_matter(self):
        doc = pipeline_doc()
        refresh = doc["properties"]["activities"][2]
        doc["properties"]["activities"][2] = {key: refresh[key] for key in reversed(list(refresh))}
        assert len(pb.locate_fields(json.dumps(doc, indent=2))) == 4

    @pytest.mark.parametrize("dump", [
        lambda doc: json.dumps(doc),
        lambda doc: json.dumps(doc, separators=(",", ":")),
        lambda doc: json.dumps(doc, indent="\t"),
        lambda doc: json.dumps(doc, indent=2).replace("\n", "\r\n"),
        lambda doc: json.dumps(doc, indent=2, ensure_ascii=False),
    ], ids=["default", "compact", "tabs", "crlf", "unicode"])
    def test_any_json_formatting(self, dump):
        assert len(pb.locate_fields(dump(pipeline_doc()))) == 4

    def test_ignores_lookalike_text_inside_strings(self):
        wait = {
            "name": "Wait",
            "type": "Wait",
            "description": '{"type": "PBISemanticModelRefresh", "datasetId": "'
                           + OTHER["Semantic model"] + '", "tail": "}',
            "typeProperties": {"waitTimeInSeconds": 1},
        }
        fields = pb.locate_fields(pipeline_text(extra=(wait,)))
        assert len(fields) == 4
        assert OTHER["Semantic model"] not in {f.value for f in fields}

    def test_accepts_a_single_refresh_nested_in_another_activity(self):
        loop = {
            "name": "Loop",
            "type": "ForEach",
            "typeProperties": {"activities": [
                refresh_activity("Nested", model=OTHER["Semantic model"], connection=OTHER["Refresh connection"]),
            ]},
        }
        doc = {"properties": {"activities": [
            notebook_activity("Run", NOTEBOOK_LOGICAL_IDS[0], OTHER["Notebook connection"]), loop,
        ]}}
        fields = pb.locate_fields(json.dumps(doc, indent=2))
        assert {f.activity for f in fields if f.binding == "Semantic model"} == {"Nested"}

    def test_counts_a_nested_refresh_as_a_second_one(self):
        loop = {
            "name": "Loop",
            "type": "ForEach",
            "typeProperties": {"activities": [
                refresh_activity("Nested", model=OTHER["Semantic model"], connection=OTHER["Refresh connection"]),
            ]},
        }
        with pytest.raises(pb.PipelineBindingError, match="found 2"):
            pb.locate_fields(pipeline_text(extra=(loop,)))

    def test_a_refresh_only_pipeline_is_fine(self):
        doc = {"properties": {"activities": [
            refresh_activity(model=OTHER["Semantic model"], connection=OTHER["Refresh connection"]),
        ]}}
        assert {f.binding for f in pb.locate_fields(json.dumps(doc))} == {"Semantic model", "Refresh connection"}

    def test_rejects_invalid_json(self):
        with pytest.raises(pb.PipelineBindingError, match="not valid JSON"):
            pb.locate_fields('{"properties": ')

    def test_requires_a_native_refresh(self):
        doc = pipeline_doc()
        del doc["properties"]["activities"][2]
        with pytest.raises(pb.PipelineBindingError, match="found 0"):
            pb.locate_fields(json.dumps(doc))

    def test_requires_exactly_one_native_refresh(self):
        second = refresh_activity("Second", model=OTHER["Semantic model"], connection=OTHER["Refresh connection"])
        with pytest.raises(pb.PipelineBindingError, match="found 2"):
            pb.locate_fields(pipeline_text(extra=(second,)))

    def test_requires_a_connection_on_every_notebook_activity(self):
        doc = pipeline_doc()
        del doc["properties"]["activities"][1]["externalReferences"]
        with pytest.raises(pb.PipelineBindingError, match=r"Validate_Patterns_Data.* has 0 connection values"):
            pb.locate_fields(json.dumps(doc))

    def test_refuses_an_expression_in_place_of_a_guid(self):
        text = pipeline_text().replace(pb.SEMANTIC_MODEL_BASELINE_ID, "@pipeline().parameters.model")
        with pytest.raises(pb.PipelineBindingError, match="not a GUID"):
            pb.locate_fields(text)

    def test_rejects_a_duplicate_key_in_one_activity(self):
        text = pipeline_text()
        needle = f'"connection": "{pb.REFRESH_CONNECTION_PLACEHOLDER_ID}"'
        assert needle in text
        with pytest.raises(pb.PipelineBindingError, match="has 2 connection values"):
            pb.locate_fields(text.replace(needle, f"{needle}, {needle}"))

    def test_reports_every_problem_together(self):
        doc = pipeline_doc()
        del doc["properties"]["activities"][2]
        del doc["properties"]["activities"][0]["externalReferences"]
        with pytest.raises(pb.PipelineBindingError) as exc:
            pb.locate_fields(json.dumps(doc))
        assert "found 0" in str(exc.value)
        assert "Import_Patterns_Data" in str(exc.value)
        assert "; " in str(exc.value)


# ── rewrite ───────────────────────────────────────────────────────────────

class TestRewrite:
    def test_sets_every_binding_and_changes_nothing_else(self):
        text = pipeline_text()
        assert pb.rewrite(text, OTHER) == swap_oracle(text, OTHER)

    def test_updates_every_notebook_activity(self):
        result = pb.rewrite(pipeline_text(), OTHER)
        activities = json.loads(result)["properties"]["activities"]
        assert [a["externalReferences"]["connection"] for a in activities[:2]] == [OTHER["Notebook connection"]] * 2

    def test_keeps_notebook_logical_ids_workspace_and_group(self):
        result = json.loads(pb.rewrite(pipeline_text(), OTHER))["properties"]["activities"]
        for notebook in result[:2]:
            assert notebook["typeProperties"]["workspaceId"] == pb.ZERO_GUID
            assert notebook["typeProperties"]["notebookId"] in NOTEBOOK_LOGICAL_IDS
        assert result[2]["typeProperties"]["groupId"] == DEV_WS_ID

    def test_round_trip_restores_the_exact_text(self):
        text = pipeline_text()
        assert pb.rewrite(pb.rewrite(text, OTHER), pb.BASELINE_VALUES) == text

    def test_is_idempotent(self):
        once = pb.rewrite(pipeline_text(), OTHER)
        assert pb.rewrite(once, OTHER) == once

    def test_replaces_whatever_value_is_there(self):
        stale = {"Semantic model": pb.ZERO_GUID, "Notebook connection": OTHER["Refresh connection"],
                 "Refresh connection": OTHER["Semantic model"]}
        assert pb.rewrite(pipeline_text(stale), pb.BASELINE_VALUES) == pipeline_text()

    def test_preserves_crlf_and_formatting_byte_for_byte(self):
        text = pipeline_text().replace("\n", "\r\n")
        assert pb.rewrite(text, OTHER) == swap_oracle(text, OTHER)

    def test_only_touches_the_bound_activity_types(self):
        copy = {
            "name": "Copy",
            "type": "Copy",
            "typeProperties": {"datasetId": BYSTANDER},
            "externalReferences": {"connection": BYSTANDER},
        }
        result = json.loads(pb.rewrite(pipeline_text(extra=(copy,)), OTHER))["properties"]["activities"]
        assert result[3]["typeProperties"]["datasetId"] == BYSTANDER
        assert result[3]["externalReferences"]["connection"] == BYSTANDER
        assert result[2]["typeProperties"]["datasetId"] == OTHER["Semantic model"]

    def test_notebook_and_refresh_connections_are_independent(self):
        values = {**pb.BASELINE_VALUES, "Notebook connection": OTHER["Notebook connection"]}
        result = json.loads(pb.rewrite(pipeline_text(), values))["properties"]["activities"]
        assert result[0]["externalReferences"]["connection"] == OTHER["Notebook connection"]
        assert result[2]["externalReferences"]["connection"] == pb.REFRESH_CONNECTION_PLACEHOLDER_ID

    @pytest.mark.parametrize("bad", ["", "not-a-guid", pb.ZERO_GUID + " "])
    def test_refuses_to_write_a_non_guid(self, bad: str):
        with pytest.raises(pb.PipelineBindingError, match="not a GUID"):
            pb.rewrite(pipeline_text(), {**OTHER, "Semantic model": bad})

    def test_refuses_a_missing_value(self):
        values = {k: v for k, v in OTHER.items() if k != "Refresh connection"}
        with pytest.raises(pb.PipelineBindingError, match="no value for Refresh connection"):
            pb.rewrite(pipeline_text(), values)

    def test_refuses_an_unsupported_shape(self):
        second = refresh_activity("Second", model=OTHER["Semantic model"], connection=OTHER["Refresh connection"])
        with pytest.raises(pb.PipelineBindingError, match="exactly one"):
            pb.rewrite(pipeline_text(extra=(second,)), OTHER)


class TestMismatches:
    def test_empty_when_every_field_matches(self):
        assert pb.mismatches(pipeline_text(), pb.BASELINE_VALUES) == []

    def test_describes_each_differing_field(self):
        problems = pb.mismatches(pipeline_text(OTHER), pb.BASELINE_VALUES)
        assert len(problems) == 4
        assert any(p.startswith("Semantic model (Refresh_Patterns_Semantic_Model)") for p in problems)
        assert sum(p.startswith("Notebook connection") for p in problems) == 2
        assert all("expected" in p for p in problems)

    def test_comparison_is_exact_so_ci_find_values_match(self):
        upper = pipeline_text().replace(pb.SEMANTIC_MODEL_BASELINE_ID, pb.SEMANTIC_MODEL_BASELINE_ID.upper())
        assert len(pb.mismatches(upper, pb.BASELINE_VALUES)) == 1

    def test_unsupported_shape_raises(self):
        with pytest.raises(pb.PipelineBindingError):
            pb.mismatches("{}", pb.BASELINE_VALUES)


class TestSourceGuard:
    def write_pipeline(self, directory: Path, text: str) -> Path:
        path = directory / "Patterns.DataPipeline" / "pipeline-content.json"
        path.parent.mkdir()
        path.write_text(text, encoding="utf-8")
        return path

    def test_accepts_exact_source_bindings(self, tmp_path: Path):
        self.write_pipeline(tmp_path, pipeline_text())
        pb.validate_pipeline_source(tmp_path, DEV_WS_ID, pb.BASELINE_VALUES)

    def test_checks_actual_refresh_workspace_not_substring_presence(self, tmp_path: Path):
        document = pipeline_doc()
        document["properties"]["activities"][2]["typeProperties"]["groupId"] = BYSTANDER
        document["description"] = DEV_WS_ID
        self.write_pipeline(tmp_path, json.dumps(document))
        with pytest.raises(pb.PipelineBindingError, match="Refresh workspace"):
            pb.validate_pipeline_source(tmp_path, DEV_WS_ID, pb.BASELINE_VALUES)

    @pytest.mark.parametrize("binding", list(OTHER))
    def test_rejects_stale_feature_binding(self, tmp_path: Path, binding: str):
        self.write_pipeline(tmp_path, pipeline_text({**pb.BASELINE_VALUES, binding: OTHER[binding]}))
        with pytest.raises(pb.PipelineBindingError, match=binding):
            pb.validate_pipeline_source(tmp_path, DEV_WS_ID, pb.BASELINE_VALUES)

    def test_rejects_uppercase_source_that_case_sensitive_replacement_would_miss(self, tmp_path: Path):
        self.write_pipeline(
            tmp_path, pipeline_text().replace(
                pb.SEMANTIC_MODEL_BASELINE_ID, pb.SEMANTIC_MODEL_BASELINE_ID.upper(),
            ),
        )
        with pytest.raises(pb.PipelineBindingError, match="Semantic model"):
            pb.validate_pipeline_source(tmp_path, DEV_WS_ID, pb.BASELINE_VALUES)

    def test_missing_owned_workspace_field_is_not_repaired_by_unrelated_group_id(self, tmp_path: Path):
        document = pipeline_doc()
        del document["properties"]["activities"][2]["typeProperties"]["groupId"]
        document["groupId"] = DEV_WS_ID
        self.write_pipeline(tmp_path, json.dumps(document))
        with pytest.raises(pb.PipelineBindingError, match="typeProperties.groupId"):
            pb.validate_pipeline_source(tmp_path, DEV_WS_ID, pb.BASELINE_VALUES)

    def test_workspace_rewrite_preserves_notebook_portable_markers_and_formatting(self):
        original = pipeline_text().replace("\n", "\r\n")
        updated = pb.rewrite(original, {**OTHER, "Refresh workspace": BYSTANDER})
        expected = swap_oracle(original, OTHER).replace(DEV_WS_ID, BYSTANDER)
        assert updated == expected
        assert updated.count(pb.ZERO_GUID) == 2

    def test_repository_without_pipeline_needs_no_bindings(self, tmp_path: Path):
        pb.validate_pipeline_source(tmp_path, DEV_WS_ID, {})


# ── Cross-file contracts ──────────────────────────────────────────────────

def as_list(value: object) -> list[str]:
    return [value] if isinstance(value, str) else list(value or [])


def parameter_rules(find_value: str) -> list[dict]:
    data = yaml.safe_load((FABRIC_DIR / "parameter.yml").read_text(encoding="utf-8")) or {}
    return [
        rule for rule in data.get("find_replace", [])
        if rule.get("find_value") == find_value and "DataPipeline" in as_list(rule.get("item_type"))
    ]


def bulk_rules(find: str) -> list[dict]:
    data = yaml.safe_load((FABRIC_DIR / "bulk-parameter.yml").read_text(encoding="utf-8")) or {}
    return [
        rule for rule in data.get("substitutions", [])
        if rule.get("find") == find and "DataPipeline" in as_list(rule.get("item_types"))
    ]


def dev_workspace_id() -> str:
    path = FABRIC_DIR / "Patterns_Variables.VariableLibrary" / "variables.json"
    variables = json.loads(path.read_text(encoding="utf-8"))["variables"]
    return next(v["value"] for v in variables if v["name"] == "target_workspace_id")


BINDING_IDS = [b["name"] for b in pb.PIPELINE_BINDINGS]


def model_item_name(token: str) -> str:
    match = re.fullmatch(r"\$items\.SemanticModel\.(.+)\.\$id", token)
    assert match, f"{token!r} must look like $items.SemanticModel.<name>.$id"
    return match.group(1)


def assert_names_a_repository_model(tokens: set[str], where: str) -> None:
    missing = sorted(n for n in map(model_item_name, tokens) if not (FABRIC_DIR / f"{n}.SemanticModel").is_dir())
    assert not missing, f"{where}: no data/fabric/<name>.SemanticModel item for {missing}"


class TestParameterFilesPinTheBaselines:
    """parameter.yml (fabric-cicd) and bulk-parameter.yml (raw REST) must replace the same baselines."""

    @pytest.fixture()
    def source_baselines(self) -> dict[str, str]:
        try:
            return pb.load_dev_bindings(FABRIC_DIR).values
        except pb.DevBindingsNotInitialized:
            return pb.BASELINE_VALUES

    @pytest.mark.parametrize("binding", pb.PIPELINE_BINDINGS, ids=BINDING_IDS)
    def test_parameter_yml_replaces_the_baseline_in_pipelines(self, binding, source_baselines):
        baseline = source_baselines[binding["name"]]
        rules = parameter_rules(baseline)
        assert rules, (
            f"data/fabric/parameter.yml needs a find_replace rule with find_value "
            f"'{baseline}' and item_type DataPipeline ({binding['name']} baseline)"
        )
        replacements = {value for rule in rules for value in rule["replace_value"].values()}
        if binding["deploy_env_key"]:
            assert replacements == {f"$ENV:{binding['deploy_env_key']}"}
        else:
            assert_names_a_repository_model(replacements, "parameter.yml")

    @pytest.mark.parametrize("binding", pb.PIPELINE_BINDINGS, ids=BINDING_IDS)
    def test_bulk_parameter_replaces_the_baseline_in_pipelines(self, binding, source_baselines):
        baseline = source_baselines[binding["name"]]
        rules = bulk_rules(baseline)
        assert rules, (
            f"data/fabric/bulk-parameter.yml needs a substitution with find '{baseline}' "
            f"and DataPipeline in item_types ({binding['name']} baseline)"
        )
        replacements = {rule["replace_with"] for rule in rules}
        if binding["deploy_env_key"]:
            assert replacements == {f"$ENV:{binding['deploy_env_key']}"}
        else:
            assert_names_a_repository_model(replacements, "bulk-parameter.yml")

    def test_both_files_replace_the_dev_workspace_in_pipelines(self):
        workspace = dev_workspace_id()
        assert parameter_rules(workspace), (
            f"data/fabric/parameter.yml needs a find_replace rule for the Dev workspace ID "
            f"'{workspace}' with item_type DataPipeline (the refresh activity's groupId)"
        )
        assert bulk_rules(workspace), (
            f"data/fabric/bulk-parameter.yml needs a substitution for the Dev workspace ID "
            f"'{workspace}' with DataPipeline in item_types (the refresh activity's groupId)"
        )


class TestEnvSampleDeclaresTheFeatureKeys:
    def test_every_binding_has_a_key_in_env_sample(self):
        sample = (REPO_ROOT / ".env.sample").read_text(encoding="utf-8")
        keys = set(re.findall(r"^([A-Z][A-Z0-9_]*)=", sample, re.MULTILINE))
        missing = {b["feature_env_key"] for b in pb.PIPELINE_BINDINGS} - keys
        assert not missing, f".env.sample is missing pipeline keys: {sorted(missing)}"


def committed_pipelines() -> list[Path]:
    return pb.pipeline_files(FABRIC_DIR)


def activities_of(node: object, kinds: tuple[str, ...]) -> list[dict]:
    found: list[dict] = []
    if isinstance(node, dict):
        if node.get("type") in kinds:
            found.append(node)
        for child in node.values():
            found.extend(activities_of(child, kinds))
    elif isinstance(node, list):
        for child in node:
            found.extend(activities_of(child, kinds))
    return found


LOAD_AND_VALIDATE = ("Import_Patterns_Data", "Validate_Patterns_Data")
MODEL_NAME = "Patterns_Semantic_Model"


def platform_items() -> dict[str, dict]:
    """Every item's .platform, keyed by its folder name."""
    return {
        path.parent.name: json.loads(path.read_text(encoding="utf-8"))
        for path in sorted(FABRIC_DIR.glob("*/.platform"))
    }


def logical_id(folder: str) -> str:
    return platform_items()[folder]["config"]["logicalId"]


def plan_groups() -> dict[str, dict]:
    path = FABRIC_DIR / "DeploymentPlan.DeploymentPlan" / "plan.yml"
    if not path.is_file():
        return {}
    return {group["name"]: group for group in yaml.safe_load(path.read_text(encoding="utf-8"))["groups"]}


def plan_predecessors(groups: dict[str, dict], logical: str) -> set[str]:
    """LogicalIds of every group the plan publishes before the group holding ``logical``."""
    pending = [name for name, group in groups.items() if group["logicalId"] == logical]
    seen: set[str] = set()
    while pending:
        for dependency in groups[pending.pop()].get("dependsOn", []):
            if dependency["groupName"] not in seen:
                seen.add(dependency["groupName"])
                pending.append(dependency["groupName"])
    return {groups[name]["logicalId"] for name in seen}


class TestItemMetadata:
    """An item exported through the API carries the zero logicalId until a real one is assigned."""

    def test_every_item_has_a_real_unique_logical_id(self):
        ids = {folder: item["config"]["logicalId"] for folder, item in platform_items().items()}
        bad = sorted(folder for folder, value in ids.items() if not pb.is_guid(value) or value == pb.ZERO_GUID)
        assert not bad, f"logicalId must be a non-zero GUID in: {bad}"
        assert len(set(ids.values())) == len(ids), "logicalIds must be unique across items"

    def test_folder_names_match_the_metadata(self):
        for folder, item in platform_items().items():
            assert folder == f"{item['metadata']['displayName']}.{item['metadata']['type']}"

    @pytest.mark.parametrize("name", LOAD_AND_VALIDATE)
    def test_load_and_validate_notebooks_have_platform_metadata(self, name: str):
        assert f"{name}.Notebook" in platform_items(), f"data/fabric/{name}.Notebook/.platform is missing"


@pytest.mark.skipif(not committed_pipelines(), reason="no DataPipeline is committed yet")
class TestCommittedPipeline:
    """Value-agnostic: holds on a feature branch (feature values) and on dev (baselines)."""

    @pytest.mark.parametrize("path", committed_pipelines(), ids=lambda p: p.parent.name)
    def test_has_the_current_template_shape(self, path: Path):
        doc = json.loads(path.read_text(encoding="utf-8"))
        notebooks = activities_of(doc, (pb.NOTEBOOK_ACTIVITY_TYPE,))
        refreshes = activities_of(doc, (pb.REFRESH_ACTIVITY_TYPE,))
        assert (len(notebooks), len(refreshes)) == (2, 1), (
            f"{path.parent.name}: expected 2 notebook activities and 1 native refresh, "
            f"found {len(notebooks)} and {len(refreshes)}; update this test with the template"
        )

    @pytest.mark.parametrize("path", committed_pipelines(), ids=lambda p: p.parent.name)
    def test_bound_fields_are_supported_whatever_the_swap_state(self, path: Path):
        fields = pb.locate_fields(path.read_text(encoding="utf-8"))
        assert {f.binding for f in fields} == set(pb.BASELINE_VALUES)

    @pytest.mark.parametrize("path", committed_pipelines(), ids=lambda p: p.parent.name)
    def test_notebook_activities_reference_the_load_and_validate_notebooks(self, path: Path):
        doc = json.loads(path.read_text(encoding="utf-8"))
        notebooks = activities_of(doc, (pb.NOTEBOOK_ACTIVITY_TYPE,))
        for notebook in notebooks:
            assert notebook["typeProperties"]["workspaceId"] == pb.ZERO_GUID, (
                f"{notebook['name']}: workspaceId must stay the zero GUID so the reference is portable"
            )
        expected = sorted(logical_id(f"{name}.Notebook") for name in LOAD_AND_VALIDATE)
        assert sorted(n["typeProperties"]["notebookId"] for n in notebooks) == expected, (
            "notebookId must be the logicalId from each notebook's .platform (not an item ID)"
        )

    @pytest.mark.parametrize("path", committed_pipelines(), ids=lambda p: p.parent.name)
    def test_plan_publishes_everything_the_pipeline_binds_first(self, path: Path):
        pipeline_id = logical_id(path.parent.name)
        groups = plan_groups()
        if pipeline_id not in {g["logicalId"] for g in groups.values()}:
            pytest.skip("the pipeline is not in the plan, so it publishes with the remaining items")
        doc = json.loads(path.read_text(encoding="utf-8"))
        required = {n["typeProperties"]["notebookId"] for n in activities_of(doc, (pb.NOTEBOOK_ACTIVITY_TYPE,))}
        required.add(logical_id(f"{MODEL_NAME}.SemanticModel"))
        required.update(
            logical_id(f"{variable['libraryName']}.VariableLibrary")
            for variable in doc["properties"].get("libraryVariables", {}).values()
        )
        before = plan_predecessors(groups, pipeline_id)
        assert required <= before, (
            f"plan.yml must publish these before the pipeline's group: "
            f"{sorted(required - before)} (add them to its dependsOn chain)"
        )


PIPELINE_PATH = FABRIC_DIR / "Patterns_Load_Validate_And_Refresh.DataPipeline" / "pipeline-content.json"


def notebook_parameters(name: str) -> dict[str, str]:
    """Parameters a notebook declares in its PARAMETERS CELL, as the pipeline's Fabric type names."""
    text = (FABRIC_DIR / f"{name}.Notebook" / "notebook-content.py").read_text(encoding="utf-8")
    cell = text.split("# PARAMETERS CELL ********************", 1)[1].split("# METADATA ********************", 1)[0]
    fabric_types = {int: "int", str: "string", bool: "bool", float: "float"}
    return {
        node.targets[0].id: fabric_types[type(ast.literal_eval(node.value))]
        for node in ast.parse(cell).body
        if isinstance(node, ast.Assign)
    }


@pytest.mark.skipif(not PIPELINE_PATH.is_file(), reason="the pipeline is not committed yet")
class TestValidateActivityBindings:
    """What the pipeline feeds the validation notebook, and where those values come from."""

    @pytest.fixture()
    def pipeline(self) -> dict:
        return json.loads(PIPELINE_PATH.read_text(encoding="utf-8"))["properties"]

    @pytest.fixture()
    def parameters(self, pipeline: dict) -> dict:
        notebook_id = logical_id("Validate_Patterns_Data.Notebook")
        activity = next(
            a for a in activities_of(pipeline, (pb.NOTEBOOK_ACTIVITY_TYPE,))
            if a["typeProperties"]["notebookId"] == notebook_id
        )
        return activity["typeProperties"]["parameters"]

    def test_passes_exactly_the_parameters_the_notebook_declares(self, parameters: dict):
        passed = {name: parameter["type"] for name, parameter in parameters.items()}
        assert passed == notebook_parameters("Validate_Patterns_Data")

    def test_every_value_comes_from_a_declared_pipeline_parameter_or_library_variable(
        self, pipeline: dict, parameters: dict,
    ):
        for name, parameter in parameters.items():
            expression = parameter["value"]["value"]
            match = re.fullmatch(r"@pipeline\(\)\.(parameters|libraryVariables)\.(\w+)", expression)
            assert match, f"{name}: unexpected source {expression!r}"
            assert match.group(2) in pipeline[match.group(1)], f"{name}: {expression} is not declared on the pipeline"

    def test_run_label_is_an_independent_string_defaulting_to_manual(self, pipeline: dict):
        assert pipeline["parameters"]["run_label"] == {"type": "string", "defaultValue": "manual"}

    def test_threshold_is_a_positive_integer_library_variable_everywhere(self, pipeline: dict):
        bound = [v for v in pipeline["libraryVariables"].values() if v["variableName"] == "minimum_patient_count"]
        assert len(bound) == 1
        assert (bound[0]["type"], bound[0]["libraryName"]) == ("Int", "Patterns_Variables")
        library = FABRIC_DIR / f"{bound[0]['libraryName']}.VariableLibrary"
        variable = next(
            v for v in json.loads((library / "variables.json").read_text(encoding="utf-8"))["variables"]
            if v["name"] == "minimum_patient_count"
        )
        assert variable["type"] == "Integer"
        values = [variable["value"]] + [
            override["value"]
            for value_set in sorted((library / "valueSets").glob("*.json"))
            for override in json.loads(value_set.read_text(encoding="utf-8")).get("variableOverrides", [])
            if override["name"] == "minimum_patient_count"
        ]
        assert all(type(value) is int and value > 0 for value in values), (
            f"the validation notebook rejects non-positive thresholds; found {values}"
        )
