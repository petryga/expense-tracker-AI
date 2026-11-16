"""Split, baselines and scoring, on made-up rows."""

from eval.baselines import bank_category_mapping, memory_then_bank, merchant_memory
from eval.dataset import LabelledRow, load_labels, monthly_splits
from eval.metrics import score


def row(
    month: str, text: str, label: str | None, bank: str = "Other", ref: str = ""
) -> LabelledRow:
    return LabelledRow(ref or f"{month}-{text}", month, text, 100, bank, label)


def test_load_labels_keeps_checked_rows_and_turns_cant_tell_into_none() -> None:
    lines = [
        "reference,date,description,amount,bank_category,guess,guess_from,label,checked,note\n",
        "A,2026-01-02,GREENLEAF MARKET,12.30,Groceries,,,Groceries,y,\n",
        "B,2026-01-03,EBAY US,5.00,Online,,,can't tell,Y,\n",
        "C,2026-01-04,NOT LOOKED AT,1.00,Online,,,Hobbies,,\n",
    ]
    rows = load_labels(lines)
    assert [(r.reference, r.month, r.cents, r.label) for r in rows] == [
        ("A", "2026-01", 1230, "Groceries"),
        ("B", "2026-01", 500, None),
    ]


def test_each_test_month_sees_only_earlier_months() -> None:
    rows = [row("2025-06", "A", "x"), row("2025-08", "B", "y"), row("2025-09", "C", "z")]
    splits = list(monthly_splits(rows, "2025-08"))
    assert [s.month for s in splits] == ["2025-08", "2025-09"]
    for s in splits:
        assert all(h.month < s.month for h in s.history)
        assert all(t.month == s.month for t in s.test)
    assert [h.description for h in splits[1].history] == ["A", "B"]


def test_merchant_memory_reuses_the_most_common_label_for_the_merchant() -> None:
    history = [
        row("2025-01", "AplPay GREENLEAF MARKET 12", "Groceries"),
        row("2025-02", "GREENLEAF MARKET 40", "Groceries"),
        row("2025-03", "GREENLEAF MARKET 40", "Household Goods"),
        row("2025-03", "EBAY US", None),
    ]
    test = [
        row("2025-04", "GREENLEAF MARKET 7", "Groceries"),
        row("2025-04", "EBAY US", None),
        row("2025-04", "NEW SHOP", "Gifts"),
    ]
    assert merchant_memory(history, test) == ["Groceries", None, None]


def test_ties_go_to_the_most_recent_label() -> None:
    history = [
        row("2025-01", "BEAN THERE", "Coffee Shops"),
        row("2025-02", "BEAN THERE", "Eating Out"),
    ]
    assert merchant_memory(history, [row("2025-03", "BEAN THERE", None)]) == ["Eating Out"]


def test_bank_category_mapping_and_the_combination() -> None:
    history = [
        row("2025-01", "PLACE ONE", "Eating Out", bank="Restaurant-Restaurant"),
        row("2025-01", "EBAY US", None, bank="Merchandise-Internet"),
    ]
    test = [
        row("2025-02", "PLACE TWO", "Eating Out", bank="Restaurant-Restaurant"),
        row("2025-02", "EBAY US", None, bank="Restaurant-Restaurant"),
        row("2025-02", "UNKNOWN", "Gifts", bank="Never Seen"),
    ]
    assert bank_category_mapping(history, test) == ["Eating Out", "Eating Out", None]
    # A known merchant's "can't tell" wins over the bank-category mapping.
    assert memory_then_bank(history, test) == ["Eating Out", None, None]


def test_score_counts_right_wrong_no_suggestion_and_can_t_tell() -> None:
    s = score(
        ["a", "b", "c", "d", "e"],
        ["Groceries", "Groceries", "Groceries", None, None],
        ["Groceries", "Eating Out", None, None, "Gifts"],
    )
    assert (s.category_rows, s.right, s.wrong, s.no_suggestion) == (3, 1, 1, 1)
    assert (s.cant_tell_rows, s.held_back, s.guessed) == (2, 1, 1)
    assert (round(s.accuracy, 3), s.precision, s.held_back_rate) == (0.333, 0.5, 0.5)
    assert [m[0] for m in s.misses] == ["b", "c", "e"]


def test_never_suggested_labels_are_left_out_of_history_and_scoring() -> None:
    rows = [
        row("2025-07", "CORNER PHARMACY", "Pharmacy"),
        row("2025-07", "CORNER PHARMACY", "Gifts", ref="gift-old"),
        row("2025-08", "CORNER PHARMACY", "Gifts", ref="gift-new"),
        row("2025-08", "CORNER PHARMACY", "Pharmacy", ref="test"),
    ]
    (split,) = monthly_splits(rows, "2025-08", frozenset({"Gifts"}))
    assert [r.label for r in split.history] == ["Pharmacy"]
    assert [r.reference for r in split.test] == ["test"]
    assert split.excluded == 1
    # Memory learns the shop's usual category, not the one-off gift.
    assert merchant_memory(split.history, split.test) == ["Pharmacy"]
