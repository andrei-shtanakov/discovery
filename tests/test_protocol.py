"""Tests for discovery.protocol — TASK-011."""

import json

from discovery import render
from discovery.protocol import (
    ANSWER_CONFLICT,
    INCOMPLETE,
    NO_TARGET_QUESTION,
    Envelope,
    exit_code,
    ok,
    refused,
    unknown,
)


class TestEnvelopeConstructors:
    def test_ok_defaults_next_action_and_findings_to_empty(self):
        envelope = ok("complete", "pass", "ready")
        assert envelope.next_action == {}
        assert envelope.findings == []

    def test_refused_defaults_next_action_and_findings_to_empty(self):
        envelope = refused(ANSWER_CONFLICT, "awaiting_input", "fail", "incomplete")
        assert envelope.next_action == {}
        assert envelope.findings == []

    def test_refused_carries_findings_through(self):
        envelope = refused(
            NO_TARGET_QUESTION,
            "complete",
            "fail",
            "incomplete",
            findings=["GC-04: missing required topic"],
        )
        assert envelope.findings == ["GC-04: missing required topic"]
        assert exit_code(envelope) == 2

    def test_unknown_defaults_next_action_and_findings_to_empty(self):
        envelope = unknown("journal unreadable")
        assert envelope.next_action == {}
        assert envelope.findings == []

    def test_constants_are_the_documented_reason_strings(self):
        assert NO_TARGET_QUESTION == "no_target_question"
        assert ANSWER_CONFLICT == "answer_conflict"

    def test_incomplete_literal_matches_render_module(self):
        """`protocol` must not import `render` (layering), so the two
        `INCOMPLETE` literals are duplicated by hand. If they ever diverged,
        `exit_code` would return 0 for a thin brief — precisely the bug this
        branch's readiness axis exists to remove. A test may import both
        modules; the modules themselves may not import each other."""
        assert INCOMPLETE == render.INCOMPLETE


class TestEnvelopeToJson:
    def test_to_json_round_trips_supplied_values(self):
        envelope = ok(
            "awaiting_input",
            "pending",
            "incomplete",
            next_action={"kind": "answer", "question_id": "customer.goals.01"},
            findings=["GC-02: partial coverage"],
        )
        payload = json.loads(envelope.to_json())
        assert payload == {
            "lifecycle": "awaiting_input",
            "gate": "pending",
            "readiness": "incomplete",
            "next_action": {"kind": "answer", "question_id": "customer.goals.01"},
            "findings": ["GC-02: partial coverage"],
            "readiness_findings": [],
            "operation": {"status": "ok"},
        }


class TestExitCodeRanks:
    def test_rank_1_unknown_lifecycle_without_unknown_operation(self):
        envelope = Envelope(lifecycle="unknown", gate="pass", readiness="ready")
        assert exit_code(envelope) == 1

    def test_rank_1_unknown_gate_without_unknown_operation(self):
        envelope = Envelope(lifecycle="complete", gate="unknown", readiness="ready")
        assert exit_code(envelope) == 1

    def test_rank_2_refused_outranks_awaiting_input(self):
        envelope = refused(ANSWER_CONFLICT, "awaiting_input", "fail", "incomplete")
        assert exit_code(envelope) == 2

    def test_rank_4_complete_fail(self):
        envelope = Envelope(lifecycle="complete", gate="fail", readiness="incomplete")
        assert exit_code(envelope) == 10

    def test_rank_5_complete_pass_is_lowest(self):
        envelope = ok("complete", "pass", "ready")
        assert exit_code(envelope) == 0

    def test_rank_1_unknown_operation_outranks_complete_pass(self):
        envelope = Envelope(
            lifecycle="complete",
            gate="pass",
            readiness="ready",
            operation={"status": "unknown", "reason": "journal unreadable"},
        )
        assert exit_code(envelope) == 1

    def test_two_calls_over_same_envelope_agree(self):
        envelope = Envelope(
            lifecycle="awaiting_input", gate="fail", readiness="incomplete"
        )
        assert exit_code(envelope) == exit_code(envelope) == 20


class TestReadinessAxis:
    def test_to_json_emits_the_seven_contract_keys_in_order(self):
        payload = json.loads(ok("complete", "pass", "ready").to_json())

        assert list(payload) == [
            "lifecycle",
            "gate",
            "readiness",
            "next_action",
            "findings",
            "readiness_findings",
            "operation",
        ]

    def test_unknown_collapses_all_three_axes(self):
        envelope = unknown("journal unreadable")

        assert envelope.lifecycle == "unknown"
        assert envelope.gate == "unknown"
        assert envelope.readiness == "unknown"
        assert envelope.readiness_findings == []

    def test_refusal_carries_the_readiness_axis_through(self):
        envelope = refused(
            ANSWER_CONFLICT,
            "complete",
            "pass",
            "incomplete",
            readiness_findings=["required topic 'goals' is not covered"],
        )

        assert envelope.readiness == "incomplete"
        assert exit_code(envelope) == 2


class TestExitCodePriority:
    def test_lint_valid_stub_is_11(self):
        assert exit_code(ok("complete", "pass", "incomplete")) == 11

    def test_ready_brief_is_0(self):
        assert exit_code(ok("complete", "pass", "ready")) == 0

    def test_gate_fail_outranks_incomplete_readiness(self):
        assert exit_code(ok("complete", "fail", "incomplete")) == 10

    def test_awaiting_input_outranks_incomplete_readiness(self):
        assert exit_code(ok("awaiting_input", "pass", "incomplete")) == 20

    def test_refusal_outranks_incomplete_readiness(self):
        assert (
            exit_code(refused(ANSWER_CONFLICT, "complete", "pass", "incomplete")) == 2
        )

    def test_unknown_readiness_is_1_even_when_the_other_axes_are_known(self):
        assert exit_code(ok("complete", "pass", "unknown")) == 1
