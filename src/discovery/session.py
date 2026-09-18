"""Session layout and atomic artifact writes.

Implements [REQ-010]-[REQ-013]: a session's header lives at
`<root>/<session_id>/header.json`, and both the header and any artifact
written into a session go through the same temp-file + `os.replace` +
directory-`fsync` sequence, so a reader never observes a partial write and
a crash mid-rename cannot lose the completed content.

`create` extends that from one file to the session as a whole: the
directory is reserved atomically, seeded files are written, and the header
lands last as the commit marker that makes the session readable.
"""

import json
import os
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path


class SessionUnreadable(Exception):
    """Raised when a session's header cannot be found or parsed."""


class InvalidSessionId(ValueError):
    """Raised for a ``session_id`` that could escape its session directory.

    Typed so a caller can catch exactly this and project it into a refusal
    envelope, without widening its handler to every `ValueError` a
    programming error might raise.
    """


@dataclass
class SessionHeader:
    """Metadata identifying and describing a discovery session."""

    session_id: str
    frame: str
    target: str
    traces_to: list[str]
    source_pin: str
    created_at: str


def _validate_session_id(session_id: str) -> None:
    """Reject a ``session_id`` that could escape its session directory."""
    if not session_id or session_id in (".", "..") or os.sep in session_id:
        raise InvalidSessionId(f"invalid session_id: {session_id!r}")
    if os.altsep and os.altsep in session_id:
        raise InvalidSessionId(f"invalid session_id: {session_id!r}")


def _write_all(fd: int, data: bytes) -> None:
    """Write every byte of ``data`` to ``fd``, looping past short writes."""
    view = memoryview(data)
    while view:
        view = view[os.write(fd, view) :]


def _atomic_write(path: Path, text: str) -> None:
    """Durably replace ``path`` with ``text``.

    Writes to a uniquely-named temp file beside ``path`` (same directory,
    so the same filesystem, and unique so concurrent writers to the same
    ``path`` never share and corrupt one temp file), fsyncs its file
    descriptor, `os.replace`s it onto ``path``, then fsyncs the parent
    directory so the rename itself survives a crash.
    """
    tmp = path.parent / f".tmp-{path.name}-{os.getpid()}-{uuid.uuid4().hex}"
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
    try:
        try:
            _write_all(fd, text.encode("utf-8"))
            os.fsync(fd)
        finally:
            os.close(fd)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise
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
    def create(
        root: Path, header: SessionHeader, files: dict[str, str] | None = None
    ) -> "Session":
        """Reserve `<root>/<header.session_id>/`, write `files`, then the header.

        The directory is created with `exist_ok=False`, and `mkdir` is
        atomic: a taken id is refused as `FileExistsError` with no
        check-then-create race, and a second `create` can no longer
        overwrite a live session's header.

        `header.json` is written **last**, as the session's commit marker.
        Anything in `files` — the admitted upstream copy the header's
        `traces_to` names — is already on disk by the time a reader can see
        the session at all, so a crash in between leaves an unreadable
        session rather than a readable one pointing at a file that was never
        written.
        """
        _validate_session_id(header.session_id)
        session_dir = root / header.session_id
        try:
            session_dir.mkdir(parents=True, exist_ok=False)
        except FileExistsError:
            # A directory without `header.json` is a reservation an earlier
            # `create` never committed, not a session. Completing it is what
            # keeps a crash from burning a caller-assigned id for good: the
            # id is unusable for `start` and unreadable for `status`, and a
            # caller may not reach into the session root to clean up. A
            # committed session is still never overwritten.
            if (session_dir / "header.json").exists():
                raise
        for name, content in (files or {}).items():
            _atomic_write(session_dir / name, content)
        text = json.dumps(asdict(header), ensure_ascii=False, indent=2, sort_keys=True)
        _atomic_write(session_dir / "header.json", text)
        return Session(header)

    @staticmethod
    def load(root: Path, session_id: str) -> "Session":
        """Load `<root>/<session_id>/header.json` into a `SessionHeader`."""
        _validate_session_id(session_id)
        path = root / session_id / "header.json"
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            header = SessionHeader(**raw)
        except (OSError, ValueError, TypeError) as exc:
            raise SessionUnreadable(f"{path.parent}: {exc}") from exc
        if header.session_id != session_id:
            # The header must agree with the directory it was loaded from.
            # `session_id` feeds `answer_id`, so a header that disagrees would
            # silently change answer identity and defeat replay/conflict
            # detection. A session that cannot say where it lives is not
            # readable — fail closed rather than trust the file.
            raise SessionUnreadable(
                f"{path}: header says session_id={header.session_id!r}, "
                f"loaded from {session_id!r}"
            )
        return Session(header)
