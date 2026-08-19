"""Frozen RED checkpoint for TASK-002.

This file is byte-frozen until the task is done: it exists to prove that,
at the moment the task started, `tools/check_vendor.py` did not yet exist,
so the consistency guarantee promised by REQ-006 could not be checked —
"copy is internally consistent with its own PINNED.txt" was not yet an
assertion anyone could run.

The freeze ended with the run that wrote it (merged in PR #9). The synthetic
manifest below mirrors `check_vendor.EXPECTED_SURFACE`, which is a fact that
legitimately grows: `verify()` rejects a manifest that does not cover the whole
surface *before* it compares any bytes, so a fixture listing fewer files stops
testing what it claims. TODO: extend it whenever the vendored surface changes —
the frames were added for TASK-014.
"""

import hashlib
import os
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


class TestCheckVendorRed:
    def test_consistency_exits_zero_when_pinned_matches_local_files(self, tmp_path):
        dest = tmp_path / "dest"
        dest.mkdir()

        contract_md = dest / "DISCOVERY-BRIEF-CONTRACT.md"
        contract_md.write_text("# Discovery Brief Contract\n\nfake pinned content.\n")
        gate_check = dest / "gate_check.py"
        gate_check.write_text("FRAMES = {'customer', 'engineer'}\n")
        frames = dest / "frames"
        frames.mkdir()
        customer = frames / "customer.md"
        customer.write_text("# fake customer frame\n")
        engineer = frames / "engineer.md"
        engineer.write_text("# fake engineer frame\n")

        md_sha = hashlib.sha256(contract_md.read_bytes()).hexdigest()
        gate_sha = hashlib.sha256(gate_check.read_bytes()).hexdigest()
        customer_sha = hashlib.sha256(customer.read_bytes()).hexdigest()
        engineer_sha = hashlib.sha256(engineer.read_bytes()).hexdigest()
        bank = ".claude/skills/discovery-interview/frames"
        (dest / "PINNED.txt").write_text(
            "upstream: git@github.com:andrei-shtanakov/discovery-toolkit.git\n"
            "commit: 0000000000000000000000000000000000000000\n"
            "\n"
            f"DISCOVERY-BRIEF-CONTRACT.md {md_sha}\n"
            f"gate_check.py {gate_sha}\n"
            f"{bank}/customer.md {customer_sha}\n"
            f"{bank}/engineer.md {engineer_sha}\n"
        )

        result = subprocess.run(
            ["uv", "run", "tools/check_vendor.py", "consistency"],
            cwd=REPO_ROOT,
            env={**os.environ, "VENDOR_DEST": str(dest)},
            capture_output=True,
            text=True,
        )

        assert result.returncode == 0, (
            "expected exit 0 for a pin that matches its local files, got "
            f"{result.returncode}: {result.stderr}"
        )
