"""Building and checking the labelled eval set (PLANS.md, Plan 3, Phase B, step 2).

Pure functions here; the two scripts (`prepare_labels`, `check_labels`) only
read and write files around them. Real data lives in data/ (gitignored).
"""

from dataclasses import dataclass

from eval.guessing import guess
from eval.merchant import merchant_key
from eval.records import CANT_TELL, Charge, Expense, is_amazon

LABEL_COLUMNS = [
    "reference",
    "date",
    "description",
    "amount",
    "bank_category",
    "guess",
    "guess_from",
    "label",
    "checked",
    "note",
]


def build_rows(
    charges: list[Charge],
    expenses: list[Expense],
    existing: dict[str, dict[str, str]],
    account: str = "",
) -> list[dict[str, str]]:
    """One row per non-Amazon charge, oldest first. A row you have labelled or
    checked keeps your label, check and note; only rows still empty take the
    new guess. The guess columns are always refreshed."""
    rows = []
    for charge in sorted(charges, key=lambda c: (c.date, c.reference)):
        if is_amazon(charge):
            continue
        g = guess(charge, expenses, charges, account)
        previous = existing.get(charge.reference, {})
        yours = bool(previous.get("label", "").strip() or previous.get("checked", "").strip())
        rows.append(
            {
                "reference": charge.reference,
                "date": charge.date.isoformat(),
                "description": charge.description,
                "amount": f"{charge.cents / 100:.2f}",
                "bank_category": charge.bank_category,
                "guess": g.category,
                "guess_from": g.source,
                "label": previous["label"] if yours else g.category,
                "checked": previous.get("checked", ""),
                "note": previous.get("note", ""),
            }
        )
    return rows


@dataclass
class LabelReport:
    total: int
    checked: int
    cant_tell: int
    per_month: dict[str, tuple[int, int]]  # month -> (checked, total)
    errors: list[str]


def check(rows: list[dict[str, str]], categories: set[str]) -> LabelReport:
    errors = []
    per_month: dict[str, tuple[int, int]] = {}
    checked = cant_tell = 0
    for row in rows:
        label = row.get("label", "").strip()
        is_checked = row.get("checked", "").strip().lower() in {"y", "yes", "x", "1", "true"}
        month = row["date"][:7]
        done, total = per_month.get(month, (0, 0))
        per_month[month] = (done + is_checked, total + 1)
        where = f"{row['date']} {row['description'][:30]}"
        if label and label != CANT_TELL and label not in categories:
            errors.append(f"{where}: '{label}' is not one of your categories")
        if is_checked:
            checked += 1
            if not label:
                errors.append(f"{where}: checked but has no label")
            if label == CANT_TELL:
                cant_tell += 1
    return LabelReport(len(rows), checked, cant_tell, dict(sorted(per_month.items())), errors)


def inconsistencies(rows: list[dict[str, str]]) -> dict[str, list[dict[str, str]]]:
    """Merchants whose rows carry more than one label. Not always wrong (one
    shop can sell several things), but worth a look."""
    by_merchant: dict[str, list[dict[str, str]]] = {}
    for row in rows:
        if row.get("label", "").strip():
            by_merchant.setdefault(merchant_key(row["description"]), []).append(row)
    return {
        merchant: group
        for merchant, group in sorted(by_merchant.items())
        if merchant and len({r["label"].strip() for r in group}) > 1
    }
