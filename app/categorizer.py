"""Suggests a category per statement row.

The endpoint and the eval runner both call `categorize`, so what the eval
measures is exactly what the app serves.
"""

from app.schemas import CategorizeRow, Suggestion


def categorize(rows: list[CategorizeRow], categories: list[str]) -> list[Suggestion]:
    # Skeleton: no model yet, so no row gets a suggestion. The whole path
    # BE -> AI -> BE works end to end with this in place.
    del categories
    return [Suggestion(id=row.id, category=None, source="none") for row in rows]
