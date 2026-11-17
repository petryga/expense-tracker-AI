import io

from eval.dataset import LabelledRow
from eval.items import by_month, load_item_labels, most_common_label

ITEMS = """id,date,text,amount,label
item-1,2026-03-04,Test Garden Hose Nozzle,12.50,Garden
item-2,2026-03-04,Test Phone Cable 2m,4.99,Electronics
item-3,2026-04-01,Test Hose Reel,30,Garden
"""


def test_loads_items_as_labelled_rows() -> None:
    rows = load_item_labels(io.StringIO(ITEMS))
    assert [(r.reference, r.month, r.cents, r.label) for r in rows] == [
        ("item-1", "2026-03", 1250, "Garden"),
        ("item-2", "2026-03", 499, "Electronics"),
        ("item-3", "2026-04", 3000, "Garden"),
    ]
    assert rows[0].description == "Test Garden Hose Nozzle"
    assert rows[0].bank_category == ""


def test_most_common_label_baseline() -> None:
    rows = load_item_labels(io.StringIO(ITEMS))
    assert most_common_label(rows) == ["Garden", "Garden", "Garden"]
    assert most_common_label([]) == []


def test_by_month_asks_one_month_per_call_and_keeps_the_order() -> None:
    rows = load_item_labels(io.StringIO(ITEMS))
    calls: list[list[str]] = []

    def predict(_history: list[LabelledRow], asked: list[LabelledRow]) -> list[str | None]:
        calls.append([r.reference for r in asked])
        return [r.reference.upper() for r in asked]

    assert by_month(rows[::-1], predict) == ["ITEM-3", "ITEM-2", "ITEM-1"]
    # Never two months in one call: that would put an item's label in the
    # same prompt as the item (as another item's past choice).
    assert calls == [["item-2", "item-1"], ["item-3"]]
