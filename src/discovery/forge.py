"""What the core needs to know from a forge — a read-only protocol.

`discovery approve` mirrors a fact that lives at the forge: a pull request
carrying the brief was merged, by whom, and what bytes landed. The core
asks for that fact through this protocol and never through a network or a
process of its own (DESIGN-016: the core's import graph holds no such
adapter). The one implementation, `discovery_forge.gh.GhForge`, is a
separate package composed in at `cli.build_forge`, the same seam
`build_source` uses for the question bank.

Two outcomes are kept apart on every read, because they lead to different
envelopes: an *established* absence (`None` — the PR is not merged, the
file is not in that commit) is a refusal the caller can act on; an
*inability to establish* (`ForgeUnavailable` — network, auth, an
unexpected shape) is `unknown`, and nothing is written on it. Folding the
second into the first is the fail-open the mirror rule exists to remove.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


class ForgeUnavailable(Exception):
    """The forge could not be asked, or answered in a shape not understood."""


@dataclass(frozen=True)
class PullRequest:
    """The facts of one PR that bear on approval, as the forge reports them.

    `state` is the forge's own word (`OPEN`/`CLOSED`/`MERGED`); it is read,
    never inferred from `merged_at` — a second definition of the same fact
    is how two readers come to disagree.
    """

    state: str
    merged_by: str | None
    merged_at: str | None
    merge_commit: str | None


class Forge(Protocol):
    """Read-only questions to a forge; every method raises `ForgeUnavailable`
    when the answer cannot be established."""

    def pull_request(self, repo: str, number: int) -> PullRequest:
        """The PR's approval-bearing facts."""
        ...

    def pull_request_files(self, repo: str, number: int) -> list[str]:
        """Repository-relative paths the PR changed."""
        ...

    def file_at(self, repo: str, commit: str, path: str) -> str | None:
        """Text of `path` in `commit`; `None` when the commit has no such file."""
        ...

    def latest_commit_touching(self, repo: str, ref: str, path: str) -> str | None:
        """SHA of the last commit on `ref` that changed `path`; `None` when
        neither the ref nor any such commit exists."""
        ...
