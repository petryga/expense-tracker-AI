"""Predictors that ask a model, through the same `categorize` the endpoint uses."""

from app.categorizer import Report, categorize_with_report
from app.config import Settings
from app.prompt import Examples
from app.schemas import CategorizeRow
from eval.baselines import Predictor, memory_map
from eval.dataset import LabelledRow
from eval.merchant import merchant_key


def to_categorize_rows(rows: list[LabelledRow]) -> list[CategorizeRow]:
    return [
        CategorizeRow(
            id=r.reference,
            text=r.description,
            amount_cents=r.cents,
            bank_category=r.bank_category or None,
        )
        for r in rows
    ]


def model_predictor(
    settings: Settings, categories: list[str], totals: Report, examples: Examples | None = None
) -> Predictor:
    """The model alone, one call per test month. Adds each call's cost and
    failures into `totals`. `examples` are past choices to show, by row id."""

    def predict(_history: list[LabelledRow], rows: list[LabelledRow]) -> list[str | None]:
        suggestions, report = categorize_with_report(
            to_categorize_rows(rows), categories, settings, examples
        )
        for name in ("calls", "failed_calls", "invalid_answers", "input_tokens", "output_tokens"):
            setattr(totals, name, getattr(totals, name) + getattr(report, name))
        totals.seconds += report.seconds
        totals.errors += report.errors
        return [s.category for s in suggestions]

    return predict


def memory_then_model(model: Predictor) -> Predictor:
    """Merchant memory where the merchant was seen before (its answer, even
    "can't tell", wins); the model is asked only about the rest (decision 3)."""

    def predict(history: list[LabelledRow], rows: list[LabelledRow]) -> list[str | None]:
        known = memory_map(history)  # the same memory as the merchant-memory baseline
        unknown = [r for r in rows if merchant_key(r.description) not in known]
        answers = model(history, unknown) if unknown else []
        asked = dict(zip((r.reference for r in unknown), answers, strict=True))
        return [
            asked[r.reference] if r.reference in asked else known[merchant_key(r.description)]
            for r in rows
        ]

    return predict
