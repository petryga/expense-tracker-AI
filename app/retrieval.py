"""Past choices to show the model next to an order item (PLANS.md, Phase C).

Measured on labelled items: 3 retrieved past choices beat both no examples
and 3 random ones (README, "Order items"). Statement rows get none: merchant
memory in BE/ already covers repeat merchants, and retrieval for them has
not been measured.

Never raises. Without a database, the embedding model or the table, rows are
categorized without examples, exactly as before.
"""

import logging
from functools import lru_cache

from app import examples_store
from app.config import Settings
from app.embeddings import Embed, local_embedder
from app.prompt import Examples
from app.schemas import CategorizeRow

log = logging.getLogger("ai")


@lru_cache(maxsize=1)
def default_embedder() -> Embed:
    """The local model, loaded once per process on first use."""
    return local_embedder()


def examples_for(
    rows: list[CategorizeRow],
    categories: list[str],
    user_id: str | None,
    settings: Settings,
    embed: Embed | None = None,
) -> Examples | None:
    items = [r for r in rows if r.kind == "item"]
    if not items or not settings.ai_database_url or settings.ai_examples_k <= 0:
        return None
    try:
        vectors = (embed or default_embedder())([r.text for r in items])
        found = examples_store.nearest(
            settings.ai_database_url, user_id, vectors, categories, settings.ai_examples_k
        )
    except Exception as error:  # No model, no database, no table: go on without.
        log.warning("retrieval unavailable: %s", type(error).__name__)
        return None
    return {r.id: shown for r, shown in zip(items, found, strict=True) if shown}
