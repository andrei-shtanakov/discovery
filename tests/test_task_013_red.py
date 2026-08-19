"""Frozen RED checkpoint for TASK-013.

This file is byte-frozen until the task is done: it exists to prove that,
at the moment the task started, the AST import-graph walker DESIGN-016(a)
describes did not yet exist — not that `discovery.cli` was missing (that is
TASK-012's checkpoint), but that `tests/test_boundary.py`, the module meant
to own `FORBIDDEN_MODULES` and the walker helper, had not been written yet.
Unlike `test_task_012_red.py`, the failure this checkpoint freezes is an
`ImportError` on that helper, not a behavioural gap: today's core already
has no forbidden import, so once the helper exists this same walk is
expected to turn green on its own, locking the property in rather than
proving it.
"""

from __future__ import annotations

from pathlib import Path

CORE_ROOT = Path(__file__).resolve().parents[1] / "src" / "discovery"


class TestBoundaryImportWalkRed:
    def test_core_today_has_no_forbidden_imports(self):
        from test_boundary import FORBIDDEN_MODULES, forbidden_imports_in

        core_files = [
            path
            for path in CORE_ROOT.rglob("*.py")
            if "contract" not in path.relative_to(CORE_ROOT).parts
        ]
        assert core_files, "expected discovery core modules to exist"

        violations = {
            path: mods for path in core_files if (mods := forbidden_imports_in(path))
        }

        assert violations == {}
        assert "os" not in FORBIDDEN_MODULES
