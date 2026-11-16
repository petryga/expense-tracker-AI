"""Collects labelled order items for the item eval into data/item_labels.csv
(gitignored), from the review files of the one-time split of old expenses
(BE/scripts/split-old-amazon.ts): each kept line is a product name with the
category its owner chose. Skipped and returned lines, and lines that are not a
product, are left out.

    .venv/bin/python scripts/export_item_labels.py REVIEW.csv [REVIEW.csv ...]
"""

import csv
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
NOT_A_PRODUCT = ("(difference", "order not found")


def main(paths: list[str]) -> None:
    rows: list[dict[str, str]] = []
    seen: set[tuple[str, str, str]] = set()
    for path in paths:
        with open(path, newline="", encoding="utf-8-sig") as f:
            for line in csv.DictReader(f):
                label = line["new_category"].strip()
                product = " ".join(line["product_name"].split())
                if not label or label.startswith("(") or any(m in product for m in NOT_A_PRODUCT):
                    continue
                key = (product, line["item_amount"], line["date"])
                if key in seen:
                    continue
                seen.add(key)
                rows.append(
                    {
                        "id": f"item-{len(rows) + 1}",
                        "date": line["date"],
                        "text": product,
                        "amount": line["item_amount"],
                        "label": label,
                    }
                )
    out = ROOT / "data" / "item_labels.csv"
    with out.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["id", "date", "text", "amount", "label"])
        writer.writeheader()
        writer.writerows(rows)
    print(f"Wrote {len(rows)} labelled items to {out.relative_to(ROOT)}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    main(sys.argv[1:])
