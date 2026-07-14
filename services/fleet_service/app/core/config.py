from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "fleet-service"
    database_url: str = "postgresql+psycopg2://drivenow:drivenow@localhost:5432/fleet_db"
    log_level: str = "INFO"
    log_dir: str = "logs"


@lru_cache
def get_settings() -> Settings:
    return Settings()
