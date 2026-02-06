#!/bin/bash
# =============================================================================
# Train Readmission Prediction Model
# =============================================================================

set -e

echo "=============================================="
echo "Training Readmission Prediction Model"
echo "=============================================="

# Default values
MODEL_TYPE="${MODEL_TYPE:-xgboost}"
MODEL_NAME="${MODEL_NAME:-readmission_model}"

# Check if running inside Docker or locally
if [ -f /.dockerenv ] || [ -n "$DOCKER_CONTAINER" ]; then
    SRC_DIR="/opt/airflow/src"
else
    SRC_DIR="$(dirname "$0")/../src"
fi

# Set environment variables if not already set
export DB_HOST="${DB_HOST:-localhost}"
export DB_PORT="${DB_PORT:-5432}"
export DB_NAME="${DB_NAME:-mimic}"
export DB_USER="${DB_USER:-mimic}"
export DB_PASSWORD="${DB_PASSWORD:-mimic_password}"
export S3_ENDPOINT_URL="${S3_ENDPOINT_URL:-http://localhost:9000}"
export AWS_ACCESS_KEY_ID="${AWS_ACCESS_KEY_ID:-minioadmin}"
export AWS_SECRET_ACCESS_KEY="${AWS_SECRET_ACCESS_KEY:-minioadmin}"

echo ""
echo "Configuration:"
echo "  - Model Type: $MODEL_TYPE"
echo "  - Model Name: $MODEL_NAME"
echo "  - Database:   $DB_HOST:$DB_PORT/$DB_NAME"
echo "  - S3 Endpoint: $S3_ENDPOINT_URL"
echo ""

# Add src to Python path
export PYTHONPATH="${SRC_DIR}:${PYTHONPATH}"

echo "Starting training..."
python "${SRC_DIR}/training/train.py" \
    --model-name "$MODEL_NAME" \
    --model-type "$MODEL_TYPE"

echo ""
echo "=============================================="
echo "Training complete!"
echo "=============================================="
echo ""
echo "Next steps:"
echo "  - Deploy model: ./scripts/deploy-model.sh"
echo "  - Or trigger via Airflow UI"
echo ""
