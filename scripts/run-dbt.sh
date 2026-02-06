#!/bin/bash
# =============================================================================
# Run dbt Transformations
# =============================================================================

set -e

echo "=============================================="
echo "Running dbt Transformations"
echo "=============================================="

# Check if running inside Docker or locally
if [ -f /.dockerenv ] || [ -n "$DOCKER_CONTAINER" ]; then
    DBT_DIR="/opt/airflow/dbt"
else
    DBT_DIR="$(dirname "$0")/../dbt"
fi

cd "$DBT_DIR"

echo ""
echo "Step 1: Installing dbt dependencies..."
dbt deps --profiles-dir . --project-dir . 2>/dev/null || true

echo ""
echo "Step 2: Running dbt models..."
dbt run --profiles-dir . --project-dir .

echo ""
echo "Step 3: Running dbt tests..."
dbt test --profiles-dir . --project-dir . || echo "Warning: Some tests failed"

echo ""
echo "Step 4: Generating dbt docs..."
dbt docs generate --profiles-dir . --project-dir . 2>/dev/null || true

echo ""
echo "=============================================="
echo "dbt run complete!"
echo "=============================================="
echo ""
echo "Next steps:"
echo "  - Train model: ./scripts/train-model.sh"
echo "  - Or trigger via Airflow UI"
echo ""
