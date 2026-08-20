"""Tests for discovery.journal: durable append and ordered replay.

Each case isolates one claim from [REQ-005]-[REQ-009]: N events round-trip
in append order, `ts` is stamped when absent and preserved when supplied,
an embedded newline stays inside one physical line, and a corrupt line
raises `JournalUnreadable` instead of being skipped.
"""

import pytest

from discovery.journal import (
    ANSWER_RECORDED,
    QUESTION_ASKED,
    Journal,
    JournalUnreadable,
)


def test_events_round_trip_in_append_order(tmp_path):
    journal = Journal(tmp_path / "journal.jsonl")

    for i in range(5):
        journal.append({"type": QUESTION_ASKED, "question_id": f"q{i}"})

    events = journal.events()
    assert [e["question_id"] for e in events] == [f"q{i}" for i in range(5)]


def test_ts_is_stamped_when_absent_and_ends_with_z(tmp_path):
    journal = Journal(tmp_path / "journal.jsonl")

    journal.append({"type": QUESTION_ASKED, "question_id": "q1"})

    event = journal.events()[0]
    assert "ts" in event
    assert event["ts"].endswith("Z")


def test_ts_is_preserved_when_supplied(tmp_path):
    journal = Journal(tmp_path / "journal.jsonl")

    journal.append(
        {"type": ANSWER_RECORDED, "answer_id": "sha256:aaa", "ts": "explicit-ts"}
    )

    assert journal.events()[0]["ts"] == "explicit-ts"


def test_embedded_newline_stays_on_one_physical_line(tmp_path):
    path = tmp_path / "journal.jsonl"
    journal = Journal(path)

    journal.append(
        {
            "type": QUESTION_ASKED,
            "question_id": "q1",
            "question_text": "line one\nline two",
        }
    )

    physical_lines = path.read_text(encoding="utf-8").splitlines()
    assert len(physical_lines) == 1
    assert journal.events()[0]["question_text"] == "line one\nline two"


def test_corrupt_line_after_valid_record_raises_journal_unreadable(tmp_path):
    path = tmp_path / "journal.jsonl"
    journal = Journal(path)

    journal.append({"type": QUESTION_ASKED, "question_id": "q1"})
    with path.open("a", encoding="utf-8") as fh:
        fh.write("{not valid json\n")

    with pytest.raises(JournalUnreadable):
        journal.events()


class TestEventShapeIsValidatedAtTheBoundary:
    """A line that parses as JSON but lacks a field its readers index by is
    unreadable, not merely odd.

    Found by GitHub Copilot on PR #14. A `question_asked` without
    `question_id` used to reach `lifecycle.issued()` and escape the CLI as a
    `KeyError` traceback — with nothing on stdout, which breaks §7's promise
    that every command emits the envelope. Validating at the loader covers
    every reader at once; skipping the line instead would be fail-open,
    since a dropped `question_asked` silently changes the lifecycle.
    """

    def test_question_asked_without_question_id_is_unreadable(self, tmp_path):
        path = tmp_path / "journal.jsonl"
        path.write_text(
            '{"event": "question_asked", "coverage_key": "goals",'
            ' "question_text": "why?"}\n',
            encoding="utf-8",
        )

        with pytest.raises(JournalUnreadable) as exc:
            Journal(path).events()
        assert "question_id" in str(exc.value)

    def test_answer_recorded_without_question_id_is_unreadable(self, tmp_path):
        path = tmp_path / "journal.jsonl"
        path.write_text('{"event": "answer_recorded", "payload": "x"}\n', "utf-8")

        with pytest.raises(JournalUnreadable):
            Journal(path).events()

    def test_a_line_without_an_event_name_carries_no_requirement(self, tmp_path):
        """Every reader selects on `event.get("event")`, so a line with no
        kind is inert, not malformed. Validating it would reject journals
        this repo's own tests append."""
        path = tmp_path / "journal.jsonl"
        path.write_text('{"question_id": "q"}\n', encoding="utf-8")

        assert Journal(path).events() == [{"question_id": "q"}]

    def test_a_non_object_line_is_unreadable(self, tmp_path):
        path = tmp_path / "journal.jsonl"
        path.write_text("[1, 2, 3]\n", encoding="utf-8")

        with pytest.raises(JournalUnreadable):
            Journal(path).events()

    def test_an_unknown_event_kind_passes_through(self, tmp_path):
        """Forward compatibility: a kind this version has no reader for
        carries no indexing requirement, so it is not the loader's business
        to reject it."""
        path = tmp_path / "journal.jsonl"
        path.write_text('{"event": "note_added", "text": "hello"}\n', "utf-8")

        assert Journal(path).events() == [{"event": "note_added", "text": "hello"}]
