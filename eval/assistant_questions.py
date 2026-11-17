"""Questions for the spending assistant eval, with what a right answer must
contain. Expected figures are computed from eval/assistant_data.py.

Grading is deliberately simple and strict: every listed number must appear in
the answer (formatting aside), at least one word from each word group must
appear, and no forbidden number may appear (for example, CAD and USD added
together).
"""

import re
from dataclasses import dataclass, field

from eval import assistant_data as d
from eval.assistant_data import r2


@dataclass(frozen=True)
class Question:
    id: str
    text: str
    numbers: tuple[float, ...] = ()
    # Each group: at least one of these words (case-insensitive) must appear.
    words: tuple[tuple[str, ...], ...] = ()
    forbidden_numbers: tuple[float, ...] = ()
    forbidden_words: tuple[str, ...] = ()
    note: str = ""


@dataclass
class Grade:
    passed: bool
    missing: list[str] = field(default_factory=list)


CANT = ("can't answer", "cannot answer", "can not answer")


def _october_top() -> str:
    usd = {c: t["USD"] for c, t in d.by_category("2026-10").items()}
    return max(usd, key=lambda c: usd[c])


QUESTIONS = [
    Question(
        "total_last_month",
        "How much did I spend last month?",
        numbers=(d.spent("2026-10", "USD"), d.spent("2026-10", "CAD")),
        forbidden_numbers=(r2(d.spent("2026-10", "USD") + d.spent("2026-10", "CAD")),),
        note="relative date; both currencies, never added",
    ),
    Question(
        "top_category_october",
        "What was my biggest spending category in October 2026?",
        words=((_october_top(),),),
        numbers=(d.by_category("2026-10")[_october_top()]["USD"],),
    ),
    Question(
        "coffee_sep_oct",
        "How did my coffee shop spending change from September to October 2026?",
        numbers=(
            d.spent("2026-09", "USD", "Coffee Shops"),
            d.spent("2026-10", "USD", "Coffee Shops"),
        ),
    ),
    Question(
        "groceries_three_months",
        "Show my grocery spending for August, September and October 2026.",
        numbers=tuple(d.spent(m, "USD", "Groceries") for m in ("2026-08", "2026-09", "2026-10")),
    ),
    Question(
        "eating_out_count_september",
        "How many times did I eat out in September 2026, and how much was it?",
        numbers=(
            float(d.count("2026-09", "Eating Out")),
            d.spent("2026-09", "USD", "Eating Out"),
            d.spent("2026-09", "CAD", "Eating Out"),
        ),
    ),
    Question(
        "recurring_total",
        "What are my recurring bills and what do they add up to each month?",
        numbers=(d.recurring_per_month("USD"), d.recurring_per_month("CAD")),
        words=(("Phone",), ("internet",)),
    ),
    Question(
        "biggest_purchase_august",
        "What was my single most expensive purchase in August 2026?",
        words=(("Paintbox",),),
        numbers=(112.30,),
    ),
    Question(
        "budget_coffee_october",
        "Was I over my Coffee Shops budget in October 2026?",
        numbers=(d.spent("2026-10", "USD", "Coffee Shops"), 30.0),
        words=(
            (
                "under",
                "within",
                "below",
                "not over",
                "weren't over",
                "wasn't over",
                "didn't go over",
                "did not go over",
            ),
        ),
    ),
    Question(
        "home_october_cad",
        "How much did I spend on Home in October 2026?",
        numbers=(d.spent("2026-10", "CAD", "Home"),),
        words=(("CAD", "CA$", "Canadian"),),
    ),
    Question(
        "off_topic",
        "What's the weather going to be tomorrow?",
        words=(CANT,),
        note="must refuse with the fixed phrase",
    ),
    Question(
        "write_request",
        "Add a $5 coffee from today to my expenses.",
        words=(("app",),),
        forbidden_words=("I've added", "I have added", "has been added", "was added"),
        note="read-only: must point to the app, never claim to have added it",
    ),
    Question(
        "no_data_month",
        "How much did I spend in March 2026?",
        words=(("no ", "nothing", "0.00", "none", "don't have", "do not have", "isn't any"),),
        forbidden_numbers=(d.spent("2026-10", "USD"), d.spent("2026-09", "USD")),
        note="no data that month: say so, don't borrow another month's figures",
    ),
]

_NUMBER = re.compile(r"(?<![\d.])\d{1,3}(?:,\d{3})+(?:\.\d+)?|(?<![\d.])\d+(?:\.\d+)?")


def numbers_in(text: str) -> list[float]:
    return [float(m.replace(",", "")) for m in _NUMBER.findall(text)]


def _has_number(found: list[float], wanted: float) -> bool:
    return any(abs(n - wanted) < 0.005 for n in found)


def grade(question: Question, answer: str) -> Grade:
    found = numbers_in(answer)
    lower = answer.lower().replace("\u2019", "'")  # curly apostrophe
    missing = [f"number {n:g}" for n in question.numbers if not _has_number(found, n)]
    missing += [
        f"one of {list(group)}"
        for group in question.words
        if not any(w.lower() in lower for w in group)
    ]
    missing += [f"forbidden {n:g}" for n in question.forbidden_numbers if _has_number(found, n)]
    missing += [f"forbidden '{w}'" for w in question.forbidden_words if w.lower() in lower]
    return Grade(passed=not missing, missing=missing)
