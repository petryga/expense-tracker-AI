"""Baselines the model has to beat (PLANS.md, decision 3). No model involved.

A predictor takes the history rows and the rows to answer, and returns one
category per row, or None for "no suggestion".
"""

from collections import Counter, defaultdict
from collections.abc import Callable

from eval.dataset import LabelledRow
from eval.merchant import merchant_key

Predictor = Callable[[list[LabelledRow], list[LabelledRow]], list[str | None]]


def _most_common(
    history: list[LabelledRow], key: Callable[[LabelledRow], str]
) -> dict[str, str | None]:
    """For each key, the label used most often in history (ties: the most
    recent). A key whose most common answer was "can't tell" maps to None."""
    seen: dict[str, Counter[str | None]] = defaultdict(Counter)
    last: dict[str, dict[str | None, int]] = defaultdict(dict)
    for i, row in enumerate(history):
        k = key(row)
        if k:
            seen[k][row.label] += 1
            last[k][row.label] = i
    return {
        k: max(counts, key=lambda label: (counts[label], last[k][label]))
        for k, counts in seen.items()
    }


def memory_map(history: list[LabelledRow]) -> dict[str, str | None]:
    """Merchant -> the label it most often had in history ("can't tell" is None)."""
    return _most_common(history, lambda r: merchant_key(r.description))


def merchant_memory(history: list[LabelledRow], rows: list[LabelledRow]) -> list[str | None]:
    """The category you gave this merchant before. Unknown merchant: nothing."""
    memory = memory_map(history)
    return [memory.get(merchant_key(r.description)) for r in rows]


def bank_category_mapping(history: list[LabelledRow], rows: list[LabelledRow]) -> list[str | None]:
    """The bank's own category column, mapped to the label it most often had in
    history ("Restaurant-Restaurant" -> "Eating Out")."""
    mapping = _most_common(history, lambda r: r.bank_category)
    return [mapping.get(r.bank_category) for r in rows]


def memory_then_bank(history: list[LabelledRow], rows: list[LabelledRow]) -> list[str | None]:
    """Merchant memory where the merchant is known, the bank-category mapping otherwise."""
    known = memory_map(history)
    by_bank = bank_category_mapping(history, rows)
    return [
        # .get keeps a known merchant's "can't tell" (None) instead of falling back.
        known.get(merchant_key(r.description), fallback)
        for r, fallback in zip(rows, by_bank, strict=True)
    ]
