"""The categorization prompt, shared by every model backend."""

import json

from app.schemas import CategorizeRow

SYSTEM = """You sort credit-card statement rows into the user's own expense categories.

Each row has the merchant text exactly as the bank printed it. It may start with a payment
prefix (AplPay, SQ *, TST*, FD *, SP, PAYPAL *), carry a store number, and have the city and
state glued onto the end. Rows may also carry the bank's own category, which is a hint, not
the answer: the user's categories are finer and named differently.

For each row, answer with exactly one of the user's categories, or null.

Answer null when the row does not say what was bought: general marketplaces and stores that
sell many unrelated kinds of things (for example eBay, AliExpress or Alipay, Shein, Walmart,
Etsy, Temu) give no clue about the item. A wrong category costs the user more than a blank
one, so answer null whenever you would be guessing."""


def user_message(rows: list[CategorizeRow], categories: list[str]) -> str:
    listing = [
        {
            "id": r.id,
            "text": r.text,
            "amount": f"{r.amount_cents / 100:.2f}",
            **({"bank_category": r.bank_category} if r.bank_category else {}),
        }
        for r in rows
    ]
    return (
        "The user's categories:\n"
        + "\n".join(f"- {c}" for c in categories)
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
