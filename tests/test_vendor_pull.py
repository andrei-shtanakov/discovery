"""Hermetic tests for tools/vendor_pull.py.

Every test builds its own fake upstream git repo under tmp_path — none of
this reads anything outside tmp_path, so it passes in an isolated worktree
with no neighbouring upstream checkout.
"""

import hashlib
import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
VENDOR_PULL = REPO_ROOT / "tools" / "vendor_pull.py"


def _init_fake_upstream(upstream: Path) -> str:
    upstream.mkdir()
    (upstream / "DISCOVERY-BRIEF-CONTRACT.md").write_text(
        "# Discovery Brief Contract\n\nfake upstream content.\n"
    )
    (upstream / "gate_check.py").write_text("FRAMES = {'customer', 'engineer'}\n")

    subprocess.run(["git", "init"], cwd=upstream, check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "test@example.com"],
        cwd=upstream,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test"],
        cwd=upstream,
        check=True,
        capture_output=True,
    )
    subprocess.run(["git", "add", "."], cwd=upstream, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "seed fake upstream"],
        cwd=upstream,
        check=True,
        capture_output=True,
    )
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=upstream,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    return head


def test_vendor_pull_copies_files_and_writes_pinned_manifest(tmp_path):
    upstream = tmp_path / "upstream"
    head = _init_fake_upstream(upstream)
    dest = tmp_path / "dest"

    result = subprocess.run(
        [sys.executable, str(VENDOR_PULL), str(upstream)],
        env={**os.environ, "VENDOR_DEST": str(dest)},
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr

    contract_md = upstream / "DISCOVERY-BRIEF-CONTRACT.md"
    gate_check = upstream / "gate_check.py"
    copied_md = dest / "DISCOVERY-BRIEF-CONTRACT.md"
    copied_gate = dest / "gate_check.py"
    assert copied_md.read_bytes() == contract_md.read_bytes()
    assert copied_gate.read_bytes() == gate_check.read_bytes()

    pinned = (dest / "PINNED.txt").read_text()
    assert "upstream: " in pinned
    assert f"commit: {head}" in pinned

    expected_md_sha = hashlib.sha256(contract_md.read_bytes()).hexdigest()
    expected_gate_sha = hashlib.sha256(gate_check.read_bytes()).hexdigest()
    assert f"DISCOVERY-BRIEF-CONTRACT.md {expected_md_sha}" in pinned
    assert f"gate_check.py {expected_gate_sha}" in pinned


def test_vendor_pull_defaults_dest_to_src_discovery_contract(tmp_path, monkeypatch):
    upstream = tmp_path / "upstream"
    _init_fake_upstream(upstream)

    monkeypatch.delenv("VENDOR_DEST", raising=False)
    fake_repo_root = tmp_path / "fake_repo"
    fake_repo_root.mkdir()
    (fake_repo_root / "tools").mkdir()
    vendor_pull_copy = fake_repo_root / "tools" / "vendor_pull.py"
    vendor_pull_copy.write_text(VENDOR_PULL.read_text())

    result = subprocess.run(
        [sys.executable, str(vendor_pull_copy), str(upstream)],
        cwd=fake_repo_root,
        env=os.environ,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    default_dest = fake_repo_root / "src" / "discovery" / "contract"
    assert (default_dest / "DISCOVERY-BRIEF-CONTRACT.md").exists()
    assert (default_dest / "gate_check.py").exists()
    assert (default_dest / "PINNED.txt").exists()


def test_vendor_pull_rejects_bad_argv(tmp_path):
    result = subprocess.run(
        [sys.executable, str(VENDOR_PULL)],
        env=os.environ,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 2
    assert "usage:" in result.stderr


def test_vendor_pull_include_frames_flag_is_accepted(tmp_path):
    upstream = tmp_path / "upstream"
    head = _init_fake_upstream(upstream)
    dest = tmp_path / "dest"

    result = subprocess.run(
        [sys.executable, str(VENDOR_PULL), str(upstream), "--include-frames"],
        env={**os.environ, "VENDOR_DEST": str(dest)},
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    pinned = (dest / "PINNED.txt").read_text()
    assert f"commit: {head}" in pinned
