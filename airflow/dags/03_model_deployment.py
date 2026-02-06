"""
=============================================================================
DAG 3: Model Deployment
=============================================================================

Deploys a validated model to the serving infrastructure and
registers it in the model registry.

Triggered by: 02_model_training (after validation passes)

Schedule: None (triggered by upstream DAG)
"""

from datetime import datetime, timedelta
from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.operators.empty import EmptyOperator
from airflow.utils.trigger_rule import TriggerRule
import os
import json


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
    "execution_timeout": timedelta(hours=1),
}


# =============================================================================
# Configuration
# =============================================================================

CONFIG = {
    "s3_endpoint": os.getenv("S3_ENDPOINT_URL", "http://minio:9000"),
    "s3_bucket_models": os.getenv("S3_BUCKET_MODELS", "mimic-models"),
    "db_host": os.getenv("DB_HOST", "postgres"),
    "db_name": os.getenv("DB_NAME", "mimic"),
    "model_name": "readmission_model",
}


# =============================================================================
# Task Functions
# =============================================================================

def get_latest_model(**context):
    """Fetch the latest trained model info from S3."""
    import boto3

    s3 = boto3.client(
        "s3",
        endpoint_url=CONFIG["s3_endpoint"],
        aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID", "minioadmin"),
        aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY", "minioadmin"),
    )

    # List model artifacts and find latest
    prefix = f"models/{CONFIG['model_name']}/"
    response = s3.list_objects_v2(
        Bucket=CONFIG["s3_bucket_models"],
        Prefix=prefix,
    )

    if "Contents" not in response or not response["Contents"]:
        raise ValueError(f"No model artifacts found in s3://{CONFIG['s3_bucket_models']}/{prefix}")

    # Sort by last modified, get latest
    latest = sorted(response["Contents"], key=lambda x: x["LastModified"], reverse=True)[0]
    model_path = f"s3://{CONFIG['s3_bucket_models']}/{latest['Key']}"

    print(f"Latest model artifact: {model_path}")
    context["ti"].xcom_push(key="model_path", value=model_path)

    # Try to load metrics from companion metadata file
    metrics_key = latest["Key"].replace(".joblib", "_metrics.json").replace(".pkl", "_metrics.json")
    try:
        metrics_obj = s3.get_object(Bucket=CONFIG["s3_bucket_models"], Key=metrics_key)
        metrics = json.loads(metrics_obj["Body"].read().decode("utf-8"))
        context["ti"].xcom_push(key="model_metrics", value=metrics)
        print(f"Model metrics: {metrics}")
    except Exception as e:
        print(f"No metrics file found ({e}), continuing without metrics")
        context["ti"].xcom_push(key="model_metrics", value={})

    return model_path


def register_model(**context):
    """Register model version in the model registry."""
    import psycopg2

    model_path = context["ti"].xcom_pull(key="model_path", task_ids="get_latest_model")
    metrics = context["ti"].xcom_pull(key="model_metrics", task_ids="get_latest_model")

    version = datetime.now().strftime("%Y%m%d_%H%M%S")

    conn = psycopg2.connect(
        host=CONFIG["db_host"],
        database=CONFIG["db_name"],
        user=os.getenv("DB_USER", "mimic"),
        password=os.getenv("DB_PASSWORD", "mimic_password"),
    )

    cur = conn.cursor()

    # Register new version
    cur.execute(
        """
        INSERT INTO model_registry (model_name, model_version, model_path, metrics, status, deployed_at)
        VALUES (%s, %s, %s, %s, 'staged', NOW())
        ON CONFLICT (model_name, model_version) DO UPDATE SET
            status = 'staged',
            deployed_at = NOW()
        """,
        (CONFIG["model_name"], version, model_path, json.dumps(metrics)),
    )

    conn.commit()
    conn.close()

    print(f"Model version {version} registered as 'staged'")
    context["ti"].xcom_push(key="model_version", value=version)

    return version


def deploy_model(**context):
    """Promote staged model to deployed and archive previous versions."""
    import psycopg2

    version = context["ti"].xcom_pull(key="model_version", task_ids="register_model")

    conn = psycopg2.connect(
        host=CONFIG["db_host"],
        database=CONFIG["db_name"],
        user=os.getenv("DB_USER", "mimic"),
        password=os.getenv("DB_PASSWORD", "mimic_password"),
    )

    cur = conn.cursor()

    # Archive previous deployed versions
    cur.execute(
        """
        UPDATE model_registry
        SET status = 'archived'
        WHERE model_name = %s AND status = 'deployed'
        """,
        (CONFIG["model_name"],),
    )

    # Promote new version
    cur.execute(
        """
        UPDATE model_registry
        SET status = 'deployed', deployed_at = NOW()
        WHERE model_name = %s AND model_version = %s
        """,
        (CONFIG["model_name"], version),
    )

    conn.commit()
    conn.close()

    print(f"Model version {version} deployed! Previous versions archived.")

    return version


def notify_success(**context):
    """Log deployment success."""
    version = context["ti"].xcom_pull(key="model_version", task_ids="register_model")
    metrics = context["ti"].xcom_pull(key="model_metrics", task_ids="get_latest_model")
    print(f"Deployment complete! Version: {version}, Metrics: {metrics}")


def notify_failure(**context):
    """Log deployment failure."""
    print("Deployment FAILED - check logs for details")


# =============================================================================
# DAG Definition
# =============================================================================

with DAG(
    dag_id="03_model_deployment",
    default_args=default_args,
    description="Deploy validated model to serving infrastructure",
    schedule_interval=None,  # Triggered by 02_model_training
    start_date=datetime(2024, 1, 1),
    catchup=False,
    tags=["mlops", "healthcare", "readmission", "deployment"],
    doc_md=__doc__,
) as dag:

    start = EmptyOperator(task_id="start")

    get_model = PythonOperator(
        task_id="get_latest_model",
        python_callable=get_latest_model,
    )

    register = PythonOperator(
        task_id="register_model",
        python_callable=register_model,
    )

    deploy = PythonOperator(
        task_id="deploy_model",
        python_callable=deploy_model,
    )

    success = PythonOperator(
        task_id="notify_success",
        python_callable=notify_success,
        trigger_rule=TriggerRule.ALL_SUCCESS,
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
    start >> get_model >> register >> deploy >> success >> end
    deploy >> failure >> end
