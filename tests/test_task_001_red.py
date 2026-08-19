"""Frozen RED checkpoint for TASK-001.

This file is byte-frozen until the task is done: it exists to prove that,
at the moment the task started, `tools/vendor_pull.py` did not yet perform
the hermetic vendoring behaviour required by REQ-002.
"""

import hashlib
import os
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


class TestVendorPullRed:
    def test_vendor_pull_copies_files_and_writes_pinned_manifest(self, tmp_path):
        upstream = tmp_path / "upstream"
        upstream.mkdir()

        contract_md = upstream / "DISCOVERY-BRIEF-CONTRACT.md"
        contract_md.write_text("# Discovery Brief Contract\n\nfake upstream content.\n")
        gate_check = upstream / "gate_check.py"
        gate_check.write_text("FRAMES = {'customer', 'engineer'}\n")

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
        subprocess.run(
            ["git", "add", "."], cwd=upstream, check=True, capture_output=True
        )
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

        dest = tmp_path / "dest"

        result = subprocess.run(
            ["uv", "run", "tools/vendor_pull.py", str(upstream)],
            cwd=REPO_ROOT,
            env={**os.environ, "VENDOR_DEST": str(dest)},
            capture_output=True,
            text=True,
        )

        assert result.returncode == 0, (
            f"vendor_pull.py did not run cleanly: {result.stderr}"
        )

        copied_md = dest / "DISCOVERY-BRIEF-CONTRACT.md"
        copied_gate = dest / "gate_check.py"
        assert copied_md.read_bytes() == contract_md.read_bytes()
        assert copied_gate.read_bytes() == gate_check.read_bytes()

        pinned = (dest / "PINNED.txt").read_text()
        assert f"commit: {head}" in pinned

        expected_md_sha = hashlib.sha256(contract_md.read_bytes()).hexdigest()
        expected_gate_sha = hashlib.sha256(gate_check.read_bytes()).hexdigest()
        assert f"DISCOVERY-BRIEF-CONTRACT.md {expected_md_sha}" in pinned
        assert f"gate_check.py {expected_gate_sha}" in pinned
