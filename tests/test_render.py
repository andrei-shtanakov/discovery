"""Tests for discovery.render — TASK-009."""

from dataclasses import dataclass, field

import yaml

from discovery.render import render_brief


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

        assert "## Functional requirements" in text
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
