"""How a predictor did, split the way the plan asks (PLANS.md, Phase B, step 6).

Rows with a real category: right, wrong, or no suggestion.
"Can't tell" rows: the right answer is no suggestion; anything else is a guess
it should not have made.
"""

from dataclasses import dataclass, field


@dataclass
class Score:
    category_rows: int = 0
    right: int = 0
    wrong: int = 0
    no_suggestion: int = 0
    cant_tell_rows: int = 0
    held_back: int = 0
    guessed: int = 0
    misses: list[tuple[str, str | None, str | None]] = field(default_factory=list)

    def add(self, description: str, label: str | None, prediction: str | None) -> None:
        if label is None:
            self.cant_tell_rows += 1
            if prediction is None:
                self.held_back += 1
            else:
                self.guessed += 1
                self.misses.append((description, label, prediction))
            return
        self.category_rows += 1
        if prediction == label:
            self.right += 1
        elif prediction is None:
            self.no_suggestion += 1
            self.misses.append((description, label, prediction))
        else:
            self.wrong += 1
            self.misses.append((description, label, prediction))

    def merge(self, other: "Score") -> None:
        for name in (
            "category_rows",
            "right",
            "wrong",
            "no_suggestion",
            "cant_tell_rows",
            "held_back",
            "guessed",
        ):
            setattr(self, name, getattr(self, name) + getattr(other, name))
        self.misses += other.misses

    @property
    def accuracy(self) -> float:
        """Right answers over all rows that have a category."""
        return self.right / self.category_rows if self.category_rows else 0.0

    @property
    def precision(self) -> float:
        """Of the suggestions it made on category rows, how many were right."""
        made = self.right + self.wrong
        return self.right / made if made else 0.0

    @property
    def held_back_rate(self) -> float:
        return self.held_back / self.cant_tell_rows if self.cant_tell_rows else 0.0


def score(
    descriptions: list[str], labels: list[str | None], predictions: list[str | None]
) -> Score:
    s = Score()
    for d, label, prediction in zip(descriptions, labels, predictions, strict=True):
        s.add(d, label, prediction)
    return s
