#!/bin/bash
# =============================================================================
# Deploy Model to Serving Infrastructure
# =============================================================================

set -e

echo "=============================================="
echo "Deploying Model to Serving Infrastructure"
echo "=============================================="

# Default values
MODEL_NAME="${MODEL_NAME:-readmission_model}"
API_URL="${API_URL:-http://localhost:8000}"

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
echo "  - Model Name: $MODEL_NAME"
echo "  - API URL:    $API_URL"
echo ""

# Step 1: Verify model exists in S3
echo "Step 1: Verifying model in S3..."
if command -v aws &> /dev/null; then
    aws --endpoint-url "$S3_ENDPOINT_URL" s3 ls "s3://mimic-models/models/${MODEL_NAME}/" || {
        echo "Error: No model found in S3. Run ./scripts/train-model.sh first."
        exit 1
    }
else
    echo "  Skipping S3 verification (aws CLI not installed)"
fi

# Step 2: Trigger model reload on serving API
echo ""
echo "Step 2: Triggering model reload on serving API..."
if curl -sf "${API_URL}/health" > /dev/null 2>&1; then
    response=$(curl -sf -X POST "${API_URL}/model/reload" 2>&1) || {
        echo "Warning: Could not reload model. API may need restart."
    }
    echo "  Response: $response"
else
    echo "  Warning: Serving API not reachable at ${API_URL}"
    echo "  The model will be loaded when the API starts."
fi

# Step 3: Verify deployment
echo ""
echo "Step 3: Verifying deployment..."
if curl -sf "${API_URL}/health" > /dev/null 2>&1; then
    health=$(curl -sf "${API_URL}/health")
    echo "  Health: $health"
    
    model_info=$(curl -sf "${API_URL}/model/info" 2>/dev/null) || true
    if [ -n "$model_info" ]; then
        echo "  Model Info: $model_info"
    fi
else
    echo "  Serving API not available for verification"
fi

echo ""
echo "=============================================="
echo "Deployment complete!"
echo "=============================================="
echo ""
echo "Test the API:"
echo "  curl -X POST ${API_URL}/predict \\"
echo "    -H 'Content-Type: application/json' \\"
echo "    -d '{\"age\": 65, \"los_days\": 5, \"has_chf\": 1}'"
echo ""
