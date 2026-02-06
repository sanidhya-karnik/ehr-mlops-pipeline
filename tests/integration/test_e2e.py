"""
Integration tests for EHR MLOps Pipeline.

These tests require running infrastructure (docker-compose up).
Run with: pytest tests/integration -v -s

Prerequisites:
    1. Docker services running: docker-compose up -d
    2. Data loaded: python scripts/load_mimic_data.py
    3. dbt run: cd dbt && dbt run
"""

import os
import pytest
import requests
import time
from typing import Generator

# =============================================================================
# Configuration
# =============================================================================

API_URL = os.getenv("API_URL", "http://localhost:8000")
AIRFLOW_URL = os.getenv("AIRFLOW_URL", "http://localhost:8080")
MINIO_URL = os.getenv("MINIO_URL", "http://localhost:9000")
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = int(os.getenv("DB_PORT", "5432"))
DB_NAME = os.getenv("DB_NAME", "mimic")
DB_USER = os.getenv("DB_USER", "mimic")
DB_PASSWORD = os.getenv("DB_PASSWORD", "mimic_password")


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture(scope="module")
def db_connection():
    """Create database connection for tests."""
    import psycopg2
    
    try:
        conn = psycopg2.connect(
            host=DB_HOST,
            port=DB_PORT,
            database=DB_NAME,
            user=DB_USER,
            password=DB_PASSWORD,
        )
        yield conn
        conn.close()
    except psycopg2.OperationalError as e:
        pytest.skip(f"Database not available: {e}")


@pytest.fixture(scope="module")
def api_session():
    """Create requests session for API tests."""
    session = requests.Session()
    session.headers.update({"Content-Type": "application/json"})
    
    # Check if API is available
    try:
        response = session.get(f"{API_URL}/health/live", timeout=5)
        if response.status_code != 200:
            pytest.skip("API not available")
    except requests.RequestException:
        pytest.skip("API not available")
    
    yield session


# =============================================================================
# Database Tests
# =============================================================================

class TestDatabase:
    """Test database connectivity and data."""
    
    def test_connection(self, db_connection):
        """Test database connection."""
        cur = db_connection.cursor()
        cur.execute("SELECT 1")
        result = cur.fetchone()
        assert result[0] == 1
    
    def test_mimic_schema_exists(self, db_connection):
        """Test that mimic_hosp schema exists."""
        cur = db_connection.cursor()
        cur.execute("""
            SELECT schema_name FROM information_schema.schemata 
            WHERE schema_name = 'mimic_hosp'
        """)
        result = cur.fetchone()
        assert result is not None, "mimic_hosp schema not found"
    
    def test_source_tables_exist(self, db_connection):
        """Test that source tables have data."""
        cur = db_connection.cursor()
        
        tables = ["patients", "admissions", "diagnoses_icd"]
        for table in tables:
            cur.execute(f"SELECT COUNT(*) FROM mimic_hosp.{table}")
            count = cur.fetchone()[0]
            assert count > 0, f"Table {table} is empty"
    
    def test_feature_table_exists(self, db_connection):
        """Test that dbt feature table exists and has data."""
        cur = db_connection.cursor()
        
        try:
            cur.execute("SELECT COUNT(*) FROM public_marts.fct_readmission_features")
            count = cur.fetchone()[0]
            assert count > 0, "Feature table is empty"
        except Exception as e:
            pytest.fail(f"Feature table not found. Run dbt first: {e}")
    
    def test_feature_columns(self, db_connection):
        """Test that feature table has expected columns."""
        cur = db_connection.cursor()
        
        cur.execute("""
            SELECT column_name FROM information_schema.columns 
            WHERE table_schema = 'public_marts' 
            AND table_name = 'fct_readmission_features'
        """)
        
        columns = {row[0] for row in cur.fetchall()}
        
        required_columns = {
            "subject_id", "hadm_id", "age", "gender", "los_days",
            "readmitted_30d", "has_chf", "has_diabetes", "charlson_index",
        }
        
        missing = required_columns - columns
        assert not missing, f"Missing columns: {missing}"
    
    def test_readmission_rate(self, db_connection):
        """Test that readmission rate is reasonable (10-20%)."""
        cur = db_connection.cursor()
        
        cur.execute("""
            SELECT 
                AVG(readmitted_30d::float) as readmission_rate
            FROM public_marts.fct_readmission_features
        """)
        
        rate = cur.fetchone()[0]
        assert 0.05 < rate < 0.30, f"Unusual readmission rate: {rate:.2%}"


# =============================================================================
# API Tests
# =============================================================================

class TestAPI:
    """Test prediction API endpoints."""
    
    def test_health_endpoint(self, api_session):
        """Test /health endpoint."""
        response = api_session.get(f"{API_URL}/health")
        assert response.status_code == 200
        
        data = response.json()
        assert "status" in data
        assert "model_loaded" in data
    
    def test_liveness_probe(self, api_session):
        """Test /health/live endpoint."""
        response = api_session.get(f"{API_URL}/health/live")
        assert response.status_code == 200
    
    def test_readiness_probe(self, api_session):
        """Test /health/ready endpoint."""
        response = api_session.get(f"{API_URL}/health/ready")
        # May return 503 if model not loaded
        assert response.status_code in [200, 503]
    
    def test_model_info(self, api_session):
        """Test /model/info endpoint."""
        response = api_session.get(f"{API_URL}/model/info")
        assert response.status_code == 200
        
        data = response.json()
        assert "model_name" in data
        assert "feature_names" in data
    
    def test_prediction_with_features(self, api_session):
        """Test /predict with direct features."""
        payload = {
            "age": 65,
            "gender": "F",
            "los_days": 5.0,
            "admission_type": "ELECTIVE",
            "insurance": "Medicare",
            "ed_admission": 0,
            "prior_admits_6mo": 1,
            "has_chf": 0,
            "has_diabetes": 1,
            "charlson_index": 2,
        }
        
        response = api_session.post(f"{API_URL}/predict", json=payload)
        assert response.status_code == 200
        
        data = response.json()
        assert "probability" in data
        assert "prediction" in data
        assert "risk_level" in data
        assert 0 <= data["probability"] <= 1
        assert data["prediction"] in [0, 1]
        assert data["risk_level"] in ["LOW", "MEDIUM", "HIGH"]
    
    def test_prediction_high_risk_patient(self, api_session):
        """Test prediction for high-risk patient profile."""
        payload = {
            "age": 85,
            "los_days": 14.0,
            "ed_admission": 1,
            "prior_admits_6mo": 3,
            "prior_admits_12mo": 5,
            "has_chf": 1,
            "has_diabetes": 1,
            "has_ckd": 1,
            "charlson_index": 6,
            "polypharmacy": 1,
        }
        
        response = api_session.post(f"{API_URL}/predict", json=payload)
        assert response.status_code == 200
        
        data = response.json()
        # High-risk patient should have higher probability
        assert data["probability"] > 0.3, "High-risk patient should have higher probability"
    
    def test_prediction_low_risk_patient(self, api_session):
        """Test prediction for low-risk patient profile."""
        payload = {
            "age": 35,
            "los_days": 2.0,
            "ed_admission": 0,
            "prior_admits_6mo": 0,
            "has_chf": 0,
            "has_diabetes": 0,
            "charlson_index": 0,
        }
        
        response = api_session.post(f"{API_URL}/predict", json=payload)
        assert response.status_code == 200
        
        data = response.json()
        # Low-risk patient should have lower probability
        assert data["probability"] < 0.5, "Low-risk patient should have lower probability"
    
    def test_prediction_latency(self, api_session):
        """Test that predictions are fast enough (<500ms)."""
        payload = {"age": 65, "los_days": 5.0, "has_chf": 1}
        
        start = time.time()
        response = api_session.post(f"{API_URL}/predict", json=payload)
        latency = (time.time() - start) * 1000
        
        assert response.status_code == 200
        assert latency < 500, f"Prediction too slow: {latency:.0f}ms"
    
    def test_batch_predictions(self, api_session):
        """Test multiple sequential predictions."""
        payloads = [
            {"age": 50 + i * 10, "los_days": 3 + i, "has_chf": i % 2}
            for i in range(10)
        ]
        
        for payload in payloads:
            response = api_session.post(f"{API_URL}/predict", json=payload)
            assert response.status_code == 200
    
    def test_invalid_request(self, api_session):
        """Test API handles invalid requests gracefully."""
        # Empty payload
        response = api_session.post(f"{API_URL}/predict", json={})
        # Should still work (uses defaults) or return 422
        assert response.status_code in [200, 422]


# =============================================================================
# MinIO Tests
# =============================================================================

class TestMinIO:
    """Test MinIO/S3 storage."""
    
    def test_minio_health(self):
        """Test MinIO is healthy."""
        try:
            response = requests.get(f"{MINIO_URL}/minio/health/live", timeout=5)
            assert response.status_code == 200
        except requests.RequestException:
            pytest.skip("MinIO not available")
    
    def test_model_bucket_exists(self):
        """Test that model bucket exists."""
        import boto3
        from botocore.client import Config
        
        try:
            s3 = boto3.client(
                "s3",
                endpoint_url=MINIO_URL,
                aws_access_key_id="minioadmin",
                aws_secret_access_key="minioadmin",
                config=Config(signature_version="s3v4"),
            )
            
            buckets = [b["Name"] for b in s3.list_buckets()["Buckets"]]
            assert "mimic-models" in buckets, "mimic-models bucket not found"
        except Exception as e:
            pytest.skip(f"MinIO not available: {e}")


# =============================================================================
# Airflow Tests
# =============================================================================

class TestAirflow:
    """Test Airflow DAGs."""
    
    def test_airflow_health(self):
        """Test Airflow is healthy."""
        try:
            response = requests.get(f"{AIRFLOW_URL}/health", timeout=5)
            assert response.status_code == 200
        except requests.RequestException:
            pytest.skip("Airflow not available")
    
    def test_dags_loaded(self):
        """Test that DAGs are loaded."""
        try:
            response = requests.get(
                f"{AIRFLOW_URL}/api/v1/dags",
                auth=("airflow", "airflow"),
                timeout=10,
            )
            
            if response.status_code != 200:
                pytest.skip("Could not fetch DAGs")
            
            dags = response.json().get("dags", [])
            dag_ids = [d.get("dag_id") for d in dags]
            
            expected_dags = [
                "01_data_validation",
                "02_model_training",
                "03_model_deployment",
            ]
            
            for dag_id in expected_dags:
                assert dag_id in dag_ids, f"DAG {dag_id} not found"
        except requests.RequestException:
            pytest.skip("Airflow API not available")


# =============================================================================
# End-to-End Tests
# =============================================================================

class TestEndToEnd:
    """Full end-to-end workflow tests."""
    
    def test_full_prediction_workflow(self, db_connection, api_session):
        """Test complete workflow from database to prediction."""
        # 1. Verify data exists in database
        cur = db_connection.cursor()
        cur.execute("""
            SELECT subject_id, hadm_id, age, los_days, has_chf
            FROM public_marts.fct_readmission_features
            LIMIT 1
        """)
        row = cur.fetchone()
        assert row is not None, "No data in feature table"
        
        subject_id, hadm_id, age, los_days, has_chf = row
        
        # 2. Make prediction with real patient data
        payload = {
            "age": int(age) if age else 65,
            "los_days": float(los_days) if los_days else 5.0,
            "has_chf": int(has_chf) if has_chf else 0,
        }
        
        response = api_session.post(f"{API_URL}/predict", json=payload)
        assert response.status_code == 200
        
        data = response.json()
        assert "probability" in data
        assert "risk_level" in data
    
    def test_model_consistency(self, api_session):
        """Test that same input produces same output."""
        payload = {
            "age": 70,
            "los_days": 7.0,
            "has_chf": 1,
            "has_diabetes": 1,
        }
        
        # Make multiple predictions
        predictions = []
        for _ in range(5):
            response = api_session.post(f"{API_URL}/predict", json=payload)
            assert response.status_code == 200
            predictions.append(response.json()["probability"])
        
        # All predictions should be identical
        assert all(p == predictions[0] for p in predictions), \
            "Model predictions are not deterministic"
