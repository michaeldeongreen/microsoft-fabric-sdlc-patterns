# Fabric notebook source

# METADATA ********************

# META {
# META   "kernel_info": {
# META     "name": "synapse_pyspark"
# META   },
# META   "dependencies": {
# META     "lakehouse": {
# META       "default_lakehouse": "7694ebac-deb9-4a40-a846-0782b36b3bda",
# META       "default_lakehouse_name": "FabulousLakehouse",
# META       "default_lakehouse_workspace_id": "ca5566de-3273-4656-a4ad-8d300301f6b2"
# META     }
# META   }
# META }

# CELL ********************

# Import required libraries for schema definition
from pyspark.sql.types import StructType, StructField, IntegerType, StringType, DateType, TimestampType
from datetime import date, datetime

# Define table names for the Healthcare industry domain
# These 3 tables form a relational model: patients and doctors linked through appointments
PATIENTS_TABLE = "patients"
DOCTORS_TABLE = "doctors"
APPOINTMENTS_TABLE = "appointments"

# -------------------------------------------------------
# Define schemas explicitly — reused for both table creation and data insertion
# to ensure type consistency and avoid merge field errors
# -------------------------------------------------------

patients_schema = StructType([
    StructField("patient_id", IntegerType(), False),
    StructField("first_name", StringType(), False),
    StructField("last_name", StringType(), False),
    StructField("date_of_birth", TimestampType(), True),
    StructField("gender", StringType(), True),
    StructField("phone_number", StringType(), True),
    StructField("email", StringType(), True)
])

doctors_schema = StructType([
    StructField("doctor_id", IntegerType(), False),
    StructField("first_name", StringType(), False),
    StructField("last_name", StringType(), False),
    StructField("specialty", StringType(), True),
    StructField("phone_number", StringType(), True),
    StructField("email", StringType(), True)
])

appointments_schema = StructType([
    StructField("appointment_id", IntegerType(), False),
    StructField("patient_id", IntegerType(), False),
    StructField("doctor_id", IntegerType(), False),
    StructField("appointment_date", TimestampType(), False),
    StructField("reason", StringType(), True),
    StructField("status", StringType(), True)
])

# -------------------------------------------------------
# Insert data using saveAsTable which writes Delta files AND registers
# tables in the Lakehouse metastore. The default Lakehouse is attached
# via the notebook's META dependencies block, so simple table names resolve
# correctly. Per Fabric docs: df.write.mode("overwrite").format("delta").saveAsTable(name)
# -------------------------------------------------------

patients_data = [
    (1, "Alice", "Johnson", datetime(1985, 3, 15), "Female", "555-0101", "alice.johnson@email.com"),
    (2, "Bob", "Smith", datetime(1990, 7, 22), "Male", "555-0102", "bob.smith@email.com"),
    (3, "Carol", "Williams", datetime(1978, 11, 8), "Female", "555-0103", "carol.williams@email.com"),
    (4, "David", "Brown", datetime(2001, 1, 30), "Male", "555-0104", "david.brown@email.com"),
    (5, "Eva", "Davis", datetime(1995, 6, 12), "Female", "555-0105", "eva.davis@email.com")
]
patients_df = spark.createDataFrame(patients_data, patients_schema)
patients_df.write.format("delta").mode("overwrite").saveAsTable(PATIENTS_TABLE)
print(f"Inserted {patients_df.count()} rows into '{PATIENTS_TABLE}'.")

doctors_data = [
    (1, "Sarah", "Mitchell", "Cardiology", "555-0201", "sarah.mitchell@hospital.com"),
    (2, "James", "Anderson", "Neurology", "555-0202", "james.anderson@hospital.com"),
    (3, "Emily", "Thompson", "Pediatrics", "555-0203", "emily.thompson@hospital.com")
]
doctors_df = spark.createDataFrame(doctors_data, doctors_schema)
doctors_df.write.format("delta").mode("overwrite").saveAsTable(DOCTORS_TABLE)
print(f"Inserted {doctors_df.count()} rows into '{DOCTORS_TABLE}'.")

appointments_data = [
    (1, 1, 1, datetime(2026, 4, 10), "Annual checkup", "Completed"),
    (2, 2, 2, datetime(2026, 4, 11), "Headache consultation", "Completed"),
    (3, 3, 3, datetime(2026, 4, 12), "Child wellness visit", "Scheduled"),
    (4, 4, 1, datetime(2026, 4, 15), "Chest pain follow-up", "Scheduled"),
    (5, 5, 2, datetime(2026, 4, 18), "Neurological evaluation", "Scheduled"),
    (6, 1, 3, datetime(2026, 4, 20), "Flu symptoms", "Scheduled")
]
appointments_df = spark.createDataFrame(appointments_data, appointments_schema)
appointments_df.write.format("delta").mode("overwrite").saveAsTable(APPOINTMENTS_TABLE)
print(f"Inserted {appointments_df.count()} rows into '{APPOINTMENTS_TABLE}'.")

print("All tables created and data loaded successfully.")



# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }
