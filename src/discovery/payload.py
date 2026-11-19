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
# Contract v1.3, customer frame: one row of `## Translation table` per
# stakeholder statement. Column order is the contract's; `render` owns it.
TRANSLATION_COLUMNS = (
    "words",
    "category",
    "constraint",
    "assumption",
    "confirmer",
    "due",
)
# The one frame whose brief carries the table; GC-18 reads no other.
TRANSLATION_FRAME = "customer"
# The linter splits a row on `|` and reads the table line by line.
_TABLE_BREAKERS = ("|", "\n", "\r")


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
    translations: list[dict[str, Any]] = field(default_factory=list)
    # Answer to a `feature` profile filter (contract v1.4); `None` — absent.
    expand: bool | None = None


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
    # A validated `traces` list is stored here as its Python repr (e.g.
    # "['G-01']"), not as a list — nothing in this module consumes it, since
    # `render` re-parses the raw payload YAML itself. A future reader of
    # `Entry.fields["traces"]` must not expect a list back.
    fields = {k: str(v) for k, v in item.items() if k not in RESERVED}
    return Entry(eid=eid, body=body, fields=fields)


def parse_payload(raw: str) -> AnswerPayload:
    """Parse a YAML answer document into an `AnswerPayload`.

    Raises `PayloadInvalid` on a YAML syntax error, a non-mapping document,
    a missing `text` key, a non-list `entries` value, an entry without an
    `id`, an entry `id` not matching `ID_RE`, one id declared twice, a
    malformed `translations` list, an `expand` that is not a YAML bool, or
    YAML nested too deeply to parse.
    """
    try:
        doc = yaml.safe_load(raw)
    except yaml.YAMLError as exc:
        raise PayloadInvalid(f"invalid YAML: {exc}") from exc
    except RecursionError as exc:
        # PyYAML's composer recurses per nesting level; ~1000 levels raise
        # this, and it is not a `YAMLError`.
        raise PayloadInvalid("YAML nested too deeply to parse") from exc
    if not isinstance(doc, dict) or "text" not in doc:
        raise PayloadInvalid(f"payload missing text: {doc!r}")
    text = str(doc["text"]).strip()
    raw_entries = doc.get("entries") if doc.get("entries") is not None else []
    if not isinstance(raw_entries, list):
        raise PayloadInvalid(f"entries must be a list: {raw_entries!r}")
    entries = [_parse_entry(item) for item in raw_entries]
    _refuse_duplicate_ids(entries)
    translations = _parse_translations(doc.get("translations"))
    expand = doc.get("expand")
    if "expand" in doc and not isinstance(expand, bool):
        raise PayloadInvalid(f"expand must be true or false: {expand!r}")
    return AnswerPayload(
        text=text, entries=entries, translations=translations, expand=expand
    )


def _parse_translations(raw: Any) -> list[dict[str, Any]]:
    """Validate `translations` structurally; its vocabulary is the linter's.

    Only what would corrupt the rendered table is refused here: a non-list,
    a row that is not a mapping or is empty (render would drop it without a
    word), a column the contract does not have (a
    misspelt `confirms:` would otherwise render as `—` and read as "no
    assumption"), and a `|` or newline that would shift the columns GC-18
    checks. Whether the category is in the dictionary is GC-18's call.
    """
    if raw is None:
        return []
    if not isinstance(raw, list):
        raise PayloadInvalid(f"translations must be a list: {raw!r}")
    for row in raw:
        if not isinstance(row, dict):
            raise PayloadInvalid(f"translations row is not a mapping: {row!r}")
        if not row:
            raise PayloadInvalid("translations row is empty: it names no statement")
        unknown = sorted(set(row) - set(TRANSLATION_COLUMNS))
        if unknown:
            raise PayloadInvalid(
                f"translations row has unknown column(s) {unknown}; "
                f"expected {list(TRANSLATION_COLUMNS)}"
            )
        for column, value in row.items():
            cells = value if isinstance(value, list) else [value]
            if any(b in str(cell) for cell in cells for b in _TABLE_BREAKERS):
                raise PayloadInvalid(
                    f"translations {column!r} must not contain '|' or a "
                    f"line break: {value!r}"
                )
    return raw


def refuse_foreign_translations(payload: AnswerPayload, frame: str) -> None:
    """Translation table is the customer frame's discovery outcome (contract
    v1.3 §3); GC-18 never reads it in another frame, so rows there would
    reach the brief unchecked. Refused at intake instead of dropped."""
    if payload.translations and frame != TRANSLATION_FRAME:
        raise PayloadInvalid(
            f"translations belong to the {TRANSLATION_FRAME} frame only, got {frame!r}"
        )


def refuse_misplaced_expand(payload: AnswerPayload, is_filter: bool) -> None:
    """`expand` is the whole point of a filter answer and meaningless
    elsewhere (contract v1.4): required on a filter, refused on any other
    question, so neither a forgotten nor a stray flag is guessed at."""
    if is_filter and payload.expand is None:
        raise PayloadInvalid("a filter question's answer needs expand: true|false")
    if not is_filter and payload.expand is not None:
        raise PayloadInvalid("expand answers a filter question only")


def _refuse_duplicate_ids(entries: list[Entry]) -> None:
    """One id at most once per payload.

    Two versions of one id in a single answer have no order between them
    a reader could rely on; across answers a repeat is an explicit new
    version (`render.effective_entries`), inside one it is a malformed
    document and the journal stays untouched.
    """
    seen: set[str] = set()
    for entry in entries:
        if entry.eid in seen:
            raise PayloadInvalid(f"entry id declared twice in one payload: {entry.eid}")
        seen.add(entry.eid)
