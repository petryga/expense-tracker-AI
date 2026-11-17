"""One-time, local: loads the hand-labelled order items (data/item_labels.csv)
into the examples store as kind "seed", for the single local user, so
retrieval has something to find before any import is confirmed.

    .venv/bin/python -m scripts.seed_item_examples

Safe to re-run: the stored seeds are made to match the file. Items confirmed
in the app are kind "item" and are not touched.
"""

from pathlib import Path

from app.config import get_settings
from app.embeddings import local_embedder
from app.examples_store import StoredExample, sync
from eval.items import load_item_labels

ROOT = Path(__file__).resolve().parent.parent


def main() -> None:
    url = get_settings().ai_database_url
    if not url:
        raise SystemExit("Set AI_DATABASE_URL in .env first (see .env.example).")
    with (ROOT / "data" / "item_labels.csv").open(newline="") as f:
        rows = load_item_labels(f)
    seeds = [StoredExample(r.reference, r.description[:512], r.label) for r in rows if r.label]
    result = sync(url, None, "seed", seeds, local_embedder())
    print(f"{result.stored} seeds stored, {result.embedded} embedded, {result.removed} removed")


if __name__ == "__main__":
    main()
