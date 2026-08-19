"""Canonical answer bytes and content-addressed identity helpers.

Implements [REQ-001]-[REQ-004]: deterministic hashing for answer identity
and file provenance, sharing the same ``"sha256:<hex>"`` convention.
"""

import hashlib
from pathlib import Path

_FIELD_SEPARATOR = b"\x00"


def canonical_answer_bytes(text: str) -> bytes:
    """Fold line-ending variants to LF and encode as UTF-8.

    CRLF is replaced before a bare CR so a CRLF pair is never
    double-substituted into two LFs. No other transformation is applied:
    leading/trailing whitespace passes through unchanged.
    """
    return text.replace("\r\n", "\n").replace("\r", "\n").encode("utf-8")


def answer_id(
    session_id: str, question_id: str, participant_role: str, text: str
) -> str:
    """Compute the content-addressed identity of an answer.

    Joins ``session_id``, ``question_id``, ``participant_role`` and the
    canonical bytes of ``text`` with a NUL separator before hashing, so a
    role change on an otherwise-identical answer changes the id, and
    field concatenation across the first three fields cannot collide.
    """
    digest = hashlib.sha256(
        session_id.encode("utf-8")
        + _FIELD_SEPARATOR
        + question_id.encode("utf-8")
        + _FIELD_SEPARATOR
        + participant_role.encode("utf-8")
        + _FIELD_SEPARATOR
        + canonical_answer_bytes(text)
    )
    return f"sha256:{digest.hexdigest()}"


def file_sha256(path: Path) -> str:
    """Return the SHA-256 digest of a file's raw bytes, not canonicalized."""
    return f"sha256:{hashlib.sha256(path.read_bytes()).hexdigest()}"
