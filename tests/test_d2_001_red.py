"""RED: TASK-001 — compute_lifecycle §5 precondition.

Empty source (no journal, empty catalogue) must project to `unknown`, but a
pending (issued, unanswered) question outranks that emptiness and still
projects to `awaiting_input` even when the source's catalogue is empty.
"""

from discovery.lifecycle import AWAITING_INPUT, UNKNOWN, compute_lifecycle
from discovery.questions import StaticQuestionSource


def question_asked(question_id, coverage_key, text, source_pin="pin-1"):
    return {
        "event": "question_asked",
        "question_id": question_id,
        "coverage_key": coverage_key,
        "question_text": text,
        "source_pin": source_pin,
    }


class TestComputeLifecyclePreconditionRed:
    def test_empty_source_and_journal_is_unknown_and_pending_outranks_emptiness(
        self,
    ):
        empty_source = StaticQuestionSource(pin="pin-1", catalogue={})

        assert compute_lifecycle([], empty_source, "customer") == UNKNOWN

        events = [question_asked("customer.goals.01", "goals", "What problem?")]

        assert compute_lifecycle(events, empty_source, "customer") == AWAITING_INPUT
