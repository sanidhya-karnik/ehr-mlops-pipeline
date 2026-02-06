#!/bin/bash
# =============================================================================
# Quick Smoke Test - Verify Infrastructure is Working
# =============================================================================
#
# Fast verification that all services are up and responding.
# Run this after docker-compose up to verify everything is working.
#
# Usage: ./scripts/smoke-test.sh
#
# =============================================================================

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

PASSED=0
FAILED=0

check() {
    local name=$1
    local cmd=$2
    
    if eval "$cmd" > /dev/null 2>&1; then
        echo -e "${GREEN}✓${NC} $name"
        ((PASSED++))
    else
        echo -e "${RED}✗${NC} $name"
        ((FAILED++))
    fi
}

echo ""
echo "═══════════════════════════════════════════════════════════"
echo "             EHR MLOps Pipeline - Smoke Test"
echo "═══════════════════════════════════════════════════════════"
echo ""

echo "Checking Docker services..."
check "Docker running" "docker info"
check "PostgreSQL" "docker exec mlops-postgres pg_isready -U postgres"
check "Redis" "docker exec mlops-redis redis-cli ping"

echo ""
echo "Checking HTTP endpoints..."
check "MinIO" "curl -sf http://localhost:9000/minio/health/live"
check "Airflow" "curl -sf http://localhost:8080/health"
check "LocalStack" "curl -sf http://localhost:4566/_localstack/health"

echo ""
echo "Checking Model API..."
if curl -sf http://localhost:8000/health > /dev/null 2>&1; then
    check "API Health" "curl -sf http://localhost:8000/health"
    check "API Ready" "curl -sf http://localhost:8000/health/ready"
    check "API Predict" "curl -sf -X POST http://localhost:8000/predict -H 'Content-Type: application/json' -d '{\"age\":65}'"
else
    echo -e "${YELLOW}!${NC} Model API not running (optional)"
fi

echo ""
echo "Checking Database..."
check "mimic_hosp schema" "docker exec mlops-postgres psql -U mimic -d mimic -c 'SELECT 1 FROM mimic_hosp.patients LIMIT 1'"

# Check feature table (may not exist yet)
if docker exec mlops-postgres psql -U mimic -d mimic -c "SELECT 1 FROM public_marts.fct_readmission_features LIMIT 1" > /dev/null 2>&1; then
    check "Feature table" "true"
else
    echo -e "${YELLOW}!${NC} Feature table not created yet (run dbt)"
fi

echo ""
echo "═══════════════════════════════════════════════════════════"
echo -e "Results: ${GREEN}$PASSED passed${NC}, ${RED}$FAILED failed${NC}"
echo "═══════════════════════════════════════════════════════════"
echo ""

if [ $FAILED -eq 0 ]; then
    echo -e "${GREEN}All checks passed!${NC}"
    exit 0
else
    echo -e "${RED}Some checks failed.${NC}"
    exit 1
fi
