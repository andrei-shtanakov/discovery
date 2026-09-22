"""Who may sign a brief — the approver allowlist from its trusted source.

The list of accounts whose merge counts as approval is owner policy. It is
read from the repository `approval-policy` (devtools spec
`2026-09-22-approver-policy-trusted-source-design.md`, owner decisions
D1–D6), a repository the executing side cannot write to, at the commit
that last touched the policy file (S5). The environment and the command
line do not supply or override it (D5): a list the executing process hands
itself is exactly the forgeable signature the mirror rule removes, so a set
`AUTHORIZED_APPROVER_ACCOUNTS` is a named refusal (S7), not a fallback.

The source's coordinates are a vendored, pinned copy of devtools' SSOT
(`approval_policy_source.env`, S8) — the cross-repo contract comes in as
bytes, never as a path outside this repository.
"""

from __future__ import annotations

import os
from pathlib import Path

from discovery.forge import Forge

#: The key of the policy file — and the environment name whose presence is
#: a refusal. One name in two places on purpose: the vault rule and the
#: policy file are read with one vocabulary.
ALLOWLIST_KEY = "AUTHORIZED_APPROVER_ACCOUNTS"

SOURCE_FILE = Path(__file__).resolve().parent / "approval_policy_source.env"


class PolicyRefused(Exception):
    """The policy could not be established, so nobody can sign."""


def definition_lines(text: str, key: str) -> list[str]:
    """Every `KEY=value` definition of `key`, by the SSOT env format.

    Shared with devtools `ssot_env`: a line is a definition only when it
    starts with exactly `KEY=` after stripping; `KEY =`, `export KEY=` and a
    lower-case key are not, so anything that merely looks like a definition
    leaves the key unfound — and an unfound key is a refusal.
    """
    prefix = f"{key}="
    found: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if stripped.startswith(prefix):
            found.append(stripped[len(prefix) :].strip())
    return found


def read_key(text: str, key: str, what: str) -> str:
    """The one non-empty definition of `key` in `text`, or `PolicyRefused`.

    A duplicate is a broken file, not a choice to make for the human; an
    absent or empty value would mean "no rule", which is protection removed
    by silence.
    """
    found = definition_lines(text, key)
    if len(found) > 1:
        raise PolicyRefused(f"{what}: {key} defined {len(found)} times — broken file")
    if not found or not found[0]:
        raise PolicyRefused(f"{what}: no non-empty {key}")
    return found[0]


def source() -> tuple[str, str, str]:
    """`(repo, ref, path)` of the policy file, from the vendored coordinates."""
    what = f"policy source {SOURCE_FILE.name}"
    text = SOURCE_FILE.read_text(encoding="utf-8")
    return (
        read_key(text, "APPROVAL_POLICY_REPO", what),
        read_key(text, "APPROVAL_POLICY_REF", what),
        read_key(text, "APPROVAL_POLICY_PATH", what),
    )


def parse_allowlist(text: str, what: str) -> frozenset[str]:
    """Logins from the policy file's `AUTHORIZED_APPROVER_ACCOUNTS`.

    Comma-separated; blanks are dropped, and a value with no login left
    (`= , ,` passes `read_key`) is refused as empty.
    """
    value = read_key(text, ALLOWLIST_KEY, what)
    logins = frozenset(login.strip() for login in value.split(",") if login.strip())
    if not logins:
        raise PolicyRefused(f"{what}: {ALLOWLIST_KEY} names nobody — nobody can sign")
    return logins


def allowlist(forge: Forge) -> frozenset[str]:
    """The current allowlist from the trusted source, via `forge`.

    Raises `PolicyRefused` when the environment tries to supply it, when
    the coordinates do not read, or when the source has no policy;
    `ForgeUnavailable` from `forge` passes through — an unread source is
    an unknown, not a refusal.
    """
    if os.environ.get(ALLOWLIST_KEY) is not None:
        raise PolicyRefused(
            f"{ALLOWLIST_KEY} is set in the environment, but the environment is "
            "no longer a source of signing policy — the source is the "
            "approval-policy repository; unset it and retry"
        )
    repo, ref, path = source()
    version = forge.latest_commit_touching(repo, ref, path)
    if version is None:
        raise PolicyRefused(f"policy source {repo}:{path}@{ref} has no history")
    text = forge.file_at(repo, version, path)
    if text is None:
        raise PolicyRefused(f"policy source {repo}@{version} has no {path}")
    return parse_allowlist(text, f"{repo}@{version}:{path}")
