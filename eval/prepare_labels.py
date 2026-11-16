"""Writes data/labels.csv: one row per non-Amazon card charge, with a guess.

    .venv/bin/python -m eval.prepare_labels

Safe to re-run: labels and checks you already made are kept. Set
EVAL_CARD_ACCOUNT to the card's account name in the app, so only expenses
entered on that card are used for guesses.
"""

import csv
from pathlib import Path

from app.config import Settings
from eval.labels import LABEL_COLUMNS, build_rows
from eval.records import read_expenses, read_statement

DATA = Path(__file__).resolve().parent.parent / "data"


def main() -> None:
    charges = []
    for path in sorted((DATA / "statements").glob("*.csv")):
        with path.open(newline="") as f:
            charges += read_statement(f)
    with (DATA / "expenses.csv").open(newline="") as f:
        expenses = read_expenses(f)

    out = DATA / "labels.csv"
    existing: dict[str, dict[str, str]] = {}
    if out.exists():
        with out.open(newline="") as f:
            existing = {row["reference"]: row for row in csv.DictReader(f)}

    rows = build_rows(charges, expenses, existing, Settings().eval_card_account)
    with out.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=LABEL_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)

    guessed = sum(1 for r in rows if r["guess"])
    print(f"Wrote {out.relative_to(DATA.parent)}: {len(rows)} rows, {guessed} with a guess.")


if __name__ == "__main__":
    main()
