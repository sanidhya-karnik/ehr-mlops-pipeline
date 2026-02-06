# Testing Guide

This document describes how to test the EHR MLOps Pipeline end-to-end.

## Quick Start

```bash
# Option 1: Full automated E2E test (Bash - Linux/Mac/WSL)
./scripts/e2e-test.sh

# Option 2: Full automated E2E test (Python - cross-platform)
python scripts/e2e_test.py

# Option 3: Quick smoke test
./scripts/smoke-test.sh
```

## Test Types

| Type | Command | Duration | Description |
|------|---------|----------|-------------|
| Unit | `pytest tests/unit` | ~10s | No external dependencies |
| Integration | `pytest tests/integration` | ~60s | Requires running services |
| Smoke | `./scripts/smoke-test.sh` | ~5s | Quick health checks |
| E2E | `./scripts/e2e-test.sh` | ~15min | Full pipeline test |

## Prerequisites

1. **Docker Desktop** installed and running
2. **Python 3.11+** with requirements installed
3. **MIMIC-IV data** in `data/mimic-iv/hosp/` (for full E2E tests)

```bash
# Install Python dependencies
pip install -r requirements.txt
```

## Running Tests

### 1. Unit Tests (No Services Required)

```bash
# Run all unit tests
pytest tests/unit -v

# Run with coverage
pytest tests/unit -v --cov=src --cov-report=html

# Run specific test file
pytest tests/unit/test_pipeline.py -v
```

### 2. Integration Tests (Services Required)

First, start the infrastructure:

```bash
docker-compose up -d
./scripts/wait-for-services.sh
```

Then run integration tests:

```bash
pytest tests/integration -v -s
```

### 3. Smoke Tests

Quick verification that all services are running:

```bash
./scripts/smoke-test.sh
```

Expected output:
```
✓ Docker running
✓ PostgreSQL
✓ Redis
✓ MinIO
✓ Airflow
✓ LocalStack
```

### 4. Full End-to-End Tests

#### Using Bash (Linux/Mac/WSL)

```bash
# Full test (includes data loading and training)
./scripts/e2e-test.sh

# Skip data loading (if already loaded)
./scripts/e2e-test.sh --skip-data-load

# Skip training (if model already exists)
./scripts/e2e-test.sh --skip-training

# Quick mode (skip both)
./scripts/e2e-test.sh --quick

# Cleanup after tests
./scripts/e2e-test.sh --cleanup
```

#### Using Python (Cross-Platform)

```bash
# Full test
python scripts/e2e_test.py

# With options
python scripts/e2e_test.py --skip-data-load
python scripts/e2e_test.py --skip-training
python scripts/e2e_test.py --quick
python scripts/e2e_test.py --cleanup
```

## E2E Test Steps

The automated E2E test performs these steps:

| Step | Description | Duration |
|------|-------------|----------|
| 1 | Start Docker infrastructure | ~60s |
| 2 | Load MIMIC-IV data | ~5-10min |
| 3 | Run dbt transformations | ~2-3min |
| 4 | Train ML model | ~3-5min |
| 5 | Test prediction API | ~30s |
| 6 | Run unit tests | ~10s |
| 7 | Validate configs | ~10s |
| 8 | Verify Airflow DAGs | ~10s |

## Manual Testing

### Test the Prediction API

```bash
# Health check
curl http://localhost:8000/health

# Model info
curl http://localhost:8000/model/info

# Make a prediction
curl -X POST http://localhost:8000/predict \
  -H "Content-Type: application/json" \
  -d '{
    "age": 75,
    "gender": "M",
    "los_days": 8.5,
    "admission_type": "EMERGENCY",
    "insurance": "Medicare",
    "ed_admission": 1,
    "prior_admits_6mo": 2,
    "has_chf": 1,
    "has_diabetes": 1,
    "charlson_index": 4
  }'
```

### Test Airflow DAGs

1. Open http://localhost:8080
2. Login: `airflow` / `airflow`
3. Enable and trigger `01_data_validation`
4. Watch the pipeline cascade through all DAGs

### Test dbt Models

```bash
cd dbt
export DB_HOST=localhost
dbt run --profiles-dir . --project-dir .
dbt test --profiles-dir . --project-dir .
```

## Troubleshooting

### Common Issues

| Issue | Solution |
|-------|----------|
| Port already in use | `docker-compose down` then restart |
| Database connection refused | Wait 30s for PostgreSQL to initialize |
| dbt fails to connect | Use `DB_HOST=localhost` for local runs |
| API can't find model | Run training first, then reload |
| Tests timeout | Increase timeout in pytest.ini |

### View Logs

```bash
# All services
docker-compose logs

# Specific service
docker-compose logs airflow-scheduler
docker-compose logs model-api

# E2E test log
cat e2e-test.log
```

### Reset Everything

```bash
# Stop and remove all containers and volumes
docker-compose down -v

# Remove built images
docker-compose down --rmi local

# Start fresh
docker-compose up -d
```

## CI/CD Testing

The GitHub Actions workflow runs these tests automatically:

```yaml
# .github/workflows/ci-cd.yaml
jobs:
  lint-test:
    - pytest tests/ -v --tb=short
  
  terraform:
    - terraform validate
  
  kubernetes:
    - kubectl apply --dry-run=client
  
  dbt:
    - dbt parse
```

## Test Coverage

Generate coverage report:

```bash
pytest tests/unit -v --cov=src --cov-report=html
open htmlcov/index.html
```

## Writing New Tests

### Unit Test Template

```python
# tests/unit/test_example.py
import pytest

class TestExample:
    def test_something(self):
        assert True
    
    @pytest.mark.slow
    def test_slow_operation(self):
        # Long running test
        pass
```

### Integration Test Template

```python
# tests/integration/test_example.py
import pytest

class TestExample:
    def test_api_endpoint(self, api_session):
        response = api_session.get("http://localhost:8000/health")
        assert response.status_code == 200
```
