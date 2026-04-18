# Fabric notebook source

# METADATA ********************

# META {
# META   "kernel_info": {
# META     "name": "synapse_pyspark"
# META   },
# META   "dependencies": {}
# META }

# CELL ********************

# Fabric notebook source

# CELL ********************
VARIABLE_LIBRARY_NAME = "Patterns_Variables"

variable_library = notebookutils.variableLibrary.getLibrary(VARIABLE_LIBRARY_NAME)

target_workspace_id = variable_library.target_workspace_id
target_lakehouse_id = variable_library.target_lakehouse_id
target_table_name = "patients"

# Build ABFS path
full_path = f"abfss://{target_workspace_id}@onelake.dfs.fabric.microsoft.com/{target_lakehouse_id}/Tables/dbo/{target_table_name}"

# Load the table
patients_df = spark.read.format("delta").load(full_path)
patients_df.show()

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }
