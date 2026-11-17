import io

import pytest

from app.embeddings import cosine, nearest
from app.prompt import EXAMPLES_NOTE, Example, user_message
from app.schemas import CategorizeRow
from eval.dataset import LabelledRow
from eval.item_examples import earlier, random_examples, retrieved_examples
from eval.items import load_item_labels

ITEMS = """id,date,text,amount,label
item-1,2026-01-10,Test Garden Hose Nozzle,12.50,Garden
item-2,2026-01-12,Test Phone Cable 2m,4.99,Electronics
item-3,2026-02-01,Test Sketch Pencils,8,Hobbies
item-4,2026-03-05,Test Hose Reel,30,Garden
item-5,2026-03-06,Test Drawing Pad,9,Hobbies
"""

# One made-up axis per kind of thing, so similarity is easy to read.
VECTORS = {
    "Test Garden Hose Nozzle": [1.0, 0.0, 0.0],
    "Test Phone Cable 2m": [0.0, 1.0, 0.0],
    "Test Sketch Pencils": [0.0, 0.0, 1.0],
    "Test Hose Reel": [0.9, 0.1, 0.0],
    "Test Drawing Pad": [0.0, 0.2, 0.9],
}


def fake_embed(texts: list[str]) -> list[list[float]]:
    return [VECTORS[t] for t in texts]


def rows() -> list[LabelledRow]:
    return load_item_labels(io.StringIO(ITEMS))


def test_cosine_and_nearest() -> None:
    assert cosine([1, 0], [1, 0]) == pytest.approx(1)
    assert cosine([1, 0], [0, 1]) == 0
    assert cosine([0, 0], [1, 0]) == 0
    assert nearest([1, 0], [[0, 1], [1, 0.1], [1, 1]], 2) == [1, 2]
    assert nearest([1, 0], [], 3) == []


def test_only_earlier_months_are_offered() -> None:
    items = rows()
    assert earlier(items, items[0]) == []
    # Same month never counts, even an earlier day.
    assert earlier(items, items[1]) == []
    assert [r.reference for r in earlier(items, items[4])] == ["item-1", "item-2", "item-3"]


def test_retrieved_examples_are_the_most_similar_earlier_items() -> None:
    shown = retrieved_examples(rows(), 1, fake_embed)
    assert shown["item-1"] == []
    assert shown["item-4"] == [Example("Test Garden Hose Nozzle", "Garden")]
    assert shown["item-5"] == [Example("Test Sketch Pencils", "Hobbies")]


def test_random_examples_come_from_earlier_months_and_repeat_with_the_seed() -> None:
    items = rows()
    shown = random_examples(items, 2, seed=1)
    assert shown == random_examples(items, 2, seed=1)
    assert shown["item-1"] == []
    assert len(shown["item-3"]) == 2
    assert {e.text for e in shown["item-5"]} <= {r.description for r in items[:3]}


def test_prompt_shows_past_choices_only_where_given() -> None:
    asked = [
        CategorizeRow(id="a", text="Test Hose Reel", amount_cents=3000),
        CategorizeRow(id="b", text="Test Phone Stand", amount_cents=900),
    ]
    plain = user_message(asked, ["Garden", "Electronics"])
    assert "past_choices" not in plain and EXAMPLES_NOTE not in plain
    # An empty list, or examples for a row not in this call, change nothing.
    assert user_message(asked, ["Garden", "Electronics"], {"b": [], "z": [Example("x", "y")]}) == (
        plain
    )

    message = user_message(
        asked, ["Garden", "Electronics"], {"a": [Example("Test Garden Hose Nozzle", "Garden")]}
    )
    assert EXAMPLES_NOTE in message
    assert message.count('"past_choices"') == 1
    assert '"text": "Test Garden Hose Nozzle"' in message
