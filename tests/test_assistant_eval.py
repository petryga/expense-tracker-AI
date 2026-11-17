"""The assistant eval's fake API and grader. No model, no MCP server."""

import json
import urllib.error
import urllib.request
from typing import Any

import pytest

from eval import assistant_data as d
from eval import fake_api
from eval.assistant_questions import QUESTIONS, Question, grade, numbers_in


def get(base: str, path: str) -> Any:
    with urllib.request.urlopen(f"{base}{path}") as res:
        return json.load(res)


def test_fake_api_serves_the_data_in_the_api_shapes() -> None:
    with fake_api.serve() as base:
        totals = {(r["type"], r["yearMonth"]): r for r in get(base, "/monthlyData")}
        assert totals[("expense", "2026-10")]["amountUsd"] == f"{d.spent('2026-10', 'USD'):.2f}"
        assert totals[("expense", "2026-10")]["amountCad"] == "129.99"
        assert totals[("income", "2026-10")]["amountUsd"] == "4200.00"

        report = get(base, "/reports/monthly?yearMonth=2026-10")
        groceries = next(c for c in report["dataByCategory"] if c["category"] == "Groceries")
        assert sum(item["amount"] for item in groceries["details"]) == pytest.approx(289.65)
        assert report["totalSpentCad"] == 129.99

        month = get(base, "/expenses?yearMonth=2026-09")["data"]
        assert len(month) == 8 and month[0]["datePosted"] == "2026-09-28"
        found = get(base, "/expenses?search=bean%20there")["data"]
        assert {e["description"] for e in found} == {"Bean There Cafe"}

        names = {c["name"]: c for c in get(base, "/categories")}
        assert names["Coffee Shops"]["budget"] == 30
        assert names["Coffee Shops"]["parentCategoryId"] == names["Food & Dining"]["id"]
        assert len(get(base, "/recurringExpenses")) == 3

        with pytest.raises(urllib.error.HTTPError) as missing:
            get(base, "/accounts")
        assert missing.value.code == 404
        post = urllib.request.Request(f"{base}/expenses", data=b"{}", method="POST")
        with pytest.raises(urllib.error.HTTPError) as refused:
            urllib.request.urlopen(post)
        assert refused.value.code == 405


def test_numbers_are_read_whatever_the_formatting() -> None:
    assert numbers_in("US$1,234.50 and CA$129.99, 3 visits in 2026-10") == [
        1234.5,
        129.99,
        3,
        2026,
        10,
    ]


def test_grade_needs_every_number_a_word_from_each_group_and_nothing_forbidden() -> None:
    q = Question(
        "q",
        "?",
        numbers=(425.7, 129.99),
        words=(("under", "within"),),
        forbidden_numbers=(555.69,),
        forbidden_words=("I've added",),
    )
    assert grade(q, "You spent US$425.70 and CA$129.99, within budget.").passed
    assert grade(q, "US$425.70, CA$129.99 - under, 555.69 in all").missing == ["forbidden 555.69"]
    assert grade(q, "US$425.70 only, under.").missing == ["number 129.99"]
    assert grade(q, "425.7 and 129.99, over.").missing == ["one of ['under', 'within']"]
    assert grade(q, "425.7, 129.99, under. I\u2019ve added it.").missing == [
        "forbidden 'I've added'"
    ]


def test_every_question_checks_something_and_ids_are_unique() -> None:
    assert len({q.id for q in QUESTIONS}) == len(QUESTIONS)
    for q in QUESTIONS:
        assert q.numbers or q.words, q.id


def test_expected_figures_match_the_data() -> None:
    # Hand-checked once against the rows in eval/assistant_data.py.
    assert d.spent("2026-10", "USD") == 425.7
    assert d.spent("2026-09", "USD", "Eating Out") == 32.85
    assert d.count("2026-09", "Eating Out") == 3
    assert d.recurring_per_month("USD") == 70.99
