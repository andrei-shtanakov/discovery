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
        # Every bank question answered with prose only: the brief is a stub.
        # Until contract v1.2 the linter had nothing to object to (gate pass,
        # readiness incomplete, exit 11 — the finding of 2026-08-19). From
        # v1.3 the customer linter itself demands the translation table,
        # perf/cost NFRs and named owners, so the stub fails the gate.
        assert envelope["gate"] == "fail"
        assert envelope["readiness"] == "incomplete"
        assert code == 10
        assert any("goals" in f for f in envelope["readiness_findings"])
        rules = {f.split()[0] for f in envelope["findings"]}
        assert {"GC-18", "GC-20", "GC-21"} <= rules

        out_path = tmp_path / "brief.md"
        code, envelope = drive(
            ["brief", "--session", session_id, "--out", str(out_path)], capsys
        )
        assert code == 10
        assert out_path.exists()

        findings = gate_check.check(
            out_path.read_text(encoding="utf-8"), base_dir=out_path.parent
        )
        assert isinstance(findings, list)
        assert all(f.level in {"error", "warning"} and f.message for f in findings)


# One answer carrying a whole v1.3-complete customer brief (contract v1.3:
# translation table, NFR categories, owner domains).
_V13_COMPLETE = """\
text: everything at once
translations:
  - words: «экспорт за секунды»
    category: делать
    constraint: FR-01
  - words: «внешнее не трогать»
    category: не делать
    constraint: OUT-01
  - words: «быстро и недорого»
    category: стоить
    constraint: [NFR-01, NFR-02]
    assumption: «быстро» = p95 до 2 с
    confirmer: product-owner
    due: 2026-12-01
  - words: «только на наших серверах»
    category: доказывать
    constraint: CON-01
entries:
  - id: G-01
    body: a goal
  - id: P-01
    body: the sponsor
    owns: [process, data, quality, operations]
  - id: J-01
    body: a job
  - id: FR-01
    body: a function
    Priority: Must
    Acceptance: exports complete within 5 s
    traces: [G-01]
  - id: NFR-01
    body: latency
    Category: perf
    Target: p95 under 2 s
  - id: NFR-02
    body: budget
    Category: cost
    Target: at most 300 $ a month
  - id: CON-01
    body: a constraint
  - id: M-01
    body: a success metric
    traces: [G-01]
  - id: OUT-01
    body: an out-of-scope item
"""


class TestCustomerInterviewReachesReady:
    """The real v1.3 bank plus one complete answer reaches exit 0."""

    def test_a_v13_complete_answer_passes_the_gate_and_is_ready(self, tmp_path, capsys):
        code, envelope = drive(
            ["start", "--frame", "customer", "--target", "org/repo"], capsys
        )
        session_id = envelope["next_action"]["session_id"]
        answer_path = tmp_path / "answer.yaml"
        answer_path.write_text(_V13_COMPLETE, encoding="utf-8")
        argv = ["answer", "--session", session_id, "--role", "customer"]

        code, envelope = drive([*argv, "--file", str(answer_path)], capsys)
        answer_path.write_text("text: nothing to add\n", encoding="utf-8")
        for _ in range(200):
            if code != 20:
                break
            code, envelope = drive([*argv, "--file", str(answer_path)], capsys)

        assert envelope["findings"] == []
        assert envelope["gate"] == "pass"
        assert envelope["readiness"] == "ready"
        assert code == 0
