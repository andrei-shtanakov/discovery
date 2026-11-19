"""Journal-derived lifecycle — DESIGN-002/003/004.

Lifecycle is a pure function of the raw journal event list, never separate
storage: `issued`/`answered_ids` fold the journal, `next_question` restores an
already-issued question entirely from its own `question_asked` event (never
by re-resolving its id against the current `QuestionSource`), and
`compute_lifecycle` projects `next_question`, plus the §5 emptiness
precondition (an empty source is `unknown`, not `complete`).
"""

from __future__ import annotations

from discovery.questions import FEATURE, FULL, Question, QuestionSource

AWAITING_INPUT = "awaiting_input"
COMPLETE = "complete"
UNKNOWN = "unknown"


def issued(events: list[dict]) -> list[dict]:
    """One entry per distinct question_id from question_asked events, latest wins."""
    by_id: dict[str, dict] = {}
    for event in events:
        if event.get("event") == "question_asked":
            by_id[event["question_id"]] = event
    return list(by_id.values())


def answered_ids(events: list[dict]) -> set[str]:
    """question_ids with at least one answer_recorded event."""
    return {
        event["question_id"]
        for event in events
        if event.get("event") == "answer_recorded"
    }


def expansions(events: list[dict]) -> dict[str, bool]:
    """`filter question_id -> expand` from each question's latest answer.

    Latest, not first: `--supersede` of a filter answer re-decides whether
    its topic is expanded.
    """
    result: dict[str, bool] = {}
    for event in events:
        if event.get("event") != "answer_recorded":
            continue
        if "expand" in event:
            result[event["question_id"]] = event["expand"] is True
        else:
            result.pop(event["question_id"], None)
    return result


def planned(
    events: list[dict], source: QuestionSource, frame: str, profile: str = FULL
) -> list[Question]:
    """The bank's questions for `profile`, given the journal's filter answers."""
    if profile == FEATURE:
        return source.feature_questions(frame, expansions(events))
    return source.questions(frame)


def next_question(
    events: list[dict], source: QuestionSource, frame: str, profile: str = FULL
) -> Question | None:
    """Pending (issued, unanswered) questions are rebuilt from their own
    question_asked event — source.questions() is not consulted for them.
    Only the "nothing pending" branch reads the source, to find the first
    unissued question."""
    answered = answered_ids(events)
    for event in issued(events):
        if event["question_id"] not in answered:
            return Question(
                event["question_id"],
                event["coverage_key"],
                event["question_text"],
                is_filter=bool(event.get("is_filter")),
            )

    already_issued = {event["question_id"] for event in issued(events)}
    settled = already_issued | answered
    for question in planned(events, source, frame, profile):
        if question.question_id not in settled:
            return question

    return None


def compute_lifecycle(
    events: list[dict], source: QuestionSource, frame: str, profile: str = FULL
) -> str:
    """`awaiting_input` iff a next question exists.

    A pending (issued, unanswered) question outranks an empty source: it is
    checked first and, if found, always yields `awaiting_input`. Only once
    nothing is pending does an empty source catalogue yield `unknown` rather
    than `complete`.
    """
    if next_question(events, source, frame, profile) is not None:
        return AWAITING_INPUT
    if not source.questions(frame):
        return UNKNOWN
    return COMPLETE
