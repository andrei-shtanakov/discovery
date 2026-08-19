"""Hermetic tests for tools/check_vendor.py.

Every test either injects an explicit `fetch` or reads only the real,
already-vendored `src/discovery/contract/` tree — none of it touches the
network, matching NFR-001. Each case isolates one claim: consistency never
claims provenance and fails loudly on a real digest mismatch, provenance is
fail-closed on an unreachable upstream and fails loudly on a byte mismatch,
drift does not deadlock on an absent run history and correctly reports a
pin that has fallen behind, and EXPECTED_SURFACE is itself a checked fact
rather than something PINNED.txt could silently drop out from under.
"""

import hashlib
import sys
from pathlib import Path

import pytest

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


def test_consistency_mismatch_fails(tmp_path, monkeypatch):
    contract_md = tmp_path / "DISCOVERY-BRIEF-CONTRACT.md"
    contract_md.write_text("pinned content\n")
    # Манифест обязан покрывать весь EXPECTED_SURFACE, иначе verify отвергнет его
    # раньше, чем дойдёт до сверки байт, и тест проверял бы не то, что заявляет.
    gate_py = tmp_path / "gate_check.py"
    gate_py.write_text("FRAMES = {}\n")
    gate_digest = hashlib.sha256(gate_py.read_bytes()).hexdigest()
    frames_dir = tmp_path / "frames"
    frames_dir.mkdir()
    customer_md = frames_dir / "customer.md"
    customer_md.write_text("customer frame\n")
    customer_digest = hashlib.sha256(customer_md.read_bytes()).hexdigest()
    engineer_md = frames_dir / "engineer.md"
    engineer_md.write_text("engineer frame\n")
    engineer_digest = hashlib.sha256(engineer_md.read_bytes()).hexdigest()
    (tmp_path / "PINNED.txt").write_text(
        "commit: 0000000000000000000000000000000000000000\n"
        "DISCOVERY-BRIEF-CONTRACT.md deadbeef\n"
        f"gate_check.py {gate_digest}\n"
        ".claude/skills/discovery-interview/frames/customer.md"
        f" {customer_digest}\n"
        ".claude/skills/discovery-interview/frames/engineer.md"
        f" {engineer_digest}\n"
    )
    monkeypatch.setattr(check_vendor, "CONTRACT", tmp_path)

    verdict = check_vendor.verify("consistency", fetch=None)

    assert verdict.status == "failed"
    assert "DISCOVERY-BRIEF-CONTRACT.md" in verdict.detail


def test_expected_surface_catches_a_manifest_missing_a_frame_line(
    tmp_path, monkeypatch
):
    # Symmetric to test_reduced_manifest_fails_both_modes: dropping a frame
    # line from PINNED.txt must be caught just as loudly as a CORE line.
    (tmp_path / "PINNED.txt").write_text(
        "commit: " + "a" * 40 + "\n"
        "DISCOVERY-BRIEF-CONTRACT.md " + "0" * 64 + "\n"
        "gate_check.py " + "0" * 64 + "\n"
        ".claude/skills/discovery-interview/frames/customer.md " + "0" * 64 + "\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(check_vendor, "CONTRACT", tmp_path)

    verdict = check_vendor.verify("consistency", fetch=None)

    assert verdict.status == "failed"
    assert ".claude/skills/discovery-interview/frames/engineer.md" in verdict.detail


def test_drift_pin_behind_upstream_fails():
    verdict = check_vendor.drift(fetch=lambda *_: b"a" * 40)
    assert verdict.status == "failed"


def test_local_path_maps_frame_files_under_the_frames_directory():
    assert check_vendor.local_path("frames/customer.md") == (
        check_vendor.CONTRACT / "frames" / "customer.md"
    )
    assert check_vendor.local_path("gate_check.py") == (
        check_vendor.CONTRACT / "gate_check.py"
    )


def test_drift_default_fetcher_resolves_head_via_the_commits_api(monkeypatch):
    """Regression for the deadlock bug: drift()'s default fetch must resolve
    upstream's HEAD sha via the Commits API, not read a literal file named
    "HEAD" via the Contents API (which 404s on every real run)."""
    requested_urls = []

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def read(self):
            return b'{"sha": "deadbeefdeadbeefdeadbeefdeadbeefdeadbeef"}'

    def fake_urlopen(request, timeout=20):
        requested_urls.append(request.full_url)
        return FakeResponse()

    monkeypatch.setattr(check_vendor.urllib.request, "urlopen", fake_urlopen)

    check_vendor.drift(fetch=None)

    assert requested_urls == [check_vendor.HEAD_API]
    assert "/contents/" not in requested_urls[0]


def test_reduced_manifest_fails_both_modes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Регресс: манифест сам предмет проверки, а не только её вход.

    Удаление строки из PINNED.txt раньше тихо выводило файл из-под обеих
    гарантий и оставляло их зелёными — тот самый класс «неизвестность как
    зелёное», против которого инструмент и заведён.
    """
    (tmp_path / "DISCOVERY-BRIEF-CONTRACT.md").write_text("x\n")
    (tmp_path / "PINNED.txt").write_text(
        "commit: " + "a" * 40 + "\nDISCOVERY-BRIEF-CONTRACT.md " + "0" * 64 + "\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(check_vendor, "CONTRACT", tmp_path)

    for mode in ("consistency", "provenance"):
        verdict = check_vendor.verify(mode, fetch=lambda *_: b"whatever")
        assert verdict.status == "failed"
        assert "gate_check.py" in verdict.detail
