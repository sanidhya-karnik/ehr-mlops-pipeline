#!/bin/bash
# =============================================================================
# Generate SHAP Analysis Report
# =============================================================================
#
# Generates comprehensive model explainability report using SHAP.
#
# Usage:
#   ./scripts/run-shap-analysis.sh
#   ./scripts/run-shap-analysis.sh --sample-size 2000
#
# =============================================================================

set -e

# Default values
SAMPLE_SIZE="${SAMPLE_SIZE:-1000}"
OUTPUT_DIR="${OUTPUT_DIR:-./shap_reports}"
MODEL_NAME="${MODEL_NAME:-readmission_model}"

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --sample-size)
            SAMPLE_SIZE="$2"
            shift 2
            ;;
        --output-dir)
            OUTPUT_DIR="$2"
            shift 2
            ;;
        --model-name)
            MODEL_NAME="$2"
            shift 2
            ;;
        *)
            echo "Unknown option: $1"
            exit 1
            ;;
    esac
done

# Set environment variables
export DB_HOST="${DB_HOST:-localhost}"
export DB_PORT="${DB_PORT:-5432}"
export DB_NAME="${DB_NAME:-mimic}"
export DB_USER="${DB_USER:-mimic}"
export DB_PASSWORD="${DB_PASSWORD:-mimic_password}"
export S3_ENDPOINT_URL="${S3_ENDPOINT_URL:-http://localhost:9000}"
export AWS_ACCESS_KEY_ID="${AWS_ACCESS_KEY_ID:-minioadmin}"
export AWS_SECRET_ACCESS_KEY="${AWS_SECRET_ACCESS_KEY:-minioadmin}"

echo "=============================================="
echo "SHAP Analysis Report Generation"
echo "=============================================="
echo ""
echo "Configuration:"
echo "  - Model Name:  $MODEL_NAME"
echo "  - Sample Size: $SAMPLE_SIZE"
echo "  - Output Dir:  $OUTPUT_DIR"
echo "  - Database:    $DB_HOST:$DB_PORT/$DB_NAME"
echo ""

# Get script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

# Add src to Python path
export PYTHONPATH="${PROJECT_DIR}/src:${PYTHONPATH}"

# Run SHAP analysis
echo "Running SHAP analysis..."
python "${PROJECT_DIR}/src/training/shap_analysis.py" \
    --model-name "$MODEL_NAME" \
    --output-dir "$OUTPUT_DIR" \
    --sample-size "$SAMPLE_SIZE" \
    --generate-report

echo ""
echo "=============================================="
echo "SHAP Analysis Complete!"
echo "=============================================="
echo ""
echo "Generated files in $OUTPUT_DIR:"
ls -la "$OUTPUT_DIR"
echo ""
echo "Key outputs:"
echo "  - shap_summary.png           : Feature importance beeswarm plot"
echo "  - shap_feature_importance.png: Feature importance bar chart"
echo "  - shap_waterfall_*.png       : Individual patient explanations"
echo "  - feature_importance.csv     : Importance rankings"
echo "  - shap_report.json           : Full report metadata"
echo ""
