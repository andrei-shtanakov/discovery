"""Tests for discovery.protocol — TASK-011."""

import json

from discovery.protocol import (
    ANSWER_CONFLICT,
    NO_TARGET_QUESTION,
    Envelope,
    exit_code,
    ok,
    refused,
    unknown,
)


class TestEnvelopeConstructors:
    def test_ok_defaults_next_action_and_findings_to_empty(self):
        envelope = ok("complete", "pass")
        assert envelope.next_action == {}
        assert envelope.findings == []

    def test_refused_defaults_next_action_and_findings_to_empty(self):
        envelope = refused(ANSWER_CONFLICT, "awaiting_input", "fail")
        assert envelope.next_action == {}
        assert envelope.findings == []

    def test_refused_carries_findings_through(self):
        envelope = refused(
            NO_TARGET_QUESTION,
            "complete",
            "fail",
            findings=["GC-04: missing required topic"],
        )
        assert envelope.findings == ["GC-04: missing required topic"]

    def test_unknown_defaults_next_action_and_findings_to_empty(self):
        envelope = unknown("journal unreadable")
        assert envelope.next_action == {}
        assert envelope.findings == []

    def test_constants_are_the_documented_reason_strings(self):
        assert NO_TARGET_QUESTION == "no_target_question"
        assert ANSWER_CONFLICT == "answer_conflict"


class TestEnvelopeToJson:
    def test_to_json_round_trips_supplied_values(self):
        envelope = ok(
            "awaiting_input",
            "pending",
            next_action={"kind": "answer", "question_id": "customer.goals.01"},
            findings=["GC-02: partial coverage"],
        )
        payload = json.loads(envelope.to_json())
        assert payload == {
            "lifecycle": "awaiting_input",
            "gate": "pending",
            "next_action": {"kind": "answer", "question_id": "customer.goals.01"},
            "findings": ["GC-02: partial coverage"],
            "operation": {"status": "ok"},
        }


class TestExitCodeRanks:
    def test_rank_1_unknown_lifecycle_without_unknown_operation(self):
        envelope = Envelope(lifecycle="unknown", gate="pass")
        assert exit_code(envelope) == 1

    def test_rank_1_unknown_gate_without_unknown_operation(self):
        envelope = Envelope(lifecycle="complete", gate="unknown")
        assert exit_code(envelope) == 1

    def test_rank_2_refused_outranks_awaiting_input(self):
        envelope = refused(ANSWER_CONFLICT, "awaiting_input", "fail")
        assert exit_code(envelope) == 2

    def test_rank_5_complete_pass_is_lowest(self):
        envelope = ok("complete", "pass")
        assert exit_code(envelope) == 0

    def test_two_calls_over_same_envelope_agree(self):
        envelope = Envelope(lifecycle="awaiting_input", gate="fail")
        assert exit_code(envelope) == exit_code(envelope) == 20
