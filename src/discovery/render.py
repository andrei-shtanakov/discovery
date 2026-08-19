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

SECTION_TITLES = {
    "G": "Goals",
    "P": "Personas",
    "J": "Jobs",
    "FR": "Functional requirements",
    "NFR": "Non-functional requirements",
    "CON": "Constraints",
    "M": "Success metrics",
    "OUT": "Out of scope",
    "S": "Systems",
    "IF": "Interfaces",
    "AP": "Architecture preferences",
    "RK": "Risks",
    "Q": "Open questions",
    "X": "Conflicts",
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
    traces_to: list[str]


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
    return {
        key: "covered"
        if prefix is not None and prefix in prefixes_present
        else "missing"
        for key, prefix in section_map.items()
    }


def _fr_all_traced(entries: list[Entry]) -> bool:
    """Every FR entry traces to at least one existing G/J entry (GC-06 mirror)."""
    ids = {e.eid for e in entries}
    fr_entries = [e for e in entries if e.prefix == "FR"]
    if not fr_entries:
        return True
    for entry in fr_entries:
        targets = [str(t) for t in (entry.fields.get("traces") or [])]
        matched = [t for t in targets if t.split("-", 1)[0] in ("G", "J")]
        if not matched or any(t not in ids for t in matched):
            return False
    return True


def _gate_passed(coverage: dict[str, str], entries: list[Entry], frame: str) -> bool:
    """`gate_passed` formula (contract §4), mirrored rather than predicted."""
    frame_def = FRAMES[frame]
    required_covered = all(coverage[key] == "covered" for key in frame_def["required"])
    blocking = sum(
        1
        for e in entries
        if e.prefix == "Q"
        and not _is_true(e.fields.get("resolved"))
        and _is_true(e.fields.get("blocking"))
    )
    return required_covered and _fr_all_traced(entries) and blocking == 0


def _is_true(value: Any) -> bool:
    return value is True


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
    lines = ["<!-- gate findings:"] + [f"- {f}" for f in findings] + ["-->"]
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
    blocking_open_questions = [
        e for e in open_questions if _is_true(e.fields.get("blocking"))
    ]
    conflicts = [
        e for e in entries if e.prefix == "X" and e.fields.get("status") == "open"
    ]

    meta: dict[str, Any] = {
        "schema": "discovery-brief",
        "schema_version": 1,
        "spec_stage": "discovery",
        "validation": validation,
        "interview": {"frame": frame, "sessions": _sessions(events)},
        "coverage": {**coverage, "gate_passed": _gate_passed(coverage, entries, frame)},
        "open_questions": len(open_questions),
        "blocking_open_questions": len(blocking_open_questions),
        "conflicts": len(conflicts),
        "traces_to": list(header.traces_to),
    }

    frontmatter = yaml.safe_dump(meta, sort_keys=False, allow_unicode=True)
    text = f"---\n{frontmatter}---\n{_render_body(entries)}"
    if findings:
        text += _render_findings(findings)
    return text
