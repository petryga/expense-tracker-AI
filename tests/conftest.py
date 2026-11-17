from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from app.config import Settings, get_settings
from app.main import app

SECRET = "test-secret"


@pytest.fixture(autouse=True)
def ignore_local_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Tests never read the developer's AI/.env (a real backend, key or
    secret there must not change what a test does), nor AI_* variables from
    the shell."""
    monkeypatch.setitem(Settings.model_config, "env_file", None)
    get_settings.cache_clear()
    for name in (
        "AI_BACKEND",
        "AI_MODEL",
        "AI_SHARED_SECRET",
        "ANTHROPIC_API_KEY",
        "AI_NEVER_SUGGEST",
        "AI_EFFORT",
        "AI_DATABASE_URL",
        "AI_EXAMPLES_K",
        "MCP_SERVER_COMMAND",
        "MCP_SERVER_ARGS",
        "EXPENSE_TRACKER_API_URL",
        "AI_AGENT_MODEL",
    ):
        monkeypatch.delenv(name, raising=False)


@pytest.fixture
def client() -> Iterator[TestClient]:
    app.dependency_overrides[get_settings] = lambda: Settings(ai_shared_secret=SECRET)
    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.fixture
def auth() -> dict[str, str]:
    return {"X-AI-Secret": SECRET}
