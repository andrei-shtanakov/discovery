"""RED checkpoint for TASK-001: FRAMES source->dest mapping in vendor_pull.py.

Hermetic: builds its own fake upstream git repo under tmp_path (same pattern
as tests/test_vendor_pull.py) — no read of ../discovery-toolkit or any other
neighbouring checkout.
"""

import hashlib
import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
VENDOR_PULL = REPO_ROOT / "tools" / "vendor_pull.py"

FRAMES_CUSTOMER_UPSTREAM = ".claude/skills/discovery-interview/frames/customer.md"
FRAMES_ENGINEER_UPSTREAM = ".claude/skills/discovery-interview/frames/engineer.md"


def _init_fake_upstream_with_frames(upstream: Path) -> str:
    upstream.mkdir()
    (upstream / "DISCOVERY-BRIEF-CONTRACT.md").write_text(
        "# Discovery Brief Contract\n\nfake upstream content.\n"
    )
    (upstream / "gate_check.py").write_text("FRAMES = {'customer', 'engineer'}\n")

    frames_dir = upstream / ".claude" / "skills" / "discovery-interview" / "frames"
    frames_dir.mkdir(parents=True)
    (frames_dir / "customer.md").write_text("# Customer frame\n\nfake customer.\n")
    (frames_dir / "engineer.md").write_text("# Engineer frame\n\nfake engineer.\n")

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
        ["git", "commit", "-m", "seed fake upstream with frames"],
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


class TestVendorPullIncludeFramesRed:
    def test_include_frames_copies_both_frame_files_and_pins_them(self, tmp_path):
        upstream = tmp_path / "upstream"
        _init_fake_upstream_with_frames(upstream)
        dest = tmp_path / "dest"

        result = subprocess.run(
            [sys.executable, str(VENDOR_PULL), str(upstream), "--include-frames"],
            env={**os.environ, "VENDOR_DEST": str(dest)},
            capture_output=True,
            text=True,
        )

        assert result.returncode == 0, result.stderr

        customer_src = upstream / FRAMES_CUSTOMER_UPSTREAM
        engineer_src = upstream / FRAMES_ENGINEER_UPSTREAM
        customer_dest = dest / "frames" / "customer.md"
        engineer_dest = dest / "frames" / "engineer.md"

        assert customer_dest.read_bytes() == customer_src.read_bytes()
        assert engineer_dest.read_bytes() == engineer_src.read_bytes()

        pinned = (dest / "PINNED.txt").read_text()
        expected_customer_sha = hashlib.sha256(customer_src.read_bytes()).hexdigest()
        expected_engineer_sha = hashlib.sha256(engineer_src.read_bytes()).hexdigest()
        assert f"{FRAMES_CUSTOMER_UPSTREAM} {expected_customer_sha}" in pinned
        assert f"{FRAMES_ENGINEER_UPSTREAM} {expected_engineer_sha}" in pinned
