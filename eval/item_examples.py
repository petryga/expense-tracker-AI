"""Which past choices each item is shown, for the three-arm retrieval eval
(PLANS.md, Phase C): none, random, and retrieved by similarity.

An item only ever sees items from earlier months, the same rule as the
statement eval, so nothing it is scored against can reach its prompt.
"""

import random

from app.embeddings import Embed, nearest
from app.prompt import Example
from eval.dataset import LabelledRow


def earlier(rows: list[LabelledRow], row: LabelledRow) -> list[LabelledRow]:
    return [r for r in rows if r.month < row.month and r.label]


def _examples(rows: list[LabelledRow]) -> list[Example]:
    return [Example(text=r.description, category=r.label) for r in rows if r.label]


def random_examples(rows: list[LabelledRow], k: int, seed: int = 0) -> dict[str, list[Example]]:
    """k earlier items picked at random: the control arm. It shows whether
    retrieval helps by finding similar items, or just by showing any."""
    rng = random.Random(seed)
    chosen = {}
    for row in rows:
        pool = earlier(rows, row)
        chosen[row.reference] = _examples(rng.sample(pool, min(k, len(pool))))
    return chosen


def retrieved_examples(rows: list[LabelledRow], k: int, embed: Embed) -> dict[str, list[Example]]:
    """The k earlier items whose names are most similar to the item's."""
    vectors = dict(
        zip((r.reference for r in rows), embed([r.description for r in rows]), strict=True)
    )
    chosen = {}
    for row in rows:
        pool = earlier(rows, row)
        best = nearest(vectors[row.reference], [vectors[r.reference] for r in pool], k)
        chosen[row.reference] = _examples([pool[i] for i in best])
    return chosen
