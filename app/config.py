from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Read from the environment (and a local .env). See .env.example."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # BE/ sends this in X-AI-Secret. Empty means "not configured": every
    # request is refused rather than served to anyone who finds the URL.
    ai_shared_secret: str = ""
    log_level: str = "INFO"


@lru_cache
def get_settings() -> Settings:
    return Settings()
