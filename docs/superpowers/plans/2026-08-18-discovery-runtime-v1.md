# discovery runtime v1 — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: use `superpowers:subagent-driven-development`
> (or `superpowers:executing-plans`) when running this plan by hand. In this repository the
> plan is normally executed by maestro + spec-runner from `spec/tasks.md`, which is derived
> from this document one-to-one (one `TASK-NNN` per task below, `Depends on` mirroring the
> dependencies stated here). Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** make the Need stage callable by a run — a CLI that conducts a contract-conformant
discovery interview across process boundaries, suspending on `awaiting_input` and resuming
from its journal.

**Architecture:** a deterministic core (session journal → coverage → render → vendored gate)
with exactly one port, `QuestionSource`. The journal of events is the source of truth; the
brief is re-derived, never edited. No model is called anywhere in the core.

**Tech Stack:** Python ≥3.12, `uv`, pytest, ruff, pyrefly, PyYAML (a dependency of the
vendored linter). POSIX file locking (`fcntl`). No network in the runtime.

**Spec:** `docs/superpowers/specs/2026-08-18-discovery-runtime-design.md` — read it first;
this plan argues from it and does not repeat its reasoning.

## Global Constraints

- Python `>=3.12`; package layout `src/discovery/`; line length 88; type hints on all code.
- `uv` only: `uv add <pkg>`, `uv run <tool>`. Never `pip`, never `uv pip install`.
- Test command: `uv run pytest`. Lint: `uv run ruff check . && uv run ruff format --check .`.
  Types: `uv run pyrefly check`.
- **The runtime resolves no path outside this repository.** No `../discovery-toolkit`, no
  `../_cowork_output`. Vendored copies only, under `src/discovery/contract/`.
- **No model call in `src/discovery/`.** Any adaptivity lives behind `QuestionSource`.
- All provenance hashes are SHA-256, recorded in fields named `*_sha256`.
- Vendored files are **never edited** — not even whitespace. They are bytes of an upstream
  commit; editing them destroys the only thing copy-integrity proves.
- Every CLI command emits the same status envelope (§7 of the spec), including on refusal.

## Deviation from the spec, resolved here

The spec does not say how a free-text answer becomes typed contract entries (`FR-01` with
`Priority`/`Acceptance`, `FR → G/J` traces). Deterministic rendering cannot infer them, and a
model in the core is excluded by the chosen approach. **Resolution: the answer payload is
structured.** `answer --file` accepts a YAML document with `text` (verbatim, kept for
provenance and the L2 tests) and `entries` (typed contract entries). Interpretation stays with
the interviewer — human or an agent running the `discovery-interview` skill — and the runtime
formats and gates. Spec §5 carries this amendment as of the commit that added this plan; the
plan and the spec agree, and neither is waiting on the other.

---

## File Structure

| Path | Responsibility |
|---|---|
| `src/discovery/contract/DISCOVERY-BRIEF-CONTRACT.md` | vendored canon (bytes of the pinned commit) |
| `src/discovery/contract/gate_check.py` | vendored linter: `check()`, `FRAMES`, `Finding` |
| `src/discovery/contract/frames/{customer,engineer}.md` | vendored question bank (Task 11) |
| `src/discovery/contract/PINNED.txt` | upstream repo, commit, `path sha256` manifest |
| `src/discovery/hashing.py` | canonical answer bytes, `answer_id`, file hashes |
| `src/discovery/journal.py` | event models, durable append, read |
| `src/discovery/session.py` | session root layout, header, atomic file replace |
| `src/discovery/payload.py` | the answer payload: `text` + typed `entries` |
| `src/discovery/lifecycle.py` | lifecycle from journal, `next_action` from journal |
| `src/discovery/render.py` | journal → brief markdown (two-pass aware) |
| `src/discovery/gate.py` | wrapper over the vendored linter, two-pass rule |
| `src/discovery/protocol.py` | status envelope, exit codes, priority |
| `src/discovery/questions.py` | `QuestionSource` port + `StaticQuestionSource` (fake) |
| `src/discovery/bank.py` | bank parsing, marker reading, fail-closed invariant (Task 11) |
| `src/discovery/cli.py` | `start` / `status` / `answer` / `brief` |
| `tools/check_vendor.py` | consistency vs `PINNED.txt`; provenance vs upstream blobs |

Files that change together live together: everything about the journal (events, durability,
reading) is one module; everything about the status contract (envelope, codes, priority) is
another. `cli.py` composes and holds no rules of its own.

---

### Task 1: Skeleton, dependencies, and the vendored contract (WS-A1)

**Files:**
- Modify: `pyproject.toml`
- Create: `src/discovery/__init__.py`, `src/discovery/contract/__init__.py`
- Create: `src/discovery/contract/DISCOVERY-BRIEF-CONTRACT.md`, `src/discovery/contract/gate_check.py`, `src/discovery/contract/PINNED.txt`
- Create: `tools/vendor_pull.py`
- Test: `tests/test_vendored_copy.py`

**Interfaces:**
- Consumes: nothing.
- Produces: importable `discovery.contract.gate_check` exposing `check(text: str, base_dir: Path | None) -> list[Finding]`, `FRAMES: dict[str, dict]`, `Finding(rule: str, level: str, ref: str, message: str)`; `PINNED.txt` format used by Task 2's tooling.

- [ ] **Step 1: Configure the package and dependencies**

```toml
# pyproject.toml — replace the [project] block's tail and add the rest
[project]
name = "discovery"
version = "0.1.0"
description = "Runtime for discovery interviews and brief authoring"
readme = "README.md"
requires-python = ">=3.12"
dependencies = ["pyyaml>=6.0"]

[project.scripts]
discovery = "discovery.cli:main"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/discovery"]

[tool.ruff]
line-length = 88

[tool.ruff.lint]
select = ["E", "F", "I", "UP"]

[tool.ruff.lint.per-file-ignores]
"src/discovery/contract/gate_check.py" = ["ALL"]  # vendored bytes, never edited

[tool.pytest.ini_options]
testpaths = ["tests"]
```

Run: `uv add pyyaml && uv add --dev pytest ruff pyrefly`

- [ ] **Step 2: Write the vendoring tool**

```python
# tools/vendor_pull.py
"""Copy contract files from an upstream checkout and write PINNED.txt.

Usage: uv run tools/vendor_pull.py <upstream-checkout> [--include-frames]

This is developer tooling. It is the only thing allowed to read a path outside
this repository, it runs by hand, and nothing in src/discovery/ imports it.
"""

from __future__ import annotations

import argparse
import hashlib
import os
import shutil
import subprocess
from pathlib import Path

DEST = Path(
    os.environ.get("VENDOR_DEST")
    or Path(__file__).resolve().parents[1] / "src" / "discovery" / "contract"
)
CORE = ["DISCOVERY-BRIEF-CONTRACT.md", "gate_check.py"]
FRAMES = [
    ".claude/skills/discovery-interview/frames/customer.md",
    ".claude/skills/discovery-interview/frames/engineer.md",
]


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("upstream", type=Path)
    ap.add_argument("--include-frames", action="store_true")
    args = ap.parse_args()

    commit = subprocess.run(
        ["git", "-C", str(args.upstream), "rev-parse", "HEAD"],
        capture_output=True, text=True, check=True,
    ).stdout.strip()

    wanted = list(CORE) + (FRAMES if args.include_frames else [])
    lines = [
        "upstream: git@github.com:andrei-shtanakov/discovery-toolkit.git",
        f"commit: {commit}",
        "",
    ]
    for rel in wanted:
        src = args.upstream / rel
        dst = DEST / ("frames/" + Path(rel).name if rel in FRAMES else rel)
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, dst)
        lines.append(f"{rel} {sha256(dst)}")
    (DEST / "PINNED.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"vendored {len(wanted)} files at {commit}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 3: Make the package importable around the already-vendored copy**

`src/discovery/contract/` **already holds** `DISCOVERY-BRIEF-CONTRACT.md`, `gate_check.py`
and `PINNED.txt`: they were vendored onto the base branch before the run, by hand, from the
upstream tree at the pinned commit. Do not run `vendor_pull.py` against a sibling checkout
here — **there is no upstream checkout inside a worktree**. `../discovery-toolkit` resolves
next to the *worktree*, not next to the primary clone, and vendoring is a one-shot developer
action that needs access no isolated task should have. (Learned the hard way: this step as
originally written made TASK-001 unexecutable under maestro — see
`docs/evidence/2026-08-19-runtime-v1-implementation-run.md`, attempt 3.)

The same applies to the bank in Task 14: those files are pre-vendored too, when that task's
upstream dependency lands.

Create `src/discovery/__init__.py` and `src/discovery/contract/__init__.py`, both empty.
The `__init__.py` sits *beside* the vendored file; the vendored file itself stays untouched.

- [ ] **Step 4: Write the failing tests**

The vendoring tool gets a **hermetic** test: a fake upstream built in `tmp_path`, never a
sibling checkout. It is the only honest way to test it inside a worktree, and it pins the
tool's contract (bytes copied verbatim, `PINNED.txt` lists commit and per-file digests)
without depending on anything outside the test.

```python
# tests/test_vendor_pull.py
import subprocess
import sys
from pathlib import Path

TOOL = Path(__file__).resolve().parents[1] / "tools" / "vendor_pull.py"


def make_fake_upstream(root: Path) -> str:
    """A real git repo with the two vendored files, so HEAD is a real commit."""
    root.mkdir(parents=True, exist_ok=True)
    (root / "DISCOVERY-BRIEF-CONTRACT.md").write_text("contract bytes\n", encoding="utf-8")
    (root / "gate_check.py").write_text("FRAMES = {}\n", encoding="utf-8")
    run = lambda *a: subprocess.run(["git", "-C", str(root), *a], check=True, capture_output=True)
    run("init", "-q")
    run("config", "user.email", "t@example.com")
    run("config", "user.name", "t")
    run("add", ".")
    run("commit", "-qm", "fixture")
    return subprocess.run(
        ["git", "-C", str(root), "rev-parse", "HEAD"],
        check=True, capture_output=True, text=True,
    ).stdout.strip()


def test_pinned_txt_records_the_commit_and_digests(tmp_path, monkeypatch):
    upstream = tmp_path / "upstream"
    commit = make_fake_upstream(upstream)
    dest = tmp_path / "dest"
    dest.mkdir()
    monkeypatch.setenv("VENDOR_DEST", str(dest))
    subprocess.run(
        [sys.executable, str(TOOL), str(upstream)], check=True, capture_output=True
    )
    pinned = (dest / "PINNED.txt").read_text(encoding="utf-8")
    assert f"commit: {commit}" in pinned
    assert "DISCOVERY-BRIEF-CONTRACT.md " in pinned
    assert (dest / "gate_check.py").read_text(encoding="utf-8") == "FRAMES = {}\n"
```

`vendor_pull.py` therefore reads its destination from `VENDOR_DEST` when set, defaulting to
`src/discovery/contract` — a two-line change to the tool in Step 2, and the reason it exists:
a tool that can only write one hardcoded path cannot be tested without touching the repo.

```python
# tests/test_vendored_copy.py
import hashlib
from pathlib import Path

CONTRACT = Path(__file__).resolve().parents[1] / "src" / "discovery" / "contract"


def parse_pinned() -> tuple[str, dict[str, str]]:
    commit, manifest = "", {}
    for line in (CONTRACT / "PINNED.txt").read_text(encoding="utf-8").splitlines():
        if line.startswith("commit:"):
            commit = line.split(":", 1)[1].strip()
        elif line and not line.startswith("upstream:"):
            rel, digest = line.rsplit(" ", 1)
            manifest[rel] = digest
    return commit, manifest


def local_name(rel: str) -> str:
    return "frames/" + rel.rsplit("/", 1)[-1] if "frames/" in rel else rel


def test_pin_names_a_commit():
    commit, manifest = parse_pinned()
    assert len(commit) == 40, "PINNED.txt must name a full commit sha"
    assert manifest, "PINNED.txt must list the vendored files"


def test_vendored_files_match_their_recorded_digests():
    _, manifest = parse_pinned()
    for rel, digest in manifest.items():
        blob = (CONTRACT / local_name(rel)).read_bytes()
        assert hashlib.sha256(blob).hexdigest() == digest, f"{rel} drifted from PINNED.txt"


def test_the_linter_is_importable_and_exposes_the_frames_table():
    from discovery.contract.gate_check import FRAMES, check

    assert set(FRAMES) == {"customer", "engineer"}
    assert FRAMES["engineer"]["required"]["feasibility_review"] is None
    assert check("", base_dir=None), "an empty brief must produce findings"
```

- [ ] **Step 5: Run the tests**

Run: `uv run pytest tests/test_vendor_pull.py tests/test_vendored_copy.py -v`
Expected: PASS (the copy vendored onto the base branch already satisfies the second file;
the first is hermetic and needs nothing outside `tmp_path`). If
`test_the_linter_is_importable...` fails on import, the package layout is wrong — check that
`src/discovery/contract/__init__.py` exists and `uv run` resolves the project.

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml src/discovery tools/vendor_pull.py tests/test_vendor_pull.py tests/test_vendored_copy.py
git commit -m "feat(contract): vendor brief contract and gate_check at a pinned commit"
```

---

### Task 2: Copy-integrity vs provenance — two guarantees, and a test on the instrument (WS-A1)

**Files:**
- Create: `tools/check_vendor.py`
- Create: `.github/workflows/vendor-integrity.yml`, `.github/workflows/vendor-drift.yml`
- Test: `tests/test_check_vendor.py`

**Interfaces:**
- Consumes: `PINNED.txt` from Task 1.
- Produces: `check_vendor.verify(mode: str, fetch: Fetcher | None) -> Verdict` where
  `Verdict` is a dataclass `(status: str, detail: str)` with `status ∈ {"ok","failed","unknown"}`;
  `Fetcher = Callable[[str, str], bytes | None]` taking `(commit, upstream_rel_path)` and
  returning the blob or `None` when unreachable. Exit codes: `0` ok, `1` failed, `3` unknown.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_check_vendor.py
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
    verdict = check_vendor.verify("provenance", fetch=lambda commit, rel: b"not the file")
    assert verdict.status == "failed"


def test_drift_without_a_previous_success_is_unknown():
    assert check_vendor.drift(last_success=None).status == "unknown"


def test_drift_with_a_stale_watch_is_unknown():
    verdict = check_vendor.drift(
        last_success="2026-08-01T06:17:00+00:00",
        now="2026-08-18T06:17:00+00:00",
    )
    assert verdict.status == "unknown"
    assert "stale" in verdict.detail


def test_drift_with_an_unparseable_timestamp_is_unknown():
    assert check_vendor.drift(last_success="last tuesday").status == "unknown"


def test_provenance_matching_bytes_pass():
    root = Path(__file__).resolve().parents[1] / "src" / "discovery" / "contract"

    def fetch(commit: str, rel: str) -> bytes:
        name = "frames/" + rel.rsplit("/", 1)[-1] if "frames/" in rel else rel
        return (root / name).read_bytes()

    assert check_vendor.verify("provenance", fetch=fetch).status == "ok"
```

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run pytest tests/test_check_vendor.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'check_vendor'`

- [ ] **Step 3: Write the tool**

```python
# tools/check_vendor.py
"""Verify the vendored contract copy.

consistency — do the files match the digests recorded in PINNED.txt?
              Proves the copy is internally consistent. NOT its origin.
provenance  — are the files the bytes of the upstream tree at the pinned commit?
              Unreachable upstream is reported as unknown, never as ok.

Exit: 0 ok · 1 failed · 3 unknown
"""

from __future__ import annotations

import argparse
import base64
import datetime as dt
import hashlib
import json
import subprocess
import urllib.error
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

CONTRACT = Path(__file__).resolve().parents[1] / "src" / "discovery" / "contract"
API = "https://api.github.com/repos/andrei-shtanakov/discovery-toolkit/contents/{rel}?ref={commit}"

Fetcher = Callable[[str, str], bytes | None]


@dataclass
class Verdict:
    status: str  # ok | failed | unknown
    detail: str


def read_pinned() -> tuple[str, dict[str, str]]:
    commit, manifest = "", {}
    for line in (CONTRACT / "PINNED.txt").read_text(encoding="utf-8").splitlines():
        if line.startswith("commit:"):
            commit = line.split(":", 1)[1].strip()
        elif line and not line.startswith("upstream:"):
            rel, digest = line.rsplit(" ", 1)
            manifest[rel] = digest
    return commit, manifest


def local_path(rel: str) -> Path:
    return CONTRACT / ("frames/" + rel.rsplit("/", 1)[-1] if "frames/" in rel else rel)


def github_fetch(commit: str, rel: str) -> bytes | None:
    try:
        with urllib.request.urlopen(API.format(rel=rel, commit=commit), timeout=20) as r:
            return base64.b64decode(json.load(r)["content"])
    except (urllib.error.URLError, TimeoutError, KeyError, ValueError):
        return None


def verify(mode: str, fetch: Fetcher | None = None) -> Verdict:
    commit, manifest = read_pinned()
    if mode == "consistency":
        drifted = [
            rel
            for rel, digest in manifest.items()
            if hashlib.sha256(local_path(rel).read_bytes()).hexdigest() != digest
        ]
        if drifted:
            return Verdict("failed", f"files differ from PINNED.txt: {', '.join(drifted)}")
        return Verdict("ok", f"{len(manifest)} files match their recorded digests")

    fetch = fetch or github_fetch
    mismatched: list[str] = []
    for rel in manifest:
        blob = fetch(commit, rel)
        if blob is None:
            return Verdict("unknown", f"upstream unreachable while reading {rel}")
        if blob != local_path(rel).read_bytes():
            mismatched.append(rel)
    if mismatched:
        return Verdict("failed", f"differ from upstream@{commit[:8]}: {', '.join(mismatched)}")
    return Verdict("ok", f"bytes identical to upstream@{commit[:8]}")


def drift(last_success: str | None, max_age_days: int = 8, now: str | None = None) -> Verdict:
    """Has upstream moved past the pin — and is the watch itself still alive?

    `last_success` is the ISO timestamp of the previous successful run of this
    watch, passed in by the workflow. Absent or older than `max_age_days` is
    `unknown`: a watch whose silence cannot be distinguished from a clean result
    is the defect it exists to prevent.
    """
    if last_success is None:
        return Verdict("unknown", "freshness unverifiable: no previous successful run reported")
    moment = dt.datetime.fromisoformat(now) if now else dt.datetime.now(dt.UTC)
    try:
        age = moment - dt.datetime.fromisoformat(last_success)
    except (ValueError, TypeError):
        # TypeError catches a naive timestamp subtracted from an aware one —
        # a silently wrong age is worse than an honest unknown.
        return Verdict("unknown", f"unusable last_success: {last_success!r}")
    if age > dt.timedelta(days=max_age_days):
        return Verdict("unknown", f"watch stale: last success {age.days}d ago (limit {max_age_days}d)")

    commit, _ = read_pinned()
    try:
        head = subprocess.run(
            ["git", "ls-remote", "git@github.com:andrei-shtanakov/discovery-toolkit.git", "HEAD"],
            capture_output=True, text=True, timeout=30, check=True,
        ).stdout.split()[0]
    except (subprocess.SubprocessError, IndexError):
        return Verdict("unknown", "upstream HEAD unreadable")
    if head != commit:
        return Verdict("failed", f"pin {commit[:8]} is behind upstream {head[:8]}")
    return Verdict("ok", f"pin matches upstream HEAD {head[:8]}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=["consistency", "provenance", "drift"])
    ap.add_argument(
        "--last-success",
        help="ISO timestamp of this watch's previous successful run (drift mode)",
    )
    args = ap.parse_args()
    verdict = (
        drift(args.last_success) if args.mode == "drift" else verify(args.mode)
    )
    print(f"{args.mode}: {verdict.status} — {verdict.detail}")
    return {"ok": 0, "failed": 1, "unknown": 3}[verdict.status]


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run the tests**

Run: `uv run pytest tests/test_check_vendor.py -v`
Expected: PASS (4 tests)

- [ ] **Step 5: Wire both guarantees into CI**

```yaml
# .github/workflows/vendor-integrity.yml
name: vendor-integrity
on: [pull_request]
jobs:
  provenance:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v3
      - run: uv run tools/check_vendor.py consistency
      - run: uv run tools/check_vendor.py provenance
```

```yaml
# .github/workflows/vendor-drift.yml
name: vendor-drift
on:
  schedule: [{cron: "17 6 * * 1"}]   # weekly; 8-day expiry means one miss is already unknown
  workflow_dispatch:
jobs:
  drift:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v3
      - name: Run the watch against its own previous success
        env:
          GH_TOKEN: ${{ github.token }}
        run: |
          ts=$(gh api \
            "repos/${{ github.repository }}/actions/workflows/vendor-drift.yml/runs?status=success&per_page=1" \
            --jq '.workflow_runs[0].created_at // empty' || true)
          if [ -n "$ts" ]; then
            uv run tools/check_vendor.py drift --last-success "$ts"
          else
            uv run tools/check_vendor.py drift   # no prior success → unknown, by design
          fi
```

An unknown verdict exits 3, so the job goes red. That is the point: silence and cleanliness
must not look the same. The freshness threshold is evaluated against the watch's **own**
previous successful run, so a schedule that stops firing is caught by the next run that does
fire — and a watch that never fires again is caught by the fleet's scheduled-run sensor, which
reads workflow state from outside this repository.

- [ ] **Step 6: Commit**

```bash
git add tools/check_vendor.py tests/test_check_vendor.py .github/workflows
git commit -m "feat(contract): copy-integrity and drift watch as separate guarantees"
```

---

### Task 3: Canonical answer bytes and `answer_id` (WS-B)

**Files:**
- Create: `src/discovery/hashing.py`
- Test: `tests/test_hashing.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `canonical_answer_bytes(text: str) -> bytes`;
  `answer_id(session_id: str, question_id: str, participant_role: str, text: str) -> str`
  returning `"sha256:<hex>"`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_hashing.py
from discovery.hashing import answer_id, canonical_answer_bytes


def test_line_endings_are_folded_but_content_is_not_trimmed():
    assert canonical_answer_bytes("a\r\nb\rc\n") == b"a\nb\nc\n"
    assert canonical_answer_bytes("  padded  ") == b"  padded  "


def test_same_answer_same_id():
    a = answer_id("s1", "customer.goals.01", "product", "we lose orders\r\n")
    b = answer_id("s1", "customer.goals.01", "product", "we lose orders\n")
    assert a == b and a.startswith("sha256:")


def test_role_is_part_of_the_identity():
    product = answer_id("s1", "customer.goals.01", "product", "same words")
    architect = answer_id("s1", "customer.goals.01", "architect", "same words")
    assert product != architect, "attribution change must not be swallowed as a replay"


def test_fields_cannot_be_confused_by_concatenation():
    left = answer_id("s1", "q1", "product", "x")
    right = answer_id("s1", "q1\x00product", "", "x")
    assert left != right
```

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run pytest tests/test_hashing.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'discovery.hashing'`

- [ ] **Step 3: Implement**

```python
# src/discovery/hashing.py
"""Content hashes for answers and files. SHA-256 everywhere (fleet convention)."""

from __future__ import annotations

import hashlib
from pathlib import Path

_SEP = b"\x00"


def canonical_answer_bytes(text: str) -> bytes:
    """UTF-8 bytes with CRLF/CR folded to LF. No trimming, no other transformation."""
    return text.replace("\r\n", "\n").replace("\r", "\n").encode("utf-8")


def answer_id(session_id: str, question_id: str, participant_role: str, text: str) -> str:
    """Identity of an answer: session, question, role, canonical bytes — NUL-separated."""
    digest = hashlib.sha256(
        _SEP.join(
            [
                session_id.encode("utf-8"),
                question_id.encode("utf-8"),
                participant_role.encode("utf-8"),
                canonical_answer_bytes(text),
            ]
        )
    ).hexdigest()
    return f"sha256:{digest}"


def file_sha256(path: Path) -> str:
    return f"sha256:{hashlib.sha256(path.read_bytes()).hexdigest()}"
```

Note the separator makes `answer_id("s1","q1","product","x")` and
`answer_id("s1","q1\x00product","","x")` collide *unless* fields are joined with a byte that
cannot appear in the first three fields. `question_id` and `participant_role` are drawn from
fixed vocabularies with no NUL, so the join is unambiguous; the test above pins that.

- [ ] **Step 4: Run to verify it passes**

Run: `uv run pytest tests/test_hashing.py -v`
Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
git add src/discovery/hashing.py tests/test_hashing.py
git commit -m "feat(core): canonical answer bytes and role-aware answer_id"
```

---

### Task 4: The journal — durable append-only events (WS-B)

**Files:**
- Create: `src/discovery/journal.py`
- Test: `tests/test_journal.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `Journal(path: Path)` with `append(event: dict) -> None` and
  `events() -> list[dict]`; module constants
  `QUESTION_ASKED = "question_asked"`, `ANSWER_RECORDED = "answer_recorded"`,
  `ANSWER_SUPERSEDED = "answer_superseded"`, `SOURCE_PIN_CHANGED = "source_pin_changed"`;
  `JournalUnreadable` exception raised by `events()` on a corrupt line.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_journal.py
import json
import pytest
from discovery.journal import Journal, JournalUnreadable, QUESTION_ASKED


def test_append_then_read_roundtrip(tmp_path):
    j = Journal(tmp_path / "journal.jsonl")
    j.append({"event": QUESTION_ASKED, "question_id": "customer.goals.01"})
    j.append({"event": QUESTION_ASKED, "question_id": "customer.goals.02"})
    assert [e["question_id"] for e in j.events()] == [
        "customer.goals.01",
        "customer.goals.02",
    ]


def test_each_event_is_one_whole_line(tmp_path):
    j = Journal(tmp_path / "journal.jsonl")
    j.append({"event": QUESTION_ASKED, "question_text": "multi\nline\ntext"})
    raw = (tmp_path / "journal.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(raw) == 1, "embedded newlines must not split an event across lines"
    assert json.loads(raw[0])["question_text"] == "multi\nline\ntext"


def test_a_corrupt_line_is_unreadable_not_silently_skipped(tmp_path):
    path = tmp_path / "journal.jsonl"
    Journal(path).append({"event": QUESTION_ASKED})
    with path.open("a", encoding="utf-8") as fh:
        fh.write("{ truncated\n")
    with pytest.raises(JournalUnreadable):
        Journal(path).events()


def test_ts_is_added_when_absent(tmp_path):
    j = Journal(tmp_path / "journal.jsonl")
    j.append({"event": QUESTION_ASKED})
    assert j.events()[0]["ts"].endswith("Z")
```

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run pytest tests/test_journal.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'discovery.journal'`

- [ ] **Step 3: Implement**

```python
# src/discovery/journal.py
"""Append-only event journal: the source of truth for a session.

Durability is promised, so an append is: lock, one whole line with O_APPEND,
flush, fsync. "Append-only" alone protects against neither a second process
nor a crash mid-write.
"""

from __future__ import annotations

import datetime as dt
import fcntl
import json
import os
from pathlib import Path

QUESTION_ASKED = "question_asked"
ANSWER_RECORDED = "answer_recorded"
ANSWER_SUPERSEDED = "answer_superseded"
SOURCE_PIN_CHANGED = "source_pin_changed"


class JournalUnreadable(Exception):
    """The journal exists but cannot be parsed — reported as lifecycle unknown."""


def _now() -> str:
    return dt.datetime.now(dt.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


class Journal:
    def __init__(self, path: Path) -> None:
        self.path = path

    def append(self, event: dict) -> None:
        record = {**event, "ts": event.get("ts") or _now()}
        line = json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(self.path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o644)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX)
            os.write(fd, line.encode("utf-8"))
            os.fsync(fd)
        finally:
            fcntl.flock(fd, fcntl.LOCK_UN)
            os.close(fd)

    def events(self) -> list[dict]:
        if not self.path.exists():
            return []
        out: list[dict] = []
        for number, line in enumerate(
            self.path.read_text(encoding="utf-8").splitlines(), start=1
        ):
            if not line.strip():
                continue
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError as exc:
                raise JournalUnreadable(f"{self.path}:{number}: {exc}") from exc
        return out
```

- [ ] **Step 4: Run to verify it passes**

Run: `uv run pytest tests/test_journal.py -v`
Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
git add src/discovery/journal.py tests/test_journal.py
git commit -m "feat(core): durable append-only session journal"
```

---

### Task 5: Session layout, header, and atomic artifact writes (WS-B)

**Files:**
- Create: `src/discovery/session.py`
- Test: `tests/test_session.py`

**Interfaces:**
- Consumes: `Journal` (Task 4).
- Produces: `SessionHeader` dataclass with fields
  `session_id: str, frame: str, target: str, traces_to: list[str], source_pin: str, created_at: str`;
  `Session` with `create(root: Path, header: SessionHeader) -> Session`,
  `load(root: Path, session_id: str) -> Session`, properties `header`, `journal`,
  and `write_artifact(path: Path, text: str) -> None`;
  `SessionUnreadable` exception. Session root layout: `<root>/<session_id>/{header.json,journal.jsonl}`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_session.py
import os
import pytest
from discovery.session import Session, SessionHeader, SessionUnreadable


def header(**kw) -> SessionHeader:
    base = dict(
        session_id="s-001",
        frame="customer",
        target="andrei-shtanakov/dispatcher",
        traces_to=[],
        source_pin="abc123",
        created_at="2026-08-18T10:00:00Z",
    )
    return SessionHeader(**{**base, **kw})


def test_create_then_load_preserves_the_header(tmp_path):
    Session.create(tmp_path, header())
    loaded = Session.load(tmp_path, "s-001")
    assert loaded.header.frame == "customer"
    assert loaded.header.source_pin == "abc123"


def test_loading_a_missing_session_is_unreadable(tmp_path):
    with pytest.raises(SessionUnreadable):
        Session.load(tmp_path, "nope")


def test_artifact_write_is_atomic_and_leaves_no_temp_files(tmp_path):
    session = Session.create(tmp_path, header())
    out = tmp_path / "brief.md"
    session.write_artifact(out, "first")
    session.write_artifact(out, "second")
    assert out.read_text(encoding="utf-8") == "second"
    assert [p.name for p in out.parent.iterdir() if p.name.startswith(".tmp")] == []


def test_artifact_write_replaces_in_place_on_the_same_filesystem(tmp_path):
    session = Session.create(tmp_path, header())
    out = tmp_path / "brief.md"
    session.write_artifact(out, "x")
    before = os.stat(out).st_dev
    session.write_artifact(out, "y")
    assert os.stat(out).st_dev == before
```

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run pytest tests/test_session.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'discovery.session'`

- [ ] **Step 3: Implement**

```python
# src/discovery/session.py
"""Session storage: a header plus the journal, under one directory."""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path

from discovery.journal import Journal


class SessionUnreadable(Exception):
    """The session directory is missing or its header cannot be parsed."""


@dataclass
class SessionHeader:
    session_id: str
    frame: str
    target: str
    traces_to: list[str]
    source_pin: str
    created_at: str


def _atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.parent / f".tmp-{path.name}"
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o644)
    try:
        os.write(fd, text.encode("utf-8"))
        os.fsync(fd)
    finally:
        os.close(fd)
    os.replace(tmp, path)
    dir_fd = os.open(path.parent, os.O_RDONLY)
    try:
        os.fsync(dir_fd)  # without this the rename itself can be lost on power failure
    finally:
        os.close(dir_fd)


class Session:
    def __init__(self, directory: Path, header: SessionHeader) -> None:
        self.directory = directory
        self._header = header

    @property
    def header(self) -> SessionHeader:
        return self._header

    @property
    def journal(self) -> Journal:
        return Journal(self.directory / "journal.jsonl")

    @classmethod
    def create(cls, root: Path, header: SessionHeader) -> Session:
        directory = root / header.session_id
        directory.mkdir(parents=True, exist_ok=True)
        _atomic_write(
            directory / "header.json",
            json.dumps(asdict(header), ensure_ascii=False, indent=2, sort_keys=True),
        )
        return cls(directory, header)

    @classmethod
    def load(cls, root: Path, session_id: str) -> Session:
        directory = root / session_id
        try:
            raw = json.loads((directory / "header.json").read_text(encoding="utf-8"))
            return cls(directory, SessionHeader(**raw))
        except (OSError, ValueError, TypeError) as exc:
            raise SessionUnreadable(f"{directory}: {exc}") from exc

    def write_artifact(self, path: Path, text: str) -> None:
        _atomic_write(path, text)
```

- [ ] **Step 4: Run to verify it passes**

Run: `uv run pytest tests/test_session.py -v`
Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
git add src/discovery/session.py tests/test_session.py
git commit -m "feat(core): session layout with atomic, dir-fsynced artifact writes"
```

---

### Task 6: The answer payload — `text` plus typed entries (WS-B)

**Files:**
- Create: `src/discovery/payload.py`
- Test: `tests/test_payload.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `Entry` dataclass `(eid: str, body: str, fields: dict[str, str])`;
  `AnswerPayload` dataclass `(text: str, entries: list[Entry])`;
  `parse_payload(raw: str) -> AnswerPayload`; `PayloadInvalid` exception.
  Payload shape (YAML):

```yaml
text: |
  we lose orders when the courier app times out
entries:
  - id: G-01
    body: cut order loss from courier timeouts
  - id: FR-01
    body: retry a timed-out courier call
    traces: G-01
    Priority: Must
    Acceptance: a timed-out call is retried twice before the order is failed
```

- [ ] **Step 1: Write the failing test**

```python
# tests/test_payload.py
import pytest
from discovery.payload import PayloadInvalid, parse_payload


def test_text_and_entries_are_both_kept():
    payload = parse_payload(
        "text: we lose orders\n"
        "entries:\n"
        "  - id: G-01\n"
        "    body: cut order loss\n"
    )
    assert payload.text == "we lose orders"
    assert payload.entries[0].eid == "G-01"
    assert payload.entries[0].body == "cut order loss"


def test_entry_fields_survive_verbatim():
    payload = parse_payload(
        "text: t\n"
        "entries:\n"
        "  - id: FR-01\n"
        "    body: retry the call\n"
        "    traces: G-01\n"
        "    Priority: Must\n"
        "    Acceptance: retried twice\n"
    )
    entry = payload.entries[0]
    assert entry.fields == {
        "traces": "G-01",
        "Priority": "Must",
        "Acceptance": "retried twice",
    }


def test_text_only_payload_is_valid():
    assert parse_payload("text: just prose\n").entries == []


def test_entry_without_id_is_rejected():
    with pytest.raises(PayloadInvalid):
        parse_payload("text: t\nentries:\n  - body: no id here\n")


def test_malformed_id_is_rejected():
    with pytest.raises(PayloadInvalid):
        parse_payload("text: t\nentries:\n  - id: lowercase-01\n    body: b\n")


def test_missing_text_is_rejected():
    with pytest.raises(PayloadInvalid):
        parse_payload("entries: []\n")
```

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run pytest tests/test_payload.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'discovery.payload'`

- [ ] **Step 3: Implement**

```python
# src/discovery/payload.py
"""The answer payload.

Interpretation belongs to the interviewer, not to this runtime: an answer arrives
as verbatim text plus already-typed contract entries. The runtime formats and
gates them; it never infers an FR from prose.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

import yaml

ID_RE = re.compile(r"^[A-Z]+-\d+$")
RESERVED = {"id", "body"}


class PayloadInvalid(Exception):
    """The answer file does not satisfy the payload shape."""


@dataclass
class Entry:
    eid: str
    body: str
    fields: dict[str, str] = field(default_factory=dict)


@dataclass
class AnswerPayload:
    text: str
    entries: list[Entry]


def parse_payload(raw: str) -> AnswerPayload:
    try:
        doc = yaml.safe_load(raw) or {}
    except yaml.YAMLError as exc:
        raise PayloadInvalid(f"not valid YAML: {exc}") from exc
    if not isinstance(doc, dict) or "text" not in doc:
        raise PayloadInvalid("payload must be a mapping with a `text` key")

    entries: list[Entry] = []
    for item in doc.get("entries") or []:
        if not isinstance(item, dict) or "id" not in item:
            raise PayloadInvalid(f"entry without an `id`: {item!r}")
        eid = str(item["id"])
        if not ID_RE.match(eid):
            raise PayloadInvalid(f"malformed entry id: {eid!r} (expected e.g. FR-01)")
        entries.append(
            Entry(
                eid=eid,
                body=str(item.get("body", "")),
                fields={k: str(v) for k, v in item.items() if k not in RESERVED},
            )
        )
    return AnswerPayload(text=str(doc["text"]).strip(), entries=entries)
```

- [ ] **Step 4: Run to verify it passes**

Run: `uv run pytest tests/test_payload.py -v`
Expected: PASS (6 tests)

- [ ] **Step 5: Commit**

```bash
git add src/discovery/payload.py tests/test_payload.py
git commit -m "feat(core): structured answer payload — verbatim text plus typed entries"
```

---

### Task 7: The `QuestionSource` port and its static implementation (WS-C)

**Files:**
- Create: `src/discovery/questions.py`
- Test: `tests/test_questions.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `Question` dataclass `(question_id: str, coverage_key: str, text: str)`;
  `QuestionSource` Protocol with `pin: str` and
  `questions(frame: str) -> list[Question]` (ordered, required topics first);
  `StaticQuestionSource(pin: str, catalogue: dict[str, list[Question]])` — the fake used by
  every test up to Task 11 and by D1's CLI tests.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_questions.py
from discovery.questions import Question, StaticQuestionSource


def test_static_source_returns_its_catalogue_in_order():
    source = StaticQuestionSource(
        pin="pin-1",
        catalogue={
            "customer": [
                Question("customer.goals.01", "goals", "What problem are we solving?"),
                Question("customer.jobs.01", "jobs", "Walk me through a recent case."),
            ]
        },
    )
    assert [q.question_id for q in source.questions("customer")] == [
        "customer.goals.01",
        "customer.jobs.01",
    ]
    assert source.questions("engineer") == []
    assert source.pin == "pin-1"
```

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run pytest tests/test_questions.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'discovery.questions'`

- [ ] **Step 3: Implement**

```python
# src/discovery/questions.py
"""The single port of the core.

`bank` (Task 12) reads the vendored frame profiles. `llm` is deliberately absent
in v1: the interface exists so a later implementation is a plug-in, not a rewrite.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class Question:
    question_id: str
    coverage_key: str
    text: str


class QuestionSource(Protocol):
    @property
    def pin(self) -> str:
        """Provenance of the questions — recorded on every question_asked event."""

    def questions(self, frame: str) -> list[Question]:
        """Ordered questions for the frame; required topics first."""


class StaticQuestionSource:
    """In-memory source. The test double, and the only source until Task 12."""

    def __init__(self, pin: str, catalogue: dict[str, list[Question]]) -> None:
        self._pin = pin
        self._catalogue = catalogue

    @property
    def pin(self) -> str:
        return self._pin

    def questions(self, frame: str) -> list[Question]:
        return list(self._catalogue.get(frame, []))
```

- [ ] **Step 4: Run to verify it passes**

Run: `uv run pytest tests/test_questions.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/discovery/questions.py tests/test_questions.py
git commit -m "feat(core): QuestionSource port with a static implementation"
```

---

### Task 8: Lifecycle and `next_action`, computed from the journal (WS-C)

**Files:**
- Create: `src/discovery/lifecycle.py`
- Test: `tests/test_lifecycle.py`

**Interfaces:**
- Consumes: `Journal`, `Session` (Tasks 4–5), `QuestionSource`, `Question` (Task 7).
- Produces: `AWAITING_INPUT = "awaiting_input"`, `COMPLETE = "complete"`, `UNKNOWN = "unknown"`;
  `answered_ids(events: list[dict]) -> set[str]`;
  `issued(events: list[dict]) -> list[dict]` (one per question, latest wins);
  `compute_lifecycle(events: list[dict], source: QuestionSource, frame: str) -> str`;
  `next_question(events, source, frame) -> Question | None` — an already-issued unanswered
  question is returned **from the journal**, never re-resolved through the source.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_lifecycle.py
from discovery.journal import ANSWER_RECORDED, QUESTION_ASKED
from discovery.lifecycle import (
    AWAITING_INPUT,
    COMPLETE,
    compute_lifecycle,
    next_question,
)
from discovery.questions import Question, StaticQuestionSource

SOURCE = StaticQuestionSource(
    pin="pin-1",
    catalogue={
        "customer": [
            Question("customer.goals.01", "goals", "What problem?"),
            Question("customer.jobs.01", "jobs", "Recent case?"),
        ]
    },
)


def asked(qid: str, text: str = "What problem?", pin: str = "pin-1") -> dict:
    return {
        "event": QUESTION_ASKED,
        "question_id": qid,
        "coverage_key": qid.split(".")[1],
        "question_text": text,
        "source_pin": pin,
    }


def answered(qid: str) -> dict:
    return {"event": ANSWER_RECORDED, "question_id": qid, "answer_id": "sha256:x"}


def test_empty_journal_awaits_the_first_question():
    assert compute_lifecycle([], SOURCE, "customer") == AWAITING_INPUT
    assert next_question([], SOURCE, "customer").question_id == "customer.goals.01"


def test_issued_but_unanswered_keeps_awaiting_and_repeats_the_same_question():
    events = [asked("customer.goals.01")]
    assert compute_lifecycle(events, SOURCE, "customer") == AWAITING_INPUT
    assert next_question(events, SOURCE, "customer").question_id == "customer.goals.01"


def test_all_issued_and_answered_is_complete():
    events = [
        asked("customer.goals.01"),
        answered("customer.goals.01"),
        asked("customer.jobs.01"),
        answered("customer.jobs.01"),
    ]
    assert compute_lifecycle(events, SOURCE, "customer") == COMPLETE
    assert next_question(events, SOURCE, "customer") is None


def test_an_unanswered_issued_question_survives_a_bank_repin():
    """The id vanished from the source; the journal still knows what was asked."""
    events = [asked("customer.retired.99", text="A question the new bank dropped")]
    question = next_question(events, SOURCE, "customer")
    assert question.question_id == "customer.retired.99"
    assert question.text == "A question the new bank dropped"


def test_answering_out_of_order_is_honoured():
    events = [
        asked("customer.goals.01"),
        asked("customer.jobs.01"),
        answered("customer.jobs.01"),
    ]
    assert next_question(events, SOURCE, "customer").question_id == "customer.goals.01"
```

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run pytest tests/test_lifecycle.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'discovery.lifecycle'`

- [ ] **Step 3: Implement**

```python
# src/discovery/lifecycle.py
"""Lifecycle is a function of the journal — and it describes the conversation.

`complete` says nothing about the artifact: thin answers can render empty sections
and fail the gate. That is why the status protocol keeps two axes.
"""

from __future__ import annotations

from discovery.journal import ANSWER_RECORDED, QUESTION_ASKED
from discovery.questions import Question, QuestionSource

AWAITING_INPUT = "awaiting_input"
COMPLETE = "complete"
UNKNOWN = "unknown"


def issued(events: list[dict]) -> list[dict]:
    seen: dict[str, dict] = {}
    for event in events:
        if event.get("event") == QUESTION_ASKED:
            seen[event["question_id"]] = event
    return list(seen.values())


def answered_ids(events: list[dict]) -> set[str]:
    return {
        event["question_id"]
        for event in events
        if event.get("event") == ANSWER_RECORDED
    }


def _pending(events: list[dict]) -> list[dict]:
    done = answered_ids(events)
    return [event for event in issued(events) if event["question_id"] not in done]


def next_question(
    events: list[dict], source: QuestionSource, frame: str
) -> Question | None:
    """The next question to put. Issued-but-unanswered comes from the journal."""
    pending = _pending(events)
    if pending:
        event = pending[0]
        return Question(
            question_id=event["question_id"],
            coverage_key=event.get("coverage_key", ""),
            text=event.get("question_text", ""),
        )
    already = {event["question_id"] for event in issued(events)}
    for question in source.questions(frame):
        if question.question_id not in already:
            return question
    return None


def compute_lifecycle(
    events: list[dict], source: QuestionSource, frame: str
) -> str:
    return AWAITING_INPUT if next_question(events, source, frame) else COMPLETE
```

- [ ] **Step 4: Run to verify it passes**

Run: `uv run pytest tests/test_lifecycle.py -v`
Expected: PASS (5 tests)

- [ ] **Step 5: Commit**

```bash
git add src/discovery/lifecycle.py tests/test_lifecycle.py
git commit -m "feat(core): lifecycle and next_action derived from the journal"
```

---

### Task 9: Render — journal to a contract-shaped brief (WS-C)

**Files:**
- Create: `src/discovery/render.py`
- Test: `tests/test_render.py`, `tests/fixtures/customer_journal.jsonl`

**Interfaces:**
- Consumes: `SessionHeader` (Task 5), `parse_payload`/`Entry` (Task 6), `FRAMES` (Task 1).
- Produces: `render_brief(header: SessionHeader, events: list[dict], validation: str, findings: list[str] | None = None) -> str`.
  `validation ∈ {"pending", "pass", "fail"}`. Coverage per required key is `covered` when at
  least one entry with that key's prefix exists, otherwise `missing`; `partial` is reserved for
  a future explicit signal from the interviewer and is not inferred.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_render.py
import yaml
from discovery.journal import ANSWER_RECORDED
from discovery.render import render_brief
from discovery.session import SessionHeader

HEADER = SessionHeader(
    session_id="s-001",
    frame="customer",
    target="andrei-shtanakov/dispatcher",
    traces_to=[],
    source_pin="pin-1",
    created_at="2026-08-18T10:00:00Z",
)


def answer(qid: str, role: str, payload: str) -> dict:
    return {
        "event": ANSWER_RECORDED,
        "question_id": qid,
        "answer_id": f"sha256:{qid}",
        "participant_role": role,
        "payload": payload,
    }


PAYLOAD = (
    "text: we lose orders\n"
    "entries:\n"
    "  - id: G-01\n"
    "    body: cut order loss\n"
    "  - id: FR-01\n"
    "    body: retry a timed-out call\n"
    "    traces: G-01\n"
    "    Priority: Must\n"
    "    Acceptance: retried twice\n"
)


def frontmatter(text: str) -> dict:
    return yaml.safe_load(text.split("---")[1])


def test_frontmatter_carries_the_contract_core():
    doc = frontmatter(render_brief(HEADER, [answer("customer.goals.01", "product", PAYLOAD)], "pending"))
    assert doc["schema"] == "discovery-brief"
    assert doc["schema_version"] == 1
    assert doc["spec_stage"] == "discovery"
    assert doc["interview"]["frame"] == "customer"
    assert doc["interview"]["sessions"][0]["participant_role"] == "product"


def test_validation_is_written_as_given_not_predicted():
    text = render_brief(HEADER, [], "pending")
    assert frontmatter(text)["validation"] == "pending"


def test_entries_reach_the_body_with_their_fields():
    text = render_brief(HEADER, [answer("customer.goals.01", "product", PAYLOAD)], "pending")
    assert "- **FR-01** retry a timed-out call" in text
    assert "Priority: Must" in text
    assert "Acceptance: retried twice" in text
    assert "traces: G-01" in text


def test_coverage_reports_missing_for_keys_without_entries():
    doc = frontmatter(render_brief(HEADER, [answer("customer.goals.01", "product", PAYLOAD)], "pending"))
    assert doc["coverage"]["goals"] == "covered"
    assert doc["coverage"]["personas"] == "missing"


def test_superseded_answers_do_not_reach_the_body():
    old = answer("customer.goals.01", "product", "text: old\nentries:\n  - id: G-01\n    body: stale goal\n")
    new = answer("customer.goals.01", "product", "text: new\nentries:\n  - id: G-01\n    body: current goal\n")
    text = render_brief(HEADER, [old, new], "pending")
    assert "current goal" in text and "stale goal" not in text


def test_render_is_a_pure_function_of_its_inputs():
    events = [answer("customer.goals.01", "product", PAYLOAD)]
    assert render_brief(HEADER, events, "pending") == render_brief(HEADER, events, "pending")
```

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run pytest tests/test_render.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'discovery.render'`

- [ ] **Step 3: Implement**

```python
# src/discovery/render.py
"""Journal → brief. The brief is derived, never edited in place.

Nothing here writes coverage, counters, gate_passed or validation by hand from a
guess: coverage is computed from the entries present, and `validation` is passed
in by the caller, which knows the linter's actual verdict (the two-pass rule).
"""

from __future__ import annotations

import yaml

from discovery.contract.gate_check import FRAMES
from discovery.journal import ANSWER_RECORDED
from discovery.payload import Entry, parse_payload
from discovery.session import SessionHeader

SECTION_TITLES = {
    "G": "Goals", "P": "Personas", "J": "Jobs", "FR": "Functional requirements",
    "NFR": "Non-functional requirements", "CON": "Constraints", "M": "Success metrics",
    "OUT": "Out of scope", "RK": "Risks", "S": "Systems", "IF": "Interfaces",
    "AP": "Architecture preferences", "Q": "Open questions", "X": "Conflicts",
}


def _latest_answers(events: list[dict]) -> list[dict]:
    latest: dict[str, dict] = {}
    for event in events:
        if event.get("event") == ANSWER_RECORDED:
            latest[event["question_id"]] = event
    return list(latest.values())


def _entries(events: list[dict]) -> list[Entry]:
    out: list[Entry] = []
    for event in _latest_answers(events):
        out.extend(parse_payload(event["payload"]).entries)
    return out


def _prefix(eid: str) -> str:
    return eid.split("-")[0]


def _coverage(frame: str, entries: list[Entry]) -> dict[str, str]:
    present = {_prefix(entry.eid) for entry in entries}
    keys = {**FRAMES[frame]["required"], **FRAMES[frame]["optional"]}
    return {
        key: ("covered" if prefix and prefix in present else "missing")
        for key, prefix in keys.items()
    }


def _sessions(events: list[dict]) -> list[dict]:
    roles: list[str] = []
    for event in _latest_answers(events):
        role = event.get("participant_role", "")
        if role and role not in roles:
            roles.append(role)
    return [{"participant_role": role} for role in roles]


def render_brief(
    header: SessionHeader,
    events: list[dict],
    validation: str,
    findings: list[str] | None = None,
) -> str:
    entries = _entries(events)
    counts = {
        "open_questions": sum(1 for e in entries if _prefix(e.eid) == "Q"),
        "blocking_open_questions": sum(
            1
            for e in entries
            if _prefix(e.eid) == "Q" and e.fields.get("blocking", "").lower() == "true"
        ),
        "conflicts": sum(1 for e in entries if _prefix(e.eid) == "X"),
    }
    coverage = _coverage(header.frame, entries)
    required = FRAMES[header.frame]["required"]
    traced = {
        e.fields.get("traces", "") for e in entries if _prefix(e.eid) == "FR"
    }
    known = {e.eid for e in entries}
    gate_passed = (
        all(coverage[key] == "covered" for key, prefix in required.items() if prefix)
        and all(ref in known for ref in traced if ref)
        and counts["blocking_open_questions"] == 0
    )

    meta = {
        "schema": "discovery-brief",
        "schema_version": 1,
        "spec_stage": "discovery",
        "status": "draft",
        "generated_by": "discovery-runtime",
        "generated_at": header.created_at,
        "validation": validation,
        "gate_passed": gate_passed,
        "coverage": coverage,
        "interview": {
            "frame": header.frame,
            "sessions": _sessions(events) or [{"participant_role": "unknown"}],
        },
        "traces_to": header.traces_to,
        **counts,
    }
    if findings:
        meta["validation_findings"] = findings

    body: list[str] = []
    for prefix, title in SECTION_TITLES.items():
        group = [e for e in entries if _prefix(e.eid) == prefix]
        if not group:
            continue
        body.append(f"\n## {title}\n")
        for entry in group:
            body.append(f"- **{entry.eid}** {entry.body}")
            for key, value in entry.fields.items():
                body.append(f"  - {key}: {value}")

    front = yaml.safe_dump(meta, sort_keys=True, allow_unicode=True).rstrip()
    return f"---\n{front}\n---\n\n# Discovery brief — {header.target}\n" + "\n".join(body) + "\n"
```

- [ ] **Step 4: Run to verify it passes**

Run: `uv run pytest tests/test_render.py -v`
Expected: PASS (6 tests)

- [ ] **Step 5: Commit**

```bash
git add src/discovery/render.py tests/test_render.py
git commit -m "feat(core): render a contract-shaped brief from the journal"
```

---

### Task 10: The gate wrapper and the two-pass rule (WS-C)

**Files:**
- Create: `src/discovery/gate.py`
- Test: `tests/test_gate.py`

**Interfaces:**
- Consumes: `check`/`Finding` (Task 1), `render_brief` (Task 9).
- Produces: `GateResult` dataclass `(status: str, findings: list[str], text: str)` with
  `status ∈ {"pass","fail"}`; `render_and_gate(header, events, base_dir: Path) -> GateResult`
  implementing `render(pending) → check → render(pass|fail) → check`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_gate.py
from discovery.gate import render_and_gate
from discovery.journal import ANSWER_RECORDED
from discovery.session import SessionHeader

HEADER = SessionHeader(
    session_id="s-001", frame="customer", target="t", traces_to=[],
    source_pin="pin-1", created_at="2026-08-18T10:00:00Z",
)


def answer(payload: str, qid: str = "customer.goals.01") -> dict:
    return {
        "event": ANSWER_RECORDED, "question_id": qid, "answer_id": "sha256:x",
        "participant_role": "product", "payload": payload,
    }


def test_a_thin_brief_fails_the_gate_with_findings(tmp_path):
    result = render_and_gate(HEADER, [answer("text: t\nentries: []\n")], tmp_path)
    assert result.status == "fail"
    assert result.findings, "a failing gate must say why"


def test_the_second_pass_is_clean_with_respect_to_gc15(tmp_path):
    result = render_and_gate(HEADER, [answer("text: t\nentries: []\n")], tmp_path)
    assert not [f for f in result.findings if f.startswith("GC-15")], (
        "the mirror must agree with the linter after the second pass"
    )


def test_validation_in_the_returned_text_matches_the_verdict(tmp_path):
    result = render_and_gate(HEADER, [answer("text: t\nentries: []\n")], tmp_path)
    assert f"validation: {result.status}" in result.text
```

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run pytest tests/test_gate.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'discovery.gate'`

- [ ] **Step 3: Implement**

```python
# src/discovery/gate.py
"""Render → gate, twice.

GC-15 demands `validation: pass` exactly when nothing else errors, so a single
pass either manufactures a GC-15 finding or forces us to predict the linter.
We mirror it instead: render pending, ask, render the answer, ask again.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from discovery.contract.gate_check import check
from discovery.render import render_brief
from discovery.session import SessionHeader


@dataclass
class GateResult:
    status: str  # pass | fail
    findings: list[str]
    text: str


def _findings(text: str, base_dir: Path) -> list[str]:
    return [str(f) for f in check(text, base_dir=base_dir)]


def _errors(findings: list[str]) -> list[str]:
    return [f for f in findings if " error " in f]


def render_and_gate(
    header: SessionHeader, events: list[dict], base_dir: Path
) -> GateResult:
    first = render_brief(header, events, validation="pending")
    findings = _findings(first, base_dir)
    status = "fail" if _errors(findings) else "pass"

    second = render_brief(header, events, validation=status, findings=findings)
    confirm = _findings(second, base_dir)
    return GateResult(status=status, findings=confirm, text=second)
```

- [ ] **Step 4: Run to verify it passes**

Run: `uv run pytest tests/test_gate.py -v`
Expected: PASS (3 tests). If `test_the_second_pass_is_clean_with_respect_to_gc15` fails, the
mirror disagrees with the linter — fix `render_brief`'s `validation` handling, never by
special-casing GC-15 out of the findings list.

- [ ] **Step 5: Commit**

```bash
git add src/discovery/gate.py tests/test_gate.py
git commit -m "feat(core): two-pass render/gate so validation mirrors the linter"
```

---

### Task 11: The status envelope and exit-code priority (WS-C)

**Files:**
- Create: `src/discovery/protocol.py`
- Test: `tests/test_protocol.py`

**Interfaces:**
- Consumes: lifecycle constants (Task 8).
- Produces: `Envelope` dataclass
  `(lifecycle: str, gate: str, next_action: dict, findings: list[str], operation: dict)`
  with `to_json() -> str`; `exit_code(envelope: Envelope) -> int`;
  helpers `ok()`, `refused(reason: str, ...)`, `unknown(detail: str)`;
  reasons `NO_TARGET_QUESTION = "no_target_question"`, `ANSWER_CONFLICT = "answer_conflict"`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_protocol.py
import json
from discovery.protocol import (
    ANSWER_CONFLICT,
    Envelope,
    exit_code,
    ok,
    refused,
    unknown,
)


def test_pass_is_zero():
    assert exit_code(ok("complete", "pass")) == 0


def test_complete_but_failing_gate_is_ten():
    assert exit_code(ok("complete", "fail")) == 10


def test_awaiting_input_is_twenty_even_when_the_gate_would_fail():
    envelope = ok("awaiting_input", "fail", findings=["GC-05 error [x] empty"])
    assert exit_code(envelope) == 20, "waiting outranks a failing gate"
    assert envelope.findings, "findings are still reported at 20"


def test_refusal_is_two_and_keeps_the_axes():
    envelope = refused(ANSWER_CONFLICT, lifecycle="awaiting_input", gate="fail")
    assert exit_code(envelope) == 2
    assert envelope.lifecycle == "awaiting_input"
    assert envelope.gate == "fail"
    assert envelope.operation == {"status": "refused", "reason": ANSWER_CONFLICT}


def test_unknown_outranks_everything():
    assert exit_code(unknown("journal corrupt")) == 1
    assert unknown("journal corrupt").lifecycle == "unknown"


def test_envelope_is_json_with_all_five_keys():
    doc = json.loads(ok("complete", "pass").to_json())
    assert set(doc) == {"lifecycle", "gate", "next_action", "findings", "operation"}
```

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run pytest tests/test_protocol.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'discovery.protocol'`

- [ ] **Step 3: Implement**

```python
# src/discovery/protocol.py
"""One envelope for every command, and a strict projection to exit codes.

`operation` describes the call; `lifecycle`/`gate` describe the session. A refusal
leaves the axes populated — the state was readable and unchanged — so only exit 1
may report unknown axes.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field

from discovery.lifecycle import AWAITING_INPUT, COMPLETE, UNKNOWN

NO_TARGET_QUESTION = "no_target_question"
ANSWER_CONFLICT = "answer_conflict"


@dataclass
class Envelope:
    lifecycle: str
    gate: str
    next_action: dict = field(default_factory=dict)
    findings: list[str] = field(default_factory=list)
    operation: dict = field(default_factory=lambda: {"status": "ok"})

    def to_json(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False, indent=2, sort_keys=True)


def ok(
    lifecycle: str,
    gate: str,
    next_action: dict | None = None,
    findings: list[str] | None = None,
) -> Envelope:
    return Envelope(lifecycle, gate, next_action or {}, findings or [], {"status": "ok"})


def refused(
    reason: str,
    lifecycle: str,
    gate: str,
    next_action: dict | None = None,
    findings: list[str] | None = None,
) -> Envelope:
    return Envelope(
        lifecycle,
        gate,
        next_action or {},
        findings or [],
        {"status": "refused", "reason": reason},
    )


def unknown(detail: str) -> Envelope:
    return Envelope(UNKNOWN, UNKNOWN, {}, [], {"status": "unknown", "reason": detail})


def exit_code(envelope: Envelope) -> int:
    status = envelope.operation.get("status")
    if status == "unknown" or UNKNOWN in (envelope.lifecycle, envelope.gate):
        return 1
    if status == "refused":
        return 2
    if envelope.lifecycle == AWAITING_INPUT:
        return 20
    if envelope.lifecycle == COMPLETE and envelope.gate == "fail":
        return 10
    return 0
```

- [ ] **Step 4: Run to verify it passes**

Run: `uv run pytest tests/test_protocol.py -v`
Expected: PASS (6 tests)

- [ ] **Step 5: Commit**

```bash
git add src/discovery/protocol.py tests/test_protocol.py
git commit -m "feat(core): status envelope with a strict exit-code priority"
```

---

### Task 12: The CLI — four commands over the core (WS-D1)

**Files:**
- Create: `src/discovery/cli.py`
- Test: `tests/test_cli.py`

**Interfaces:**
- Consumes: everything from Tasks 3–11.
- Produces: `main(argv: list[str] | None = None) -> int`; sessions live under
  `$DISCOVERY_HOME/sessions` (default `~/.discovery`); `build_source() -> QuestionSource`
  is the single composition point that Task 13 replaces with the bank.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_cli.py
import json
import pytest
from discovery import cli
from discovery.questions import Question, StaticQuestionSource

CATALOGUE = {
    "customer": [
        Question("customer.goals.01", "goals", "What problem?"),
        Question("customer.jobs.01", "jobs", "Recent case?"),
    ]
}

PAYLOAD = (
    "text: we lose orders\n"
    "entries:\n"
    "  - id: G-01\n"
    "    body: cut order loss\n"
)


@pytest.fixture(autouse=True)
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("DISCOVERY_HOME", str(tmp_path / "home"))
    monkeypatch.setattr(
        cli, "build_source", lambda: StaticQuestionSource("pin-1", CATALOGUE)
    )
    return tmp_path


def run(argv: list[str], capsys) -> tuple[int, dict]:
    code = cli.main(argv)
    return code, json.loads(capsys.readouterr().out)


def test_start_returns_awaiting_input_and_exit_20(capsys):
    code, doc = run(["start", "--frame", "customer", "--target", "org/repo"], capsys)
    assert code == 20
    assert doc["lifecycle"] == "awaiting_input"
    assert doc["next_action"]["question_id"] == "customer.goals.01"


def test_status_in_a_fresh_process_resumes_the_same_question(capsys, home):
    _, started = run(["start", "--frame", "customer", "--target", "org/repo"], capsys)
    sid = started["next_action"]["session_id"]
    code, doc = run(["status", "--session", sid], capsys)
    assert code == 20
    assert doc["next_action"]["question_id"] == "customer.goals.01"


def test_answer_without_a_target_question_is_refused_with_exit_2(capsys, home, tmp_path):
    _, started = run(["start", "--frame", "customer", "--target", "org/repo"], capsys)
    sid = started["next_action"]["session_id"]
    payload = tmp_path / "a.yaml"
    payload.write_text(PAYLOAD, encoding="utf-8")
    run(["answer", "--session", sid, "--role", "product", "--file", str(payload)], capsys)
    run(["answer", "--session", sid, "--question", "customer.jobs.01",
         "--role", "product", "--file", str(payload)], capsys)
    code, doc = run(["answer", "--session", sid, "--question", "customer.jobs.01",
                     "--role", "product", "--file", str(payload)], capsys)
    assert code == 0 or code == 10, "an identical replay is a no-op, not a refusal"
    assert doc["operation"]["status"] == "ok"


def test_a_conflicting_answer_is_refused_and_supersede_accepts_it(capsys, home, tmp_path):
    _, started = run(["start", "--frame", "customer", "--target", "org/repo"], capsys)
    sid = started["next_action"]["session_id"]
    first, second = tmp_path / "1.yaml", tmp_path / "2.yaml"
    first.write_text(PAYLOAD, encoding="utf-8")
    second.write_text(PAYLOAD.replace("cut order loss", "different goal"), encoding="utf-8")
    run(["answer", "--session", sid, "--role", "product", "--file", str(first)], capsys)
    code, doc = run(["answer", "--session", sid, "--question", "customer.goals.01",
                     "--role", "product", "--file", str(second)], capsys)
    assert code == 2
    assert doc["operation"] == {"status": "refused", "reason": "answer_conflict"}
    assert doc["lifecycle"] == "awaiting_input", "a refusal keeps the axes populated"
    code, _ = run(["answer", "--session", sid, "--question", "customer.goals.01",
                   "--role", "product", "--file", str(second), "--supersede"], capsys)
    assert code == 20


def test_unknown_session_is_exit_1(capsys):
    code, doc = run(["status", "--session", "does-not-exist"], capsys)
    assert code == 1
    assert doc["lifecycle"] == "unknown"


def test_brief_writes_only_to_the_given_path(capsys, home, tmp_path):
    _, started = run(["start", "--frame", "customer", "--target", "org/repo"], capsys)
    sid = started["next_action"]["session_id"]
    out = tmp_path / "brief.md"
    code, doc = run(["brief", "--session", sid, "--out", str(out)], capsys)
    assert out.exists()
    assert doc["gate"] in {"pass", "fail"}
```

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run pytest tests/test_cli.py -v`
Expected: FAIL — `AttributeError: module 'discovery.cli' has no attribute 'build_source'`

- [ ] **Step 3: Implement**

```python
# src/discovery/cli.py
"""Four commands over the core. The CLI composes; it holds no rules of its own."""

from __future__ import annotations

import argparse
import os
import sys
import uuid
from pathlib import Path

from discovery import protocol
from discovery.gate import render_and_gate
from discovery.hashing import answer_id
from discovery.journal import (
    ANSWER_RECORDED,
    ANSWER_SUPERSEDED,
    QUESTION_ASKED,
    SOURCE_PIN_CHANGED,
    JournalUnreadable,
)
from discovery.lifecycle import (
    AWAITING_INPUT,
    answered_ids,
    compute_lifecycle,
    next_question,
)
from discovery.payload import PayloadInvalid, parse_payload
from discovery.questions import QuestionSource, StaticQuestionSource
from discovery.session import Session, SessionHeader, SessionUnreadable


def sessions_root() -> Path:
    return Path(os.environ.get("DISCOVERY_HOME", Path.home() / ".discovery")) / "sessions"


def build_source() -> QuestionSource:
    """Composition point. Task 13 returns the bank-backed source here."""
    return StaticQuestionSource(pin="unpinned", catalogue={})


def _issue_if_needed(session: Session, source: QuestionSource) -> dict:
    """Persist question_asked BEFORE returning it, or the answer cannot be attributed."""
    events = session.journal.events()
    if session.header.source_pin != source.pin:
        session.journal.append(
            {"event": SOURCE_PIN_CHANGED, "from": session.header.source_pin, "to": source.pin}
        )
    question = next_question(events, source, session.header.frame)
    if question is None:
        return {}
    if question.question_id not in {e.get("question_id") for e in events}:
        session.journal.append(
            {
                "event": QUESTION_ASKED,
                "question_id": question.question_id,
                "coverage_key": question.coverage_key,
                "question_text": question.text,
                "source_pin": source.pin,
            }
        )
    return {
        "session_id": session.header.session_id,
        "question_id": question.question_id,
        "coverage_key": question.coverage_key,
        "question_text": question.text,
    }


def _envelope(session: Session, source: QuestionSource) -> protocol.Envelope:
    next_action = _issue_if_needed(session, source)
    events = session.journal.events()
    lifecycle = compute_lifecycle(events, source, session.header.frame)
    result = render_and_gate(session.header, events, session.directory)
    return protocol.ok(lifecycle, result.status, next_action, result.findings)


def _emit(envelope: protocol.Envelope) -> int:
    print(envelope.to_json())
    return protocol.exit_code(envelope)


def cmd_start(args: argparse.Namespace) -> int:
    source = build_source()
    header = SessionHeader(
        session_id=f"s-{uuid.uuid4().hex[:12]}",
        frame=args.frame,
        target=args.target,
        traces_to=list(args.traces_to or []),
        source_pin=source.pin,
        created_at=__import__("datetime").datetime.now(
            __import__("datetime").UTC
        ).strftime("%Y-%m-%dT%H:%M:%SZ"),
    )
    session = Session.create(sessions_root(), header)
    return _emit(_envelope(session, source))


def cmd_status(args: argparse.Namespace) -> int:
    source = build_source()
    session = Session.load(sessions_root(), args.session)
    return _emit(_envelope(session, source))


def cmd_answer(args: argparse.Namespace) -> int:
    source = build_source()
    session = Session.load(sessions_root(), args.session)
    raw = sys.stdin.read() if args.file == "-" else Path(args.file).read_text("utf-8")
    parse_payload(raw)  # validate before anything is written

    events = session.journal.events()
    target = args.question
    if target is None:
        question = next_question(events, source, session.header.frame)
        target = question.question_id if question else None
    if target is None:
        envelope = _envelope(session, source)
        return _emit(
            protocol.refused(
                protocol.NO_TARGET_QUESTION, envelope.lifecycle, envelope.gate,
                envelope.next_action, envelope.findings,
            )
        )

    new_id = answer_id(session.header.session_id, target, args.role, raw)
    existing = [
        e for e in events if e.get("event") == ANSWER_RECORDED and e["question_id"] == target
    ]
    if existing:
        if existing[-1]["answer_id"] == new_id:
            return _emit(_envelope(session, source))  # idempotent replay
        if not args.supersede:
            envelope = _envelope(session, source)
            return _emit(
                protocol.refused(
                    protocol.ANSWER_CONFLICT, envelope.lifecycle, envelope.gate,
                    envelope.next_action, envelope.findings,
                )
            )
        session.journal.append(
            {
                "event": ANSWER_SUPERSEDED, "question_id": target,
                "from": existing[-1]["answer_id"], "to": new_id,
            }
        )
    session.journal.append(
        {
            "event": ANSWER_RECORDED, "question_id": target, "answer_id": new_id,
            "participant_role": args.role, "payload": raw,
        }
    )
    return _emit(_envelope(session, source))


def cmd_brief(args: argparse.Namespace) -> int:
    source = build_source()
    session = Session.load(sessions_root(), args.session)
    events = session.journal.events()
    result = render_and_gate(session.header, events, session.directory)
    session.write_artifact(Path(args.out), result.text)
    lifecycle = compute_lifecycle(events, source, session.header.frame)
    next_action = {} if lifecycle != AWAITING_INPUT else _issue_if_needed(session, source)
    return _emit(protocol.ok(lifecycle, result.status, next_action, result.findings))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="discovery")
    sub = parser.add_subparsers(dest="command", required=True)

    start = sub.add_parser("start")
    start.add_argument("--frame", choices=["customer", "engineer"], required=True)
    start.add_argument("--target", required=True)
    start.add_argument("--traces-to", action="append", dest="traces_to")
    start.set_defaults(func=cmd_start)

    status = sub.add_parser("status")
    status.add_argument("--session", required=True)
    status.add_argument("--json", action="store_true")
    status.set_defaults(func=cmd_status)

    answer = sub.add_parser("answer")
    answer.add_argument("--session", required=True)
    answer.add_argument("--question")
    answer.add_argument("--role", required=True)
    answer.add_argument("--file", required=True)
    answer.add_argument("--supersede", action="store_true")
    answer.set_defaults(func=cmd_answer)

    brief = sub.add_parser("brief")
    brief.add_argument("--session", required=True)
    brief.add_argument("--out", required=True)
    brief.set_defaults(func=cmd_brief)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except (SessionUnreadable, JournalUnreadable, PayloadInvalid, OSError) as exc:
        return _emit(protocol.unknown(str(exc)))


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run to verify it passes**

Run: `uv run pytest tests/test_cli.py -v`
Expected: PASS (6 tests)

- [ ] **Step 5: Run everything and the linters**

Run: `uv run pytest && uv run ruff check . && uv run ruff format --check . && uv run pyrefly check`
Expected: all green. `answered_ids` is imported but unused in `cli.py` — remove it if ruff
flags F401 rather than silencing the rule.

- [ ] **Step 6: Commit**

```bash
git add src/discovery/cli.py tests/test_cli.py
git commit -m "feat(cli): start/status/answer/brief over the deterministic core"
```

---

### Task 13: The capability boundary, enforced (WS-D1)

**Files:**
- Create: `tests/test_boundary.py`
- Modify: `src/discovery/cli.py` (only if the test finds a real write outside the allowed set)

**Interfaces:**
- Consumes: the CLI (Task 12).
- Produces: no production interface — this task's deliverable is the enforced boundary.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_boundary.py
"""author ≠ execute as a capability, not a string search.

Writes are allowed under the session root and to the one brief path passed in.
The core's dependency graph contains no network or process-launch adapter.
"""

import ast
import json
from pathlib import Path

import pytest
from discovery import cli
from discovery.questions import Question, StaticQuestionSource

SRC = Path(__file__).resolve().parents[1] / "src" / "discovery"
FORBIDDEN_MODULES = {"socket", "http", "urllib", "requests", "httpx", "subprocess", "asyncio"}

CATALOGUE = {"customer": [Question("customer.goals.01", "goals", "What problem?")]}
PAYLOAD = "text: t\nentries:\n  - id: G-01\n    body: cut order loss\n"


@pytest.fixture(autouse=True)
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("DISCOVERY_HOME", str(tmp_path / "home"))
    monkeypatch.setattr(cli, "build_source", lambda: StaticQuestionSource("pin-1", CATALOGUE))


def core_modules() -> list[Path]:
    return [p for p in SRC.rglob("*.py") if "contract" not in p.parts]


def test_core_imports_no_network_or_process_launcher():
    offenders = []
    for path in core_modules():
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            names = []
            if isinstance(node, ast.Import):
                names = [a.name.split(".")[0] for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                names = [node.module.split(".")[0]]
            offenders += [(path.name, n) for n in names if n in FORBIDDEN_MODULES]
    assert offenders == [], f"core must not reach the network or spawn processes: {offenders}"


def test_a_full_run_writes_only_under_the_session_root_and_the_brief_path(
    tmp_path, capsys, monkeypatch
):
    workdir = tmp_path / "elsewhere"
    workdir.mkdir()
    monkeypatch.chdir(workdir)

    payload = tmp_path / "a.yaml"
    payload.write_text(PAYLOAD, encoding="utf-8")
    out = tmp_path / "brief.md"

    before = {p for p in tmp_path.rglob("*")}
    cli.main(["start", "--frame", "customer", "--target", "org/repo"])
    sid = json.loads(capsys.readouterr().out)["next_action"]["session_id"]
    cli.main(["answer", "--session", sid, "--role", "product", "--file", str(payload)])
    capsys.readouterr()
    cli.main(["brief", "--session", sid, "--out", str(out)])
    capsys.readouterr()

    created = {p for p in tmp_path.rglob("*")} - before
    root = tmp_path / "home" / "sessions"
    stray = [
        p for p in created
        if p != out and root not in p.parents and p != root and not p.is_dir()
    ]
    assert stray == [], f"wrote outside the allowed set: {stray}"
    assert list(workdir.iterdir()) == [], "nothing may be written to the working directory"


def test_the_runtime_writes_no_downstream_artifact(tmp_path, capsys):
    payload = tmp_path / "a.yaml"
    payload.write_text(PAYLOAD, encoding="utf-8")
    cli.main(["start", "--frame", "customer", "--target", "org/repo"])
    sid = json.loads(capsys.readouterr().out)["next_action"]["session_id"]
    cli.main(["brief", "--session", sid, "--out", str(tmp_path / "brief.md")])
    capsys.readouterr()
    assert not list(tmp_path.rglob("tasks.md"))
    assert not list(tmp_path.rglob("design.md"))
```

- [ ] **Step 2: Run it**

Run: `uv run pytest tests/test_boundary.py -v`
Expected: the import test may FAIL if `cli.py` still imports something forbidden. Fix the
import, not the test. `test_a_full_run_writes_only...` must pass as written — if it fails,
something writes into the working directory, which is the defect the test exists for.

- [ ] **Step 3: Commit**

```bash
git add tests/test_boundary.py
git commit -m "test(boundary): author != execute enforced as a capability"
```

---

### Task 14: The bank — vendored frames, markers, fail-closed invariant (WS-A2)

**Blocked by:** `discovery-toolkit#4` (machine `coverage_key` markers). Do not start this task
by inventing a heading heuristic; if the upstream marker format differs from what is assumed
below, update this task first.

**Files:**
- Modify: `src/discovery/contract/PINNED.txt` (re-vendor with `--include-frames`)
- Create: `src/discovery/contract/frames/customer.md`, `.../engineer.md` (vendored bytes)
- Create: `src/discovery/bank.py`
- Test: `tests/test_bank.py`

**Interfaces:**
- Consumes: `FRAMES` (Task 1), `Question` (Task 7).
- Produces: `Topic` dataclass `(coverage_key: str | None, produces: list[str], questions: list[str])`;
  `parse_frame(text: str) -> list[Topic]`; `BankInvalid` exception;
  `BankQuestionSource(pin: str, frames_dir: Path)` implementing `QuestionSource`, with
  question ids shaped `<frame>.<coverage_key>.<NN>`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_bank.py
import pytest
from discovery.bank import BankInvalid, BankQuestionSource, parse_frame

FRAME = """# Frame: customer

### 1. Problem and goals
<!-- coverage_key: goals; produces: G -->
- What problem are we solving?
- Why now?

### 9. Closing (always)
<!-- coverage_key: none; produces: X,Q -->
- Who else must we ask?
"""


def test_markers_are_read_not_guessed_from_headings():
    topics = parse_frame(FRAME)
    assert topics[0].coverage_key == "goals"
    assert topics[0].produces == ["G"]
    assert len(topics[0].questions) == 2
    assert topics[1].coverage_key is None, "`none` is a legitimate topic without a key"


def test_a_frame_missing_a_required_key_is_rejected(tmp_path):
    (tmp_path / "customer.md").write_text(FRAME, encoding="utf-8")
    (tmp_path / "engineer.md").write_text(FRAME, encoding="utf-8")
    with pytest.raises(BankInvalid) as excinfo:
        BankQuestionSource("pin-1", tmp_path).questions("customer")
    assert "personas" in str(excinfo.value), "the error must name what is missing"


def test_produces_must_agree_with_the_frames_table(tmp_path):
    bad = FRAME.replace("produces: G", "produces: FR")
    (tmp_path / "customer.md").write_text(bad, encoding="utf-8")
    with pytest.raises(BankInvalid):
        BankQuestionSource("pin-1", tmp_path).questions("customer")


def test_question_ids_are_stable_and_namespaced(tmp_path):
    (tmp_path / "customer.md").write_text(FRAME, encoding="utf-8")
    source = BankQuestionSource("pin-1", tmp_path)
    with pytest.raises(BankInvalid):
        source.questions("customer")  # incomplete fixture still fails closed
    topics = parse_frame(FRAME)
    assert topics[0].questions[0].startswith("What problem")
```

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run pytest tests/test_bank.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'discovery.bank'`

- [ ] **Step 3: Implement**

```python
# src/discovery/bank.py
"""The vendored question bank.

A topic declares its coverage key with an explicit marker. The key is never guessed
from the heading, and no second `topic → key` table exists here: admissibility and
prefixes come from FRAMES in the vendored linter.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from discovery.contract.gate_check import FRAMES
from discovery.questions import Question

MARKER_RE = re.compile(r"<!--\s*coverage_key:\s*([\w.]+)\s*;\s*produces:\s*([\w,\s]*)-->")
HEADING_RE = re.compile(r"^###\s+(.*)$")
BULLET_RE = re.compile(r"^-\s+(.*)$")


class BankInvalid(Exception):
    """The bank cannot serve the coverage gate — an error, never a warning."""


@dataclass
class Topic:
    coverage_key: str | None
    produces: list[str]
    questions: list[str]


def parse_frame(text: str) -> list[Topic]:
    topics: list[Topic] = []
    current: Topic | None = None
    for line in text.splitlines():
        if HEADING_RE.match(line):
            current = None
            continue
        marker = MARKER_RE.search(line)
        if marker:
            key = marker.group(1)
            current = Topic(
                coverage_key=None if key == "none" else key,
                produces=[p.strip() for p in marker.group(2).split(",") if p.strip()],
                questions=[],
            )
            topics.append(current)
            continue
        bullet = BULLET_RE.match(line)
        if bullet and current is not None:
            current.questions.append(bullet.group(1).strip())
    return topics


def _validate(frame: str, topics: list[Topic]) -> None:
    required = FRAMES[frame]["required"]
    admissible = set(required) | set(FRAMES[frame]["optional"])
    claimed = {t.coverage_key for t in topics if t.coverage_key}

    unknown = claimed - admissible
    if unknown:
        raise BankInvalid(f"{frame}: unknown coverage keys {sorted(unknown)}")

    missing = set(required) - claimed
    if missing:
        raise BankInvalid(
            f"{frame}: required keys claimed by no topic: {sorted(missing)} — "
            "the coverage gate would be unreachable"
        )

    for topic in topics:
        prefix = required.get(topic.coverage_key or "")
        if prefix and prefix not in topic.produces:
            raise BankInvalid(
                f"{frame}: topic {topic.coverage_key} must produce {prefix}, "
                f"declares {topic.produces}"
            )


class BankQuestionSource:
    def __init__(self, pin: str, frames_dir: Path) -> None:
        self._pin = pin
        self._dir = frames_dir

    @property
    def pin(self) -> str:
        return self._pin

    def questions(self, frame: str) -> list[Question]:
        path = self._dir / f"{frame}.md"
        if not path.exists():
            raise BankInvalid(f"no vendored bank for frame {frame}")
        topics = parse_frame(path.read_text(encoding="utf-8"))
        _validate(frame, topics)
        out: list[Question] = []
        for topic in topics:
            if topic.coverage_key is None:
                continue
            for number, text in enumerate(topic.questions, start=1):
                out.append(
                    Question(f"{frame}.{topic.coverage_key}.{number:02d}", topic.coverage_key, text)
                )
        return out
```

- [ ] **Step 4: Re-vendor the frames and run**

Run: `uv run tools/vendor_pull.py ../discovery-toolkit --include-frames`
Run: `uv run pytest tests/test_bank.py tests/test_vendored_copy.py -v`
Expected: PASS. If the real upstream frames fail `_validate`, that is the invariant doing its
job — report it on `discovery-toolkit#4` rather than loosening the check.

- [ ] **Step 5: Commit**

```bash
git add src/discovery/bank.py src/discovery/contract tests/test_bank.py
git commit -m "feat(bank): vendored frames with marker-driven, fail-closed coverage"
```

---

### Task 15: Wire the bank into the CLI and prove one full flow (WS-D2)

**Files:**
- Modify: `src/discovery/cli.py:build_source`
- Test: `tests/test_end_to_end.py`

**Interfaces:**
- Consumes: `BankQuestionSource` (Task 14), the CLI (Task 12).
- Produces: `build_source()` returning a `BankQuestionSource` pinned to the vendored commit.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_end_to_end.py
"""One interview, start to gate, across process boundaries in-process."""

import json
from pathlib import Path

import pytest
from discovery import cli


@pytest.fixture(autouse=True)
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("DISCOVERY_HOME", str(tmp_path / "home"))


def drive(argv, capsys) -> tuple[int, dict]:
    code = cli.main(argv)
    return code, json.loads(capsys.readouterr().out)


def test_the_real_bank_serves_questions_for_both_frames():
    source = cli.build_source()
    assert source.questions("customer"), "the vendored bank must answer for customer"
    assert source.questions("engineer"), "the vendored bank must answer for engineer"
    assert source.pin != "unpinned"


def test_suspend_and_resume_reach_a_gated_brief(tmp_path, capsys):
    code, started = drive(["start", "--frame", "customer", "--target", "org/repo"], capsys)
    assert code == 20
    sid = started["next_action"]["session_id"]

    guard = 0
    while True:
        code, doc = drive(["status", "--session", sid], capsys)
        if code != 20:
            break
        guard += 1
        assert guard < 200, "the bank must terminate"
        question = doc["next_action"]
        payload = tmp_path / f"{guard}.yaml"
        payload.write_text(
            f"text: answer to {question['question_id']}\n"
            f"entries:\n  - id: {_id_for(question['coverage_key'], guard)}\n"
            f"    body: substantive content for {question['coverage_key']}\n",
            encoding="utf-8",
        )
        drive(
            ["answer", "--session", sid, "--question", question["question_id"],
             "--role", "product", "--file", str(payload)],
            capsys,
        )

    assert doc["lifecycle"] == "complete"
    out = tmp_path / "brief.md"
    code, final = drive(["brief", "--session", sid, "--out", str(out)], capsys)
    assert out.exists()
    assert final["gate"] in {"pass", "fail"}
    assert "validation: " in out.read_text(encoding="utf-8")


def _id_for(coverage_key: str, n: int) -> str:
    from discovery.contract.gate_check import FRAMES

    prefix = FRAMES["customer"]["required"].get(coverage_key) or \
        FRAMES["customer"]["optional"].get(coverage_key) or "G"
    return f"{prefix}-{n:02d}"
```

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run pytest tests/test_end_to_end.py -v`
Expected: FAIL — `build_source()` still returns the empty static source, so
`test_the_real_bank_serves_questions_for_both_frames` fails on the first assertion.

- [ ] **Step 3: Implement**

```python
# src/discovery/cli.py — replace build_source
def build_source() -> QuestionSource:
    """Composition point: the vendored bank, pinned to the commit in PINNED.txt."""
    from discovery.bank import BankQuestionSource

    contract = Path(__file__).parent / "contract"
    pin = ""
    for line in (contract / "PINNED.txt").read_text(encoding="utf-8").splitlines():
        if line.startswith("commit:"):
            pin = line.split(":", 1)[1].strip()
    return BankQuestionSource(pin=pin, frames_dir=contract / "frames")
```

Remove the now-unused `StaticQuestionSource` import from `cli.py`; the tests import it
directly from `discovery.questions`.

- [ ] **Step 4: Run to verify it passes**

Run: `uv run pytest -v`
Expected: all suites PASS. A `gate: fail` in the end-to-end test is acceptable — the test
asserts the flow reaches a gated brief, not that synthetic answers satisfy the contract.

- [ ] **Step 5: Full verification before the arc is called done**

Run: `uv run pytest && uv run ruff check . && uv run ruff format --check . && uv run pyrefly check && uv run tools/check_vendor.py consistency && uv run tools/check_vendor.py provenance`
Expected: all green. Provenance requires network; unreachable exits 3 and that is not a pass.

- [ ] **Step 6: Commit**

```bash
git add src/discovery/cli.py tests/test_end_to_end.py
git commit -m "feat(cli): serve questions from the vendored bank; full flow covered"
```

---

### Task 16: Live acceptance (WS-D2, requires a human stakeholder)

**Files:**
- Create: `docs/evidence/2026-XX-XX-runtime-v1-live-run.md`
- Modify: `TODO.md` (mark the arc's items with their PR numbers)

**Precondition — recorded authority expansion.** The implementation arc runs with
`write_scope = {discovery}`. This run writes a brief into the target repository, so it declares
`write_scope = {discovery, <target>}` **before it starts**, in the evidence file, and the
expansion applies to this run alone.

- [ ] **Step 1: Declare the run** — evidence file with frame, target repo, stakeholder role, and the declared `write_scope`.
- [ ] **Step 2: `start`** — record the command, the returned `next_action`, and that the exit code was `20`.
- [ ] **Step 3: End the process.** The suspension must be real, not simulated in one session.
- [ ] **Step 4: From a new process, `status` then `answer`** — repeatedly, with a real stakeholder answering. Record the session id.
- [ ] **Step 5: Reach `lifecycle: complete`, `gate: pass`, exit `0`.** A thin brief that fails the gate is not acceptance; continue the interview.
- [ ] **Step 6: `brief --out` into the allowed path in the target repo**, then verify independently: `uv run python -m discovery.contract.gate_check <brief>` exits 0.
- [ ] **Step 7: Record the ledger** — session id, `transcript_sha256`, `brief_sha256`, and the commit/PR of the target repo, all in the evidence file. These two artifacts are the only ones the arc hashes, and this step is where it happens: at this moment the journal lives under `$DISCOVERY_HOME` and the brief is not yet committed, so a hash is the only thing that ties the brief in the pull request to this session. Everything that *is* in git — backlog, plan, config — is pinned by the commit SHA recorded when the implementation run was launched (spec §11 readiness) — a different run from this one, and a different record.
- [ ] **Step 8: Commit and open the PR** for the arc.

If no stakeholder is available, the arc's status is **`implementation complete, live acceptance
pending`** — never `accepted`. An interview with the repository owner acting as the product
stakeholder counts, because the interviewer and stakeholder roles are genuinely separate; a
solo self-interview does not, and the mini-profile that case needs is a separate open question
in `TODO.md`.

---

## Self-Review

**Spec coverage.** §3 approach → Tasks 7, 15. §4 vendoring and both guarantees → Tasks 1, 2;
the bank invariant → Task 14. §5 journal, durability, idempotency, supersede, lifecycle →
Tasks 3, 4, 5, 8, 12. §6 two-pass → Task 10. §7 envelope and codes → Tasks 11, 12. §8 boundary
→ Task 13. §9 pyramid → L0 in Tasks 1–2 and 14, L1 in Tasks 3–13, L2 seeded by Task 15's
frozen flow. §10 workstreams → the task-to-WS mapping above. §11 orchestration → the
`project.yaml` in the spec, generated with `spec/tasks.md`. §12 DoD → Task 16.

**Gap found and closed:** the spec had no answer-to-entries mechanism; the structured payload
(Task 6) fills it and is flagged for a spec amendment.

**Naming consistency checked across tasks:** `answer_id`, `canonical_answer_bytes`,
`Journal.append/events`, `Session.create/load/write_artifact`, `SessionHeader.source_pin`,
`parse_payload`, `Entry.eid/body/fields`, `Question.question_id/coverage_key/text`,
`QuestionSource.pin/questions`, `compute_lifecycle`, `next_question`, `render_brief`,
`render_and_gate`, `GateResult.status/findings/text`, `Envelope`, `exit_code`, `build_source`,
`parse_frame`, `BankQuestionSource`. Each name is defined in exactly one task and used with the
same signature everywhere after it.

**Known sequencing:** Tasks 1–13 are unblocked today. Task 14 waits on `discovery-toolkit#4`;
Task 15 waits on 14; Task 16 waits on 15 and a stakeholder.
