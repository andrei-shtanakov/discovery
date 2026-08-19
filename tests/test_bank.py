"""Tests for discovery.bank — TASK-003 (DESIGN-010)."""

from pathlib import Path

import pytest

from discovery.bank import BankInvalid, BankQuestionSource, Topic, _validate
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
    assert ids[0] == "customer.goals.01"
    assert ids[1] == "customer.goals.02"
    assert ids[2] == "customer.personas.01"
    assert all(not qid.startswith("customer.none") for qid in ids)
    assert "Anything else we should ask?" not in [q.text for q in questions]


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
