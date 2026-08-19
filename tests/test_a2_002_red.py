"""RED checkpoint for TASK-002: EXPECTED_SURFACE extension to the 4-key surface.

Hermetic: reads only the real, already-vendored src/discovery/contract/PINNED.txt
(4 lines, commit 4664604) — no network access, matching NFR-001.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))

import check_vendor  # noqa: E402

EXPECTED_UPSTREAM_KEYS = frozenset(
    {
        "DISCOVERY-BRIEF-CONTRACT.md",
        "gate_check.py",
        ".claude/skills/discovery-interview/frames/customer.md",
        ".claude/skills/discovery-interview/frames/engineer.md",
    }
)


def test_expected_surface_is_the_four_upstream_keys_and_verifies_ok():
    assert check_vendor.EXPECTED_SURFACE == EXPECTED_UPSTREAM_KEYS

    _, manifest = check_vendor.read_pinned()
    verdict = check_vendor.verify("consistency")

    assert verdict.status == "ok"
    assert manifest.keys() == EXPECTED_UPSTREAM_KEYS
    assert str(len(EXPECTED_UPSTREAM_KEYS)) in verdict.detail
