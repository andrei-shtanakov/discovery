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

import argparse
import json
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


PINNED = (
    Path(__file__).resolve().parents[1]
    / "src"
    / "discovery"
    / "contract"
    / "PINNED.txt"
)


def snapshot(frames_dir: Path) -> dict:
    """JSON-able classification of both frames, plus the contract pin."""
    return {
        "pin": PINNED.read_text(encoding="utf-8").strip(),
        "frames": {
            frame: {
                "issued": len(audit.questions),
                "questions": {
                    q.question_id: q.categories for q in audit.questions if q.categories
                },
                "claimed": audit.claimed,
                "unissued_topics": audit.unissued_topics,
            }
            for frame in ("customer", "engineer")
            if (audit := audit_frame(frame, frames_dir))
        },
    }


def _report(frames_dir: Path) -> None:
    """Print the human-readable audit: coverage claims, then flagged questions."""
    for frame in ("customer", "engineer"):
        audit = audit_frame(frame, frames_dir)
        flagged = [q for q in audit.questions if q.categories]
        leading = [q for q in flagged if q.categories != ["advisory"]]
        print(f"\n=== {frame}: {len(audit.questions)} issued question(s)")
        print(f"    claimed keys: {', '.join(sorted(audit.claimed))}")
        for note in audit.unissued_topics:
            print(f"    never issued: {note}")
        advisory_only = len(flagged) - len(leading)
        print(f"    leading: {len(leading)}   advisory-only: {advisory_only}")
        for q in flagged:
            print(f"      {q.question_id}  [{', '.join(q.categories)}]")


def main() -> int:
    """Report the audit, or refresh the committed baseline snapshot."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--frames", type=Path, default=PINNED.parent / "frames")
    parser.add_argument("--emit-baseline", action="store_true")
    args = parser.parse_args()
    if args.emit_baseline:
        target = (
            Path(__file__).resolve().parents[1]
            / "tests"
            / "data"
            / "bank_audit_baseline.json"
        )
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            json.dumps(
                snapshot(args.frames), ensure_ascii=False, indent=2, sort_keys=True
            )
            + "\n",
            encoding="utf-8",
        )
        print(f"wrote {target}")
        return 0
    _report(args.frames)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
