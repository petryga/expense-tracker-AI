"""Statement charges and hand-entered expenses, read from the CSVs in data/."""

import csv
import re
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, datetime

CANT_TELL = "can't tell"

# Amazon rows are left out: Phase D matches them to orders instead.
_AMAZON = re.compile(r"AMAZON|AMZN|PRIME VIDEO", re.IGNORECASE)


@dataclass(frozen=True)
class Charge:
    reference: str
    date: date
    description: str
    cents: int
    bank_category: str


@dataclass(frozen=True)
class Expense:
    date: date
    description: str
    category: str
    cents: int
    account: str


def to_cents(value: str) -> int:
    cleaned = value.strip().replace("$", "").replace(",", "")
    negative = cleaned.startswith("-")
    whole, _, frac = cleaned.lstrip("-").partition(".")
    cents = int(whole or "0") * 100 + int((frac + "00")[:2])
    return -cents if negative else cents


def read_statement(lines: Iterable[str]) -> list[Charge]:
    """Charges only (positive amounts): payments, rewards and refunds are not labelled."""
    charges = []
    for row in csv.DictReader(lines):
        cents = to_cents(row["Amount"])
        if cents <= 0:
            continue
        charges.append(
            Charge(
                reference=row["Reference"].strip().lstrip("'"),
                date=datetime.strptime(row["Date"].strip(), "%m/%d/%Y").date(),
                description=" ".join(row["Description"].split()),
                cents=cents,
                bank_category=(row.get("Category") or "").strip(),
            )
        )
    return charges


def read_expenses(lines: Iterable[str]) -> list[Expense]:
    # date_posted is "YYYY-MM-DD" or a full ISO timestamp; the day is enough
    # here, and the match window absorbs any time-zone shift.
    return [
        Expense(
            date=date.fromisoformat(row["date_posted"][:10]),
            description=row["description"],
            category=row["category"],
            cents=to_cents(row["amount"]),
            account=row["account"],
        )
        for row in csv.DictReader(lines)
        if row["date_posted"] and row["amount"]
    ]


def is_amazon(charge: Charge) -> bool:
    return bool(_AMAZON.search(charge.description))
