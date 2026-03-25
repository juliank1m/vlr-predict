"""Application settings loaded from environment variables."""

from functools import lru_cache

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "postgresql+asyncpg://vlr:changeme@localhost:5432/vlr_predict"
    database_url_sync: str = "postgresql://vlr:changeme@localhost:5432/vlr_predict"
    model_path: str = "models/model.joblib"
    feature_config_path: str = "models/feature_config.json"
    training_metadata_path: str = "models/training_metadata.json"
    elo_k_factor: float = 32.0
    elo_start: float = 1500.0
    elo_decay_days: int = 60
    elo_decay_rate: float = 0.02
    model_config = {"env_file": ".env", "protected_namespaces": ("settings_",)}


@lru_cache
def get_settings() -> Settings:
    return Settings()
