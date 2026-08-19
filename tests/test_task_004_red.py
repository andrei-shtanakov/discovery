"""Frozen RED checkpoint for TASK-004.

This file is byte-frozen until the task is done: it exists to prove that,
at the moment the task started, `src/discovery/journal.py` did not yet
exist, so none of REQ-005 (durable single-line append), REQ-006
(round-trip order), REQ-007 (implicit ts), REQ-008 (JournalUnreadable on a
corrupt line), or REQ-009 (named event-type constants) could be checked.
"""

import pytest


class TestJournalRed:
    def test_durable_append_and_replay_follow_req_005_through_009(self, tmp_path):
        try:
            from discovery.journal import (
                ANSWER_RECORDED,
                ANSWER_SUPERSEDED,
                QUESTION_ASKED,
                SOURCE_PIN_CHANGED,
                Journal,
                JournalUnreadable,
            )
        except ModuleNotFoundError as exc:
            pytest.fail(
                "discovery.journal does not exist yet "
                f"(REQ-005..REQ-009 unimplemented): {exc}"
            )

        path = tmp_path / "journal.jsonl"
        journal = Journal(path)

        # REQ-006: N events round-trip in append order with every field
        # preserved. REQ-005: a value with an embedded newline (multi-line
        # question_text) does not split the record across physical lines —
        # the file must have exactly as many physical lines as events.
        journal.append(
            {
                "type": QUESTION_ASKED,
                "question_id": "q1",
                "question_text": "line one\nline two",
            }
        )
        journal.append({"type": ANSWER_RECORDED, "answer_id": "sha256:aaa"})
        journal.append({"type": ANSWER_SUPERSEDED, "answer_id": "sha256:bbb"})
        journal.append({"type": SOURCE_PIN_CHANGED, "pin": "commit:deadbeef"})

        physical_lines = path.read_text(encoding="utf-8").splitlines()
        assert len(physical_lines) == 4

        events = journal.events()
        assert [e["type"] for e in events] == [
            QUESTION_ASKED,
            ANSWER_RECORDED,
            ANSWER_SUPERSEDED,
            SOURCE_PIN_CHANGED,
        ]
        assert events[0]["question_text"] == "line one\nline two"
        assert events[1]["answer_id"] == "sha256:aaa"

        # REQ-007: ts is stamped automatically (UTC, ends with "Z") when
        # not supplied, and preserved verbatim when the caller sets it.
        assert events[0]["ts"].endswith("Z")
        for event in events:
            assert "ts" in event

        journal.append({"type": QUESTION_ASKED, "question_id": "q2", "ts": "explicit"})
        assert journal.events()[-1]["ts"] == "explicit"

        # REQ-008: a syntactically-broken line appended after valid
        # records raises JournalUnreadable instead of silently skipping it
        # or returning a truncated list.
        with path.open("a", encoding="utf-8") as fh:
            fh.write("{not valid json\n")

        with pytest.raises(JournalUnreadable):
            journal.events()

        # REQ-009: event-type constants are distinct string literals.
        assert {
            QUESTION_ASKED,
            ANSWER_RECORDED,
            ANSWER_SUPERSEDED,
            SOURCE_PIN_CHANGED,
        } == {
            "question_asked",
            "answer_recorded",
            "answer_superseded",
            "source_pin_changed",
        }
