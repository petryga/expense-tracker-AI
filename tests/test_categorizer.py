"""The categorizer around a model, with the model faked. Made-up rows only."""

from typing import Any

import pytest

from app import categorizer
from app.backends import ollama
from app.config import Settings
from app.prompt import answer_schema, user_message
from app.schemas import CategorizeRow
from eval.dataset import LabelledRow
from eval.model_predictors import memory_then_model

ROWS = [
    CategorizeRow(id="a", text="GREENLEAF MARKET", amount_cents=8642, bank_category="Groceries"),
    CategorizeRow(id="b", text="EBAY ORDER", amount_cents=1999),
]
CATEGORIES = ["Groceries", "Clothing"]
ON = Settings(ai_backend="ollama", ai_model="test-model")


def fake_model(monkeypatch: pytest.MonkeyPatch, answer: Any) -> list[Any]:
    calls: list[Any] = []

    def ask(*args: Any) -> tuple[Any, dict[str, int]]:
        calls.append(args)
        if isinstance(answer, Exception):
            raise answer
        return answer, {"input_tokens": 100, "output_tokens": 20}

    monkeypatch.setattr(ollama, "ask", ask)
    return calls


def test_keeps_valid_answers_and_null(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_model(
        monkeypatch,
        {"answers": [{"id": "a", "category": "Groceries"}, {"id": "b", "category": None}]},
    )
    suggestions, report = categorizer.categorize_with_report(ROWS, CATEGORIES, ON)
    assert [(s.id, s.category, s.source) for s in suggestions] == [
        ("a", "Groceries", "model"),
        ("b", None, "none"),
    ]
    assert (report.calls, report.input_tokens, report.output_tokens) == (1, 100, 20)


def test_never_passes_on_a_category_the_user_does_not_have(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_model(
        monkeypatch,
        {"answers": [{"id": "a", "category": "Yachts"}, {"id": "zzz", "category": "Groceries"}]},
    )
    suggestions, report = categorizer.categorize_with_report(ROWS, CATEGORIES, ON)
    assert [s.category for s in suggestions] == [None, None]
    assert report.invalid_answers == 1


@pytest.mark.parametrize(
    "answer",
    [TimeoutError("slow"), ConnectionRefusedError(), ValueError("bad json"), ["not", "a", "dict"]],
)
def test_any_failure_means_no_suggestions(monkeypatch: pytest.MonkeyPatch, answer: Any) -> None:
    fake_model(monkeypatch, answer)
    suggestions, _ = categorizer.categorize_with_report(ROWS, CATEGORIES, ON)
    assert [s.category for s in suggestions] == [None, None]


def test_backend_none_never_calls_a_model(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = fake_model(monkeypatch, {"answers": []})
    categorizer.categorize_with_report(ROWS, CATEGORIES, Settings(ai_backend="none"))
    assert calls == []


def test_the_schema_limits_categories_and_the_prompt_lists_them() -> None:
    schema = answer_schema(CATEGORIES)
    item = schema["properties"]["answers"]["items"]  # type: ignore[index]
    assert item["properties"]["category"] == {"anyOf": [{"enum": CATEGORIES}, {"type": "null"}]}
    message = user_message(ROWS, CATEGORIES)
    assert "- Groceries" in message and '"bank_category": "Groceries"' in message
    assert '"amount": "86.42"' in message


def test_memory_then_model_asks_the_model_only_about_unknown_merchants() -> None:
    def row(month: str, text: str, label: str | None) -> LabelledRow:
        return LabelledRow(f"{month}-{text}", month, text, 100, "", label)

    asked: list[str] = []

    def model(_history: list[LabelledRow], rows: list[LabelledRow]) -> list[str | None]:
        asked.extend(r.description for r in rows)
        return ["Hobbies" for _ in rows]

    history = [row("2025-01", "GREENLEAF MARKET", "Groceries"), row("2025-01", "EBAY US", None)]
    test = [
        row("2025-02", "GREENLEAF MARKET", "Groceries"),
        row("2025-02", "EBAY US", None),
        row("2025-02", "NEW SHOP", "Hobbies"),
    ]
    assert memory_then_model(model)(history, test) == ["Groceries", None, "Hobbies"]
    assert asked == ["NEW SHOP"]


def test_large_requests_go_in_chunks_and_a_failed_chunk_costs_only_its_rows(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rows = [CategorizeRow(id=str(i), text="GREENLEAF MARKET", amount_cents=100) for i in range(90)]
    calls: list[int] = []

    def ask(_url: str, _model: str, chunk: list[CategorizeRow], *_: Any) -> Any:
        calls.append(len(chunk))
        if len(calls) == 2:
            raise TimeoutError("slow")
        return {"answers": [{"id": r.id, "category": "Groceries"} for r in chunk]}, {
            "input_tokens": 1,
            "output_tokens": 1,
        }

    monkeypatch.setattr(ollama, "ask", ask)
    suggestions, report = categorizer.categorize_with_report(rows, CATEGORIES, ON)
    assert calls == [40, 40, 10]
    assert (report.calls, report.failed_calls) == (3, 1)
    got = [s.category for s in suggestions]
    assert (
        got[:40] == ["Groceries"] * 40
        and got[40:80] == [None] * 40
        and got[80:] == ["Groceries"] * 10
    )
