"""
=============================================================================
SHAP Analysis Module for Readmission Prediction Model
=============================================================================

Generates model explanations using SHAP (SHapley Additive exPlanations).
Provides global feature importance and individual patient explanations.

Usage:
    python src/training/shap_analysis.py --model-path s3://mimic-models/models/readmission_model/latest/model.pkl
    python src/training/shap_analysis.py --generate-report
"""

import os
import io
import json
import pickle
import logging
import base64
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')  # Non-interactive backend
import matplotlib.pyplot as plt
import shap
import boto3
from botocore.client import Config

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class SHAPAnalyzer:
    """
    SHAP-based model explainability for readmission prediction.
    
    Provides:
    - Global feature importance
    - Feature interaction analysis
    - Individual patient explanations
    - Visualization generation
    """
    
    def __init__(
        self,
        model: Any,
        feature_names: List[str],
        X_background: Optional[np.ndarray] = None,
        n_background_samples: int = 100,
    ):
        """
        Initialize SHAP analyzer.
        
        Args:
            model: Trained model (XGBoost, RandomForest, or LogisticRegression)
            feature_names: List of feature names
            X_background: Background dataset for SHAP (uses sample if None)
            n_background_samples: Number of background samples to use
        """
        self.model = model
        self.feature_names = feature_names
        self.n_background_samples = n_background_samples
        self.explainer = None
        self.shap_values = None
        self.X_explain = None
        
        # Determine model type and create appropriate explainer
        model_type = type(model).__name__
        logger.info(f"Initializing SHAP explainer for {model_type}")
        
        if hasattr(model, 'get_booster') or 'XGB' in model_type:
            # XGBoost - use TreeExplainer
            self.explainer = shap.TreeExplainer(model)
            self.model_type = "tree"
        elif 'RandomForest' in model_type or 'GradientBoosting' in model_type:
            # Tree-based sklearn models
            self.explainer = shap.TreeExplainer(model)
            self.model_type = "tree"
        elif 'LogisticRegression' in model_type or 'Linear' in model_type:
            # Linear models
            if X_background is not None:
                background = shap.sample(X_background, min(n_background_samples, len(X_background)))
            else:
                raise ValueError("Background data required for linear models")
            self.explainer = shap.LinearExplainer(model, background)
            self.model_type = "linear"
        else:
            # Fallback to KernelExplainer (slower but universal)
            if X_background is not None:
                background = shap.sample(X_background, min(n_background_samples, len(X_background)))
            else:
                raise ValueError("Background data required for KernelExplainer")
            self.explainer = shap.KernelExplainer(model.predict_proba, background)
            self.model_type = "kernel"
    
    def compute_shap_values(
        self,
        X: np.ndarray,
        max_samples: int = 1000,
    ) -> np.ndarray:
        """
        Compute SHAP values for given data.
        
        Args:
            X: Feature matrix to explain
            max_samples: Maximum samples to compute (for performance)
            
        Returns:
            SHAP values array
        """
        # Limit samples for performance
        if len(X) > max_samples:
            logger.info(f"Sampling {max_samples} from {len(X)} samples for SHAP computation")
            indices = np.random.choice(len(X), max_samples, replace=False)
            X = X[indices]
        
        self.X_explain = X
        
        logger.info(f"Computing SHAP values for {len(X)} samples...")
        self.shap_values = self.explainer.shap_values(X)
        
        # Handle multi-output (binary classification returns list)
        if isinstance(self.shap_values, list):
            # Take positive class (index 1)
            self.shap_values = self.shap_values[1]
        
        logger.info(f"SHAP values shape: {self.shap_values.shape}")
        return self.shap_values
    
    def get_feature_importance(self) -> pd.DataFrame:
        """
        Get global feature importance based on mean |SHAP|.
        
        Returns:
            DataFrame with feature importance rankings
        """
        if self.shap_values is None:
            raise ValueError("Must compute SHAP values first")
        
        # Mean absolute SHAP value per feature
        importance = np.abs(self.shap_values).mean(axis=0)
        
        df = pd.DataFrame({
            'feature': self.feature_names,
            'importance': importance,
            'importance_pct': importance / importance.sum() * 100,
        }).sort_values('importance', ascending=False).reset_index(drop=True)
        
        df['rank'] = range(1, len(df) + 1)
        
        return df
    
    def get_feature_effects(self) -> pd.DataFrame:
        """
        Get directional feature effects (positive = increases risk).
        
        Returns:
            DataFrame with mean SHAP values per feature
        """
        if self.shap_values is None:
            raise ValueError("Must compute SHAP values first")
        
        mean_shap = self.shap_values.mean(axis=0)
        
        df = pd.DataFrame({
            'feature': self.feature_names,
            'mean_shap': mean_shap,
            'direction': ['increases risk' if v > 0 else 'decreases risk' for v in mean_shap],
            'abs_effect': np.abs(mean_shap),
        }).sort_values('abs_effect', ascending=False).reset_index(drop=True)
        
        return df
    
    def explain_patient(
        self,
        patient_features: np.ndarray,
        top_n: int = 10,
    ) -> Dict[str, Any]:
        """
        Generate explanation for a single patient.
        
        Args:
            patient_features: Feature array for one patient
            top_n: Number of top contributing features to return
            
        Returns:
            Dictionary with patient explanation
        """
        # Ensure 2D
        if patient_features.ndim == 1:
            patient_features = patient_features.reshape(1, -1)
        
        # Compute SHAP values for this patient
        shap_vals = self.explainer.shap_values(patient_features)
        
        if isinstance(shap_vals, list):
            shap_vals = shap_vals[1]  # Positive class
        
        shap_vals = shap_vals.flatten()
        
        # Get base value (expected value)
        if hasattr(self.explainer, 'expected_value'):
            base_value = self.explainer.expected_value
            if isinstance(base_value, (list, np.ndarray)):
                base_value = base_value[1]  # Positive class
        else:
            base_value = 0.5
        
        # Create feature contributions
        contributions = []
        for i, (feat, val, shap_val) in enumerate(zip(
            self.feature_names, patient_features.flatten(), shap_vals
        )):
            contributions.append({
                'feature': feat,
                'value': float(val),
                'shap_value': float(shap_val),
                'direction': 'risk_increase' if shap_val > 0 else 'risk_decrease',
                'abs_contribution': abs(float(shap_val)),
            })
        
        # Sort by absolute contribution
        contributions.sort(key=lambda x: x['abs_contribution'], reverse=True)
        
        # Get prediction
        if hasattr(self.model, 'predict_proba'):
            prob = float(self.model.predict_proba(patient_features)[0, 1])
        else:
            prob = float(self.model.predict(patient_features)[0])
        
        return {
            'prediction_probability': prob,
            'base_value': float(base_value),
            'sum_of_shap': float(shap_vals.sum()),
            'top_risk_factors': [c for c in contributions[:top_n] if c['shap_value'] > 0],
            'top_protective_factors': [c for c in contributions[:top_n] if c['shap_value'] < 0],
            'all_contributions': contributions,
        }
    
    def plot_summary(self, max_display: int = 20) -> plt.Figure:
        """
        Generate SHAP summary plot (beeswarm).
        
        Args:
            max_display: Maximum features to display
            
        Returns:
            Matplotlib figure
        """
        if self.shap_values is None or self.X_explain is None:
            raise ValueError("Must compute SHAP values first")
        
        fig, ax = plt.subplots(figsize=(12, 10))
        shap.summary_plot(
            self.shap_values,
            self.X_explain,
            feature_names=self.feature_names,
            max_display=max_display,
            show=False,
        )
        plt.tight_layout()
        return fig
    
    def plot_feature_importance(self, max_display: int = 20) -> plt.Figure:
        """
        Generate SHAP feature importance bar plot.
        
        Args:
            max_display: Maximum features to display
            
        Returns:
            Matplotlib figure
        """
        if self.shap_values is None:
            raise ValueError("Must compute SHAP values first")
        
        fig, ax = plt.subplots(figsize=(10, 8))
        shap.summary_plot(
            self.shap_values,
            self.X_explain,
            feature_names=self.feature_names,
            max_display=max_display,
            plot_type="bar",
            show=False,
        )
        plt.tight_layout()
        return fig
    
    def plot_waterfall(self, patient_idx: int = 0) -> plt.Figure:
        """
        Generate waterfall plot for a single patient.
        
        Args:
            patient_idx: Index of patient in X_explain
            
        Returns:
            Matplotlib figure
        """
        if self.shap_values is None or self.X_explain is None:
            raise ValueError("Must compute SHAP values first")
        
        # Get expected value
        if hasattr(self.explainer, 'expected_value'):
            base_value = self.explainer.expected_value
            if isinstance(base_value, (list, np.ndarray)):
                base_value = base_value[1]
        else:
            base_value = 0.5
        
        # Create Explanation object
        explanation = shap.Explanation(
            values=self.shap_values[patient_idx],
            base_values=base_value,
            data=self.X_explain[patient_idx],
            feature_names=self.feature_names,
        )
        
        fig, ax = plt.subplots(figsize=(10, 8))
        shap.plots.waterfall(explanation, max_display=15, show=False)
        plt.tight_layout()
        return fig
    
    def plot_dependence(self, feature: str, interaction_feature: Optional[str] = None) -> plt.Figure:
        """
        Generate dependence plot for a feature.
        
        Args:
            feature: Feature to plot
            interaction_feature: Feature to color by (auto-detected if None)
            
        Returns:
            Matplotlib figure
        """
        if self.shap_values is None or self.X_explain is None:
            raise ValueError("Must compute SHAP values first")
        
        feature_idx = self.feature_names.index(feature)
        
        fig, ax = plt.subplots(figsize=(10, 6))
        shap.dependence_plot(
            feature_idx,
            self.shap_values,
            self.X_explain,
            feature_names=self.feature_names,
            interaction_index=interaction_feature,
            ax=ax,
            show=False,
        )
        plt.tight_layout()
        return fig
    
    def generate_report(
        self,
        output_dir: Path,
        include_dependence_plots: bool = True,
        top_features_for_dependence: int = 5,
    ) -> Dict[str, Any]:
        """
        Generate comprehensive SHAP analysis report.
        
        Args:
            output_dir: Directory to save report files
            include_dependence_plots: Whether to generate dependence plots
            top_features_for_dependence: Number of top features for dependence plots
            
        Returns:
            Dictionary with report metadata
        """
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        
        logger.info(f"Generating SHAP report in {output_dir}")
        
        report = {
            'generated_at': datetime.utcnow().isoformat(),
            'n_samples': len(self.X_explain) if self.X_explain is not None else 0,
            'n_features': len(self.feature_names),
            'files': [],
        }
        
        # 1. Feature importance table
        importance_df = self.get_feature_importance()
        importance_path = output_dir / 'feature_importance.csv'
        importance_df.to_csv(importance_path, index=False)
        report['files'].append(str(importance_path))
        report['feature_importance'] = importance_df.head(20).to_dict('records')
        
        # 2. Feature effects table
        effects_df = self.get_feature_effects()
        effects_path = output_dir / 'feature_effects.csv'
        effects_df.to_csv(effects_path, index=False)
        report['files'].append(str(effects_path))
        
        # 3. Summary plot (beeswarm)
        fig = self.plot_summary()
        summary_path = output_dir / 'shap_summary.png'
        fig.savefig(summary_path, dpi=150, bbox_inches='tight')
        plt.close(fig)
        report['files'].append(str(summary_path))
        
        # 4. Feature importance bar plot
        fig = self.plot_feature_importance()
        bar_path = output_dir / 'shap_feature_importance.png'
        fig.savefig(bar_path, dpi=150, bbox_inches='tight')
        plt.close(fig)
        report['files'].append(str(bar_path))
        
        # 5. Example waterfall plots
        for i in range(min(3, len(self.X_explain))):
            fig = self.plot_waterfall(patient_idx=i)
            waterfall_path = output_dir / f'shap_waterfall_patient_{i}.png'
            fig.savefig(waterfall_path, dpi=150, bbox_inches='tight')
            plt.close(fig)
            report['files'].append(str(waterfall_path))
        
        # 6. Dependence plots for top features
        if include_dependence_plots:
            top_features = importance_df.head(top_features_for_dependence)['feature'].tolist()
            for feature in top_features:
                try:
                    fig = self.plot_dependence(feature)
                    dep_path = output_dir / f'shap_dependence_{feature}.png'
                    fig.savefig(dep_path, dpi=150, bbox_inches='tight')
                    plt.close(fig)
                    report['files'].append(str(dep_path))
                except Exception as e:
                    logger.warning(f"Could not generate dependence plot for {feature}: {e}")
        
        # 7. Save report metadata
        report_path = output_dir / 'shap_report.json'
        with open(report_path, 'w') as f:
            json.dump(report, f, indent=2, default=str)
        
        logger.info(f"Report generated with {len(report['files'])} files")
        return report


def load_model_from_s3(
    s3_endpoint: str,
    bucket: str,
    model_name: str,
) -> Tuple[Any, Dict]:
    """Load model artifact from S3."""
    s3 = boto3.client(
        "s3",
        endpoint_url=s3_endpoint,
        aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID", "minioadmin"),
        aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY", "minioadmin"),
        config=Config(signature_version="s3v4"),
    )
    
    # Find latest model
    prefix = f"models/{model_name}/"
    response = s3.list_objects_v2(Bucket=bucket, Prefix=prefix)
    
    if "Contents" not in response:
        raise ValueError(f"No model found at s3://{bucket}/{prefix}")
    
    model_files = [obj["Key"] for obj in response["Contents"] if obj["Key"].endswith("model.pkl")]
    if not model_files:
        raise ValueError("No model.pkl found")
    
    latest_key = sorted(model_files)[-1]
    logger.info(f"Loading model: {latest_key}")
    
    response = s3.get_object(Bucket=bucket, Key=latest_key)
    artifact = pickle.loads(response["Body"].read())
    
    return artifact["model"], artifact


def load_data_from_db(
    db_host: str,
    db_name: str,
    db_user: str,
    db_password: str,
    sample_size: int = 1000,
) -> Tuple[np.ndarray, np.ndarray, List[str]]:
    """Load feature data from database."""
    import psycopg2
    
    conn = psycopg2.connect(
        host=db_host,
        database=db_name,
        user=db_user,
        password=db_password,
    )
    
    query = f"""
        SELECT * FROM public_marts.fct_readmission_features
        ORDER BY RANDOM()
        LIMIT {sample_size}
    """
    
    df = pd.read_sql(query, conn)
    conn.close()
    
    return df


# =============================================================================
# CLI
# =============================================================================

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="SHAP Analysis for Readmission Model")
    parser.add_argument("--model-name", default="readmission_model")
    parser.add_argument("--output-dir", default="./shap_reports")
    parser.add_argument("--sample-size", type=int, default=1000)
    parser.add_argument("--generate-report", action="store_true")
    args = parser.parse_args()
    
    # Configuration
    DB_HOST = os.getenv("DB_HOST", "localhost")
    DB_NAME = os.getenv("DB_NAME", "mimic")
    DB_USER = os.getenv("DB_USER", "mimic")
    DB_PASSWORD = os.getenv("DB_PASSWORD", "mimic_password")
    S3_ENDPOINT = os.getenv("S3_ENDPOINT_URL", "http://localhost:9000")
    S3_BUCKET = os.getenv("S3_BUCKET_MODELS", "mimic-models")
    
    # Load model
    logger.info("Loading model...")
    model, artifact = load_model_from_s3(S3_ENDPOINT, S3_BUCKET, args.model_name)
    feature_names = artifact.get("feature_names", [])
    scaler = artifact.get("scaler")
    label_encoders = artifact.get("label_encoders", {})
    
    # Load data
    logger.info("Loading data...")
    df = load_data_from_db(DB_HOST, DB_NAME, DB_USER, DB_PASSWORD, args.sample_size)
    
    # Preprocess (same as training)
    from train import ModelTrainer
    trainer = ModelTrainer(DB_HOST, DB_NAME, DB_USER, DB_PASSWORD)
    trainer.label_encoders = label_encoders
    trainer.scaler = scaler
    
    # Get numeric data
    all_features = trainer.NUMERIC_FEATURES + trainer.CATEGORICAL_FEATURES + trainer.BINARY_FEATURES
    feature_cols = [c for c in all_features if c in df.columns]
    
    for col in trainer.NUMERIC_FEATURES:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
            df[col] = df[col].fillna(df[col].median())
    
    for col in trainer.CATEGORICAL_FEATURES:
        if col in df.columns:
            df[col] = df[col].fillna("Unknown")
            if col in label_encoders:
                df[col] = label_encoders[col].transform(df[col].astype(str))
            else:
                df[col] = 0
    
    for col in trainer.BINARY_FEATURES:
        if col in df.columns:
            df[col] = df[col].fillna(0).astype(int)
    
    X = df[feature_cols].values
    if scaler:
        X = scaler.transform(X)
    
    # Create analyzer
    logger.info("Initializing SHAP analyzer...")
    analyzer = SHAPAnalyzer(model, feature_cols, X_background=X)
    
    # Compute SHAP values
    analyzer.compute_shap_values(X, max_samples=args.sample_size)
    
    # Generate report
    if args.generate_report:
        report = analyzer.generate_report(Path(args.output_dir))
        print(f"\nReport generated: {args.output_dir}")
        print("\nTop 10 Features by Importance:")
        for item in report['feature_importance'][:10]:
            print(f"  {item['rank']:2d}. {item['feature']:30s} {item['importance_pct']:5.1f}%")
    else:
        # Print summary
        importance = analyzer.get_feature_importance()
        print("\nTop 20 Features by SHAP Importance:")
        print(importance.head(20).to_string(index=False))
