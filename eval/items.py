"""Item-category eval (PLANS.md, Phase D): one order item at a time, the
product name as the text, against the category its owner gave it.

    .venv/bin/python -m eval.items                    # baseline only
    .venv/bin/python -m eval.items --claude MODEL     # plus a Claude model (paid)
    .venv/bin/python -m eval.items --claude MODEL --examples 3
        # three arms: no examples, 3 random past choices, 3 retrieved ones

Labels come from data/item_labels.csv (scripts/export_item_labels.py).
Product names have no history to learn from the way statement merchants do,
so the whole set is one test set. Results also go to results/ (gitignored):
they quote product names.
"""

import argparse
import csv
import json
from collections import Counter
from collections.abc import Iterable
from datetime import datetime
from typing import Literal

from app.categorizer import Report
from app.config import Settings
from app.embeddings import local_embedder
from app.prompt import SYSTEM, Examples, user_message
from eval.baselines import Predictor
from eval.dataset import LabelledRow
from eval.item_examples import random_examples, retrieved_examples
from eval.metrics import Score, score
from eval.model_predictors import model_predictor, to_categorize_rows
from eval.records import to_cents
from eval.run import PRICES, ROOT, categories, cost, pct


def load_item_labels(lines: Iterable[str]) -> list[LabelledRow]:
    return [
        LabelledRow(
            reference=r["id"],
            month=r["date"][:7],
            description=r["text"],
            cents=to_cents(r["amount"]),
            bank_category="",
            label=r["label"].strip() or None,
        )
        for r in csv.DictReader(lines)
    ]


def most_common_label(rows: list[LabelledRow]) -> list[str | None]:
    """Baseline: the label used most often, for every item."""
    top = Counter(r.label for r in rows if r.label).most_common(1)
    return [top[0][0] if top else None] * len(rows)


def by_month(rows: list[LabelledRow], predict: Predictor) -> list[str | None]:
    """One call per month. Examples come from earlier months only, so no item
    in a call can also appear in that call as someone's past choice, label
    and all. Asking every item at once would leak answers that way."""
    answers: dict[str, str | None] = {}
    for month in sorted({r.month for r in rows}):
        asked = [r for r in rows if r.month == month]
        answers.update(zip((r.reference for r in asked), predict([], asked), strict=True))
    return [answers[r.reference] for r in rows]


def estimate(
    model: str, rows: list[LabelledRow], names: list[str], arms: dict[str, Examples | None]
) -> str:
    """Upper bound before a paid call: ~3.5 characters a token, ~60 output
    tokens an item including thinking, summed over the arms."""
    months = [
        to_categorize_rows([r for r in rows if r.month == month])
        for month in sorted({r.month for r in rows})
    ]
    chars = sum(
        len(SYSTEM) + len(user_message(asked, names, shown))
        for shown in arms.values()
        for asked in months
    )
    tokens_in = int(chars / 3.5)
    tokens_out = len(rows) * 60 * len(arms)
    return (
        f"Estimate for {model}: ~{tokens_in} tokens in, ~{tokens_out} out, "
        f"about ${cost(model, tokens_in, tokens_out):.4f} (upper bound)"
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--claude", metavar="MODEL", help="also run this Claude model (paid)")
    parser.add_argument("--effort", default="low", choices=["low", "medium", "high"])
    parser.add_argument(
        "--examples",
        type=int,
        default=0,
        metavar="K",
        help="also run with K random and K retrieved past choices per item",
    )
    parser.add_argument("--yes", action="store_true", help="skip the cost confirmation")
    parser.add_argument("--misses", action="store_true", help="list each arm's misses")
    args = parser.parse_args()

    with (ROOT / "data" / "item_labels.csv").open(newline="") as f:
        rows = load_item_labels(f)
    names = categories()
    labels = [r.label for r in rows]
    texts = [r.description for r in rows]
    unknown = sorted({r.label for r in rows if r.label and r.label not in names})
    if unknown:
        print(f"Labels not in data/categories.csv (re-export it): {unknown}")

    totals: dict[str, Score] = {"most-common": score(texts, labels, most_common_label(rows))}
    reports: dict[str, Report] = {}
    if args.claude:
        arms: dict[str, Examples | None] = {"model": None}
        if args.examples:
            retrieved = retrieved_examples(rows, args.examples, local_embedder())
            arms["random"] = random_examples(rows, args.examples)
            arms["retrieved"] = retrieved
            with_examples = sum(1 for shown in retrieved.values() if shown)
            print(f"{with_examples} of {len(rows)} items have earlier items to show.")
        print(estimate(args.claude, rows, names, arms))
        if not args.yes and input("Run it? [y/N] ").strip().lower() != "y":
            return
        effort: Literal["low", "medium", "high"] = args.effort
        settings = Settings(ai_backend="claude", ai_model=args.claude, ai_effort=effort)
        print(f"Effort: {effort}. Product names are sent to the Anthropic API for this run.\n")
        for arm, shown in arms.items():
            reports[arm] = Report()
            predict = model_predictor(settings, names, reports[arm], shown)
            totals[arm] = score(texts, labels, by_month(rows, predict))

    print(f"{len(rows)} labelled items, {len(set(labels))} categories used\n")
    print(f"{'predictor':<12} {'accuracy':<18} {'precision':<18} no suggestion")
    for name, s in totals.items():
        print(
            f"{name:<12} {pct(s.right, s.category_rows):<18} "
            f"{pct(s.right, s.right + s.wrong):<18} {s.no_suggestion}"
        )
    print()
    for arm, report in reports.items():
        print(
            f"{arm}: {report.calls} calls, {report.failed_calls} failed, "
            f"{report.invalid_answers} invalid, {report.input_tokens} tokens in / "
            f"{report.output_tokens} out, {report.seconds:.0f}s"
            + (
                f", cost ${cost(args.claude, report.input_tokens, report.output_tokens):.4f}"
                if args.claude in PRICES
                else ""
            )
        )
    if args.misses:
        for arm in reports:
            print(f"\nMisses, {arm} (label -> suggestion):")
            for text, label, prediction in totals[arm].misses:
                print(f"  {text[:50]:<50} {label or '-':<22} -> {prediction or '-'}")

    out = ROOT / "results"
    out.mkdir(exist_ok=True)
    path = out / f"items-{datetime.now():%Y%m%d-%H%M%S}.json"
    path.write_text(
        json.dumps(
            {name: vars(s) for name, s in totals.items()}
            | {"reports": {arm: vars(report) for arm, report in reports.items()}},
            indent=2,
            default=str,
        )
    )
    print(f"\nSaved {path.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
