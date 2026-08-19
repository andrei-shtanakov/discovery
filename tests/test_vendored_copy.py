"""Self-consistency regression test for the vendored contract copy.

Checks that src/discovery/contract/PINNED.txt matches the actual files
sitting next to it, and that the vendored gate_check module is importable
and behaves as the contract's gate linter.
"""

import hashlib
from pathlib import Path

from discovery.contract.gate_check import FRAMES, check

CONTRACT_DIR = Path(__file__).resolve().parent.parent / "src" / "discovery" / "contract"


def _parse_pinned(pinned_text: str) -> tuple[str, dict[str, str]]:
    lines = [line for line in pinned_text.splitlines() if line.strip()]
    commit_line = next(line for line in lines if line.startswith("commit:"))
    commit = commit_line.split("commit:", 1)[1].strip()
    digests = {}
    for line in lines:
        parts = line.split()
        if len(parts) != 2 or not parts[1].isalnum() or len(parts[1]) != 64:
            continue
        name, digest = parts
        digests[name] = digest
    return commit, digests


def test_pinned_commit_is_a_full_sha_and_lists_at_least_one_file():
    pinned_text = (CONTRACT_DIR / "PINNED.txt").read_text()
    commit, digests = _parse_pinned(pinned_text)

    assert len(commit) == 40
    assert digests


def test_pinned_digests_match_local_files():
    pinned_text = (CONTRACT_DIR / "PINNED.txt").read_text()
    _, digests = _parse_pinned(pinned_text)

    for name, expected_digest in digests.items():
        actual_digest = hashlib.sha256((CONTRACT_DIR / name).read_bytes()).hexdigest()
        assert actual_digest == expected_digest, f"digest mismatch for {name}"


def test_gate_check_frames_cover_customer_and_engineer():
    assert set(FRAMES) == {"customer", "engineer"}


def test_gate_check_reports_findings_for_empty_brief():
    findings = check("", base_dir=None)

    assert findings
