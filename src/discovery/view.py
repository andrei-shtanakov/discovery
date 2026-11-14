"""session_view — the public, read-only picture of one session (`discovery show`).

A pure function of `(header, events)`, built only from the projections the
brief itself is rendered from (`render.effective_entries`, `entry_holders`,
`coverage`), so what a caller sees is what the gate judges — never a second
reading of the journal that could drift from the first. Readiness and gate
are not repeated here: they travel on the envelope's axes.
"""

from __future__ import annotations

from typing import Any

import yaml

from discovery.contract.gate_check import FRAMES
from discovery.journal import ANSWER_RECORDED
from discovery.lifecycle import issued
from discovery.render import coverage, effective_entries, entry_holders
from discovery.session import SessionHeader


def session_view(header: SessionHeader, events: list[dict]) -> dict[str, Any]:
    """Header, topics, coverage, entries, holders, asked questions, answers."""
    frame = header.frame
    return {
        "session_id": header.session_id,
        "frame": frame,
        "target": header.target,
        "traces_to": list(header.traces_to),
        "source_pin": header.source_pin,
        "created_at": header.created_at,
        "topics": {
            "required": dict(FRAMES[frame]["required"]),
            "optional": dict(FRAMES[frame]["optional"]),
        },
        "coverage": coverage(events, frame),
        "entries": [
            {"id": e.eid, "body": e.body, "fields": e.fields}
            for e in effective_entries(events)
        ],
        "declared": _declared(events),
        "holders": {eid: held[0] for eid, held in entry_holders(events).items()},
        "asked": [
            {
                "question_id": e["question_id"],
                "coverage_key": e.get("coverage_key"),
                "question_text": e.get("question_text"),
            }
            for e in issued(events)
        ],
        "answers": _answers(events),
    }


def _payload(raw: object) -> dict[str, Any]:
    """An answer payload as a mapping; anything else reads as empty."""
    loaded = yaml.safe_load(raw) if isinstance(raw, str) else None
    return loaded if isinstance(loaded, dict) else {}


def _declared(events: list[dict]) -> list[str]:
    """Every entry id ever declared, superseded answers included, first-seen.

    The effective entries alone hide ids a later version dropped; a caller
    minting the next free id must not reuse one of those.
    """
    seen: dict[str, None] = {}
    for event in events:
        if event.get("event") != ANSWER_RECORDED:
            continue
        for raw in _payload(event.get("payload")).get("entries") or []:
            if isinstance(raw, dict) and "id" in raw:
                seen[str(raw["id"])] = None
    return list(seen)


def _answers(events: list[dict]) -> list[dict[str, Any]]:
    """The latest answer per question, ordered by when that answer landed."""
    latest: dict[str, dict] = {}
    for event in events:
        if event.get("event") == ANSWER_RECORDED:
            latest.pop(event["question_id"], None)
            latest[event["question_id"]] = event
    return [
        {
            "question_id": question_id,
            "answer_id": event.get("answer_id"),
            "participant_role": event.get("participant_role"),
            "payload": _payload(event.get("payload")),
        }
        for question_id, event in latest.items()
    ]
