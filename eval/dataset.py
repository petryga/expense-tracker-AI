"""The labelled eval set and its month-by-month split.

Each month is a test month in turn, scored using only the months before it
(PLANS.md, "Data in hand": the set is small, so every month counts).
"""

import csv
from collections.abc import Iterable, Iterator
from dataclasses import dataclass

from eval.records import CANT_TELL


@dataclass(frozen=True)
class LabelledRow:
    reference: str
    month: str  # YYYY-MM
    description: str
    cents: int
    bank_category: str
    label: str | None  # None means "can't tell from the row"


def load_labels(lines: Iterable[str]) -> list[LabelledRow]:
    """Checked rows only."""
    rows = []
    for r in csv.DictReader(lines):
        if r.get("checked", "").strip().lower() not in {"y", "yes", "x", "1", "true"}:
            continue
        label = r["label"].strip()
        rows.append(
            LabelledRow(
                reference=r["reference"],
                month=r["date"][:7],
                description=r["description"],
                cents=round(float(r["amount"]) * 100),
                bank_category=r["bank_category"],
                label=None if label == CANT_TELL else label,
            )
        )
    return rows


@dataclass(frozen=True)
class Split:
    month: str
    history: list[LabelledRow]
    test: list[LabelledRow]
    # Test rows left out because their label can't be known from the row.
    excluded: int = 0


def monthly_splits(
    rows: list[LabelledRow], first_test_month: str, never_suggest: frozenset[str] = frozenset()
) -> Iterator[Split]:
    """One split per month from first_test_month on. History is strictly
    earlier months, so nothing from a test month ever informs its own answers.

    Rows labelled with a never-suggested category ("Gifts") are left out of
    both: no predictor may produce that label, and one gift says nothing about
    what a shop usually is."""
    knowable = [r for r in rows if r.label not in never_suggest]
    for month in sorted({r.month for r in rows if r.month >= first_test_month}):
        yield Split(
            month=month,
            history=[r for r in knowable if r.month < month],
            test=[r for r in knowable if r.month == month],
            excluded=sum(1 for r in rows if r.month == month and r.label in never_suggest),
        )
