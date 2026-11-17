"""A local model served by Ollama (https://ollama.com). Free, and nothing leaves the machine.

Uses only the standard library, so the service needs no extra dependency for it.
"""

import json
import urllib.request

from app.prompt import SYSTEM, Examples, answer_schema, user_message
from app.schemas import CategorizeRow


def ask(
    url: str,
    model: str,
    rows: list[CategorizeRow],
    categories: list[str],
    timeout_s: float,
    examples: Examples | None = None,
) -> tuple[object, dict[str, int]]:
    """Returns the parsed JSON answer and token counts. Raises on any failure;
    the caller turns failures into "no suggestion"."""
    body = {
        "model": model,
        "stream": False,
        # Constrained decoding against the schema: only listed categories or null.
        "format": answer_schema(categories),
        # Thinking models (Qwen 3 and similar) answer directly; this is a lookup task.
        "think": False,
        "options": {"temperature": 0},
        "messages": [
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": user_message(rows, categories, examples)},
        ],
    }
    request = urllib.request.Request(
        f"{url.rstrip('/')}/api/chat",
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=timeout_s) as response:
        reply = json.load(response)
    tokens = {
        "input_tokens": int(reply.get("prompt_eval_count", 0)),
        "output_tokens": int(reply.get("eval_count", 0)),
    }
    return json.loads(reply["message"]["content"]), tokens
