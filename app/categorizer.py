"""Suggests a category per statement row.

The endpoint and the eval runner both call `categorize`, so what the eval
measures is exactly what the app serves.
"""

import logging
import time
from dataclasses import dataclass, field

from app.backends import claude, ollama
from app.config import Settings, get_settings
from app.schemas import CategorizeRow, Suggestion

log = logging.getLogger("ai")


@dataclass
class Report:
    """What one categorize call cost and how it went, for the eval and logs."""

    calls: int = 0
    failed_calls: int = 0
    invalid_answers: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    seconds: float = 0.0
    errors: list[str] = field(default_factory=list)


def _none(rows: list[CategorizeRow]) -> list[Suggestion]:
    return [Suggestion(id=row.id, category=None, source="none") for row in rows]


def _read_answers(
    answer: object, rows: list[CategorizeRow], categories: list[str], report: Report
) -> list[Suggestion]:
    """Checks the model's answer in code (decision 5): known ids only, and only
    categories from the user's list. Anything else becomes no suggestion."""
    by_id: dict[str, str | None] = {}
    items = answer.get("answers") if isinstance(answer, dict) else None
    if not isinstance(items, list):
        report.invalid_answers += len(rows)
        return _none(rows)
    allowed = set(categories)
    for item in items:
        if not isinstance(item, dict):
            continue
        row_id, category = item.get("id"), item.get("category")
        if isinstance(row_id, str) and (category is None or category in allowed):
            by_id[row_id] = category
        else:
            report.invalid_answers += 1
    suggestions = []
    for row in rows:
        category = by_id.get(row.id)
        source = "model" if category else "none"
        suggestions.append(Suggestion(id=row.id, category=category, source=source))
    return suggestions


def categorize_with_report(
    rows: list[CategorizeRow], categories: list[str], settings: Settings | None = None
) -> tuple[list[Suggestion], Report]:
    settings = settings or get_settings()
    report = Report()
    never = set(settings.ai_never_suggest)
    categories = [c for c in categories if c not in never]
    if not rows or not categories or settings.ai_backend == "none":
        return _none(rows), report

    started = time.perf_counter()
    report.calls += 1
    try:
        if settings.ai_backend == "claude":
            answer, tokens = claude.ask(
                settings.anthropic_api_key,
                settings.ai_model or "claude-haiku-5-5",
                rows,
                categories,
                settings.ai_timeout_s,
                settings.ai_effort,
            )
        else:
            answer, tokens = ollama.ask(
                settings.ollama_url, settings.ai_model, rows, categories, settings.ai_timeout_s
            )
    except (
        Exception
    ) as error:  # Timeout, connection, HTTP or bad JSON: no suggestions (decision 11).
        report.failed_calls += 1
        report.errors.append(type(error).__name__)
        log.warning("categorize failed: %s", type(error).__name__)
        return _none(rows), report
    finally:
        report.seconds += time.perf_counter() - started
    report.input_tokens += tokens["input_tokens"]
    report.output_tokens += tokens["output_tokens"]
    return _read_answers(answer, rows, categories, report), report


def categorize(rows: list[CategorizeRow], categories: list[str]) -> list[Suggestion]:
    return categorize_with_report(rows, categories)[0]
