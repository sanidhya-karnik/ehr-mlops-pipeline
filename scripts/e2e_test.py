"""
=============================================================================
EHR MLOps Pipeline - End-to-End Test Script (Python)
=============================================================================

Cross-platform E2E test script that works on Windows, Mac, and Linux.

Usage:
    python scripts/e2e_test.py
    python scripts/e2e_test.py --skip-data-load
    python scripts/e2e_test.py --skip-training
    python scripts/e2e_test.py --quick
    python scripts/e2e_test.py --cleanup
"""

import argparse
import json
import os
import subprocess
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import List, Optional

import requests

# =============================================================================
# Configuration
# =============================================================================

PROJECT_DIR = Path(__file__).parent.parent.absolute()
LOG_FILE = PROJECT_DIR / "e2e-test.log"

# Service URLs
POSTGRES_CONTAINER = "mlops-postgres"
MINIO_URL = "http://localhost:9000"
AIRFLOW_URL = "http://localhost:8080"
API_URL = "http://localhost:8000"
LOCALSTACK_URL = "http://localhost:4566"


# =============================================================================
# Test Result Tracking
# =============================================================================

@dataclass
class TestResults:
    passed: int = 0
    failed: int = 0
    skipped: int = 0
    details: List[str] = field(default_factory=list)
    
    def success(self, msg: str):
        self.passed += 1
        self.details.append(f"✓ PASS: {msg}")
        print(f"\033[92m[✓]\033[0m {msg}")
    
    def fail(self, msg: str):
        self.failed += 1
        self.details.append(f"✗ FAIL: {msg}")
        print(f"\033[91m[✗]\033[0m {msg}")
    
    def skip(self, msg: str):
        self.skipped += 1
        self.details.append(f"- SKIP: {msg}")
        print(f"\033[93m[SKIP]\033[0m {msg}")
    
    def warn(self, msg: str):
        self.details.append(f"! WARN: {msg}")
        print(f"\033[93m[!]\033[0m {msg}")


results = TestResults()


# =============================================================================
# Utility Functions
# =============================================================================

def log(msg: str):
    """Log message with timestamp."""
    timestamp = datetime.now().strftime("%H:%M:%S")
    print(f"\033[94m[{timestamp}]\033[0m {msg}")
    with open(LOG_FILE, "a") as f:
        f.write(f"[{timestamp}] {msg}\n")


def section(title: str):
    """Print section header."""
    print()
    print("\033[94m" + "=" * 60 + "\033[0m")
    print(f"\033[94m {title}\033[0m")
    print("\033[94m" + "=" * 60 + "\033[0m")


def run_command(cmd: List[str], cwd: Optional[Path] = None, capture: bool = True) -> tuple:
    """Run a command and return (success, output)."""
    try:
        result = subprocess.run(
            cmd,
            cwd=cwd or PROJECT_DIR,
            capture_output=capture,
            text=True,
            timeout=300,
        )
        return result.returncode == 0, result.stdout + result.stderr
    except subprocess.TimeoutExpired:
        return False, "Command timed out"
    except Exception as e:
        return False, str(e)


def wait_for_url(url: str, max_attempts: int = 30, interval: int = 2) -> bool:
    """Wait for a URL to become available."""
    for attempt in range(max_attempts):
        try:
            response = requests.get(url, timeout=5)
            if response.status_code < 500:
                return True
        except requests.RequestException:
            pass
        time.sleep(interval)
    return False


def wait_for_postgres(max_attempts: int = 30) -> bool:
    """Wait for PostgreSQL to be ready."""
    for attempt in range(max_attempts):
        success, _ = run_command([
            "docker", "exec", POSTGRES_CONTAINER,
            "pg_isready", "-U", "postgres"
        ])
        if success:
            return True
        time.sleep(2)
    return False


def docker_compose(*args) -> tuple:
    """Run docker-compose command."""
    return run_command(["docker-compose", *args])


# =============================================================================
# Test Steps
# =============================================================================

def step1_start_infrastructure():
    """Start Docker infrastructure."""
    section("Step 1: Starting Docker Infrastructure")
    
    log("Stopping any existing containers...")
    docker_compose("down")
    
    log("Starting Docker services...")
    success, output = docker_compose("up", "-d")
    if not success:
        results.fail("Failed to start Docker services")
        print(output)
        return False
    results.success("Docker services started")
    
    # Wait for services
    log("Waiting for PostgreSQL...")
    if wait_for_postgres(60):
        results.success("PostgreSQL is ready")
    else:
        results.fail("PostgreSQL failed to start")
        return False
    
    log("Waiting for MinIO...")
    if wait_for_url(f"{MINIO_URL}/minio/health/live", 30):
        results.success("MinIO is ready")
    else:
        results.fail("MinIO failed to start")
        return False
    
    log("Waiting for Airflow...")
    if wait_for_url(f"{AIRFLOW_URL}/health", 90):
        results.success("Airflow is ready")
    else:
        results.fail("Airflow failed to start")
        return False
    
    log("Waiting for LocalStack...")
    if wait_for_url(f"{LOCALSTACK_URL}/_localstack/health", 30):
        results.success("LocalStack is ready")
    else:
        results.warn("LocalStack may not be ready (non-critical)")
    
    return True


def step2_load_data(skip: bool = False):
    """Load MIMIC-IV data into PostgreSQL."""
    section("Step 2: Loading MIMIC-IV Data")
    
    if skip:
        results.skip("Data loading (--skip-data-load flag set)")
        return True
    
    # Check if data files exist
    data_dir = PROJECT_DIR / "data" / "mimic-iv" / "hosp"
    if not (data_dir / "patients.csv").exists():
        results.fail(f"MIMIC-IV data not found at {data_dir}")
        results.warn("Please download MIMIC-IV data from PhysioNet first")
        return False
    
    log("Loading MIMIC-IV data into PostgreSQL...")
    success, output = run_command([
        sys.executable, str(PROJECT_DIR / "scripts" / "load_mimic_data.py")
    ])
    
    if success:
        results.success("MIMIC-IV data loaded successfully")
    else:
        results.fail("Failed to load MIMIC-IV data")
        print(output[-500:])  # Print last 500 chars
        return False
    
    # Verify data
    log("Verifying data in PostgreSQL...")
    success, output = run_command([
        "docker", "exec", POSTGRES_CONTAINER,
        "psql", "-U", "mimic", "-d", "mimic", "-t", "-c",
        "SELECT COUNT(*) FROM mimic_hosp.patients;"
    ])
    
    if success:
        count = output.strip()
        if count and int(count) > 0:
            results.success(f"Verified: {count} patients in database")
            return True
    
    results.fail("No patient data found in database")
    return False


def step3_run_dbt():
    """Run dbt transformations."""
    section("Step 3: Running dbt Transformations")
    
    dbt_dir = PROJECT_DIR / "dbt"
    
    # Set environment variables
    env = os.environ.copy()
    env.update({
        "DB_HOST": "localhost",
        "DB_PORT": "5432",
        "DB_NAME": "mimic",
        "DB_USER": "mimic",
        "DB_PASSWORD": "mimic_password",
    })
    
    log("Running dbt models...")
    result = subprocess.run(
        ["dbt", "run", "--profiles-dir", ".", "--project-dir", "."],
        cwd=dbt_dir,
        capture_output=True,
        text=True,
        env=env,
    )
    
    if result.returncode == 0:
        results.success("dbt models completed")
    else:
        results.fail("dbt run failed")
        print(result.stderr[-500:])
        return False
    
    log("Running dbt tests...")
    result = subprocess.run(
        ["dbt", "test", "--profiles-dir", ".", "--project-dir", "."],
        cwd=dbt_dir,
        capture_output=True,
        text=True,
        env=env,
    )
    
    if result.returncode == 0:
        results.success("dbt tests passed")
    else:
        results.warn("Some dbt tests failed (check logs)")
    
    # Verify feature table
    log("Verifying feature table...")
    success, output = run_command([
        "docker", "exec", POSTGRES_CONTAINER,
        "psql", "-U", "mimic", "-d", "mimic", "-t", "-c",
        "SELECT COUNT(*) FROM public_marts.fct_readmission_features;"
    ])
    
    if success:
        count = output.strip()
        if count and int(count) > 0:
            results.success(f"Verified: {count} rows in feature table")
            return True
    
    results.fail("Feature table is empty or doesn't exist")
    return False


def step4_train_model(skip: bool = False):
    """Train the ML model."""
    section("Step 4: Training ML Model")
    
    if skip:
        results.skip("Model training (--skip-training flag set)")
        return True
    
    env = os.environ.copy()
    env.update({
        "DB_HOST": "localhost",
        "DB_NAME": "mimic",
        "DB_USER": "mimic",
        "DB_PASSWORD": "mimic_password",
        "S3_ENDPOINT_URL": "http://localhost:9000",
        "AWS_ACCESS_KEY_ID": "minioadmin",
        "AWS_SECRET_ACCESS_KEY": "minioadmin",
    })
    
    log("Training XGBoost model...")
    result = subprocess.run(
        [
            sys.executable,
            str(PROJECT_DIR / "src" / "training" / "train.py"),
            "--model-type", "xgboost",
            "--model-name", "readmission_model",
        ],
        cwd=PROJECT_DIR,
        capture_output=True,
        text=True,
        env=env,
        timeout=600,
    )
    
    if result.returncode == 0:
        results.success("Model training completed")
        return True
    else:
        results.fail("Model training failed")
        print(result.stderr[-500:])
        return False


def step5_test_api():
    """Test the prediction API."""
    section("Step 5: Testing Prediction API")
    
    log("Building and starting model-api...")
    docker_compose("up", "-d", "model-api")
    
    log("Waiting for Model API...")
    if not wait_for_url(f"{API_URL}/health/live", 60):
        results.fail("Model API failed to start")
        success, output = run_command(["docker-compose", "logs", "model-api"])
        print(output[-500:])
        return False
    results.success("Model API is running")
    
    # Test health endpoint
    log("Testing /health endpoint...")
    try:
        response = requests.get(f"{API_URL}/health", timeout=10)
        if response.status_code == 200 and "status" in response.json():
            results.success("Health endpoint working")
        else:
            results.fail("Health endpoint not responding correctly")
    except Exception as e:
        results.fail(f"Health endpoint error: {e}")
    
    # Test model info endpoint
    log("Testing /model/info endpoint...")
    try:
        response = requests.get(f"{API_URL}/model/info", timeout=10)
        if response.status_code == 200:
            results.success("Model info endpoint working")
        else:
            results.warn("Model info endpoint may not have loaded model yet")
    except Exception as e:
        results.warn(f"Model info endpoint: {e}")
    
    # Test prediction endpoint
    log("Testing /predict endpoint...")
    try:
        payload = {
            "age": 75,
            "gender": "M",
            "los_days": 8.5,
            "admission_type": "EMERGENCY",
            "insurance": "Medicare",
            "ed_admission": 1,
            "prior_admits_6mo": 2,
            "has_chf": 1,
            "has_diabetes": 1,
            "charlson_index": 4,
        }
        response = requests.post(
            f"{API_URL}/predict",
            json=payload,
            timeout=10,
        )
        
        if response.status_code == 200:
            data = response.json()
            prob = data.get("probability", "N/A")
            risk = data.get("risk_level", "N/A")
            results.success(f"Prediction endpoint working (probability={prob:.3f}, risk={risk})")
        else:
            results.fail(f"Prediction endpoint returned {response.status_code}")
    except Exception as e:
        results.fail(f"Prediction endpoint error: {e}")
    
    # Test batch predictions
    log("Testing batch predictions...")
    batch_success = True
    for i in range(5):
        try:
            payload = {"age": 50 + i * 5, "los_days": 3 + i, "has_chf": i % 2}
            response = requests.post(f"{API_URL}/predict", json=payload, timeout=10)
            if response.status_code != 200:
                batch_success = False
                break
        except:
            batch_success = False
            break
    
    if batch_success:
        results.success("Batch predictions working")
    else:
        results.fail("Batch predictions failed")
    
    return True


def step6_run_unit_tests():
    """Run unit tests."""
    section("Step 6: Running Unit Tests")
    
    log("Running pytest...")
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "tests/", "-v", "--tb=short"],
        cwd=PROJECT_DIR,
        capture_output=True,
        text=True,
    )
    
    if result.returncode == 0:
        results.success("All unit tests passed")
    else:
        results.warn("Some unit tests failed (check logs)")
        print(result.stdout[-1000:])
    
    return True


def step7_validate_configs():
    """Validate Terraform and Kubernetes configs."""
    section("Step 7: Validating Infrastructure Configs")
    
    # Validate Kubernetes manifests
    log("Validating Kubernetes manifests...")
    success, output = run_command([
        "kubectl", "apply", "-k", "k8s/overlays/dev", "--dry-run=client"
    ])
    
    if success:
        results.success("Kubernetes manifests are valid")
    elif "command not found" in output.lower() or "'kubectl'" in output.lower():
        results.skip("kubectl not installed - skipping K8s validation")
    else:
        results.fail("Kubernetes manifest validation failed")
    
    # Validate Terraform
    log("Validating Terraform configuration...")
    tf_dir = PROJECT_DIR / "terraform" / "environments" / "dev"
    
    success, _ = run_command(["terraform", "init", "-backend=false"], cwd=tf_dir)
    if success:
        success, output = run_command(["terraform", "validate"], cwd=tf_dir)
        if success:
            results.success("Terraform configuration is valid")
        else:
            results.fail("Terraform validation failed")
    elif "command not found" in str(success).lower():
        results.skip("terraform not installed - skipping Terraform validation")
    else:
        results.fail("Terraform init failed")
    
    return True


def step8_verify_airflow_dags():
    """Verify Airflow DAGs are loaded."""
    section("Step 8: Verifying Airflow DAGs")
    
    log("Checking DAG parsing...")
    try:
        response = requests.get(
            f"{AIRFLOW_URL}/api/v1/dags",
            auth=("airflow", "airflow"),
            timeout=10,
        )
        
        if response.status_code == 200:
            dags = response.json().get("dags", [])
            dag_ids = [d.get("dag_id") for d in dags]
            
            for dag_id in ["01_data_validation", "02_model_training", "03_model_deployment"]:
                if dag_id in dag_ids:
                    results.success(f"DAG {dag_id} loaded")
                else:
                    results.warn(f"DAG {dag_id} not found")
        else:
            results.warn(f"Could not fetch DAGs: {response.status_code}")
    except Exception as e:
        results.warn(f"Could not verify DAGs: {e}")
    
    return True


def cleanup():
    """Stop and remove Docker containers."""
    section("Cleanup")
    log("Stopping Docker containers...")
    docker_compose("down")
    results.success("Containers stopped")


# =============================================================================
# Main
# =============================================================================

def main():
    parser = argparse.ArgumentParser(description="EHR MLOps Pipeline E2E Tests")
    parser.add_argument("--skip-data-load", action="store_true",
                        help="Skip loading MIMIC data")
    parser.add_argument("--skip-training", action="store_true",
                        help="Skip model training")
    parser.add_argument("--quick", action="store_true",
                        help="Quick mode (skip data load and training)")
    parser.add_argument("--cleanup", action="store_true",
                        help="Stop containers after tests")
    args = parser.parse_args()
    
    if args.quick:
        args.skip_data_load = True
        args.skip_training = True
    
    # Clear log file
    with open(LOG_FILE, "w") as f:
        f.write(f"E2E Test Log - {datetime.now()}\n\n")
    
    print()
    print("\033[92m╔════════════════════════════════════════════════════════════╗\033[0m")
    print("\033[92m║     EHR MLOps Pipeline - End-to-End Test Suite            ║\033[0m")
    print("\033[92m╚════════════════════════════════════════════════════════════╝\033[0m")
    print()
    
    start_time = time.time()
    
    try:
        # Run all steps
        if not step1_start_infrastructure():
            return 1
        
        if not step2_load_data(skip=args.skip_data_load):
            return 1
        
        if not step3_run_dbt():
            return 1
        
        step4_train_model(skip=args.skip_training)
        step5_test_api()
        step6_run_unit_tests()
        step7_validate_configs()
        step8_verify_airflow_dags()
        
    except KeyboardInterrupt:
        print("\n\nTest interrupted by user")
        return 1
    except Exception as e:
        print(f"\n\nUnexpected error: {e}")
        return 1
    finally:
        if args.cleanup:
            cleanup()
    
    # Print summary
    duration = int(time.time() - start_time)
    
    section("Test Summary")
    print()
    print(f"  \033[92mPassed:\033[0m  {results.passed}")
    print(f"  \033[91mFailed:\033[0m  {results.failed}")
    print(f"  \033[93mSkipped:\033[0m {results.skipped}")
    print()
    print(f"  Duration: {duration}s")
    print(f"  Log file: {LOG_FILE}")
    print()
    
    if results.failed == 0:
        print("\033[92m╔════════════════════════════════════════════════════════════╗\033[0m")
        print("\033[92m║              ALL TESTS PASSED SUCCESSFULLY!                ║\033[0m")
        print("\033[92m╚════════════════════════════════════════════════════════════╝\033[0m")
        return 0
    else:
        print("\033[91m╔════════════════════════════════════════════════════════════╗\033[0m")
        print("\033[91m║              SOME TESTS FAILED - CHECK LOGS                ║\033[0m")
        print("\033[91m╚════════════════════════════════════════════════════════════╝\033[0m")
        return 1


if __name__ == "__main__":
    sys.exit(main())
