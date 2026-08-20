"""Durable append-only JSONL event journal.

Implements [REQ-005]-[REQ-009]: a single locked+fsynced write per event,
ordered replay, implicit UTC timestamps, and a hard failure on a corrupt
line rather than a silent skip.
"""

import datetime as dt
import fcntl
import json
import os
from pathlib import Path

QUESTION_ASKED = "question_asked"
ANSWER_RECORDED = "answer_recorded"
ANSWER_SUPERSEDED = "answer_superseded"
SOURCE_PIN_CHANGED = "source_pin_changed"


# The fields each event kind's readers index by name (`event["..."]`), so a
# line missing one is unreadable rather than merely odd. Kept next to the
# loader deliberately: this is a statement about what the *file* must
# contain, not about what any one reader happens to want today.
REQUIRED_FIELDS: dict[str, tuple[str, ...]] = {
    QUESTION_ASKED: ("question_id", "coverage_key", "question_text"),
    ANSWER_RECORDED: ("question_id",),
    ANSWER_SUPERSEDED: ("question_id",),
}


class JournalUnreadable(Exception):
    """Raised when a journal line cannot be parsed as JSON."""


def _now() -> str:
    """Return the current UTC time as an ISO-8601 string ending in "Z"."""
    return dt.datetime.now(dt.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


class Journal:
    """Append-only JSONL journal with durable, ordered writes."""

    def __init__(self, path: Path) -> None:
        """Bind this journal to the JSONL file at ``path``."""
        self._path = path

    def append(self, event: dict) -> None:
        """Durably append ``event`` as one JSON line, stamping ``ts``.

        Opens the file for append, takes an exclusive lock, writes a
        single ``json.dumps(...) + "\\n"`` line, flushes and fsyncs, then
        unlocks and closes. Any embedded newline in a field value is
        JSON-escaped by ``json.dumps``, so one event always yields exactly
        one physical line.
        """
        record = {**event, "ts": event.get("ts") or _now()}
        line = json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n"
        self._path.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(self._path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o644)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX)
            try:
                os.write(fd, line.encode("utf-8"))
                os.fsync(fd)
            finally:
                fcntl.flock(fd, fcntl.LOCK_UN)
        finally:
            os.close(fd)

    def events(self) -> list[dict]:
        """Return all events in append order.

        Raises ``JournalUnreadable`` on the first line that fails to parse
        as JSON *or* that parses into an event missing the fields its
        readers index by, rather than skipping it or returning a partial
        list. The journal is a file on disk and therefore untrusted input;
        validating here means every reader — lifecycle, render, the CLI —
        is covered by one boundary, and an unreadable journal reaches the
        caller as `unknown` + exit 1 with an envelope, never as a traceback
        with nothing on stdout.

        Skipping a malformed line would be the fail-open alternative: a
        dropped `question_asked` silently changes the computed lifecycle.
        """
        if not self._path.exists():
            return []
        result = []
        for line_number, line in enumerate(
            self._path.read_text(encoding="utf-8").splitlines(), start=1
        ):
            if not line:
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError as exc:
                raise JournalUnreadable(f"{self._path}:{line_number}: {exc}") from exc
            self._require_shape(event, line_number)
            result.append(event)
        return result

    def _require_shape(self, event: object, line_number: int) -> None:
        """Reject an event that a reader would index into and fail on."""
        if not isinstance(event, dict):
            raise JournalUnreadable(
                f"{self._path}:{line_number}: event is not an object"
            )
        # A line with no `event` name carries no reader and no requirement:
        # every reader selects on `event.get("event")`, so such a line is
        # inert rather than malformed. Only a kind that has readers indexing
        # by name imposes anything.
        kind = event.get("event")
        for field_name in (
            REQUIRED_FIELDS.get(kind, ()) if isinstance(kind, str) else ()
        ):
            if field_name not in event:
                raise JournalUnreadable(
                    f"{self._path}:{line_number}: {kind} has no {field_name!r}"
                )
