"""QuestionSource port and its static implementation — DESIGN-001.

The single seam through which any future adaptive question source (bank,
model-backed) plugs into the core without lifecycle, render, or gate ever
changing.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Protocol

# Interview profiles, contract v1.4 (`interview.profile`); no field = `full`.
FULL = "full"
FEATURE = "feature"
PROFILES = (FULL, FEATURE)


@dataclass(frozen=True)
class Question:
    """One interview question, addressed by a stable id and coverage key."""

    question_id: str
    coverage_key: str
    text: str
    # A `feature` profile yes/no filter: its answer carries `expand`.
    is_filter: bool = False


class QuestionSource(Protocol):
    """Port for obtaining ordered questions for a frame."""

    @property
    def pin(self) -> str:
        """Provenance of the questions — recorded on every question_asked event."""
        ...

    def questions(self, frame: str) -> list[Question]:
        """Ordered questions for the frame; required topics first."""
        ...

    def feature_questions(
        self, frame: str, expansions: Mapping[str, bool]
    ) -> list[Question]:
        """The `feature` profile's ordered questions, given the filter
        answers so far (`filter question_id -> expand`)."""
        ...


class StaticQuestionSource:
    """Fixed catalogue implementation of `QuestionSource`."""

    def __init__(self, pin: str, catalogue: dict[str, list[Question]]) -> None:
        """Store the pin and a defensive copy of the frame-to-questions catalogue."""
        self._pin = pin
        self._catalogue = {frame: list(qs) for frame, qs in catalogue.items()}

    @property
    def pin(self) -> str:
        """Return exactly the pin this source was constructed with."""
        return self._pin

    def questions(self, frame: str) -> list[Question]:
        """Return the frame's questions in catalogue order, or `[]` if unknown."""
        return list(self._catalogue.get(frame, []))

    def feature_questions(
        self, frame: str, expansions: Mapping[str, bool]
    ) -> list[Question]:
        """A fixed catalogue has no profile markup: the same list as `full`."""
        return self.questions(frame)
