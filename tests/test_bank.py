"""Tests for discovery.bank — TASK-003 (DESIGN-010)."""

from pathlib import Path

import pytest

from discovery.bank import (
    BankInvalid,
    BankQuestionSource,
    Topic,
    _validate,
    parse_frame,
)
from discovery.contract import gate_check

SYNTHETIC_CUSTOMER_FRAME = """# Frame: synthetic customer fixture

### 1. Goals
<!-- coverage_key: goals; produces: G -->
- What problem are we solving?
- Why now?

### 2. Personas
<!-- coverage_key: personas; produces: P -->
- Who uses this?

### 3. Jobs
<!-- coverage_key: jobs; produces: J -->
- What job needs doing?

### 4. Functions
<!-- coverage_key: functions; produces: FR -->
- What must it do?

### 5. NFR
<!-- coverage_key: nfr; produces: NFR -->
- How fast must it be?

### 6. Constraints
<!-- coverage_key: constraints; produces: CON -->
- What is the budget?

### 7. Success metrics
<!-- coverage_key: success_metrics; produces: M -->
- What number proves success?

### 8. Out of scope
<!-- coverage_key: out_of_scope; produces: OUT -->
- What is excluded?

### Closing
<!-- coverage_key: none; produces: X,Q -->
- Anything else we should ask?
"""


def _customer_topics_with(**overrides: list[str]) -> list[Topic]:
    """Build one Topic per required customer key, correct produces by default."""
    topics = []
    for key, prefix in gate_check.FRAMES["customer"]["required"].items():
        produces = overrides.get(key, [prefix])
        topics.append(Topic(coverage_key=key, produces=produces, questions=["q"]))
    return topics


def test_validate_raises_on_missing_required_key():
    topics = [t for t in _customer_topics_with() if t.coverage_key != "personas"]

    with pytest.raises(BankInvalid, match="personas"):
        _validate("customer", topics)


def test_validate_raises_on_produces_prefix_mismatch():
    topics = _customer_topics_with(goals=["X"])

    with pytest.raises(BankInvalid, match="goals"):
        _validate("customer", topics)


def test_bank_question_source_id_format_and_none_topic_excluded(tmp_path):
    (tmp_path / "customer.md").write_text(SYNTHETIC_CUSTOMER_FRAME, encoding="utf-8")
    source = BankQuestionSource(pin="test-pin", frames_dir=tmp_path)

    questions = source.questions("customer")

    ids = [q.question_id for q in questions]
    assert ids == [
        "customer.goals.01",
        "customer.goals.02",
        "customer.personas.01",
        "customer.jobs.01",
        "customer.functions.01",
        "customer.nfr.01",
        "customer.constraints.01",
        "customer.success_metrics.01",
        "customer.out_of_scope.01",
    ]
    assert all(not qid.startswith("customer.none") for qid in ids)
    assert "Anything else we should ask?" not in [q.text for q in questions]


def test_validate_raises_on_unknown_frame():
    with pytest.raises(BankInvalid, match="bogus"):
        _validate("bogus", [])


def test_validate_accepts_a_key_claimed_by_two_topics():
    """Contract v1.3: blocks 2 and 7 both close `functions` (discovery#74)."""
    topics = _customer_topics_with() + [
        Topic(coverage_key="functions", produces=["FR", "M", "Q"], questions=["q"])
    ]

    _validate("customer", topics)


def test_validate_accepts_secondary_produces_beside_the_section_prefix():
    _validate("customer", _customer_topics_with(out_of_scope=["OUT", "NFR"]))


def test_validate_raises_when_produces_lacks_the_section_prefix():
    with pytest.raises(BankInvalid, match="out_of_scope"):
        _validate("customer", _customer_topics_with(out_of_scope=["NFR"]))


def test_validate_raises_on_a_prefix_no_contract_section_knows():
    with pytest.raises(BankInvalid, match="ZZ"):
        _validate("customer", _customer_topics_with(goals=["G", "ZZ"]))


def test_question_ids_run_on_across_topics_of_one_key(tmp_path):
    """Two topics on one key must not mint the same question id twice."""
    frame = SYNTHETIC_CUSTOMER_FRAME.replace(
        "### Closing",
        "### 9. Acceptance\n"
        "<!-- coverage_key: functions; produces: FR,M -->\n"
        "- How do we accept it?\n"
        "- Who signs off?\n\n"
        "### Closing",
    )
    (tmp_path / "customer.md").write_text(frame, encoding="utf-8")

    questions = BankQuestionSource(pin="p", frames_dir=tmp_path).questions("customer")

    ids = [q.question_id for q in questions]
    assert len(ids) == len(set(ids))
    functions = [q for q in questions if q.coverage_key == "functions"]
    assert [q.question_id for q in functions] == [
        "customer.functions.01",
        "customer.functions.02",
        "customer.functions.03",
    ]
    assert functions[2].text == "Who signs off?"


def test_validate_raises_on_empty_produces_for_required_key():
    topics = _customer_topics_with(goals=[])

    with pytest.raises(BankInvalid, match="goals"):
        _validate("customer", topics)


def test_parse_frame_marker_tolerates_space_after_comma_in_produces():
    text = (
        "<!-- coverage_key: none; produces: X, Q -->\n"
        "- filler\n"
        "### Next\n"
        "<!-- coverage_key: goals; produces: G -->\n"
        "- What problem are we solving?\n"
    )

    topics = parse_frame(text)

    assert [t.coverage_key for t in topics] == [None, "goals"]
    assert topics[0].produces == ["X", "Q"]
    assert topics[1].questions == ["What problem are we solving?"]


def test_bank_question_source_raises_before_returning_partial_list(tmp_path):
    incomplete_frame = SYNTHETIC_CUSTOMER_FRAME.replace(
        "### 8. Out of scope\n"
        "<!-- coverage_key: out_of_scope; produces: OUT -->\n"
        "- What is excluded?\n\n",
        "",
    )
    (tmp_path / "customer.md").write_text(incomplete_frame, encoding="utf-8")
    source = BankQuestionSource(pin="test-pin", frames_dir=tmp_path)

    with pytest.raises(BankInvalid, match="out_of_scope"):
        source.questions("customer")


def test_bank_question_source_over_real_vendored_frames():
    frames_dir = (
        Path(__file__).resolve().parent.parent
        / "src"
        / "discovery"
        / "contract"
        / "frames"
    )
    source = BankQuestionSource(pin="real-pin", frames_dir=frames_dir)

    for frame in ("customer", "engineer"):
        questions = source.questions(frame)

        assert questions, f"{frame} produced no questions"
        assert all(q.question_id.startswith(f"{frame}.") for q in questions), (
            f"{frame} produced a question_id not prefixed '{frame}.'"
        )
