"""Verify the vendored contract copy.

consistency — do the files match the digests recorded in PINNED.txt?
              Proves the copy is internally consistent. NOT its origin.
provenance  — are the files the bytes of the upstream tree at the pinned commit?
              Unreachable upstream is reported as unknown, never as ok.
drift       — has upstream moved past the pin?

Exit: 0 ok · 1 failed · 3 unknown
Destination override: set VENDOR_DEST to an absolute path (mirrors vendor_pull.py).
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import urllib.error
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

API = (
    "https://api.github.com/repos/andrei-shtanakov/discovery-toolkit"
    "/contents/{rel}?ref={commit}"
)

Fetcher = Callable[[str, str], bytes | None]


@dataclass
class Verdict:
    status: str  # ok | failed | unknown
    detail: str


# What the vendored copy must contain. Without this, deleting a line from
# PINNED.txt quietly drops that file from BOTH guarantees and leaves them
# green: the manifest says WHAT gets checked, so the manifest is itself
# something to check. Task 14 extends the set with the two frame files.
EXPECTED_SURFACE = frozenset({"DISCOVERY-BRIEF-CONTRACT.md", "gate_check.py"})


def resolve_dest() -> Path:
    """Return the vendoring destination: VENDOR_DEST if set, else the default."""
    env_dest = os.environ.get("VENDOR_DEST")
    if env_dest:
        return Path(env_dest)
    return Path(__file__).resolve().parent.parent / "src" / "discovery" / "contract"


CONTRACT = resolve_dest()


def read_pinned() -> tuple[str, dict[str, str]]:
    """Parse the commit and per-file digests out of PINNED.txt."""
    commit, manifest = "", {}
    for line in (CONTRACT / "PINNED.txt").read_text(encoding="utf-8").splitlines():
        if line.startswith("commit:"):
            commit = line.split(":", 1)[1].strip()
        elif line and not line.startswith("upstream:"):
            rel, digest = line.rsplit(" ", 1)
            manifest[rel] = digest
    return commit, manifest


def local_path(rel: str) -> Path:
    """Map a manifest key to its path under the vendored copy."""
    if "frames/" in rel:
        return CONTRACT / "frames" / rel.rsplit("/", 1)[-1]
    return CONTRACT / rel


def github_fetch(commit: str, rel: str) -> bytes | None:
    """Default fetcher: read a blob from the upstream repo via the GitHub API."""
    try:
        with urllib.request.urlopen(
            API.format(rel=rel, commit=commit), timeout=20
        ) as response:
            return base64.b64decode(json.load(response)["content"])
    except (urllib.error.URLError, TimeoutError, KeyError, ValueError):
        return None


def verify(
    mode: Literal["consistency", "provenance"], fetch: Fetcher | None = None
) -> Verdict:
    """Check consistency (against PINNED.txt) or provenance (against upstream)."""
    commit, manifest = read_pinned()
    if mode == "consistency":
        drifted = [
            rel
            for rel, digest in manifest.items()
            if hashlib.sha256(local_path(rel).read_bytes()).hexdigest() != digest
        ]
        if drifted:
            return Verdict(
                "failed", f"files differ from PINNED.txt: {', '.join(drifted)}"
            )
        return Verdict("ok", f"{len(manifest)} files match their recorded digests")

    fetch = fetch or github_fetch
    mismatched: list[str] = []
    for rel in manifest:
        blob = fetch(commit, rel)
        if blob is None:
            return Verdict("unknown", f"upstream unreachable while reading {rel}")
        if blob != local_path(rel).read_bytes():
            mismatched.append(rel)
    if mismatched:
        return Verdict(
            "failed", f"differ from upstream@{commit[:8]}: {', '.join(mismatched)}"
        )
    return Verdict("ok", f"bytes identical to upstream@{commit[:8]}")


def drift(fetch: Fetcher | None = None) -> Verdict:
    """Has upstream moved past the pin?

    Deliberately does NOT gate on when this watch last succeeded. Proving the
    watch's own freshness from inside the watch deadlocks: run one has no
    previous success, so it reports unknown, so the job fails, so a previous
    success never appears. That the run happened at all proves the schedule
    fired; a schedule that stops firing is caught from outside, by the
    fleet's scheduled-run sensor.
    """
    commit, _ = read_pinned()
    fetch = fetch or github_fetch
    head = fetch("HEAD", "HEAD")
    if head is None:
        return Verdict("unknown", "upstream HEAD unreachable")
    head_sha = head.decode("utf-8").strip()
    if head_sha == commit:
        return Verdict("ok", f"pin matches upstream HEAD {head_sha[:8]}")
    return Verdict("failed", f"pin {commit[:8]} is behind upstream {head_sha[:8]}")


def main() -> int:
    """CLI entry point: `check_vendor.py {consistency|provenance|drift}`."""
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=["consistency", "provenance", "drift"])
    args = parser.parse_args()
    verdict = drift() if args.mode == "drift" else verify(args.mode)
    print(f"{args.mode}: {verdict.status} — {verdict.detail}")
    return {"ok": 0, "failed": 1, "unknown": 3}[verdict.status]


if __name__ == "__main__":
    raise SystemExit(main())
