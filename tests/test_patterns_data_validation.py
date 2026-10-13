"""Unit tests and contracts for the Validate_Patterns_Data notebook.

The notebook keeps its decisions in one stdlib-only cell and its Spark reads in
another, so these tests execute the real notebook source without installing
Spark. Fixtures shaped like the seed data (5 patients, 3 doctors, 6
appointments) live only here: the notebook itself must not pin exact counts.
"""

from __future__ import annotations

import ast
import json
import re
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import Mock, call
from uuid import UUID

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
FABRIC_DIR = REPO_ROOT / "data" / "fabric"
NOTEBOOK_PATH = FABRIC_DIR / "Validate_Patterns_Data.Notebook" / "notebook-content.py"
LOADER_PATH = FABRIC_DIR / "Import_Patterns_Data.Notebook" / "notebook-content.py"

CELL_HEADER = re.compile(r"^# (CELL|MARKDOWN|PARAMETERS CELL|METADATA) \*+\s*$")
SEED_ROW_COUNTS = {"patients": 5, "doctors": 3, "appointments": 6}
PATIENT_REFERENCE = "appointments.patient_id->patients.patient_id"
DOCTOR_REFERENCE = "appointments.doctor_id->doctors.doctor_id"

# Validation only reads: no writes, raw SQL, REST or credential helpers, or exit().
FORBIDDEN_NAMES = {
    "write", "writeTo", "saveAsTable", "insertInto", "sql", "refreshTable", "refreshByPath",
    "createTable", "dropTable", "exit", "credentials", "getToken", "getSecret",
    "mssparkutils", "requests", "sempy",
    "sempy_labs", "delta", "DeltaTable", "azure", "urllib", "subprocess",
}

# The validation notebook has no attached Lakehouse; it reads Variable Library
# configuration. Review any additional META fields for internal metadata.
ALLOWED_FILE_META = {"kernel_info", "dependencies"}
ALLOWED_CELL_META = {"language", "language_group"}

# Spark simpleString names for the types Import_Patterns_Data declares.
LOADER_TYPES = {"IntegerType": "int", "StringType": "string", "TimestampType": "timestamp", "DateType": "date"}


def read_cells(path: Path) -> list[tuple[str, str]]:
    """Split a Fabric notebook source file into (kind, source) pairs, dropping META blocks."""
    cells: list[tuple[str, list[str]]] = []
    in_source = False
    for line in path.read_text(encoding="utf-8").splitlines():
        header = CELL_HEADER.match(line)
        if header is None:
            if in_source:
                cells[-1][1].append(line)
            continue
        in_source = header.group(1) != "METADATA"
        if in_source:
            cells.append((header.group(1), []))
    return [(kind, "\n".join(lines).strip()) for kind, lines in cells]


def find_cell(cells: list[tuple[str, str]], kind: str, marker: str = "") -> str:
    matches = [source for cell_kind, source in cells if cell_kind == kind and source.startswith(marker)]
    assert len(matches) == 1, f"expected exactly one {kind} starting with {marker!r}, found {len(matches)}"
    return matches[0]


def read_meta_blocks(path: Path) -> list[dict[str, Any]]:
    """Return every `# META {...}` block as JSON: the file block first, then one per cell."""
    blocks: list[list[str]] = []
    in_meta = False
    for line in path.read_text(encoding="utf-8").splitlines():
        header = CELL_HEADER.match(line)
        if header is not None:
            in_meta = header.group(1) == "METADATA"
            if in_meta:
                blocks.append([])
        elif in_meta and line.startswith("# META "):
            blocks[-1].append(line[len("# META "):])
    return [json.loads("\n".join(block)) for block in blocks]


def parameter_defaults(source: str) -> dict[str, object]:
    return {
        target.id: ast.literal_eval(node.value)
        for node in ast.parse(source).body
        if isinstance(node, ast.Assign)
        for target in node.targets
        if isinstance(target, ast.Name)
    }


def imported_modules(tree: ast.AST) -> set[str]:
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules |= {alias.name.split(".")[0] for alias in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.add(node.module.split(".")[0])
    return modules


def names_used(tree: ast.AST) -> set[str]:
    return {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)}


def attributes_used(tree: ast.AST) -> set[str]:
    return {node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)}


def function_names(source: str) -> set[str]:
    return {node.name for node in ast.walk(ast.parse(source)) if isinstance(node, ast.FunctionDef)}


def loader_tree() -> ast.Module:
    return ast.parse(LOADER_PATH.read_text(encoding="utf-8"))


def loader_schemas() -> dict[str, dict[str, str]]:
    """Read the StructField declarations of Import_Patterns_Data without importing Spark."""
    schemas: dict[str, dict[str, str]] = {}
    for node in ast.walk(loader_tree()):
        if not (isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name)):
            continue
        variable = node.targets[0].id
        if not variable.endswith("_schema"):
            continue
        columns: dict[str, str] = {}
        for call in ast.walk(node.value):
            if not (isinstance(call, ast.Call) and isinstance(call.func, ast.Name) and call.func.id == "StructField"):
                continue
            spark_type = call.args[1]
            assert isinstance(spark_type, ast.Call) and isinstance(spark_type.func, ast.Name)
            if spark_type.func.id not in LOADER_TYPES:
                pytest.fail(f"Map the loader's {spark_type.func.id} to its simpleString name in LOADER_TYPES")
            columns[ast.literal_eval(call.args[0])] = LOADER_TYPES[spark_type.func.id]
        schemas[variable.removesuffix("_schema")] = columns
    return schemas


def loader_tables() -> set[str]:
    return {
        ast.literal_eval(node.value)
        for node in ast.walk(loader_tree())
        if isinstance(node, ast.Assign)
        and isinstance(node.targets[0], ast.Name)
        and node.targets[0].id.endswith("_TABLE")
    }


def seed_facts(notebook: dict[str, Any], row_counts: dict[str, int] | None = None) -> dict[str, Any]:
    counts = row_counts or SEED_ROW_COUNTS
    tables = {
        table: {
            "columns": dict(columns),
            "row_count": counts[table],
            "null_counts": {notebook["KEY_COLUMNS"][table]: 0},
            "duplicate_counts": {notebook["KEY_COLUMNS"][table]: 0},
        }
        for table, columns in notebook["EXPECTED_SCHEMAS"].items()
    }
    orphans = {notebook["reference_name"](*reference): 0 for reference in notebook["REFERENCES"]}
    return {"tables": tables, "orphan_counts": orphans}


@pytest.fixture(scope="module")
def cells() -> list[tuple[str, str]]:
    return read_cells(NOTEBOOK_PATH)


@pytest.fixture(scope="module")
def pure_source(cells: list[tuple[str, str]]) -> str:
    return find_cell(cells, "CELL", "# Pure validation logic")


@pytest.fixture(scope="module")
def spark_source(cells: list[tuple[str, str]]) -> str:
    return find_cell(cells, "CELL", "# Spark boundary")


@pytest.fixture(scope="module")
def run_source(cells: list[tuple[str, str]]) -> str:
    return find_cell(cells, "CELL", "# Run")


@pytest.fixture(scope="module")
def notebook(pure_source: str) -> dict[str, Any]:
    namespace: dict[str, Any] = {}
    exec(compile(pure_source, str(NOTEBOOK_PATH), "exec"), namespace)
    return namespace


@pytest.fixture
def facts(notebook: dict[str, Any]) -> dict[str, Any]:
    return seed_facts(notebook)


def evaluate(notebook: dict[str, Any], facts: dict[str, Any], minimum: int = 5) -> list[str]:
    return notebook["evaluate_facts"](facts, minimum)


# ----- Data checks -----------------------------------------------------------


def test_seed_shaped_facts_pass(notebook: dict[str, Any], facts: dict[str, Any]) -> None:
    assert evaluate(notebook, facts) == []


def test_exact_seed_counts_are_not_required(notebook: dict[str, Any]) -> None:
    larger = seed_facts(notebook, {"patients": 50, "doctors": 0, "appointments": 1000})
    assert evaluate(notebook, larger) == []


def test_minimum_patient_count_boundary(notebook: dict[str, Any], facts: dict[str, Any]) -> None:
    assert evaluate(notebook, facts, minimum=5) == []
    assert evaluate(notebook, facts, minimum=6) == ["patients: 5 row(s), at least 6 required"]


@pytest.mark.parametrize(
    ("table", "column", "actual", "message"),
    [
        ("patients", "date_of_birth", "date", "patients.date_of_birth: expected timestamp, found date"),
        ("appointments", "appointment_date", "string", "appointments.appointment_date: expected timestamp, found string"),
        ("patients", "patient_id", "bigint", "patients.patient_id: expected int, found bigint"),
        ("doctors", "specialty", None, "doctors.specialty: column is missing"),
        # A missing key column is reported once; its key and reference checks are skipped.
        ("patients", "patient_id", None, "patients.patient_id: column is missing"),
    ],
)
def test_schema_problems_are_reported(
    notebook: dict[str, Any], facts: dict[str, Any], table: str, column: str, actual: str | None, message: str
) -> None:
    columns = facts["tables"][table]["columns"]
    if actual is None:
        del columns[column]
    else:
        columns[column] = actual
    assert evaluate(notebook, facts) == [message]


def test_extra_columns_are_allowed_but_named_in_the_summary(notebook: dict[str, Any], facts: dict[str, Any]) -> None:
    facts["tables"]["patients"]["columns"]["nickname"] = "string"
    assert evaluate(notebook, facts) == []
    assert "patients: 5 row(s); unvalidated columns: nickname" in notebook["summarize_facts"](facts)


def test_missing_table_is_reported_once(notebook: dict[str, Any], facts: dict[str, Any]) -> None:
    del facts["tables"]["doctors"]
    assert evaluate(notebook, facts) == ["doctors: table not found"]


def test_null_and_duplicate_keys_are_reported(notebook: dict[str, Any], facts: dict[str, Any]) -> None:
    facts["tables"]["patients"]["null_counts"]["patient_id"] = 1
    facts["tables"]["appointments"]["duplicate_counts"]["appointment_id"] = 2
    assert evaluate(notebook, facts) == [
        "patients.patient_id: 1 null value(s)",
        "appointments.appointment_id: 2 duplicate value(s)",
    ]


def test_orphaned_references_are_reported(notebook: dict[str, Any], facts: dict[str, Any]) -> None:
    facts["orphan_counts"][PATIENT_REFERENCE] = 1
    facts["orphan_counts"][DOCTOR_REFERENCE] = 2
    assert evaluate(notebook, facts) == [
        f"{PATIENT_REFERENCE}: 1 row(s) have no matching parent",
        f"{DOCTOR_REFERENCE}: 2 row(s) have no matching parent",
    ]


def test_counts_that_were_not_collected_fail_instead_of_passing(
    notebook: dict[str, Any], facts: dict[str, Any]
) -> None:
    del facts["tables"]["patients"]["null_counts"]["patient_id"]
    del facts["tables"]["doctors"]["duplicate_counts"]["doctor_id"]
    del facts["orphan_counts"][PATIENT_REFERENCE]
    assert evaluate(notebook, facts) == [
        "patients.patient_id: null count was not collected",
        "doctors.doctor_id: duplicate count was not collected",
        f"{PATIENT_REFERENCE}: orphan count was not collected",
    ]


def test_every_failed_check_is_reported_together(notebook: dict[str, Any], facts: dict[str, Any]) -> None:
    facts["tables"]["patients"]["columns"]["date_of_birth"] = "date"
    facts["tables"]["patients"]["null_counts"]["patient_id"] = 1
    facts["orphan_counts"][DOCTOR_REFERENCE] = 1
    assert len(evaluate(notebook, facts, minimum=6)) == 4


# ----- Parameters ------------------------------------------------------------


@pytest.mark.parametrize(
    ("count", "label"),
    [(5, "manual"), (1, "a"), (2, "Test-38069561086"), (3, "a" * 64), (4, "run_1.2-x")],
)
def test_valid_parameters_are_returned_unchanged(notebook: dict[str, Any], count: int, label: str) -> None:
    assert notebook["validate_parameters"](count, label) == (count, label)


@pytest.mark.parametrize("value", [0, -1, True, False, "5", 5.0, None, [5]])
def test_minimum_patient_count_must_be_a_positive_integer(notebook: dict[str, Any], value: object) -> None:
    with pytest.raises(notebook["PatternsDataValidationError"], match="minimum_patient_count"):
        notebook["validate_parameters"](value, "manual")


@pytest.mark.parametrize(
    "value", ["", " ", "has space", "-leading", "a" * 65, "semi;colon", "new\nline", "trailing\n", None, 5]
)
def test_run_label_must_be_a_short_safe_string(notebook: dict[str, Any], value: object) -> None:
    with pytest.raises(notebook["PatternsDataValidationError"], match="run_label"):
        notebook["validate_parameters"](5, value)


def test_all_parameter_problems_are_reported_together(notebook: dict[str, Any]) -> None:
    with pytest.raises(notebook["PatternsDataValidationError"], match="minimum_patient_count.*run_label"):
        notebook["validate_parameters"](0, "")


def test_parameter_cell_holds_only_placeholders_that_are_rejected(
    cells: list[tuple[str, str]], notebook: dict[str, Any]
) -> None:
    defaults = parameter_defaults(find_cell(cells, "PARAMETERS CELL"))
    assert defaults == {"minimum_patient_count": 0, "run_label": ""}
    with pytest.raises(notebook["PatternsDataValidationError"]):
        notebook["validate_parameters"](**defaults)


def test_lakehouse_path_matches_demo_pattern(notebook: dict[str, Any]) -> None:
    workspace = "6df0254d-0ae4-444a-9128-6524e0b69e47"
    lakehouse = "02c2df5f-daca-4318-b000-77358ce11a7b"
    expected = f"abfss://{workspace}@onelake.dfs.fabric.microsoft.com/{lakehouse}/Tables/dbo"
    assert notebook["lakehouse_tables_path"](workspace, lakehouse) == expected
    assert notebook["lakehouse_tables_path"](UUID(workspace), UUID(lakehouse)) == expected
    assert notebook["lakehouse_tables_path"](workspace.upper(), lakehouse.upper()) == expected


@pytest.mark.parametrize("field", ["workspace", "lakehouse"])
@pytest.mark.parametrize("invalid", [
    "", None, 123, "invalid", "00000000-0000-0000-0000-000000000000",
    " 6df0254d-0ae4-444a-9128-6524e0b69e47",
])
def test_lakehouse_path_rejects_invalid_library_ids(
    notebook: dict[str, Any], field: str, invalid: object,
) -> None:
    values: dict[str, object] = {
        "workspace": "6df0254d-0ae4-444a-9128-6524e0b69e47",
        "lakehouse": "02c2df5f-daca-4318-b000-77358ce11a7b",
    }
    values[field] = invalid
    with pytest.raises(notebook["PatternsDataValidationError"], match=f"target_{field}_id"):
        notebook["lakehouse_tables_path"](values["workspace"], values["lakehouse"])


def test_collect_facts_reads_all_delta_paths_without_catalog_binding(
    notebook: dict[str, Any], spark_source: str, facts: dict[str, Any],
) -> None:
    tree = ast.parse(spark_source)
    collector = next(
        node for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "collect_facts"
    )
    spark = Mock()
    dataframes = [Mock(name=table) for table in notebook["EXPECTED_SCHEMAS"]]
    spark.read.format.return_value.load.side_effect = dataframes
    namespace = {
        **notebook,
        "SparkSession": object,
        "read_table_facts": Mock(side_effect=list(facts["tables"].values())),
        "count_orphans": Mock(return_value=0),
    }
    exec(compile(ast.Module(body=[collector], type_ignores=[]), str(NOTEBOOK_PATH), "exec"), namespace)
    root = notebook["lakehouse_tables_path"](
        "6df0254d-0ae4-444a-9128-6524e0b69e47", "02c2df5f-daca-4318-b000-77358ce11a7b",
    )
    assert namespace["collect_facts"](spark, root) == facts
    assert spark.read.format.call_args_list == [call("delta")] * 3
    assert spark.read.format.return_value.load.call_args_list == [
        call(f"{root}/{table}") for table in notebook["EXPECTED_SCHEMAS"]
    ]
    spark.table.assert_not_called()
    assert not spark.catalog.mock_calls
    assert namespace["count_orphans"].call_count == 2


def test_run_resolves_target_from_library_and_uses_passed_threshold(
    notebook: dict[str, Any], run_source: str, facts: dict[str, Any],
) -> None:
    workspace = "6df0254d-0ae4-444a-9128-6524e0b69e47"
    lakehouse = "02c2df5f-daca-4318-b000-77358ce11a7b"
    library = SimpleNamespace(target_workspace_id=workspace, target_lakehouse_id=lakehouse)
    get_library = Mock(return_value=library)
    collector = Mock(return_value=facts)
    spark = Mock()
    namespace = {
        **notebook,
        "minimum_patient_count": 5,
        "run_label": "unit-test",
        "notebookutils": SimpleNamespace(variableLibrary=SimpleNamespace(getLibrary=get_library)),
        "collect_facts": collector,
        "spark": spark,
    }
    exec(compile(run_source, str(NOTEBOOK_PATH), "exec"), namespace)
    get_library.assert_called_once_with("Patterns_Variables")
    collector.assert_called_once_with(spark, notebook["lakehouse_tables_path"](workspace, lakehouse))


# ----- Notebook contracts ----------------------------------------------------


def test_pure_cell_uses_only_the_standard_library(pure_source: str) -> None:
    tree = ast.parse(pure_source)
    assert imported_modules(tree) <= set(sys.stdlib_module_names)
    assert {"spark", "F"}.isdisjoint(names_used(tree))


def test_decisions_and_spark_reads_live_in_separate_cells(pure_source: str, spark_source: str) -> None:
    pure_functions = function_names(pure_source)
    spark_functions = function_names(spark_source)
    assert {"validate_parameters", "evaluate_facts", "summarize_facts"} <= pure_functions
    assert {"collect_facts", "read_table_facts", "count_orphans"} <= spark_functions
    assert pure_functions.isdisjoint(spark_functions)
    assert "pyspark" in imported_modules(ast.parse(spark_source))


def test_notebook_is_read_only() -> None:
    tree = ast.parse(NOTEBOOK_PATH.read_text(encoding="utf-8"))
    used = names_used(tree) | attributes_used(tree) | imported_modules(tree)
    assert sorted(used & FORBIDDEN_NAMES) == []


def test_run_cell_fails_the_notebook_instead_of_swallowing_or_exiting(run_source: str) -> None:
    tree = ast.parse(run_source)
    raises = [ast.unparse(node) for node in ast.walk(tree) if isinstance(node, ast.Raise)]
    assert len(raises) == 1 and "PatternsDataValidationError" in raises[0]
    assert not any(isinstance(node, ast.Try) for node in ast.walk(tree))


def test_keys_and_references_match_the_expected_schemas(notebook: dict[str, Any]) -> None:
    schemas = notebook["EXPECTED_SCHEMAS"]
    assert set(notebook["KEY_COLUMNS"]) == set(schemas)
    assert notebook["PATIENTS_TABLE"] in schemas
    for table, key in notebook["KEY_COLUMNS"].items():
        assert schemas[table][key] == "int"
    for child, child_column, parent, parent_column in notebook["REFERENCES"]:
        assert schemas[child][child_column] == schemas[parent][parent_column]


def test_date_columns_are_validated_as_timestamps(notebook: dict[str, Any]) -> None:
    schemas = notebook["EXPECTED_SCHEMAS"]
    assert schemas["patients"]["date_of_birth"] == "timestamp"
    assert schemas["appointments"]["appointment_date"] == "timestamp"


def test_expected_schemas_match_the_loader(notebook: dict[str, Any]) -> None:
    assert set(notebook["EXPECTED_SCHEMAS"]) == loader_tables()
    assert notebook["EXPECTED_SCHEMAS"] == loader_schemas()


def test_cell_markers_use_the_exact_fabric_format() -> None:
    markers = [
        line
        for line in NOTEBOOK_PATH.read_text(encoding="utf-8").splitlines()
        if line.startswith(("# CELL", "# MARKDOWN", "# PARAMETERS CELL", "# METADATA"))
    ]
    assert markers, "no Fabric cell markers found"
    assert all(re.fullmatch(r"# (CELL|MARKDOWN|PARAMETERS CELL|METADATA) \*{20}", marker) for marker in markers)


def test_metadata_has_no_attached_lakehouse() -> None:
    file_meta, *cell_meta = read_meta_blocks(NOTEBOOK_PATH)
    dependencies = file_meta.get("dependencies", {})
    assert set(file_meta) <= ALLOWED_FILE_META
    assert dependencies == {}
    assert all(set(block) <= ALLOWED_CELL_META for block in cell_meta)


def test_notebookutils_access_is_limited_to_reading_variable_library() -> None:
    tree = ast.parse(NOTEBOOK_PATH.read_text(encoding="utf-8"))
    accesses = [
        node.attr for node in ast.walk(tree)
        if isinstance(node, ast.Attribute)
        and isinstance(node.value, ast.Name) and node.value.id == "notebookutils"
    ]
    assert accesses == ["variableLibrary"]
