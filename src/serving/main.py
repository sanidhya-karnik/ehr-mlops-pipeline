"""
=============================================================================
Model Serving API
=============================================================================

FastAPI application for serving readmission predictions.
"""

import os
import pickle
import logging
import time
from datetime import datetime
from typing import Dict, Any, Optional, List
from contextlib import asynccontextmanager

import numpy as np
import psycopg2
from psycopg2.extras import RealDictCursor
import boto3
from botocore.client import Config
from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# =============================================================================
# Configuration
# =============================================================================

class Settings:
    S3_ENDPOINT = os.getenv("S3_ENDPOINT_URL", "http://localhost:9000")
    S3_BUCKET = os.getenv("S3_BUCKET_MODELS", "mimic-models")
    MODEL_NAME = os.getenv("MODEL_NAME", "readmission_model")
    
    DB_HOST = os.getenv("DB_HOST", "localhost")
    DB_PORT = int(os.getenv("DB_PORT", "5432"))
    DB_NAME = os.getenv("DB_NAME", "mimic")
    DB_USER = os.getenv("DB_USER", "mimic")
    DB_PASSWORD = os.getenv("DB_PASSWORD", "mimic_password")
    
    REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
    REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))


settings = Settings()


# =============================================================================
# Model Manager
# =============================================================================

class ModelManager:
    """Manages model loading and caching."""
    
    def __init__(self):
        self.model = None
        self.scaler = None
        self.label_encoders = {}
        self.feature_names = []
        self.metrics = {}
        self.version = None
        self.shap_explainer = None
        self.shap_base_value = None
        
    def load_latest_model(self):
        """Load the latest deployed model from S3."""
        logger.info("Loading model from S3...")
        
        s3 = boto3.client(
            "s3",
            endpoint_url=settings.S3_ENDPOINT,
            aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID", "minioadmin"),
            aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY", "minioadmin"),
            config=Config(signature_version="s3v4"),
        )
        
        # List model versions
        prefix = f"models/{settings.MODEL_NAME}/"
        response = s3.list_objects_v2(Bucket=settings.S3_BUCKET, Prefix=prefix)
        
        if "Contents" not in response:
            logger.warning("No model found in S3")
            return False
        
        # Find latest version
        model_files = [
            obj["Key"] for obj in response["Contents"]
            if obj["Key"].endswith("model.pkl")
        ]
        
        if not model_files:
            logger.warning("No model.pkl found")
            return False
        
        latest_key = sorted(model_files)[-1]
        logger.info(f"Loading model: {latest_key}")
        
        # Download and load
        response = s3.get_object(Bucket=settings.S3_BUCKET, Key=latest_key)
        artifact = pickle.loads(response["Body"].read())
        
        self.model = artifact["model"]
        self.scaler = artifact["scaler"]
        self.label_encoders = artifact.get("label_encoders", {})
        self.feature_names = artifact.get("feature_names", [])
        self.metrics = artifact.get("metrics", {})
        self.version = latest_key.split("/")[-2]
        
        # Initialize SHAP explainer
        self._init_shap_explainer()
        
        logger.info(f"Model loaded: version={self.version}, metrics={self.metrics}")
        return True
    
    def _init_shap_explainer(self):
        """Initialize SHAP explainer for model explanations."""
        try:
            import shap
            
            model_type = type(self.model).__name__
            logger.info(f"Initializing SHAP explainer for {model_type}")
            
            if hasattr(self.model, 'get_booster') or 'XGB' in model_type:
                self.shap_explainer = shap.TreeExplainer(self.model)
            elif 'RandomForest' in model_type or 'GradientBoosting' in model_type:
                self.shap_explainer = shap.TreeExplainer(self.model)
            else:
                logger.warning(f"SHAP not supported for {model_type}, explanations disabled")
                self.shap_explainer = None
                return
            
            # Get base value - handle both array and scalar cases
            if hasattr(self.shap_explainer, 'expected_value'):
                base_val = self.shap_explainer.expected_value
                if isinstance(base_val, (list, np.ndarray)):
                    # Multi-class: use positive class (index 1) if available
                    if len(base_val) > 1:
                        self.shap_base_value = float(base_val[1])
                    else:
                        self.shap_base_value = float(base_val[0])
                else:
                    # Single value (binary XGBoost)
                    self.shap_base_value = float(base_val)
            else:
                self.shap_base_value = 0.5
                
            logger.info(f"SHAP explainer initialized (base_value={self.shap_base_value:.3f})")
            
        except ImportError:
            logger.warning("SHAP not installed, explanations disabled")
            self.shap_explainer = None
        except Exception as e:
            logger.error(f"Failed to initialize SHAP explainer: {e}")
            self.shap_explainer = None
    
    def predict(self, features: Dict[str, Any]) -> Dict[str, Any]:
        """Make prediction from feature dict."""
        if self.model is None:
            raise ValueError("Model not loaded")
        
        # Build feature vector
        X = np.zeros((1, len(self.feature_names)))
        
        for i, name in enumerate(self.feature_names):
            if name in features:
                value = features[name]
                
                # Handle categorical encoding
                if name in self.label_encoders:
                    le = self.label_encoders[name]
                    try:
                        value = le.transform([str(value)])[0]
                    except ValueError:
                        value = 0  # Unknown category
                
                X[0, i] = value
        
        # Scale
        if self.scaler:
            X = self.scaler.transform(X)
        
        # Predict
        prob = self.model.predict_proba(X)[0, 1]
        pred = int(prob >= 0.5)
        
        return {
            "probability": float(prob),
            "prediction": pred,
            "risk_level": "HIGH" if prob >= 0.7 else ("MEDIUM" if prob >= 0.4 else "LOW"),
            "model_version": self.version,
            "_X": X,  # Keep for explanation
        }
    
    def explain(self, features: Dict[str, Any], top_n: int = 10) -> Dict[str, Any]:
        """
        Generate SHAP explanation for a prediction.
        
        Args:
            features: Feature dictionary
            top_n: Number of top contributing features to return
            
        Returns:
            Dictionary with explanation details
        """
        if self.shap_explainer is None:
            raise ValueError("SHAP explainer not available")
        
        # Get prediction first (this also builds the feature vector)
        pred_result = self.predict(features)
        X = pred_result["_X"]
        
        # Compute SHAP values
        shap_values = self.shap_explainer.shap_values(X)
        
        # Handle different SHAP output formats
        if isinstance(shap_values, list):
            # Multi-class output: use positive class (index 1) if available
            if len(shap_values) > 1:
                shap_values = shap_values[1]
            else:
                shap_values = shap_values[0]
        
        # Ensure we have a 1D array
        shap_values = np.array(shap_values).flatten()
        
        # Build feature contributions
        contributions = []
        for i, (feat, shap_val) in enumerate(zip(self.feature_names, shap_values)):
            feat_value = X[0, i] if i < X.shape[1] else 0
            contributions.append({
                "feature": feat,
                "value": float(feat_value),
                "shap_value": float(shap_val),
                "direction": "risk_increase" if shap_val > 0 else "risk_decrease",
                "abs_contribution": abs(float(shap_val)),
            })
        
        # Sort by absolute contribution
        contributions.sort(key=lambda x: x["abs_contribution"], reverse=True)
        
        # Split into risk factors and protective factors
        risk_factors = [c for c in contributions if c["shap_value"] > 0][:top_n]
        protective_factors = [c for c in contributions if c["shap_value"] < 0][:top_n]
        
        return {
            "probability": pred_result["probability"],
            "prediction": pred_result["prediction"],
            "risk_level": pred_result["risk_level"],
            "base_value": self.shap_base_value,
            "top_risk_factors": risk_factors,
            "top_protective_factors": protective_factors,
            "model_version": self.version,
        }


# Global model manager
model_manager = ModelManager()


# =============================================================================
# Application Lifecycle
# =============================================================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Load model on startup."""
    logger.info("Starting model serving API...")
    try:
        model_manager.load_latest_model()
    except Exception as e:
        logger.error(f"Failed to load model: {e}")
    yield
    logger.info("Shutting down...")


# =============================================================================
# FastAPI Application
# =============================================================================

app = FastAPI(
    title="Readmission Prediction API",
    description="Predict 30-day hospital readmission risk",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# =============================================================================
# Request/Response Models
# =============================================================================

class PredictionRequest(BaseModel):
    subject_id: Optional[int] = None
    hadm_id: Optional[int] = None
    
    # Or provide features directly
    age: Optional[int] = None
    gender: Optional[str] = None
    admission_type: Optional[str] = None
    insurance: Optional[str] = None
    los_days: Optional[float] = None
    discharge_location: Optional[str] = None
    ed_admission: Optional[int] = 0
    prior_admits_6mo: Optional[int] = 0
    prior_admits_12mo: Optional[int] = 0
    prior_ed_visits_6mo: Optional[int] = 0
    has_chf: Optional[int] = 0
    has_diabetes: Optional[int] = 0
    has_ckd: Optional[int] = 0
    has_copd: Optional[int] = 0
    has_hypertension: Optional[int] = 0
    has_cancer: Optional[int] = 0
    diagnosis_count: Optional[int] = 0
    charlson_index: Optional[int] = 0


class PredictionResponse(BaseModel):
    probability: float
    prediction: int
    risk_level: str
    model_version: str
    latency_ms: float


class HealthResponse(BaseModel):
    status: str
    model_loaded: bool
    model_version: Optional[str]
    timestamp: str


class ModelInfoResponse(BaseModel):
    model_name: str
    model_version: Optional[str]
    metrics: Dict[str, Any]
    feature_names: List[str]


class FeatureContribution(BaseModel):
    feature: str
    value: float
    shap_value: float
    direction: str
    abs_contribution: float


class ExplanationResponse(BaseModel):
    probability: float
    prediction: int
    risk_level: str
    base_value: float
    top_risk_factors: List[FeatureContribution]
    top_protective_factors: List[FeatureContribution]
    model_version: str
    latency_ms: float


# =============================================================================
# Endpoints
# =============================================================================

@app.get("/health", response_model=HealthResponse)
async def health_check():
    """Health check endpoint."""
    return HealthResponse(
        status="healthy" if model_manager.model else "degraded",
        model_loaded=model_manager.model is not None,
        model_version=model_manager.version,
        timestamp=datetime.utcnow().isoformat(),
    )


@app.get("/health/ready")
async def readiness():
    """Kubernetes readiness probe."""
    if model_manager.model is None:
        raise HTTPException(status_code=503, detail="Model not loaded")
    return {"status": "ready"}


@app.get("/health/live")
async def liveness():
    """Kubernetes liveness probe."""
    return {"status": "alive"}


@app.get("/model/info", response_model=ModelInfoResponse)
async def model_info():
    """Get model information."""
    return ModelInfoResponse(
        model_name=settings.MODEL_NAME,
        model_version=model_manager.version,
        metrics=model_manager.metrics,
        feature_names=model_manager.feature_names,
    )


@app.post("/model/reload")
async def reload_model():
    """Reload model from S3."""
    success = model_manager.load_latest_model()
    if not success:
        raise HTTPException(status_code=500, detail="Failed to reload model")
    return {"status": "reloaded", "version": model_manager.version}


@app.post("/predict", response_model=PredictionResponse)
async def predict(request: PredictionRequest, background_tasks: BackgroundTasks):
    """Make readmission prediction."""
    start_time = time.time()
    
    if model_manager.model is None:
        raise HTTPException(status_code=503, detail="Model not loaded")
    
    # Build features from request
    features = request.model_dump(exclude_none=True)
    
    # If subject_id/hadm_id provided, fetch features from database
    if request.subject_id and request.hadm_id:
        features = await fetch_features_from_db(request.subject_id, request.hadm_id)
    
    # Make prediction
    try:
        result = model_manager.predict(features)
    except Exception as e:
        logger.error(f"Prediction failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    
    latency_ms = (time.time() - start_time) * 1000
    
    # Log prediction in background
    background_tasks.add_task(
        log_prediction,
        model_version=result["model_version"],
        subject_id=request.subject_id,
        hadm_id=request.hadm_id,
        features=features,
        prediction=result["probability"],
        latency_ms=latency_ms,
    )
    
    return PredictionResponse(
        probability=result["probability"],
        prediction=result["prediction"],
        risk_level=result["risk_level"],
        model_version=result["model_version"],
        latency_ms=latency_ms,
    )


@app.post("/explain", response_model=ExplanationResponse)
async def explain_prediction(request: PredictionRequest):
    """
    Get SHAP-based explanation for a prediction.
    
    Returns the top risk factors (features increasing readmission risk)
    and top protective factors (features decreasing risk).
    """
    start_time = time.time()
    
    if model_manager.model is None:
        raise HTTPException(status_code=503, detail="Model not loaded")
    
    if model_manager.shap_explainer is None:
        raise HTTPException(status_code=503, detail="SHAP explainer not available")
    
    # Build features from request
    features = request.model_dump(exclude_none=True)
    
    # If subject_id/hadm_id provided, fetch features from database
    if request.subject_id and request.hadm_id:
        features = await fetch_features_from_db(request.subject_id, request.hadm_id)
    
    # Get explanation
    try:
        result = model_manager.explain(features)
    except Exception as e:
        logger.error(f"Explanation failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    
    latency_ms = (time.time() - start_time) * 1000
    
    return ExplanationResponse(
        probability=result["probability"],
        prediction=result["prediction"],
        risk_level=result["risk_level"],
        base_value=result["base_value"],
        top_risk_factors=[FeatureContribution(**f) for f in result["top_risk_factors"]],
        top_protective_factors=[FeatureContribution(**f) for f in result["top_protective_factors"]],
        model_version=result["model_version"],
        latency_ms=latency_ms,
    )


@app.get("/explain/feature-importance")
async def global_feature_importance():
    """
    Get global SHAP feature importance.
    
    Note: This requires pre-computed SHAP values. For real-time use,
    run the SHAP analysis script and cache results.
    """
    if model_manager.model is None:
        raise HTTPException(status_code=503, detail="Model not loaded")
    
    # Return feature names with placeholder importance
    # In production, load pre-computed SHAP importance from S3
    return {
        "feature_names": model_manager.feature_names,
        "message": "Run scripts/run-shap-analysis.sh for full importance analysis",
    }


# =============================================================================
# Helper Functions
# =============================================================================

async def fetch_features_from_db(subject_id: int, hadm_id: int) -> Dict[str, Any]:
    """Fetch features from database."""
    conn = psycopg2.connect(
        host=settings.DB_HOST,
        port=settings.DB_PORT,
        database=settings.DB_NAME,
        user=settings.DB_USER,
        password=settings.DB_PASSWORD,
        cursor_factory=RealDictCursor,
    )
    
    cur = conn.cursor()
    cur.execute(
        """
        SELECT * FROM public_marts.fct_readmission_features
        WHERE subject_id = %s AND hadm_id = %s
        """,
        (subject_id, hadm_id),
    )
    
    row = cur.fetchone()
    conn.close()
    
    if not row:
        raise HTTPException(status_code=404, detail="Patient/admission not found")
    
    return dict(row)


def log_prediction(
    model_version: str,
    subject_id: Optional[int],
    hadm_id: Optional[int],
    features: Dict,
    prediction: float,
    latency_ms: float,
):
    """Log prediction to database."""
    try:
        import json
        conn = psycopg2.connect(
            host=settings.DB_HOST,
            port=settings.DB_PORT,
            database=settings.DB_NAME,
            user=settings.DB_USER,
            password=settings.DB_PASSWORD,
        )
        
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO prediction_logs 
                (model_version, subject_id, hadm_id, features, prediction, latency_ms)
            VALUES (%s, %s, %s, %s, %s, %s)
            """,
            (model_version, subject_id, hadm_id, json.dumps(features), prediction, latency_ms),
        )
        
        conn.commit()
        conn.close()
    except Exception as e:
        logger.error(f"Failed to log prediction: {e}")


# =============================================================================
# Main
# =============================================================================

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host=os.getenv("API_HOST", "0.0.0.0"),
        port=int(os.getenv("API_PORT", "8000")),
        reload=True,
    )
