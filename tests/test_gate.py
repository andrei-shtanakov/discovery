"""Tests for discovery.gate — TASK-010."""

from dataclasses import dataclass, field

from discovery.gate import render_and_gate


@dataclass(frozen=True)
class Header:
    """Minimal stand-in for `SessionHeader` (WS-B) — only the fields read."""

    frame: str
    traces_to: list[str] = field(default_factory=list)
    created_at: str = "2026-08-19T10:00:00Z"


def answer(question_id, role, payload):
    return {
        "event": "answer_recorded",
        "question_id": question_id,
        "answer_id": f"sha256:{question_id}",
        "participant_role": role,
        "payload": payload,
    }


CUSTOMER = Header(frame="customer")

_ALL_REQUIRED_COVERED = (
    "entries:\n"
    "  - id: G-01\n"
    "    body: a goal\n"
    "  - id: P-01\n"
    "    body: a persona\n"
    "  - id: J-01\n"
    "    body: a job\n"
    "  - id: FR-01\n"
    "    body: a function\n"
    "    Priority: Must\n"
    "    Acceptance: exports complete within 5s\n"
    "    traces: [G-01]\n"
    "  - id: NFR-01\n"
    "    body: a non-functional requirement\n"
    "    Acceptance: yes\n"
    "  - id: CON-01\n"
    "    body: a constraint\n"
    "  - id: M-01\n"
    "    body: a success metric\n"
    "    traces: [G-01]\n"
    "  - id: OUT-01\n"
    "    body: an out-of-scope item\n"
)


class TestThinBrief:
    def test_fails_with_non_empty_findings(self, tmp_path):
        result = render_and_gate(CUSTOMER, [], tmp_path)

        assert result.status == "fail"
        assert result.findings


class TestNoGC15EverInSecondPass:
    def test_thin_brief_second_pass_has_no_gc_15(self, tmp_path):
        result = render_and_gate(CUSTOMER, [], tmp_path)

        assert not [f for f in result.findings if f.startswith("GC-15")]

    def test_passing_brief_second_pass_has_no_gc_15(self, tmp_path):
        events = [answer("customer.all.01", "product", _ALL_REQUIRED_COVERED)]

        result = render_and_gate(CUSTOMER, events, tmp_path)

        assert not [f for f in result.findings if f.startswith("GC-15")]


class TestTextMirrorsStatus:
    def test_text_contains_literal_validation_status(self, tmp_path):
        result = render_and_gate(CUSTOMER, [], tmp_path)

        assert f"validation: {result.status}" in result.text


class TestPassingBrief:
    def test_fully_covered_brief_passes_with_no_findings(self, tmp_path):
        events = [answer("customer.all.01", "product", _ALL_REQUIRED_COVERED)]

        result = render_and_gate(CUSTOMER, events, tmp_path)

        assert result.status == "pass"
        assert result.findings == []
        assert f"validation: {result.status}" in result.text

    def test_fully_covered_brief_text_has_no_embedded_findings_comment(
        self, tmp_path
    ):
        """The pass-1 GC-15 mismatch against the "pending" placeholder must
        not survive into the final text as a stale finding (it never
        reflects a real problem with the accepted "pass" brief)."""
        events = [answer("customer.all.01", "product", _ALL_REQUIRED_COVERED)]

        result = render_and_gate(CUSTOMER, events, tmp_path)

        assert "gate findings" not in result.text
