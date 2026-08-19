"""Frozen RED checkpoint for TASK-012.

This file is byte-frozen until the task is done: it exists to prove that,
at the moment the task started, `discovery.cli` did not yet exist, so a
`start` -> `status` round trip could not be shown to persist the issued
question under `$DISCOVERY_HOME/sessions` before the command returns —
DESIGN-007's envelope contract (`awaiting_input` -> exit code 20) — nor
that a fresh process resuming the same session sees the very same
`next_action.question_id` instead of re-issuing a different one.
"""

from __future__ import annotations

import json


class TestCliStartStatusRed:
    def test_start_then_status_resumes_the_same_question(
        self, tmp_path, monkeypatch, capsys
    ):
        monkeypatch.setenv("DISCOVERY_HOME", str(tmp_path / "home"))

        from discovery import cli
        from discovery.questions import Question, StaticQuestionSource

        catalogue = {
            "customer": [
                Question("customer.goals.01", "goals", "What problem?"),
                Question("customer.jobs.01", "jobs", "Recent case?"),
            ]
        }
        monkeypatch.setattr(
            cli, "build_source", lambda: StaticQuestionSource("pin-1", catalogue)
        )

        start_code = cli.main(["start", "--frame", "customer", "--target", "org/repo"])
        started = json.loads(capsys.readouterr().out)
        assert start_code == 20
        assert started["lifecycle"] == "awaiting_input"
        assert started["next_action"]["question_id"] == "customer.goals.01"

        session_id = started["next_action"]["session_id"]
        status_code = cli.main(["status", "--session", session_id])
        status_doc = json.loads(capsys.readouterr().out)

        assert status_code == 20
        assert status_doc["next_action"]["question_id"] == "customer.goals.01"
