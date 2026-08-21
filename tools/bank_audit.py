"""Static audit of the vendored question bank (L3 spec §5).

Two products, both deterministic and both offline: a classification of every
question the runtime can issue, and a coverage report of which required keys
are claimed by which topics. No model runs here — a CI test may not reach the
network, and the number must be reproducible.

The classification is deliberately conservative. It is a tripwire on change,
not a verdict on wording: `tests/test_bank_audit.py` compares it against a
committed snapshot, so a re-pin that alters a question fails cheaply here
instead of surfacing inside an expensive benchmark run.
"""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from discovery.bank import BankQuestionSource, parse_frame  # noqa: E402

CATEGORIES = ("tag_question", "answer_menu", "presupposition", "advisory")

#: Leading by grammar: the question carries its own confirmation.
_TAG_RE = re.compile(
    r"(не так ли|правда ли|верно\?|согласны\?|правильно ли я понимаю|вы же)",
    re.IGNORECASE,
)

#: Leading by presupposition: the question asserts the fact it asks about.
_PRESUPPOSITION_RE = re.compile(
    r"(почему вы не |что мешает вам |когда вы наконец |почему до сих пор )",
    re.IGNORECASE,
)

#: A parenthetical listing candidate answers seeds the answer. A parenthetical
#: addressed to the interviewer does not — those open with an imperative, and
#: the list is pinned rather than inferred.
_PAREN_RE = re.compile(r"\(([^)]+)\)")
_INSTRUCTION_VERBS = (
    "иди",
    "проведи",
    "прогони",
    "спроси",
    "зафиксируй",
    "запиши",
    "сверься",
    "не записывай",
)


def classify(text: str) -> list[str]:
    """Return the categories `text` falls into, in `CATEGORIES` order."""
    found: list[str] = []
    if _TAG_RE.search(text):
        found.append("tag_question")
    if _is_answer_menu(text):
        found.append("answer_menu")
    if _PRESUPPOSITION_RE.search(text):
        found.append("presupposition")
    if "?" not in text:
        found.append("advisory")
    return found


def _is_answer_menu(text: str) -> bool:
    """A parenthetical enumerating ≥2 candidate answers, instructions aside."""
    for inner in _PAREN_RE.findall(text):
        stripped = inner.strip().lower()
        if stripped.startswith(_INSTRUCTION_VERBS):
            continue
        if inner.count(",") >= 1:
            return True
    return False


@dataclass(frozen=True)
class QuestionAudit:
    """One issued question and the categories it falls into."""

    question_id: str
    coverage_key: str
    categories: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class FrameAudit:
    """One frame: its issued questions, claimed keys, and unissued topics."""

    frame: str
    questions: list[QuestionAudit]
    claimed: dict[str, list[str]]
    unissued_topics: list[str]


def audit_frame(frame: str, frames_dir: Path) -> FrameAudit:
    """Classify `frame`'s issued questions and report its coverage claims."""
    source = BankQuestionSource(pin="audit", frames_dir=frames_dir)
    questions = [
        QuestionAudit(q.question_id, q.coverage_key, classify(q.text))
        for q in source.questions(frame)
    ]
    topics = parse_frame((frames_dir / f"{frame}.md").read_text(encoding="utf-8"))
    claimed = {
        topic.coverage_key: list(topic.produces)
        for topic in topics
        if topic.coverage_key is not None
    }
    unissued = [
        f"{len(topic.questions)} bullet(s) under a coverage_key: none topic"
        for topic in topics
        if topic.coverage_key is None and topic.questions
    ]
    return FrameAudit(frame, questions, claimed, unissued)
