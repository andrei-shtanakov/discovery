"""vendor_pull — copy the discovery-brief contract from an upstream checkout.

Copies DISCOVERY-BRIEF-CONTRACT.md and gate_check.py from an upstream git
checkout into a destination directory (default: src/discovery/contract),
and writes a PINNED.txt manifest recording the upstream remote URL, the HEAD
commit, and the sha256 of each copied file.

Usage: uv run tools/vendor_pull.py <upstream_path> [--include-frames]
Destination override: set VENDOR_DEST to an absolute path.
"""

from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import sys
from pathlib import Path

# Upstream-relative path -> vendored-relative path.
CORE = {
    "DISCOVERY-BRIEF-CONTRACT.md": "DISCOVERY-BRIEF-CONTRACT.md",
    "gate_check.py": "gate_check.py",
}
# Not to be confused with discovery.contract.gate_check.FRAMES (the
# required/optional coverage table) — different object, different module,
# do not import or alias one in place of the other.
FRAMES: dict[str, str] = {
    ".claude/skills/discovery-interview/frames/customer.md": "frames/customer.md",
    ".claude/skills/discovery-interview/frames/engineer.md": "frames/engineer.md",
}


def default_dest() -> Path:
    """Return the default vendoring destination relative to this file."""
    return Path(__file__).resolve().parent.parent / "src" / "discovery" / "contract"


def resolve_dest() -> Path:
    """Return the vendoring destination: VENDOR_DEST if set, else the default."""
    env_dest = os.environ.get("VENDOR_DEST")
    if env_dest:
        return Path(env_dest)
    return default_dest()


def upstream_head(upstream: Path) -> str:
    """Return the full HEAD commit sha of the upstream git checkout."""
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=upstream,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def upstream_url(upstream: Path) -> str:
    """Return the upstream's `origin` remote URL, or its path if unset."""
    result = subprocess.run(
        ["git", "remote", "get-url", "origin"],
        cwd=upstream,
        capture_output=True,
        text=True,
    )
    if result.returncode == 0:
        return result.stdout.strip()
    return str(upstream)


def vendor_pull(upstream: Path, dest: Path, *, include_frames: bool = False) -> None:
    """Copy CORE (and FRAMES, if requested) from upstream to dest.

    Writes a PINNED.txt manifest recording the upstream remote URL, the HEAD
    commit sha, and the sha256 of each copied file.
    """
    dest.mkdir(parents=True, exist_ok=True)
    url = upstream_url(upstream)
    head = upstream_head(upstream)

    digests: list[tuple[str, str]] = []
    for upstream_rel, dest_rel in CORE.items():
        src_file = upstream / upstream_rel
        dest_file = dest / dest_rel
        shutil.copyfile(src_file, dest_file)
        digest = hashlib.sha256(dest_file.read_bytes()).hexdigest()
        digests.append((upstream_rel, digest))

    if include_frames:
        (dest / "frames").mkdir(parents=True, exist_ok=True)
        for upstream_rel, dest_rel in FRAMES.items():
            src_file = upstream / upstream_rel
            dest_file = dest / dest_rel
            shutil.copyfile(src_file, dest_file)
            digest = hashlib.sha256(dest_file.read_bytes()).hexdigest()
            digests.append((upstream_rel, digest))

    lines = [f"upstream: {url}", f"commit: {head}", ""]
    lines.extend(f"{name} {digest}" for name, digest in digests)
    (dest / "PINNED.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main(argv: list[str]) -> int:
    """CLI entry point: `vendor_pull.py <upstream_path> [--include-frames]`."""
    include_frames = "--include-frames" in argv
    positional = [arg for arg in argv if arg != "--include-frames"]
    if len(positional) != 1:
        print(
            "usage: vendor_pull.py <upstream_path> [--include-frames]",
            file=sys.stderr,
        )
        return 2
    upstream = Path(positional[0])
    dest = resolve_dest()
    vendor_pull(upstream, dest, include_frames=include_frames)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
