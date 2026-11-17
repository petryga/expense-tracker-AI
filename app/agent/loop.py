"""The spending assistant: a tool-calling loop over the Claude API.

The model sees the user's question and the read-only tools from the MCP
server. Each turn it either asks for tool calls, which run here and go back
as results, or answers. Guardrails: a cap on model turns, a time limit for
the whole question, and a fixed answer when it runs out of either.
"""

import asyncio
import json
import time
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Literal, Protocol

from app.agent.prompt import system_prompt

MAX_TOOL_TEXT = 20_000  # characters of one tool result passed to the model


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    input_schema: dict[str, Any]


class ToolBox(Protocol):
    async def tools(self) -> list[ToolSpec]: ...

    async def call(self, name: str, arguments: dict[str, Any]) -> tuple[str, bool]:
        """The result as text, and whether it is an error."""
        ...


class Model(Protocol):
    def create(self, **kwargs: Any) -> Any:
        """One Messages API call (the Anthropic client's messages.create)."""
        ...


@dataclass(frozen=True)
class Turn:
    role: Literal["user", "assistant"]
    text: str


@dataclass
class AgentResult:
    answer: str
    # "answered", or why it stopped early: "max_steps", "timeout", "model_error".
    outcome: str
    tool_calls: list[str] = field(default_factory=list)
    model_calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    seconds: float = 0.0


@dataclass(frozen=True)
class Limits:
    max_model_calls: int = 6
    timeout_s: float = 60.0
    max_tokens: int = 2000


STOPPED = {
    "max_steps": "I couldn't finish that within my step limit. Try a narrower question.",
    "timeout": "That took too long to answer. Try a narrower question.",
    "model_error": "The assistant is unavailable right now. Try again in a moment.",
}


async def answer_question(
    question: str,
    history: Sequence[Turn],
    toolbox: ToolBox,
    model: Model,
    model_name: str,
    limits: Limits = Limits(),
    today: date | None = None,
) -> AgentResult:
    result = AgentResult(answer="", outcome="answered")
    started = time.perf_counter()
    try:
        await asyncio.wait_for(
            _run(question, history, toolbox, model, model_name, limits, today, result),
            timeout=limits.timeout_s,
        )
    except TimeoutError:
        result.outcome, result.answer = "timeout", STOPPED["timeout"]
    finally:
        result.seconds = time.perf_counter() - started
    return result


async def _run(
    question: str,
    history: Sequence[Turn],
    toolbox: ToolBox,
    model: Model,
    model_name: str,
    limits: Limits,
    today: date | None,
    result: AgentResult,
) -> None:
    specs = await toolbox.tools()
    tools = [
        {"name": t.name, "description": t.description, "input_schema": t.input_schema}
        for t in specs
    ]
    messages: list[dict[str, Any]] = [{"role": t.role, "content": t.text} for t in history]
    messages.append({"role": "user", "content": question})
    system = system_prompt(today or date.today())

    while result.model_calls < limits.max_model_calls:
        result.model_calls += 1
        try:
            response = await asyncio.to_thread(
                model.create,
                model=model_name,
                max_tokens=limits.max_tokens,
                system=system,
                tools=tools,
                messages=messages,
            )
        except Exception:  # API error, refusal to connect: no answer, never a crash.
            result.outcome, result.answer = "model_error", STOPPED["model_error"]
            return
        result.input_tokens += response.usage.input_tokens
        result.output_tokens += response.usage.output_tokens

        uses = [b for b in response.content if b.type == "tool_use"]
        if response.stop_reason != "tool_use" or not uses:
            text = "".join(b.text for b in response.content if b.type == "text").strip()
            if response.stop_reason in ("end_turn", "stop_sequence") and text:
                result.answer = text
            else:  # cut off, refused, or empty: not an answer to show
                result.outcome, result.answer = "model_error", STOPPED["model_error"]
            return

        # The assistant turn goes back exactly as received (thinking included).
        messages.append({"role": "assistant", "content": response.content})
        results = []
        for use in uses:
            result.tool_calls.append(use.name)
            text, is_error = await toolbox.call(use.name, dict(use.input or {}))
            results.append(
                {
                    "type": "tool_result",
                    "tool_use_id": use.id,
                    "content": text[:MAX_TOOL_TEXT],
                    **({"is_error": True} if is_error else {}),
                }
            )
        messages.append({"role": "user", "content": results})

    result.outcome, result.answer = "max_steps", STOPPED["max_steps"]


def tool_text(content: Sequence[Any], structured: dict[str, Any] | None) -> str:
    """A tool result as text for the model: the text blocks, else the JSON."""
    texts = [getattr(c, "text", "") for c in content if getattr(c, "type", "") == "text"]
    if any(texts):
        return "\n".join(texts)
    return json.dumps(structured or {})
