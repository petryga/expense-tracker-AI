"""The spending assistant's loop, with the model and the tools faked.
Made-up data only."""

import asyncio
from datetime import date
from types import SimpleNamespace
from typing import Any

import pytest

from app.agent.loop import STOPPED, Limits, ToolSpec, Turn, answer_question
from app.agent.mcp_tools import McpToolBox
from app.agent.prompt import CANT_ANSWER, system_prompt

TODAY = date(2026, 11, 17)


def text(t: str) -> Any:
    return SimpleNamespace(type="text", text=t)


def use(name: str, args: dict[str, Any], id: str = "t1") -> Any:
    return SimpleNamespace(type="tool_use", name=name, input=args, id=id)


def reply(*blocks: Any, stop: str = "end_turn") -> Any:
    return SimpleNamespace(
        content=list(blocks),
        stop_reason=stop,
        usage=SimpleNamespace(input_tokens=100, output_tokens=10),
    )


class ScriptedModel:
    """Answers with the given replies in order and records every request."""

    def __init__(self, *replies: Any) -> None:
        self.replies = list(replies)
        self.requests: list[dict[str, Any]] = []

    def create(self, **kwargs: Any) -> Any:
        # Messages are mutated later by the loop; keep a copy as sent.
        self.requests.append({**kwargs, "messages": list(kwargs["messages"])})
        item = self.replies.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


class FakeTools:
    def __init__(self, answers: dict[str, tuple[str, bool]], delay: float = 0) -> None:
        self.answers = answers
        self.delay = delay
        self.calls: list[tuple[str, dict[str, Any]]] = []

    async def tools(self) -> list[ToolSpec]:
        return [
            ToolSpec(name, f"Tool {name}", {"type": "object", "properties": {}})
            for name in self.answers
        ]

    async def call(self, name: str, arguments: dict[str, Any]) -> tuple[str, bool]:
        self.calls.append((name, arguments))
        await asyncio.sleep(self.delay)
        return self.answers[name]


def ask(model: ScriptedModel, tools: FakeTools, **kwargs: Any) -> Any:
    return asyncio.run(
        answer_question(
            kwargs.pop("question", "How much on coffee in October?"),
            kwargs.pop("history", []),
            tools,
            model,
            "test-model",
            today=TODAY,
            **kwargs,
        )
    )


def test_calls_a_tool_then_answers_from_its_result() -> None:
    tools = FakeTools({"spending_report": ('{"spent": {"USD": 11.15}}', False)})
    model = ScriptedModel(
        reply(use("spending_report", {"month": "2026-10"}), stop="tool_use"),
        reply(text("You spent US$11.15 on coffee in October 2026.")),
    )
    result = ask(model, tools)

    assert result.answer == "You spent US$11.15 on coffee in October 2026."
    assert result.outcome == "answered"
    assert result.tool_calls == ["spending_report"]
    assert tools.calls == [("spending_report", {"month": "2026-10"})]
    assert (result.model_calls, result.input_tokens, result.output_tokens) == (2, 200, 20)
    # The tool result went back tied to the call, after the assistant's turn.
    second = model.requests[1]["messages"]
    assert second[1]["role"] == "assistant"
    assert second[2] == {
        "role": "user",
        "content": [
            {"type": "tool_result", "tool_use_id": "t1", "content": '{"spent": {"USD": 11.15}}'}
        ],
    }
    first = model.requests[0]
    assert first["model"] == "test-model"
    assert [t["name"] for t in first["tools"]] == ["spending_report"]
    assert "2026-11-17" in first["system"]


def test_a_tool_error_goes_back_marked_as_an_error() -> None:
    tools = FakeTools({"spending_report": ("Use YYYY-MM, for example 2026-10", True)})
    model = ScriptedModel(
        reply(use("spending_report", {"month": "Oct"}), stop="tool_use"),
        reply(text("Which month do you mean?")),
    )
    ask(model, tools)
    result_block = model.requests[1]["messages"][2]["content"][0]
    assert result_block["is_error"] is True


def test_earlier_turns_come_first() -> None:
    model = ScriptedModel(reply(text("Groceries.")))
    ask(
        model,
        FakeTools({}),
        question="And the biggest category?",
        history=[Turn("user", "Coffee in October?"), Turn("assistant", "US$11.15.")],
    )
    assert model.requests[0]["messages"] == [
        {"role": "user", "content": "Coffee in October?"},
        {"role": "assistant", "content": "US$11.15."},
        {"role": "user", "content": "And the biggest category?"},
    ]


def test_stops_at_the_step_limit() -> None:
    tools = FakeTools({"monthly_summary": ("{}", False)})
    model = ScriptedModel(*[reply(use("monthly_summary", {}), stop="tool_use")] * 3)
    result = ask(model, tools, limits=Limits(max_model_calls=3))
    assert (result.outcome, result.answer) == ("max_steps", STOPPED["max_steps"])
    assert result.tool_calls == ["monthly_summary"] * 3


def test_stops_when_the_question_takes_too_long() -> None:
    tools = FakeTools({"monthly_summary": ("{}", False)}, delay=1)
    model = ScriptedModel(reply(use("monthly_summary", {}), stop="tool_use"))
    result = ask(model, tools, limits=Limits(timeout_s=0.05))
    assert (result.outcome, result.answer) == ("timeout", STOPPED["timeout"])


@pytest.mark.parametrize(
    "outcome",
    [
        RuntimeError("connection reset"),
        reply(text("Half an ans"), stop="max_tokens"),
        reply(stop="refusal"),
        reply(text("   ")),
    ],
)
def test_no_usable_answer_is_a_plain_failure_message(outcome: Any) -> None:
    result = ask(ScriptedModel(outcome), FakeTools({}))
    assert (result.outcome, result.answer) == ("model_error", STOPPED["model_error"])


def test_prompt_states_the_rules() -> None:
    prompt = system_prompt(TODAY)
    assert CANT_ANSWER in prompt
    assert "2026-11" in prompt
    assert "Never add the two currencies" in prompt
    assert "no Markdown" in prompt
    assert "re-checked" in prompt


def mcp_tool(name: str, read_only: bool | None) -> Any:
    annotations = None if read_only is None else SimpleNamespace(read_only_hint=read_only)
    return SimpleNamespace(
        name=name,
        description=f"{name} tool",
        input_schema={"type": "object"},
        annotations=annotations,
    )


class FakeMcpClient:
    def __init__(self) -> None:
        self.called: list[str] = []

    async def list_tools(self) -> Any:
        return SimpleNamespace(
            tools=[
                mcp_tool("spending_report", True),
                mcp_tool("add_expense", False),
                mcp_tool("mystery", None),
            ]
        )

    async def call_tool(self, name: str, arguments: Any, read_timeout_seconds: float) -> Any:
        self.called.append(name)
        return SimpleNamespace(
            content=[SimpleNamespace(type="text", text='{"ok": true}')],
            structured_content=None,
            is_error=False,
        )


def test_mcp_toolbox_offers_only_read_only_tools_and_refuses_the_rest() -> None:
    client = FakeMcpClient()
    box = McpToolBox(client)  # type: ignore[arg-type]

    async def run() -> tuple[list[str], Any, Any]:
        names = [t.name for t in await box.tools()]
        return names, await box.call("spending_report", {}), await box.call("add_expense", {})

    names, read, write = asyncio.run(run())
    assert names == ["spending_report"]
    assert read == ('{"ok": true}', False)
    assert write == ("There is no tool named add_expense.", True)
    assert client.called == ["spending_report"]
