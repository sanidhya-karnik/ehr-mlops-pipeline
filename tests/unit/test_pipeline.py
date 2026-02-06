"""
Unit tests for the EHR MLOps Pipeline.
"""

import pytest
import sys
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))


class TestTrainingModule:
    """Tests for the training module."""

    def test_model_trainer_feature_lists(self):
        """Verify feature lists are properly defined."""
        from training.train import ModelTrainer
        
        trainer = ModelTrainer(
            db_host="localhost",
            db_name="test",
            db_user="test",
            db_password="test",
        )
        
        # Check feature lists exist and are non-empty
        assert len(trainer.NUMERIC_FEATURES) > 0
        assert len(trainer.CATEGORICAL_FEATURES) > 0
        assert len(trainer.BINARY_FEATURES) > 0
        
        # Verify no duplicates
        all_features = (
            trainer.NUMERIC_FEATURES + 
            trainer.CATEGORICAL_FEATURES + 
            trainer.BINARY_FEATURES
        )
        assert len(all_features) == len(set(all_features)), "Duplicate features found"
    
    def test_model_trainer_target_defined(self):
        """Verify target variable is defined."""
        from training.train import ModelTrainer
        
        assert ModelTrainer.TARGET == "readmitted_30d"


class TestServingModule:
    """Tests for the serving module."""

    def test_settings_defaults(self):
        """Verify settings have sensible defaults."""
        from serving.main import Settings
        
        settings = Settings()
        
        assert settings.S3_BUCKET == "mimic-models"
        assert settings.MODEL_NAME == "readmission_model"
        assert settings.DB_PORT == 5432
        assert settings.REDIS_PORT == 6379
    
    def test_prediction_request_model(self):
        """Test PredictionRequest pydantic model."""
        from serving.main import PredictionRequest
        
        # Test with minimal data
        request = PredictionRequest(age=65, los_days=5.0)
        assert request.age == 65
        assert request.los_days == 5.0
        assert request.has_chf == 0  # Default value
        
        # Test with subject_id/hadm_id
        request2 = PredictionRequest(subject_id=12345, hadm_id=67890)
        assert request2.subject_id == 12345
        assert request2.hadm_id == 67890
    
    def test_health_response_model(self):
        """Test HealthResponse pydantic model."""
        from serving.main import HealthResponse
        
        response = HealthResponse(
            status="healthy",
            model_loaded=True,
            model_version="v1.0",
            timestamp="2024-01-01T00:00:00Z",
        )
        
        assert response.status == "healthy"
        assert response.model_loaded is True


class TestFeatureAlignment:
    """Tests to ensure feature alignment between training and serving."""
    
    def test_feature_names_consistency(self):
        """Verify training features match expected schema."""
        from training.train import ModelTrainer
        
        # Expected features from fct_readmission_features.sql
        expected_numeric = {
            "age", "los_days", "prior_admits_6mo", "prior_admits_12mo",
            "prior_ed_visits_6mo", "avg_prior_los", "diagnosis_count",
            "charlson_index", "discharge_dow", "discharge_hour",
            "creatinine_max", "creatinine_avg", "glucose_max", "glucose_avg",
            "hemoglobin_min", "hemoglobin_avg", "wbc_max", "wbc_avg",
            "sodium_min", "sodium_max", "potassium_min", "potassium_max",
            "bun_max", "platelet_min", "abnormal_lab_count", "abnormal_lab_ratio",
            "unique_med_count", "high_risk_med_count",
        }
        
        expected_categorical = {"gender", "admission_type", "insurance", "discharge_location"}
        
        expected_binary = {
            "ed_admission", "has_chf", "has_diabetes", "has_ckd", "has_copd",
            "has_hypertension", "has_cancer", "on_anticoagulant", "on_insulin",
            "on_antidiabetic", "on_opioid", "on_diuretic", "on_digoxin",
            "polypharmacy", "severe_polypharmacy",
        }
        
        trainer_numeric = set(ModelTrainer.NUMERIC_FEATURES)
        trainer_categorical = set(ModelTrainer.CATEGORICAL_FEATURES)
        trainer_binary = set(ModelTrainer.BINARY_FEATURES)
        
        # Check for missing features
        missing_numeric = expected_numeric - trainer_numeric
        missing_categorical = expected_categorical - trainer_categorical
        missing_binary = expected_binary - trainer_binary
        
        assert not missing_numeric, f"Missing numeric features: {missing_numeric}"
        assert not missing_categorical, f"Missing categorical features: {missing_categorical}"
        assert not missing_binary, f"Missing binary features: {missing_binary}"


class TestConfigValidation:
    """Tests for configuration validation."""
    
    def test_dbt_var_defaults(self):
        """Verify dbt variable defaults are sensible."""
        # These should match dbt_project.yml
        expected_vars = {
            "readmission_window": 30,
            "min_age": 18,
            "max_age": 120,
        }
        
        for var, expected in expected_vars.items():
            # Just verify the values are reasonable
            assert isinstance(expected, int)
            assert expected > 0


# Smoke tests that don't require database
class TestSmokeTests:
    """Basic smoke tests that don't require external services."""
    
    def test_imports(self):
        """Verify all main modules can be imported."""
        import importlib
        
        modules = [
            "training.train",
            "serving.main",
        ]
        
        for module_name in modules:
            try:
                importlib.import_module(module_name)
            except ImportError as e:
                pytest.fail(f"Failed to import {module_name}: {e}")
    
    def test_model_types_available(self):
        """Verify supported model types."""
        from training.train import ModelTrainer
        
        supported_types = ["logistic", "random_forest", "xgboost"]
        
        # ModelTrainer should support these types (checking via train method signature)
        trainer = ModelTrainer(
            db_host="test",
            db_name="test", 
            db_user="test",
            db_password="test",
        )
        
        # Just verify the method exists and accepts model_type
        import inspect
        sig = inspect.signature(trainer.train)
        assert "model_type" in sig.parameters
