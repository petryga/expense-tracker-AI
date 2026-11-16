"""Starting labels from your own hand-entered expenses (never from a model).

Rules are tried in order; the first that points at exactly one category wins.
Each returns where its guess came from, so you can judge it while labelling.
"""

import re
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass

from eval.merchant import merchant_key
from eval.records import CANT_TELL, Charge, Expense

MATCH_WINDOW_DAYS = 4
WIDE_WINDOW_DAYS = 15
# A tip, rounding or exchange-rate difference: up to $1, or 5% on bigger amounts.
CLOSE_CENTS = 100
CLOSE_SHARE = 0.05

# Marketplaces whose rows don't say what was bought: usually "can't tell".
_MARKETPLACE = re.compile(
    r"POSHMARK|VINTED|EBAY|ALIPAY|ALIEXPRESS|WALMART|ETSY|TEMU|SHEIN|MERCARI|DEPOP",
    re.IGNORECASE,
)
_AMAZON_TEXT = re.compile(r"AMAZON|AMZN", re.IGNORECASE)
_STOPWORDS = {"THE", "AND", "FOR", "WITH", "FROM", "TOTAL", "FEE", "FEES", "BILL", "PAYMENT"}


@dataclass(frozen=True)
class Guess:
    category: str
    source: str


NO_GUESS = Guess("", "")


def _days(a: Expense, charge: Charge) -> int:
    return abs((a.date - charge.date).days)


def _usable(expenses: list[Expense], account: str) -> list[Expense]:
    """Expenses that can describe a statement charge: those entered on the card's
    account in the app (all accounts when none is set), minus Amazon ones.
    Amazon expenses belong to the Amazon charges, which are left out of this
    set; letting them match other charges only produces wrong guesses."""
    return [
        e
        for e in expenses
        if (not account or e.account == account) and not _AMAZON_TEXT.search(e.description)
    ]


def _decide(candidates: list[Expense], charge: Charge, what: str) -> Guess | None:
    """One category among the candidates: a guess. Several: a note, no guess.
    None when there are no candidates, so the next rule gets a turn."""
    if not candidates:
        return None
    # When matches disagree, the closest in date decides, if it alone is closest
    # (a same-day copay beats a subscription of the same amount 4 days off).
    closest = min(_days(e, charge) for e in candidates)
    nearest = [e for e in candidates if _days(e, charge) == closest]
    categories = sorted({e.category for e in nearest})
    if len(categories) > 1:
        return Guess("", f"{what}: {len(nearest)} expenses disagree ({' / '.join(categories)})")
    e = nearest[0]
    return Guess(categories[0], f"{what}: expense {e.date} '{e.description}'")


def _exact(charge: Charge, expenses: list[Expense], _charges: list[Charge]) -> Guess | None:
    return _decide(
        [e for e in expenses if e.cents == charge.cents and _days(e, charge) <= MATCH_WINDOW_DAYS],
        charge,
        "same amount",
    )


def _combined(charge: Charge, expenses: list[Expense], charges: list[Charge]) -> Guess | None:
    """Several charges from one shop on one day, entered as a single expense
    (e.g. a permit fee plus its card service fee)."""
    key = merchant_key(charge.description)
    same_day = [c for c in charges if c.date == charge.date and merchant_key(c.description) == key]
    if len(same_day) < 2:
        return None
    total = sum(c.cents for c in same_day)
    return _decide(
        [e for e in expenses if e.cents == total and _days(e, charge) <= MATCH_WINDOW_DAYS],
        charge,
        f"{len(same_day)} same-day charges together (${total / 100:.2f})",
    )


def _close(charge: Charge, expenses: list[Expense], _charges: list[Charge]) -> Guess | None:
    """A nearly equal amount is often a different purchase, so this is only a
    hint to read, never a pre-filled label."""
    limit = max(CLOSE_CENTS, round(charge.cents * CLOSE_SHARE))
    near = [
        e
        for e in expenses
        if 0 < abs(e.cents - charge.cents) <= limit and _days(e, charge) <= MATCH_WINDOW_DAYS
    ]
    if not near:
        return None
    e = min(near, key=lambda x: (abs(x.cents - charge.cents), _days(x, charge)))
    amount = f"${e.cents / 100:.2f}"
    return Guess(
        "", f"hint, close amount: expense {e.date} '{e.description}' {amount} is {e.category}"
    )


def _wide(charge: Charge, expenses: list[Expense], _charges: list[Charge]) -> Guess | None:
    # Never overrides a same-amount expense closer in date, even a conflicting one.
    if any(e.cents == charge.cents and _days(e, charge) <= MATCH_WINDOW_DAYS for e in expenses):
        return None
    return _decide(
        [
            e
            for e in expenses
            if e.cents == charge.cents and MATCH_WINDOW_DAYS < _days(e, charge) <= WIDE_WINDOW_DAYS
        ],
        charge,
        f"same amount, up to {WIDE_WINDOW_DAYS} days apart",
    )


def _same_merchant(charge: Charge, expenses: list[Expense], _charges: list[Charge]) -> Guess | None:
    """An expense, any date, whose own words appear in the statement text
    ("Bean There Coffee" in "BEANTHERECOFFEECOSPRINGFIELD IL"). Needs a clear
    majority, since one shop can fit several categories."""
    text = re.sub(r"[^A-Z]", "", charge.description.upper())
    hits = []
    for e in expenses:
        words = [
            w for w in re.findall(r"[A-Za-z]{4,}", e.description.upper()) if w not in _STOPWORDS
        ]
        if words and all(w in text for w in words):
            hits.append(e)
    if not hits:
        return None
    counts = Counter(e.category for e in hits)
    category, n = counts.most_common(1)[0]
    if n / len(hits) < 2 / 3:
        return Guess(
            "", f"same merchant: {len(hits)} expenses disagree ({' / '.join(sorted(counts))})"
        )
    example = hits[0].description
    return Guess(
        category, f"same merchant: {n} of {len(hits)} expenses like '{example}' are {category}"
    )


RULES: list[Callable[[Charge, list[Expense], list[Charge]], Guess | None]] = [
    _exact,
    _combined,
    _close,
    _wide,
    _same_merchant,
]


def guess(
    charge: Charge, expenses: list[Expense], charges: list[Charge], account: str = ""
) -> Guess:
    """`account` is the name the card has in the app's Accounts (set locally
    as EVAL_CARD_ACCOUNT); empty means expenses on any account may match."""
    expenses = _usable(expenses, account)
    conflict = None
    for rule in RULES:
        result = rule(charge, expenses, charges)
        if result is None:
            continue
        if result.category:
            return result
        conflict = conflict or result
    if conflict:
        return conflict
    if _MARKETPLACE.search(charge.description):
        return Guess(CANT_TELL, "marketplace: the row doesn't say what was bought")
    return NO_GUESS
