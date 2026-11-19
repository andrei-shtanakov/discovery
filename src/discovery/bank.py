"""Marker-driven question bank parser — DESIGN-006, DESIGN-007, DESIGN-008,
DESIGN-009.

Topics and their `coverage_key`/`produces` come from an explicit HTML marker
placed above the topic, never from the heading text next to it, so the bank
stays checkable against `gate_check.FRAMES` instead of guessing at headings.

Contract v1.4 adds a second marker right under a topic's: the feature
profile line `<!-- profile: feature; short: <N,...|none>[; filter: <q>] -->`
(grammar: toolkit SKILL.md, appendix). It names the topic's questions asked
in the `feature` profile and an optional yes/no filter asked first.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from discovery.contract import gate_check
from discovery.questions import Question

FILTER = "filter"

MARKER_RE = re.compile(r"<!--\s*coverage_key:\s*(\S+);\s*produces:\s*([\w,\s]*)\s*-->")
_HEADING_RE = re.compile(r"^#{1,6}\s")
# Any profile line at all, so a malformed one is refused rather than skipped.
_PROFILE_ANY_RE = re.compile(r"<!--\s*profile:")
_PROFILE_RE = re.compile(
    r"<!--\s*profile:\s*feature;\s*short:\s*(none|\d+(?:\s*,\s*\d+)*)\s*"
    r"(?:;\s*filter:\s*([^;]*?\S)\s*)?-->$"
)


@dataclass(frozen=True)
class Topic:
    """One bank topic: its coverage key, claimed produces prefixes, questions."""

    coverage_key: str | None
    produces: list[str]
    questions: list[str]
    # Feature profile line: `None` — the topic has none; `()` — `short: none`.
    short: tuple[int, ...] | None = None
    filter: str | None = None


class BankInvalid(Exception):
    """Frame fails fail-closed coverage validation against `gate_check.FRAMES`."""


def parse_frame(text: str) -> list[Topic]:
    """Line-scan `text` into marker-delimited `Topic`s (DESIGN-007).

    A topic opens only at a `coverage_key` marker; the heading that follows
    it is ignored as a data source. Any heading line (any level) closes the
    currently open topic before that heading line is otherwise processed.

    A profile line is legal only directly under a keyed topic's marker; a
    misplaced, repeated or malformed one raises `BankInvalid`.
    """
    topics: list[Topic] = []
    coverage_key: str | None = None
    produces: list[str] = []
    questions: list[str] = []
    short: tuple[int, ...] | None = None
    filter_text: str | None = None
    open_topic = False
    just_opened = False

    def close_topic() -> None:
        nonlocal open_topic
        if open_topic:
            topics.append(
                Topic(
                    coverage_key=coverage_key,
                    produces=produces,
                    questions=questions,
                    short=short,
                    filter=filter_text,
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
            short, filter_text = None, None
            open_topic = True
            just_opened = True
            continue
        if _PROFILE_ANY_RE.match(line.strip()):
            if not (just_opened and coverage_key is not None):
                raise BankInvalid(f"profile line not under a keyed topic: {line!r}")
            short, filter_text = _parse_profile(line.strip())
            just_opened = False
            continue
        just_opened = False
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


def _parse_profile(line: str) -> tuple[tuple[int, ...], str | None]:
    """`(short, filter)` of one feature profile line, or `BankInvalid`."""
    match = _PROFILE_RE.match(line)
    if match is None:
        raise BankInvalid(f"malformed profile line: {line!r}")
    raw_short, filter_text = match.groups()
    if raw_short == "none":
        return (), filter_text
    return tuple(int(n) for n in raw_short.split(",")), filter_text


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
        frame never returns a partial list. Profile lines are ignored: this
        is the `full` profile.
        """
        return [q for _, q in self._numbered(frame) if not q.is_filter]

    def feature_questions(
        self, frame: str, expansions: Mapping[str, bool]
    ) -> list[Question]:
        """The `feature` profile's questions in order (contract v1.4).

        A topic with a filter yields the filter first; nothing more of the
        topic until `expansions` holds its answer — `True` yields the whole
        topic, `False` its `short` questions. A topic without a filter
        yields its `short` questions. Ids are the `full` ids, so a question
        is the same question in either profile.
        """
        numbered = self._numbered(frame)
        _validate_feature(frame, [t for t, _ in numbered])
        short_ids = _short_ids(numbered)
        # The filter's answer, per topic; a topic without a filter is absent.
        answer: dict[int, bool | None] = {
            id(t): expansions.get(q.question_id) for t, q in numbered if q.is_filter
        }
        result: list[Question] = []
        for topic, question in numbered:
            expanded = answer.get(id(topic), False)
            if question.is_filter:
                result.append(question)
            elif expanded is None:
                continue  # filter not answered yet: the topic waits for it
            elif expanded or question.question_id in short_ids:
                result.append(question)
        return result

    def _numbered(self, frame: str) -> list[tuple[Topic, Question]]:
        """Every keyed topic's filter and questions, paired with the topic.

        Numbering runs on per key, not per topic: a key claimed by two
        topics would otherwise mint `functions.01` twice. Filters number
        apart (`<key>.filterNN`) so the question ids stay those of `full`.
        """
        text = (self._frames_dir / f"{frame}.md").read_text(encoding="utf-8")
        topics = parse_frame(text)
        _validate(frame, topics)
        result: list[tuple[Topic, Question]] = []
        issued: dict[str, int] = {}
        filters: dict[str, int] = {}
        for topic in topics:
            key = topic.coverage_key
            if key is None:
                continue
            if topic.filter is not None:
                filters[key] = filters.get(key, 0) + 1
                filter_question = Question(
                    question_id=f"{frame}.{key}.{FILTER}{filters[key]:02d}",
                    coverage_key=key,
                    text=topic.filter,
                    is_filter=True,
                )
                result.append((topic, filter_question))
            for question_text in topic.questions:
                issued[key] = issued.get(key, 0) + 1
                question = Question(
                    question_id=f"{frame}.{key}.{issued[key]:02d}",
                    coverage_key=key,
                    text=question_text,
                )
                result.append((topic, question))
        return result


def _short_ids(numbered: list[tuple[Topic, Question]]) -> set[str]:
    """Ids of the questions every topic's `short` names (1-based, in-topic)."""
    own: dict[int, list[Question]] = {}
    shorts: dict[int, tuple[int, ...]] = {}
    for topic, question in numbered:
        if not question.is_filter:
            own.setdefault(id(topic), []).append(question)
            shorts[id(topic)] = topic.short or ()
    return {
        own[key][n - 1].question_id for key, numbers in shorts.items() for n in numbers
    }


def _validate_feature(frame: str, topics: list[Topic]) -> None:
    """Raise `BankInvalid` unless `frame`'s bank can run the `feature` profile.

    Mirrors the toolkit's marker invariants: the profile is customer-only,
    every keyed topic has a profile line, `short` numbers exist and ascend,
    `short: none` needs a filter, and every required key is reachable.
    """
    if frame != "customer":
        raise BankInvalid(f"profile 'feature' is customer-only, got {frame!r}")
    reachable: set[str] = set()
    for topic in topics:
        key = topic.coverage_key
        if key is None:
            continue
        if topic.short is None:
            raise BankInvalid(f"topic {key!r} has no feature profile line")
        if list(topic.short) != sorted(set(topic.short)) or not all(
            1 <= n <= len(topic.questions) for n in topic.short
        ):
            raise BankInvalid(
                f"topic {key!r}: short {list(topic.short)} is not ascending "
                f"numbers within its {len(topic.questions)} question(s)"
            )
        if not topic.short and topic.filter is None:
            raise BankInvalid(f"topic {key!r}: 'short: none' without a filter")
        reachable.add(key)
    missing = set(gate_check.FRAMES[frame]["required"]) - reachable
    if missing:
        raise BankInvalid(f"feature profile misses required key(s): {sorted(missing)}")
