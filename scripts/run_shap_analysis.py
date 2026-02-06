"""
=============================================================================
SHAP Analysis Runner (Python - Cross-Platform)
=============================================================================

Generate SHAP analysis report for the readmission prediction model.

Usage:
    python scripts/run_shap_analysis.py
    python scripts/run_shap_analysis.py --sample-size 2000
    python scripts/run_shap_analysis.py --output-dir ./my_reports
"""

import argparse
import os
import sys
from pathlib import Path

# Add src to path
PROJECT_DIR = Path(__file__).parent.parent.absolute()
sys.path.insert(0, str(PROJECT_DIR / "src"))


def main():
    parser = argparse.ArgumentParser(description="SHAP Analysis for Readmission Model")
    parser.add_argument("--model-name", default="readmission_model", help="Model name in S3")
    parser.add_argument("--output-dir", default="./shap_reports", help="Output directory")
    parser.add_argument("--sample-size", type=int, default=1000, help="Number of samples")
    args = parser.parse_args()

    # Set environment variables
    os.environ.setdefault("DB_HOST", "localhost")
    os.environ.setdefault("DB_PORT", "5432")
    os.environ.setdefault("DB_NAME", "mimic")
    os.environ.setdefault("DB_USER", "mimic")
    os.environ.setdefault("DB_PASSWORD", "mimic_password")
    os.environ.setdefault("S3_ENDPOINT_URL", "http://localhost:9000")
    os.environ.setdefault("AWS_ACCESS_KEY_ID", "minioadmin")
    os.environ.setdefault("AWS_SECRET_ACCESS_KEY", "minioadmin")

    print("=" * 60)
    print("SHAP Analysis Report Generation")
    print("=" * 60)
    print(f"\nModel: {args.model_name}")
    print(f"Sample Size: {args.sample_size}")
    print(f"Output Dir: {args.output_dir}\n")

    # Import after setting up path
    from training.shap_analysis import (
        SHAPAnalyzer,
        load_model_from_s3,
        load_data_from_db,
    )
    from training.train import ModelTrainer
    import pandas as pd
    import numpy as np

    # Load model
    print("Loading model from S3...")
    model, artifact = load_model_from_s3(
        os.environ["S3_ENDPOINT_URL"],
        os.environ.get("S3_BUCKET_MODELS", "mimic-models"),
        args.model_name,
    )
    
    feature_names = artifact.get("feature_names", [])
    scaler = artifact.get("scaler")
    label_encoders = artifact.get("label_encoders", {})
    
    print(f"Model loaded: {len(feature_names)} features")

    # Load data
    print(f"Loading {args.sample_size} samples from database...")
    df = load_data_from_db(
        os.environ["DB_HOST"],
        os.environ["DB_NAME"],
        os.environ["DB_USER"],
        os.environ["DB_PASSWORD"],
        args.sample_size,
    )
    print(f"Loaded {len(df)} samples")

    # Prepare features (same preprocessing as training)
    trainer = ModelTrainer(
        os.environ["DB_HOST"],
        os.environ["DB_NAME"],
        os.environ["DB_USER"],
        os.environ["DB_PASSWORD"],
    )
    
    # Get feature columns
    all_features = trainer.NUMERIC_FEATURES + trainer.CATEGORICAL_FEATURES + trainer.BINARY_FEATURES
    feature_cols = [c for c in all_features if c in df.columns]
    
    # Preprocess
    for col in trainer.NUMERIC_FEATURES:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
            df[col] = df[col].fillna(df[col].median())
    
    for col in trainer.CATEGORICAL_FEATURES:
        if col in df.columns:
            df[col] = df[col].fillna("Unknown")
            if col in label_encoders:
                # Handle unseen categories
                le = label_encoders[col]
                df[col] = df[col].apply(lambda x: x if x in le.classes_ else le.classes_[0])
                df[col] = le.transform(df[col].astype(str))
            else:
                df[col] = 0
    
    for col in trainer.BINARY_FEATURES:
        if col in df.columns:
            df[col] = df[col].fillna(0).astype(int)
    
    X = df[feature_cols].values
    if scaler:
        X = scaler.transform(X)
    
    print(f"Feature matrix shape: {X.shape}")

    # Create analyzer and compute SHAP values
    print("\nInitializing SHAP analyzer...")
    analyzer = SHAPAnalyzer(model, feature_cols, X_background=X)
    
    print("Computing SHAP values (this may take a few minutes)...")
    analyzer.compute_shap_values(X, max_samples=args.sample_size)
    
    # Generate report
    print("\nGenerating report...")
    output_path = Path(args.output_dir)
    report = analyzer.generate_report(output_path)
    
    # Print summary
    print("\n" + "=" * 60)
    print("SHAP Analysis Complete!")
    print("=" * 60)
    
    print("\nTop 10 Features by SHAP Importance:")
    print("-" * 50)
    for item in report['feature_importance'][:10]:
        bar = "█" * int(item['importance_pct'] / 2)
        print(f"  {item['rank']:2d}. {item['feature']:30s} {item['importance_pct']:5.1f}% {bar}")
    
    print(f"\nGenerated {len(report['files'])} files in {args.output_dir}/")
    print("\nKey outputs:")
    print("  - shap_summary.png            : Beeswarm plot (feature impact distribution)")
    print("  - shap_feature_importance.png : Bar chart (mean |SHAP|)")
    print("  - shap_waterfall_*.png        : Individual patient explanations")
    print("  - feature_importance.csv      : Full importance rankings")
    print("  - shap_report.json            : Report metadata")


if __name__ == "__main__":
    main()
