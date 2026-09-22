"""`discovery.forge.Forge` over the `gh` CLI.

`gh` rather than raw HTTP so authentication is the operator's own `gh`
profile — the same one under which every other forge *fact* in the
ecosystem is read (devtools S9); the agent profile is for acts of
publication, and this adapter performs none. Every method is a read.

The queries mirror `devtools/governance/ops.py` (`pr_facts`, `pr_files`,
`policy_version_fact`, `repo_file_fact`) so the two readers of the same
facts cannot drift in what they ask for. Any non-zero exit, unparsable
output or unexpected shape is `ForgeUnavailable`: an inability to
establish a fact is never reported as its absence.
"""

from __future__ import annotations

import json
import subprocess
from typing import Any

from discovery.forge import ForgeUnavailable, PullRequest

_PR_FIELDS = "state,mergedAt,mergedBy,mergeCommit"

_LATEST_COMMIT_QUERY = (
    "query($o:String!,$n:String!,$q:String!,$p:String!){"
    "repository(owner:$o,name:$n){ref(qualifiedName:$q){target{"
    "... on Commit{history(first:1,path:$p){nodes{oid}}}}}}}"
)
_FILE_QUERY = (
    "query($o:String!,$n:String!,$s:GitObjectID!,$p:String!){"
    "repository(owner:$o,name:$n){object(oid:$s){"
    "... on Commit{file(path:$p){object{"
    "... on Blob{text isBinary isTruncated}}}}}}}"
)


def _run(argv: list[str]) -> str:
    """stdout of `argv`, or `ForgeUnavailable` on any failure to run it."""
    try:
        done = subprocess.run(argv, capture_output=True, text=True, check=False)
    except (OSError, subprocess.SubprocessError) as exc:
        raise ForgeUnavailable(f"{argv[0]} could not be run: {exc}") from exc
    if done.returncode != 0:
        detail = done.stderr.strip() or f"exit {done.returncode}"
        raise ForgeUnavailable(f"{' '.join(argv[:3])}: {detail}")
    return done.stdout


def _json(text: str, what: str) -> Any:
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise ForgeUnavailable(f"{what}: not JSON ({exc})") from exc


def _split_repo(repo: str) -> tuple[str, str]:
    owner, _, name = repo.partition("/")
    if not owner or not name or "/" in name:
        raise ForgeUnavailable(f"repository must be owner/name, got {repo!r}")
    return owner, name


class GhForge:
    """The `gh`-backed forge; see the module docstring for the contract."""

    def pull_request(self, repo: str, number: int) -> PullRequest:
        """`gh pr view --json` projected onto `PullRequest`."""
        what = f"PR {repo}#{number}"
        raw = _json(
            _run(["gh", "pr", "view", str(number), "-R", repo, "--json", _PR_FIELDS]),
            what,
        )
        if not isinstance(raw, dict) or not isinstance(raw.get("state"), str):
            raise ForgeUnavailable(f"{what}: unexpected shape")
        merged_by = raw.get("mergedBy")
        commit = raw.get("mergeCommit")
        return PullRequest(
            state=raw["state"],
            merged_by=merged_by.get("login") if isinstance(merged_by, dict) else None,
            merged_at=raw.get("mergedAt") or None,
            merge_commit=commit.get("oid") if isinstance(commit, dict) else None,
        )

    def pull_request_files(self, repo: str, number: int) -> list[str]:
        """Paths the PR changed, as `gh pr view --json files` lists them."""
        what = f"files of PR {repo}#{number}"
        raw = _json(
            _run(["gh", "pr", "view", str(number), "-R", repo, "--json", "files"]),
            what,
        )
        files = raw.get("files") if isinstance(raw, dict) else None
        if not isinstance(files, list):
            raise ForgeUnavailable(f"{what}: unexpected shape")
        paths = [f.get("path") for f in files if isinstance(f, dict)]
        if any(not isinstance(p, str) for p in paths):
            raise ForgeUnavailable(f"{what}: unexpected shape")
        return [p for p in paths if isinstance(p, str)]

    def _repository(self, query: str, **variables: str) -> dict[str, Any]:
        argv = ["gh", "api", "graphql", "-f", f"query={query}"]
        for key, value in variables.items():
            argv += ["-F", f"{key}={value}"]
        raw = _json(_run(argv), "graphql")
        repository = (
            raw.get("data", {}).get("repository") if isinstance(raw, dict) else None
        )
        if not isinstance(repository, dict):
            raise ForgeUnavailable("graphql: no repository in reply")
        return repository

    def file_at(self, repo: str, commit: str, path: str) -> str | None:
        """Text of `path` at `commit`; `None` when that commit lacks the file."""
        owner, name = _split_repo(repo)
        what = f"{repo}@{commit}:{path}"
        repository = self._repository(_FILE_QUERY, o=owner, n=name, s=commit, p=path)
        if "object" not in repository:
            raise ForgeUnavailable(f"{what}: unexpected shape")
        obj = repository["object"]
        if obj is None:
            raise ForgeUnavailable(f"{what}: commit {commit} not found")
        entry = obj.get("file") if isinstance(obj, dict) else None
        if entry is None:
            return None
        blob = entry.get("object") if isinstance(entry, dict) else None
        text = blob.get("text") if isinstance(blob, dict) else None
        if not isinstance(text, str) or blob.get("isBinary") or blob.get("isTruncated"):
            raise ForgeUnavailable(f"{what}: content not readable")
        return text

    def latest_commit_touching(self, repo: str, ref: str, path: str) -> str | None:
        """SHA of the last commit on `ref` touching `path`; `None` if none."""
        owner, name = _split_repo(repo)
        what = f"{repo}:{path}@{ref}"
        repository = self._repository(
            _LATEST_COMMIT_QUERY, o=owner, n=name, q=f"refs/heads/{ref}", p=path
        )
        if "ref" not in repository:
            raise ForgeUnavailable(f"{what}: unexpected shape")
        if repository["ref"] is None:
            return None
        try:
            nodes = repository["ref"]["target"]["history"]["nodes"]
        except (KeyError, TypeError) as exc:
            raise ForgeUnavailable(f"{what}: unexpected shape") from exc
        if not isinstance(nodes, list):
            raise ForgeUnavailable(f"{what}: unexpected shape")
        if not nodes:
            return None
        oid = nodes[0].get("oid") if isinstance(nodes[0], dict) else None
        if not isinstance(oid, str):
            raise ForgeUnavailable(f"{what}: unexpected shape")
        return oid
