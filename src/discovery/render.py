"""render_brief — journal to a contract-shaped brief (DESIGN-005).

Pure function of `(header, events, validation, findings)`: frontmatter, coverage
and body are all derived from `SessionHeader` and the journal's *latest*
answers; `validation` is the one fact the caller supplies and this module never
infers or predicts (DESIGN-P3). Superseded answers are excluded structurally —
`_latest_answers` folds `answer_recorded` events by `question_id` the same way
`issued()` folds `question_asked` (DESIGN-002): last write wins, so a
superseded answer's entries never reach `_entries()` and never reach the body.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

import yaml

from discovery.contract.gate_check import FRAMES
from discovery.payload import PayloadInvalid

# Section headings follow the contract's §2 table, not this module's taste:
# `J` is "Jobs-to-be-done" and `X` is "Stakeholder Conflicts" there, and a brief
# that renames them is navigable only by whoever wrote the renderer. The linter
# does not parse these headings (`_DEF_RE` finds entries, `_HEADING_RE` only
# closes a block), so nothing here is load-bearing for the gate — which is
# exactly why it drifted unnoticed until a human read the output.
SECTION_TITLES = {
    "G": "Goals",
    "P": "Personas",
    "J": "Jobs-to-be-done",
    "FR": "Functional Requirements",
    "NFR": "Non-Functional",
    "CON": "Constraints",
    "M": "Success Metrics",
    "OUT": "Out of Scope",
    "S": "System Assessment",
    "IF": "Interfaces",
    "AP": "Architecture Preferences",
    "RK": "Risks",
    "Q": "Open Questions",
    "X": "Stakeholder Conflicts",
}

_SECTION_ORDER = list(SECTION_TITLES)

_LABELLED_FIELDS = {
    "priority": "Priority",
    "acceptance": "Acceptance",
    "target": "Target",
    "category": "Category",
}


class SessionHeaderLike(Protocol):
    """The subset of `SessionHeader` (WS-B) `render_brief` reads."""

    frame: str
    target: str
    traces_to: list[str]
    created_at: str


GENERATED_BY = "discovery-runtime"


@dataclass(frozen=True)
class Entry:
    """One typed entry parsed from an answer payload's `entries` list."""

    eid: str
    body: str
    fields: dict[str, Any]

    @property
    def prefix(self) -> str:
        return self.eid.rsplit("-", 1)[0]


def _latest_answers(events: list[dict]) -> list[dict]:
    """One entry per distinct question_id from answer_recorded events, latest wins."""
    by_id: dict[str, dict] = {}
    for event in events:
        if event.get("event") == "answer_recorded":
            by_id[event["question_id"]] = event
    return list(by_id.values())


def _parse_payload(payload: str) -> dict[str, Any]:
    loaded = yaml.safe_load(payload)
    return loaded if isinstance(loaded, dict) else {}


def _entries(events: list[dict]) -> list[Entry]:
    """Typed entries from every latest answer's payload, in answer order."""
    entries: list[Entry] = []
    for answer in _latest_answers(events):
        parsed = _parse_payload(answer.get("payload", ""))
        for raw in parsed.get("entries") or []:
            fields = {k: v for k, v in raw.items() if k not in ("id", "body")}
            entries.append(
                Entry(eid=raw["id"], body=raw.get("body", ""), fields=fields)
            )
    return entries


def _sessions(events: list[dict]) -> list[dict[str, str]]:
    """One session per distinct participant_role among latest answers, first-seen."""
    seen: dict[str, None] = {}
    for answer in _latest_answers(events):
        role = answer.get("participant_role")
        if role is not None:
            seen[role] = None
    return [{"participant_role": role} for role in seen]


def _coverage(entries: list[Entry], frame: str) -> dict[str, str]:
    """`covered` iff >=1 entry's id-prefix matches the key's FRAMES[frame] prefix."""
    frame_def = FRAMES[frame]
    section_map = {**frame_def["required"], **frame_def["optional"]}
    prefixes_present = {e.prefix for e in entries}
    # engineer's required `feasibility_review` has prefix None ("process, not
    # a section"), so this always reads "missing" — structurally unreachable
    # until @id:feasibility-review-not-derived (TODO.md) is fixed.
    return {
        key: "covered"
        if prefix is not None and prefix in prefixes_present
        else "missing"
        for key, prefix in section_map.items()
    }


def _traces_of(entry: Entry) -> list[str]:
    """The entry's `traces` as ids, refusing any other type.

    A string is not a one-element list: iterating `"[J-02, G-01]"` yields
    characters, two of which survive the G/J prefix filter and match no id,
    so the old code answered `False` where it knew nothing. §7 forbids that
    trade — an undeterminable axis is `unknown`, never a guess.
    """
    raw = entry.fields.get("traces")
    if raw is None:
        return []
    if not isinstance(raw, list):
        raise PayloadInvalid(
            f"{entry.eid}: 'traces' must be a YAML list, got "
            f"{type(raw).__name__}: {raw!r}"
        )
    return [str(t) for t in raw]


READY = "ready"
INCOMPLETE = "incomplete"


@dataclass(frozen=True)
class ReadinessResult:
    """The §4 coverage-gate verdict plus the clauses that failed it.

    The one source of both the brief's `gate_passed` and the protocol's
    `readiness` axis (§6, §7): a caller that needs the verdict receives this
    object, never a second evaluation of the formula.
    """

    verdict: str
    findings: list[str]

    @property
    def gate_passed(self) -> bool:
        return self.verdict == READY


def readiness(events: list[dict], frame: str) -> ReadinessResult:
    """`gate_passed` (contract §4), mirrored rather than predicted.

    The events-level entry point. A caller that has already parsed the
    transcript into entries uses `_readiness_of` instead, so the payload
    YAML is parsed once per render pass rather than twice.
    """
    return _readiness_of(_entries(events), frame)


def _readiness_of(entries: list[Entry], frame: str) -> ReadinessResult:
    """The §4 formula over already-parsed entries, with the failed clauses
    named in a deterministic order: uncovered required topics in frame
    order, then untraced FRs and blocking open questions in answer order."""
    coverage = _coverage(entries, frame)
    ids = {e.eid for e in entries}
    findings: list[str] = []

    for key in FRAMES[frame]["required"]:
        if coverage.get(key) != "covered":
            findings.append(f"required topic {key!r} is not covered")

    for entry in entries:
        if entry.prefix != "FR":
            continue
        targets = _traces_of(entry)
        matched = [t for t in targets if t.split("-", 1)[0] in ("G", "J")]
        if not matched or any(t not in ids for t in matched):
            findings.append(f"{entry.eid} has no trace to an existing G/J entry")

    for entry in _blocking_open(entries):
        findings.append(f"{entry.eid} is a blocking open question")

    return ReadinessResult(verdict=INCOMPLETE if findings else READY, findings=findings)


def _is_true(value: Any) -> bool:
    return value is True


def _blocking_open(entries: list[Entry]) -> list[Entry]:
    """Open `Q` entries marked `blocking` and not yet `resolved` — the §4
    blocking-open-question clause. Shared by `render_brief`'s GC-10 counters
    and `readiness`'s verdict so the rule is expressed once, not twice."""
    return [
        e
        for e in entries
        if e.prefix == "Q"
        and not _is_true(e.fields.get("resolved"))
        and _is_true(e.fields.get("blocking"))
    ]


def _format_field_value(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, list):
        return "[" + ", ".join(str(v) for v in value) + "]"
    return str(value)


def _render_entry(entry: Entry) -> str:
    lines = [f"- **{entry.eid}** {entry.body}"]
    for key, value in entry.fields.items():
        label = _LABELLED_FIELDS.get(key.lower())
        formatted = _format_field_value(value)
        if label is not None:
            lines.append(f"  **{label}**: {formatted}")
        else:
            lines.append(f"  {key}: {formatted}")
    return "\n".join(lines)


def _render_body(entries: list[Entry]) -> str:
    sections: list[str] = []
    for prefix in _SECTION_ORDER:
        section_entries = [e for e in entries if e.prefix == prefix]
        if not section_entries:
            continue
        block = [f"## {SECTION_TITLES[prefix]}", ""]
        block.extend(_render_entry(e) for e in section_entries)
        sections.append("\n".join(block))
    return "\n\n".join(sections)


def _render_findings(findings: list[str]) -> str:
    # A leading heading line closes the last body entry in `gate_check`'s
    # parser (which otherwise has no signal that the body has ended), so the
    # comment's own text can never be folded into — and corrupt — a real
    # entry's regex-parsed fields (status/blocking/traces/...).
    lines = (
        ["## Gate findings", "", "<!-- gate findings:"]
        + [f"- {f}" for f in findings]
        + ["-->"]
    )
    return "\n\n" + "\n".join(lines)


def render_brief(
    header: SessionHeaderLike,
    events: list[dict],
    validation: str,
    findings: list[str] | None = None,
) -> str:
    """Derive the entire brief — frontmatter and body — from `header`/`events`.

    `validation` is written verbatim into the frontmatter; it is never
    inferred or computed here (DESIGN-P3) — that is `render_and_gate`'s job.
    """
    frame = header.frame
    entries = _entries(events)
    coverage = _coverage(entries, frame)
    open_questions = [
        e for e in entries if e.prefix == "Q" and not _is_true(e.fields.get("resolved"))
    ]
    blocking_open_questions = _blocking_open(entries)
    conflicts = [
        e for e in entries if e.prefix == "X" and e.fields.get("status") == "open"
    ]

    meta: dict[str, Any] = {
        "schema": "discovery-brief",
        "schema_version": 1,
        "spec_stage": "discovery",
        "status": "draft",
        "generated_by": GENERATED_BY,
        "generated_at": header.created_at,
        "validation": validation,
        "interview": {"frame": frame, "sessions": _sessions(events)},
        "coverage": {
            **coverage,
            # `entries` is already parsed here; going through the
            # events-level `readiness()` would re-parse every payload.
            "gate_passed": _readiness_of(entries, frame).gate_passed,
        },
        "open_questions": len(open_questions),
        "blocking_open_questions": len(blocking_open_questions),
        "conflicts": len(conflicts),
        "traces_to": list(header.traces_to),
    }

    frontmatter = yaml.safe_dump(meta, sort_keys=False, allow_unicode=True)
    title = f"# Discovery Brief — {header.target} ({frame}-фрейм)"
    text = f"---\n{frontmatter}---\n\n{title}\n\n{_render_body(entries)}"
    if findings:
        text += _render_findings(findings)
    return text
