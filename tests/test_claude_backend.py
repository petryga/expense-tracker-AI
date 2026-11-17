"""The Claude backend with the Anthropic client faked. No network, no key."""

import json
from types import SimpleNamespace
from typing import Any

import anthropic
import pytest

from app import categorizer
from app.backends import claude
from app.config import Settings
from app.schemas import CategorizeRow

ROWS = [CategorizeRow(id="a", text="GREENLEAF MARKET", amount_cents=8642)]
CATEGORIES = ["Groceries", "Clothing"]


class FakeClient:
    def __init__(self, stop_reason: str = "end_turn", answer: Any = None) -> None:
        self.sent: dict[str, Any] = {}
        answer = (
            answer if answer is not None else {"answers": [{"id": "a", "category": "Groceries"}]}
        )
        self.response = SimpleNamespace(
            stop_reason=stop_reason,
            content=[
                SimpleNamespace(type="thinking", thinking=""),
                SimpleNamespace(type="text", text=json.dumps(answer)),
            ],
            usage=SimpleNamespace(input_tokens=500, output_tokens=60),
        )
        self.messages = SimpleNamespace(create=self.create)

    def create(self, **kwargs: Any) -> Any:
        self.sent = kwargs
        return self.response


def test_sends_schema_and_low_effort_and_no_sampling_params() -> None:
    client = FakeClient()
    answer, tokens = claude.ask("k", "claude-haiku-5-5", ROWS, CATEGORIES, 30, client=client)  # type: ignore[arg-type]
    sent = client.sent
    assert sent["model"] == "claude-haiku-5-5"
    assert sent["output_config"]["effort"] == "low"
    assert sent["output_config"]["format"]["type"] == "json_schema"
    assert not {"temperature", "top_p", "top_k"} & set(sent)
    assert sent["messages"][-1]["role"] == "user"  # no prefill
    # The answer is read from the text block, after the thinking block.
    assert answer == {"answers": [{"id": "a", "category": "Groceries"}]}
    assert tokens == {"input_tokens": 500, "output_tokens": 60}


@pytest.mark.parametrize("stop_reason", ["refusal", "max_tokens"])
def test_a_refusal_or_cut_off_answer_raises(stop_reason: str) -> None:
    with pytest.raises(ValueError, match=stop_reason):
        claude.ask("k", "m", ROWS, CATEGORIES, 30, client=FakeClient(stop_reason))  # type: ignore[arg-type]


def test_effort_comes_from_the_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    client = FakeClient()
    monkeypatch.setattr(anthropic, "Anthropic", lambda **_: client)
    categorizer.categorize_with_report(
        ROWS, CATEGORIES, Settings(ai_backend="claude", anthropic_api_key="k", ai_effort="high")
    )
    assert client.sent["output_config"]["effort"] == "high"


def test_categorizer_uses_claude_and_turns_failure_into_no_suggestion(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: list[str] = []

    def ask(api_key: str, model: str, *_: Any, **__: Any) -> Any:
        seen.append(model)
        raise ValueError("stop_reason=refusal")

    monkeypatch.setattr(claude, "ask", ask)
    suggestions, report = categorizer.categorize_with_report(
        ROWS, CATEGORIES, Settings(ai_backend="claude", anthropic_api_key="k")
    )
    assert seen == ["claude-haiku-5-5"]  # the default model
    assert [s.category for s in suggestions] == [None]
    assert (report.failed_calls, report.errors) == (1, ["ValueError"])
