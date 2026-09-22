"""Admitting an upstream customer brief into an engineer session.

The engineer frame traces to an approved customer brief, but the gate
resolves `traces_to` from the session directory (`gate_check._resolve_ref`
drops absolute paths and anything outside the brief's root), and a caller
may not write into `$DISCOVERY_HOME` itself. `admit` is the public way in:
it validates a proposed source and returns the text to copy into the
session under `UPSTREAM_NAME`.

The name is fixed rather than the source's basename. A basename that
collided with the final brief's own file name would make `traces_to`
resolve to the brief itself — GC-16 green, GC-05 checking the document
against its own body, every upstream Must-FR trivially "mentioned". A
silent false pass is worth more than an informative file name; the
source's provenance lives in the caller's ledger either way.

Validation runs here, before any session exists, because a source
rejected later is a source an engineer interview can already have been
half-run against.
"""

from __future__ import annotations

from pathlib import Path

from discovery import approval
from discovery.contract.gate_check import Finding, check, split_frontmatter

UPSTREAM_NAME = "upstream.md"


class UpstreamRejected(Exception):
    """The proposed document cannot serve as an upstream customer brief."""


def admit(path: Path) -> str:
    """Return `path`'s text if it is an approved, lint-clean customer brief.

    Raises `UpstreamRejected` otherwise. `OSError`/`UnicodeDecodeError` from
    reading the file are left to the caller's envelope, which already
    projects them.
    """
    # A restriction on what a caller may hand in, not something the linter
    # imposes: the copy's own name is fixed, so the ref the linter sees ends
    # in `.md` whatever the source was called.
    if path.suffix != ".md":
        raise UpstreamRejected(f"upstream must be a .md file, got {path.name!r}")
    text = path.read_text(encoding="utf-8")
    meta, _ = split_frontmatter(text)
    if meta is None:
        raise UpstreamRejected(f"{path}: no readable frontmatter")
    if meta.get("schema") != "discovery-brief":
        raise UpstreamRejected(
            f"{path}: schema={meta.get('schema')!r}, expected 'discovery-brief'"
        )
    interview = meta.get("interview")
    if not isinstance(interview, dict):
        raise UpstreamRejected(
            f"{path}: interview is {type(interview).__name__}, expected a mapping"
        )
    frame = interview.get("frame")
    if frame != "customer":
        raise UpstreamRejected(
            f"{path}: interview.frame={frame!r}, expected 'customer'"
        )
    if meta.get("status") != "approved":
        raise UpstreamRejected(
            f"{path}: status={meta.get('status')!r}, expected 'approved'"
        )
    # `approved` is a claim; the self-hash is what ties it to these bytes.
    # A brief edited after `discovery approve` stamped it carries a hash
    # that no longer matches, and is not the document a human merged. A
    # brief with no hash at all is one stamped before the act existed:
    # migration debt, admitted as before until the policy source exists
    # to re-approve it (TODO.md `@id:brief-approval-act`).
    if approval.verify(text) == approval.DEBT_SELF_HASH:
        raise UpstreamRejected(
            f"{path}: status is 'approved' but {approval.SELF_HASH_KEY} does "
            "not match the bytes: the brief was edited after its approval"
        )
    errors = [f for f in _lint(text, path) if f.level == "error"]
    if errors:
        raise UpstreamRejected(
            f"{path}: upstream does not pass the vendored linter: "
            + "; ".join(str(f) for f in errors)
        )
    return text


def _lint(text: str, path: Path) -> list[Finding]:
    """`check` fenced against a document that came from outside this runtime.

    The vendored linter was written for briefs this runtime rendered itself,
    where `interview`, `coverage` and the rest are always the shape it
    expects; `admit` is the first place it meets a document a caller wrote.
    A scalar where it reads a mapping raises `AttributeError` *inside* the
    pinned copy — a traceback instead of the one JSON envelope every command
    owes its caller. The copy is pinned and cannot be repaired from here, so
    an unlintable document is refused as one.
    """
    try:
        return check(text, base_dir=path.parent)
    except Exception as exc:  # noqa: BLE001 — the pinned linter, on foreign input
        raise UpstreamRejected(
            f"{path}: upstream could not be linted "
            f"({type(exc).__name__}: {exc}) — malformed for the contract"
        ) from exc
