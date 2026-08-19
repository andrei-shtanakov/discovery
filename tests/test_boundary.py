"""TASK-013 — capability boundary: author != execute (DESIGN-016).

Two independent claims, neither checked as a string search:

(a) No network/process-launch import anywhere in `src/discovery/**/*.py`
(excluding `contract/`, vendored and covered by its own copy-integrity
test — TASK-002). `forbidden_imports_in` walks the AST and collects the
root module of every `Import`/`ImportFrom`, plus any `os.system`/
`os.exec*` call — `os` itself is not forbidden, since `os.path`/
`os.environ` are legitimate, only its process-launch attributes are.

(b) A full CLI run (`start` -> `answer` on every required question ->
`brief --out`) only ever writes under `sessions_root()` or the one
passed `--out` path — never into `cwd` or anywhere else. This is a
behavioural, filesystem-snapshot assertion, not a name-based one; the
`tasks.md`/`design.md` check below is kept only as a secondary, redundant
sanity check on top of it.
"""

from __future__ import annotations

import ast
import json
from pathlib import Path

from discovery import cli
from discovery.questions import Question, StaticQuestionSource

CORE_ROOT = Path(__file__).resolve().parent.parent / "src" / "discovery"

FORBIDDEN_MODULES = frozenset(
    {
        "socket",
        "http",
        "urllib",
        "requests",
        "httpx",
        "subprocess",
        "asyncio",
    }
)

_PROCESS_LAUNCH_ATTR = "system"


def _is_os_process_call(func: ast.expr, os_names: set[str]) -> str | None:
    """`os.system(...)` / `os.exec*(...)` where `os` names an `os` import."""
    if not isinstance(func, ast.Attribute):
        return None
    if not isinstance(func.value, ast.Name) or func.value.id not in os_names:
        return None
    if func.attr == _PROCESS_LAUNCH_ATTR or func.attr.startswith("exec"):
        return f"os.{func.attr}"
    return None


def forbidden_imports_in(path: Path) -> set[str]:
    """Root modules from `FORBIDDEN_MODULES` plus `os.system`/`os.exec*` calls.

    A plain `"os" in FORBIDDEN_MODULES` would false-positive on the
    legitimate `os.path`/`os.environ` usage in `session.py`/`cli.py`, so
    `os` as a whole module is never flagged — only its process-launch
    attributes, detected as `ast.Call` nodes.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    os_names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                root = alias.name.split(".")[0]
                if root == "os":
                    os_names.add(alias.asname or root)

    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                root = alias.name.split(".")[0]
                if root in FORBIDDEN_MODULES:
                    found.add(root)
        elif isinstance(node, ast.ImportFrom):
            root = (node.module or "").split(".")[0]
            if root in FORBIDDEN_MODULES:
                found.add(root)
        elif isinstance(node, ast.Call):
            call = _is_os_process_call(node.func, os_names)
            if call is not None:
                found.add(call)
    return found


def _core_files() -> list[Path]:
    """`src/discovery/**/*.py`, excluding the vendored `contract/` tree."""
    return [
        path
        for path in CORE_ROOT.rglob("*.py")
        if "contract" not in path.relative_to(CORE_ROOT).parts
    ]


class TestForbiddenImportWalk:
    """DESIGN-016(a): the import graph's shape, not a string search."""

    def test_core_has_no_forbidden_imports(self):
        core_files = _core_files()
        assert core_files, "expected discovery core modules to exist"

        violations = {
            path: mods for path in core_files if (mods := forbidden_imports_in(path))
        }

        assert violations == {}

    def test_os_module_itself_is_not_forbidden(self):
        assert "os" not in FORBIDDEN_MODULES

    def test_os_system_call_is_detected(self, tmp_path):
        sample = tmp_path / "sample.py"
        sample.write_text("import os\nos.system('rm -rf /')\n")

        assert forbidden_imports_in(sample) == {"os.system"}

    def test_os_exec_call_is_detected(self, tmp_path):
        sample = tmp_path / "sample.py"
        sample.write_text("import os\nos.execvp('sh', ['sh'])\n")

        assert forbidden_imports_in(sample) == {"os.execvp"}

    def test_os_path_and_environ_usage_is_not_flagged(self, tmp_path):
        sample = tmp_path / "sample.py"
        sample.write_text("import os\nos.path.join('a', 'b')\nos.environ.get('X')\n")

        assert forbidden_imports_in(sample) == set()

    def test_plain_import_of_forbidden_module_is_detected(self, tmp_path):
        sample = tmp_path / "sample.py"
        sample.write_text("import socket\n")

        assert forbidden_imports_in(sample) == {"socket"}

    def test_from_import_of_forbidden_module_is_detected(self, tmp_path):
        sample = tmp_path / "sample.py"
        sample.write_text("from urllib import request\n")

        assert forbidden_imports_in(sample) == {"urllib"}


REQUIRED_QUESTIONS = {
    "customer": [
        Question("customer.g.01", "goals", "What problem?"),
        Question("customer.j.01", "jobs", "Recent case?"),
    ]
}


def _snapshot(root: Path) -> set[Path]:
    """Every regular file under `root`, present or not (missing -> empty)."""
    if not root.exists():
        return set()
    return {path for path in root.rglob("*") if path.is_file()}


def _run(capsys, argv):
    code = cli.main(argv)
    return code, json.loads(capsys.readouterr().out)


class TestWriteCapabilityBoundary:
    """DESIGN-016(b): the only writes a full run performs."""

    def test_full_run_only_writes_under_session_root_or_out_path(
        self, capsys, monkeypatch, tmp_path
    ):
        home = tmp_path / "home"
        cwd = tmp_path / "cwd"
        cwd.mkdir()
        out_dir = tmp_path / "out"
        out_dir.mkdir()
        out_path = out_dir / "brief.md"
        fixtures = tmp_path / "fixtures"
        fixtures.mkdir()
        answer_paths = [
            fixtures / f"answer-{i}.yaml"
            for i in range(len(REQUIRED_QUESTIONS["customer"]))
        ]
        for i, answer_path in enumerate(answer_paths):
            answer_path.write_text(f"text: answer {i}\n")

        monkeypatch.setenv("DISCOVERY_HOME", str(home))
        monkeypatch.chdir(cwd)
        source = StaticQuestionSource("pin-boundary", REQUIRED_QUESTIONS)
        monkeypatch.setattr(cli, "build_source", lambda: source)

        before = _snapshot(tmp_path)

        _, started = _run(
            capsys, ["start", "--frame", "customer", "--target", "org/repo"]
        )
        session_id = started["next_action"]["session_id"]

        next_action = started["next_action"]
        for answer_path in answer_paths:
            assert next_action != {}
            _, envelope = _run(
                capsys,
                [
                    "answer",
                    "--session",
                    session_id,
                    "--role",
                    "customer",
                    "--file",
                    str(answer_path),
                ],
            )
            next_action = envelope["next_action"]
        assert next_action == {}

        _, brief_envelope = _run(
            capsys, ["brief", "--session", session_id, "--out", str(out_path)]
        )
        assert brief_envelope["lifecycle"] == "complete"

        after = _snapshot(tmp_path)
        created = after - before
        sessions_root = home / "sessions"
        outside_session_root = {
            path for path in created if not path.is_relative_to(sessions_root)
        }

        assert outside_session_root == {out_path}
        assert _snapshot(cwd) == set()
        assert not any(tmp_path.rglob("tasks.md"))
        assert not any(tmp_path.rglob("design.md"))
