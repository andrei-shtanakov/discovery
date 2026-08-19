"""Tests for discovery.lifecycle — TASK-008."""

from discovery.lifecycle import (
    AWAITING_INPUT,
    COMPLETE,
    UNKNOWN,
    answered_ids,
    compute_lifecycle,
    issued,
    next_question,
)
from discovery.questions import Question, StaticQuestionSource


class SpyQuestionSource:
    """Records every `.questions()` call so a test can assert it never fires."""

    def __init__(self, pin, catalogue):
        self._pin = pin
        self._catalogue = catalogue
        self.questions_calls = []

    @property
    def pin(self):
        return self._pin

    def questions(self, frame):
        self.questions_calls.append(frame)
        return list(self._catalogue.get(frame, []))


def question_asked(question_id, coverage_key, text, source_pin="pin-1"):
    return {
        "event": "question_asked",
        "question_id": question_id,
        "coverage_key": coverage_key,
        "question_text": text,
        "source_pin": source_pin,
    }


def answer_recorded(question_id, answer_id="sha256:x"):
    return {
        "event": "answer_recorded",
        "question_id": question_id,
        "answer_id": answer_id,
    }


class TestIssued:
    def test_returns_one_entry_per_distinct_question_id(self):
        events = [
            question_asked("customer.goals.01", "goals", "What problem?"),
            question_asked("customer.jobs.01", "jobs", "Walk me through it."),
        ]

        result = issued(events)

        assert [e["question_id"] for e in result] == [
            "customer.goals.01",
            "customer.jobs.01",
        ]

    def test_repeated_question_id_collapses_to_the_latest_event(self):
        events = [
            question_asked("customer.goals.01", "goals", "First text"),
            question_asked("customer.goals.01", "goals", "Updated text"),
        ]

        result = issued(events)

        assert len(result) == 1
        assert result[0]["question_text"] == "Updated text"

    def test_preserves_first_seen_insertion_order(self):
        events = [
            question_asked("customer.jobs.01", "jobs", "second-first"),
            question_asked("customer.goals.01", "goals", "first-first"),
            question_asked("customer.jobs.01", "jobs", "second-second"),
        ]

        result = issued(events)

        assert [e["question_id"] for e in result] == [
            "customer.jobs.01",
            "customer.goals.01",
        ]

    def test_ignores_non_question_asked_events(self):
        events = [
            question_asked("customer.goals.01", "goals", "What problem?"),
            answer_recorded("customer.goals.01"),
        ]

        result = issued(events)

        assert len(result) == 1


class TestAnsweredIds:
    def test_returns_question_ids_with_an_answer(self):
        events = [
            question_asked("customer.goals.01", "goals", "What problem?"),
            answer_recorded("customer.goals.01"),
        ]

        assert answered_ids(events) == {"customer.goals.01"}

    def test_question_without_an_answer_is_absent(self):
        events = [question_asked("customer.goals.01", "goals", "What problem?")]

        assert answered_ids(events) == set()

    def test_does_not_require_a_matching_question_asked_event(self):
        events = [answer_recorded("customer.goals.01")]

        assert answered_ids(events) == {"customer.goals.01"}


class TestNextQuestion:
    def test_empty_journal_returns_first_catalogue_question(self):
        source = StaticQuestionSource(
            pin="pin-1",
            catalogue={
                "customer": [
                    Question("customer.goals.01", "goals", "What problem?"),
                    Question("customer.jobs.01", "jobs", "Walk me through it."),
                ]
            },
        )

        result = next_question([], source, "customer")

        assert result == Question("customer.goals.01", "goals", "What problem?")

    def test_pending_question_is_rebuilt_from_its_own_event(self):
        events = [question_asked("customer.goals.01", "goals", "What problem?")]
        source = StaticQuestionSource(
            pin="pin-1",
            catalogue={
                "customer": [Question("customer.goals.01", "goals", "Different text")]
            },
        )

        result = next_question(events, source, "customer")

        assert result == Question("customer.goals.01", "goals", "What problem?")

    def test_pending_question_dropped_from_repinned_source_still_returns_from_journal(
        self,
    ):
        events = [question_asked("customer.retired.99", "retired", "Old question")]
        source = StaticQuestionSource(
            pin="pin-2",
            catalogue={
                "customer": [Question("customer.goals.01", "goals", "What problem?")]
            },
        )

        result = next_question(events, source, "customer")

        assert result == Question("customer.retired.99", "retired", "Old question")

    def test_answered_out_of_order_returns_earliest_issued_unanswered(self):
        events = [
            question_asked("customer.goals.01", "goals", "First issued"),
            question_asked("customer.jobs.01", "jobs", "Second issued"),
            answer_recorded("customer.jobs.01"),
        ]
        source = StaticQuestionSource(pin="pin-1", catalogue={"customer": []})

        result = next_question(events, source, "customer")

        assert result == Question("customer.goals.01", "goals", "First issued")

    def test_all_issued_questions_answered_advances_to_next_unissued(self):
        events = [
            question_asked("customer.goals.01", "goals", "First issued"),
            answer_recorded("customer.goals.01"),
        ]
        source = StaticQuestionSource(
            pin="pin-1",
            catalogue={
                "customer": [
                    Question("customer.goals.01", "goals", "First issued"),
                    Question("customer.jobs.01", "jobs", "Second question"),
                ]
            },
        )

        result = next_question(events, source, "customer")

        assert result == Question("customer.jobs.01", "jobs", "Second question")

    def test_every_source_question_issued_and_answered_returns_none(self):
        events = [
            question_asked("customer.goals.01", "goals", "Only question"),
            answer_recorded("customer.goals.01"),
        ]
        source = StaticQuestionSource(
            pin="pin-1",
            catalogue={
                "customer": [Question("customer.goals.01", "goals", "Only question")]
            },
        )

        result = next_question(events, source, "customer")

        assert result is None

    def test_dangling_answer_for_a_still_catalogued_question_is_not_reoffered(self):
        events = [answer_recorded("customer.goals.01")]
        source = StaticQuestionSource(
            pin="pin-1",
            catalogue={
                "customer": [Question("customer.goals.01", "goals", "What problem?")]
            },
        )

        result = next_question(events, source, "customer")

        assert result is None

    def test_pending_question_never_queries_the_source(self):
        events = [question_asked("customer.goals.01", "goals", "What problem?")]
        source = SpyQuestionSource(
            pin="pin-1",
            catalogue={
                "customer": [Question("customer.goals.01", "goals", "Different text")]
            },
        )

        next_question(events, source, "customer")

        assert source.questions_calls == []


class TestComputeLifecycle:
    def test_empty_journal_is_awaiting_input(self):
        source = StaticQuestionSource(
            pin="pin-1",
            catalogue={
                "customer": [Question("customer.goals.01", "goals", "What problem?")]
            },
        )

        assert compute_lifecycle([], source, "customer") == AWAITING_INPUT

    def test_every_question_issued_and_answered_is_complete(self):
        events = [
            question_asked("customer.goals.01", "goals", "Only question"),
            answer_recorded("customer.goals.01"),
        ]
        source = StaticQuestionSource(
            pin="pin-1",
            catalogue={
                "customer": [Question("customer.goals.01", "goals", "Only question")]
            },
        )

        assert compute_lifecycle(events, source, "customer") == COMPLETE

    def test_issued_but_unanswered_question_stays_awaiting_input(self):
        events = [question_asked("customer.goals.01", "goals", "Only question")]
        source = StaticQuestionSource(
            pin="pin-1",
            catalogue={
                "customer": [Question("customer.goals.01", "goals", "Only question")]
            },
        )

        assert compute_lifecycle(events, source, "customer") == AWAITING_INPUT

    def test_empty_source_and_journal_is_unknown(self):
        empty_source = StaticQuestionSource(pin="pin-1", catalogue={})

        assert compute_lifecycle([], empty_source, "customer") == UNKNOWN

    def test_pending_question_outranks_empty_source_catalogue(self):
        empty_source = StaticQuestionSource(pin="pin-1", catalogue={})
        events = [question_asked("customer.goals.01", "goals", "What problem?")]

        result = compute_lifecycle(events, empty_source, "customer")

        assert result == AWAITING_INPUT
