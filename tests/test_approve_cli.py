"""`discovery approve <brief> --repo <owner/name> --pr <n>` (discovery#55).

The act of approval is a human merging the brief's PR; the command only
mirrors that fact onto the file. Each case isolates one claim, over a
`FakeForge` replacing `cli.build_forge` (the composition seam), never a
network:

A brief whose PR was merged by an allowlisted human is stamped `approved`
with the four contract fields and the self-hash, and nothing else in the
file changes. Every denial leaves the file untouched and refuses (exit 2)
with a machine reason: the PR is not merged; the merger is not on the
allowlist; the PR did not change the brief; the merged bytes differ from
the local ones. The one exception is a brief that *claims* `approved`
while its bytes no longer match what was merged: the claim is withdrawn
(`draft`) — git holds no such approval, and the file mirrors git.

Facts that cannot be established — the forge unreachable, a merged PR with
an incomplete event, the policy repository unreadable — are `unknown`
(exit 1) and write nothing. The allowlist comes from the policy repository
only: a set `AUTHORIZED_APPROVER_ACCOUNTS` is a named refusal, not a
source (devtools S7). Evidence of the merge is never taken from a file or
a flag: a forged signature is exactly what the act removes.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

import pytest

from discovery import approval, cli, policy, protocol
from discovery.contract.gate_check import split_frontmatter
from discovery.forge import ForgeUnavailable, PullRequest

REPO = "org/polygon"
PR = 7
BRIEF_PATH = "docs/discovery/brief.md"
POLICY_REPO, POLICY_REF, POLICY_PATH = policy.source()
POLICY_SHA = "feedfacefeedfacefeedfacefeedfacefeedface"
MERGE_SHA = "0123456789abcdef0123456789abcdef01234567"
HUMAN = "andrei-shtanakov"

DRAFT = """---
schema: discovery-brief
schema_version: 1
spec_stage: discovery
status: draft
generated_by: discovery-runtime
generated_at: '2026-09-22T00:00:00Z'
validation: pass
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
open_questions: 0
blocking_open_questions: 0
conflicts: 0
traces_to: []
---

# Discovery Brief — org/polygon (customer-фрейм)

## Goals

- **G-01** cut failed courier calls by half

## Personas

- **P-01** dispatcher on the night shift

## Jobs-to-be-done

- **J-01** retry a call without leaving the queue view

## Functional Requirements

- **FR-01** retry a timed-out courier call
  **Priority**: Must
  **Acceptance**: a timed-out call is retried within 30s
  traces: [G-01]

## Non-Functional

- **NFR-01** retry latency
  **Target**: p95 under 30s

## Constraints

- **CON-01** no changes to the courier API

## Success Metrics

- **M-01** failed calls per shift
  traces: [G-01]

## Out of Scope

- **OUT-01** courier-side retries
"""

MERGED = PullRequest("MERGED", HUMAN, "2026-09-22T10:00:00Z", MERGE_SHA)


@dataclass
class FakeForge:
    """A forge whose every answer is a fixture; `calls` records the reads."""

    pr: PullRequest = MERGED
    files: list[str] = field(default_factory=lambda: [BRIEF_PATH])
    merged_text: str | None = DRAFT
    policy_text: str | None = f"{policy.ALLOWLIST_KEY}={HUMAN}\n"
    policy_sha: str | None = POLICY_SHA
    down: bool = False
    calls: list[tuple] = field(default_factory=list)

    def _up(self) -> None:
        if self.down:
            raise ForgeUnavailable("gh: connection refused")

    def pull_request(self, repo: str, number: int) -> PullRequest:
        self._up()
        self.calls.append(("pull_request", repo, number))
        return self.pr

    def pull_request_files(self, repo: str, number: int) -> list[str]:
        self._up()
        self.calls.append(("pull_request_files", repo, number))
        return self.files

    def file_at(self, repo: str, commit: str, path: str) -> str | None:
        self._up()
        self.calls.append(("file_at", repo, commit, path))
        if repo == POLICY_REPO:
            return self.policy_text
        return self.merged_text

    def latest_commit_touching(self, repo: str, ref: str, path: str) -> str | None:
        self._up()
        self.calls.append(("latest_commit_touching", repo, ref, path))
        return self.policy_sha


@pytest.fixture
def forge(monkeypatch):
    fake = FakeForge()
    monkeypatch.setattr(cli, "build_forge", lambda: fake)
    monkeypatch.delenv(policy.ALLOWLIST_KEY, raising=False)
    return fake


@pytest.fixture
def brief(tmp_path, monkeypatch):
    """The brief at its repository-relative path, cwd at the repository root."""
    monkeypatch.chdir(tmp_path)
    path = Path(BRIEF_PATH)
    path.parent.mkdir(parents=True)
    path.write_text(DRAFT, encoding="utf-8")
    return path


def _approve(capsys, *extra):
    code = cli.main(["approve", BRIEF_PATH, "--repo", REPO, "--pr", str(PR), *extra])
    return code, json.loads(capsys.readouterr().out)


def _meta(path: Path) -> dict:
    meta, _ = split_frontmatter(path.read_text(encoding="utf-8"))
    assert meta is not None
    return meta


class TestMirror:
    def test_merged_by_an_allowlisted_human_stamps_approved(self, capsys, forge, brief):
        code, envelope = _approve(capsys)

        assert envelope["operation"] == {"status": "ok"}
        assert code == 0, envelope
        meta = _meta(brief)
        assert meta["status"] == "approved"
        assert meta["approved_by"] == "discovery-runtime"
        assert meta["approved_at"] == MERGED.merged_at
        assert meta["approver"] == HUMAN
        assert meta[approval.SELF_HASH_KEY] == approval.self_hash(DRAFT)

    def test_stamping_changes_nothing_outside_the_envelope(self, capsys, forge, brief):
        _approve(capsys)

        assert approval.withdraw(brief.read_text(encoding="utf-8")) == DRAFT

    def test_is_idempotent(self, capsys, forge, brief):
        _approve(capsys)
        once = brief.read_bytes()
        code, _ = _approve(capsys)

        assert code == 0
        assert brief.read_bytes() == once

    def test_asks_the_forge_for_the_pr_the_files_and_the_merged_bytes(
        self, capsys, forge, brief
    ):
        _approve(capsys)

        assert ("pull_request", REPO, PR) in forge.calls
        assert ("pull_request_files", REPO, PR) in forge.calls
        assert ("file_at", REPO, MERGE_SHA, BRIEF_PATH) in forge.calls

    def test_path_flag_names_the_file_in_the_repository(
        self, capsys, forge, brief, tmp_path
    ):
        forge.files = ["elsewhere/brief.md"]
        code = cli.main(
            [
                "approve",
                str(tmp_path / BRIEF_PATH),
                "--repo",
                REPO,
                "--pr",
                str(PR),
                "--path",
                "elsewhere/brief.md",
            ]
        )
        envelope = json.loads(capsys.readouterr().out)

        assert code == 0, envelope
        assert ("file_at", REPO, MERGE_SHA, "elsewhere/brief.md") in forge.calls

    def test_absolute_brief_without_path_decides_nothing(
        self, capsys, forge, brief, tmp_path
    ):
        code = cli.main(
            ["approve", str(tmp_path / BRIEF_PATH), "--repo", REPO, "--pr", str(PR)]
        )
        envelope = json.loads(capsys.readouterr().out)

        assert code == 1
        assert envelope["operation"]["status"] == "unknown"
        assert "--path" in envelope["operation"]["reason"]
        assert _meta(brief)["status"] == "draft"


class TestDenials:
    """Each established fact that denies the mirror: refused, file untouched."""

    @pytest.mark.parametrize("state", ["OPEN", "CLOSED"])
    def test_unmerged_pr(self, capsys, forge, brief, state):
        forge.pr = PullRequest(state, None, None, None)

        code, envelope = _approve(capsys)

        assert code == 2
        assert envelope["operation"]["reason"] == protocol.PR_NOT_MERGED
        assert state in envelope["operation"]["detail"]
        assert brief.read_text(encoding="utf-8") == DRAFT

    def test_merger_not_on_the_allowlist(self, capsys, forge, brief):
        forge.pr = PullRequest("MERGED", "ai-prosto", MERGED.merged_at, MERGE_SHA)

        code, envelope = _approve(capsys)

        assert code == 2
        assert envelope["operation"]["reason"] == protocol.APPROVER_NOT_AUTHORIZED
        assert "ai-prosto" in envelope["operation"]["detail"]
        assert brief.read_text(encoding="utf-8") == DRAFT

    def test_pr_that_did_not_change_the_brief(self, capsys, forge, brief):
        forge.files = ["README.md"]

        code, envelope = _approve(capsys)

        assert code == 2
        assert envelope["operation"]["reason"] == protocol.BRIEF_NOT_IN_PR
        assert brief.read_text(encoding="utf-8") == DRAFT

    def test_brief_absent_from_the_merge_commit(self, capsys, forge, brief):
        forge.merged_text = None

        code, envelope = _approve(capsys)

        assert code == 2
        assert envelope["operation"]["reason"] == protocol.BRIEF_NOT_IN_PR
        assert brief.read_text(encoding="utf-8") == DRAFT

    def test_local_bytes_differ_from_the_merged_ones(self, capsys, forge, brief):
        forge.merged_text = DRAFT.replace("by half", "by a third")

        code, envelope = _approve(capsys)

        assert code == 2
        assert envelope["operation"]["reason"] == protocol.BRIEF_BYTES_DIVERGED
        assert brief.read_text(encoding="utf-8") == DRAFT

    def test_merged_file_that_is_not_a_brief(self, capsys, forge, brief):
        """Review finding on PR #57: a merged file without frontmatter used
        to escape as a traceback instead of the envelope."""
        forge.merged_text = "# not a brief\n"

        code, envelope = _approve(capsys)

        assert code == 2
        assert envelope["operation"]["reason"] == protocol.BRIEF_BYTES_DIVERGED
        assert "not a brief" in envelope["operation"]["detail"]
        assert brief.read_text(encoding="utf-8") == DRAFT

    def test_merged_bytes_are_compared_outside_the_envelope(self, capsys, forge, brief):
        """What git holds is the draft; what is on disk may already carry a
        stamp. The comparison is of content, not of the envelope."""
        forge.merged_text = DRAFT
        brief.write_text(approval.stamp(DRAFT, approval.MergeEvent(HUMAN, "x", "y")))

        code, _ = _approve(capsys)

        assert code == 0
        assert _meta(brief)["approved_at"] == MERGED.merged_at


class TestWithdrawal:
    def test_an_edited_approved_brief_is_returned_to_draft(self, capsys, forge, brief):
        _approve(capsys)
        stamped = brief.read_text(encoding="utf-8")
        brief.write_text(stamped.replace("by half", "by a third"), encoding="utf-8")

        code, envelope = _approve(capsys)

        assert code == 2
        assert envelope["operation"]["reason"] == protocol.BRIEF_BYTES_DIVERGED
        meta = _meta(brief)
        assert meta["status"] == "draft"
        assert "approver" not in meta
        assert approval.SELF_HASH_KEY not in meta
        assert "by a third" in brief.read_text(encoding="utf-8")


class TestUnknowns:
    """Facts that cannot be established: exit 1, nothing written."""

    def test_forge_unreachable(self, capsys, forge, brief):
        forge.down = True

        code, envelope = _approve(capsys)

        assert code == 1
        assert envelope["operation"]["status"] == "unknown"
        assert brief.read_text(encoding="utf-8") == DRAFT

    def test_merged_pr_with_an_incomplete_event(self, capsys, forge, brief):
        forge.pr = PullRequest("MERGED", None, MERGED.merged_at, MERGE_SHA)

        code, envelope = _approve(capsys)

        assert code == 1
        assert "mergedBy.login" in envelope["operation"]["reason"]
        assert brief.read_text(encoding="utf-8") == DRAFT

    def test_policy_repository_without_a_policy(self, capsys, forge, brief):
        forge.policy_sha = None

        code, envelope = _approve(capsys)

        assert code == 1
        assert brief.read_text(encoding="utf-8") == DRAFT

    def test_allowlist_from_the_environment_is_refused(
        self, capsys, forge, brief, monkeypatch
    ):
        monkeypatch.setenv(policy.ALLOWLIST_KEY, HUMAN)

        code, envelope = _approve(capsys)

        assert code == 1
        assert policy.ALLOWLIST_KEY in envelope["operation"]["reason"]
        assert brief.read_text(encoding="utf-8") == DRAFT

    def test_not_a_brief(self, capsys, forge, brief):
        brief.write_text("# not a brief\n", encoding="utf-8")

        code, envelope = _approve(capsys)

        assert code == 1
        assert envelope["operation"]["status"] == "unknown"

    def test_missing_brief(self, capsys, forge, brief):
        brief.unlink()

        code, envelope = _approve(capsys)

        assert code == 1
        assert envelope["operation"]["status"] == "unknown"


class TestEnvelope:
    def test_axes_describe_the_brief_on_disk(self, capsys, forge, brief):
        code, envelope = _approve(capsys)

        assert code == 0
        assert envelope["lifecycle"] == "complete"
        assert envelope["gate"] == "pass"
        assert envelope["readiness"] == "ready"

    def test_a_lint_failing_brief_is_still_mirrored_but_reports_it(
        self, capsys, forge, brief
    ):
        failing = DRAFT.replace("traces: [G-01]", "traces: [G-99]")
        brief.write_text(failing, encoding="utf-8")
        forge.merged_text = failing

        code, envelope = _approve(capsys)

        assert envelope["gate"] == "fail"
        assert code == 10
        assert _meta(brief)["status"] == "approved"

    def test_policy_is_read_from_the_vendored_coordinates(self, capsys, forge, brief):
        _approve(capsys)

        assert ("latest_commit_touching", POLICY_REPO, POLICY_REF, POLICY_PATH) in (
            forge.calls
        )
        assert ("file_at", POLICY_REPO, POLICY_SHA, POLICY_PATH) in forge.calls
