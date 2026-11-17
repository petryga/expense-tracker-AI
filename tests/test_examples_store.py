"""Against a real Postgres with pgvector. Set AI_TEST_DATABASE_URL to a
throwaway database to run these (CI does); they are skipped otherwise.
Each test gets its own schema, dropped afterwards."""

import os
from collections.abc import Iterator
from pathlib import Path
from urllib.parse import quote

import psycopg
import pytest

from app.config import Settings
from app.examples_store import StoredExample, nearest, sync
from app.prompt import Example
from app.retrieval import examples_for
from app.schemas import CategorizeRow

ADMIN_URL = os.environ.get("AI_TEST_DATABASE_URL", "")
pytestmark = pytest.mark.skipif(not ADMIN_URL, reason="AI_TEST_DATABASE_URL is not set")

SCHEMA = "ai_store_test"
ANA = "11111111-1111-4111-8111-111111111111"
BEN = "22222222-2222-4222-8222-222222222222"
CATEGORIES = ["Garden", "Electronics", "Hobbies"]

# One made-up axis per kind of thing; the rest of the 384 are zero.
AXES = {"hose": 0, "cable": 1, "pencil": 2}


def fake_embed(texts: list[str]) -> list[list[float]]:
    vectors = []
    for text in texts:
        vector = [0.0] * 384
        for word, axis in AXES.items():
            if word in text.lower():
                vector[axis] = 1.0
        vectors.append(vector)
    return vectors


@pytest.fixture
def url() -> Iterator[str]:
    with psycopg.connect(ADMIN_URL, autocommit=True) as conn:
        conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
        conn.execute(f"DROP SCHEMA IF EXISTS {SCHEMA} CASCADE")
        conn.execute(f"CREATE SCHEMA {SCHEMA}")
        conn.execute(f"SET search_path TO {SCHEMA}, public")
        conn.execute((Path(__file__).parent / "schema.sql").read_text())
    separator = "&" if "?" in ADMIN_URL else "?"
    yield f"{ADMIN_URL}{separator}options={quote(f'-csearch_path={SCHEMA},public')}"
    with psycopg.connect(ADMIN_URL, autocommit=True) as conn:
        conn.execute(f"DROP SCHEMA IF EXISTS {SCHEMA} CASCADE")


def stored(url: str) -> list[tuple[str | None, str, str, str]]:
    with psycopg.connect(url) as conn:
        return [
            (str(user) if user else None, source, text, category)
            for user, source, text, category in conn.execute(
                "SELECT user_id, source, text, category FROM category_examples ORDER BY source"
            )
        ]


def test_sync_makes_the_stored_set_match_and_embeds_only_what_changed(url: str) -> None:
    embedded: list[list[str]] = []

    def embed(texts: list[str]) -> list[list[float]]:
        embedded.append(texts)
        return fake_embed(texts)

    first = [
        StoredExample("a", "Test Garden Hose", "Garden"),
        StoredExample("b", "Test Phone Cable", "Electronics"),
        StoredExample("c", "Test Sketch Pencil", "Hobbies"),
    ]
    result = sync(url, ANA, "item", first, embed)
    assert (result.stored, result.embedded, result.removed) == (3, 3, 0)

    # Same again: nothing to embed, nothing changes.
    again = sync(url, ANA, "item", first, embed)
    assert (again.embedded, again.removed) == (0, 0)

    # "a" gets a new category, "b" new wording, "c" is gone, "d" is new.
    second = [
        StoredExample("a", "Test Garden Hose", "Hobbies"),
        StoredExample("b", "Test Phone Cable 2m", "Electronics"),
        StoredExample("d", "Test Colour Pencil", "Hobbies"),
    ]
    result = sync(url, ANA, "item", second, embed)
    assert (result.stored, result.embedded, result.removed) == (3, 2, 1)
    assert embedded == [
        ["Test Garden Hose", "Test Phone Cable", "Test Sketch Pencil"],
        ["Test Phone Cable 2m", "Test Colour Pencil"],
    ]
    assert stored(url) == [
        (ANA, "a", "Test Garden Hose", "Hobbies"),
        (ANA, "b", "Test Phone Cable 2m", "Electronics"),
        (ANA, "d", "Test Colour Pencil", "Hobbies"),
    ]


def test_sync_touches_only_its_own_user_and_kind(url: str) -> None:
    sync(url, ANA, "item", [StoredExample("a", "Test Garden Hose", "Garden")], fake_embed)
    sync(url, BEN, "item", [StoredExample("a", "Test Phone Cable", "Electronics")], fake_embed)
    sync(url, None, "item", [StoredExample("a", "Test Sketch Pencil", "Hobbies")], fake_embed)
    sync(url, None, "seed", [StoredExample("a", "Test Hose Reel", "Garden")], fake_embed)

    # The local user (no id) empties their items: everyone else's stay.
    sync(url, None, "item", [], fake_embed)
    assert stored(url) == [
        (ANA, "a", "Test Garden Hose", "Garden"),
        (BEN, "a", "Test Phone Cable", "Electronics"),
        (None, "a", "Test Hose Reel", "Garden"),
    ]


def test_nearest_never_returns_another_users_rows(url: str) -> None:
    sync(url, ANA, "item", [StoredExample("a", "Test Phone Cable", "Electronics")], fake_embed)
    sync(url, BEN, "item", [StoredExample("a", "Test Garden Hose", "Garden")], fake_embed)
    sync(url, None, "item", [StoredExample("a", "Test Hose Reel", "Garden")], fake_embed)
    query = fake_embed(["Test Hose Nozzle"])

    # Ana has nothing about hoses; she still only ever gets her own row.
    assert nearest(url, ANA, query, CATEGORIES, 3) == [[Example("Test Phone Cable", "Electronics")]]
    assert nearest(url, BEN, query, CATEGORIES, 3) == [[Example("Test Garden Hose", "Garden")]]
    assert nearest(url, None, query, CATEGORIES, 3) == [[Example("Test Hose Reel", "Garden")]]


def test_nearest_orders_by_similarity_skips_dropped_categories_and_repeats(url: str) -> None:
    sync(
        url,
        ANA,
        "item",
        [
            StoredExample("a", "Test Garden Hose", "Garden"),
            StoredExample("b", "Test Garden Hose", "Garden"),  # bought twice
            StoredExample("c", "Test Hose and Cable Kit", "Electronics"),
            StoredExample("d", "Test Sketch Pencil", "Hobbies"),
            StoredExample("e", "Test Hose Hanger", "Shed"),  # a category since deleted
        ],
        fake_embed,
    )
    found = nearest(url, ANA, fake_embed(["Test Hose Nozzle"]), CATEGORIES, 2)
    assert found == [
        [Example("Test Garden Hose", "Garden"), Example("Test Hose and Cable Kit", "Electronics")]
    ]


def test_examples_for_asks_only_for_items_and_survives_a_broken_store(url: str) -> None:
    sync(url, ANA, "item", [StoredExample("a", "Test Garden Hose", "Garden")], fake_embed)
    rows = [
        CategorizeRow(id="r1", text="GREENLEAF HOSE SUPPLY", amount_cents=100),
        CategorizeRow(id="i1", text="Test Hose Nozzle", amount_cents=200, kind="item"),
    ]
    settings = Settings(ai_database_url=url)
    assert examples_for(rows, CATEGORIES, ANA, settings, fake_embed) == {
        "i1": [Example("Test Garden Hose", "Garden")]
    }
    # Statement rows alone: the store is never asked.
    assert examples_for(rows[:1], CATEGORIES, ANA, settings, fake_embed) is None
    # Retrieval off, no database, an unreachable one, a failing model: no examples.
    assert examples_for(rows, CATEGORIES, ANA, Settings(), fake_embed) is None
    off = Settings(ai_database_url=url, ai_examples_k=0)
    assert examples_for(rows, CATEGORIES, ANA, off, fake_embed) is None
    unreachable = Settings(ai_database_url="postgresql://127.0.0.1:1/nope")
    assert examples_for(rows, CATEGORIES, ANA, unreachable, fake_embed) is None

    def broken(_texts: list[str]) -> list[list[float]]:
        raise RuntimeError("no model")

    assert examples_for(rows, CATEGORIES, ANA, settings, broken) is None
