"""Tests for discovery.session: layout, atomic writes, and load errors.

Each case isolates one claim from [REQ-010]-[REQ-013]: create/load round
trips every header field including `frame` and `source_pin`, loading a
missing session raises `SessionUnreadable` instead of returning `None`, a
second `write_artifact` call leaves only the latest content behind with no
leftover temp file, and the target's `st_dev` is stable across overwrites.
"""

import os

import pytest

from discovery.session import Session, SessionHeader, SessionUnreadable, write_artifact


def _make_header(session_id: str = "sess-1") -> SessionHeader:
    return SessionHeader(
        session_id=session_id,
        frame="customer",
        target="discovery-brief",
        traces_to=["REQ-010", "REQ-011"],
        source_pin="commit:deadbeef",
        created_at="2026-08-19T00:00:00Z",
    )


def test_create_and_load_round_trip_every_header_field(tmp_path):
    root = tmp_path / "sessions"
    header = _make_header()

    Session.create(root, header)
    loaded = Session.load(root, "sess-1")

    assert loaded.header == header
    assert loaded.header.frame == "customer"
    assert loaded.header.source_pin == "commit:deadbeef"


def test_load_missing_session_raises_session_unreadable(tmp_path):
    root = tmp_path / "sessions"

    with pytest.raises(SessionUnreadable):
        Session.load(root, "does-not-exist")


def test_double_write_artifact_leaves_only_latest_content(tmp_path):
    root = tmp_path / "sessions"
    Session.create(root, _make_header())
    artifact = root / "sess-1" / "brief.md"

    write_artifact(artifact, "first version")
    write_artifact(artifact, "second version")

    assert artifact.read_text(encoding="utf-8") == "second version"


def test_double_write_artifact_leaves_no_tmp_files(tmp_path):
    root = tmp_path / "sessions"
    Session.create(root, _make_header())
    session_dir = root / "sess-1"
    artifact = session_dir / "brief.md"

    write_artifact(artifact, "first version")
    write_artifact(artifact, "second version")

    leftover_tmp = [p for p in session_dir.iterdir() if p.name.startswith(".tmp")]
    assert leftover_tmp == []


def test_write_artifact_keeps_st_dev_stable_across_overwrites(tmp_path):
    root = tmp_path / "sessions"
    Session.create(root, _make_header())
    artifact = root / "sess-1" / "brief.md"

    write_artifact(artifact, "first version")
    first_dev = os.stat(artifact).st_dev
    write_artifact(artifact, "second version")

    assert os.stat(artifact).st_dev == first_dev
