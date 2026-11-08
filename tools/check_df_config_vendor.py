"""Verify the vendored DarkFactory config loader (devtools governance/df_config.py).

Same three modes and exit codes as check_vendor.py (0 ok · 1 failed · 3 unknown),
reusing its functions for a second vendored copy:
`src/discovery/darkfactory/` pinned against andrei-shtanakov/devtools.
Destination override: set DF_CONFIG_VENDOR_DEST to an absolute path.
"""

from __future__ import annotations

import argparse
import hashlib
import os
import sys
from functools import partial
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import check_vendor  # noqa: E402
from check_vendor import Verdict  # noqa: E402

UPSTREAM_REPO = "andrei-shtanakov/devtools"
SURFACE = frozenset({"df_config.py"})
UPSTREAM_PATHS = {"df_config.py": "governance/df_config.py"}


def resolve_dest() -> Path:
    """Return the vendoring destination: DF_CONFIG_VENDOR_DEST or the default."""
    env_dest = os.environ.get("DF_CONFIG_VENDOR_DEST")
    if env_dest:
        return Path(env_dest)
    root = Path(__file__).resolve().parent.parent
    return root / "src" / "discovery" / "darkfactory"


def upstream_path(rel: str) -> str:
    """Map a manifest key to its path in the devtools tree."""
    return UPSTREAM_PATHS.get(rel, rel)


def drift(fetch: check_vendor.Fetcher, dest: Path) -> Verdict:
    """Did the vendored file itself change upstream since the pin?

    Compares the digest of `governance/df_config.py` at upstream HEAD with
    the pinned digest — not the repository HEAD, so unrelated devtools
    commits keep the weekly job green (the pin may lag the repo).
    """
    _, manifest = check_vendor.read_pinned(dest)
    blob = fetch("HEAD", UPSTREAM_PATHS["df_config.py"])
    if blob is None:
        return Verdict("unknown", "upstream df_config.py unreachable")
    head = hashlib.sha256(blob).hexdigest()
    pinned = manifest["df_config.py"]
    if head == pinned:
        return Verdict("ok", f"df_config.py unchanged upstream ({pinned[:8]})")
    return Verdict(
        "failed",
        f"upstream df_config.py changed: pinned {pinned[:8]}, HEAD {head[:8]}",
    )


def run(
    mode: str,
    fetch: check_vendor.Fetcher | None = None,
    dest: Path | None = None,
) -> Verdict:
    """Run one mode against the df_config copy; `fetch` is injectable."""
    dest = dest or resolve_dest()
    if mode == "drift":
        fetch = fetch or partial(check_vendor.github_fetch, repo=UPSTREAM_REPO)
        return drift(fetch, dest)
    if mode == "provenance" and fetch is None:
        fetch = partial(check_vendor.github_fetch, repo=UPSTREAM_REPO)
    return check_vendor.verify(
        "provenance" if mode == "provenance" else "consistency",
        fetch,
        dest=dest,
        surface=SURFACE,
        upstream_path=upstream_path,
    )


def main() -> int:
    """CLI entry point: `check_df_config_vendor.py {consistency|provenance|drift}`."""
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=["consistency", "provenance", "drift"])
    args = parser.parse_args()
    try:
        verdict = run(args.mode)
    except OSError as exc:
        verdict = Verdict("unknown", f"could not read vendored state: {exc}")
    except ValueError as exc:
        verdict = Verdict("unknown", f"could not parse PINNED.txt: {exc}")
    print(f"{args.mode}: {verdict.status} — {verdict.detail}")
    return {"ok": 0, "failed": 1, "unknown": 3}[verdict.status]


if __name__ == "__main__":
    raise SystemExit(main())
