"""Entry redefinition across answers — `@id:duplicate-entry-ids-across-answers`.

Decided 2026-09-11 after the first live S1 run rendered 83 entry instances
over 76 unique ids (the caller re-declared FR-01 in three answers):

1. two equal ids inside one payload — refused, journal unchanged;
2. the same id in a later answer is an explicit new version;
3. projection: latest answer per question_id, then — in journal order —
   the latest version of each entry_id;
4. a new version replaces the old one whole, no field merging;
5. the replacement is recorded atomically in the `answer_recorded` event
   as `replaces_entries`;
6. render, readiness and gate share one projector.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from discovery import cli
from discovery import render as render_module
from discovery.payload import PayloadInvalid, parse_payload
from discovery.questions import Question, StaticQuestionSource
from discovery.render import readiness, render_brief

FIXTURE = Path(__file__).parent / "data" / "s1-live-2026-09-11"


# ---------------------------------------------------------------------------
# 1. Two equal ids inside one payload.
# ---------------------------------------------------------------------------


def test_a_payload_declaring_one_id_twice_is_invalid():
    raw = "text: t\nentries:\n  - id: FR-01\n    body: a\n  - id: FR-01\n    body: b\n"
    with pytest.raises(PayloadInvalid, match="FR-01"):
        parse_payload(raw)


# ---------------------------------------------------------------------------
# 3/4. The projector.
# ---------------------------------------------------------------------------


def _answer(question_id: str, payload: str, suffix: str = "") -> dict:
    return {
        "event": "answer_recorded",
        "question_id": question_id,
        "answer_id": f"sha256:{question_id}{suffix}",
        "participant_role": "stakeholder",
        "payload": payload,
    }


def _entries_payload(*items: tuple[str, str, dict]) -> str:
    return yaml.safe_dump(
        {
            "text": "t",
            "entries": [{"id": i, "body": b, **f} for i, b, f in items],
        },
        allow_unicode=True,
    )


def test_a_later_answer_redefines_an_entry_whole():
    events = [
        _answer("q1", _entries_payload(("FR-01", "v1", {"priority": "Must"}))),
        _answer("q2", _entries_payload(("FR-01", "v2", {}), ("FR-02", "x", {}))),
    ]
    entries = render_module.effective_entries(events)
    assert [e.eid for e in entries] == ["FR-01", "FR-02"]
    fr01 = entries[0]
    assert fr01.body == "v2"
    assert "priority" not in fr01.fields, (
        "no field merging — the linter catches the loss"
    )


def test_the_latest_version_is_chosen_by_journal_order_not_first_appearance():
    """q1 answered first, then q2, then q1 superseded later: q1's new version
    is the newest event and must win even though q1 was seen first."""
    events = [
        _answer("q1", _entries_payload(("FR-01", "v1", {}))),
        _answer("q2", _entries_payload(("FR-01", "v2", {}))),
        {"event": "answer_superseded", "question_id": "q1", "answer_id": "sha256:q1"},
        _answer("q1", _entries_payload(("FR-01", "v3", {})), suffix="b"),
    ]
    (fr01,) = render_module.effective_entries(events)
    assert fr01.body == "v3"


def test_a_superseded_answers_entries_never_come_back():
    events = [
        _answer("q1", _entries_payload(("FR-01", "v1", {}), ("FR-09", "gone", {}))),
        {"event": "answer_superseded", "question_id": "q1", "answer_id": "sha256:q1"},
        _answer("q1", _entries_payload(("FR-01", "v2", {})), suffix="b"),
    ]
    assert [e.eid for e in render_module.effective_entries(events)] == ["FR-01"]


# ---------------------------------------------------------------------------
# 6. One projector for render, readiness and gate.
# ---------------------------------------------------------------------------


class _Header:
    frame = "customer"
    target = "org/repo"
    traces_to: list[str] = []
    created_at = "2026-09-11T00:00:00Z"


def test_render_and_readiness_see_the_same_redefined_entries():
    events = [
        _answer("q1", _entries_payload(("FR-01", "старая", {}))),
        _answer("q2", _entries_payload(("FR-01", "новая", {}))),
    ]
    brief = render_brief(_Header(), events, validation="pass")
    assert brief.count("**FR-01**") == 1
    assert "новая" in brief and "старая" not in brief
    assert readiness(events, "customer") == render_module._readiness_of(
        render_module.effective_entries(events),
        "customer",
        render_module._answered_coverage_keys(events),
    )


# ---------------------------------------------------------------------------
# 2/5. The CLI records a redefinition atomically.
# ---------------------------------------------------------------------------

TWO_QUESTIONS = {
    "customer": [
        Question("customer.f.01", "functions", "what?"),
        Question("customer.f.02", "functions", "how?"),
    ]
}


def _run(capsys, argv):
    code = cli.main(argv)
    return code, json.loads(capsys.readouterr().out)


def _start(capsys, monkeypatch, tmp_path):
    monkeypatch.setenv("DISCOVERY_HOME", str(tmp_path / "home"))
    monkeypatch.setattr(
        cli, "build_source", lambda: StaticQuestionSource("pin-test", TWO_QUESTIONS)
    )
    _, envelope = _run(capsys, ["start", "--frame", "customer", "--target", "org/repo"])
    return envelope["next_action"]["session_id"]


def _answer_file(tmp_path, name, payload, session_id, question_id, capsys, *extra):
    path = tmp_path / name
    path.write_text(payload, encoding="utf-8")
    return _run(
        capsys,
        [
            "answer",
            "--session",
            session_id,
            "--question",
            question_id,
            "--role",
            "stakeholder",
            "--file",
            str(path),
            *extra,
        ],
    )


def test_a_redefinition_is_recorded_on_the_answer_event(capsys, monkeypatch, tmp_path):
    session_id = _start(capsys, monkeypatch, tmp_path)
    _answer_file(
        tmp_path,
        "a.yaml",
        _entries_payload(("FR-01", "v1", {}), ("FR-02", "keep", {})),
        session_id,
        "customer.f.01",
        capsys,
    )
    code, envelope = _answer_file(
        tmp_path,
        "b.yaml",
        _entries_payload(("FR-01", "v2", {}), ("FR-03", "new", {})),
        session_id,
        "customer.f.02",
        capsys,
    )
    assert envelope["operation"] == {"status": "ok"}
    events = cli._journal(session_id).events()
    first, second = [e for e in events if e["event"] == "answer_recorded"]
    assert "replaces_entries" not in first
    assert second["replaces_entries"] == [
        {
            "entry_id": "FR-01",
            "previous_question_id": "customer.f.01",
            "previous_answer_id": first["answer_id"],
        }
    ]


def test_a_supersede_of_the_same_question_is_not_a_redefinition(
    capsys, monkeypatch, tmp_path
):
    """The previous version lives in the answer being superseded, and
    `answer_superseded` already records that; nothing else held FR-01."""
    session_id = _start(capsys, monkeypatch, tmp_path)
    _answer_file(
        tmp_path,
        "a.yaml",
        _entries_payload(("FR-01", "v1", {})),
        session_id,
        "customer.f.01",
        capsys,
    )
    _answer_file(
        tmp_path,
        "b.yaml",
        _entries_payload(("FR-01", "v2", {})),
        session_id,
        "customer.f.01",
        capsys,
        "--supersede",
    )
    events = cli._journal(session_id).events()
    latest = [e for e in events if e["event"] == "answer_recorded"][-1]
    assert "replaces_entries" not in latest


def test_a_payload_with_a_duplicate_id_leaves_the_journal_unchanged(
    capsys, monkeypatch, tmp_path
):
    session_id = _start(capsys, monkeypatch, tmp_path)
    before = cli._journal(session_id).events()
    code, envelope = _answer_file(
        tmp_path,
        "dup.yaml",
        "text: t\nentries:\n  - id: FR-01\n    body: a\n  - id: FR-01\n    body: b\n",
        session_id,
        "customer.f.01",
        capsys,
    )
    assert code == 1
    assert "FR-01" in envelope["operation"]["reason"]
    assert cli._journal(session_id).events() == before


# ---------------------------------------------------------------------------
# Frozen journal: the first live S1 run, as recorded.
# ---------------------------------------------------------------------------


def test_the_first_live_s1_journal_projects_to_76_unique_entries():
    """Recorded 2026-09-11 by the L3 stand (`runs/20260911T143421Z-00`):
    83 instances over 76 ids before this rule. The projector must yield
    each id once, with the version from the latest answer that declared it."""
    events = [
        json.loads(line)
        for line in (FIXTURE / "journal.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    entries = render_module.effective_entries(events)
    ids = [e.eid for e in entries]
    assert len(ids) == 76
    assert len(set(ids)) == 76

    # FR-01 was declared as an entry twice — the second time when the
    # caller re-stated it with Acceptance for `functions.03` (the third
    # rendered mention, under `nfr.01`, is only text). The latest wins.
    holders = [
        e
        for e in events
        if e["event"] == "answer_recorded"
        and any(
            raw["id"] == "FR-01"
            for raw in yaml.safe_load(e["payload"]).get("entries") or []
        )
    ]
    assert [h["question_id"] for h in holders] == [
        "customer.functions.01",
        "customer.functions.03",
    ]
    latest_fr01 = next(
        raw
        for raw in yaml.safe_load(holders[-1]["payload"])["entries"]
        if raw["id"] == "FR-01"
    )
    fr01 = next(e for e in entries if e.eid == "FR-01")
    assert fr01.body == latest_fr01.get("body", "")
    assert fr01.fields == {
        k: v for k, v in latest_fr01.items() if k not in ("id", "body")
    }
