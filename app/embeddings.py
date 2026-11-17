"""Text embeddings from a small local model, and nearest-neighbour lookup.

The model runs on this machine (PLANS.md, decision 15): nothing is sent
anywhere, and there is no second API key. `fastembed` is an optional extra
(`pip install -e '.[embeddings]'`); only retrieval needs it.
"""

import math
from collections.abc import Callable, Sequence

Vector = Sequence[float]
Embed = Callable[[list[str]], list[list[float]]]

DEFAULT_MODEL = "BAAI/bge-small-en-v1.5"


def local_embedder(model_name: str = DEFAULT_MODEL) -> Embed:
    """Loads the model once (downloaded on first use) and returns the function."""
    from fastembed import TextEmbedding

    model = TextEmbedding(model_name)

    def embed(texts: list[str]) -> list[list[float]]:
        return [[float(x) for x in vector] for vector in model.embed(texts)]

    return embed


def cosine(a: Vector, b: Vector) -> float:
    norm = math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(x * x for x in b))
    return sum(x * y for x, y in zip(a, b, strict=True)) / norm if norm else 0.0


def nearest(query: Vector, pool: Sequence[Vector], k: int) -> list[int]:
    """Indexes of the k pool vectors most similar to the query, best first."""
    ranked = sorted(range(len(pool)), key=lambda i: cosine(query, pool[i]), reverse=True)
    return ranked[:k]
