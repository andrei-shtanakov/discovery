"""Structured answer payload parsing.

Implements [REQ-014]-[REQ-016]: an interview answer arrives as a YAML
document with a free-text `text` field and an optional list of typed
`entries`; `parse_payload` turns it into an `AnswerPayload`, preserving
non-reserved entry fields verbatim and rejecting structural violations via
a single `PayloadInvalid` exception.
"""

import re
from dataclasses import dataclass, field
from typing import Any

import yaml

RESERVED = {"id", "body"}
ID_RE = re.compile(r"^[A-Z]+-\d+$")
# Deliberately stricter than the vendored linter's `traces_to` handling
# (gate_check.py:252-258 normalises a bare string to a one-element list):
# normalising an entry's `traces` the same way would turn `'[J-02, G-01]'`
# into one bogus target and report "no trace" for an entry the operator did
# trace. Refusing instead of guessing is the point (§7) — do not "fix" this
# asymmetry by normalising here too.
LIST_FIELDS = {"traces"}


class PayloadInvalid(Exception):
    """Raised when a raw payload document is structurally invalid."""


@dataclass
class Entry:
    """One typed record (FR/G/J, ...) inside an answer payload."""

    eid: str
    body: str
    fields: dict[str, str] = field(default_factory=dict)


@dataclass
class AnswerPayload:
    """A parsed interview answer: free text plus typed entries."""

    text: str
    entries: list[Entry]


def _parse_entry(item: Any) -> Entry:
    """Build one `Entry` from a raw `entries` mapping item."""
    if not isinstance(item, dict) or "id" not in item:
        raise PayloadInvalid(f"entry without an id: {item!r}")
    eid = str(item["id"])
    if not ID_RE.match(eid):
        raise PayloadInvalid(f"malformed entry id: {eid!r}")
    body = str(item.get("body", ""))
    for key, value in item.items():
        if key in LIST_FIELDS and not isinstance(value, list):
            raise PayloadInvalid(
                f"{eid}: {key!r} must be a YAML list, got "
                f"{type(value).__name__}: {value!r}"
            )
    fields = {k: str(v) for k, v in item.items() if k not in RESERVED}
    return Entry(eid=eid, body=body, fields=fields)


def parse_payload(raw: str) -> AnswerPayload:
    """Parse a YAML answer document into an `AnswerPayload`.

    Raises `PayloadInvalid` on a YAML syntax error, a non-mapping document,
    a missing `text` key, a non-list `entries` value, an entry without an
    `id`, or an entry `id` not matching `ID_RE`.
    """
    try:
        doc = yaml.safe_load(raw)
    except yaml.YAMLError as exc:
        raise PayloadInvalid(f"invalid YAML: {exc}") from exc
    if not isinstance(doc, dict) or "text" not in doc:
        raise PayloadInvalid(f"payload missing text: {doc!r}")
    text = str(doc["text"]).strip()
    raw_entries = doc.get("entries") if doc.get("entries") is not None else []
    if not isinstance(raw_entries, list):
        raise PayloadInvalid(f"entries must be a list: {raw_entries!r}")
    entries = [_parse_entry(item) for item in raw_entries]
    return AnswerPayload(text=text, entries=entries)
