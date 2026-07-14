from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "rental-service"
    database_url: str = "postgresql+psycopg2://drivenow:drivenow@localhost:5432/rental_db"
    fleet_service_url: str = "http://localhost:8001"
    # Must match fleet-service INTERNAL_SERVICE_TOKEN for in_use CAS claims/releases.
    internal_service_token: str = "drivenow-dev-internal"
    log_level: str = "INFO"
    log_dir: str = "logs"


@lru_cache
def get_settings() -> Settings:
    return Settings()
