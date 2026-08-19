"""Frozen RED checkpoint for TASK-008.

This file is byte-frozen until the task is done: it exists to prove that,
at the moment the task started, `discovery.lifecycle` did not yet exist, so
`next_question` could not be shown to honour DESIGN-ADR-001's rule that an
already-issued, still-unanswered question is rebuilt entirely from its own
`question_asked` event — never re-resolved through `QuestionSource.questions`.
A re-pinned bank that no longer carries the id (or would answer with
different text) must not be consulted at all for that id.
"""

from discovery.questions import Question


class SpyQuestionSource:
    """Records every `.questions()` call so a test can assert it never fires."""

    def __init__(self, catalogue: dict[str, list[Question]]) -> None:
        self._catalogue = catalogue
        self.questions_calls: list[str] = []

    @property
    def pin(self) -> str:
        return "pin-2"

    def questions(self, frame: str) -> list[Question]:
        self.questions_calls.append(frame)
        return list(self._catalogue.get(frame, []))


class TestNextQuestionRed:
    def test_pending_question_is_rebuilt_from_journal_without_querying_source(self):
        from discovery.lifecycle import next_question

        events = [
            {
                "event": "question_asked",
                "question_id": "customer.retired.99",
                "coverage_key": "retired",
                "question_text": "A question the new bank dropped",
                "source_pin": "pin-1",
            }
        ]
        source = SpyQuestionSource(
            catalogue={
                "customer": [
                    Question("customer.goals.01", "goals", "What problem?"),
                ]
            }
        )

        question = next_question(events, source, "customer")

        assert question.question_id == "customer.retired.99"
        assert question.text == "A question the new bank dropped"
        assert source.questions_calls == []
