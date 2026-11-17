"""Invented data for the spending assistant eval: three months of expenses,
categories, budgets and recurring entries. Not derived from any real data.

The eval's correct answers are computed from these rows, so they can't drift
from what the fake API serves.
"""

from collections import defaultdict
from dataclasses import dataclass

# "Today" for every eval question: early November, so "last month" is October.
TODAY = "2026-11-05"

CATEGORIES = [
    # (name, group, monthly budget or None)
    ("Groceries", "Food & Dining", 400),
    ("Coffee Shops", "Food & Dining", 30),
    ("Eating Out", "Food & Dining", 150),
    ("Home", "Household", None),
    ("Hobbies", "Fun", 60),
    ("Transport", "Getting Around", None),
    ("Phone Bills", "Bills", None),
    ("Internet", "Bills", None),
]


@dataclass(frozen=True)
class Expense:
    date: str
    description: str
    amount: float
    currency: str
    category: str
    account: str = "Card"


EXPENSES = [
    # August 2026
    Expense("2026-08-02", "Greenleaf Market", 82.40, "USD", "Groceries"),
    Expense("2026-08-06", "Bean There Cafe", 4.75, "USD", "Coffee Shops"),
    Expense("2026-08-09", "Noodle Corner", 23.10, "USD", "Eating Out"),
    Expense("2026-08-14", "Greenleaf Market", 64.15, "USD", "Groceries"),
    Expense("2026-08-18", "Maple Hardware", 46.00, "CAD", "Home"),
    Expense("2026-08-21", "Bean There Cafe", 5.25, "USD", "Coffee Shops"),
    Expense("2026-08-27", "Paintbox Supplies", 112.30, "USD", "Hobbies"),
    Expense("2026-08-30", "City Transit Pass", 98.00, "USD", "Transport"),
    # September 2026
    Expense("2026-09-03", "Greenleaf Market", 91.20, "USD", "Groceries"),
    Expense("2026-09-05", "Noodle Corner", 18.60, "USD", "Eating Out"),
    Expense("2026-09-09", "Bean There Cafe", 4.75, "USD", "Coffee Shops"),
    Expense("2026-09-12", "Taco Window", 14.25, "USD", "Eating Out"),
    Expense("2026-09-17", "Greenleaf Market", 77.85, "USD", "Groceries"),
    Expense("2026-09-20", "Lakeside Bistro", 41.00, "CAD", "Eating Out"),
    Expense("2026-09-24", "Bean There Cafe", 6.10, "USD", "Coffee Shops"),
    Expense("2026-09-28", "City Transit Pass", 98.00, "USD", "Transport"),
    # October 2026
    Expense("2026-10-01", "Greenleaf Market", 104.60, "USD", "Groceries"),
    Expense("2026-10-04", "Bean There Cafe", 5.50, "USD", "Coffee Shops"),
    Expense("2026-10-07", "Bean There Cafe", 4.90, "USD", "Coffee Shops"),
    Expense("2026-10-11", "Maple Hardware", 129.99, "CAD", "Home"),
    Expense("2026-10-15", "Greenleaf Market", 96.30, "USD", "Groceries"),
    Expense("2026-10-19", "Bean There Cafe", 6.25, "USD", "Coffee Shops"),
    Expense("2026-10-22", "Noodle Corner", 21.40, "USD", "Eating Out"),
    Expense("2026-10-26", "Greenleaf Market", 88.75, "USD", "Groceries"),
    Expense("2026-10-29", "City Transit Pass", 98.00, "USD", "Transport"),
]

RECURRING_EXPENSES = [
    # (description, category, amount, currency, day of month)
    ("Phone plan", "Phone Bills", 45.00, "CAD", 5),
    ("Home internet", "Internet", 60.00, "USD", 12),
    ("Music app", "Hobbies", 10.99, "USD", 20),
]

RECURRING_INCOME = [
    # (description, category, amount, currency)
    ("Salary", "bankAccounts", 4200.00, "USD"),
]


def r2(value: float) -> float:
    return round(value + 1e-9, 2)


def month_of(expense: Expense) -> str:
    return expense.date[:7]


def spent(month: str, currency: str, category: str | None = None) -> float:
    return r2(
        sum(
            e.amount
            for e in EXPENSES
            if month_of(e) == month
            and e.currency == currency
            and (category is None or e.category == category)
        )
    )


def by_category(month: str) -> dict[str, dict[str, float]]:
    totals: dict[str, dict[str, float]] = defaultdict(lambda: {"CAD": 0.0, "USD": 0.0})
    for e in EXPENSES:
        if month_of(e) == month:
            totals[e.category][e.currency] = r2(totals[e.category][e.currency] + e.amount)
    return dict(totals)


def count(month: str, category: str) -> int:
    return sum(1 for e in EXPENSES if month_of(e) == month and e.category == category)


def recurring_per_month(currency: str) -> float:
    return r2(sum(r[2] for r in RECURRING_EXPENSES if r[3] == currency))
