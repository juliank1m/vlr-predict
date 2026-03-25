"""Application settings loaded from environment variables."""

import os
from functools import lru_cache

from pydantic_settings import BaseSettings

_is_production = bool(
    os.getenv("RAILWAY_ENVIRONMENT_NAME") or os.getenv("NODE_ENV") == "production"
)

# Local-only defaults; production must set DATABASE_URL / DATABASE_URL_SYNC.
_DB_DEFAULT = None if _is_production else "postgresql+asyncpg://vlr:changeme@localhost:5432/vlr_predict"
_DB_SYNC_DEFAULT = None if _is_production else "postgresql://vlr:changeme@localhost:5432/vlr_predict"


class Settings(BaseSettings):
    database_url: str = _DB_DEFAULT  # type: ignore[assignment]
    database_url_sync: str = _DB_SYNC_DEFAULT  # type: ignore[assignment]
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
