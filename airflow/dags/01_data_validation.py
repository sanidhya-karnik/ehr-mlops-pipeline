"""
=============================================================================
DAG 1: Data Validation & Feature Engineering
=============================================================================

Validates source data in PostgreSQL and runs dbt transformations
to build the feature table for model training.

Triggers: 02_model_training on success.

Schedule: Daily at 2 AM
"""

from datetime import datetime, timedelta
from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.operators.empty import EmptyOperator
from airflow.operators.trigger_dagrun import TriggerDagRunOperator
from airflow.utils.trigger_rule import TriggerRule
import os


# =============================================================================
# Default Arguments
# =============================================================================

default_args = {
    "owner": "mlops",
    "depends_on_past": False,
    "email_on_failure": False,
    "email_on_retry": False,
    "retries": 2,
    "retry_delay": timedelta(minutes=5),
    "execution_timeout": timedelta(hours=2),
}


# =============================================================================
# Configuration
# =============================================================================

CONFIG = {
    "db_host": os.getenv("DB_HOST", "postgres"),
    "db_name": os.getenv("DB_NAME", "mimic"),
}


# =============================================================================
# Task Functions
# =============================================================================

def notify_failure(**context):
    """Log pipeline failure details."""
    print("Data validation pipeline FAILED - check logs for details")
    # In production, send alerts via Slack, PagerDuty, email, etc.


def validate_source_data(**context):
    """Check that source data exists and is valid."""
    import psycopg2

    conn = psycopg2.connect(
        host=CONFIG["db_host"],
        database=CONFIG["db_name"],
        user=os.getenv("DB_USER", "mimic"),
        password=os.getenv("DB_PASSWORD", "mimic_password"),
    )

    cur = conn.cursor()

    tables = ["patients", "admissions", "diagnoses_icd"]
    results = {}

    for table in tables:
        try:
            cur.execute(f"SELECT COUNT(*) FROM mimic_hosp.{table}")
            count = cur.fetchone()[0]
            results[table] = count
            print(f"Table {table}: {count} rows")
        except Exception as e:
            print(f"Table {table} not found or error: {e}")
            results[table] = 0

    conn.close()

    context["ti"].xcom_push(key="source_validation", value=results)

    if all(count > 0 for count in results.values()):
        print("Source data validation passed!")
        return True
    else:
        raise ValueError("Source data validation failed - missing tables")


def run_dbt_transformations(**context):
    """Execute dbt models to create feature tables."""
    import subprocess

    dbt_project_dir = "/opt/airflow/dbt"

    # Run dbt
    result = subprocess.run(
        ["dbt", "run", "--profiles-dir", dbt_project_dir, "--project-dir", dbt_project_dir],
        capture_output=True,
        text=True,
    )

    print(f"dbt stdout: {result.stdout}")
    print(f"dbt stderr: {result.stderr}")

    if result.returncode != 0:
        raise Exception(f"dbt run failed: {result.stderr}")

    # Run dbt tests
    test_result = subprocess.run(
        ["dbt", "test", "--profiles-dir", dbt_project_dir, "--project-dir", dbt_project_dir],
        capture_output=True,
        text=True,
    )

    print(f"dbt test stdout: {test_result.stdout}")

    if test_result.returncode != 0:
        print(f"Warning: Some dbt tests failed: {test_result.stderr}")

    return True


def check_feature_table(**context):
    """Verify feature table was created and has data after dbt run."""
    import psycopg2

    conn = psycopg2.connect(
        host=CONFIG["db_host"],
        database=CONFIG["db_name"],
        user=os.getenv("DB_USER", "mimic"),
        password=os.getenv("DB_PASSWORD", "mimic_password"),
    )

    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM public_marts.fct_readmission_features")
    count = cur.fetchone()[0]
    conn.close()

    print(f"Feature table has {count} rows after dbt run")
    context["ti"].xcom_push(key="feature_row_count", value=count)

    if count == 0:
        raise ValueError("Feature table is empty after dbt run")

    return count


# =============================================================================
# DAG Definition
# =============================================================================

with DAG(
    dag_id="01_data_validation",
    default_args=default_args,
    description="Validate source data and run dbt feature engineering",
    schedule_interval="0 2 * * *",
    start_date=datetime(2024, 1, 1),
    catchup=False,
    tags=["mlops", "healthcare", "readmission", "data"],
    doc_md=__doc__,
) as dag:

    start = EmptyOperator(task_id="start")

    validate_data = PythonOperator(
        task_id="validate_source_data",
        python_callable=validate_source_data,
    )

    dbt_run = PythonOperator(
        task_id="run_dbt",
        python_callable=run_dbt_transformations,
        execution_timeout=timedelta(hours=1),
    )

    check_features = PythonOperator(
        task_id="check_feature_table",
        python_callable=check_feature_table,
    )

    trigger_training = TriggerDagRunOperator(
        task_id="trigger_training",
        trigger_dag_id="02_model_training",
        wait_for_completion=False,
        poke_interval=30,
    )

    failure = PythonOperator(
        task_id="notify_failure",
        python_callable=notify_failure,
        trigger_rule=TriggerRule.ONE_FAILED,
    )

    end = EmptyOperator(
        task_id="end",
        trigger_rule=TriggerRule.NONE_FAILED_MIN_ONE_SUCCESS,
    )

    # Dependencies
    start >> validate_data >> dbt_run >> check_features >> trigger_training >> end
    [validate_data, dbt_run, check_features] >> failure >> end
