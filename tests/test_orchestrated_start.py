"""Orchestrated start: `--upstream` and a caller-assigned `--session-id`.

Both flags exist for a caller that drives the interview from a run of its
own (discovery#49). Each case isolates one claim:

`--upstream` admits an upstream customer brief through the *public* CLI —
the caller may not write into `$DISCOVERY_HOME` itself — by copying it
into the session under the fixed name `upstream.md` and putting that name
first in `traces_to`. The name is fixed, not the source's basename,
because a basename colliding with the final brief's own file name would
make `traces_to` resolve to the brief itself: GC-16 green, GC-05 checking
the document against itself, every upstream Must-FR trivially "mentioned".

Four invariants guard the admission: the source is validated *before* a
session exists, so an interview cannot be half-run against the wrong
source; `header.json` is written *last*, as the session's commit marker,
so a crash cannot leave a readable session pointing at a missing file;
`upstream.md` is reserved, so a second claim on the name via `--traces-to`
is refused as ambiguous; and `brief --out .../upstream.md` is refused,
because the fixed name removes the ordinary collision but an arbitrary
`--out` still permits the self-reference.

`--session-id` lets the caller write the id ahead of the call, which is
what removes orphaned "session created, record never written" states by
construction. A taken id is refused without touching what is already
there.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from discovery import cli
from discovery.contract import gate_check

APPROVED_UPSTREAM = """---
schema: discovery-brief
schema_version: 1
spec_stage: discovery
status: approved
generated_by: discovery-toolkit
generated_at: 2026-09-18T00:00:00Z
validation: pass
traces_to: []
open_questions: 0
blocking_open_questions: 0
conflicts: 0
interview:
  frame: customer
  sessions:
    - participant_role: customer
coverage:
  goals: covered
  personas: covered
  jobs: covered
  functions: covered
  nfr: covered
  constraints: covered
  success_metrics: covered
  out_of_scope: covered
  gate_passed: true
---

# Discovery brief: acme/widgets

## Goals

- **G-01** cut failed courier calls by half

## Personas

- **P-01** dispatcher on the night shift

## Jobs

- **J-01** retry a call without leaving the queue view

## Functional requirements

- **FR-01** retry a timed-out courier call
  **Priority**: Must
  **Acceptance**: a timed-out call is retried within 30s
  traces: [G-01]

## Non-functional requirements

- **NFR-01** retry latency
  **Target**: p95 under 30s

## Constraints

- **CON-01** no changes to the courier API

## Success metrics

- **M-01** failed calls per shift
  traces: [G-01]

## Out of scope

- **OUT-01** courier-side retries
"""


@pytest.fixture(autouse=True)
def _discovery_home(monkeypatch, tmp_path):
    """Isolate every case's sessions under its own tmp_path, never `~/.discovery`."""
    monkeypatch.setenv("DISCOVERY_HOME", str(tmp_path / "home"))


def drive(argv: list[str], capsys) -> tuple[int, dict]:
    """Run `cli.main(argv)` and return `(exit_code, parsed envelope)`."""
    code = cli.main(argv)
    envelope = json.loads(capsys.readouterr().out)
    return code, envelope


def write_upstream(tmp_path: Path, text: str = APPROVED_UPSTREAM) -> Path:
    """An upstream customer brief on disk, outside the session root."""
    path = tmp_path / "source" / "customer-brief.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def start_engineer(capsys, tmp_path, *extra: str) -> tuple[int, dict]:
    """`start --frame engineer --upstream <approved brief>` plus `extra`."""
    upstream = write_upstream(tmp_path)
    return drive(
        [
            "start",
            "--frame",
            "engineer",
            "--target",
            "org/repo",
            "--upstream",
            str(upstream),
            *extra,
        ],
        capsys,
    )


def session_ids(tmp_path: Path) -> list[str]:
    """Every session directory currently under the isolated sessions root."""
    root = tmp_path / "home" / "sessions"
    return sorted(p.name for p in root.iterdir()) if root.exists() else []


def header_of(tmp_path: Path, session_id: str) -> dict:
    """The raw `header.json` of one session."""
    path = tmp_path / "home" / "sessions" / session_id / "header.json"
    return json.loads(path.read_text(encoding="utf-8"))


class TestUpstreamAdmission:
    """`--upstream` copies the source in under a fixed, first-listed name."""

    def test_upstream_is_copied_into_the_session_under_the_fixed_name(
        self, capsys, tmp_path
    ):
        code, envelope = start_engineer(capsys, tmp_path)

        assert code == 20
        session_id = envelope["next_action"]["session_id"]
        copy = tmp_path / "home" / "sessions" / session_id / "upstream.md"
        assert copy.read_text(encoding="utf-8") == APPROVED_UPSTREAM

    def test_the_copy_is_traced_to_by_its_fixed_name_not_the_source_basename(
        self, capsys, tmp_path
    ):
        _, envelope = start_engineer(capsys, tmp_path)

        header = header_of(tmp_path, envelope["next_action"]["session_id"])
        assert header["traces_to"] == ["upstream.md"]

    def test_the_copy_precedes_every_explicitly_passed_traces_to(
        self, capsys, tmp_path
    ):
        """`gate_check` takes the *first* resolvable ref as the upstream brief,
        so the admitted copy has to come before anything the caller passed."""
        _, envelope = start_engineer(
            capsys, tmp_path, "--traces-to", "other.md", "--traces-to", "third.md"
        )

        header = header_of(tmp_path, envelope["next_action"]["session_id"])
        assert header["traces_to"] == ["upstream.md", "other.md", "third.md"]


class TestUpstreamRefusals:
    """A source that cannot serve as upstream is refused before a session exists."""

    def test_upstream_is_refused_for_the_customer_frame(self, capsys, tmp_path):
        upstream = write_upstream(tmp_path)

        code, envelope = drive(
            [
                "start",
                "--frame",
                "customer",
                "--target",
                "org/repo",
                "--upstream",
                str(upstream),
            ],
            capsys,
        )

        assert code == 1
        assert envelope["operation"]["status"] == "unknown"
        assert session_ids(tmp_path) == []

    def test_upstream_that_is_not_markdown_is_refused(self, capsys, tmp_path):
        """A non-`.md` ref never enters `gate_check`'s `path_refs`, so GC-16,
        GC-12 and GC-05 would all silently skip it — an unchecked reference
        handed on as a working one."""
        source = tmp_path / "source" / "customer-brief.txt"
        source.parent.mkdir(parents=True, exist_ok=True)
        source.write_text(APPROVED_UPSTREAM, encoding="utf-8")

        code, envelope = drive(
            [
                "start",
                "--frame",
                "engineer",
                "--target",
                "org/repo",
                "--upstream",
                str(source),
            ],
            capsys,
        )

        assert code == 1
        assert session_ids(tmp_path) == []

    def test_missing_upstream_file_is_refused(self, capsys, tmp_path):
        code, _ = drive(
            [
                "start",
                "--frame",
                "engineer",
                "--target",
                "org/repo",
                "--upstream",
                str(tmp_path / "nowhere.md"),
            ],
            capsys,
        )

        assert code == 1
        assert session_ids(tmp_path) == []

    @pytest.mark.parametrize(
        "mutate,why",
        [
            (
                lambda t: t.replace("status: approved", "status: draft"),
                "an unapproved upstream is what GC-12 exists to reject",
            ),
            (
                lambda t: t.replace("frame: customer", "frame: engineer"),
                "an engineer brief is not an upstream for the engineer frame",
            ),
            (
                lambda t: t.replace("schema: discovery-brief", "schema: tasks"),
                "a document that is not a discovery-brief at all",
            ),
            (
                lambda t: t.replace("  **Priority**: Must\n", ""),
                "a brief the vendored linter reports errors on (GC-08, GC-11)",
            ),
            (
                lambda t: t.split("---\n", 2)[2],
                "a document with no frontmatter to read",
            ),
        ],
    )
    def test_upstream_that_is_not_an_approved_customer_brief_is_refused(
        self, capsys, tmp_path, mutate, why
    ):
        """Validation happens before the session exists: otherwise almost a
        whole engineer interview can be run against the wrong source."""
        upstream = write_upstream(tmp_path, mutate(APPROVED_UPSTREAM))

        code, envelope = drive(
            [
                "start",
                "--frame",
                "engineer",
                "--target",
                "org/repo",
                "--upstream",
                str(upstream),
            ],
            capsys,
        )

        assert code == 1, why
        assert envelope["operation"]["status"] == "unknown"
        assert session_ids(tmp_path) == [], why

    def test_traces_to_claiming_the_reserved_name_alongside_upstream_is_refused(
        self, capsys, tmp_path
    ):
        code, _ = start_engineer(capsys, tmp_path, "--traces-to", "upstream.md")

        assert code == 1
        assert session_ids(tmp_path) == []


class TestHeaderIsTheCommitMarker:
    """`header.json` is written last, after the session's other files."""

    def test_a_crash_before_the_header_leaves_no_readable_session(
        self, capsys, tmp_path, monkeypatch
    ):
        """Were the header written first, the crash would leave a readable
        session whose `traces_to` names a file that does not exist."""
        from discovery import session as session_module

        real_write = session_module._atomic_write

        def fail_on_header(path: Path, text: str) -> None:
            if path.name == "header.json":
                raise OSError("disk full")
            real_write(path, text)

        monkeypatch.setattr(session_module, "_atomic_write", fail_on_header)

        code, _ = start_engineer(capsys, tmp_path)

        assert code == 1
        created = session_ids(tmp_path)
        assert created != [], "the directory is reserved before anything is written"
        session_dir = tmp_path / "home" / "sessions" / created[0]
        assert (session_dir / "upstream.md").exists()
        assert not (session_dir / "header.json").exists()

        code, envelope = drive(["status", "--session", created[0]], capsys)
        assert code == 1
        assert envelope["lifecycle"] == "unknown"


class TestCallerAssignedSessionId:
    """`--session-id` is used verbatim, validated, and never silently reused."""

    def test_caller_assigned_id_is_used_verbatim(self, capsys, tmp_path):
        code, envelope = drive(
            [
                "start",
                "--frame",
                "customer",
                "--target",
                "org/repo",
                "--session-id",
                "run-2026-09-18-01",
            ],
            capsys,
        )

        assert code == 20
        assert envelope["next_action"]["session_id"] == "run-2026-09-18-01"
        assert session_ids(tmp_path) == ["run-2026-09-18-01"]

    @pytest.mark.parametrize("bad", ["..", ".", "../escape", "a/b", ""])
    def test_invalid_caller_assigned_id_is_refused(self, capsys, tmp_path, bad):
        code, envelope = drive(
            [
                "start",
                "--frame",
                "customer",
                "--target",
                "org/repo",
                "--session-id",
                bad,
            ],
            capsys,
        )

        assert code == 1
        assert envelope["operation"]["status"] == "unknown"
        assert session_ids(tmp_path) == []

    def test_taken_id_is_refused_leaving_the_existing_session_untouched(
        self, capsys, tmp_path
    ):
        """Without this, a repeated id overwrites a live session's header."""
        drive(
            [
                "start",
                "--frame",
                "customer",
                "--target",
                "org/repo",
                "--session-id",
                "run-01",
            ],
            capsys,
        )
        session_dir = tmp_path / "home" / "sessions" / "run-01"
        before = {
            p.name: p.read_bytes() for p in sorted(session_dir.iterdir()) if p.is_file()
        }

        code, envelope = drive(
            [
                "start",
                "--frame",
                "engineer",
                "--target",
                "other/repo",
                "--session-id",
                "run-01",
            ],
            capsys,
        )

        assert code == 1
        assert envelope["operation"]["status"] == "unknown"
        after = {
            p.name: p.read_bytes() for p in sorted(session_dir.iterdir()) if p.is_file()
        }
        assert after == before


class TestBriefOutCannotShadowTheUpstreamCopy:
    """`brief --out .../upstream.md` would make the brief its own upstream."""

    def test_brief_out_named_like_the_reserved_copy_is_refused(self, capsys, tmp_path):
        _, envelope = start_engineer(capsys, tmp_path)
        session_id = envelope["next_action"]["session_id"]
        out = tmp_path / "out" / "upstream.md"
        out.parent.mkdir(parents=True, exist_ok=True)

        code, _ = drive(["brief", "--session", session_id, "--out", str(out)], capsys)

        assert code == 1
        assert not out.exists()

    def test_any_other_out_name_is_still_written(self, capsys, tmp_path):
        _, envelope = start_engineer(capsys, tmp_path)
        session_id = envelope["next_action"]["session_id"]
        out = tmp_path / "out" / "brief.md"
        out.parent.mkdir(parents=True, exist_ok=True)

        drive(["brief", "--session", session_id, "--out", str(out)], capsys)

        assert out.exists()


class TestPortableTracesToAcceptance:
    """discovery#49's "done" criterion, against the real vendored bank.

    `brief --out` produces a brief whose `traces_to` resolves relative to the
    brief itself once the caller's own durable copy sits beside it — and the
    negative control proves the assertion has teeth: without that copy the
    very same brief fails GC-16.
    """

    def test_engineer_brief_traces_to_resolves_beside_the_brief(self, capsys, tmp_path):
        _, envelope = start_engineer(capsys, tmp_path)
        session_id = envelope["next_action"]["session_id"]

        code = 20
        guard = 0
        answer_path = tmp_path / "answer.yaml"
        while code == 20:
            guard += 1
            assert guard <= 200, "the engineer answer cycle did not converge"
            code, envelope = drive(["status", "--session", session_id], capsys)
            if code != 20:
                break
            answer_path.write_text(
                f"text: FR-01 is feasible; synthetic answer {guard}\n",
                encoding="utf-8",
            )
            code, envelope = drive(
                [
                    "answer",
                    "--session",
                    session_id,
                    "--role",
                    "engineer",
                    "--file",
                    str(answer_path),
                ],
                capsys,
            )

        out_dir = tmp_path / "run" / "brief-input" / "00-discovery"
        out_dir.mkdir(parents=True, exist_ok=True)
        out = out_dir / "brief.md"
        drive(["brief", "--session", session_id, "--out", str(out)], capsys)

        brief_text = out.read_text(encoding="utf-8")
        assert "traces_to:\n- upstream.md\n" in brief_text

        # The caller keeps its own durable copy of the same file beside the brief.
        (out_dir / "upstream.md").write_text(APPROVED_UPSTREAM, encoding="utf-8")
        findings = gate_check.check(brief_text, base_dir=out_dir)
        assert [f for f in findings if f.rule == "GC-16"] == []
        assert [f for f in findings if f.rule == "GC-12" and f.level == "error"] == []

        # Negative control: the same brief, no copy beside it, fails GC-16.
        bare = tmp_path / "bare"
        bare.mkdir()
        bare_findings = gate_check.check(brief_text, base_dir=bare)
        assert [f for f in bare_findings if f.rule == "GC-16"] != []
