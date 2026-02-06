"""
Common utilities shared across training and serving modules.
"""

import os
from dataclasses import dataclass


@dataclass
class DatabaseConfig:
    """Database connection configuration."""
    
    host: str = os.getenv("DB_HOST", "localhost")
    port: int = int(os.getenv("DB_PORT", "5432"))
    name: str = os.getenv("DB_NAME", "mimic")
    user: str = os.getenv("DB_USER", "mimic")
    password: str = os.getenv("DB_PASSWORD", "mimic_password")
    
    @property
    def connection_string(self) -> str:
        """Return PostgreSQL connection string."""
        return f"postgresql://{self.user}:{self.password}@{self.host}:{self.port}/{self.name}"


@dataclass
class S3Config:
    """S3/MinIO connection configuration."""
    
    endpoint_url: str = os.getenv("S3_ENDPOINT_URL", "http://localhost:9000")
    access_key_id: str = os.getenv("AWS_ACCESS_KEY_ID", "minioadmin")
    secret_access_key: str = os.getenv("AWS_SECRET_ACCESS_KEY", "minioadmin")
    bucket_raw: str = os.getenv("S3_BUCKET_RAW", "mimic-raw")
    bucket_processed: str = os.getenv("S3_BUCKET_PROCESSED", "mimic-processed")
    bucket_models: str = os.getenv("S3_BUCKET_MODELS", "mimic-models")


# Feature schema for validation
FEATURE_SCHEMA = {
    "numeric": [
        "age", "los_days", "prior_admits_6mo", "prior_admits_12mo",
        "prior_ed_visits_6mo", "avg_prior_los", "diagnosis_count",
        "charlson_index", "discharge_dow", "discharge_hour",
        "creatinine_max", "creatinine_avg", "glucose_max", "glucose_avg",
        "hemoglobin_min", "hemoglobin_avg", "wbc_max", "wbc_avg",
        "sodium_min", "sodium_max", "potassium_min", "potassium_max",
        "bun_max", "platelet_min", "abnormal_lab_count", "abnormal_lab_ratio",
        "unique_med_count", "high_risk_med_count",
    ],
    "categorical": [
        "gender", "admission_type", "insurance", "discharge_location",
    ],
    "binary": [
        "ed_admission", "has_chf", "has_diabetes", "has_ckd", "has_copd",
        "has_hypertension", "has_cancer", "on_anticoagulant", "on_insulin",
        "on_antidiabetic", "on_opioid", "on_diuretic", "on_digoxin",
        "polypharmacy", "severe_polypharmacy",
    ],
    "target": "readmitted_30d",
}
