"""
Pytest configuration and shared fixtures.
"""

import os
import sys
from pathlib import Path

import pytest

# Add src to path for imports
PROJECT_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_DIR / "src"))


# =============================================================================
# Markers
# =============================================================================

def pytest_configure(config):
    """Register custom markers."""
    config.addinivalue_line("markers", "unit: Unit tests (no external dependencies)")
    config.addinivalue_line("markers", "integration: Integration tests (require services)")
    config.addinivalue_line("markers", "slow: Slow tests (>10 seconds)")
    config.addinivalue_line("markers", "smoke: Quick smoke tests")


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture(scope="session")
def project_dir():
    """Return project root directory."""
    return PROJECT_DIR


@pytest.fixture(scope="session")
def db_config():
    """Return database configuration."""
    return {
        "host": os.getenv("DB_HOST", "localhost"),
        "port": int(os.getenv("DB_PORT", "5432")),
        "database": os.getenv("DB_NAME", "mimic"),
        "user": os.getenv("DB_USER", "mimic"),
        "password": os.getenv("DB_PASSWORD", "mimic_password"),
    }


@pytest.fixture(scope="session")
def s3_config():
    """Return S3/MinIO configuration."""
    return {
        "endpoint_url": os.getenv("S3_ENDPOINT_URL", "http://localhost:9000"),
        "aws_access_key_id": os.getenv("AWS_ACCESS_KEY_ID", "minioadmin"),
        "aws_secret_access_key": os.getenv("AWS_SECRET_ACCESS_KEY", "minioadmin"),
        "bucket": os.getenv("S3_BUCKET_MODELS", "mimic-models"),
    }


@pytest.fixture(scope="session")
def api_url():
    """Return API base URL."""
    return os.getenv("API_URL", "http://localhost:8000")


# =============================================================================
# Skip Conditions
# =============================================================================

@pytest.fixture(scope="session")
def skip_if_no_docker():
    """Skip test if Docker is not available."""
    import subprocess
    try:
        subprocess.run(["docker", "info"], capture_output=True, check=True)
    except (subprocess.CalledProcessError, FileNotFoundError):
        pytest.skip("Docker not available")


@pytest.fixture(scope="session")
def skip_if_no_services(api_url):
    """Skip test if services are not running."""
    import requests
    try:
        requests.get(f"{api_url}/health/live", timeout=5)
    except requests.RequestException:
        pytest.skip("Services not running. Start with: docker-compose up -d")
