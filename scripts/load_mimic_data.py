"""
=============================================================================
Load MIMIC-IV Data into PostgreSQL
=============================================================================

Usage:
    python scripts/load_mimic_data.py

Loads patients, admissions, diagnoses_icd, labevents, and prescriptions.
"""

import os
import pandas as pd
import psycopg2
from pathlib import Path
import time

# =============================================================================
# Configuration
# =============================================================================

DB_CONFIG = {
    "host": os.getenv("DB_HOST", "localhost"),
    "port": int(os.getenv("DB_PORT", "5432")),
    "database": os.getenv("DB_NAME", "mimic"),
    "user": os.getenv("DB_USER", "mimic"),
    "password": os.getenv("DB_PASSWORD", "mimic_password"),
}

DATA_DIR = Path(__file__).parent.parent / "data" / "mimic-iv" / "hosp"

# Key lab itemids to filter (reduces 120M rows to ~15-20M)
KEY_LAB_ITEMIDS = [
    50912,  # Creatinine
    50931,  # Glucose
    51222,  # Hemoglobin
    51301,  # WBC
    50971,  # Potassium
    50983,  # Sodium
    51006,  # BUN
    50882,  # Bicarbonate
    51265,  # Platelet Count
]

# =============================================================================
# Table Schemas
# =============================================================================

SCHEMAS = {
    "patients": """
        CREATE TABLE IF NOT EXISTS mimic_hosp.patients (
            subject_id INTEGER PRIMARY KEY,
            gender VARCHAR(10),
            anchor_age INTEGER,
            anchor_year INTEGER,
            anchor_year_group VARCHAR(20),
            dod DATE
        )
    """,
    
    "admissions": """
        CREATE TABLE IF NOT EXISTS mimic_hosp.admissions (
            subject_id INTEGER,
            hadm_id INTEGER PRIMARY KEY,
            admittime TIMESTAMP,
            dischtime TIMESTAMP,
            deathtime TIMESTAMP,
            admission_type VARCHAR(100),
            admit_provider_id VARCHAR(50),
            admission_location VARCHAR(100),
            discharge_location VARCHAR(100),
            insurance VARCHAR(100),
            language VARCHAR(50),
            marital_status VARCHAR(100),
            race VARCHAR(100),
            edregtime TIMESTAMP,
            edouttime TIMESTAMP,
            hospital_expire_flag SMALLINT
        )
    """,
    
    "diagnoses_icd": """
        CREATE TABLE IF NOT EXISTS mimic_hosp.diagnoses_icd (
            subject_id INTEGER,
            hadm_id INTEGER,
            seq_num INTEGER,
            icd_code VARCHAR(20),
            icd_version INTEGER
        )
    """,
    
    "labevents": """
        CREATE TABLE IF NOT EXISTS mimic_hosp.labevents (
            labevent_id NUMERIC,
            subject_id NUMERIC,
            hadm_id NUMERIC,
            itemid NUMERIC,
            charttime TIMESTAMP,
            valuenum NUMERIC,
            valueuom VARCHAR(50),
            ref_range_lower NUMERIC,
            ref_range_upper NUMERIC,
            flag VARCHAR(50)
        )
    """,
    
    "prescriptions": """
        CREATE TABLE IF NOT EXISTS mimic_hosp.prescriptions (
            subject_id NUMERIC,
            hadm_id NUMERIC,
            pharmacy_id NUMERIC,
            starttime TIMESTAMP,
            stoptime TIMESTAMP,
            drug_type TEXT,
            drug TEXT,
            gsn TEXT,
            ndc TEXT,
            prod_strength TEXT,
            dose_val_rx TEXT,
            dose_unit_rx TEXT,
            route TEXT
        )
    """,
}

# =============================================================================
# Functions
# =============================================================================

def get_connection():
    return psycopg2.connect(**DB_CONFIG)


def create_schema(conn):
    with conn.cursor() as cur:
        cur.execute("CREATE SCHEMA IF NOT EXISTS mimic_hosp")
    conn.commit()
    print("[OK] Schema 'mimic_hosp' created")


def create_tables(conn):
    with conn.cursor() as cur:
        for table_name, schema in SCHEMAS.items():
            cur.execute(f"DROP TABLE IF EXISTS mimic_hosp.{table_name} CASCADE")
            cur.execute(schema)
            print(f"[OK] Table 'mimic_hosp.{table_name}' created")
    conn.commit()


def load_csv_fast(conn, table_name: str, file_path: Path):
    """Load CSV using PostgreSQL COPY."""
    print(f"\nLoading {table_name}...")
    print(f"  File: {file_path}")
    
    if not file_path.exists():
        print(f"  [ERROR] File not found: {file_path}")
        return
    
    file_size_mb = file_path.stat().st_size / (1024 * 1024)
    print(f"  Size: {file_size_mb:.1f} MB")
    
    start_time = time.time()
    
    with conn.cursor() as cur:
        with open(file_path, 'r', encoding='utf-8') as f:
            next(f)
            cur.copy_expert(
                f"COPY mimic_hosp.{table_name} FROM STDIN WITH CSV NULL ''",
                f
            )
    conn.commit()
    
    with conn.cursor() as cur:
        cur.execute(f"SELECT COUNT(*) FROM mimic_hosp.{table_name}")
        count = cur.fetchone()[0]
    
    elapsed = time.time() - start_time
    print(f"  [OK] Loaded {count:,} rows in {elapsed:.1f}s")


def load_labevents_filtered(conn, file_path: Path, chunk_size: int = 500000):
    """Load labevents filtered to key labs only."""
    print(f"\nLoading labevents (filtered to key labs)...")
    print(f"  File: {file_path}")
    
    if not file_path.exists():
        print(f"  [ERROR] File not found: {file_path}")
        return
    
    file_size_gb = file_path.stat().st_size / (1024 * 1024 * 1024)
    print(f"  Size: {file_size_gb:.1f} GB")
    print(f"  Filtering to {len(KEY_LAB_ITEMIDS)} key lab tests")
    
    start_time = time.time()
    total_rows = 0
    filtered_rows = 0
    
    for chunk in pd.read_csv(file_path, chunksize=chunk_size, low_memory=False):
        total_rows += len(chunk)
        
        # Filter to key labs only
        chunk = chunk[chunk['itemid'].isin(KEY_LAB_ITEMIDS)]
        
        if len(chunk) == 0:
            continue
        
        # Select only needed columns
        cols_to_keep = ['labevent_id', 'subject_id', 'hadm_id', 'itemid',
                        'charttime', 'valuenum', 'valueuom', 
                        'ref_range_lower', 'ref_range_upper', 'flag']
        chunk = chunk[[c for c in cols_to_keep if c in chunk.columns]]
        
        # Convert numeric columns safely
        for col in ['labevent_id', 'subject_id', 'hadm_id', 'itemid']:
            if col in chunk.columns:
                chunk[col] = pd.to_numeric(chunk[col], errors='coerce').astype('Int64')
        
        for col in ['valuenum', 'ref_range_lower', 'ref_range_upper']:
            if col in chunk.columns:
                chunk[col] = pd.to_numeric(chunk[col], errors='coerce')
        
        # Handle NaN - convert to None for psycopg2
        chunk = chunk.where(pd.notnull(chunk), None)
        
        # Convert Int64 NA to None
        for col in chunk.columns:
            chunk[col] = chunk[col].apply(lambda x: None if pd.isna(x) else x)
        
        # Insert
        with conn.cursor() as cur:
            cols = list(chunk.columns)
            placeholders = ','.join(['%s'] * len(cols))
            insert_sql = f"INSERT INTO mimic_hosp.labevents ({','.join(cols)}) VALUES ({placeholders})"
            data = [tuple(row) for row in chunk.values]
            cur.executemany(insert_sql, data)
        
        conn.commit()
        filtered_rows += len(chunk)
        
        elapsed = time.time() - start_time
        print(f"  Processed {total_rows:,} rows, kept {filtered_rows:,} ({elapsed:.0f}s)...", end="\r")
    
    elapsed = time.time() - start_time
    print(f"\n  [OK] Loaded {filtered_rows:,} rows (from {total_rows:,} total) in {elapsed:.1f}s")


def load_prescriptions(conn, file_path: Path, chunk_size: int = 200000):
    """Load prescriptions in chunks."""
    print(f"\nLoading prescriptions...")
    print(f"  File: {file_path}")
    
    if not file_path.exists():
        print(f"  [ERROR] File not found: {file_path}")
        return
    
    file_size_gb = file_path.stat().st_size / (1024 * 1024 * 1024)
    print(f"  Size: {file_size_gb:.1f} GB")
    
    start_time = time.time()
    total_rows = 0
    
    for chunk in pd.read_csv(file_path, chunksize=chunk_size, low_memory=False, dtype=str):
        # Select only needed columns
        cols_to_keep = ['subject_id', 'hadm_id', 'pharmacy_id', 'starttime', 'stoptime',
                        'drug_type', 'drug', 'gsn', 'ndc', 'prod_strength',
                        'dose_val_rx', 'dose_unit_rx', 'route']
        chunk = chunk[[c for c in cols_to_keep if c in chunk.columns]]
        
        # Convert numeric columns safely
        for col in ['subject_id', 'hadm_id', 'pharmacy_id']:
            if col in chunk.columns:
                chunk[col] = pd.to_numeric(chunk[col], errors='coerce')
        
        # Handle NaN - convert to None for psycopg2
        chunk = chunk.where(pd.notnull(chunk), None)
        
        # Convert any remaining NA to None
        for col in chunk.columns:
            chunk[col] = chunk[col].apply(lambda x: None if pd.isna(x) else x)
        
        # Insert
        with conn.cursor() as cur:
            cols = list(chunk.columns)
            placeholders = ','.join(['%s'] * len(cols))
            insert_sql = f"INSERT INTO mimic_hosp.prescriptions ({','.join(cols)}) VALUES ({placeholders})"
            data = [tuple(row) for row in chunk.values]
            cur.executemany(insert_sql, data)
        
        conn.commit()
        total_rows += len(chunk)
        
        elapsed = time.time() - start_time
        print(f"  Loaded {total_rows:,} rows ({elapsed:.0f}s)...", end="\r")
    
    elapsed = time.time() - start_time
    print(f"\n  [OK] Loaded {total_rows:,} rows in {elapsed:.1f}s")


def create_indexes(conn):
    print("\nCreating indexes...")
    
    indexes = [
        "CREATE INDEX IF NOT EXISTS idx_admissions_subject ON mimic_hosp.admissions(subject_id)",
        "CREATE INDEX IF NOT EXISTS idx_diagnoses_subject ON mimic_hosp.diagnoses_icd(subject_id)",
        "CREATE INDEX IF NOT EXISTS idx_diagnoses_hadm ON mimic_hosp.diagnoses_icd(hadm_id)",
        "CREATE INDEX IF NOT EXISTS idx_labevents_hadm ON mimic_hosp.labevents(hadm_id)",
        "CREATE INDEX IF NOT EXISTS idx_labevents_itemid ON mimic_hosp.labevents(itemid)",
        "CREATE INDEX IF NOT EXISTS idx_prescriptions_hadm ON mimic_hosp.prescriptions(hadm_id)",
    ]
    
    with conn.cursor() as cur:
        for idx_sql in indexes:
            cur.execute(idx_sql)
            print("  [OK] Index created")
    
    conn.commit()
    print("[OK] All indexes created")


def verify_data(conn):
    print("\n" + "="*50)
    print("Data Verification")
    print("="*50)
    
    tables = ["patients", "admissions", "diagnoses_icd", "labevents", "prescriptions"]
    
    with conn.cursor() as cur:
        for table in tables:
            try:
                cur.execute(f"SELECT COUNT(*) FROM mimic_hosp.{table}")
                count = cur.fetchone()[0]
                print(f"  mimic_hosp.{table}: {count:,} rows")
            except:
                print(f"  mimic_hosp.{table}: [NOT LOADED]")


def main():
    print("="*50)
    print("MIMIC-IV Data Loader")
    print("="*50)
    print(f"\nConnecting to PostgreSQL at {DB_CONFIG['host']}:{DB_CONFIG['port']}...")
    
    try:
        conn = get_connection()
        print("[OK] Connected to database")
    except Exception as e:
        print(f"[ERROR] Connection failed: {e}")
        return
    
    try:
        create_schema(conn)
        create_tables(conn)
        
        # Core tables (fast COPY)
        load_csv_fast(conn, "patients", DATA_DIR / "patients.csv")
        load_csv_fast(conn, "admissions", DATA_DIR / "admissions.csv")
        load_csv_fast(conn, "diagnoses_icd", DATA_DIR / "diagnoses_icd.csv")
        
        # Large tables (chunked, filtered)
        load_labevents_filtered(conn, DATA_DIR / "labevents.csv")
        load_prescriptions(conn, DATA_DIR / "prescriptions.csv")
        
        create_indexes(conn)
        verify_data(conn)
        
        print("\n" + "="*50)
        print("[OK] Data loading complete!")
        print("="*50)
        print("\nNext steps:")
        print("  1. Run dbt: cd dbt && dbt run")
        print("  2. Train model: python src/training/train.py")
        
    except Exception as e:
        print(f"\n[ERROR] {e}")
        import traceback
        traceback.print_exc()
    finally:
        conn.close()


if __name__ == "__main__":
    main()
