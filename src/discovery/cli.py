"""CLI over the core — DESIGN-009..DESIGN-018.

`start`/`status`/`answer`/`brief` are thin compositions over
`discovery.{journal,lifecycle,gate,protocol}`: this module owns only where
a session's files live (`sessions_root`/`_session_dir`/`_journal`) and how
to reach the question source (`build_source`) and the forge
(`build_forge`), never lifecycle/gate/coverage rules. `approve` is the
fifth command and the one that acts on a brief file rather than a session:
it mirrors a human merge onto the brief's approval envelope
(`discovery.approval`), the fact coming from a `Forge` and the allowlist
from `discovery.policy`. `_emit` is the single `print()` + `protocol.exit_code()`
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

from discovery import approval, policy, protocol, render
from discovery.approval import MergeEvent
from discovery.contract.gate_check import check, split_frontmatter
from discovery.forge import Forge, ForgeUnavailable
from discovery.gate import GateInvariantError, render_and_gate
from discovery.hashing import answer_id
from discovery.journal import (
    ANSWER_RECORDED,
    ANSWER_SUPERSEDED,
    QUESTION_ASKED,
    Journal,
    JournalUnreadable,
)
from discovery.lifecycle import AWAITING_INPUT, compute_lifecycle, next_question
from discovery.payload import AnswerPayload, PayloadInvalid, parse_payload
from discovery.policy import PolicyRefused
from discovery.protocol import Envelope
from discovery.questions import QuestionSource
from discovery.session import (
    InvalidSessionId,
    Session,
    SessionHeader,
    SessionUnreadable,
    write_artifact,
)
from discovery.upstream import UPSTREAM_NAME, UpstreamRejected, admit


class CallRefused(Exception):
    """The call's arguments do not cohere — nothing was read or written.

    Distinct from `UpstreamRejected`, which judges the *document*: this one
    judges the *call*. Both project to the same envelope — a call the
    runtime will not make is a call that decided nothing.
    """


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


def _pinned_commit() -> str:
    """The upstream commit pinned in `discovery/contract/PINNED.txt`."""
    pinned_txt = Path(__file__).resolve().parent / "contract" / "PINNED.txt"
    for line in pinned_txt.read_text(encoding="utf-8").splitlines():
        if line.startswith("commit:"):
            return line.removeprefix("commit:").strip()
    raise RuntimeError("PINNED.txt has no commit: line")


def build_source() -> QuestionSource:
    """Composition seam: a `BankQuestionSource` over the vendored frames,
    pinned to the commit recorded in `discovery/contract/PINNED.txt`."""
    from discovery.bank import BankQuestionSource

    frames_dir = Path(__file__).resolve().parent / "contract" / "frames"
    return BankQuestionSource(pin=_pinned_commit(), frames_dir=frames_dir)


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
    journal: Journal, header: SessionHeader, source: QuestionSource, session_id: str
) -> Envelope:
    """`_issue_if_needed` -> `compute_lifecycle` -> `render_and_gate`, one envelope.

    `session_id` is the CLI-validated id (not `header.session_id`, which is
    unvalidated content read back out of `header.json`), so the session
    directory used for the gate's `base_dir` can never be steered by a
    mismatched header field.
    """
    next_action = _issue_if_needed(journal, header, source)
    events = journal.events()
    lifecycle = compute_lifecycle(events, source, header.frame)
    result = render_and_gate(header, events, _session_dir(session_id))
    return protocol.ok(
        lifecycle=lifecycle,
        gate=result.status,
        readiness=result.readiness,
        next_action=next_action,
        findings=result.findings,
        readiness_findings=result.readiness_findings,
    )


def _emit(envelope: Envelope) -> int:
    """The only `print()` + `protocol.exit_code()` site."""
    print(envelope.to_json())
    return protocol.exit_code(envelope)


def _admit_upstream(args: argparse.Namespace) -> dict[str, str]:
    """`{UPSTREAM_NAME: text}` to seed the session with, or `{}`.

    Called before `Session.create`, so a source the runtime will not accept
    never leaves a session behind for an interview to be run in.
    """
    if args.upstream is None:
        return {}
    if args.frame != "engineer":
        raise CallRefused(
            f"--upstream applies to the engineer frame only, got {args.frame!r}"
        )
    if UPSTREAM_NAME in args.traces_to:
        raise CallRefused(
            f"--traces-to {UPSTREAM_NAME} is ambiguous with --upstream: "
            f"{UPSTREAM_NAME} is the name the admitted copy takes"
        )
    return {UPSTREAM_NAME: admit(Path(args.upstream))}


def cmd_start(args: argparse.Namespace) -> int:
    """Create a session, then emit its shared status envelope.

    An admitted upstream copy leads `traces_to`: `gate_check` takes the
    first resolvable ref as the upstream brief, so the copy has to precede
    whatever `--traces-to` passed.
    """
    source = build_source()
    files = _admit_upstream(args)
    # `is None`, not falsiness: an explicitly empty `--session-id` is a
    # caller that got its own write-ahead id wrong, and silently generating
    # one would hand back a session it never named.
    session_id = (
        f"s-{uuid.uuid4().hex[:12]}" if args.session_id is None else args.session_id
    )
    header = SessionHeader(
        session_id=session_id,
        frame=args.frame,
        target=args.target,
        traces_to=[*files, *args.traces_to],
        source_pin=source.pin,
        created_at=_now(),
    )
    try:
        session = Session.create(sessions_root(), header, files=files)
    except FileExistsError as exc:
        raise CallRefused(f"session id already in use: {session_id}") from exc
    journal = _journal(session.header.session_id)
    return _emit(
        _status_envelope(journal, session.header, source, session.header.session_id)
    )


def cmd_status(args: argparse.Namespace) -> int:
    """Load a session, then emit its shared status envelope."""
    source = build_source()
    session = Session.load(sessions_root(), args.session)
    journal = _journal(args.session)
    return _emit(_status_envelope(journal, session.header, source, args.session))


def _latest_answer(events: list[dict], question_id: str) -> dict | None:
    """The most recent `answer_recorded` event for `question_id`, if any."""
    matches = [
        e
        for e in events
        if e.get("event") == ANSWER_RECORDED and e.get("question_id") == question_id
    ]
    return matches[-1] if matches else None


def _refuse(
    journal: Journal,
    header: SessionHeader,
    source: QuestionSource,
    reason: str,
    session_id: str,
) -> Envelope:
    """A refusal envelope built from the current, unwritten-to journal state."""
    envelope = _status_envelope(journal, header, source, session_id)
    return protocol.refused(
        reason=reason,
        lifecycle=envelope.lifecycle,
        gate=envelope.gate,
        readiness=envelope.readiness,
        next_action=envelope.next_action,
        findings=envelope.findings,
        readiness_findings=envelope.readiness_findings,
    )


def _replacements(events: list[dict], target: str, payload: AnswerPayload) -> dict:
    """`replaces_entries` for an answer that re-declares ids another
    question's answer currently holds — recorded on the same
    `answer_recorded` event, never as a second append a crash could split
    off. The answer to `target` itself is left out: its previous version is
    what `answer_superseded` already records. Empty → no key at all.
    """
    holders = render.entry_holders(events)
    replaced = [
        {
            "entry_id": entry.eid,
            "previous_question_id": question_id,
            "previous_answer_id": previous_id,
        }
        for entry in payload.entries
        if (held := holders.get(entry.eid)) is not None
        for question_id, previous_id in [held]
        if question_id != target
    ]
    return {"replaces_entries": replaced} if replaced else {}


def cmd_answer(args: argparse.Namespace) -> int:
    """Resolve the target question, then no-op / refuse / record / supersede."""
    source = build_source()
    session = Session.load(sessions_root(), args.session)
    header = session.header
    journal = _journal(args.session)
    events = journal.events()

    target = args.question
    if target is None:
        pending = next_question(events, source, header.frame)
        target = pending.question_id if pending is not None else None
    if target is None:
        return _emit(
            _refuse(journal, header, source, protocol.NO_TARGET_QUESTION, args.session)
        )

    raw = (
        sys.stdin.read()
        if args.file == "-"
        else Path(args.file).read_text(encoding="utf-8")
    )
    payload = parse_payload(raw)

    new_id = answer_id(header.session_id, target, args.role, raw)
    existing = _latest_answer(events, target)
    record = {
        "event": ANSWER_RECORDED,
        "question_id": target,
        "participant_role": args.role,
        "answer_id": new_id,
        "payload": raw,
        **_replacements(events, target, payload),
    }

    if existing is None:
        journal.append(record)
    elif existing.get("answer_id") == new_id:
        pass
    elif not args.supersede:
        return _emit(
            _refuse(journal, header, source, protocol.ANSWER_CONFLICT, args.session)
        )
    else:
        journal.append(
            {
                "event": ANSWER_SUPERSEDED,
                "question_id": target,
                "answer_id": existing.get("answer_id"),
            }
        )
        journal.append(record)

    return _emit(_status_envelope(journal, header, source, args.session))


def _has_upstream(session_id: str) -> bool:
    """Whether this session admitted an upstream copy under `UPSTREAM_NAME`."""
    return (_session_dir(session_id) / UPSTREAM_NAME).is_file()


def cmd_brief(args: argparse.Namespace) -> int:
    """Render+gate into `args.out`, the one write outside the session root.

    The fixed copy name removes the ordinary collision between the upstream
    and the brief, but an arbitrary `--out` still permits the
    self-reference, so that one name is refused.
    """
    source = build_source()
    session = Session.load(sessions_root(), args.session)
    # Case-folded: on a case-insensitive filesystem `--out UPSTREAM.MD`
    # produces exactly the self-reference this refuses, because
    # `_resolve_ref("upstream.md", out_dir)` finds it all the same.
    if Path(args.out).name.lower() == UPSTREAM_NAME and _has_upstream(args.session):
        raise CallRefused(
            f"--out may not be named {UPSTREAM_NAME} for a session that admitted "
            "an upstream: the brief would become its own upstream, and the gate "
            "would check it against its own body"
        )
    journal = _journal(args.session)
    events = journal.events()
    result = render_and_gate(session.header, events, _session_dir(args.session))
    write_artifact(Path(args.out), result.text)
    lifecycle = compute_lifecycle(events, source, session.header.frame)
    next_action = (
        {}
        if lifecycle != AWAITING_INPUT
        else _issue_if_needed(journal, session.header, source)
    )
    return _emit(
        protocol.ok(
            lifecycle=lifecycle,
            gate=result.status,
            readiness=result.readiness,
            next_action=next_action,
            findings=result.findings,
            readiness_findings=result.readiness_findings,
        )
    )


def build_forge() -> Forge:
    """Composition seam: the `gh`-backed forge from the adapter package.

    Imported here and nowhere else in the core, so the process-launch
    capability enters through one named function a test can replace, the
    way `build_source` admits the question bank.
    """
    from discovery_forge.gh import GhForge

    return GhForge()


def _lint_brief(text: str, path: Path) -> tuple[str, list[str]]:
    """`(gate, findings)` of a brief file the runtime did not just render.

    Fenced like `upstream._lint`: the pinned linter on a foreign document
    may raise instead of finding, and a brief it cannot read is a failed
    gate, not a traceback.
    """
    try:
        findings = check(text, base_dir=path.parent)
    except Exception as exc:  # noqa: BLE001 — the pinned linter, on foreign input
        return "fail", [f"brief could not be linted ({type(exc).__name__}: {exc})"]
    errors = [str(f) for f in findings if f.level == "error"]
    return ("fail" if errors else "pass"), [str(f) for f in findings]


def _brief_envelope(text: str, path: Path, refusal: tuple[str, str] | None) -> Envelope:
    """The envelope `approve` emits over the brief as it is on disk.

    `lifecycle` is `complete`: a brief under approval is a finished
    interview. `gate` is the linter over the file; `readiness` mirrors the
    file's own `coverage.gate_passed`, since there is no journal here to
    re-derive it from — the linter's GC-11 already holds that claim to the
    body.
    """
    meta, _ = split_frontmatter(text)
    gate, findings = _lint_brief(text, path)
    coverage = meta.get("coverage") if isinstance(meta, dict) else None
    passed = isinstance(coverage, dict) and coverage.get("gate_passed") is True
    readiness = "ready" if passed else "incomplete"
    if refusal is None:
        return protocol.ok("complete", gate, readiness, findings=findings)
    reason, detail = refusal
    return protocol.refused(
        reason, "complete", gate, readiness, findings=findings, detail=detail
    )


def _merge_event(forge: Forge, repo: str, number: int) -> MergeEvent | tuple[str, str]:
    """The act to mirror, or the refusal that denies it.

    A merged PR whose event is missing a login, a time or a commit is not a
    refusal but an inability: an incomplete event can neither sign the
    brief nor be checked against it (devtools `merge_event`).
    """
    pr = forge.pull_request(repo, number)
    if pr.state != "MERGED":
        return protocol.PR_NOT_MERGED, f"PR {repo}#{number} is {pr.state}, not MERGED"
    missing = [
        name
        for name, value in (
            ("mergedBy.login", pr.merged_by),
            ("mergedAt", pr.merged_at),
            ("mergeCommit.oid", pr.merge_commit),
        )
        if not value
    ]
    if missing:
        raise ForgeUnavailable(
            f"PR {repo}#{number} is merged but the event is incomplete: "
            f"no {', '.join(missing)}"
        )
    return MergeEvent(str(pr.merged_by), str(pr.merged_at), str(pr.merge_commit))


def _brief_path_in_repo(args: argparse.Namespace) -> str:
    """The brief's path as the forge knows it: `--path`, else the path as
    given when relative — a caller at the repository root names the file
    the way git does. An absolute path names nothing in a repository."""
    if args.path is not None:
        return args.path
    given = Path(args.brief)
    if given.is_absolute():
        raise CallRefused(
            "--path is required when the brief is given by an absolute path: "
            "the repository-relative path cannot be inferred from it"
        )
    return given.as_posix()


def _denial(
    forge: Forge, args: argparse.Namespace, merge: MergeEvent, local: str
) -> tuple[str, str] | None:
    """Every fact that denies mirroring `merge` onto `local`, first one wins."""
    allowed = policy.allowlist(forge)
    if merge.login not in allowed:
        return (
            protocol.APPROVER_NOT_AUTHORIZED,
            f"merged by {merge.login!r}, not in the approver allowlist",
        )
    path = _brief_path_in_repo(args)
    if path not in forge.pull_request_files(args.repo, args.pr):
        return (
            protocol.BRIEF_NOT_IN_PR,
            f"PR {args.repo}#{args.pr} did not change {path}",
        )
    merged = forge.file_at(args.repo, merge.commit, path)
    if merged is None:
        return (
            protocol.BRIEF_NOT_IN_PR,
            f"{path} is not in merge commit {merge.commit}",
        )
    ours, theirs = approval.self_hash(local), approval.self_hash(merged)
    if ours != theirs:
        return (
            protocol.BRIEF_BYTES_DIVERGED,
            f"local {ours} != merged {theirs} at {merge.commit}",
        )
    return None


def cmd_approve(args: argparse.Namespace) -> int:
    """Mirror a human merge onto the brief's approval envelope.

    Read-only towards the forge, and the one write is the brief itself: the
    envelope is stamped only once the PR is merged, the merger is on the
    policy allowlist, the PR changed this file and the merged bytes are
    these bytes outside the envelope. A brief that claims `approved` while
    its bytes no longer match what was merged is returned to `draft` —
    the mirror reflects git, and git does not hold these bytes.
    """
    brief = Path(args.brief)
    local = brief.read_text(encoding="utf-8")
    try:
        approval.self_hash(local)
    except approval.NotABrief as exc:
        raise CallRefused(f"{brief}: {exc}") from exc
    forge = build_forge()
    merge = _merge_event(forge, args.repo, args.pr)
    refusal = merge if isinstance(merge, tuple) else _denial(forge, args, merge, local)
    if refusal is None:
        assert isinstance(merge, MergeEvent)
        text = approval.stamp(local, merge)
    elif refusal[0] == protocol.BRIEF_BYTES_DIVERGED:
        text = approval.withdraw(local)
    else:
        text = local
    if text != local:
        write_artifact(brief, text)
    return _emit(_brief_envelope(text, brief, refusal))


def _build_parser() -> argparse.ArgumentParser:
    """The five-command `argparse` surface (DESIGN-018 + `approve`)."""
    parser = argparse.ArgumentParser(prog="discovery")
    subparsers = parser.add_subparsers(required=True)

    start = subparsers.add_parser("start")
    start.add_argument("--frame", required=True, choices=["customer", "engineer"])
    start.add_argument("--target", required=True)
    start.add_argument("--traces-to", action="append", default=[])
    start.add_argument("--upstream")
    start.add_argument("--session-id")
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

    approve = subparsers.add_parser("approve")
    approve.add_argument("brief")
    approve.add_argument("--repo", required=True)
    approve.add_argument("--pr", required=True, type=int)
    approve.add_argument("--path")
    approve.set_defaults(func=cmd_approve)

    return parser


def main(argv: list[str] | None = None) -> int:
    """The single process-facing entry point."""
    parser = _build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except (
        SessionUnreadable,
        JournalUnreadable,
        PayloadInvalid,
        GateInvariantError,
        CallRefused,
        UpstreamRejected,
        InvalidSessionId,
        ForgeUnavailable,
        PolicyRefused,
        OSError,
        UnicodeDecodeError,
    ) as exc:
        return _emit(protocol.unknown(str(exc)))


if __name__ == "__main__":
    raise SystemExit(main())
