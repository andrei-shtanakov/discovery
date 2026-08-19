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
