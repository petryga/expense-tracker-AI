"""The user's past category choices, with their embeddings, in Postgres
(pgvector). The table is created by a BE/ migration; this service is the
only one that reads or writes it, with a role limited to it.

The table is an index, not a source of truth: BE/ sends the full current set
before it asks for suggestions, and `sync` makes the table match.
"""

from dataclasses import dataclass

import psycopg

from app.embeddings import Embed
from app.prompt import Example

TABLE = "category_examples"


@dataclass(frozen=True)
class StoredExample:
    source: str  # the sender's own id for it, unique per user and kind
    text: str
    category: str


@dataclass(frozen=True)
class SyncResult:
    stored: int
    embedded: int
    removed: int


def _vector(values: list[float]) -> str:
    return "[" + ",".join(f"{v:.7g}" for v in values) + "]"


def sync(
    url: str, user_id: str | None, kind: str, examples: list[StoredExample], embed: Embed
) -> SyncResult:
    """Makes the user's examples of this kind equal to `examples`. Only new
    or reworded ones are embedded; a changed category is just updated."""
    wanted = {e.source: e for e in examples}
    with psycopg.connect(url, connect_timeout=5) as conn:
        existing = {
            source: (text, category)
            for source, text, category in conn.execute(
                f"SELECT source, text, category FROM {TABLE} "
                "WHERE user_id IS NOT DISTINCT FROM %s::uuid AND kind = %s",
                (user_id, kind),
            )
        }
        to_embed = [e for s, e in wanted.items() if s not in existing or existing[s][0] != e.text]
        recategorized = [
            e
            for s, e in wanted.items()
            if s in existing and existing[s][0] == e.text and existing[s][1] != e.category
        ]
        gone = [s for s in existing if s not in wanted]
        replaced = gone + [e.source for e in to_embed if e.source in existing]
        # Embed before writing, so a failure here leaves the table as it was.
        vectors = embed([e.text for e in to_embed]) if to_embed else []
        if replaced:
            conn.execute(
                f"DELETE FROM {TABLE} WHERE user_id IS NOT DISTINCT FROM %s::uuid "
                "AND kind = %s AND source = ANY(%s)",
                (user_id, kind, replaced),
            )
        with conn.cursor() as cursor:
            cursor.executemany(
                f"INSERT INTO {TABLE} (user_id, kind, source, text, category, embedding) "
                "VALUES (%s::uuid, %s, %s, %s, %s, %s::vector)",
                [
                    (user_id, kind, e.source, e.text, e.category, _vector(v))
                    for e, v in zip(to_embed, vectors, strict=True)
                ],
            )
            cursor.executemany(
                f"UPDATE {TABLE} SET category = %s, updated_at = now() "
                "WHERE user_id IS NOT DISTINCT FROM %s::uuid AND kind = %s AND source = %s",
                [(e.category, user_id, kind, e.source) for e in recategorized],
            )
    return SyncResult(stored=len(wanted), embedded=len(to_embed), removed=len(gone))


def nearest(
    url: str, user_id: str | None, vectors: list[list[float]], categories: list[str], k: int
) -> list[list[Example]]:
    """For each vector, this user's k most similar examples, best first.
    Only categories the user still has, and no example twice."""
    found: list[list[Example]] = []
    with psycopg.connect(url, connect_timeout=5) as conn:
        for vector in vectors:
            rows = conn.execute(
                f"SELECT text, category FROM {TABLE} "
                "WHERE user_id IS NOT DISTINCT FROM %s::uuid AND category = ANY(%s) "
                "ORDER BY embedding <=> %s::vector LIMIT %s",
                (user_id, categories, _vector(vector), k * 3),
            ).fetchall()
            unique = list(dict.fromkeys(Example(text, category) for text, category in rows))
            found.append(unique[:k])
    return found
