"""Session layout and atomic artifact writes.

Implements [REQ-010]-[REQ-013]: a session's header lives at
`<root>/<session_id>/header.json`, and both the header and any artifact
written into a session go through the same temp-file + `os.replace` +
directory-`fsync` sequence, so a reader never observes a partial write and
a crash mid-rename cannot lose the completed content.
"""

import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path


class SessionUnreadable(Exception):
    """Raised when a session's header cannot be found or parsed."""


@dataclass
class SessionHeader:
    """Metadata identifying and describing a discovery session."""

    session_id: str
    frame: str
    target: str
    traces_to: list[str]
    source_pin: str
    created_at: str


def _atomic_write(path: Path, text: str) -> None:
    """Durably replace ``path`` with ``text``.

    Writes to a temp file beside ``path`` (same directory, so the same
    filesystem), fsyncs its file descriptor, `os.replace`s it onto
    ``path``, then fsyncs the parent directory so the rename itself
    survives a crash.
    """
    tmp = path.parent / f".tmp-{path.name}"
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o644)
    try:
        os.write(fd, text.encode("utf-8"))
        os.fsync(fd)
    finally:
        os.close(fd)
    os.replace(tmp, path)
    dir_fd = os.open(path.parent, os.O_RDONLY)
    try:
        os.fsync(dir_fd)
    finally:
        os.close(dir_fd)


def write_artifact(path: Path, text: str) -> None:
    """Atomically write ``text`` to ``path`` via `_atomic_write`."""
    _atomic_write(path, text)


class Session:
    """Create and load a session's on-disk header."""

    def __init__(self, header: SessionHeader) -> None:
        """Wrap the loaded or created ``header``."""
        self.header = header

    @staticmethod
    def create(root: Path, header: SessionHeader) -> "Session":
        """Create `<root>/<header.session_id>/` and write `header.json`."""
        session_dir = root / header.session_id
        session_dir.mkdir(parents=True, exist_ok=True)
        text = json.dumps(asdict(header), ensure_ascii=False, indent=2, sort_keys=True)
        _atomic_write(session_dir / "header.json", text)
        return Session(header)

    @staticmethod
    def load(root: Path, session_id: str) -> "Session":
        """Load `<root>/<session_id>/header.json` into a `SessionHeader`."""
        path = root / session_id / "header.json"
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            header = SessionHeader(**raw)
        except (OSError, ValueError, TypeError) as exc:
            raise SessionUnreadable(f"{path.parent}: {exc}") from exc
        return Session(header)
