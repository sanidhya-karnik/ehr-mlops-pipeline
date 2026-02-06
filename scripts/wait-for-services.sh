#!/bin/bash
# =============================================================================
# Wait for All Services to be Healthy
# =============================================================================

set -e

echo "Waiting for services to be ready..."

# Function to wait for a service
wait_for_service() {
    local service=$1
    local url=$2
    local max_attempts=${3:-30}
    local attempt=1

    echo "Waiting for $service..."
    while [ $attempt -le $max_attempts ]; do
        if curl -sf "$url" > /dev/null 2>&1; then
            echo "  ✓ $service is ready"
            return 0
        fi
        echo "  Attempt $attempt/$max_attempts - $service not ready yet..."
        sleep 2
        attempt=$((attempt + 1))
    done

    echo "  ✗ $service failed to start after $max_attempts attempts"
    return 1
}

# Wait for PostgreSQL
echo "Waiting for PostgreSQL..."
max_attempts=30
attempt=1
while [ $attempt -le $max_attempts ]; do
    if docker exec mlops-postgres pg_isready -U postgres > /dev/null 2>&1; then
        echo "  ✓ PostgreSQL is ready"
        break
    fi
    echo "  Attempt $attempt/$max_attempts - PostgreSQL not ready yet..."
    sleep 2
    attempt=$((attempt + 1))
done

if [ $attempt -gt $max_attempts ]; then
    echo "  ✗ PostgreSQL failed to start"
    exit 1
fi

# Wait for MinIO
wait_for_service "MinIO" "http://localhost:9000/minio/health/live"

# Wait for Airflow
wait_for_service "Airflow Webserver" "http://localhost:8080/health" 60

# Wait for LocalStack
wait_for_service "LocalStack" "http://localhost:4566/_localstack/health"

# Wait for Redis
echo "Waiting for Redis..."
max_attempts=30
attempt=1
while [ $attempt -le $max_attempts ]; do
    if docker exec mlops-redis redis-cli ping > /dev/null 2>&1; then
        echo "  ✓ Redis is ready"
        break
    fi
    echo "  Attempt $attempt/$max_attempts - Redis not ready yet..."
    sleep 2
    attempt=$((attempt + 1))
done

echo ""
echo "=============================================="
echo "All services are ready!"
echo "=============================================="
echo ""
echo "Service URLs:"
echo "  - Airflow UI:     http://localhost:8080 (airflow/airflow)"
echo "  - MinIO Console:  http://localhost:9001 (minioadmin/minioadmin)"
echo "  - PostgreSQL:     localhost:5432"
echo "  - Redis:          localhost:6379"
echo ""
