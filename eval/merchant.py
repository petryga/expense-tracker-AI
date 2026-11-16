"""Merchant normalization shared by label guessing, merchant memory and the eval.

When merchant memory moves into BE/ (PLANS.md, decision 3), it must use this
same rule, or the eval's baseline won't describe what the app does.
"""

import re

# Processor and wallet prefixes the bank glues onto the merchant.
_PREFIX = re.compile(r"^(?:APLPAY|FD|SQ|TST|SP|PAYPAL|BT|DD|IC)\b\s*\*?\s*", re.IGNORECASE)


def merchant_key(description: str) -> str:
    """First two meaningful words, prefixes and store numbers stripped:
    "AplPay FD *STATE PERMITS 7SPRINGFIELD IL" -> "STATE PERMITS"."""
    text = description.upper()
    while (stripped := _PREFIX.sub("", text)) != text:
        text = stripped
    words = re.findall(r"[A-Z]{2,}", text)
    return " ".join(words[:2])
