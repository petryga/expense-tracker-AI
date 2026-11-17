"""The contract with BE/ (PLANS.md, Plan 3, "Architecture"). JSON is camelCase."""

from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StringConstraints
from pydantic.alias_generators import to_camel

CategoryName = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)
]


class _Camel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, extra="forbid")


class CategorizeRow(_Camel):
    id: Annotated[str, StringConstraints(min_length=1, max_length=64)]
    # The statement text as the bank printed it.
    text: Annotated[str, StringConstraints(min_length=1, max_length=512)]
    amount_cents: int
    # The bank's own category for the row (e.g. "Restaurant-Restaurant"), if sent.
    bank_category: Annotated[str, StringConstraints(max_length=100)] | None = None
    # "item": an order item, where the text is a product name. Items are
    # shown the user's past choices for similar products.
    kind: Literal["statement", "item"] = "statement"


class CategorizeRequest(_Camel):
    rows: Annotated[list[CategorizeRow], Field(max_length=500)]
    # The user's own category names; a suggestion must be one of these.
    categories: Annotated[list[CategoryName], Field(max_length=300)]
    # Whose past choices to look in. None is the single local user (auth off).
    user_id: UUID | None = None


# Where a suggestion came from. "none" means no suggestion: the model was not
# asked, could not tell, or failed. BE/ treats every row the same way then.
SuggestionSource = Literal["model", "none"]


class Suggestion(_Camel):
    id: str
    category: str | None
    source: SuggestionSource


class CategorizeResponse(_Camel):
    suggestions: list[Suggestion]


class ExampleIn(_Camel):
    # The sender's own id for this choice.
    source: Annotated[str, StringConstraints(min_length=1, max_length=100)]
    text: Annotated[str, StringConstraints(min_length=1, max_length=512)]
    category: CategoryName


class SyncExamplesRequest(_Camel):
    """All of a user's past item choices. The stored set is made to match."""

    user_id: UUID | None = None
    examples: Annotated[list[ExampleIn], Field(max_length=5000)]


class SyncExamplesResponse(_Camel):
    stored: int
    embedded: int
    removed: int
