"""Item-category eval (PLANS.md, Phase D): one order item at a time, the
product name as the text, against the category its owner gave it.

    .venv/bin/python -m eval.items                    # baseline only
    .venv/bin/python -m eval.items --claude MODEL     # plus a Claude model (paid)

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
from app.prompt import SYSTEM, user_message
from eval.dataset import LabelledRow
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


def estimate(model: str, rows: list[LabelledRow], names: list[str]) -> str:
    """Upper bound before a paid call: ~3.5 characters a token, ~60 output
    tokens an item including thinking."""
    tokens_in = int((len(SYSTEM) + len(user_message(to_categorize_rows(rows), names))) / 3.5)
    tokens_out = len(rows) * 60
    return (
        f"Estimate for {model}: ~{tokens_in} tokens in, ~{tokens_out} out, "
        f"about ${cost(model, tokens_in, tokens_out):.4f} (upper bound)"
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--claude", metavar="MODEL", help="also run this Claude model (paid)")
    parser.add_argument("--effort", default="low", choices=["low", "medium", "high"])
    parser.add_argument("--yes", action="store_true", help="skip the cost confirmation")
    parser.add_argument("--misses", action="store_true", help="list the model's misses")
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
    report = Report()
    if args.claude:
        print(estimate(args.claude, rows, names))
        if not args.yes and input("Run it? [y/N] ").strip().lower() != "y":
            return
        effort: Literal["low", "medium", "high"] = args.effort
        settings = Settings(ai_backend="claude", ai_model=args.claude, ai_effort=effort)
        print(f"Effort: {effort}. Product names are sent to the Anthropic API for this run.\n")
        predict = model_predictor(settings, names, report)
        totals["model"] = score(texts, labels, predict([], rows))

    print(f"{len(rows)} labelled items, {len(set(labels))} categories used\n")
    print(f"{'predictor':<12} {'accuracy':<18} {'precision':<18} no suggestion")
    for name, s in totals.items():
        print(
            f"{name:<12} {pct(s.right, s.category_rows):<18} "
            f"{pct(s.right, s.right + s.wrong):<18} {s.no_suggestion}"
        )
    if args.claude:
        print(
            f"\nmodel: {report.calls} calls, {report.failed_calls} failed, "
            f"{report.invalid_answers} invalid, {report.input_tokens} tokens in / "
            f"{report.output_tokens} out, {report.seconds:.0f}s"
            + (
                f", cost ${cost(args.claude, report.input_tokens, report.output_tokens):.4f}"
                if args.claude in PRICES
                else ""
            )
        )
        if args.misses:
            print("\nMisses (label -> suggestion):")
            for text, label, prediction in totals["model"].misses:
                print(f"  {text[:50]:<50} {label or '-':<22} -> {prediction or '-'}")

    out = ROOT / "results"
    out.mkdir(exist_ok=True)
    path = out / f"items-{datetime.now():%Y%m%d-%H%M%S}.json"
    path.write_text(
        json.dumps(
            {name: vars(s) for name, s in totals.items()}
            | ({"report": vars(report)} if args.claude else {}),
            indent=2,
            default=str,
        )
    )
    print(f"\nSaved {path.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
