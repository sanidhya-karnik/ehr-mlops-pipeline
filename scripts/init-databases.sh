#!/bin/bash
# =============================================================================
# Initialize Multiple PostgreSQL Databases
# =============================================================================

set -e

function create_database() {
    local database=$1
    echo "Creating database: $database"
    psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" <<-EOSQL
        CREATE DATABASE $database;
EOSQL
}

function create_user_and_grant() {
    local user=$1
    local password=$2
    local database=$3
    echo "Creating user: $user for database: $database"
    psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" <<-EOSQL
        CREATE USER $user WITH PASSWORD '$password';
        GRANT ALL PRIVILEGES ON DATABASE $database TO $user;
EOSQL
    psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$database" <<-EOSQL
        GRANT ALL ON SCHEMA public TO $user;
        ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO $user;
        ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON SEQUENCES TO $user;
EOSQL
}

# Create airflow database and user
create_database "airflow"
create_user_and_grant "airflow" "airflow" "airflow"

# Create mimic database and user
create_database "mimic"
create_user_and_grant "mimic" "mimic_password" "mimic"

# Initialize MIMIC database schema (using postgres for extension creation)
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "mimic" <<-EOSQL
    -- Enable extensions
    CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
    
    -- ==========================================================================
    -- Model Registry Tables
    -- ==========================================================================
    
    CREATE TABLE IF NOT EXISTS model_registry (
        id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
        model_name VARCHAR(100) NOT NULL,
        model_version VARCHAR(50) NOT NULL,
        model_path VARCHAR(500) NOT NULL,
        metrics JSONB DEFAULT '{}',
        parameters JSONB DEFAULT '{}',
        status VARCHAR(20) DEFAULT 'registered',
        created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
        deployed_at TIMESTAMP WITH TIME ZONE,
        UNIQUE(model_name, model_version)
    );
    
    CREATE INDEX idx_model_registry_name ON model_registry(model_name);
    CREATE INDEX idx_model_registry_status ON model_registry(status);
    
    -- ==========================================================================
    -- Prediction Logs
    -- ==========================================================================
    
    CREATE TABLE IF NOT EXISTS prediction_logs (
        id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
        model_version VARCHAR(50) NOT NULL,
        subject_id INTEGER,
        hadm_id INTEGER,
        features JSONB NOT NULL,
        prediction FLOAT NOT NULL,
        prediction_label VARCHAR(20),
        latency_ms FLOAT,
        created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
    );
    
    CREATE INDEX idx_prediction_logs_time ON prediction_logs(created_at DESC);
    CREATE INDEX idx_prediction_logs_subject ON prediction_logs(subject_id);
    
    -- ==========================================================================
    -- Feature Store Tables (populated by dbt)
    -- ==========================================================================
    
    CREATE TABLE IF NOT EXISTS feature_store (
        subject_id INTEGER NOT NULL,
        hadm_id INTEGER NOT NULL,
        features JSONB NOT NULL,
        feature_version VARCHAR(50),
        created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
        PRIMARY KEY (subject_id, hadm_id)
    );
    
    -- ==========================================================================
    -- Training Jobs
    -- ==========================================================================
    
    CREATE TABLE IF NOT EXISTS training_jobs (
        id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
        job_name VARCHAR(100) NOT NULL,
        status VARCHAR(20) DEFAULT 'pending',
        config JSONB DEFAULT '{}',
        metrics JSONB DEFAULT '{}',
        started_at TIMESTAMP WITH TIME ZONE,
        completed_at TIMESTAMP WITH TIME ZONE,
        error_message TEXT,
        created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
    );
    
    CREATE INDEX idx_training_jobs_status ON training_jobs(status);
EOSQL

echo "Database initialization complete!"
