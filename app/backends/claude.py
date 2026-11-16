"""Claude through the Anthropic API (decision 10). Statement text leaves the
machine on this backend; the key lives only in AI/.env (decision 12)."""

import json
from typing import Literal

import anthropic

from app.prompt import SYSTEM, answer_schema, user_message
from app.schemas import CategorizeRow


class ModelStopped(ValueError):
    """The model ended without a usable answer (refusal, or cut off at max_tokens)."""


def ask(
    api_key: str,
    model: str,
    rows: list[CategorizeRow],
    categories: list[str],
    timeout_s: float,
    effort: Literal["low", "medium", "high"] = "low",
    client: anthropic.Anthropic | None = None,
) -> tuple[object, dict[str, int]]:
    """Returns the parsed JSON answer and token counts. Raises on any failure;
    the caller turns failures into "no suggestion"."""
    client = client or anthropic.Anthropic(api_key=api_key, timeout=timeout_s, max_retries=2)
    response = client.messages.create(
        model=model,
        # Room for (low-effort) thinking plus one short answer per row.
        max_tokens=8000,
        system=SYSTEM,
        output_config={
            # Classification: little thinking needed; low is the measured default.
            "effort": effort,
            # Only the user's categories or null can come back.
            "format": {"type": "json_schema", "schema": answer_schema(categories)},
        },
        messages=[{"role": "user", "content": user_message(rows, categories)}],
    )
    if response.stop_reason != "end_turn":
        # A refusal or a cut-off answer is not something to read suggestions from.
        raise ModelStopped(f"stop_reason={response.stop_reason}")
    # Thinking blocks can come first; the answer is the text block.
    text = next(block.text for block in response.content if block.type == "text")
    tokens = {
        "input_tokens": response.usage.input_tokens,
        "output_tokens": response.usage.output_tokens,
    }
    return json.loads(text), tokens
