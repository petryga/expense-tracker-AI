"""Synthetic rows only; real statement data never goes in tests."""

from typing import Any

from fastapi.testclient import TestClient

from app.config import Settings, get_settings
from app.main import app

BODY: dict[str, Any] = {
    "rows": [
        {"id": "r1", "text": "GREENLEAF MARKET SPRINGFIELD", "amountCents": 8642},
        {"id": "r2", "text": "AMAZON.COM*DEMO1", "amountCents": 3499},
    ],
    "categories": ["Groceries", "Clothing"],
}


def test_health_needs_no_secret(client: TestClient) -> None:
    res = client.get("/health")
    assert res.status_code == 200
    assert res.json() == {"status": "ok"}


def test_categorize_returns_one_suggestion_per_row_in_camel_case(
    client: TestClient, auth: dict[str, str]
) -> None:
    res = client.post("/categorize", json=BODY, headers=auth)
    assert res.status_code == 200
    assert res.json() == {
        "suggestions": [
            {"id": "r1", "category": None, "source": "none"},
            {"id": "r2", "category": None, "source": "none"},
        ]
    }


def test_categorize_rejects_a_missing_or_wrong_secret(client: TestClient) -> None:
    assert client.post("/categorize", json=BODY).status_code == 401
    assert client.post("/categorize", json=BODY, headers={"X-AI-Secret": "nope"}).status_code == 401


def test_refuses_everything_when_the_secret_is_not_configured() -> None:
    app.dependency_overrides[get_settings] = lambda: Settings(ai_shared_secret="")
    try:
        res = TestClient(app).post("/categorize", json=BODY, headers={"X-AI-Secret": ""})
        assert res.status_code == 503
    finally:
        app.dependency_overrides.clear()


def test_validates_the_request(client: TestClient, auth: dict[str, str]) -> None:
    bad = {"rows": [{"id": "", "text": "x", "amountCents": 1}], "categories": []}
    assert client.post("/categorize", json=bad, headers=auth).status_code == 422
    extra = {**BODY, "userId": "someone"}
    assert client.post("/categorize", json=extra, headers=auth).status_code == 422
    too_many = {"rows": [BODY["rows"][0]] * 501, "categories": ["A"]}
    assert client.post("/categorize", json=too_many, headers=auth).status_code == 422


def test_echoes_a_well_formed_request_id_and_replaces_a_bad_one(client: TestClient) -> None:
    assert (
        client.get("/health", headers={"X-Request-Id": "abc-123"}).headers["x-request-id"]
        == "abc-123"
    )
    replaced = client.get("/health", headers={"X-Request-Id": "bad id"}).headers["x-request-id"]
    assert replaced != "bad id" and len(replaced) == 36
