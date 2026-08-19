"""vendor_pull — copy the discovery-brief contract from an upstream checkout.

Copies DISCOVERY-BRIEF-CONTRACT.md and gate_check.py from an upstream git
checkout into a destination directory (default: src/discovery/contract),
and writes a PINNED.txt manifest recording the upstream HEAD commit and the
sha256 of each copied file.

Usage: uv run tools/vendor_pull.py <upstream_path>
Destination override: set VENDOR_DEST to an absolute path.
"""

from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import sys
from pathlib import Path

VENDORED_FILES = ("DISCOVERY-BRIEF-CONTRACT.md", "gate_check.py")


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


def vendor_pull(upstream: Path, dest: Path) -> None:
    """Copy VENDORED_FILES from upstream to dest and write PINNED.txt."""
    dest.mkdir(parents=True, exist_ok=True)
    head = upstream_head(upstream)

    digests: list[tuple[str, str]] = []
    for name in VENDORED_FILES:
        src_file = upstream / name
        dest_file = dest / name
        shutil.copyfile(src_file, dest_file)
        digest = hashlib.sha256(dest_file.read_bytes()).hexdigest()
        digests.append((name, digest))

    lines = [f"commit: {head}", ""]
    lines.extend(f"{name} {digest}" for name, digest in digests)
    (dest / "PINNED.txt").write_text("\n".join(lines) + "\n")


def main(argv: list[str]) -> int:
    """CLI entry point: `vendor_pull.py <upstream_path>`."""
    if len(argv) != 1:
        print("usage: vendor_pull.py <upstream_path>", file=sys.stderr)
        return 2
    upstream = Path(argv[0])
    dest = resolve_dest()
    vendor_pull(upstream, dest)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
