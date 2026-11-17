"""The categorization prompt, shared by every model backend.

Frozen (PLANS.md, "A trustworthy accuracy number"): accuracy measured on rows
imported after PROMPT_FROZEN_ON is held out, because the prompt was not tuned
on them. Any change to the wording here starts a new freeze: set today's date,
update the fingerprint in tests/test_prompt_freeze.py, and note it in README.
"""

import json
from collections.abc import Mapping
from typing import NamedTuple

from app.schemas import CategorizeRow

PROMPT_FROZEN_ON = "2026-11-17"


class Example(NamedTuple):
    """Something this user categorized before, shown next to a similar row."""

    text: str
    category: str


# Row id -> its examples. Rows without an entry are asked as before.
Examples = Mapping[str, list[Example]]

EXAMPLES_NOTE = """Some rows carry past_choices: similar things this user categorized before.
Where a past choice is the same kind of thing as the row, follow the user's habit, even
if you would have picked another category. Ignore past choices that are not really similar."""

SYSTEM = """You sort credit-card statement rows into the user's own expense categories.

Each row has the merchant text exactly as the bank printed it. It may start with a payment
prefix (AplPay, SQ *, TST*, FD *, SP, PAYPAL *), carry a store number, and have the city and
state glued onto the end. Rows may also carry the bank's own category, which is a hint, not
the answer: the user's categories are finer and named differently.

For each row, answer with exactly one of the user's categories, or null.

Answer null when the row does not say what was bought: general marketplaces and stores that
sell many unrelated kinds of things (for example eBay, AliExpress or Alipay, Shein, Walmart,
Etsy, Temu, Vinted) give no clue about the item. A wrong category costs the user more than a blank
one, so answer null whenever you would be guessing."""


def user_message(
    rows: list[CategorizeRow], categories: list[str], examples: Examples | None = None
) -> str:
    shown = {r.id: examples[r.id] for r in rows if examples and examples.get(r.id)}
    listing = [
        {
            "id": r.id,
            "text": r.text,
            "amount": f"{r.amount_cents / 100:.2f}",
            **({"bank_category": r.bank_category} if r.bank_category else {}),
            **(
                {"past_choices": [{"text": e.text, "category": e.category} for e in shown[r.id]]}
                if r.id in shown
                else {}
            ),
        }
        for r in rows
    ]
    return (
        "The user's categories:\n"
        + "\n".join(f"- {c}" for c in categories)
        + (f"\n\n{EXAMPLES_NOTE}" if shown else "")
        + "\n\nRows:\n"
        + json.dumps(listing, indent=1)
        + "\n\nAnswer for every row, by id."
    )


def answer_schema(categories: list[str]) -> dict[str, object]:
    """JSON schema for the answer. The category is limited to the user's list
    (or null), so a model that supports constrained output can't invent one."""
    return {
        "type": "object",
        "properties": {
            "answers": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "id": {"type": "string"},
                        "category": {"anyOf": [{"enum": categories}, {"type": "null"}]},
                    },
                    "required": ["id", "category"],
                    "additionalProperties": False,
                },
            }
        },
        "required": ["answers"],
        "additionalProperties": False,
    }
