"""Each guessing rule, on made-up rows."""

from datetime import date

from eval.guessing import guess
from eval.merchant import merchant_key
from eval.records import CANT_TELL, Charge, Expense


def charge(
    cents: int = 8642, day: int = 2, text: str = "GREENLEAF MARKET", ref: str = "R"
) -> Charge:
    return Charge(ref, date(2026, 10, day), text, cents, "")


def expense(
    cents: int = 8642,
    day: int = 3,
    category: str = "Groceries",
    account: str = "Card",
    text: str = "groceries",
    month: int = 10,
) -> Expense:
    return Expense(date(2026, month, day), text, category, cents, account)


def test_same_amount_within_a_few_days() -> None:
    g = guess(charge(), [expense()], [])
    assert g.category == "Groceries"
    assert g.source.startswith("same amount: expense 2026-10-03")


def test_only_expenses_on_the_card_account_count_when_one_is_set() -> None:
    assert guess(charge(), [expense(account="Cash")], [], account="Card").category == ""
    assert guess(charge(), [expense(account="Cash")], []).category == "Groceries"


def test_same_day_charges_entered_as_one_expense() -> None:
    fee = charge(cents=4500, text="FD *STATE PERMITS 12 0000 SPRINGFIELD", ref="a")
    service = charge(cents=95, text="FD *STATE PERMITS 12 *SVC SPRINGFIELD", ref="b")
    other = charge(cents=95, text="BEAN THERE CAFE", ref="c")
    expenses = [expense(cents=4595, category="Government Fees", text="Permit")]
    for c in (fee, service):
        g = guess(c, expenses, [fee, service, other])
        assert g.category == "Government Fees"
        assert g.source.startswith("2 same-day charges together ($45.95)")
    assert guess(other, expenses, [fee, service, other]).category == ""


def test_close_amount_is_only_a_hint() -> None:
    g = guess(charge(cents=2000), [expense(cents=2080, text="corner cafe")], [])
    assert g.category == ""
    assert g.source == "hint, close amount: expense 2026-10-03 'corner cafe' $20.80 is Groceries"
    assert guess(charge(cents=2000), [expense(cents=2150)], []).source == ""  # $1.50 off on $20


def test_amazon_expenses_never_match_other_charges() -> None:
    assert guess(charge(), [expense(text="Amazon Desk Lamp")], []).category == ""


def test_same_amount_further_apart() -> None:
    g = guess(charge(day=2), [expense(day=14)], [])
    assert (g.category, g.source[:11]) == ("Groceries", "same amount")
    assert guess(charge(day=1), [expense(day=20)], []).category == ""  # 19 days


def test_same_merchant_by_the_expense_s_own_words() -> None:
    text = "BEANTHERECOFFEECOSPRINGFIELD IL"
    seen = [
        expense(cents=2000, month=m, text="Bean There Coffee", category="Groceries")
        for m in (1, 2, 3)
    ]
    g = guess(charge(cents=3900, text=text), seen, [])
    assert g.category == "Groceries"
    assert g.source == "same merchant: 3 of 3 expenses like 'Bean There Coffee' are Groceries"


def test_same_merchant_needs_a_clear_majority() -> None:
    seen = [
        expense(cents=1, month=1, text="Corner Store", category="Groceries"),
        expense(cents=2, month=2, text="Corner Store", category="Household Goods"),
    ]
    g = guess(charge(cents=999, text="CORNER STORE 12"), seen, [])
    assert g.category == ""
    assert g.source.startswith("same merchant: 2 expenses disagree")


def test_the_closest_date_settles_a_disagreement() -> None:
    copay = expense(cents=2000, day=22, category="Medical Expenses", text="Clinic copay")
    other = expense(cents=2000, day=18, category="Subscriptions", text="Streaming")
    far = expense(cents=2000, day=11, category="Groceries", text="Coffee")
    g = guess(charge(cents=2000, day=22), [copay, other, far], [])
    assert (g.category, g.source) == (
        "Medical Expenses",
        "same amount: expense 2026-10-22 'Clinic copay'",
    )


def test_a_far_match_never_overrides_a_close_conflict() -> None:
    a = expense(cents=2000, day=20, category="Subscriptions")
    b = expense(cents=2000, day=24, category="Eating Out")
    far = expense(cents=2000, day=8, category="Groceries")
    assert guess(charge(cents=2000, day=22), [a, b, far], []).category == ""


def test_disagreeing_matches_give_a_note_not_a_guess() -> None:
    g = guess(charge(), [expense(category="Groceries"), expense(category="Eating Out")], [])
    assert g.category == ""
    assert g.source == "same amount: 2 expenses disagree (Eating Out / Groceries)"


def test_a_later_rule_can_settle_what_an_earlier_one_could_not() -> None:
    expenses = [
        expense(category="Groceries"),
        expense(category="Eating Out"),
        expense(cents=1, month=1, text="Greenleaf Market", category="Groceries"),
    ]
    assert guess(charge(), expenses, []).category == "Groceries"


def test_marketplaces_start_as_cant_tell_and_nothing_else_is_guessed() -> None:
    assert guess(charge(text="POSHMARK ORDER"), [], []).category == CANT_TELL
    assert guess(charge(text="UNKNOWN SHOP"), [], []).category == ""


def test_merchant_key_drops_wallet_and_processor_prefixes() -> None:
    assert merchant_key("AplPay FD *STATE PERMITS 7SPRINGFIELD IL") == "STATE PERMITS"
    assert merchant_key("SQ *BEAN THERE CAFE") == "BEAN THERE"
