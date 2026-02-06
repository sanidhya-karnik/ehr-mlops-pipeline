"""
=============================================================================
DAG 2: Model Training & Validation
=============================================================================

Trains the readmission prediction model on dbt-generated features,
validates performance against threshold, and triggers deployment
if the model passes.

Triggered by: 01_data_validation
Triggers: 03_model_deployment on success.

Schedule: None (triggered by upstream DAG)
"""

from datetime import datetime, timedelta
from airflow import DAG
from airflow.operators.python import PythonOperator, BranchPythonOperator
from airflow.operators.empty import EmptyOperator
from airflow.operators.trigger_dagrun import TriggerDagRunOperator
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
    "execution_timeout": timedelta(hours=2),
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
    "model_type": "xgboost",  # Options: logistic, random_forest, xgboost
    "min_auc_threshold": 0.70,
    "min_samples": 1000,
}


# =============================================================================
# Task Functions
# =============================================================================

def check_training_data(**context):
    """Verify feature table has enough samples for training."""
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

    print(f"Feature table has {count} samples")
    context["ti"].xcom_push(key="sample_count", value=count)

    if count >= CONFIG["min_samples"]:
        return "train_model"
    else:
        return "skip_training"


def train_model(**context):
    """Train the readmission prediction model."""
    import sys
    sys.path.append("/opt/airflow/src")

    from training.train import ModelTrainer

    trainer = ModelTrainer(
        db_host=CONFIG["db_host"],
        db_name=CONFIG["db_name"],
        db_user=os.getenv("DB_USER", "mimic"),
        db_password=os.getenv("DB_PASSWORD", "mimic_password"),
    )

    # Train model
    metrics = trainer.train(model_type=CONFIG["model_type"])

    # Save model to S3
    model_path = trainer.save_model(
        s3_endpoint=CONFIG["s3_endpoint"],
        bucket=CONFIG["s3_bucket_models"],
        model_name=CONFIG["model_name"],
    )

    # Push metrics to XCom for downstream tasks
    context["ti"].xcom_push(key="model_metrics", value=metrics)
    context["ti"].xcom_push(key="model_path", value=model_path)

    print(f"Model trained with metrics: {metrics}")
    print(f"Model saved to: {model_path}")

    return metrics


def validate_model(**context):
    """Check if model meets deployment criteria."""
    metrics = context["ti"].xcom_pull(key="model_metrics", task_ids="train_model")

    auc = metrics.get("auc_roc", 0)
    print(f"Model AUC: {auc}, Threshold: {CONFIG['min_auc_threshold']}")

    if auc >= CONFIG["min_auc_threshold"]:
        return "trigger_deployment"
    else:
        return "model_rejected"


def notify_rejection(**context):
    """Log model rejection details."""
    metrics = context["ti"].xcom_pull(key="model_metrics", task_ids="train_model")
    print(
        f"Model REJECTED - AUC {metrics.get('auc_roc', 'N/A')} "
        f"below threshold {CONFIG['min_auc_threshold']}"
    )


def notify_insufficient_data(**context):
    """Log insufficient data details."""
    count = context["ti"].xcom_pull(key="sample_count", task_ids="check_training_data")
    print(
        f"Training SKIPPED - only {count} samples, "
        f"need {CONFIG['min_samples']}"
    )


# =============================================================================
# DAG Definition
# =============================================================================

with DAG(
    dag_id="02_model_training",
    default_args=default_args,
    description="Train and validate readmission prediction model",
    schedule_interval=None,  # Triggered by 01_data_validation
    start_date=datetime(2024, 1, 1),
    catchup=False,
    tags=["mlops", "healthcare", "readmission", "training"],
    doc_md=__doc__,
) as dag:

    start = EmptyOperator(task_id="start")

    # Check data sufficiency
    check_data = BranchPythonOperator(
        task_id="check_training_data",
        python_callable=check_training_data,
    )

    # Happy path: train → validate → trigger deploy
    train = PythonOperator(
        task_id="train_model",
        python_callable=train_model,
        execution_timeout=timedelta(hours=1),
    )

    validate = BranchPythonOperator(
        task_id="validate_model",
        python_callable=validate_model,
    )

    trigger_deploy = TriggerDagRunOperator(
        task_id="trigger_deployment",
        trigger_dag_id="03_model_deployment",
        conf={
            "model_name": CONFIG["model_name"],
        },
        wait_for_completion=False,
        poke_interval=30,
    )

    # Rejection paths
    rejected = PythonOperator(
        task_id="model_rejected",
        python_callable=notify_rejection,
    )

    skip_training = PythonOperator(
        task_id="skip_training",
        python_callable=notify_insufficient_data,
    )

    end = EmptyOperator(
        task_id="end",
        trigger_rule=TriggerRule.NONE_FAILED_MIN_ONE_SUCCESS,
    )

    # Dependencies
    start >> check_data

    check_data >> train >> validate
    check_data >> skip_training >> end

    validate >> trigger_deploy >> end
    validate >> rejected >> end
