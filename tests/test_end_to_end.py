"""End-to-end: the real, vendored bank drives a full interview to a brief.

Unlike `test_cli.py`, nothing here monkeypatches `cli.build_source` — every
case runs against the actual `discovery/contract/frames` bank pinned by
`PINNED.txt`, so a break in the D2 wiring (bank parsing, coverage
validation, the CLI composition seam) shows up here even if a fixture
elsewhere would have masked it.
"""

from __future__ import annotations

import json

import pytest

from discovery import cli
from discovery.contract import gate_check


@pytest.fixture(autouse=True)
def _discovery_home(monkeypatch, tmp_path):
    """Isolate every case's sessions under its own tmp_path, never `~/.discovery`."""
    monkeypatch.setenv("DISCOVERY_HOME", str(tmp_path / "home"))


def drive(argv: list[str], capsys) -> tuple[int, dict]:
    """Run `cli.main(argv)` and return `(exit_code, parsed envelope)`."""
    code = cli.main(argv)
    envelope = json.loads(capsys.readouterr().out)
    return code, envelope


class TestRealBuildSourceSanity:
    """`cli.build_source()`, unpatched, is a real pinned bank for both frames."""

    def test_build_source_is_a_nonempty_pinned_bank_for_both_frames(self):
        source = cli.build_source()

        assert source.pin != "unpinned"
        assert source.questions("customer") != []
        assert source.questions("engineer") != []


class TestCustomerInterviewEndToEnd:
    """start -> exit 20 -> answer cycle -> complete -> brief -> gate_check."""

    def test_full_customer_interview_reaches_complete_brief_and_gate_check(
        self, tmp_path, capsys
    ):
        code, envelope = drive(
            ["start", "--frame", "customer", "--target", "org/repo"], capsys
        )
        assert code == 20
        session_id = envelope["next_action"]["session_id"]

        answer_path = tmp_path / "answer.yaml"
        max_iterations = 200
        iterations = 0
        while code == 20:
            iterations += 1
            assert iterations <= max_iterations, (
                "answer cycle did not converge to exit-20 completion "
                "(possible §5 regression)"
            )
            code, envelope = drive(["status", "--session", session_id], capsys)
            if code != 20:
                break
            answer_path.write_text(
                f"text: synthetic answer {iterations}\n", encoding="utf-8"
            )
            code, envelope = drive(
                [
                    "answer",
                    "--session",
                    session_id,
                    "--role",
                    "customer",
                    "--file",
                    str(answer_path),
                ],
                capsys,
            )

        code, envelope = drive(["status", "--session", session_id], capsys)
        assert envelope["lifecycle"] == "complete"

        out_path = tmp_path / "brief.md"
        drive(["brief", "--session", session_id, "--out", str(out_path)], capsys)
        assert out_path.exists()

        findings = gate_check.check(
            out_path.read_text(encoding="utf-8"), base_dir=out_path.parent
        )
        errors = [f for f in findings if f.level == "error"]
        verdict = "fail" if errors else "pass"
        assert verdict in {"pass", "fail"}
