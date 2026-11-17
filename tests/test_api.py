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


def test_categorize_accepts_a_user_and_item_rows(client: TestClient, auth: dict[str, str]) -> None:
    body = {
        "rows": [{"id": "i1", "text": "Test Garden Hose", "amountCents": 1250, "kind": "item"}],
        "categories": ["Garden"],
        "userId": "11111111-1111-4111-8111-111111111111",
    }
    res = client.post("/categorize", json=body, headers=auth)
    assert res.status_code == 200
    assert client.post("/categorize", json=body | {"userId": None}, headers=auth).status_code == 200
    bad = body | {"userId": "not-a-uuid"}
    assert client.post("/categorize", json=bad, headers=auth).status_code == 422


def test_item_rows_are_shown_past_choices_and_statement_rows_are_not(
    auth: dict[str, str], monkeypatch: Any
) -> None:
    from app import examples_store, main, retrieval
    from app.prompt import Example

    asked: dict[str, Any] = {}

    def nearest(url: str, user_id: str | None, vectors: Any, categories: Any, k: int) -> Any:
        asked.update(url=url, user_id=user_id, count=len(vectors), k=k)
        return [[Example("Test Hose Reel", "Garden")]]

    def categorize(rows: Any, categories: Any, settings: Any, examples: Any) -> Any:
        asked["examples"] = examples
        return [], None

    monkeypatch.setattr(examples_store, "nearest", nearest)
    monkeypatch.setattr(retrieval, "default_embedder", lambda: lambda texts: [[1.0] for _ in texts])
    monkeypatch.setattr(main, "categorize_with_report", categorize)
    app.dependency_overrides[get_settings] = lambda: Settings(
        ai_shared_secret="test-secret", ai_database_url="postgresql://example.invalid/db"
    )
    try:
        body = {
            "rows": [
                {"id": "r1", "text": "GREENLEAF MARKET", "amountCents": 100},
                {"id": "i1", "text": "Test Garden Hose", "amountCents": 1250, "kind": "item"},
            ],
            "categories": ["Garden"],
        }
        assert TestClient(app).post("/categorize", json=body, headers=auth).status_code == 200
    finally:
        app.dependency_overrides.clear()
    # Only the item was looked up, for the local user (no id).
    assert (asked["user_id"], asked["count"], asked["k"]) == (None, 1, 3)
    assert asked["examples"] == {"i1": [Example("Test Hose Reel", "Garden")]}


def test_examples_sync_needs_the_secret_and_a_configured_store(
    client: TestClient, auth: dict[str, str]
) -> None:
    body = {"examples": [{"source": "s1", "text": "Test Garden Hose", "category": "Garden"}]}
    assert client.put("/examples", json=body).status_code == 401
    # No database configured: BE/ carries on without retrieval.
    assert client.put("/examples", json=body, headers=auth).status_code == 503


def test_examples_sync_stores_the_set_and_hides_store_errors(
    auth: dict[str, str], monkeypatch: Any
) -> None:
    from app import main
    from app.examples_store import StoredExample, SyncResult

    calls: list[Any] = []

    def sync(url: str, user_id: str | None, kind: str, examples: Any, embed: Any) -> SyncResult:
        calls.append((user_id, kind, examples))
        if not examples:
            raise RuntimeError("Test Garden Hose could not be stored")
        return SyncResult(stored=len(examples), embedded=1, removed=0)

    monkeypatch.setattr(main, "sync", sync)
    monkeypatch.setattr(main, "default_embedder", lambda: None)
    app.dependency_overrides[get_settings] = lambda: Settings(
        ai_shared_secret="test-secret", ai_database_url="postgresql://example.invalid/db"
    )
    try:
        client = TestClient(app)
        user = "11111111-1111-4111-8111-111111111111"
        body = {
            "userId": user,
            "examples": [{"source": "s1", "text": "Test Garden Hose", "category": "Garden"}],
        }
        res = client.put("/examples", json=body, headers=auth)
        assert res.json() == {"stored": 1, "embedded": 1, "removed": 0}
        assert calls == [(user, "item", [StoredExample("s1", "Test Garden Hose", "Garden")])]
        failed = client.put("/examples", json={"examples": []}, headers=auth)
        assert failed.status_code == 503
        assert "Hose" not in failed.text
    finally:
        app.dependency_overrides.clear()
