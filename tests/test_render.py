"""Tests for discovery.render — TASK-009."""

from dataclasses import dataclass, field

import pytest
import yaml

from discovery.payload import PayloadInvalid
from discovery.render import readiness, render_brief


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


def _frontmatter(text: str) -> dict:
    assert text.startswith("---\n")
    end = text.find("\n---", 4)
    return yaml.safe_load(text[4:end])


class TestFrontmatterShape:
    def test_carries_schema_and_validation_fields(self):
        events = [
            answer(
                "customer.goals.01",
                "product",
                "entries:\n  - id: G-01\n    body: reach 10k users\n",
            )
        ]

        text = render_brief(CUSTOMER, events, "pending")
        meta = _frontmatter(text)

        assert meta["schema"] == "discovery-brief"
        assert meta["schema_version"] == 1
        assert meta["spec_stage"] == "discovery"
        assert meta["interview"]["frame"] == "customer"
        assert meta["interview"]["sessions"] == [{"participant_role": "product"}]

    def test_validation_is_exactly_the_caller_supplied_value_never_inferred(self):
        events = [
            answer(
                "customer.goals.01",
                "product",
                "entries:\n  - id: G-01\n    body: reach 10k users\n",
            )
        ]

        text = render_brief(CUSTOMER, events, "fail")

        assert _frontmatter(text)["validation"] == "fail"


class TestSpecMetaCore:
    """GC-02 requires non-empty status/generated_by/generated_at (contract §5)."""

    def test_carries_status_generated_by_and_generated_at(self):
        events = [
            answer(
                "customer.goals.01",
                "product",
                "entries:\n  - id: G-01\n    body: reach 10k users\n",
            )
        ]

        meta = _frontmatter(render_brief(CUSTOMER, events, "pending"))

        assert meta["status"] == "draft"
        assert meta["generated_by"]
        assert meta["generated_at"] == CUSTOMER.created_at


class TestCoverage:
    def test_key_with_a_matching_entry_prefix_is_covered(self):
        events = [
            answer(
                "customer.goals.01",
                "product",
                "entries:\n  - id: G-01\n    body: reach 10k users\n",
            )
        ]

        meta = _frontmatter(render_brief(CUSTOMER, events, "pending"))

        assert meta["coverage"]["goals"] == "covered"

    def test_required_key_with_no_matching_entry_is_missing(self):
        meta = _frontmatter(render_brief(CUSTOMER, [], "pending"))

        assert meta["coverage"]["goals"] == "missing"
        assert meta["coverage"]["personas"] == "missing"


class TestSupersession:
    def test_only_the_latest_answers_entries_reach_the_body(self):
        old = answer(
            "customer.goals.01",
            "product",
            "entries:\n  - id: G-01\n    body: stale goal\n",
        )
        new = answer(
            "customer.goals.01",
            "product",
            "entries:\n  - id: G-01\n    body: current goal\n",
        )

        text = render_brief(CUSTOMER, [old, new], "pending")

        assert "current goal" in text
        assert "stale goal" not in text


class TestPurity:
    def test_identical_calls_produce_byte_identical_output(self):
        events = [
            answer(
                "customer.goals.01",
                "product",
                "entries:\n  - id: G-01\n    body: reach 10k users\n",
            )
        ]

        first = render_brief(CUSTOMER, events, "pending")
        second = render_brief(CUSTOMER, events, "pending")

        assert first == second


class TestBodyRendering:
    def test_entry_fields_render_verbatim(self):
        payload = (
            "entries:\n"
            "  - id: FR-01\n"
            "    body: Users can export a report\n"
            "    Priority: Must\n"
            "    Acceptance: exports complete within 5s\n"
            "    traces: [G-01]\n"
        )
        events = [answer("customer.functions.01", "product", payload)]

        text = render_brief(CUSTOMER, events, "pending")

        assert "## Functional Requirements" in text
        assert "- **FR-01** Users can export a report" in text
        assert "**Priority**: Must" in text
        assert "**Acceptance**: exports complete within 5s" in text
        assert "traces: [G-01]" in text

    def test_entries_group_by_id_prefix_into_named_sections(self):
        events = [
            answer(
                "customer.goals.01",
                "product",
                "entries:\n  - id: G-01\n    body: a goal\n",
            ),
            answer(
                "customer.personas.01",
                "product",
                "entries:\n  - id: P-01\n    body: a persona\n",
            ),
        ]

        text = render_brief(CUSTOMER, events, "pending")

        assert "## Goals" in text
        assert "## Personas" in text
        assert text.index("## Goals") < text.index("## Personas")

    def test_section_titles_follow_the_contract_table_not_local_taste(self):
        """§2 names the sections; a renamed section is navigable only by us.

        The linter never parses these headings, so nothing here fails the
        gate — which is why the drift survived until a human read a brief
        (found reviewing dispatcher#162).
        """
        from discovery.render import SECTION_TITLES

        assert SECTION_TITLES["J"] == "Jobs-to-be-done"
        assert SECTION_TITLES["X"] == "Stakeholder Conflicts"
        assert SECTION_TITLES["S"] == "System Assessment"
        assert all(
            title == title[0].upper() + title[1:] for title in SECTION_TITLES.values()
        )

    def test_brief_opens_with_an_h1_naming_target_and_frame(self):
        events = [
            answer(
                "customer.goals.01",
                "product",
                "entries:\n  - id: G-01\n    body: a goal\n",
            )
        ]

        text = render_brief(CUSTOMER, events, "pending")
        body = text.split("---\n", 2)[2]

        assert body.lstrip().startswith(
            "# Discovery Brief — org/repo (customer-фрейм)"
        ), (
            "a brief with no title is an anonymous document once it leaves the "
            "session directory"
        )


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
    "    traces: [G-01]\n"
    "  - id: NFR-01\n"
    "    body: a non-functional requirement\n"
    "  - id: CON-01\n"
    "    body: a constraint\n"
    "  - id: M-01\n"
    "    body: a success metric\n"
    "  - id: OUT-01\n"
    "    body: an out-of-scope item\n"
)


class TestGatePassed:
    def test_true_when_all_required_covered_fr_traced_and_no_blocking_questions(self):
        events = [answer("customer.all.01", "product", _ALL_REQUIRED_COVERED)]

        meta = _frontmatter(render_brief(CUSTOMER, events, "pending"))

        assert meta["coverage"]["gate_passed"] is True

    def test_false_when_a_required_key_has_no_covering_entry(self):
        payload = _ALL_REQUIRED_COVERED.replace(
            "  - id: OUT-01\n    body: an out-of-scope item\n", ""
        )
        events = [answer("customer.all.01", "product", payload)]

        meta = _frontmatter(render_brief(CUSTOMER, events, "pending"))

        assert meta["coverage"]["out_of_scope"] == "missing"
        assert meta["coverage"]["gate_passed"] is False

    def test_false_when_an_fr_entry_has_no_traces(self):
        payload = _ALL_REQUIRED_COVERED.replace(
            "  - id: FR-01\n    body: a function\n    traces: [G-01]\n",
            "  - id: FR-01\n    body: a function\n",
        )
        events = [answer("customer.all.01", "product", payload)]

        meta = _frontmatter(render_brief(CUSTOMER, events, "pending"))

        assert meta["coverage"]["gate_passed"] is False

    def test_false_when_an_fr_entry_traces_to_a_nonexistent_id(self):
        payload = _ALL_REQUIRED_COVERED.replace("traces: [G-01]", "traces: [G-99]")
        events = [answer("customer.all.01", "product", payload)]

        meta = _frontmatter(render_brief(CUSTOMER, events, "pending"))

        assert meta["coverage"]["gate_passed"] is False

    def test_false_when_an_unresolved_blocking_question_exists(self):
        payload = _ALL_REQUIRED_COVERED + (
            "  - id: Q-01\n"
            "    body: an open question\n"
            "    blocking: true\n"
            "    resolved: false\n"
        )
        events = [answer("customer.all.01", "product", payload)]

        meta = _frontmatter(render_brief(CUSTOMER, events, "pending"))

        assert meta["coverage"]["gate_passed"] is False

    def test_true_when_an_open_question_is_not_blocking(self):
        payload = _ALL_REQUIRED_COVERED + (
            "  - id: Q-01\n"
            "    body: an open question\n"
            "    blocking: false\n"
            "    resolved: false\n"
        )
        events = [answer("customer.all.01", "product", payload)]

        meta = _frontmatter(render_brief(CUSTOMER, events, "pending"))

        assert meta["coverage"]["gate_passed"] is True


class TestFindingsRendering:
    def test_findings_render_as_a_trailing_html_comment_block(self):
        events = [
            answer(
                "customer.goals.01",
                "product",
                "entries:\n  - id: G-01\n    body: reach 10k users\n",
            )
        ]

        text = render_brief(
            CUSTOMER, events, "fail", findings=["GC-06 FR-01: no traces"]
        )

        assert "<!-- gate findings:" in text
        assert "- GC-06 FR-01: no traces" in text
        assert text.rstrip().endswith("-->")

    def test_no_findings_block_when_findings_is_none_or_empty(self):
        events = [
            answer(
                "customer.goals.01",
                "product",
                "entries:\n  - id: G-01\n    body: reach 10k users\n",
            )
        ]

        assert "gate findings" not in render_brief(CUSTOMER, events, "pending")
        assert "gate findings" not in render_brief(
            CUSTOMER, events, "pending", findings=[]
        )


class TestTracesTypeOnRead:
    def test_missing_traces_on_an_fr_is_a_finding_not_an_error(self):
        """A `traces` key that is simply absent (never a payload.py concern —
        that module refuses an *explicit* null, see test_payload.py) reads as
        "no trace" and surfaces as a readiness finding, not an exception."""
        events = [
            answer(
                "customer.functions.01",
                "product",
                "entries:\n"
                "  - id: G-01\n"
                "    body: a goal\n"
                "  - id: FR-01\n"
                "    body: a function\n",
            )
        ]

        result = readiness(events, "customer")

        assert result.verdict == "incomplete"
        assert any("FR-01" in f for f in result.findings)

    def test_string_traces_raise_instead_of_yielding_a_false_verdict(self):
        events = [
            answer(
                "customer.functions.01",
                "product",
                "entries:\n"
                "  - id: G-01\n"
                "    body: a goal\n"
                "  - id: FR-01\n"
                "    body: a function\n"
                "    traces: '[G-01]'\n",
            )
        ]
        with pytest.raises(PayloadInvalid) as exc:
            render_brief(CUSTOMER, events, validation="pending")
        assert "FR-01" in str(exc.value)


class TestReadiness:
    def test_empty_transcript_is_incomplete_and_names_every_required_topic(self):
        result = readiness([], "customer")

        assert result.verdict == "incomplete"
        assert result.gate_passed is False
        assert len(result.findings) == 8
        assert any("goals" in f for f in result.findings)
        assert any("out_of_scope" in f for f in result.findings)

    def test_full_customer_brief_is_ready_with_no_findings(self):
        result = readiness([answer("q", "product", _ALL_REQUIRED_COVERED)], "customer")

        assert result.verdict == "ready"
        assert result.gate_passed is True
        assert result.findings == []

    def test_untraced_fr_is_named_by_id(self):
        payload = _ALL_REQUIRED_COVERED.replace("    traces: [G-01]\n", "", 1)
        result = readiness([answer("q", "product", payload)], "customer")

        assert result.verdict == "incomplete"
        assert any("FR-01" in f for f in result.findings)

    def test_blocking_open_question_is_named_by_id(self):
        payload = _ALL_REQUIRED_COVERED + (
            "  - id: Q-01\n"
            "    body: an unresolved question\n"
            "    owner_role: product\n"
            "    blocking: true\n"
        )
        result = readiness([answer("q", "product", payload)], "customer")

        assert result.verdict == "incomplete"
        assert any("Q-01" in f for f in result.findings)

    def test_findings_are_deterministic_across_calls(self):
        events = [answer("q", "product", "entries:\n  - id: G-01\n    body: a goal\n")]

        assert readiness(events, "customer").findings == (
            readiness(events, "customer").findings
        )

    def test_frontmatter_gate_passed_equals_the_readiness_verdict(self):
        events = [answer("q", "product", _ALL_REQUIRED_COVERED)]
        meta = _frontmatter(render_brief(CUSTOMER, events, validation="pending"))

        assert (
            meta["coverage"]["gate_passed"] is readiness(events, "customer").gate_passed
        )

    def test_engineer_frame_cannot_reach_ready_even_fully_populated(self):
        """Pins a known limitation, tracked as @id:feasibility-review-not-derived.

        `feasibility_review` is engineer's one required key with prefix
        `None` ("process, not a section" — FRAMES["engineer"]), and
        `_coverage` marks a key `covered` only when an entry's id-prefix
        matches. That key is therefore always `missing`, so `readiness` is
        always `incomplete` for the engineer frame, no matter how complete
        the transcript — every engineer run exits 11, never 0. This test
        exists so a future change to `_coverage` that silently fixes or
        worsens this moves a test; when @id:feasibility-review-not-derived
        (TODO.md) is fixed, delete this test.
        """
        payload = (
            "entries:\n"
            "  - id: S-01\n"
            "    body: current system assessment\n"
            "  - id: IF-01\n"
            "    body: an interface\n"
            "  - id: CON-01\n"
            "    body: a constraint\n"
            "  - id: AP-01\n"
            "    body: an architecture preference\n"
            "  - id: RK-01\n"
            "    body: a risk\n"
        )
        result = readiness([answer("q", "engineer", payload)], "engineer")

        assert result.verdict == "incomplete"
        assert any("feasibility_review" in f for f in result.findings)
