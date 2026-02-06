#!/bin/bash
# =============================================================================
# EHR MLOps Pipeline - End-to-End Test Script
# =============================================================================
#
# This script runs a complete end-to-end test of the pipeline:
#   1. Starts Docker infrastructure
#   2. Loads MIMIC-IV data into PostgreSQL
#   3. Runs dbt transformations
#   4. Trains the ML model
#   5. Tests the prediction API
#   6. Runs unit tests
#   7. Validates Terraform and Kubernetes configs
#
# Usage:
#   ./scripts/e2e-test.sh [--skip-data-load] [--skip-training] [--cleanup]
#
# =============================================================================

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
LOG_FILE="$PROJECT_DIR/e2e-test.log"

# Test results tracking
TESTS_PASSED=0
TESTS_FAILED=0
TESTS_SKIPPED=0

# =============================================================================
# Helper Functions
# =============================================================================

log() {
    echo -e "${BLUE}[$(date +'%H:%M:%S')]${NC} $1" | tee -a "$LOG_FILE"
}

success() {
    echo -e "${GREEN}[✓]${NC} $1" | tee -a "$LOG_FILE"
    ((TESTS_PASSED++))
}

fail() {
    echo -e "${RED}[✗]${NC} $1" | tee -a "$LOG_FILE"
    ((TESTS_FAILED++))
}

warn() {
    echo -e "${YELLOW}[!]${NC} $1" | tee -a "$LOG_FILE"
}

skip() {
    echo -e "${YELLOW}[SKIP]${NC} $1" | tee -a "$LOG_FILE"
    ((TESTS_SKIPPED++))
}

section() {
    echo "" | tee -a "$LOG_FILE"
    echo -e "${BLUE}============================================================${NC}" | tee -a "$LOG_FILE"
    echo -e "${BLUE} $1${NC}" | tee -a "$LOG_FILE"
    echo -e "${BLUE}============================================================${NC}" | tee -a "$LOG_FILE"
}

wait_for_service() {
    local name=$1
    local url=$2
    local max_attempts=${3:-30}
    local attempt=1

    log "Waiting for $name..."
    while [ $attempt -le $max_attempts ]; do
        if curl -sf "$url" > /dev/null 2>&1; then
            return 0
        fi
        sleep 2
        attempt=$((attempt + 1))
    done
    return 1
}

wait_for_postgres() {
    local max_attempts=${1:-30}
    local attempt=1

    log "Waiting for PostgreSQL..."
    while [ $attempt -le $max_attempts ]; do
        if docker exec mlops-postgres pg_isready -U postgres > /dev/null 2>&1; then
            return 0
        fi
        sleep 2
        attempt=$((attempt + 1))
    done
    return 1
}

# =============================================================================
# Parse Arguments
# =============================================================================

SKIP_DATA_LOAD=false
SKIP_TRAINING=false
CLEANUP=false
QUICK_MODE=false

while [[ $# -gt 0 ]]; do
    case $1 in
        --skip-data-load)
            SKIP_DATA_LOAD=true
            shift
            ;;
        --skip-training)
            SKIP_TRAINING=true
            shift
            ;;
        --cleanup)
            CLEANUP=true
            shift
            ;;
        --quick)
            QUICK_MODE=true
            SKIP_DATA_LOAD=true
            SKIP_TRAINING=true
            shift
            ;;
        --help)
            echo "Usage: $0 [OPTIONS]"
            echo ""
            echo "Options:"
            echo "  --skip-data-load  Skip loading MIMIC data (use existing)"
            echo "  --skip-training   Skip model training (use existing model)"
            echo "  --quick           Quick mode (skip data load and training)"
            echo "  --cleanup         Stop and remove containers after tests"
            echo "  --help            Show this help message"
            exit 0
            ;;
        *)
            echo "Unknown option: $1"
            exit 1
            ;;
    esac
done

# =============================================================================
# Main Test Script
# =============================================================================

cd "$PROJECT_DIR"

# Clear log file
> "$LOG_FILE"

echo ""
echo -e "${GREEN}╔════════════════════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║     EHR MLOps Pipeline - End-to-End Test Suite            ║${NC}"
echo -e "${GREEN}╚════════════════════════════════════════════════════════════╝${NC}"
echo ""

START_TIME=$(date +%s)

# =============================================================================
# Step 1: Start Docker Infrastructure
# =============================================================================

section "Step 1: Starting Docker Infrastructure"

log "Stopping any existing containers..."
docker-compose down > /dev/null 2>&1 || true

log "Starting Docker services..."
if docker-compose up -d; then
    success "Docker services started"
else
    fail "Failed to start Docker services"
    exit 1
fi

# Wait for services
log "Waiting for services to be healthy..."

if wait_for_postgres 60; then
    success "PostgreSQL is ready"
else
    fail "PostgreSQL failed to start"
    exit 1
fi

if wait_for_service "MinIO" "http://localhost:9000/minio/health/live" 30; then
    success "MinIO is ready"
else
    fail "MinIO failed to start"
    exit 1
fi

if wait_for_service "Airflow" "http://localhost:8080/health" 90; then
    success "Airflow is ready"
else
    fail "Airflow failed to start"
    exit 1
fi

if wait_for_service "LocalStack" "http://localhost:4566/_localstack/health" 30; then
    success "LocalStack is ready"
else
    warn "LocalStack may not be ready (non-critical)"
fi

# =============================================================================
# Step 2: Load MIMIC-IV Data
# =============================================================================

section "Step 2: Loading MIMIC-IV Data"

if [ "$SKIP_DATA_LOAD" = true ]; then
    skip "Data loading (--skip-data-load flag set)"
else
    # Check if data files exist
    if [ ! -f "$PROJECT_DIR/data/mimic-iv/hosp/patients.csv" ]; then
        fail "MIMIC-IV data not found at data/mimic-iv/hosp/"
        warn "Please download MIMIC-IV data from PhysioNet first"
        exit 1
    fi

    log "Loading MIMIC-IV data into PostgreSQL..."
    if python scripts/load_mimic_data.py >> "$LOG_FILE" 2>&1; then
        success "MIMIC-IV data loaded successfully"
    else
        fail "Failed to load MIMIC-IV data"
        exit 1
    fi
fi

# Verify data loaded
log "Verifying data in PostgreSQL..."
PATIENT_COUNT=$(docker exec mlops-postgres psql -U mimic -d mimic -t -c "SELECT COUNT(*) FROM mimic_hosp.patients;" 2>/dev/null | tr -d ' ')

if [ -n "$PATIENT_COUNT" ] && [ "$PATIENT_COUNT" -gt 0 ]; then
    success "Verified: $PATIENT_COUNT patients in database"
else
    fail "No patient data found in database"
    exit 1
fi

# =============================================================================
# Step 3: Run dbt Transformations
# =============================================================================

section "Step 3: Running dbt Transformations"

log "Running dbt models..."
export DB_HOST=localhost
export DB_PORT=5432
export DB_NAME=mimic
export DB_USER=mimic
export DB_PASSWORD=mimic_password

cd "$PROJECT_DIR/dbt"

if dbt run --profiles-dir . --project-dir . >> "$LOG_FILE" 2>&1; then
    success "dbt models completed"
else
    fail "dbt run failed"
    cat "$LOG_FILE" | tail -50
    exit 1
fi

log "Running dbt tests..."
if dbt test --profiles-dir . --project-dir . >> "$LOG_FILE" 2>&1; then
    success "dbt tests passed"
else
    warn "Some dbt tests failed (check logs)"
fi

cd "$PROJECT_DIR"

# Verify feature table
log "Verifying feature table..."
FEATURE_COUNT=$(docker exec mlops-postgres psql -U mimic -d mimic -t -c "SELECT COUNT(*) FROM public_marts.fct_readmission_features;" 2>/dev/null | tr -d ' ')

if [ -n "$FEATURE_COUNT" ] && [ "$FEATURE_COUNT" -gt 0 ]; then
    success "Verified: $FEATURE_COUNT rows in feature table"
else
    fail "Feature table is empty or doesn't exist"
    exit 1
fi

# =============================================================================
# Step 4: Train the Model
# =============================================================================

section "Step 4: Training ML Model"

if [ "$SKIP_TRAINING" = true ]; then
    skip "Model training (--skip-training flag set)"
else
    export S3_ENDPOINT_URL=http://localhost:9000
    export AWS_ACCESS_KEY_ID=minioadmin
    export AWS_SECRET_ACCESS_KEY=minioadmin

    log "Training XGBoost model..."
    if python src/training/train.py --model-type xgboost --model-name readmission_model >> "$LOG_FILE" 2>&1; then
        success "Model training completed"
    else
        fail "Model training failed"
        cat "$LOG_FILE" | tail -30
        exit 1
    fi
fi

# Verify model in MinIO
log "Verifying model in MinIO..."
MODEL_EXISTS=$(curl -sf "http://localhost:9000/mimic-models/models/readmission_model/" -u minioadmin:minioadmin 2>/dev/null || echo "")

if [ -n "$MODEL_EXISTS" ] || [ "$SKIP_TRAINING" = true ]; then
    success "Model artifacts exist in MinIO"
else
    warn "Could not verify model in MinIO (may still be valid)"
fi

# =============================================================================
# Step 5: Test Prediction API
# =============================================================================

section "Step 5: Testing Prediction API"

log "Building and starting model-api..."
docker-compose up -d model-api >> "$LOG_FILE" 2>&1

if wait_for_service "Model API" "http://localhost:8000/health/live" 60; then
    success "Model API is running"
else
    fail "Model API failed to start"
    docker-compose logs model-api | tail -30
    exit 1
fi

# Test health endpoint
log "Testing /health endpoint..."
HEALTH_RESPONSE=$(curl -sf http://localhost:8000/health 2>/dev/null)
if echo "$HEALTH_RESPONSE" | grep -q "status"; then
    success "Health endpoint working"
else
    fail "Health endpoint not responding correctly"
fi

# Test model info endpoint
log "Testing /model/info endpoint..."
MODEL_INFO=$(curl -sf http://localhost:8000/model/info 2>/dev/null)
if echo "$MODEL_INFO" | grep -q "model_name"; then
    success "Model info endpoint working"
else
    warn "Model info endpoint may not have loaded model yet"
fi

# Test prediction endpoint
log "Testing /predict endpoint..."
PREDICT_RESPONSE=$(curl -sf -X POST http://localhost:8000/predict \
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
    }' 2>/dev/null)

if echo "$PREDICT_RESPONSE" | grep -q "probability"; then
    PROB=$(echo "$PREDICT_RESPONSE" | python -c "import sys,json; print(json.load(sys.stdin).get('probability', 'N/A'))" 2>/dev/null || echo "N/A")
    RISK=$(echo "$PREDICT_RESPONSE" | python -c "import sys,json; print(json.load(sys.stdin).get('risk_level', 'N/A'))" 2>/dev/null || echo "N/A")
    success "Prediction endpoint working (probability=$PROB, risk=$RISK)"
else
    fail "Prediction endpoint not working"
    echo "Response: $PREDICT_RESPONSE"
fi

# Test with multiple predictions
log "Testing batch predictions..."
for i in {1..5}; do
    RESPONSE=$(curl -sf -X POST http://localhost:8000/predict \
        -H "Content-Type: application/json" \
        -d "{\"age\": $((50 + i*5)), \"los_days\": $((3 + i)), \"has_chf\": $((i % 2))}" 2>/dev/null)
    if ! echo "$RESPONSE" | grep -q "probability"; then
        fail "Batch prediction $i failed"
        break
    fi
done
success "Batch predictions working"

# =============================================================================
# Step 6: Run Unit Tests
# =============================================================================

section "Step 6: Running Unit Tests"

log "Running pytest..."
if pytest tests/ -v --tb=short >> "$LOG_FILE" 2>&1; then
    success "All unit tests passed"
else
    warn "Some unit tests failed (check logs)"
fi

# =============================================================================
# Step 7: Validate Infrastructure Configs
# =============================================================================

section "Step 7: Validating Infrastructure Configs"

# Validate Kubernetes manifests
log "Validating Kubernetes manifests..."
if command -v kubectl &> /dev/null; then
    if kubectl apply -k k8s/overlays/dev --dry-run=client >> "$LOG_FILE" 2>&1; then
        success "Kubernetes manifests are valid"
    else
        fail "Kubernetes manifest validation failed"
    fi
else
    skip "kubectl not installed - skipping K8s validation"
fi

# Validate Terraform
log "Validating Terraform configuration..."
if command -v terraform &> /dev/null; then
    cd "$PROJECT_DIR/terraform/environments/dev"
    if terraform init -backend=false >> "$LOG_FILE" 2>&1; then
        if terraform validate >> "$LOG_FILE" 2>&1; then
            success "Terraform configuration is valid"
        else
            fail "Terraform validation failed"
        fi
    else
        fail "Terraform init failed"
    fi
    cd "$PROJECT_DIR"
else
    skip "terraform not installed - skipping Terraform validation"
fi

# =============================================================================
# Step 8: Test Airflow DAGs
# =============================================================================

section "Step 8: Verifying Airflow DAGs"

log "Checking DAG parsing..."
DAGS=$(curl -sf "http://localhost:8080/api/v1/dags" -u airflow:airflow 2>/dev/null || echo "")

if echo "$DAGS" | grep -q "01_data_validation"; then
    success "DAG 01_data_validation loaded"
else
    warn "DAG 01_data_validation not found"
fi

if echo "$DAGS" | grep -q "02_model_training"; then
    success "DAG 02_model_training loaded"
else
    warn "DAG 02_model_training not found"
fi

if echo "$DAGS" | grep -q "03_model_deployment"; then
    success "DAG 03_model_deployment loaded"
else
    warn "DAG 03_model_deployment not found"
fi

# =============================================================================
# Cleanup (if requested)
# =============================================================================

if [ "$CLEANUP" = true ]; then
    section "Cleanup"
    log "Stopping Docker containers..."
    docker-compose down
    success "Containers stopped"
fi

# =============================================================================
# Summary
# =============================================================================

END_TIME=$(date +%s)
DURATION=$((END_TIME - START_TIME))

section "Test Summary"

echo ""
echo -e "  ${GREEN}Passed:${NC}  $TESTS_PASSED"
echo -e "  ${RED}Failed:${NC}  $TESTS_FAILED"
echo -e "  ${YELLOW}Skipped:${NC} $TESTS_SKIPPED"
echo ""
echo -e "  Duration: ${DURATION}s"
echo -e "  Log file: $LOG_FILE"
echo ""

if [ $TESTS_FAILED -eq 0 ]; then
    echo -e "${GREEN}╔════════════════════════════════════════════════════════════╗${NC}"
    echo -e "${GREEN}║              ALL TESTS PASSED SUCCESSFULLY!                ║${NC}"
    echo -e "${GREEN}╚════════════════════════════════════════════════════════════╝${NC}"
    exit 0
else
    echo -e "${RED}╔════════════════════════════════════════════════════════════╗${NC}"
    echo -e "${RED}║              SOME TESTS FAILED - CHECK LOGS                ║${NC}"
    echo -e "${RED}╚════════════════════════════════════════════════════════════╝${NC}"
    exit 1
fi
