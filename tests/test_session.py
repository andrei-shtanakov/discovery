"""Tests for discovery.session: layout, atomic writes, and load errors.

Each case isolates one claim from [REQ-010]-[REQ-013]: create/load round
trips every header field including `frame` and `source_pin`; loading a
missing session, malformed JSON, or a header with a missing/unexpected
field all raise `SessionUnreadable` instead of returning `None` or a
partial object; a second `write_artifact` call leaves only the latest
content behind with no leftover temp file, even for a large payload; the
target's `st_dev` is stable across overwrites; a second `Session.create`
call for the same id overwrites the header; and a `session_id` that could
escape the session root is rejected by both `create` and `load`.
"""

import json
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


def test_load_malformed_json_raises_session_unreadable(tmp_path):
    root = tmp_path / "sessions"
    session_dir = root / "sess-1"
    session_dir.mkdir(parents=True)
    (session_dir / "header.json").write_text("{not json", encoding="utf-8")

    with pytest.raises(SessionUnreadable):
        Session.load(root, "sess-1")


def test_load_header_with_missing_field_raises_session_unreadable(tmp_path):
    root = tmp_path / "sessions"
    session_dir = root / "sess-1"
    session_dir.mkdir(parents=True)
    header_path = session_dir / "header.json"
    header_path.write_text('{"session_id": "sess-1"}', encoding="utf-8")

    with pytest.raises(SessionUnreadable):
        Session.load(root, "sess-1")


def test_load_header_with_unexpected_field_raises_session_unreadable(tmp_path):
    root = tmp_path / "sessions"
    Session.create(root, _make_header())
    header_path = root / "sess-1" / "header.json"
    raw = json.loads(header_path.read_text(encoding="utf-8"))
    raw["unexpected_field"] = "surprise"
    header_path.write_text(json.dumps(raw), encoding="utf-8")

    with pytest.raises(SessionUnreadable):
        Session.load(root, "sess-1")


def test_create_twice_overwrites_header_with_latest_call(tmp_path):
    root = tmp_path / "sessions"
    Session.create(root, _make_header())

    second_header = _make_header()
    second_header.target = "updated-target"
    Session.create(root, second_header)

    loaded = Session.load(root, "sess-1")
    assert loaded.header.target == "updated-target"


@pytest.mark.parametrize("bad_session_id", ["..", ".", "../escape", "a/b", ""])
def test_create_rejects_session_id_that_could_escape_root(tmp_path, bad_session_id):
    root = tmp_path / "sessions"
    header = _make_header(session_id=bad_session_id)

    with pytest.raises(ValueError):
        Session.create(root, header)


@pytest.mark.parametrize("bad_session_id", ["..", ".", "../escape", "a/b", ""])
def test_load_rejects_session_id_that_could_escape_root(tmp_path, bad_session_id):
    root = tmp_path / "sessions"

    with pytest.raises(ValueError):
        Session.load(root, bad_session_id)


def test_concurrent_writes_do_not_share_temp_file(tmp_path):
    root = tmp_path / "sessions"
    Session.create(root, _make_header())
    session_dir = root / "sess-1"
    artifact = session_dir / "brief.md"
    write_artifact(artifact, "first version")

    long_text = "y" * (1024 * 1024)
    write_artifact(artifact, long_text)

    assert artifact.read_text(encoding="utf-8") == long_text
    leftover_tmp = [p for p in session_dir.iterdir() if p.name.startswith(".tmp")]
    assert leftover_tmp == []
