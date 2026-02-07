"""
Airflow DAG: Lakehouse batch pipeline
Bronze -> Silver -> Gold with data quality checks.
Scheduled hourly. Submits Spark jobs to the cluster.
"""

import os
from datetime import datetime, timedelta

from airflow import DAG
from airflow.operators.python import PythonOperator, BranchPythonOperator
from airflow.operators.bash import BashOperator
from airflow.operators.empty import EmptyOperator

# --------------- Configuration ---------------
SPARK_MASTER = "local[*]"
LAKEHOUSE_PATH = os.getenv("LAKEHOUSE_PATH", "/data/lakehouse")
SPARK_JOBS_PATH = "/opt/spark-jobs"

PG_HOST = os.getenv("POSTGRES_HOST", "postgres")
PG_PORT = os.getenv("POSTGRES_PORT", "5432")
PG_DB = os.getenv("POSTGRES_DB", "serving")
PG_USER = os.getenv("POSTGRES_USER", "platform")
PG_PASSWORD = os.getenv("POSTGRES_PASSWORD", "platform123")

DELTA_PACKAGES = "io.delta:delta-spark_2.12:3.1.0"
DELTA_CONF = (
    "--conf spark.sql.extensions=io.delta.sql.DeltaSparkSessionExtension "
    "--conf spark.sql.catalog.spark_catalog=org.apache.spark.sql.delta.catalog.DeltaCatalog "
    "--conf spark.driver.extraJavaOptions=-Divy.cache.dir=/tmp/.ivy2"
)

default_args = {
    "owner": "data-platform",
    "depends_on_past": False,
    "email_on_failure": False,
    "retries": 2,
    "retry_delay": timedelta(minutes=2),
}


def check_bronze_exists(**kwargs):
    """Check if Bronze Delta table exists and has data."""
    bronze_path = f"{LAKEHOUSE_PATH}/bronze/user_events"
    delta_log = f"{bronze_path}/_delta_log"
    if os.path.exists(delta_log):
        # Check for at least one parquet file
        for root, dirs, files in os.walk(bronze_path):
            for f in files:
                if f.endswith(".parquet"):
                    print(f"Bronze table exists with data at {bronze_path}")
                    return "run_bronze_to_silver"
    print(f"Bronze table not found or empty at {bronze_path}")
    return "skip_pipeline"


def check_row_counts(**kwargs):
    """Basic data quality: verify Silver and Gold have data."""
    import psycopg2

    conn = psycopg2.connect(
        host=PG_HOST, port=PG_PORT, database=PG_DB,
        user=PG_USER, password=PG_PASSWORD,
    )
    cur = conn.cursor()

    checks = [
        ("gold.daily_active_users", "dau_count"),
        ("gold.events_per_source_daily", "event_count"),
        ("gold.conversion_rate_daily", "conversion_rate"),
    ]

    all_ok = True
    for table, col in checks:
        try:
            cur.execute(f"SELECT COUNT(*) FROM {table}")
            row_count = cur.fetchone()[0]
            print(f"  {table}: {row_count} rows")
            if row_count == 0:
                print(f"  WARNING: {table} is empty!")
                all_ok = False

            # Null check on key column
            cur.execute(f"SELECT COUNT(*) FROM {table} WHERE {col} IS NULL")
            null_count = cur.fetchone()[0]
            if null_count > 0:
                print(f"  WARNING: {table}.{col} has {null_count} NULLs")
                all_ok = False
        except Exception as e:
            print(f"  ERROR checking {table}: {e}")
            all_ok = False

    cur.close()
    conn.close()

    if not all_ok:
        print("Data quality issues detected (non-fatal)")

    # Also check Delta table existence
    for layer in ["silver/user_events", "gold/fact_events", "gold/kpi_dau"]:
        path = f"{LAKEHOUSE_PATH}/{layer}/_delta_log"
        exists = os.path.exists(path)
        print(f"  Delta {layer}: {'EXISTS' if exists else 'MISSING'}")

    return all_ok


with DAG(
    dag_id="lakehouse_batch_pipeline",
    default_args=default_args,
    description="Bronze -> Silver -> Gold batch pipeline with quality checks",
    schedule_interval="@hourly",
    start_date=datetime(2024, 1, 1),
    catchup=False,
    tags=["lakehouse", "batch", "delta-lake"],
) as dag:

    check_bronze = BranchPythonOperator(
        task_id="check_bronze_exists",
        python_callable=check_bronze_exists,
    )

    skip_pipeline = EmptyOperator(
        task_id="skip_pipeline",
    )

    bronze_to_silver = BashOperator(
        task_id="run_bronze_to_silver",
        bash_command=(
            f"spark-submit "
            f"--master {SPARK_MASTER} "
            f"--packages {DELTA_PACKAGES} "
            f"{DELTA_CONF} "
            f"{SPARK_JOBS_PATH}/spark_bronze_to_silver.py"
        ),
        env={
            "LAKEHOUSE_PATH": LAKEHOUSE_PATH,
            "JAVA_HOME": "/usr/lib/jvm/java-17-openjdk-amd64",
            "SPARK_HOME": "/opt/spark",
            "PATH": "/opt/spark/bin:/usr/local/bin:/usr/bin:/bin",
        },
    )

    silver_to_gold = BashOperator(
        task_id="run_silver_to_gold",
        bash_command=(
            f"spark-submit "
            f"--master {SPARK_MASTER} "
            f"--packages {DELTA_PACKAGES} "
            f"--jars /opt/spark/extra-jars/postgresql-42.7.1.jar "
            f"{DELTA_CONF} "
            f"{SPARK_JOBS_PATH}/spark_silver_to_gold.py"
        ),
        env={
            "LAKEHOUSE_PATH": LAKEHOUSE_PATH,
            "POSTGRES_HOST": PG_HOST,
            "POSTGRES_PORT": PG_PORT,
            "POSTGRES_DB": PG_DB,
            "POSTGRES_USER": PG_USER,
            "POSTGRES_PASSWORD": PG_PASSWORD,
            "JAVA_HOME": "/usr/lib/jvm/java-17-openjdk-amd64",
            "SPARK_HOME": "/opt/spark",
            "PATH": "/opt/spark/bin:/usr/local/bin:/usr/bin:/bin",
        },
    )

    quality_checks = PythonOperator(
        task_id="data_quality_checks",
        python_callable=check_row_counts,
        trigger_rule="all_success",
    )

    pipeline_done = EmptyOperator(
        task_id="pipeline_done",
        trigger_rule="none_failed_min_one_success",
    )

    # DAG structure
    check_bronze >> [bronze_to_silver, skip_pipeline]
    bronze_to_silver >> silver_to_gold >> quality_checks >> pipeline_done
    skip_pipeline >> pipeline_done
