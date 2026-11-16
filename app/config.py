from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Read from the environment (and a local .env). See .env.example."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # BE/ sends this in X-AI-Secret. Empty means "not configured": every
    # request is refused rather than served to anyone who finds the URL.
    ai_shared_secret: str = ""
    log_level: str = "INFO"

    # Which model answers (decision 10). "none" gives no suggestions at all.
    ai_backend: Literal["none", "ollama", "claude"] = "none"
    ai_model: str = ""
    # Only for the "claude" backend. Never in BE/ or FE/ (decision 12).
    anthropic_api_key: str = ""
    # How much the Claude model thinks before answering. Low holds accuracy
    # for this task (see README, eval results) at the lowest cost.
    ai_effort: Literal["low", "medium", "high"] = "low"
    # A local Ollama server; nothing leaves the machine.
    ollama_url: str = "http://localhost:11434"
    # Short, so a slow model never holds an import up for long (decision 11).
    ai_timeout_s: float = 120.0

    # Eval only: the card's account name in the app (see eval/prepare_labels.py).
    eval_card_account: str = ""


@lru_cache
def get_settings() -> Settings:
    return Settings()
