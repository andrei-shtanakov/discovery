"""Tests for discovery.cli — TASK-012, covering REQ-001..REQ-009 and NFR-001.

Each case isolates one claim: the CLI itself never computes lifecycle/gate,
every command emits the same five-key envelope with the documented
exit-code priority (REQ-001, REQ-002); `question_asked` survives a
start/status round trip and is never re-appended once issued (REQ-003); an
answer replay by `answer_id` is a no-op (REQ-004); a conflicting answer is
refused with the journal unchanged unless `--supersede` is passed
(REQ-005, REQ-006); an unknown session collapses every command to
`unknown` (REQ-007); sessions live under `$DISCOVERY_HOME/sessions`,
defaulting to `~/.discovery/sessions` (REQ-008); `build_source()` defaults
to an empty `StaticQuestionSource` unless a test monkeypatches it
(REQ-009); and a repeated call over an unchanged journal returns an
identical envelope (NFR-001).
"""

from __future__ import annotations

import json
from pathlib import Path

from discovery import cli
from discovery.questions import Question, StaticQuestionSource

ENVELOPE_KEYS = {"lifecycle", "gate", "next_action", "findings", "operation"}
ONE_QUESTION = {"customer": [Question("customer.g.01", "goals", "What problem?")]}


def _use_source(monkeypatch, catalogue, pin="pin-test"):
    """Monkeypatch `cli.build_source` with a fixture (never the module catalogue)."""
    source = StaticQuestionSource(pin, catalogue)
    monkeypatch.setattr(cli, "build_source", lambda: source)
    return source


def _run(capsys, argv):
    code = cli.main(argv)
    envelope = json.loads(capsys.readouterr().out)
    return code, envelope


def _start(capsys, monkeypatch, tmp_path, catalogue, frame="customer"):
    monkeypatch.setenv("DISCOVERY_HOME", str(tmp_path / "home"))
    _use_source(monkeypatch, catalogue)
    code, envelope = _run(capsys, ["start", "--frame", frame, "--target", "org/repo"])
    session_id = envelope["next_action"]["session_id"]
    return session_id, code, envelope


def _payload(text):
    return f"text: {text}\n"


def _payload_with_broken_trace(text):
    """A payload whose FR-01 traces to a nonexistent G id — a real GC-06 error."""
    return f"text: {text}\nentries:\n  - id: FR-01\n    body: x\n    traces: [G-99]\n"


class TestSharedEnvelope:
    """REQ-001, REQ-002: one five-key envelope, one exit-code priority."""

    def test_every_command_returns_exactly_the_five_contract_keys(
        self, capsys, monkeypatch, tmp_path
    ):
        session_id, code, started = _start(capsys, monkeypatch, tmp_path, ONE_QUESTION)
        assert set(started) == ENVELOPE_KEYS
        assert code == 20

        status_code, status_doc = _run(capsys, ["status", "--session", session_id])
        assert set(status_doc) == ENVELOPE_KEYS
        assert status_code == 20

    def test_awaiting_input_outranks_gate_fail_for_exit_20(
        self, capsys, monkeypatch, tmp_path
    ):
        _, code, envelope = _start(capsys, monkeypatch, tmp_path, ONE_QUESTION)

        assert envelope["lifecycle"] == "awaiting_input"
        assert envelope["gate"] == "fail"
        assert envelope["operation"] == {"status": "ok"}
        assert code == 20

    def test_complete_with_failing_gate_is_exit_10(self, capsys, monkeypatch, tmp_path):
        session_id, _, _ = _start(capsys, monkeypatch, tmp_path, ONE_QUESTION)
        answer_path = tmp_path / "a.yaml"
        answer_path.write_text(_payload_with_broken_trace("an answer"))

        code, envelope = _run(
            capsys,
            [
                "answer",
                "--session",
                session_id,
                "--role",
                "customer",
                "--file",
                str(answer_path),
            ],
        )

        assert envelope["lifecycle"] == "complete"
        assert envelope["gate"] == "fail"
        assert code == 10


class TestQuestionPersistedBeforeReturn:
    """REQ-003: `question_asked` is durable before the command returns."""

    def test_question_asked_event_is_in_the_journal_after_start(
        self, capsys, monkeypatch, tmp_path
    ):
        session_id, _, envelope = _start(capsys, monkeypatch, tmp_path, ONE_QUESTION)

        events = cli._journal(session_id).events()
        asked = [e for e in events if e["event"] == "question_asked"]

        assert len(asked) == 1
        assert asked[0]["question_id"] == "customer.g.01"
        assert envelope["next_action"]["question_id"] == "customer.g.01"

    def test_status_does_not_reissue_an_already_asked_question(
        self, capsys, monkeypatch, tmp_path
    ):
        session_id, _, _ = _start(capsys, monkeypatch, tmp_path, ONE_QUESTION)

        _run(capsys, ["status", "--session", session_id])

        events = cli._journal(session_id).events()
        asked = [e for e in events if e["event"] == "question_asked"]
        assert len(asked) == 1


class TestAnswerNoOpReplay:
    """REQ-004: replaying the same answer_id appends no new event."""

    def test_replaying_the_same_answer_is_a_no_op(self, capsys, monkeypatch, tmp_path):
        session_id, _, _ = _start(capsys, monkeypatch, tmp_path, ONE_QUESTION)
        answer_path = tmp_path / "a.yaml"
        answer_path.write_text(_payload("an answer"))
        argv = [
            "answer",
            "--session",
            session_id,
            "--question",
            "customer.g.01",
            "--role",
            "customer",
            "--file",
            str(answer_path),
        ]

        code1, envelope1 = _run(capsys, argv)
        after_first = cli._journal(session_id).events()
        code2, envelope2 = _run(capsys, argv)
        after_second = cli._journal(session_id).events()

        assert [e for e in after_first if e["event"] == "answer_recorded"]
        assert after_first == after_second
        assert code1 == code2
        assert envelope1 == envelope2
        assert envelope2["operation"] == {"status": "ok"}


class TestAnswerConflict:
    """REQ-005: a conflicting answer without --supersede is refused unchanged."""

    def test_conflicting_answer_without_supersede_is_refused(
        self, capsys, monkeypatch, tmp_path
    ):
        session_id, _, _ = _start(capsys, monkeypatch, tmp_path, ONE_QUESTION)
        first = tmp_path / "a.yaml"
        first.write_text(_payload("first answer"))
        _run(
            capsys,
            [
                "answer",
                "--session",
                session_id,
                "--question",
                "customer.g.01",
                "--role",
                "customer",
                "--file",
                str(first),
            ],
        )
        before = cli._journal(session_id).events()

        second = tmp_path / "b.yaml"
        second.write_text(_payload("a different answer"))
        code, envelope = _run(
            capsys,
            [
                "answer",
                "--session",
                session_id,
                "--question",
                "customer.g.01",
                "--role",
                "customer",
                "--file",
                str(second),
            ],
        )
        after = cli._journal(session_id).events()

        assert code == 2
        assert envelope["operation"] == {
            "status": "refused",
            "reason": "answer_conflict",
        }
        assert envelope["lifecycle"] != "unknown"
        assert envelope["gate"] != "unknown"
        assert after == before


class TestAnswerSupersede:
    """REQ-006: --supersede keeps both events, the original stays readable."""

    def test_supersede_appends_both_events(self, capsys, monkeypatch, tmp_path):
        session_id, _, _ = _start(capsys, monkeypatch, tmp_path, ONE_QUESTION)
        first = tmp_path / "a.yaml"
        first.write_text(_payload("first answer"))
        _run(
            capsys,
            [
                "answer",
                "--session",
                session_id,
                "--question",
                "customer.g.01",
                "--role",
                "customer",
                "--file",
                str(first),
            ],
        )

        second = tmp_path / "b.yaml"
        second.write_text(_payload_with_broken_trace("second answer"))
        code, envelope = _run(
            capsys,
            [
                "answer",
                "--session",
                session_id,
                "--question",
                "customer.g.01",
                "--role",
                "customer",
                "--file",
                str(second),
                "--supersede",
            ],
        )

        events = cli._journal(session_id).events()
        recorded = [e for e in events if e["event"] == "answer_recorded"]
        superseded = [e for e in events if e["event"] == "answer_superseded"]

        assert len(recorded) == 2
        assert len(superseded) == 1
        assert superseded[0]["answer_id"] == recorded[0]["answer_id"]
        assert recorded[1]["answer_id"] != recorded[0]["answer_id"]
        assert envelope["operation"] == {"status": "ok"}
        assert code == 10


class TestUnknownSession:
    """REQ-007: an unreadable session collapses every command to unknown."""

    def test_status_of_unknown_session_is_exit_1(self, capsys, monkeypatch, tmp_path):
        monkeypatch.setenv("DISCOVERY_HOME", str(tmp_path / "home"))
        _use_source(monkeypatch, {})

        code, envelope = _run(capsys, ["status", "--session", "does-not-exist"])

        assert code == 1
        assert envelope["lifecycle"] == "unknown"
        assert envelope["gate"] == "unknown"
        assert envelope["operation"]["status"] == "unknown"

    def test_answer_of_unknown_session_is_exit_1(self, capsys, monkeypatch, tmp_path):
        monkeypatch.setenv("DISCOVERY_HOME", str(tmp_path / "home"))
        _use_source(monkeypatch, {})
        answer_path = tmp_path / "a.yaml"
        answer_path.write_text(_payload("x"))

        code, envelope = _run(
            capsys,
            [
                "answer",
                "--session",
                "does-not-exist",
                "--role",
                "customer",
                "--file",
                str(answer_path),
            ],
        )

        assert code == 1
        assert envelope["lifecycle"] == "unknown"

    def test_brief_of_unknown_session_is_exit_1(self, capsys, monkeypatch, tmp_path):
        monkeypatch.setenv("DISCOVERY_HOME", str(tmp_path / "home"))
        _use_source(monkeypatch, {})

        code, envelope = _run(
            capsys,
            ["brief", "--session", "does-not-exist", "--out", str(tmp_path / "b.md")],
        )

        assert code == 1
        assert envelope["lifecycle"] == "unknown"


class TestSessionLayout:
    """REQ-008: sessions live under $DISCOVERY_HOME/sessions, default ~/.discovery."""

    def test_session_files_live_under_discovery_home_sessions(
        self, capsys, monkeypatch, tmp_path
    ):
        home = tmp_path / "home"
        session_id, _, _ = _start(capsys, monkeypatch, tmp_path, ONE_QUESTION)

        assert (home / "sessions" / session_id / "header.json").exists()
        assert cli.sessions_root() == home / "sessions"

    def test_default_root_is_home_dot_discovery_when_env_unset(self, monkeypatch):
        monkeypatch.delenv("DISCOVERY_HOME", raising=False)

        assert cli.sessions_root() == Path.home() / ".discovery" / "sessions"


class TestDefaultQuestionSource:
    """REQ-009: build_source() defaults to an empty StaticQuestionSource."""

    def test_build_source_defaults_to_an_empty_static_source(self):
        source = cli.build_source()

        assert isinstance(source, StaticQuestionSource)
        assert source.pin == "unpinned"
        assert source.questions("customer") == []


class TestDeterminism:
    """NFR-001: repeated calls over an unchanged journal agree."""

    def test_repeated_status_call_on_unchanged_journal_is_identical(
        self, capsys, monkeypatch, tmp_path
    ):
        session_id, _, _ = _start(capsys, monkeypatch, tmp_path, ONE_QUESTION)

        code1, envelope1 = _run(capsys, ["status", "--session", session_id])
        code2, envelope2 = _run(capsys, ["status", "--session", session_id])

        assert code1 == code2
        assert envelope1 == envelope2


class TestBrief:
    """cmd_brief: renders+gates into --out, the only write outside the session root."""

    def test_brief_writes_out_path_and_reflects_current_state(
        self, capsys, monkeypatch, tmp_path
    ):
        session_id, _, _ = _start(capsys, monkeypatch, tmp_path, ONE_QUESTION)
        answer_path = tmp_path / "a.yaml"
        answer_path.write_text(_payload_with_broken_trace("an answer"))
        _run(
            capsys,
            [
                "answer",
                "--session",
                session_id,
                "--role",
                "customer",
                "--file",
                str(answer_path),
            ],
        )
        out_path = tmp_path / "brief.md"

        code, envelope = _run(
            capsys, ["brief", "--session", session_id, "--out", str(out_path)]
        )

        assert out_path.exists()
        assert envelope["lifecycle"] == "complete"
        assert code == 10
