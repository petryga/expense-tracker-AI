"""Runs predictors over the labelled set, month by month, and prints the results.

    .venv/bin/python -m eval.run                 # baselines only
    .venv/bin/python -m eval.run --ollama MODEL  # plus a local model, alone and after memory
    .venv/bin/python -m eval.run --misses memory # also list one predictor's misses

Each month is answered using only earlier months. Results also go to
results/ (gitignored): they quote statement descriptions.
"""

import argparse
import csv
import json
from datetime import datetime
from pathlib import Path
from typing import Literal

from app.categorizer import Report
from app.config import Settings
from app.prompt import SYSTEM, user_message
from eval.baselines import Predictor, bank_category_mapping, memory_then_bank, merchant_memory
from eval.dataset import load_labels, monthly_splits
from eval.metrics import Score, score
from eval.model_predictors import memory_then_model, model_predictor, to_categorize_rows

ROOT = Path(__file__).resolve().parent.parent
# Before August 2025 there are only a handful of rows a month; those months are
# history only.
FIRST_TEST_MONTH = "2025-08"

PREDICTORS: dict[str, Predictor] = {
    "memory": merchant_memory,
    "bank-map": bank_category_mapping,
    "memory+bank": memory_then_bank,
}


def pct(part: int, whole: int) -> str:
    return f"{100 * part / whole:5.1f}% ({part}/{whole})" if whole else "    -"


def categories() -> list[str]:
    with (ROOT / "data" / "categories.csv").open(newline="") as f:
        return [row["name"] for row in csv.DictReader(f)]


# $ per million tokens, input / output (Claude API, prompts under 100K tokens;
# from the Claude API skill's model table, 2026-11-03). Local models cost nothing.
PRICES = {
    "claude-haiku-5-5": (0.10, 0.50),
    "claude-sonnet-5-5": (2.00, 10.00),
    "claude-opus-5-5": (4.00, 20.00),
}


def cost(model: str, input_tokens: int, output_tokens: int) -> float:
    price_in, price_out = PRICES.get(model, (0.0, 0.0))
    return (input_tokens * price_in + output_tokens * price_out) / 1_000_000


def estimate(model: str) -> str:
    """Before any paid call: prompt size from the real prompts (about 3.5
    characters a token), and about 60 output tokens a row including thinking.
    Both predictors together; memory+model asks about fewer rows."""
    with (ROOT / "data" / "labels.csv").open(newline="") as f:
        rows = load_labels(f)
    names = categories()
    chars = n_rows = 0
    for split in monthly_splits(rows, FIRST_TEST_MONTH):
        chars += len(SYSTEM) + len(user_message(to_categorize_rows(split.test), names))
        n_rows += len(split.test)
    tokens_in = int(chars / 3.5 * 2)  # two predictors, upper bound
    tokens_out = n_rows * 60 * 2
    return (
        f"Estimate for {model}: ~{tokens_in} tokens in, ~{tokens_out} out, "
        f"about ${cost(model, tokens_in, tokens_out):.3f} (upper bound)"
    )


def add_model(
    backend: str, model: str, url: str = "", effort: Literal["low", "medium", "high"] = "low"
) -> dict[str, Report]:
    """Registers "model" and "memory+model" for one model."""
    # A whole month per call on a local model can be slow; this is a batch run, not an import.
    settings = Settings(
        ai_backend=backend,
        ai_model=model,
        ollama_url=url or "http://localhost:11434",
        ai_timeout_s=900,
        ai_effort=effort,
    )
    reports = {"model": Report(), "memory+model": Report()}
    PREDICTORS["model"] = model_predictor(settings, categories(), reports["model"])
    PREDICTORS["memory+model"] = memory_then_model(
        model_predictor(settings, categories(), reports["memory+model"])
    )
    return reports


def run(names: list[str]) -> dict[str, Score]:
    with (ROOT / "data" / "labels.csv").open(newline="") as f:
        rows = load_labels(f)
    totals = {name: Score() for name in names}
    for split in monthly_splits(rows, FIRST_TEST_MONTH):
        for name in names:
            predictions = PREDICTORS[name](split.history, split.test)
            totals[name].merge(
                score(
                    [r.description for r in split.test],
                    [r.label for r in split.test],
                    predictions,
                )
            )
    return totals


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "predictors", nargs="*", help="which to run (default: baselines, plus model ones)"
    )
    parser.add_argument("--misses", help="print the misses of this predictor")
    parser.add_argument("--ollama", metavar="MODEL", help="also run this local Ollama model")
    parser.add_argument("--ollama-url", default="http://localhost:11434")
    parser.add_argument("--claude", metavar="MODEL", help="also run this Claude model (paid)")
    parser.add_argument("--yes", action="store_true", help="skip the cost confirmation")
    parser.add_argument("--effort", default="low", choices=["low", "medium", "high"])
    args = parser.parse_args()

    reports: dict[str, Report] = {}
    names = args.predictors or list(PREDICTORS)
    model_name = args.claude or args.ollama
    if args.claude:
        print(estimate(args.claude))
        if not args.yes and input("Run it? [y/N] ").strip().lower() != "y":
            return
        reports = add_model("claude", args.claude, effort=args.effort)
        print(f"Effort: {args.effort}")
        print("Statement text is sent to the Anthropic API for this run.\n")
    elif args.ollama:
        reports = add_model("ollama", args.ollama, args.ollama_url)
        print(f"Local model {args.ollama} via Ollama: no cost, nothing leaves this machine.\n")
    if not args.predictors:  # nothing named: run the model ones too
        names = [*names, *(n for n in reports if n not in names)]

    totals = run(names)
    any_score = next(iter(totals.values()))
    print(
        f"Test months {FIRST_TEST_MONTH} on: {any_score.category_rows} rows with a category, "
        f"{any_score.cant_tell_rows} can't-tell rows\n"
    )
    header = ("predictor", "accuracy", "precision", "held back on can't tell")
    print(f"{header[0]:<12} {header[1]:<18} {header[2]:<18} {header[3]}")
    for name, s in totals.items():
        print(
            f"{name:<12} {pct(s.right, s.category_rows):<18} "
            f"{pct(s.right, s.right + s.wrong):<18} {pct(s.held_back, s.cant_tell_rows)}"
        )

    for name, r in reports.items():
        print(
            f"{name}: {r.calls} calls, {r.failed_calls} failed, "
            f"{r.invalid_answers} invalid answers, "
            f"{r.input_tokens} tokens in / {r.output_tokens} out, {r.seconds:.0f}s"
            + (f", errors: {sorted(set(r.errors))}" if r.errors else "")
            + (
                f", cost ${cost(model_name, r.input_tokens, r.output_tokens):.4f}"
                if model_name in PRICES
                else ""
            )
        )

    if args.misses in totals:
        print(f"\nMisses of {args.misses} (label -> suggestion):")
        for description, label, prediction in totals[args.misses].misses:
            shown = label or "can't tell"
            print(f"  {description[:40]:<40} {shown:<20} -> {prediction or '-'}")

    out = ROOT / "results"
    out.mkdir(exist_ok=True)
    path = out / f"eval-{datetime.now():%Y%m%d-%H%M%S}.json"
    path.write_text(
        json.dumps(
            {
                name: {k: v for k, v in vars(s).items() if k != "misses"}
                | {"misses": s.misses}
                | ({"report": vars(reports[name])} if name in reports else {})
                for name, s in totals.items()
            },
            indent=2,
        )
    )
    print(f"\nSaved {path.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
