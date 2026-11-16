"""Checks data/labels.csv and shows how far labelling has got.

    .venv/bin/python -m eval.check_labels

Exits with an error if any label isn't one of your categories (or "can't tell").
"""

import csv
import sys
from pathlib import Path

from eval.labels import check, inconsistencies

DATA = Path(__file__).resolve().parent.parent / "data"


def main() -> int:
    with (DATA / "labels.csv").open(newline="") as f:
        rows = list(csv.DictReader(f))
    with (DATA / "categories.csv").open(newline="") as f:
        categories = {row["name"] for row in csv.DictReader(f)}

    report = check(rows, categories)
    print(f"Checked {report.checked} of {report.total} ({report.cant_tell} marked can't tell)")
    for month, (done, total) in report.per_month.items():
        print(f"  {month}  {done:3d}/{total:<3d} {'done' if done == total else ''}")
    for error in report.errors:
        print(f"ERROR {error}")
    for merchant, group in inconsistencies(rows).items():
        print(f"WARN  {merchant}: different labels")
        for row in group:
            mark = "checked" if row.get("checked", "").strip() else ""
            print(f"        {row['date']}  {row['amount']:>8}  {row['label']:<22} {mark}")
    return 1 if report.errors else 0


if __name__ == "__main__":
    sys.exit(main())
