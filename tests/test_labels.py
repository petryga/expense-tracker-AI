"""Label building and checking, on made-up rows only."""

from datetime import date

from eval.labels import build_rows, check, inconsistencies
from eval.records import CANT_TELL, read_expenses, read_statement, to_cents

STATEMENT = """Date,Description,Amount,Reference,Category
10/02/2026,GREENLEAF MARKET SPRINGFIELD,86.42,'DEMO1,Merchandise & Supplies-Groceries
10/04/2026,AMAZON.COM*DEMO,34.99,'DEMO2,
10/05/2026,POSHMARK ORDER 9,25.00,'DEMO3,
10/06/2026,AUTOPAY PAYMENT - THANK YOU,-500.00,'DEMO4,
10/07/2026,"BEAN THERE CAFE","1,006.75",'DEMO5,
""".splitlines(keepends=True)


def test_reads_only_charges_with_cents_and_references() -> None:
    charges = read_statement(STATEMENT)
    assert [(c.reference, c.cents) for c in charges] == [
        ("DEMO1", 8642),
        ("DEMO2", 3499),
        ("DEMO3", 2500),
        ("DEMO5", 100675),
    ]
    assert to_cents("-1,350.5") == -135050


def test_expense_dates_in_both_stored_formats() -> None:
    lines = [
        "date_posted,description,category,amount,account,currency\n",
        "2026-10-03,a,Groceries,86.42,Card,USD\n",
        "2026-10-03T05:00:00.000Z,b,Groceries,1.5,Card,USD\n",
    ]
    assert [e.date for e in read_expenses(lines)] == [date(2026, 10, 3)] * 2


def test_build_rows_leaves_out_amazon_and_keeps_earlier_work() -> None:
    charges = read_statement(STATEMENT)
    existing = {
        "DEMO1": {"label": "Eating Out", "checked": "y", "note": "lunch"},
        # Empty from an earlier run: takes the new guess.
        "DEMO3": {"label": "", "checked": "", "note": ""},
    }
    rows = build_rows(charges, [], existing)
    assert [r["reference"] for r in rows] == ["DEMO1", "DEMO3", "DEMO5"]
    assert (rows[0]["label"], rows[0]["checked"], rows[0]["note"]) == (
        "Eating Out",
        "y",
        "lunch",
    )
    assert rows[1]["label"] == CANT_TELL and rows[1]["checked"] == ""


def test_check_reports_progress_and_bad_labels() -> None:
    rows = [
        {"date": "2026-09-01", "description": "A", "label": "Groceries", "checked": "y"},
        {"date": "2026-09-02", "description": "B", "label": CANT_TELL, "checked": "Y"},
        {"date": "2026-10-01", "description": "C", "label": "Yachts", "checked": ""},
        {"date": "2026-10-02", "description": "D", "label": "", "checked": "x"},
    ]
    report = check(rows, {"Groceries"})
    assert (report.total, report.checked, report.cant_tell) == (4, 3, 1)
    assert report.per_month == {"2026-09": (2, 2), "2026-10": (1, 2)}
    assert report.errors == [
        "2026-10-01 C: 'Yachts' is not one of your categories",
        "2026-10-02 D: checked but has no label",
    ]


def test_inconsistencies_lists_merchants_with_more_than_one_label() -> None:
    def row(description: str, label: str) -> dict[str, str]:
        return {"date": "2026-10-01", "description": description, "label": label, "amount": "1"}

    rows = [
        row("AplPay BEAN THERE CAFE OAKLAND", "Coffee Shops"),
        row("BEAN THERE CAFE SF", "Eating Out"),
        row("GREENLEAF MARKET 12", "Groceries"),
        row("GREENLEAF MARKET 40", "Groceries"),
        row("ONE OFF SHOP", ""),
    ]
    found = inconsistencies(rows)
    assert list(found) == ["BEAN THERE"]
    assert [r["label"] for r in found["BEAN THERE"]] == ["Coffee Shops", "Eating Out"]
