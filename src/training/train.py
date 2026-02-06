"""
=============================================================================
Model Training Module
=============================================================================

Trains readmission prediction model using features from dbt.
Supports XGBoost and Logistic Regression.
"""

import os
import json
import pickle
import logging
from datetime import datetime
from typing import Dict, Any, Tuple

import pandas as pd
import numpy as np
from sklearn.model_selection import train_test_split, cross_val_score
from sklearn.preprocessing import StandardScaler, LabelEncoder
from sklearn.linear_model import LogisticRegression
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import (
    roc_auc_score,
    precision_score,
    recall_score,
    f1_score,
    classification_report,
    confusion_matrix,
)
import psycopg2
import boto3
from botocore.client import Config

try:
    import xgboost as xgb
    HAS_XGBOOST = True
except ImportError:
    HAS_XGBOOST = False

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class ModelTrainer:
    """Train and evaluate readmission prediction models."""
    
    # Features to use for training
    NUMERIC_FEATURES = [
        "age",
        "los_days",
        "prior_admits_6mo",
        "prior_admits_12mo",
        "prior_ed_visits_6mo",
        "avg_prior_los",
        "diagnosis_count",
        "charlson_index",
        "discharge_dow",
        "discharge_hour",
        # Lab features (aligned with fct_readmission_features.sql)
        "creatinine_max",
        "creatinine_avg",
        "glucose_max",
        "glucose_avg",
        "hemoglobin_min",
        "hemoglobin_avg",
        "wbc_max",
        "wbc_avg",
        "sodium_min",
        "sodium_max",
        "potassium_min",
        "potassium_max",
        "bun_max",
        "platelet_min",
        "abnormal_lab_count",
        "abnormal_lab_ratio",
        # Medication features
        "unique_med_count",
        "high_risk_med_count",
    ]
    
    CATEGORICAL_FEATURES = [
        "gender",
        "admission_type",
        "insurance",
        "discharge_location",
    ]
    
    BINARY_FEATURES = [
        "ed_admission",
        "has_chf",
        "has_diabetes",
        "has_ckd",
        "has_copd",
        "has_hypertension",
        "has_cancer",
        # Medication flags
        "on_anticoagulant",
        "on_insulin",
        "on_antidiabetic",
        "on_opioid",
        "on_diuretic",
        "on_digoxin",
        "polypharmacy",
        "severe_polypharmacy",
    ]
    
    TARGET = "readmitted_30d"
    
    def __init__(
        self,
        db_host: str,
        db_name: str,
        db_user: str,
        db_password: str,
        db_port: int = 5432,
    ):
        self.db_config = {
            "host": db_host,
            "database": db_name,
            "user": db_user,
            "password": db_password,
            "port": db_port,
        }
        self.model = None
        self.scaler = None
        self.label_encoders = {}
        self.metrics = {}
        
    def _get_connection(self):
        """Create database connection."""
        return psycopg2.connect(**self.db_config)
    
    def load_data(self) -> pd.DataFrame:
        """Load feature data from database."""
        logger.info("Loading data from feature store...")
        
        conn = self._get_connection()
        
        query = """
            SELECT * FROM public_marts.fct_readmission_features
        """
        
        df = pd.read_sql(query, conn)
        conn.close()
        
        logger.info(f"Loaded {len(df)} samples")
        return df
    
    def preprocess(self, df: pd.DataFrame) -> Tuple[np.ndarray, np.ndarray]:
        """Preprocess features for model training."""
        logger.info("Preprocessing features...")
        
        # Make a copy
        data = df.copy()
        
        # Handle numeric features
        for col in self.NUMERIC_FEATURES:
            if col in data.columns:
                data[col] = pd.to_numeric(data[col], errors="coerce")
                data[col] = data[col].fillna(data[col].median())
        
        # Encode categorical features
        for col in self.CATEGORICAL_FEATURES:
            if col in data.columns:
                le = LabelEncoder()
                data[col] = data[col].fillna("Unknown")
                data[col] = le.fit_transform(data[col].astype(str))
                self.label_encoders[col] = le
        
        # Binary features - ensure 0/1
        for col in self.BINARY_FEATURES:
            if col in data.columns:
                data[col] = data[col].fillna(0).astype(int)
        
        # Combine all features
        all_features = self.NUMERIC_FEATURES + self.CATEGORICAL_FEATURES + self.BINARY_FEATURES
        feature_cols = [c for c in all_features if c in data.columns]
        
        X = data[feature_cols].values
        y = data[self.TARGET].values
        
        # Scale numeric features
        self.scaler = StandardScaler()
        X = self.scaler.fit_transform(X)
        
        logger.info(f"Final feature matrix shape: {X.shape}")
        return X, y
    
    def train(self, model_type: str = "logistic") -> Dict[str, float]:
        """Train the model and return metrics."""
        # Load and preprocess data
        df = self.load_data()
        X, y = self.preprocess(df)
        
        # Split data
        X_train, X_test, y_train, y_test = train_test_split(
            X, y, test_size=0.2, random_state=42, stratify=y
        )
        
        logger.info(f"Training set: {len(X_train)}, Test set: {len(X_test)}")
        logger.info(f"Positive class rate: {y.mean():.2%}")
        
        # Initialize model
        if model_type == "logistic":
            self.model = LogisticRegression(
                max_iter=1000,
                class_weight="balanced",
                random_state=42,
            )
        elif model_type == "random_forest":
            self.model = RandomForestClassifier(
                n_estimators=100,
                max_depth=10,
                class_weight="balanced",
                random_state=42,
                n_jobs=-1,
            )
        elif model_type == "xgboost":
            if not HAS_XGBOOST:
                raise ImportError("xgboost not installed. Run: pip install xgboost")
            
            # Calculate scale_pos_weight for imbalanced data
            scale_pos_weight = (y_train == 0).sum() / (y_train == 1).sum()
            
            self.model = xgb.XGBClassifier(
                n_estimators=200,
                max_depth=6,
                learning_rate=0.1,
                scale_pos_weight=scale_pos_weight,
                random_state=42,
                n_jobs=-1,
                eval_metric="auc",
            )
        else:
            raise ValueError(f"Unknown model type: {model_type}")
        
        # Train
        logger.info(f"Training {model_type} model...")
        self.model.fit(X_train, y_train)
        
        # Evaluate
        y_pred = self.model.predict(X_test)
        y_prob = self.model.predict_proba(X_test)[:, 1]
        
        self.metrics = {
            "auc_roc": float(roc_auc_score(y_test, y_prob)),
            "precision": float(precision_score(y_test, y_pred)),
            "recall": float(recall_score(y_test, y_pred)),
            "f1": float(f1_score(y_test, y_pred)),
            "train_samples": int(len(X_train)),
            "test_samples": int(len(X_test)),
            "positive_rate": float(y.mean()),
            "model_type": model_type,
            "trained_at": datetime.utcnow().isoformat(),
        }
        
        # Cross-validation
        cv_scores = cross_val_score(self.model, X, y, cv=5, scoring="roc_auc")
        self.metrics["cv_auc_mean"] = float(cv_scores.mean())
        self.metrics["cv_auc_std"] = float(cv_scores.std())
        
        # Log feature importance for tree-based models
        if model_type in ["xgboost", "random_forest"]:
            feature_names = self.NUMERIC_FEATURES + self.CATEGORICAL_FEATURES + self.BINARY_FEATURES
            importances = self.model.feature_importances_
            importance_df = pd.DataFrame({
                "feature": feature_names[:len(importances)],
                "importance": importances
            }).sort_values("importance", ascending=False)
            
            logger.info("Top 10 features:")
            for _, row in importance_df.head(10).iterrows():
                logger.info(f"  {row['feature']}: {row['importance']:.4f}")
        
        logger.info(f"Model metrics: {json.dumps(self.metrics, indent=2)}")
        
        return self.metrics
    
    def save_model(
        self,
        s3_endpoint: str,
        bucket: str,
        model_name: str,
    ) -> str:
        """Save model to S3."""
        if self.model is None:
            raise ValueError("No model trained yet")
        
        # Create model artifact
        artifact = {
            "model": self.model,
            "scaler": self.scaler,
            "label_encoders": self.label_encoders,
            "metrics": self.metrics,
            "feature_names": self.NUMERIC_FEATURES + self.CATEGORICAL_FEATURES + self.BINARY_FEATURES,
        }
        
        # Serialize
        model_bytes = pickle.dumps(artifact)
        
        # Generate version
        version = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        key = f"models/{model_name}/{version}/model.pkl"
        
        # Upload to S3
        s3_client = boto3.client(
            "s3",
            endpoint_url=s3_endpoint,
            aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID", "minioadmin"),
            aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY", "minioadmin"),
            config=Config(signature_version="s3v4"),
        )
        
        s3_client.put_object(
            Bucket=bucket,
            Key=key,
            Body=model_bytes,
        )
        
        # Also save metrics as JSON
        metrics_key = f"models/{model_name}/{version}/metrics.json"
        s3_client.put_object(
            Bucket=bucket,
            Key=metrics_key,
            Body=json.dumps(self.metrics, indent=2),
            ContentType="application/json",
        )
        
        model_path = f"s3://{bucket}/{key}"
        logger.info(f"Model saved to {model_path}")
        
        return model_path


# =============================================================================
# CLI
# =============================================================================

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Train readmission model")
    parser.add_argument("--model-name", default="readmission_model")
    parser.add_argument("--model-type", default="xgboost", choices=["logistic", "random_forest", "xgboost"])
    parser.add_argument("--output-path", default="s3://mimic-models/models/")
    args = parser.parse_args()
    
    trainer = ModelTrainer(
        db_host=os.getenv("DB_HOST", "localhost"),
        db_name=os.getenv("DB_NAME", "mimic"),
        db_user=os.getenv("DB_USER", "mimic"),
        db_password=os.getenv("DB_PASSWORD", "mimic_password"),
    )
    
    metrics = trainer.train(model_type=args.model_type)
    
    model_path = trainer.save_model(
        s3_endpoint=os.getenv("S3_ENDPOINT_URL", "http://localhost:9000"),
        bucket="mimic-models",
        model_name=args.model_name,
    )
    
    print(f"Training complete! Model saved to {model_path}")
    print(f"Metrics: {json.dumps(metrics, indent=2)}")
