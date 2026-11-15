"""Marker-driven question bank parser — DESIGN-006, DESIGN-007, DESIGN-008,
DESIGN-009.

Topics and their `coverage_key`/`produces` come from an explicit HTML marker
placed above the topic, never from the heading text next to it, so the bank
stays checkable against `gate_check.FRAMES` instead of guessing at headings.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from discovery.contract import gate_check
from discovery.questions import Question

MARKER_RE = re.compile(r"<!--\s*coverage_key:\s*(\S+);\s*produces:\s*([\w,\s]*)\s*-->")
_HEADING_RE = re.compile(r"^#{1,6}\s")


@dataclass(frozen=True)
class Topic:
    """One bank topic: its coverage key, claimed produces prefixes, questions."""

    coverage_key: str | None
    produces: list[str]
    questions: list[str]


class BankInvalid(Exception):
    """Frame fails fail-closed coverage validation against `gate_check.FRAMES`."""


def parse_frame(text: str) -> list[Topic]:
    """Line-scan `text` into marker-delimited `Topic`s (DESIGN-007).

    A topic opens only at a `coverage_key` marker; the heading that follows
    it is ignored as a data source. Any heading line (any level) closes the
    currently open topic before that heading line is otherwise processed.
    """
    topics: list[Topic] = []
    coverage_key: str | None = None
    produces: list[str] = []
    questions: list[str] = []
    open_topic = False

    def close_topic() -> None:
        nonlocal open_topic
        if open_topic:
            topics.append(
                Topic(
                    coverage_key=coverage_key,
                    produces=produces,
                    questions=questions,
                )
            )
            open_topic = False

    for line in text.splitlines():
        marker = MARKER_RE.match(line.strip())
        if marker:
            close_topic()
            key = marker.group(1)
            coverage_key = None if key == "none" else key
            produces = (
                [p.strip() for p in marker.group(2).split(",") if p.strip()]
                if marker.group(2).strip()
                else []
            )
            questions = []
            open_topic = True
            continue
        if _HEADING_RE.match(line):
            close_topic()
            continue
        if not open_topic:
            continue
        if line.startswith("- "):
            questions.append(line.strip()[2:])
            continue
        stripped = line.strip()
        if stripped and line.startswith("  ") and questions:
            questions[-1] = f"{questions[-1]} {stripped}"
    close_topic()
    return topics


# Prefixes legal in `produces` of a frame: that frame's own sections plus the
# Q/X invariants every topic may raise. Stricter than upstream's
# `test_frames_markers.ALLOWED_PREFIXES`, which unions both frames: a
# customer topic producing `S`/`IF`/`AP` would leak solution space into a
# problem-space brief, and the brief-level GC-14 is only a warning.
_INVARIANT_PREFIXES = {"Q", "X"}


def _allowed_prefixes(frame: str) -> set[str]:
    """`frame`'s section prefixes plus the Q/X invariants."""
    frame_def = gate_check.FRAMES[frame]
    sections = {**frame_def["required"], **frame_def["optional"]}
    return _INVARIANT_PREFIXES | {p for p in sections.values() if p}


def _validate(frame: str, topics: list[Topic]) -> None:
    """Raise `BankInvalid` if `frame`'s required coverage is unreachable
    (DESIGN-008).

    One key may be claimed by several topics (contract v1.3: blocks 2 and 7
    both close `functions`). Each topic of a key with a section must list
    that section's prefix among its `produces`; further prefixes are allowed
    as long as the frame itself has those sections. A required key whose
    upstream value is `None` (engineer's `feasibility_review`) names a
    process, not a section, so it has no prefix to demand.
    """
    if frame not in gate_check.FRAMES:
        raise BankInvalid(f"unknown frame {frame!r}")
    coverage = gate_check.FRAMES[frame]
    claimed = {t.coverage_key for t in topics if t.coverage_key is not None}
    missing = set(coverage["required"]) - claimed
    if missing:
        raise BankInvalid(
            f"frame {frame!r} missing required coverage key(s): {sorted(missing)}"
        )
    sections = {**coverage["required"], **coverage["optional"]}
    for topic in topics:
        if topic.coverage_key is None:
            continue
        unknown = sorted(set(topic.produces) - _allowed_prefixes(frame))
        if unknown:
            raise BankInvalid(
                f"topic {topic.coverage_key!r} in frame {frame!r} "
                f"produces unknown prefix(es) {unknown}"
            )
        section = sections.get(topic.coverage_key)
        if section is not None and section not in topic.produces:
            raise BankInvalid(
                f"topic {topic.coverage_key!r} in frame {frame!r} "
                f"produces {topic.produces}, missing its section prefix "
                f"{section!r}"
            )


class BankQuestionSource:
    """`QuestionSource` backed by marker-parsed, coverage-validated frame
    files (DESIGN-009)."""

    def __init__(self, pin: str, frames_dir: Path) -> None:
        """Store the provenance pin and the directory holding `<frame>.md` files."""
        self._pin = pin
        self._frames_dir = frames_dir

    @property
    def pin(self) -> str:
        """Return exactly the pin this source was constructed with."""
        return self._pin

    def questions(self, frame: str) -> list[Question]:
        """Validate `frame`'s coverage, then return its questions in order.

        `_validate` runs before any result is built, so a `BankInvalid`
        frame never returns a partial list.
        """
        text = (self._frames_dir / f"{frame}.md").read_text(encoding="utf-8")
        topics = parse_frame(text)
        _validate(frame, topics)
        result: list[Question] = []
        # Numbering runs on per key, not per topic: a key claimed by two
        # topics would otherwise mint `functions.01` twice.
        issued: dict[str, int] = {}
        for topic in topics:
            key = topic.coverage_key
            if key is None:
                continue
            for question_text in topic.questions:
                issued[key] = issued.get(key, 0) + 1
                result.append(
                    Question(
                        question_id=f"{frame}.{key}.{issued[key]:02d}",
                        coverage_key=key,
                        text=question_text,
                    )
                )
        return result
