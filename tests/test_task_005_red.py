"""Frozen RED checkpoint for TASK-005.

This file is byte-frozen until the task is done: it exists to prove that,
at the moment the task started, `src/discovery/session.py` did not yet
exist, so none of REQ-010 (create/load session layout with header),
REQ-011 (SessionUnreadable on a missing session), REQ-012 (atomic
artifact write via temp file + os.replace + directory fsync), or
REQ-013 (same-filesystem temp placement, stable st_dev across
overwrites) could be checked.
"""

import os

import pytest


class TestSessionRed:
    def test_create_load_and_atomic_artifact_write_follow_req_010_through_013(
        self, tmp_path
    ):
        try:
            from discovery.session import (
                Session,
                SessionHeader,
                SessionUnreadable,
                write_artifact,
            )
        except ModuleNotFoundError as exc:
            pytest.fail(
                "discovery.session does not exist yet "
                f"(REQ-010..REQ-013 unimplemented): {exc}"
            )

        root = tmp_path / "sessions"

        # REQ-010: create() lays out <root>/<session_id>/header.json and
        # load() reconstructs every field, including frame and source_pin.
        header = SessionHeader(
            session_id="sess-1",
            frame="customer",
            target="discovery-brief",
            traces_to=["REQ-010", "REQ-011"],
            source_pin="commit:deadbeef",
            created_at="2026-08-19T00:00:00Z",
        )
        Session.create(root, header)

        session_dir = root / "sess-1"
        assert (session_dir / "header.json").exists()

        loaded = Session.load(root, "sess-1")
        assert loaded.header == header

        # REQ-011: loading a session_id with no directory under root is an
        # explicit SessionUnreadable, not None or a partial object.
        with pytest.raises(SessionUnreadable):
            Session.load(root, "does-not-exist")

        # REQ-012: write_artifact goes through a temp file + os.replace, so
        # a second call with different content leaves only the latest text
        # behind and no ".tmp"-prefixed file remains in the parent dir.
        artifact = session_dir / "brief.md"
        write_artifact(artifact, "first version")
        first_dev = os.stat(artifact).st_dev
        write_artifact(artifact, "second version")

        assert artifact.read_text(encoding="utf-8") == "second version"
        leftover_tmp = [p for p in session_dir.iterdir() if p.name.startswith(".tmp")]
        assert leftover_tmp == []

        # REQ-013: the temp file shares a filesystem with the target, so
        # os.replace is an atomic rename and st_dev is stable across
        # overwrites of the same artifact.
        assert os.stat(artifact).st_dev == first_dev
