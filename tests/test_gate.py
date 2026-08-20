"""Tests for discovery.gate — TASK-010."""

from dataclasses import dataclass, field

from discovery.gate import render_and_gate


@dataclass(frozen=True)
class Header:
    """Minimal stand-in for `SessionHeader` (WS-B) — only the fields read."""

    frame: str
    target: str = "org/repo"
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

    def test_fully_covered_brief_text_has_no_embedded_findings_comment(self, tmp_path):
        """The pass-1 GC-15 mismatch against the "pending" placeholder must
        not survive into the final text as a stale finding (it never
        reflects a real problem with the accepted "pass" brief)."""
        events = [answer("customer.all.01", "product", _ALL_REQUIRED_COVERED)]

        result = render_and_gate(CUSTOMER, events, tmp_path)

        assert "gate findings" not in result.text


class TestPassingBriefWithWarningsOnly:
    def test_warning_only_findings_still_pass_and_survive_into_result(self, tmp_path):
        """A brief with zero errors but a real warning (GC-14: solution-space
        entry in a customer-frame brief) must still gate "pass" — and the
        warning must survive, unmangled, into the returned findings."""
        events = [
            answer(
                "customer.all.01",
                "product",
                _ALL_REQUIRED_COVERED + "  - id: S-01\n    body: a system\n",
            )
        ]

        result = render_and_gate(CUSTOMER, events, tmp_path)

        assert result.status == "pass"
        assert any(f.startswith("GC-14") for f in result.findings)
        assert not any(f.startswith("GC-15") for f in result.findings)


class TestReadinessOnGateResult:
    def test_thin_brief_is_lint_clean_but_not_ready(self, tmp_path):
        result = render_and_gate(CUSTOMER, [], tmp_path)

        assert result.readiness == "incomplete"
        assert result.readiness_findings != []

    def test_full_brief_is_ready_with_no_readiness_findings(self, tmp_path):
        events = [answer("q", "product", _ALL_REQUIRED_COVERED)]

        result = render_and_gate(CUSTOMER, events, tmp_path)

        assert result.status == "pass"
        assert result.readiness == "ready"
        assert result.readiness_findings == []

    def test_readiness_findings_are_not_mixed_into_linter_findings(self, tmp_path):
        result = render_and_gate(CUSTOMER, [], tmp_path)

        assert not set(result.readiness_findings) & set(result.findings)


class TestPass2NeverCorruptsTrailingEntry:
    def test_findings_comment_does_not_leak_into_last_body_entry(self, tmp_path):
        """Regression: the embedded findings HTML comment must not be parsed
        as part of the brief's last body entry — else its own finding
        message text can pollute that entry's regex-parsed fields
        (status/blocking/traces/...), swallowing a real finding (GC-09
        here) or fabricating a spurious one (GC-10, from a corrupted
        conflict count) in its place."""
        events = [
            answer(
                "customer.all.01",
                "product",
                _ALL_REQUIRED_COVERED + "  - id: X-01\n    body: a conflict\n",
            )
        ]

        result = render_and_gate(CUSTOMER, events, tmp_path)

        assert result.status == "fail"
        assert any(f.startswith("GC-09") for f in result.findings)
        assert not any(f.startswith("GC-10") for f in result.findings)
