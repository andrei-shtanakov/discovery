"""Hermetic tests for tools/check_vendor.py.

Every test either injects an explicit `fetch` or reads only the real,
already-vendored `src/discovery/contract/` tree — none of it touches the
network, matching NFR-001. The six cases each isolate one claim: consistency
never claims provenance, provenance is fail-closed on an unreachable
upstream and fails loudly on a mismatch, drift does not deadlock on an
absent run history, and EXPECTED_SURFACE is itself a checked fact rather
than something PINNED.txt could silently drop out from under.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

import check_vendor  # noqa: E402


def test_consistency_mode_never_claims_provenance():
    verdict = check_vendor.verify("consistency", fetch=None)
    assert verdict.status == "ok"
    assert "provenance" not in verdict.detail.lower(), (
        "agreement with a stored digest is not evidence of origin; "
        "the instrument must not describe itself as proving it"
    )


def test_provenance_unreachable_is_unknown_not_ok():
    verdict = check_vendor.verify("provenance", fetch=lambda commit, rel: None)
    assert verdict.status == "unknown"


def test_provenance_mismatch_fails():
    verdict = check_vendor.verify(
        "provenance", fetch=lambda commit, rel: b"not the file"
    )
    assert verdict.status == "failed"


def test_drift_first_run_is_not_blocked_by_absent_history():
    """The deadlock regression: run one must be able to pass."""
    commit, _ = check_vendor.read_pinned()
    assert check_vendor.drift(fetch=lambda *_: commit.encode()).status == "ok"


def test_drift_unreachable_upstream_is_unknown():
    assert check_vendor.drift(fetch=lambda *_: None).status == "unknown"


def test_provenance_matching_bytes_pass():
    root = Path(__file__).resolve().parents[1] / "src" / "discovery" / "contract"

    def fetch(commit: str, rel: str) -> bytes:
        name = "frames/" + rel.rsplit("/", 1)[-1] if "frames/" in rel else rel
        return (root / name).read_bytes()

    assert check_vendor.verify("provenance", fetch=fetch).status == "ok"


def test_expected_surface_is_fully_covered_by_the_real_manifest():
    _, manifest = check_vendor.read_pinned()
    assert check_vendor.EXPECTED_SURFACE <= set(manifest)


def test_expected_surface_catches_a_manifest_missing_a_line():
    # Simulated in-test, never by mutating the real PINNED.txt: a manifest
    # with one required entry cut out must not look complete.
    reduced_manifest = {"DISCOVERY-BRIEF-CONTRACT.md": "deadbeef"}
    assert not check_vendor.EXPECTED_SURFACE <= set(reduced_manifest)
