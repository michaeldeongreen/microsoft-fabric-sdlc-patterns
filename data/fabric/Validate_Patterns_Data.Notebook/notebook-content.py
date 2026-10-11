# Fabric notebook source

# METADATA ********************

# META {
# META   "kernel_info": {
# META     "name": "synapse_pyspark"
# META   },
# META   "dependencies": {}
# META }

# PARAMETERS CELL ********************

# Supplied by the pipeline. The placeholders are rejected, so a missing binding fails the run.
minimum_patient_count = 0
run_label = ""

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# CELL ********************

# Pure validation logic (stdlib only; unit-tested outside Fabric)
import re
from typing import Any
from uuid import UUID

# Facts are plain dicts built by collect_facts() in the Spark cell:
#   {"tables": {table: {"columns": {name: spark_type}, "row_count": int,
#                       "null_counts": {key: int}, "duplicate_counts": {key: int}}},
#    "orphan_counts": {"child.column->parent.column": int}}

PATIENTS_TABLE = "patients"
VARIABLE_LIBRARY_NAME = "Patterns_Variables"

# Column types as Spark's DataType.simpleString() reports them. Extra columns are
# reported but allowed. The unit tests keep this in sync with Import_Patterns_Data.
EXPECTED_SCHEMAS: dict[str, dict[str, str]] = {
    "patients": {
        "patient_id": "int",
        "first_name": "string",
        "last_name": "string",
        "date_of_birth": "timestamp",
        "gender": "string",
        "phone_number": "string",
        "email": "string",
    },
    "doctors": {
        "doctor_id": "int",
        "first_name": "string",
        "last_name": "string",
        "specialty": "string",
        "phone_number": "string",
        "email": "string",
    },
    "appointments": {
        "appointment_id": "int",
        "patient_id": "int",
        "doctor_id": "int",
        "appointment_date": "timestamp",
        "reason": "string",
        "status": "string",
    },
}

# One key per table; it must be non-null and unique.
KEY_COLUMNS: dict[str, str] = {
    "patients": "patient_id",
    "doctors": "doctor_id",
    "appointments": "appointment_id",
}

# (child table, child column, parent table, parent column)
REFERENCES: list[tuple[str, str, str, str]] = [
    ("appointments", "patient_id", "patients", "patient_id"),
    ("appointments", "doctor_id", "doctors", "doctor_id"),
]

RUN_LABEL_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}")


class PatternsDataValidationError(Exception):
    """The parameters or the Patterns lakehouse tables failed validation."""


def reference_name(child: str, child_column: str, parent: str, parent_column: str) -> str:
    return f"{child}.{child_column}->{parent}.{parent_column}"


def validate_parameters(minimum_patient_count: object, run_label: object) -> tuple[int, str]:
    """Return the validated parameters; invalid inputs are rejected, never replaced by defaults."""
    problems: list[str] = []
    count = 0
    if (
        isinstance(minimum_patient_count, int)
        and not isinstance(minimum_patient_count, bool)
        and minimum_patient_count >= 1
    ):
        count = minimum_patient_count
    else:
        problems.append(f"minimum_patient_count must be a positive integer, got {minimum_patient_count!r:.80}")
    label = ""
    if isinstance(run_label, str) and RUN_LABEL_PATTERN.fullmatch(run_label):
        label = run_label
    else:
        problems.append(f"run_label must match {RUN_LABEL_PATTERN.pattern}, got {run_label!r:.80}")
    if problems:
        raise PatternsDataValidationError("; ".join(problems))
    return count, label


def lakehouse_tables_path(workspace_id: object, lakehouse_id: object) -> str:
    """Build the OneLake path from validated active Variable Library IDs."""
    ids: list[str] = []
    for value, name in ((workspace_id, "target_workspace_id"), (lakehouse_id, "target_lakehouse_id")):
        if not isinstance(value, (str, UUID)):
            raise PatternsDataValidationError(f"{name} must be a nonzero GUID.")
        text = str(value)
        try:
            guid = UUID(text)
        except ValueError as exc:
            raise PatternsDataValidationError(f"{name} must be a nonzero GUID.") from exc
        if guid.int == 0 or text.lower() != str(guid):
            raise PatternsDataValidationError(f"{name} must be a nonzero GUID in hyphenated form.")
        ids.append(str(guid))
    return f"abfss://{ids[0]}@onelake.dfs.fabric.microsoft.com/{ids[1]}/Tables/dbo"


def _schema_failures(table: str, columns: dict[str, str]) -> list[str]:
    failures: list[str] = []
    for column, expected in EXPECTED_SCHEMAS[table].items():
        actual = columns.get(column)
        if actual is None:
            failures.append(f"{table}.{column}: column is missing")
        elif actual != expected:
            failures.append(f"{table}.{column}: expected {expected}, found {actual}")
    return failures


def _key_failures(table: str, table_facts: dict[str, Any]) -> list[str]:
    key = KEY_COLUMNS[table]
    if key not in table_facts["columns"]:
        return []  # already reported as a missing column
    failures: list[str] = []
    for problem, counts in (("null", table_facts["null_counts"]), ("duplicate", table_facts["duplicate_counts"])):
        count = counts.get(key)
        if count is None:
            failures.append(f"{table}.{key}: {problem} count was not collected")
        elif count:
            failures.append(f"{table}.{key}: {count} {problem} value(s)")
    return failures


def _has_column(tables: dict[str, Any], table: str, column: str) -> bool:
    return column in tables.get(table, {}).get("columns", {})


def _reference_failures(facts: dict[str, Any]) -> list[str]:
    failures: list[str] = []
    for child, child_column, parent, parent_column in REFERENCES:
        if not (_has_column(facts["tables"], child, child_column) and _has_column(facts["tables"], parent, parent_column)):
            continue  # already reported as a missing table or column
        name = reference_name(child, child_column, parent, parent_column)
        orphans = facts["orphan_counts"].get(name)
        if orphans is None:
            failures.append(f"{name}: orphan count was not collected")
        elif orphans:
            failures.append(f"{name}: {orphans} row(s) have no matching parent")
    return failures


def evaluate_facts(facts: dict[str, Any], minimum_patient_count: int) -> list[str]:
    """Return one message per failed check; an empty list means the data is valid."""
    tables = facts["tables"]
    failures: list[str] = []
    for table in EXPECTED_SCHEMAS:
        table_facts = tables.get(table)
        if table_facts is None:
            failures.append(f"{table}: table not found")
            continue
        failures += _schema_failures(table, table_facts["columns"])
        failures += _key_failures(table, table_facts)
    patients = tables.get(PATIENTS_TABLE)
    if patients is not None and patients["row_count"] < minimum_patient_count:
        failures.append(f"{PATIENTS_TABLE}: {patients['row_count']} row(s), at least {minimum_patient_count} required")
    return failures + _reference_failures(facts)


def summarize_facts(facts: dict[str, Any]) -> list[str]:
    """One line per table, naming any columns the validation does not check."""
    lines: list[str] = []
    for table, table_facts in facts["tables"].items():
        unvalidated = sorted(set(table_facts["columns"]) - set(EXPECTED_SCHEMAS.get(table, {})))
        suffix = f"; unvalidated columns: {', '.join(unvalidated)}" if unvalidated else ""
        lines.append(f"{table}: {table_facts['row_count']} row(s){suffix}")
    return lines

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# CELL ********************

# Spark boundary: read-only aggregates that feed evaluate_facts (no writes)
from pyspark.sql import DataFrame, SparkSession, functions as F


def read_table_facts(df: DataFrame, key: str) -> dict[str, Any]:
    columns = {field.name: field.dataType.simpleString() for field in df.schema.fields}
    facts: dict[str, Any] = {
        "columns": columns,
        "row_count": df.count(),
        "null_counts": {},
        "duplicate_counts": {},
    }
    if key in columns:
        key_column = F.col(key)
        counts = df.agg(
            F.count(F.when(key_column.isNull(), 1)).alias("nulls"),
            (F.count(key_column) - F.count_distinct(key_column)).alias("duplicates"),
        ).first()
        facts["null_counts"][key] = counts["nulls"]
        facts["duplicate_counts"][key] = counts["duplicates"]
    return facts


def count_orphans(child: DataFrame, child_column: str, parent: DataFrame, parent_column: str) -> int:
    parent_keys = parent.select(F.col(parent_column).alias("parent_key")).distinct()
    return (
        child.where(F.col(child_column).isNotNull())
        .join(parent_keys, F.col(child_column) == F.col("parent_key"), "left_anti")
        .count()
    )


def collect_facts(spark: SparkSession, tables_path: str) -> dict[str, Any]:
    dataframes = {
        table: spark.read.format("delta").load(f"{tables_path}/{table}")
        for table in EXPECTED_SCHEMAS
    }
    facts: dict[str, Any] = {
        "tables": {table: read_table_facts(df, KEY_COLUMNS[table]) for table, df in dataframes.items()},
        "orphan_counts": {},
    }
    for child, child_column, parent, parent_column in REFERENCES:
        if _has_column(facts["tables"], child, child_column) and _has_column(facts["tables"], parent, parent_column):
            name = reference_name(child, child_column, parent, parent_column)
            facts["orphan_counts"][name] = count_orphans(
                dataframes[child], child_column, dataframes[parent], parent_column
            )
    return facts

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# CELL ********************

# Run: an uncaught error fails this notebook, so the pipeline skips the model refresh
threshold, label = validate_parameters(minimum_patient_count, run_label)
print(f"Validating Patterns data (run_label={label}, minimum_patient_count={threshold})")

variable_library = notebookutils.variableLibrary.getLibrary(VARIABLE_LIBRARY_NAME)
target_workspace_id = variable_library.target_workspace_id
target_lakehouse_id = variable_library.target_lakehouse_id
tables_path = lakehouse_tables_path(target_workspace_id, target_lakehouse_id)
print(f"Variable Library: {VARIABLE_LIBRARY_NAME}")
print(f"Workspace ID: {target_workspace_id}")
print(f"Lakehouse ID: {target_lakehouse_id}")

facts = collect_facts(spark, tables_path)
for line in summarize_facts(facts):
    print(line)

failures = evaluate_facts(facts, threshold)
if failures:
    raise PatternsDataValidationError(f"{len(failures)} validation check(s) failed: " + "; ".join(failures))
print("All validation checks passed.")

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }
