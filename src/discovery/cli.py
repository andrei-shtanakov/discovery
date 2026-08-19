"""CLI over the core — DESIGN-009..DESIGN-018.

`start`/`status`/`answer`/`brief` are thin compositions over
`discovery.{journal,lifecycle,gate,protocol}`: this module owns only where
a session's files live (`sessions_root`/`_session_dir`/`_journal`) and how
to reach the question source (`build_source`), never lifecycle/gate/
coverage rules. `_emit` is the single `print()` + `protocol.exit_code()`
site, so one envelope shape is physically impossible to diverge between
commands.
"""

from __future__ import annotations

import argparse
import datetime as dt
import os
import sys
import uuid
from pathlib import Path

from discovery import protocol
from discovery.gate import render_and_gate
from discovery.hashing import answer_id
from discovery.journal import (
    ANSWER_RECORDED,
    ANSWER_SUPERSEDED,
    QUESTION_ASKED,
    Journal,
    JournalUnreadable,
)
from discovery.lifecycle import AWAITING_INPUT, compute_lifecycle, next_question
from discovery.payload import PayloadInvalid, parse_payload
from discovery.protocol import Envelope
from discovery.questions import QuestionSource, StaticQuestionSource
from discovery.session import Session, SessionHeader, SessionUnreadable, write_artifact


def sessions_root() -> Path:
    """`$DISCOVERY_HOME/sessions`, defaulting to `~/.discovery/sessions`."""
    home = os.environ.get("DISCOVERY_HOME", str(Path.home() / ".discovery"))
    return Path(home) / "sessions"


def _session_dir(session_id: str) -> Path:
    """The on-disk directory for one session."""
    return sessions_root() / session_id


def _journal(session_id: str) -> Journal:
    """The journal bound to one session's `journal.jsonl`."""
    return Journal(_session_dir(session_id) / "journal.jsonl")


def build_source() -> QuestionSource:
    """Composition seam. D2 replaces the body with a bank-backed source."""
    return StaticQuestionSource(pin="unpinned", catalogue={})


def _now() -> str:
    """Current UTC time as an ISO-8601 string ending in "Z"."""
    return dt.datetime.now(dt.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _issue_if_needed(
    journal: Journal, header: SessionHeader, source: QuestionSource
) -> dict:
    """Persist `question_asked` before returning the pending question, if any."""
    events = journal.events()
    question = next_question(events, source, header.frame)
    if question is None:
        return {}
    if question.question_id not in {e.get("question_id") for e in events}:
        journal.append(
            {
                "event": QUESTION_ASKED,
                "question_id": question.question_id,
                "coverage_key": question.coverage_key,
                "question_text": question.text,
                "source_pin": source.pin,
            }
        )
    return {
        "session_id": header.session_id,
        "question_id": question.question_id,
        "coverage_key": question.coverage_key,
        "question_text": question.text,
    }


def _status_envelope(
    journal: Journal, header: SessionHeader, source: QuestionSource
) -> Envelope:
    """`_issue_if_needed` -> `compute_lifecycle` -> `render_and_gate`, one envelope."""
    next_action = _issue_if_needed(journal, header, source)
    events = journal.events()
    lifecycle = compute_lifecycle(events, source, header.frame)
    result = render_and_gate(header, events, _session_dir(header.session_id))
    return protocol.ok(lifecycle, result.status, next_action, result.findings)


def _emit(envelope: Envelope) -> int:
    """The only `print()` + `protocol.exit_code()` site."""
    print(envelope.to_json())
    return protocol.exit_code(envelope)


def cmd_start(args: argparse.Namespace) -> int:
    """Create a session, then emit its shared status envelope."""
    source = build_source()
    header = SessionHeader(
        session_id=f"s-{uuid.uuid4().hex[:12]}",
        frame=args.frame,
        target=args.target,
        traces_to=list(args.traces_to),
        source_pin=source.pin,
        created_at=_now(),
    )
    session = Session.create(sessions_root(), header)
    journal = _journal(session.header.session_id)
    return _emit(_status_envelope(journal, session.header, source))


def cmd_status(args: argparse.Namespace) -> int:
    """Load a session, then emit its shared status envelope."""
    source = build_source()
    session = Session.load(sessions_root(), args.session)
    journal = _journal(session.header.session_id)
    return _emit(_status_envelope(journal, session.header, source))


def _latest_answer(events: list[dict], question_id: str) -> dict | None:
    """The most recent `answer_recorded` event for `question_id`, if any."""
    matches = [
        e
        for e in events
        if e.get("event") == ANSWER_RECORDED and e.get("question_id") == question_id
    ]
    return matches[-1] if matches else None


def _refuse(
    journal: Journal, header: SessionHeader, source: QuestionSource, reason: str
) -> Envelope:
    """A refusal envelope built from the current, unwritten-to journal state."""
    envelope = _status_envelope(journal, header, source)
    return protocol.refused(
        reason,
        envelope.lifecycle,
        envelope.gate,
        envelope.next_action,
        envelope.findings,
    )


def cmd_answer(args: argparse.Namespace) -> int:
    """Resolve the target question, then no-op / refuse / record / supersede."""
    source = build_source()
    session = Session.load(sessions_root(), args.session)
    header = session.header
    journal = _journal(header.session_id)
    events = journal.events()

    target = args.question
    if target is None:
        pending = next_question(events, source, header.frame)
        target = pending.question_id if pending is not None else None
    if target is None:
        return _emit(_refuse(journal, header, source, protocol.NO_TARGET_QUESTION))

    raw = (
        sys.stdin.read()
        if args.file == "-"
        else Path(args.file).read_text(encoding="utf-8")
    )
    parse_payload(raw)

    new_id = answer_id(header.session_id, target, args.role, raw)
    existing = _latest_answer(events, target)

    if existing is None:
        journal.append(
            {
                "event": ANSWER_RECORDED,
                "question_id": target,
                "participant_role": args.role,
                "answer_id": new_id,
                "payload": raw,
            }
        )
    elif existing.get("answer_id") == new_id:
        pass
    elif not args.supersede:
        return _emit(_refuse(journal, header, source, protocol.ANSWER_CONFLICT))
    else:
        journal.append(
            {
                "event": ANSWER_SUPERSEDED,
                "question_id": target,
                "answer_id": existing.get("answer_id"),
            }
        )
        journal.append(
            {
                "event": ANSWER_RECORDED,
                "question_id": target,
                "participant_role": args.role,
                "answer_id": new_id,
                "payload": raw,
            }
        )

    return _emit(_status_envelope(journal, header, source))


def cmd_brief(args: argparse.Namespace) -> int:
    """Render+gate into `args.out`, the one write outside the session root."""
    source = build_source()
    session = Session.load(sessions_root(), args.session)
    journal = _journal(session.header.session_id)
    events = journal.events()
    result = render_and_gate(
        session.header, events, _session_dir(session.header.session_id)
    )
    write_artifact(Path(args.out), result.text)
    lifecycle = compute_lifecycle(events, source, session.header.frame)
    next_action = (
        {}
        if lifecycle != AWAITING_INPUT
        else _issue_if_needed(journal, session.header, source)
    )
    return _emit(protocol.ok(lifecycle, result.status, next_action, result.findings))


def _build_parser() -> argparse.ArgumentParser:
    """The four-command `argparse` surface (DESIGN-018)."""
    parser = argparse.ArgumentParser(prog="discovery")
    subparsers = parser.add_subparsers(required=True)

    start = subparsers.add_parser("start")
    start.add_argument("--frame", required=True, choices=["customer", "engineer"])
    start.add_argument("--target", required=True)
    start.add_argument("--traces-to", action="append", default=[])
    start.set_defaults(func=cmd_start)

    status = subparsers.add_parser("status")
    status.add_argument("--session", required=True)
    status.set_defaults(func=cmd_status)

    answer = subparsers.add_parser("answer")
    answer.add_argument("--session", required=True)
    answer.add_argument("--role", required=True)
    answer.add_argument("--file", required=True)
    answer.add_argument("--question")
    answer.add_argument("--supersede", action="store_true")
    answer.set_defaults(func=cmd_answer)

    brief = subparsers.add_parser("brief")
    brief.add_argument("--session", required=True)
    brief.add_argument("--out", required=True)
    brief.set_defaults(func=cmd_brief)

    return parser


def main(argv: list[str] | None = None) -> int:
    """The single process-facing entry point."""
    parser = _build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except (SessionUnreadable, JournalUnreadable, PayloadInvalid, OSError) as exc:
        return _emit(protocol.unknown(str(exc)))


if __name__ == "__main__":
    raise SystemExit(main())
