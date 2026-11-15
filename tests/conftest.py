from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from app.config import Settings, get_settings
from app.main import app

SECRET = "test-secret"


@pytest.fixture
def client() -> Iterator[TestClient]:
    app.dependency_overrides[get_settings] = lambda: Settings(ai_shared_secret=SECRET)
    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.fixture
def auth() -> dict[str, str]:
    return {"X-AI-Secret": SECRET}
