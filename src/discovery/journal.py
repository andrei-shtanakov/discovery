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
        as JSON, rather than skipping it or returning a partial list.
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
                result.append(json.loads(line))
            except json.JSONDecodeError as exc:
                raise JournalUnreadable(f"{self._path}:{line_number}: {exc}") from exc
        return result
