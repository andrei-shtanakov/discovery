"""Frozen RED checkpoint for TASK-003.

This file is byte-frozen until the task is done: it exists to prove that,
at the moment the task started, `src/discovery/hashing.py` did not yet
exist, so none of REQ-001 (canonical line-ending folding), REQ-002
(role-aware answer_id), REQ-003 (non-colliding field concatenation), or
REQ-004 (file_sha256 convention) could be checked.
"""

import hashlib

import pytest


class TestHashingRed:
    def test_answer_identity_and_file_hash_follow_req_001_through_004(self, tmp_path):
        try:
            from discovery.hashing import (
                answer_id,
                canonical_answer_bytes,
                file_sha256,
            )
        except ModuleNotFoundError as exc:
            pytest.fail(
                "discovery.hashing does not exist yet "
                f"(REQ-001..REQ-004 unimplemented): {exc}"
            )

        # REQ-001: CRLF and a lone CR both fold to LF; nothing else is
        # transformed — leading/trailing whitespace passes through untouched.
        raw = "line one\r\nline two\rline three  \n  trailing"
        assert canonical_answer_bytes(raw) == (
            b"line one\nline two\nline three  \n  trailing"
        )

        # REQ-002: answer_id has the "sha256:<hex>" shape, is stable across
        # EOL styles once folded, and changes when only participant_role
        # changes (a re-attributed answer must not look like a replay).
        id_lf = answer_id("s1", "q1", "product", "line one\nline two")
        id_crlf = answer_id("s1", "q1", "product", "line one\r\nline two")
        assert id_lf.startswith("sha256:")
        assert id_lf == id_crlf
        id_other_role = answer_id("s1", "q1", "engineer", "line one\nline two")
        assert id_other_role != id_lf

        # REQ-003: fields are NUL-separated before hashing, so a naive
        # concatenation of adjacent fields cannot collide with the real ones.
        id_a = answer_id("s1", "q1", "product", "x")
        id_b = answer_id("s1", "q1\x00product", "", "x")
        assert id_a != id_b

        # REQ-004: file_sha256 hashes raw file bytes, same "sha256:<hex>"
        # convention as answer_id, with no canonicalization applied.
        target = tmp_path / "artifact.bin"
        target.write_bytes(b"raw file bytes, not text")
        expected = f"sha256:{hashlib.sha256(target.read_bytes()).hexdigest()}"
        assert file_sha256(target) == expected
