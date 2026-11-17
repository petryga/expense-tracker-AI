"""Guards the prompt freeze (PLANS.md, "A trustworthy accuracy number").

Accuracy on rows imported after the freeze date counts as held out only if
the prompt really stayed the same. This test fails on any change to the
system prompt, the examples note, how rows are laid out, or the answer schema.
If the change is intended: set PROMPT_FROZEN_ON in app/prompt.py to today,
put the new fingerprint below, and add the date to README ("Prompt freeze").
"""

import hashlib
import json

from app.prompt import (
    EXAMPLES_NOTE,
    PROMPT_FROZEN_ON,
    SYSTEM,
    Example,
    answer_schema,
    user_message,
)
from app.schemas import CategorizeRow

FINGERPRINT = "66c9edd96ba69777"
FROZEN_ON = "2026-11-17"


def fingerprint() -> str:
    rows = [
        CategorizeRow(
            id="a", text="GREENLEAF MARKET", amount_cents=1250, bank_category="Groceries"
        ),
        CategorizeRow(id="b", text="Test Garden Hose", amount_cents=999, kind="item"),
    ]
    categories = ["Garden", "Groceries"]
    text = (
        SYSTEM
        + EXAMPLES_NOTE
        + user_message(rows, categories, {"b": [Example("Test Hose Reel", "Garden")]})
        + json.dumps(answer_schema(categories), sort_keys=True)
    )
    return hashlib.sha256(text.encode()).hexdigest()[:16]


def test_the_prompt_has_not_changed_since_the_freeze() -> None:
    assert fingerprint() == FINGERPRINT, (
        "The categorization prompt changed. If intended, start a new freeze: set "
        "PROMPT_FROZEN_ON to today, update FINGERPRINT and FROZEN_ON here, and note it in "
        "README. Accuracy from before the new date no longer describes this prompt."
    )
    assert PROMPT_FROZEN_ON == FROZEN_ON
