# MIMIC-IV Readmission Prediction MLOps Platform

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![FastAPI](https://img.shields.io/badge/FastAPI-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![Apache Airflow](https://img.shields.io/badge/Apache%20Airflow-017CEE?logo=apacheairflow&logoColor=white)](https://airflow.apache.org/)
[![Docker](https://img.shields.io/badge/Docker-2496ED?logo=docker&logoColor=white)](https://www.docker.com/)
[![Kubernetes](https://img.shields.io/badge/Kubernetes-326CE5?logo=kubernetes&logoColor=white)](https://kubernetes.io/)
[![Terraform](https://img.shields.io/badge/Terraform-7B42BC?logo=terraform&logoColor=white)](https://www.terraform.io/)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-4169E1?logo=postgresql&logoColor=white)](https://www.postgresql.org/)
[![dbt](https://img.shields.io/badge/dbt-FF694B?logo=dbt&logoColor=white)](https://www.getdbt.com/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

End-to-end MLOps platform for predicting 30-day hospital readmissions using MIMIC-IV clinical data. Demonstrates production-grade infrastructure, data engineering, and machine learning pipelines.

## Problem Statement

Hospital readmissions cost the US healthcare system **$26 billion annually**. CMS penalizes hospitals up to 3% of Medicare reimbursements for excessive readmission rates. This platform predicts which patients are at high risk of readmission within 30 days, enabling targeted interventions.

## Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              GitHub Actions CI/CD                           │
│              (lint → test → build → terraform → deploy → validate)          │
└─────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                         Terraform (Infrastructure as Code)                  │
│                VPC  │  EKS  │  S3  │  SQS  │  RDS PostgreSQL                │
└─────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                              Kubernetes (EKS)                               │
│                                                                             │
│  ┌──────────────────────────────────────────────────────────────────────┐   │
│  │                        Airflow (Orchestration)                       │   │
│  │                                                                      │   │
│  │   DAG 1: Data Validation    DAG 2: Training      DAG 3: Deployment   │   │
│  │   ┌──────────┬──────────┐ ┌──────────┬──────────┐ ┌────────┬────────┐│   │
│  │   │ Validate │   dbt    │→│  Train   │ Validate │→│Register│ Deploy ││   │
│  │   └──────────┴──────────┘ └──────────┴──────────┘ └────────┴────────┘│   │
│  │         (scheduled)            (triggered)            (triggered)    │   │
│  └──────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│     ┌───────────────────┐  ┌───────────────────┐  ┌───────────────────┐     │
│     │   Model Serving   │  │   Prediction API  │  │   Airflow Web UI  │     │
│     │   (HPA: 2-10)     │  │   (FastAPI)       │  │                   │     │
│     └───────────────────┘  └───────────────────┘  └───────────────────┘     │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                              Data Layer                                     │
│                                                                             │
│   S3 (MinIO)              PostgreSQL                    SQS (LocalStack)    │
│   ├── raw/mimic-iv/       ├── airflow_db                ├── training-queue  │
│   ├── processed/          ├── mimic (features)          └── prediction-queue│
│   └── models/             └── model_registry                                │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Technology Stack

| Layer | Local (Docker) | AWS (Production) |
|-------|----------------|------------------|
| **Orchestration** | Airflow 2.8 | Airflow on EKS |
| **Infrastructure** | Terraform (validate) | Terraform (apply) |
| **Containers** | Docker Compose | EKS |
| **Object Storage** | MinIO | S3 |
| **Message Queue** | LocalStack | SQS |
| **Database** | PostgreSQL 15 | RDS PostgreSQL |
| **Data Transform** | dbt Core 1.9 | dbt Core |
| **ML Training** | XGBoost, scikit-learn | Same |
| **Model Serving** | FastAPI | FastAPI + HPA |
| **CI/CD** | GitHub Actions | GitHub Actions |

## Project Structure

```
ehr-mlops-pipeline/
├── .github/workflows/           # CI/CD pipelines
│   └── ci-cd.yaml
│
├── airflow/                     # Airflow DAGs & logs
│   └── dags/
│       ├── 01_data_validation.py
│       ├── 02_model_training.py
│       └── 03_model_deployment.py
│
├── data/                        # MIMIC-IV data (gitignored)
│   └── mimic-iv/hosp/
│
├── dbt/                         # Data transformations
│   ├── models/
│   │   ├── staging/             # stg_patients, stg_admissions, etc.
│   │   ├── intermediate/        # int_comorbidities, int_lab_summary, etc.
│   │   └── marts/               # fct_readmission_features
│   ├── dbt_project.yml
│   └── profiles.yml
│
├── docker/                      # Dockerfiles
│   ├── Dockerfile.serving
│   └── Dockerfile.training
│
├── k8s/                         # Kubernetes manifests
│   ├── base/
│   └── overlays/dev/
│
├── scripts/                     # Utility scripts
│   ├── e2e-test.sh              # End-to-end test (Bash)
│   ├── e2e_test.py              # End-to-end test (Python)
│   ├── smoke-test.sh            # Quick health checks
│   ├── wait-for-services.sh     # Wait for Docker services
│   ├── run-dbt.sh               # Run dbt transformations
│   ├── train-model.sh           # Train ML model
│   ├── deploy-model.sh          # Deploy model to API
│   ├── load_mimic_data.py       # Load MIMIC data to PostgreSQL
│   ├── init-databases.sh        # Initialize databases
│   └── init-localstack.sh       # Initialize LocalStack
│
├── src/                         # Application code
│   ├── common/                  # Shared utilities
│   ├── training/                # Model training (train.py)
│   └── serving/                 # FastAPI application (main.py)
│
├── terraform/                   # Infrastructure as Code
│   ├── modules/
│   │   ├── vpc/
│   │   ├── eks/
│   │   ├── s3/
│   │   ├── sqs/
│   │   └── rds/
│   └── environments/dev/
│
├── tests/                       # Test suites
│   ├── unit/                    # Unit tests
│   ├── integration/             # Integration tests
│   └── conftest.py              # Pytest fixtures
│
├── docker-compose.yaml          # Local development stack
├── requirements.txt             # Python dependencies
├── pytest.ini                   # Pytest configuration
├── TESTING.md                   # Testing documentation
└── README.md
```

## Quick Start

### Prerequisites

- **Docker Desktop** (with Docker Compose)
- **Python 3.11+**
- **MIMIC-IV data** from [PhysioNet](https://physionet.org/content/mimiciv/3.1/) (requires credentialing)

### 1. Clone and Setup

```bash
git clone https://github.com/sanidhya-karnik/ehr-mlops-pipeline.git
cd ehr-mlops-pipeline

# Create Python environment
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Add MIMIC-IV Data

```bash
# After downloading from PhysioNet, place files in:
# data/mimic-iv/hosp/
#   ├── patients.csv
#   ├── admissions.csv
#   ├── diagnoses_icd.csv
#   ├── labevents.csv
#   └── prescriptions.csv
```

### 3. Start Infrastructure

```bash
# Start all services
docker-compose up -d

# Wait for services to be healthy
./scripts/wait-for-services.sh  # Linux/Mac
# Or check manually: docker-compose ps
```

### 4. Load Data & Run Pipeline

```bash
# Load MIMIC-IV data into PostgreSQL
python scripts/load_mimic_data.py

# Run dbt transformations
./scripts/run-dbt.sh

# Train the model
./scripts/train-model.sh

# Start the API (if not already running)
docker-compose up -d model-api
```

### 5. Make Predictions

```bash
# Health check
curl http://localhost:8000/health

# Make a prediction
curl -X POST http://localhost:8000/predict \
  -H "Content-Type: application/json" \
  -d '{
    "age": 75,
    "gender": "M",
    "los_days": 8.5,
    "admission_type": "EMERGENCY",
    "ed_admission": 1,
    "prior_admits_6mo": 2,
    "has_chf": 1,
    "has_diabetes": 1,
    "charlson_index": 4
  }'
```

**Response:**
```json
{
  "probability": 0.67,
  "prediction": 1,
  "risk_level": "MEDIUM",
  "model_version": "20240201_143052",
  "latency_ms": 12.5
}
```

## Pipeline DAGs

The platform uses three Airflow DAGs that cascade automatically:

| DAG | Schedule | Trigger | Description |
|-----|----------|---------|-------------|
| `01_data_validation` | Daily 2 AM | Manual/Schedule | Validates source data, runs dbt |
| `02_model_training` | None | DAG 1 success | Trains XGBoost model, validates AUC > 0.70 |
| `03_model_deployment` | None | DAG 2 success | Registers model, deploys to API |

**Access Airflow UI:** http://localhost:8080 (airflow / airflow)

## Data Pipeline

### MIMIC-IV Tables Used

| Table | Purpose | Size |
|-------|---------|------|
| `patients` | Demographics | ~300K |
| `admissions` | Hospital visits | ~500K |
| `diagnoses_icd` | Diagnosis codes | ~5M |
| `labevents` | Lab results | ~120M → ~15M (filtered) |
| `prescriptions` | Medications | ~17M |

### dbt Model Layers

```
Raw (CSV files)
    │
    ▼
Staging (stg_*)           ← Clean, cast types, filter nulls
    │
    ▼
Intermediate (int_*)      ← Calculate scores, aggregate values
    │
    ▼
Marts (fct_*)             ← Final ML-ready feature table
```

### Features Engineered (50+)

| Category | Features |
|----------|----------|
| **Demographics** | age, gender |
| **Admission** | admission_type, insurance, los_days, ed_admission |
| **History** | prior_admits_6mo, prior_admits_12mo, prior_ed_visits_6mo, avg_prior_los |
| **Comorbidities** | has_chf, has_diabetes, has_ckd, has_copd, has_hypertension, has_cancer, charlson_index |
| **Labs** | creatinine_max/avg, glucose_max/avg, hemoglobin_min/avg, wbc_max/avg, sodium_min/max, potassium_min/max, bun_max, platelet_min, abnormal_lab_count/ratio |
| **Medications** | unique_med_count, high_risk_med_count, on_anticoagulant, on_insulin, on_opioid, polypharmacy, severe_polypharmacy |
| **Target** | readmitted_30d (binary) |

## Testing

### Quick Commands

```bash
# Unit tests (no services required)
pytest tests/unit -v

# Integration tests (requires running services)
pytest tests/integration -v

# Quick smoke test
./scripts/smoke-test.sh

# Full end-to-end test
./scripts/e2e-test.sh           # Bash (Linux/Mac/WSL)
python scripts/e2e_test.py      # Python (cross-platform)
```

### Test Options

| Command | Duration | Description |
|---------|----------|-------------|
| `pytest tests/unit -v` | ~10s | Unit tests only |
| `./scripts/smoke-test.sh` | ~5s | Quick health checks |
| `./scripts/e2e-test.sh --quick` | ~3min | Skip data load & training |
| `./scripts/e2e-test.sh` | ~15min | Full pipeline test |
| `python scripts/e2e_test.py --help` | - | See all options |

### E2E Test Coverage

The automated E2E test verifies:

- ✅ Docker infrastructure starts correctly
- ✅ MIMIC-IV data loads into PostgreSQL
- ✅ dbt transformations complete successfully
- ✅ ML model trains with AUC > 0.70
- ✅ Prediction API responds correctly
- ✅ Unit tests pass
- ✅ Kubernetes manifests are valid
- ✅ Terraform configuration is valid
- ✅ Airflow DAGs are loaded

See [TESTING.md](TESTING.md) for comprehensive testing documentation.

## Model Performance

| Metric | Value |
|--------|-------|
| **AUC-ROC** | 0.72 |
| **Precision** | 0.35 |
| **Recall** | 0.61 |
| **F1 Score** | 0.45 |

*Baseline readmission rate in MIMIC-IV: 20.7%*

### Top Predictive Features (SHAP Importance)

| Rank | Feature | Importance |
|------|---------|------------|
| 1 | prior_admits_6mo | 11.7% |
| 2 | has_cancer | 8.4% |
| 3 | prior_admits_12mo | 8.0% |
| 4 | abnormal_lab_count | 6.8% |
| 5 | los_days | 4.5% |
| 6 | admission_type | 4.2% |
| 7 | discharge_location | 4.2% |
| 8 | age | 3.7% |
| 9 | ed_admission | 3.3% |
| 10 | hemoglobin_avg | 3.2% |

## Model Explainability (SHAP)

The platform includes comprehensive SHAP (SHapley Additive exPlanations) analysis for model interpretability.

### Generate SHAP Report

```bash
# Generate full SHAP analysis report
./scripts/run-shap-analysis.sh

# Or using Python (Windows compatible)
python scripts/run_shap_analysis.py --sample-size 1000
```

### SHAP Outputs

| File | Description |
|------|-------------|
| `shap_summary.png` | Beeswarm plot showing feature impact distribution |
| `shap_feature_importance.png` | Bar chart of mean absolute SHAP values |
| `shap_waterfall_*.png` | Individual patient explanations |
| `shap_dependence_*.png` | Feature dependence plots |
| `feature_importance.csv` | Ranked feature importance |

### Real-time Explanations via API

```bash
# Get explanation for a prediction
curl -X POST http://localhost:8000/explain \
  -H "Content-Type: application/json" \
  -d '{
    "age": 75,
    "los_days": 8.5,
    "has_chf": 1,
    "prior_admits_6mo": 2,
    "charlson_index": 4
  }'
```

**Response:**
```json
{
  "probability": 0.91,
  "risk_level": "HIGH",
  "base_value": 0.0,
  "top_risk_factors": [
    {"feature": "discharge_location", "shap_value": 1.43},
    {"feature": "prior_admits_6mo", "value": 2.0, "shap_value": 0.39},
    {"feature": "high_risk_med_count", "shap_value": 0.22},
    {"feature": "abnormal_lab_count", "shap_value": 0.21}
  ],
  "top_protective_factors": [
    {"feature": "discharge_hour", "shap_value": -0.26},
    {"feature": "age", "value": 75.0, "shap_value": -0.15},
    {"feature": "insurance", "shap_value": -0.10}
  ]
}
```

## Service Endpoints

| Service | URL | Credentials |
|---------|-----|-------------|
| **Airflow UI** | http://localhost:8080 | airflow / airflow |
| **Prediction API** | http://localhost:8000 | - |
| **API Docs** | http://localhost:8000/docs | - |
| **MinIO Console** | http://localhost:9001 | minioadmin / minioadmin |
| **PostgreSQL** | localhost:5432 | mimic / mimic_password |

## Configuration

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `DB_HOST` | postgres | Database host |
| `DB_PORT` | 5432 | Database port |
| `DB_NAME` | mimic | Database name |
| `DB_USER` | mimic | Database user |
| `DB_PASSWORD` | mimic_password | Database password |
| `S3_ENDPOINT_URL` | http://minio:9000 | MinIO/S3 endpoint |
| `AWS_ACCESS_KEY_ID` | minioadmin | S3 access key |
| `AWS_SECRET_ACCESS_KEY` | minioadmin | S3 secret key |

### Validate Infrastructure

```bash
# Terraform
cd terraform/environments/dev
terraform init -backend=false
terraform validate
terraform plan -var="database_password=test"

# Kubernetes
kubectl apply -k k8s/overlays/dev --dry-run=client
```

## Troubleshooting

| Issue | Solution |
|-------|----------|
| Port already in use | `docker-compose down` then restart |
| Database connection refused | Wait 30-60s for PostgreSQL to initialize |
| dbt fails to connect | Use `DB_HOST=localhost` for local runs, `DB_HOST=postgres` in Docker |
| Model API returns 503 | Model not loaded - run training first, then `curl -X POST http://localhost:8000/model/reload` |
| Airflow DAG not visible | Restart scheduler: `docker-compose restart airflow-scheduler` |
| Out of memory | Increase Docker memory limit to 8GB+ |

### View Logs

```bash
# All services
docker-compose logs -f

# Specific service
docker-compose logs -f model-api
docker-compose logs -f airflow-scheduler

# E2E test log
cat e2e-test.log
```

### Reset Everything

```bash
# Stop containers
docker-compose down

# Stop and remove all data
docker-compose down -v

# Full reset including images
docker-compose down -v --rmi local
```

## Documentation

- [TESTING.md](TESTING.md) - Comprehensive testing guide
- [API Docs](http://localhost:8000/docs) - FastAPI Swagger UI (when running)

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## References

If you use this project or MIMIC-IV data, please cite:

**MIMIC-IV Dataset:**
> Johnson, A., Bulgarelli, L., Pollard, T., Gow, B., Moody, B., Horng, S., Celi, L. A., & Mark, R. (2024). MIMIC-IV (version 3.1). *PhysioNet*. https://doi.org/10.13026/kpb9-mt58

**Original Publication:**
> Johnson, A.E.W., Bulgarelli, L., Shen, L. et al. MIMIC-IV, a freely accessible electronic health record dataset. *Sci Data* 10, 1 (2023). https://doi.org/10.1038/s41597-022-01899-x

**PhysioNet:**
> Goldberger, A., Amaral, L., Glass, L., Hausdorff, J., Ivanov, P. C., Mark, R., ... & Stanley, H. E. (2000). PhysioBank, PhysioToolkit, and PhysioNet: Components of a new research resource for complex physiologic signals. *Circulation* 101(23), e215–e220.

## Acknowledgments

- [MIMIC-IV](https://physionet.org/content/mimiciv/3.1/) - Clinical database from PhysioNet
- [PhysioNet](https://physionet.org/) - Research resource for complex physiologic signals

---

**Note:** MIMIC-IV data requires credentialed access through PhysioNet. This project does not include any patient data.
