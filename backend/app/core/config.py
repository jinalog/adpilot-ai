from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "AdPilot AI"
    app_version: str = "0.1.0"
    app_env: str = "local"
    api_v1_prefix: str = "/api/v1"
    database_url: str = "postgresql+psycopg://adpilot:adpilot@localhost:5432/adpilot"
    ai_provider: str = "mock"
    ai_provider_timeout_seconds: float = 10.0
    ai_provider_max_retries: int = 2
    ai_real_llm_opt_in: bool = False
    openai_api_key: str | None = None
    openai_model: str = "gpt-4.1-mini"
    analyst_provider: str = "mock"
    analyst_provider_timeout_seconds: float = 10.0
    analyst_provider_max_retries: int = 2
    analyst_statement_timeout_ms: int = 2_500
    analyst_absolute_max_rows: int = 500


@lru_cache
def get_settings() -> Settings:
    return Settings()
