"""Tests for discovery.gate — TASK-010."""

from dataclasses import dataclass, field

import pytest

from discovery import protocol
from discovery.contract import gate_check
from discovery.gate import GateInvariantError, render_and_gate


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


def _asked(question_id, coverage_key):
    return {
        "event": "question_asked",
        "question_id": question_id,
        "coverage_key": coverage_key,
        "question_text": f"question for {coverage_key}?",
        "source_pin": "pin-test",
    }


_ENGINEER_SECTIONS = (
    "entries:\n"
    "  - id: S-01\n"
    "    body: current system assessment\n"
    "  - id: IF-01\n"
    "    body: an interface\n"
    "    traces: [S-01]\n"
    "  - id: CON-01\n"
    "    body: a constraint\n"
    "  - id: AP-01\n"
    "    body: an architecture preference\n"
    "    traces: [S-01]\n"
    "  - id: RK-01\n"
    "    body: a risk\n"
)

_UPSTREAM_APPROVED = """---
schema: discovery-brief
schema_version: 1
spec_stage: discovery
status: approved
generated_by: discovery-runtime
generated_at: 2026-08-19T10:00:00Z
validation: pass
interview:
  frame: customer
  sessions:
    - participant_role: product
coverage:
  goals: covered
  personas: covered
  jobs: covered
  functions: covered
  nfr: covered
  constraints: covered
  success_metrics: covered
  out_of_scope: covered
  gate_passed: true
open_questions: 0
blocking_open_questions: 0
conflicts: 0
traces_to: []
---

# Discovery Brief — org/repo (customer-фрейм)

## Functional Requirements

- **FR-07** retry a timed-out courier call
  **Priority**: Must
  **Acceptance**: retried within 30s
  traces: [G-01]
"""


def _engineer_session(tmp_path, verdict_body):
    """An engineer session whose upstream customer brief carries one Must-FR."""
    (tmp_path / "upstream.md").write_text(_UPSTREAM_APPROVED, encoding="utf-8")
    header = Header(frame="engineer", traces_to=["upstream.md"])
    events = [
        _asked("eng.feas.01", "feasibility_review"),
        answer("eng.feas.01", "architect", verdict_body),
        answer("eng.body.01", "architect", _ENGINEER_SECTIONS),
    ]
    return header, events


class TestFeasibilityReviewActivatesGC05:
    """The claim the runtime now makes is the trigger of the linter's check.

    GC-05 (engineer) fires only when the brief declares
    `coverage.feasibility_review: covered`. While the runtime wrote `missing`
    unconditionally, the rule never ran on any brief this runtime produced —
    a key nobody claimed was a check nobody performed. These two cases pin
    both sides of that transition, and neither asserts anything about the
    quality of a feasibility verdict: only that the formalised check now
    runs and reaches a verdict.
    """

    def test_unmentioned_upstream_must_fr_fails_the_gate_by_name(self, tmp_path):
        header, events = _engineer_session(
            tmp_path, "text: reviewed the upstream brief in general terms\n"
        )

        result = render_and_gate(header, events, tmp_path)

        assert result.readiness == "ready"
        assert result.status == "fail"
        gc05 = [f for f in result.findings if "GC-05" in f]
        assert gc05, result.findings
        assert any("FR-07" in f for f in gc05)

    def test_a_completed_run_with_the_failed_claim_projects_to_exit_10(self, tmp_path):
        header, events = _engineer_session(
            tmp_path, "text: reviewed the upstream brief in general terms\n"
        )
        result = render_and_gate(header, events, tmp_path)

        envelope = protocol.ok(
            "complete", result.status, result.readiness, {}, result.findings
        )

        assert protocol.exit_code(envelope) == 10

    def test_every_upstream_must_fr_mentioned_leaves_no_gc05_finding(self, tmp_path):
        header, events = _engineer_session(
            tmp_path,
            "text: feasibility verdicts recorded\n"
            "entries:\n"
            "  - id: X-01\n"
            "    body: FR-07 is feasible on the current courier API\n"
            "    status: resolved\n",
        )

        result = render_and_gate(header, events, tmp_path)

        assert result.readiness == "ready"
        assert [f for f in result.findings if "GC-05" in f] == []


class TestTwoPassInvariant:
    """§6: the accepted pass must have seen the same facts as the first.

    Asserting equality rather than "pass 2 is GC-15-clean" is what catches a
    content-scanning rule whose own diagnostic satisfies it. The comparison
    is on ordered lists: a vanished duplicate or a reordering is a changed
    result too.
    """

    def test_clean_brief_agrees_across_passes(self, tmp_path):
        events = [answer("customer.all.01", "product", _ALL_REQUIRED_COVERED)]

        result = render_and_gate(CUSTOMER, events, tmp_path)

        assert result.status == "pass"
        assert result.findings == []

    def test_failing_brief_keeps_its_reason_in_the_returned_findings(self, tmp_path):
        """The regression this invariant exists for: the reason used to
        vanish between the passes, leaving `gate: fail` unexplained."""
        header, events = _engineer_session(
            tmp_path, "text: reviewed the upstream brief in general terms\n"
        )

        result = render_and_gate(header, events, tmp_path)

        assert result.status == "fail"
        assert any("FR-07" in f for f in result.findings)

    def test_a_pass_that_changes_the_findings_fails_closed(self, tmp_path, monkeypatch):
        """An artificial divergence: the second check reports something the
        first did not. There is no verdict to trust, so the gate refuses."""
        events = [answer("customer.all.01", "product", _ALL_REQUIRED_COVERED)]
        real = gate_check.check
        calls = {"n": 0}

        def flaky(text, base_dir=None):
            calls["n"] += 1
            if calls["n"] == 1:
                return real(text, base_dir=base_dir)
            return [gate_check.Finding("GC-06", "error", "FR-99", "invented")]

        monkeypatch.setattr("discovery.gate.check", flaky)

        with pytest.raises(GateInvariantError) as exc:
            render_and_gate(CUSTOMER, events, tmp_path)
        assert "two-pass mismatch" in str(exc.value)

    def test_final_text_rechecks_independently_to_the_same_result(self, tmp_path):
        """The artifact on disk is the artifact that was checked: an
        independent run of the vendored linter over the accepted text must
        reproduce the accepted findings exactly."""
        header, events = _engineer_session(
            tmp_path, "text: reviewed the upstream brief in general terms\n"
        )

        result = render_and_gate(header, events, tmp_path)
        independent = gate_check.check(result.text, base_dir=tmp_path)

        assert [str(f) for f in independent] == result.findings
