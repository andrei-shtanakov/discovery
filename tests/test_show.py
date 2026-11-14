"""`discovery show` — the public, read-only view of one session (issue #70).

The claims: `show` projects the same three axes as `status` plus a `session`
view (entries, holders, asked questions, answers, coverage, topics); it
writes nothing, so a question the bank would issue next is not issued by
looking; and an unreadable session is `unknown` with no view at all.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from discovery import cli
from discovery.questions import Question, StaticQuestionSource

TWO_QUESTIONS = {
    "customer": [
        Question("customer.goals.01", "goals", "What problem?"),
        Question("customer.functions.01", "functions", "What must it do?"),
    ]
}

GOALS_ANSWER = """\
text: couriers time out
entries:
  - id: G-01
    body: cut failed calls
  - id: G-02
    body: dropped later
"""

GOALS_SUPERSEDING = """\
text: couriers time out, revised
entries:
  - id: G-01
    body: cut failed calls by half
"""

FUNCTIONS_ANSWER = """\
text: retries
entries:
  - id: FR-01
    body: retry a timed-out call
    Priority: Must
    Acceptance: retried within 30s
    traces: [G-01]
"""


def _run(capsys, argv: list[str]) -> tuple[int, dict]:
    code = cli.main(argv)
    return code, json.loads(capsys.readouterr().out)


def _answer(capsys, tmp_path: Path, session_id: str, text: str, *extra: str) -> int:
    path = tmp_path / "answer.yaml"
    path.write_text(text, encoding="utf-8")
    argv = ["answer", "--session", session_id, "--role", "customer"]
    code, _ = _run(capsys, [*argv, "--file", str(path), *extra])
    return code


@pytest.fixture
def session_id(capsys, monkeypatch, tmp_path) -> str:
    """A customer session over a two-question static bank."""
    monkeypatch.setenv("DISCOVERY_HOME", str(tmp_path / "home"))
    source = StaticQuestionSource("pin-test", TWO_QUESTIONS)
    monkeypatch.setattr(cli, "build_source", lambda: source)
    _, started = _run(capsys, ["start", "--frame", "customer", "--target", "o/r"])
    return started["next_action"]["session_id"]


def _snapshot(root: Path) -> dict[str, bytes]:
    return {str(p): p.read_bytes() for p in sorted(root.rglob("*")) if p.is_file()}


class TestAxes:
    def test_axes_and_exit_code_match_status(self, capsys, session_id):
        status_code, status = _run(capsys, ["status", "--session", session_id])
        code, shown = _run(capsys, ["show", "--session", session_id])

        assert code == status_code == 20
        for key in ("lifecycle", "gate", "readiness", "findings", "next_action"):
            assert shown[key] == status[key]
        assert shown["readiness_findings"] == status["readiness_findings"]

    def test_other_commands_keep_the_seven_keys(self, capsys, session_id):
        _, status = _run(capsys, ["status", "--session", session_id])

        assert "session" not in status


class TestReadOnly:
    def test_show_writes_nothing(self, capsys, session_id, tmp_path):
        before = _snapshot(tmp_path / "home")

        _run(capsys, ["show", "--session", session_id])

        assert _snapshot(tmp_path / "home") == before

    def test_show_does_not_issue_the_next_question(
        self, capsys, monkeypatch, session_id, tmp_path
    ):
        # A re-pinned bank grows a question nobody has been asked yet: `status`
        # would issue it, `show` only reports what is already pending.
        _answer(capsys, tmp_path, session_id, GOALS_ANSWER)
        _answer(capsys, tmp_path, session_id, FUNCTIONS_ANSWER)
        grown = {
            "customer": [
                *TWO_QUESTIONS["customer"],
                Question("customer.nfr.01", "nfr", "How fast?"),
            ]
        }
        source = StaticQuestionSource("pin-test", grown)
        monkeypatch.setattr(cli, "build_source", lambda: source)
        before = _snapshot(tmp_path / "home")

        code, shown = _run(capsys, ["show", "--session", session_id])

        assert _snapshot(tmp_path / "home") == before
        assert shown["lifecycle"] == "awaiting_input"
        assert shown["next_action"] == {}
        assert code == 20


class TestSessionView:
    def test_header_topics_and_pending_question(self, capsys, session_id):
        _, shown = _run(capsys, ["show", "--session", session_id])
        view = shown["session"]

        assert view["session_id"] == session_id
        assert view["frame"] == "customer"
        assert view["target"] == "o/r"
        assert view["topics"]["required"]["goals"] == "G"
        assert view["asked"] == [
            {
                "question_id": "customer.goals.01",
                "coverage_key": "goals",
                "question_text": "What problem?",
            }
        ]
        assert view["answers"] == []
        assert view["coverage"]["goals"] == "missing"

    def test_entries_holders_declared_and_answers(self, capsys, session_id, tmp_path):
        _answer(capsys, tmp_path, session_id, GOALS_ANSWER)
        _answer(capsys, tmp_path, session_id, FUNCTIONS_ANSWER)
        argv = ("--question", "customer.goals.01", "--supersede")
        _answer(capsys, tmp_path, session_id, GOALS_SUPERSEDING, *argv)

        code, shown = _run(capsys, ["show", "--session", session_id])
        view = shown["session"]

        assert code == shown_code_of(shown)
        # The brief's own projection: the superseding goals answer landed
        # after the functions one, so its entries follow; G-02 was dropped.
        assert view["entries"] == [
            {
                "id": "FR-01",
                "body": "retry a timed-out call",
                "fields": {
                    "Priority": "Must",
                    "Acceptance": "retried within 30s",
                    "traces": ["G-01"],
                },
            },
            {"id": "G-01", "body": "cut failed calls by half", "fields": {}},
        ]
        assert view["declared"] == ["G-01", "G-02", "FR-01"]
        assert view["holders"] == {
            "G-01": "customer.goals.01",
            "FR-01": "customer.functions.01",
        }
        assert [a["question_id"] for a in view["answers"]] == [
            "customer.functions.01",
            "customer.goals.01",
        ]
        latest = view["answers"][1]
        assert latest["participant_role"] == "customer"
        assert latest["payload"]["text"] == "couriers time out, revised"
        assert latest["answer_id"]
        assert view["coverage"]["goals"] == "covered"
        assert view["coverage"]["functions"] == "covered"


def shown_code_of(envelope: dict) -> int:
    """The exit code the envelope projects, through the one ranked function."""
    from discovery.protocol import Envelope, exit_code

    return exit_code(
        Envelope(
            lifecycle=envelope["lifecycle"],
            gate=envelope["gate"],
            readiness=envelope["readiness"],
            operation=envelope["operation"],
        )
    )


class TestUnreadable:
    def test_unknown_session_is_exit_1_without_a_view(
        self, capsys, monkeypatch, tmp_path
    ):
        monkeypatch.setenv("DISCOVERY_HOME", str(tmp_path / "home"))

        code, shown = _run(capsys, ["show", "--session", "s-missing"])

        assert code == 1
        assert shown["operation"]["status"] == "unknown"
        assert "session" not in shown
