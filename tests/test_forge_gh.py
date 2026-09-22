"""`discovery_forge.gh.GhForge` — the `gh`-backed forge, with `gh` faked.

`subprocess.run` is replaced by a recorder, so each case checks two things
without a network: what `gh` is asked (the argv mirrors devtools' queries)
and how its reply is projected. Every failure to run, non-zero exit,
non-JSON reply or unexpected shape is `ForgeUnavailable`; an established
absence (no such file at the commit, no history for the path) is `None`.
"""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass

import pytest

from discovery.forge import ForgeUnavailable
from discovery_forge import gh


@dataclass
class _Done:
    returncode: int
    stdout: str = ""
    stderr: str = ""


@pytest.fixture
def fake_gh(monkeypatch):
    """Route `subprocess.run` to a scripted reply; records every argv."""
    state = {"reply": _Done(0, "{}"), "argv": []}

    def run(argv, **kwargs):
        state["argv"].append(argv)
        reply = state["reply"]
        if isinstance(reply, Exception):
            raise reply
        return reply

    monkeypatch.setattr(gh.subprocess, "run", run)
    return state


def _reply(fake_gh, payload, code=0, stderr=""):
    text = payload if isinstance(payload, str) else json.dumps(payload)
    fake_gh["reply"] = _Done(code, text, stderr)


class TestPullRequest:
    def test_asks_gh_pr_view_for_the_approval_fields(self, fake_gh):
        _reply(fake_gh, {"state": "OPEN", "mergedBy": None, "mergedAt": None})

        gh.GhForge().pull_request("org/repo", 7)

        assert fake_gh["argv"] == [
            ["gh", "pr", "view", "7", "-R", "org/repo", "--json", gh._PR_FIELDS]
        ]

    def test_projects_a_merged_reply(self, fake_gh):
        _reply(
            fake_gh,
            {
                "state": "MERGED",
                "mergedAt": "2026-09-22T10:00:00Z",
                "mergedBy": {"login": "alice"},
                "mergeCommit": {"oid": "abc"},
            },
        )

        pr = gh.GhForge().pull_request("org/repo", 7)

        assert (pr.state, pr.merged_by, pr.merged_at, pr.merge_commit) == (
            "MERGED",
            "alice",
            "2026-09-22T10:00:00Z",
            "abc",
        )

    def test_missing_event_fields_project_to_none(self, fake_gh):
        _reply(fake_gh, {"state": "MERGED", "mergedBy": None, "mergedAt": ""})

        pr = gh.GhForge().pull_request("org/repo", 7)

        assert (pr.merged_by, pr.merged_at, pr.merge_commit) == (None, None, None)

    def test_nonzero_exit_is_unavailable_with_stderr(self, fake_gh):
        _reply(fake_gh, "", code=1, stderr="no pull requests found")

        with pytest.raises(ForgeUnavailable, match="no pull requests found"):
            gh.GhForge().pull_request("org/repo", 7)

    def test_gh_missing_is_unavailable(self, fake_gh):
        fake_gh["reply"] = FileNotFoundError("gh")

        with pytest.raises(ForgeUnavailable, match="could not be run"):
            gh.GhForge().pull_request("org/repo", 7)

    def test_timeout_is_unavailable(self, fake_gh):
        fake_gh["reply"] = subprocess.TimeoutExpired(["gh"], 1)

        with pytest.raises(ForgeUnavailable):
            gh.GhForge().pull_request("org/repo", 7)

    def test_non_json_is_unavailable(self, fake_gh):
        _reply(fake_gh, "not json")

        with pytest.raises(ForgeUnavailable, match="not JSON"):
            gh.GhForge().pull_request("org/repo", 7)

    def test_shape_without_state_is_unavailable(self, fake_gh):
        _reply(fake_gh, {"mergedAt": None})

        with pytest.raises(ForgeUnavailable, match="unexpected shape"):
            gh.GhForge().pull_request("org/repo", 7)


class TestPullRequestFiles:
    def test_lists_paths(self, fake_gh):
        _reply(fake_gh, {"files": [{"path": "a.md"}, {"path": "b/c.md"}]})

        assert gh.GhForge().pull_request_files("org/repo", 7) == ["a.md", "b/c.md"]
        assert fake_gh["argv"][0][-2:] == ["--json", "files"]

    def test_shape_without_files_is_unavailable(self, fake_gh):
        _reply(fake_gh, {"files": "nope"})

        with pytest.raises(ForgeUnavailable):
            gh.GhForge().pull_request_files("org/repo", 7)


def _graphql(repository):
    return {"data": {"repository": repository}}


class TestFileAt:
    def test_asks_graphql_with_the_repository_split(self, fake_gh):
        _reply(fake_gh, _graphql({"object": {"file": {"object": {"text": "x"}}}}))

        gh.GhForge().file_at("org/repo", "abc", "docs/brief.md")

        argv = fake_gh["argv"][0]
        assert argv[:3] == ["gh", "api", "graphql"]
        assert "-F" in argv and "o=org" in argv and "n=repo" in argv
        assert "s=abc" in argv and "p=docs/brief.md" in argv

    def test_returns_the_text(self, fake_gh):
        _reply(fake_gh, _graphql({"object": {"file": {"object": {"text": "hi\n"}}}}))

        assert gh.GhForge().file_at("org/repo", "abc", "p") == "hi\n"

    def test_missing_file_is_none(self, fake_gh):
        _reply(fake_gh, _graphql({"object": {"file": None}}))

        assert gh.GhForge().file_at("org/repo", "abc", "p") is None

    def test_missing_commit_is_unavailable(self, fake_gh):
        _reply(fake_gh, _graphql({"object": None}))

        with pytest.raises(ForgeUnavailable, match="not found"):
            gh.GhForge().file_at("org/repo", "abc", "p")

    @pytest.mark.parametrize("flag", ["isBinary", "isTruncated"])
    def test_binary_or_truncated_is_unavailable(self, fake_gh, flag):
        _reply(
            fake_gh,
            _graphql({"object": {"file": {"object": {"text": "x", flag: True}}}}),
        )

        with pytest.raises(ForgeUnavailable, match="not readable"):
            gh.GhForge().file_at("org/repo", "abc", "p")

    def test_bad_repository_name_is_unavailable(self, fake_gh):
        with pytest.raises(ForgeUnavailable, match="owner/name"):
            gh.GhForge().file_at("repo", "abc", "p")
        assert fake_gh["argv"] == []


class TestLatestCommitTouching:
    def test_returns_the_first_history_oid(self, fake_gh):
        _reply(
            fake_gh,
            _graphql({"ref": {"target": {"history": {"nodes": [{"oid": "abc"}]}}}}),
        )

        assert gh.GhForge().latest_commit_touching("org/repo", "main", "p") == "abc"
        assert "q=refs/heads/main" in fake_gh["argv"][0]

    def test_missing_ref_is_none(self, fake_gh):
        _reply(fake_gh, _graphql({"ref": None}))

        assert gh.GhForge().latest_commit_touching("org/repo", "main", "p") is None

    def test_empty_history_is_none(self, fake_gh):
        _reply(fake_gh, _graphql({"ref": {"target": {"history": {"nodes": []}}}}))

        assert gh.GhForge().latest_commit_touching("org/repo", "main", "p") is None

    def test_unexpected_shape_is_unavailable(self, fake_gh):
        _reply(fake_gh, _graphql({"ref": {"target": {}}}))

        with pytest.raises(ForgeUnavailable):
            gh.GhForge().latest_commit_touching("org/repo", "main", "p")

    def test_reply_without_repository_is_unavailable(self, fake_gh):
        _reply(fake_gh, {"data": {"repository": None}})

        with pytest.raises(ForgeUnavailable, match="no repository"):
            gh.GhForge().latest_commit_touching("org/repo", "main", "p")
