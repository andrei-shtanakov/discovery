# L3 interview quality benchmark — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: use `superpowers:subagent-driven-development`
> (recommended) or `superpowers:executing-plans` to implement this plan task-by-task.
> Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** measure what the discovery stage actually elicits — coverage-recall, invention,
feasibility coverage, contradiction recall, interview length and cost — so the decision on
`@id:phase-3-grounding` rests on numbers instead of on a promise.

**Architecture:** two execution boundaries that never mix. **Part A** lives in this
repository: a deterministic static audit of the vendored question bank, its baseline
snapshot, and one observability item. **Part B** lives in `../discovery-test`, a local git
repository without a remote: the simulator, the reference caller, judge, matcher, harness,
scenarios, hidden specs and run logs. Nothing in Part B is imported by the runtime, and no
runtime path resolves into it.

**Tech Stack:** Python ≥3.12, `uv`, pytest, ruff (line length 88), pyrefly. Part B adds
`tomllib` (stdlib) and drives Claude Code headlessly (`claude -p`). No network calls in Part
A — its tests run in CI.

**Spec:** `docs/superpowers/specs/2026-08-21-l3-quality-benchmark-design.md` — read it first.
Every "why" below is short on purpose; the spec carries the argument.

## Global Constraints

- **Package management:** `uv` only (`uv add`, `uv run`). Never `pip`, never `uv pip install`.
- **Style:** ruff, line length 88; type hints on everything; docstrings on public APIs.
- **Part A ships through a PR.** Direct commits to `master` are forbidden; branch,
  `gh pr create`, read the Copilot review, and let the owner merge.
- **Part B never pushes.** `discovery-test` has no remote by decision (spec §2). Commits are
  local. Do not `git remote add`, do not register it in the fleet manifest.
- **Neighbour repositories are read-only.** `discovery-toolkit` is copied from by pin, never
  edited and never resolved as a runtime path.
- **Part A adds nothing to `src/discovery/**`.** The audit is dev tooling and lives in
  `tools/`, like `check_vendor.py`; `tests/test_boundary.py` must keep passing untouched.
- **The vendored linter stays normative.** Where a metric restates a linter rule, the harness
  projects the linter's own id set into a ratio and never re-implements the rule.
- **Model selection is recorded twice:** the CLI argument and the `model` identifier reported
  in `stream-json`. It is called a model selection, never a pin.
- **No pass/fail threshold on any loop metric in v1.** The only regression threshold is Part
  A's baseline snapshot.

---

# Part A — the discovery repository

Deliverable: `tools/bank_audit.py`, its tests, a committed baseline snapshot that fails CI
when the bank's wording changes, and one observability item in `TODO.md`.

### Task A1: bank audit — classification of issued questions

**Files:**
- Create: `tools/bank_audit.py`
- Test: `tests/test_bank_audit.py`

**Interfaces:**
- Consumes: `discovery.bank.BankQuestionSource.questions(frame) -> list[Question]` and
  `discovery.bank.parse_frame(text) -> list[Topic]`, both existing.
- Produces: `classify(text: str) -> list[str]`; `CATEGORIES: tuple[str, ...]`;
  `audit_frame(frame: str, frames_dir: Path) -> FrameAudit` where
  `FrameAudit(frame: str, questions: list[QuestionAudit], claimed: dict[str, list[str]],
  unissued_topics: list[str])` and `QuestionAudit(question_id: str, coverage_key: str,
  categories: list[str])`. Task A2 consumes `audit_frame` and `CATEGORIES`.

Four categories, deliberately conservative. `advisory` is reported but is **not** part of the
leading rate: it marks a bullet the runtime issues to a stakeholder although it is not a
question at all (the bank carries a few interviewer directives, e.g. "Прогони перед
стейкхолдером краткое резюме…"). A slash-enumeration such as
"быстро/надёжно/безопасно" is **not** a signal: the bank uses it for domain lists, and
flagging it would train the reader to ignore the metric.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_bank_audit.py
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

import bank_audit  # noqa: E402

FRAMES = Path(__file__).resolve().parents[1] / "src" / "discovery" / "contract" / "frames"


class TestClassify:
    def test_tag_question_is_leading(self):
        assert "tag_question" in bank_audit.classify("Это ведь важно, не так ли?")

    def test_answer_menu_is_leading(self):
        text = "Что недопустимо (потеря данных, запись куда-то, простой)?"
        assert "answer_menu" in bank_audit.classify(text)

    def test_instruction_parenthetical_is_not_an_answer_menu(self):
        text = "Что продукт должен уметь? (иди от jobs, не от «списка хотелок»)"
        assert bank_audit.classify(text) == []

    def test_slash_enumeration_is_not_a_signal(self):
        text = "Насколько быстро/надёжно/безопасно это должно работать — в числах?"
        assert bank_audit.classify(text) == []

    def test_presupposition_is_leading(self):
        assert "presupposition" in bank_audit.classify("Почему вы не сделали это раньше?")

    def test_non_question_is_advisory(self):
        text = "Прогони перед стейкхолдером краткое резюме целей."
        assert bank_audit.classify(text) == ["advisory"]

    def test_plain_question_is_clean(self):
        assert bank_audit.classify("Какую проблему решаем?") == []


class TestAuditFrame:
    @pytest.mark.parametrize("frame,issued", [("customer", 19), ("engineer", 15)])
    def test_audits_exactly_the_issued_questions(self, frame, issued):
        audit = bank_audit.audit_frame(frame, FRAMES)
        assert len(audit.questions) == issued

    def test_reports_topics_that_are_never_issued(self):
        audit = bank_audit.audit_frame("engineer", FRAMES)
        assert audit.unissued_topics, (
            "engineer carries at least one coverage_key: none topic, "
            "whose bullets are never issued to a stakeholder"
        )

    def test_claimed_covers_every_required_key(self):
        from discovery.contract import gate_check

        audit = bank_audit.audit_frame("customer", FRAMES)
        required = set(gate_check.FRAMES["customer"]["required"])
        assert required <= set(audit.claimed)
```

- [ ] **Step 2: Run it to make sure it fails**

Run: `uv run pytest tests/test_bank_audit.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'bank_audit'`.

- [ ] **Step 3: Implement the minimal module**

```python
# tools/bank_audit.py
"""Static audit of the vendored question bank (L3 spec §5).

Two products, both deterministic and both offline: a classification of every
question the runtime can issue, and a coverage report of which required keys
are claimed by which topics. No model runs here — a CI test may not reach the
network, and the number must be reproducible.

The classification is deliberately conservative. It is a tripwire on change,
not a verdict on wording: `tests/test_bank_audit.py` compares it against a
committed snapshot, so a re-pin that alters a question fails cheaply here
instead of surfacing inside an expensive benchmark run.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from discovery.bank import BankQuestionSource, parse_frame  # noqa: E402

CATEGORIES = ("tag_question", "answer_menu", "presupposition", "advisory")

#: Leading by grammar: the question carries its own confirmation.
_TAG_RE = re.compile(
    r"(не так ли|правда ли|верно\?|согласны\?|правильно ли я понимаю|вы же)",
    re.IGNORECASE,
)

#: Leading by presupposition: the question asserts the fact it asks about.
_PRESUPPOSITION_RE = re.compile(
    r"(почему вы не |что мешает вам |когда вы наконец |почему до сих пор )",
    re.IGNORECASE,
)

#: A parenthetical listing candidate answers seeds the answer. A parenthetical
#: addressed to the interviewer does not — those open with an imperative, and
#: the list is pinned rather than inferred.
_PAREN_RE = re.compile(r"\(([^)]+)\)")
_INSTRUCTION_VERBS = (
    "иди",
    "проведи",
    "прогони",
    "спроси",
    "зафиксируй",
    "запиши",
    "сверься",
    "не записывай",
)


def classify(text: str) -> list[str]:
    """Return the categories `text` falls into, in `CATEGORIES` order."""
    found: list[str] = []
    if _TAG_RE.search(text):
        found.append("tag_question")
    if _is_answer_menu(text):
        found.append("answer_menu")
    if _PRESUPPOSITION_RE.search(text):
        found.append("presupposition")
    if "?" not in text:
        found.append("advisory")
    return found


def _is_answer_menu(text: str) -> bool:
    """A parenthetical enumerating ≥2 candidate answers, instructions aside."""
    for inner in _PAREN_RE.findall(text):
        stripped = inner.strip().lower()
        if stripped.startswith(_INSTRUCTION_VERBS):
            continue
        if inner.count(",") >= 1:
            return True
    return False


@dataclass(frozen=True)
class QuestionAudit:
    """One issued question and the categories it falls into."""

    question_id: str
    coverage_key: str
    categories: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class FrameAudit:
    """One frame: its issued questions, claimed keys, and unissued topics."""

    frame: str
    questions: list[QuestionAudit]
    claimed: dict[str, list[str]]
    unissued_topics: list[str]


def audit_frame(frame: str, frames_dir: Path) -> FrameAudit:
    """Classify `frame`'s issued questions and report its coverage claims."""
    source = BankQuestionSource(pin="audit", frames_dir=frames_dir)
    questions = [
        QuestionAudit(q.question_id, q.coverage_key, classify(q.text))
        for q in source.questions(frame)
    ]
    topics = parse_frame((frames_dir / f"{frame}.md").read_text(encoding="utf-8"))
    claimed = {
        topic.coverage_key: list(topic.produces)
        for topic in topics
        if topic.coverage_key is not None
    }
    unissued = [
        f"{len(topic.questions)} bullet(s) under a coverage_key: none topic"
        for topic in topics
        if topic.coverage_key is None and topic.questions
    ]
    return FrameAudit(frame, questions, claimed, unissued)
```

- [ ] **Step 4: Run the tests and make sure they pass**

Run: `uv run pytest tests/test_bank_audit.py -q && uv run ruff check tools/bank_audit.py tests/test_bank_audit.py && uv run ruff format --check tools/bank_audit.py tests/test_bank_audit.py && uv run pyrefly check`
Expected: all green. If `test_audits_exactly_the_issued_questions` reports different counts,
**do not edit the expectation to match** — the bank pin moved, and that is a finding: stop and
report it.

- [ ] **Step 5: Commit**

```bash
git add tools/bank_audit.py tests/test_bank_audit.py
git commit -m "feat(audit): классификация выдаваемых вопросов банка"
```

---

### Task A2: baseline snapshot and the CI tripwire

**Files:**
- Modify: `tools/bank_audit.py`
- Create: `tests/data/bank_audit_baseline.json`
- Modify: `tests/test_bank_audit.py`

**Interfaces:**
- Consumes: `audit_frame`, `CATEGORIES` from Task A1.
- Produces: `snapshot(frames_dir: Path) -> dict` and the CLI entry
  `python tools/bank_audit.py report|--emit-baseline`.

The snapshot pins the exact classification per question id, not a threshold. A threshold
invites argument about the number; an exact set makes any change to the bank's wording
visible in a diff, which is the property worth having.

- [ ] **Step 1: Write the failing test**

```python
# append to tests/test_bank_audit.py
BASELINE = Path(__file__).resolve().parent / "data" / "bank_audit_baseline.json"


class TestBaseline:
    def test_snapshot_matches_the_committed_baseline(self):
        import json

        current = bank_audit.snapshot(FRAMES)
        recorded = json.loads(BASELINE.read_text(encoding="utf-8"))
        assert current == recorded, (
            "the bank's wording or composition changed. If the change is "
            "deliberate, refresh with `uv run python tools/bank_audit.py "
            "--emit-baseline` and explain the diff in the pull request; the "
            "leading-question categories are the thing under review."
        )

    def test_snapshot_records_the_contract_pin(self):
        current = bank_audit.snapshot(FRAMES)
        assert current["pin"], "a snapshot without its pin cannot be attributed"
```

- [ ] **Step 2: Run it to make sure it fails**

Run: `uv run pytest tests/test_bank_audit.py::TestBaseline -q`
Expected: FAIL — `AttributeError: module 'bank_audit' has no attribute 'snapshot'`.

- [ ] **Step 3: Implement `snapshot` and the CLI**

```python
# append to tools/bank_audit.py
PINNED = Path(__file__).resolve().parents[1] / "src" / "discovery" / "contract" / "PINNED.txt"


def snapshot(frames_dir: Path) -> dict:
    """JSON-able classification of both frames, plus the contract pin."""
    return {
        "pin": PINNED.read_text(encoding="utf-8").strip(),
        "frames": {
            frame: {
                "issued": len(audit.questions),
                "questions": {
                    q.question_id: q.categories
                    for q in audit.questions
                    if q.categories
                },
                "claimed": audit.claimed,
                "unissued_topics": audit.unissued_topics,
            }
            for frame in ("customer", "engineer")
            if (audit := audit_frame(frame, frames_dir))
        },
    }


def _report(frames_dir: Path) -> None:
    """Print the human-readable audit: coverage claims, then flagged questions."""
    for frame in ("customer", "engineer"):
        audit = audit_frame(frame, frames_dir)
        flagged = [q for q in audit.questions if q.categories]
        leading = [q for q in flagged if q.categories != ["advisory"]]
        print(f"\n=== {frame}: {len(audit.questions)} issued question(s)")
        print(f"    claimed keys: {', '.join(sorted(audit.claimed))}")
        for note in audit.unissued_topics:
            print(f"    never issued: {note}")
        print(f"    leading: {len(leading)}   advisory-only: {len(flagged) - len(leading)}")
        for q in flagged:
            print(f"      {q.question_id}  [{', '.join(q.categories)}]")


def main() -> int:
    """Report the audit, or refresh the committed baseline snapshot."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--frames", type=Path, default=PINNED.parent / "frames")
    parser.add_argument("--emit-baseline", action="store_true")
    args = parser.parse_args()
    if args.emit_baseline:
        target = Path(__file__).resolve().parents[1] / "tests" / "data" / "bank_audit_baseline.json"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            json.dumps(snapshot(args.frames), ensure_ascii=False, indent=2, sort_keys=True)
            + "\n",
            encoding="utf-8",
        )
        print(f"wrote {target}")
        return 0
    _report(args.frames)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Generate the baseline and read it before committing**

Run: `uv run python tools/bank_audit.py --emit-baseline && uv run python tools/bank_audit.py report`
Expected: the snapshot lands in `tests/data/bank_audit_baseline.json`. **Read the report
output.** The flagged questions are the first finding of this whole plan — if a question is
flagged that a human would not call leading, or an obviously leading one is missed, fix the
rule now, while it is cheap. Record what you saw in the commit message.

- [ ] **Step 5: Run the tests and make sure they pass**

Run: `uv run pytest -q && uv run ruff check . && uv run ruff format --check . && uv run pyrefly check`
Expected: all green, 246 pre-existing tests included.

- [ ] **Step 6: Commit**

```bash
git add tools/bank_audit.py tests/test_bank_audit.py tests/data/bank_audit_baseline.json
git commit -m "feat(audit): baseline-снимок классификации банка как регрессионный порог"
```

- [ ] **Step 7: Open the pull request**

```bash
git push -u origin feat/bank-audit
gh pr create --title "feat(audit): статический аудит вендоренного банка" --body "…"
gh api -X POST repos/andrei-shtanakov/discovery/pulls/<n>/requested_reviewers \
  -f 'reviewers[]=copilot-pull-request-reviewer[bot]'
gh pr view <n> --json reviews -q '[.reviews[]?|.author.login+":"+.state]|join(",")'
```

The PR body states the flagged counts per frame and what the reviewer should look at: the
rules, not the number. Wait for the Copilot review, address it, and leave the merge to the
owner.

---

### Task A3: the observability item

**Files:**
- Modify: `TODO.md`

**Depends on:** Task B1 — the freshness command must name a stand that exists.

**Interfaces:**
- Consumes: `discovery-test/runs/<ULID>/run-manifest.json` (Task B2) and
  `discovery-test/tools/freshness.py` (Task B2).

- [ ] **Step 1: Add the item under "Наполнение runtime"**

```markdown
- [ ] Стенд L3 свеж относительно текущей конфигурации @owner:github:andrei-shtanakov @trigger:"изменился любой эффективный вход манифеста: пин банка/контракта, промпты (caller, simulator, judge, matcher, annotator), config.toml, пин методики, сценарий, ground truth, ревизия харнесса, версия Claude Code, model selection" @id:l3-stand-freshness
      Стенд `../discovery-test` — локальный репо без remote и без CI, поэтому
      протухает молча: ни дайджест Robin, ни plan-check его не видят.
      Проверка: `uv run python ../discovery-test/tools/freshness.py` — сверяет
      эффективные входы последнего `run-manifest.json` с текущими (файловое по
      хешу, внешнее по значению) и печатает список расхождений.
      Несовпадение означает «для текущей конфигурации прогона нет» — дата не
      доказывает ничего. Спека: `docs/superpowers/specs/2026-08-21-l3-quality-benchmark-design.md` §9.
```

- [ ] **Step 2: Verify the command actually runs**

Run: `uv run python ../discovery-test/tools/freshness.py; echo "exit=$?"`
Expected: it prints either "no run exists for the current configuration" with the diverged
inputs, or the ULID of the run that matches. An `ImportError` or a missing path means the item
is describing something that does not exist — fix the path, not the prose.

- [ ] **Step 3: Commit and open the PR**

```bash
git add TODO.md
git commit -m "chore(todo): наблюдаемая точка свежести стенда L3"
```

---

# Part B — the `discovery-test` stand

Local git repository, no remote, not in the fleet manifest. Every task here commits locally;
none pushes.

### Task B1: bootstrap the stand

**Files:**
- Create: `../discovery-test/.gitignore`, `pyproject.toml`, `README.md`, `config.toml`,
  `PINNED.txt`, `l3bench/__init__.py`, `tests/conftest.py`, `tests/fake_claude/claude`

**Interfaces:**
- Produces: the package `l3bench`, the fixture `fake_claude` (a `claude` stand-in on `PATH`),
  and `config.toml` — the pinned run parameters every later task reads.

- [ ] **Step 1: Create the repository and its layout**

```bash
mkdir -p ~/labs/all_ai_orchestrators/discovery-test
cd ~/labs/all_ai_orchestrators/discovery-test
git init
mkdir -p l3bench/metrics prompts scenarios tools tests/fake_claude runs
```

Verify no remote is configured and none is added: `git remote -v` must print nothing, here
and after every later task.

- [ ] **Step 2: Write `config.toml` — every run parameter, pinned**

```toml
# L3 benchmark run parameters. Every value here is an effective input of a run:
# config.toml is hashed into run-manifest.json, so changing a number invalidates
# the freshness of previous runs rather than silently redefining them.

repetitions = 5              # runs per scenario; results are distributions

[leakage]
leak_shingle_tokens = 12     # a shared 12-token shingle with the hidden spec is a leak
structural_forms = [         # structural disclosure, matched case-insensitively
  "list of requirements",
  "список требований",
  "hidden spec",
  "скрытая спека",
]
max_id_mentions = 2          # ≥3 ground-truth ids in one utterance is a structural dump

[models]
simulator = "sonnet"
caller = "sonnet"
judge = "sonnet"
matcher = "sonnet"
annotator = "sonnet"

[limits]
max_turns = 40               # a loop that will not end is a harness_error, not a result
```

- [ ] **Step 3: Write `PINNED.txt` — the methodology pin**

```
# The interviewer methodology the reference caller is built from. Copied by
# pin, never resolved as a path at run time.
discovery-toolkit .claude/skills/discovery-interview/SKILL.md <sha>
```

Obtain `<sha>` with `git -C ../discovery-toolkit rev-parse HEAD` and record the file's own
digest next to it: `shasum -a 256 ../discovery-toolkit/.claude/skills/discovery-interview/SKILL.md`.

- [ ] **Step 4: Write the fake `claude` used by every test**

```bash
# tests/fake_claude/claude
#!/usr/bin/env python3
"""A `claude -p` stand-in: emits canned stream-json, never reaches the network.

The reply comes from L3BENCH_FAKE_REPLY (a file path) so a test can script a
turn; the reported model comes from --model, so the manifest's "argument vs
reported identifier" distinction stays testable.
"""
import json, os, sys

argv = sys.argv[1:]
model = argv[argv.index("--model") + 1] if "--model" in argv else "unknown"
reply = os.environ.get("L3BENCH_FAKE_REPLY", "")
if reply and os.path.exists(reply):
    with open(reply, encoding="utf-8") as fh:
        reply = fh.read()
for event in (
    {"type": "system", "subtype": "init", "model": f"{model}-20260101"},
    {"type": "assistant", "message": {"model": f"{model}-20260101",
                                      "content": [{"type": "text", "text": reply}]}},
    {"type": "result", "subtype": "success", "usage": {"input_tokens": 11,
                                                       "output_tokens": 7}},
):
    print(json.dumps(event, ensure_ascii=False))
```

```python
# tests/conftest.py
from __future__ import annotations

import os
from pathlib import Path

import pytest

FAKE = Path(__file__).resolve().parent / "fake_claude"


@pytest.fixture
def fake_claude(monkeypatch, tmp_path):
    """Put the canned `claude` first on PATH and return a reply-setter."""
    FAKE.joinpath("claude").chmod(0o755)
    monkeypatch.setenv("PATH", f"{FAKE}:{os.environ['PATH']}")

    def set_reply(text: str) -> None:
        target = tmp_path / "reply.txt"
        target.write_text(text, encoding="utf-8")
        monkeypatch.setenv("L3BENCH_FAKE_REPLY", str(target))

    return set_reply
```

- [ ] **Step 5: Write `pyproject.toml` and install**

```toml
[project]
name = "l3bench"
version = "0.1.0"
description = "L3 interview-quality benchmark stand for discovery (local, no remote)"
requires-python = ">=3.12"
dependencies = ["pyyaml>=6.0", "discovery"]

[tool.uv.sources]
discovery = { path = "../discovery", editable = false }

[tool.ruff]
line-length = 88

[tool.pytest.ini_options]
testpaths = ["tests"]

[dependency-groups]
dev = ["pytest>=9.1.1", "ruff>=0.16.3"]
```

`discovery` is a dependency because the harness reads the **vendored linter** through it
(Task B8) — the normative rule must not be re-implemented. The reference caller still talks to
the CLI only.

Run: `uv sync && uv run pytest -q`
Expected: no tests collected yet, exit 5 — that is fine, the environment resolves.

- [ ] **Step 6: Commit locally**

```bash
git add -A && git commit -m "chore: bootstrap L3 stand (local, no remote)"
git remote -v   # must print nothing
```

---

### Task B2: the run manifest and the freshness check

**Files:**
- Create: `../discovery-test/l3bench/hashes.py`, `l3bench/manifest.py`, `tools/freshness.py`
- Test: `../discovery-test/tests/test_manifest.py`

**Interfaces:**
- Consumes: `config.toml` from Task B1.
- Produces: `sha256_file(path) -> str`; `RunManifest` with fields
  `run_id, files: dict[str, str], values: dict[str, str], counters: dict[str, int],
  transcripts: dict[str, str], state: str`; `RunManifest.write(run_dir) -> Path`;
  `load(run_dir) -> RunManifest`; `diverged(manifest, current) -> list[str]`. Tasks B5–B10
  consume all of these.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_manifest.py
from __future__ import annotations

import json
from pathlib import Path

from l3bench import manifest


def test_files_are_hashed_and_values_are_recorded_verbatim(tmp_path):
    prompt = tmp_path / "simulator.md"
    prompt.write_text("hidden", encoding="utf-8")
    m = manifest.RunManifest(
        run_id="01TEST",
        files={"prompts/simulator.md": manifest.sha256_file(prompt)},
        values={"claude_version": "2.1.237 (Claude Code)",
                "model.simulator.argument": "sonnet",
                "model.simulator.reported": "sonnet-20260101"},
        counters={"input_tokens": 11},
        transcripts={"simulator": "roles/simulator/stream.jsonl"},
        state="ok",
    )
    written = m.write(tmp_path)
    payload = json.loads(written.read_text(encoding="utf-8"))
    assert payload["files"]["prompts/simulator.md"].startswith("sha256:")
    assert payload["values"]["claude_version"] == "2.1.237 (Claude Code)"
    assert payload["state"] == "ok"


def test_diverged_names_every_changed_input(tmp_path):
    recorded = manifest.RunManifest(
        run_id="01TEST",
        files={"config.toml": "sha256:aaa"},
        values={"claude_version": "2.1.237 (Claude Code)"},
        counters={}, transcripts={}, state="ok",
    )
    current_files = {"config.toml": "sha256:bbb"}
    current_values = {"claude_version": "2.2.0 (Claude Code)"}
    assert manifest.diverged(recorded, current_files, current_values) == [
        "config.toml", "claude_version",
    ]


def test_a_matching_configuration_diverges_in_nothing(tmp_path):
    recorded = manifest.RunManifest(
        run_id="01TEST", files={"config.toml": "sha256:aaa"},
        values={"claude_version": "2.1.237 (Claude Code)"},
        counters={}, transcripts={}, state="ok",
    )
    assert manifest.diverged(recorded, {"config.toml": "sha256:aaa"},
                             {"claude_version": "2.1.237 (Claude Code)"}) == []
```

- [ ] **Step 2: Run it to make sure it fails**

Run: `uv run pytest tests/test_manifest.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'l3bench.manifest'`.

- [ ] **Step 3: Implement**

```python
# l3bench/hashes.py
"""Digests for the files the stand owns. Values that are not files are never
hashed — a CLI version and a model identifier are recorded verbatim (spec §8)."""

from __future__ import annotations

import hashlib
from pathlib import Path


def sha256_file(path: Path) -> str:
    """Return `sha256:<hex>` for one file's bytes."""
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    return f"sha256:{digest}"
```

```python
# l3bench/manifest.py
"""`run-manifest.json`: every effective input of a run, in the form it has.

Files are hashed, external facts are recorded as values. Freshness compares the
two dictionaries and names what diverged; a date proves nothing (spec §9).
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

from l3bench.hashes import sha256_file

__all__ = ["RunManifest", "sha256_file", "load", "diverged"]


@dataclass(frozen=True)
class RunManifest:
    """One run's inputs, counters, transcripts and terminal state."""

    run_id: str
    files: dict[str, str]
    values: dict[str, str]
    counters: dict[str, int]
    transcripts: dict[str, str]
    state: str

    def write(self, run_dir: Path) -> Path:
        """Write `run-manifest.json` into `run_dir` and return its path."""
        run_dir.mkdir(parents=True, exist_ok=True)
        target = run_dir / "run-manifest.json"
        target.write_text(
            json.dumps(asdict(self), ensure_ascii=False, indent=2, sort_keys=True)
            + "\n",
            encoding="utf-8",
        )
        return target


def load(run_dir: Path) -> RunManifest:
    """Read a manifest previously written by `RunManifest.write`."""
    payload = json.loads((run_dir / "run-manifest.json").read_text(encoding="utf-8"))
    return RunManifest(**payload)


def diverged(
    recorded: RunManifest, files: dict[str, str], values: dict[str, str]
) -> list[str]:
    """Names of inputs whose current state differs from the recorded run."""
    changed = [k for k, v in recorded.files.items() if files.get(k) != v]
    changed += [k for k, v in recorded.values.items() if values.get(k) != v]
    changed += [k for k in files if k not in recorded.files]
    changed += [k for k in values if k not in recorded.values]
    return changed
```

- [ ] **Step 4: Run the tests and make sure they pass**

Run: `uv run pytest tests/test_manifest.py -q && uv run ruff check . && uv run ruff format --check .`
Expected: 3 passed, lint clean.

- [ ] **Step 5: Write `tools/freshness.py`, the command Task A3 names**

```python
# tools/freshness.py
"""Is there a run for the current configuration? Compares every effective input
of the newest manifest against the stand's current state (spec §9).

Exit: 0 a matching run exists · 1 none does (diverged inputs are printed).
"""

from __future__ import annotations

import subprocess
import sys
import tomllib
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from l3bench import manifest  # noqa: E402

STAND = Path(__file__).resolve().parents[1]
HASHED = (
    "config.toml",
    "PINNED.txt",
    "prompts/simulator.md",
    "prompts/caller.md",
    "prompts/judge.md",
    "prompts/matcher.md",
    "prompts/annotator.md",
)


def current_state() -> tuple[dict[str, str], dict[str, str]]:
    """Hashes of the stand's own files, plus the external values it depends on."""
    files = {
        rel: manifest.sha256_file(STAND / rel)
        for rel in HASHED
        if (STAND / rel).exists()
    }
    for scenario in sorted((STAND / "scenarios").glob("*/ground-truth.yaml")):
        files[str(scenario.relative_to(STAND))] = manifest.sha256_file(scenario)
    config = tomllib.loads((STAND / "config.toml").read_text(encoding="utf-8"))
    values = {
        "claude_version": subprocess.run(
            ["claude", "--version"], capture_output=True, text=True, check=True
        ).stdout.strip(),
        "harness_revision": subprocess.run(
            ["git", "-C", str(STAND), "rev-parse", "HEAD"],
            capture_output=True, text=True, check=True,
        ).stdout.strip(),
        "discovery_revision": subprocess.run(
            ["git", "-C", str(STAND.parent / "discovery"), "rev-parse", "HEAD"],
            capture_output=True, text=True, check=True,
        ).stdout.strip(),
    }
    for role, model in config["models"].items():
        values[f"model.{role}.argument"] = model
    return files, values


def main() -> int:
    """Print the newest matching run, or the inputs that diverged."""
    runs = sorted((STAND / "runs").glob("*/run-manifest.json"))
    if not runs:
        print("no run exists for the current configuration: the stand has no runs")
        return 1
    files, values = current_state()
    newest = manifest.load(runs[-1].parent)
    changes = manifest.diverged(newest, files, values)
    if changes:
        print("no run exists for the current configuration; diverged inputs:")
        for name in changes:
            print(f"  - {name}")
        return 1
    print(f"current configuration was run: {newest.run_id} ({newest.state})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 6: Commit locally**

```bash
git add -A && git commit -m "feat(manifest): эффективные входы прогона и проверка свежести"
```

---

### Task B3: role runner and filesystem isolation

**Files:**
- Create: `../discovery-test/l3bench/roles.py`
- Test: `../discovery-test/tests/test_roles.py`

**Interfaces:**
- Consumes: `config.toml`, the `fake_claude` fixture.
- Produces: `RoleSpec(name: str, model: str, prompt: Path, allowed_tools: list[str],
  workdir: Path | None)` and `run_role(spec, user_text, run_dir) -> RoleResult`, where
  `RoleResult(text: str, reported_model: str, usage: dict[str, int], transcript: Path)`.
  Tasks B4–B10 consume `run_role`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_roles.py
from __future__ import annotations

from pathlib import Path

from l3bench import roles


def _spec(tmp_path: Path, **kw) -> roles.RoleSpec:
    prompt = tmp_path / "p.md"
    prompt.write_text("you are a role", encoding="utf-8")
    return roles.RoleSpec(
        name=kw.get("name", "simulator"),
        model=kw.get("model", "sonnet"),
        prompt=prompt,
        allowed_tools=kw.get("allowed_tools", []),
        workdir=kw.get("workdir"),
    )


def test_reports_both_the_argument_and_the_identifier(tmp_path, fake_claude):
    fake_claude("сроки горят")
    result = roles.run_role(_spec(tmp_path), "какая проблема?", tmp_path)
    assert result.text == "сроки горят"
    assert result.reported_model == "sonnet-20260101"


def test_a_toolless_role_disallows_every_tool(tmp_path, fake_claude, monkeypatch):
    seen: list[list[str]] = []
    monkeypatch.setattr(roles, "_invoke", lambda argv, text, cwd: seen.append(argv) or "")
    roles.run_role(_spec(tmp_path), "вопрос", tmp_path)
    assert "--disallowedTools" in seen[0]
    assert "--allowedTools" not in seen[0]


def test_a_tooled_role_gets_only_its_own_directory(tmp_path, fake_claude, monkeypatch):
    seen: list[list[str]] = []
    monkeypatch.setattr(roles, "_invoke", lambda argv, text, cwd: seen.append(argv) or "")
    workdir = tmp_path / "roles" / "caller"
    workdir.mkdir(parents=True)
    roles.run_role(
        _spec(tmp_path, name="caller", allowed_tools=["Bash(discovery:*)"],
              workdir=workdir),
        "ответь", tmp_path,
    )
    argv = seen[0]
    assert argv[argv.index("--add-dir") + 1] == str(workdir)
    assert "Bash(discovery:*)" in argv


def test_the_transcript_is_kept_in_full(tmp_path, fake_claude):
    fake_claude("ответ")
    result = roles.run_role(_spec(tmp_path), "вопрос", tmp_path)
    assert result.transcript.exists()
    assert "stream" in result.transcript.name or result.transcript.suffix == ".jsonl"
```

- [ ] **Step 2: Run it to make sure it fails**

Run: `uv run pytest tests/test_roles.py -q`
Expected: FAIL — no module `l3bench.roles`.

- [ ] **Step 3: Implement**

```python
# l3bench/roles.py
"""One process per role, each blind to the others (spec §4).

Isolation is filesystem-level: a tooled role receives `cwd` and `--add-dir`
limited to its own directory, and the hidden spec lives only in the simulator's
system prompt, inside the simulator's process. The harness relays; the roles
never touch.
"""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

EVERY_TOOL = "Bash,Read,Write,Edit,Glob,Grep,WebFetch,WebSearch,Task,NotebookEdit"


@dataclass(frozen=True)
class RoleSpec:
    """How one role is launched: its model, prompt, tools and workdir."""

    name: str
    model: str
    prompt: Path
    allowed_tools: list[str] = field(default_factory=list)
    workdir: Path | None = None


@dataclass(frozen=True)
class RoleResult:
    """What one invocation produced, plus what it reported about itself."""

    text: str
    reported_model: str
    usage: dict[str, int]
    transcript: Path


def _invoke(argv: list[str], user_text: str, cwd: Path | None) -> str:
    """Run `claude` and return its raw stream-json stdout."""
    completed = subprocess.run(
        argv,
        input=user_text,
        capture_output=True,
        text=True,
        cwd=str(cwd) if cwd else None,
        check=True,
    )
    return completed.stdout


def run_role(spec: RoleSpec, user_text: str, run_dir: Path) -> RoleResult:
    """Invoke one role once and append its full transcript to the run."""
    argv = [
        "claude", "-p",
        "--model", spec.model,
        "--output-format", "stream-json",
        "--system-prompt", spec.prompt.read_text(encoding="utf-8"),
    ]
    if spec.allowed_tools:
        argv += ["--allowedTools", *spec.allowed_tools]
        if spec.workdir is not None:
            argv += ["--add-dir", str(spec.workdir)]
    else:
        argv += ["--disallowedTools", EVERY_TOOL]

    raw = _invoke(argv, user_text, spec.workdir)
    transcript = run_dir / "roles" / spec.name / "stream.jsonl"
    transcript.parent.mkdir(parents=True, exist_ok=True)
    with transcript.open("a", encoding="utf-8") as fh:
        fh.write(raw)

    text, reported, usage = "", "unknown", {}
    for line in raw.splitlines():
        if not line.strip():
            continue
        event = json.loads(line)
        if event.get("type") == "assistant":
            message = event.get("message", {})
            reported = message.get("model", reported)
            for block in message.get("content", []):
                if block.get("type") == "text":
                    text += block["text"]
        elif event.get("type") == "result":
            usage = event.get("usage", {})
    return RoleResult(text.strip(), reported, usage, transcript)
```

- [ ] **Step 4: Run the tests and make sure they pass**

Run: `uv run pytest tests/test_roles.py -q && uv run ruff check . && uv run ruff format --check .`
Expected: 4 passed.

- [ ] **Step 5: Commit locally**

```bash
git add -A && git commit -m "feat(roles): изолированный запуск ролей и полный транскрипт"
```

---

### Task B4: leakage check

**Files:**
- Create: `../discovery-test/l3bench/leakage.py`
- Test: `../discovery-test/tests/test_leakage.py`

**Interfaces:**
- Consumes: `config.toml [leakage]`, ground-truth ids (Task B6).
- Produces: `LeakVerdict(leaked: bool, kind: str, evidence: str)` and
  `check(utterance: str, hidden_spec: str, gt_ids: list[str], cfg: dict) -> LeakVerdict`.
  Task B5 consumes `check`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_leakage.py
from __future__ import annotations

from l3bench import leakage

CFG = {"leak_shingle_tokens": 5, "structural_forms": ["скрытая спека"],
       "max_id_mentions": 2}
SPEC = "система обязана повторять таймаутный вызов курьера в течение тридцати секунд"


def test_a_verbatim_quotation_is_a_leak():
    verdict = leakage.check(
        "система обязана повторять таймаутный вызов курьера в течение тридцати секунд",
        SPEC, [], CFG,
    )
    assert verdict.leaked and verdict.kind == "shingle"


def test_paraphrase_below_the_shingle_is_not_a_leak():
    verdict = leakage.check("ну, звонки иногда срываются и это бесит", SPEC, [], CFG)
    assert not verdict.leaked


def test_dumping_ids_is_structural_disclosure():
    verdict = leakage.check("вот всё: FR-01, FR-02, FR-03", SPEC,
                            ["FR-01", "FR-02", "FR-03"], CFG)
    assert verdict.leaked and verdict.kind == "id_dump"


def test_naming_the_hidden_spec_is_structural_disclosure():
    verdict = leakage.check("у меня тут скрытая спека, зачитываю", SPEC, [], CFG)
    assert verdict.leaked and verdict.kind == "structural"


def test_evidence_is_carried_so_a_human_can_judge():
    verdict = leakage.check(SPEC, SPEC, [], CFG)
    assert verdict.evidence
```

- [ ] **Step 2: Run it to make sure it fails**

Run: `uv run pytest tests/test_leakage.py -q`
Expected: FAIL — no module `l3bench.leakage`.

- [ ] **Step 3: Implement**

```python
# l3bench/leakage.py
"""Absence of tools is not absence of leakage (spec §4).

A simulator with no tools can still quote its hidden spec. This check is
deterministic and its parameters live in `config.toml`, so a change to them is
a configuration change with its own hash in the run manifest.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

_WORD_RE = re.compile(r"\w+", re.UNICODE)


@dataclass(frozen=True)
class LeakVerdict:
    """Whether an utterance leaked, by which rule, and on what evidence."""

    leaked: bool
    kind: str
    evidence: str


def _shingles(text: str, size: int) -> set[tuple[str, ...]]:
    tokens = [t.lower() for t in _WORD_RE.findall(text)]
    return {tuple(tokens[i : i + size]) for i in range(0, max(0, len(tokens) - size + 1))}


def check(
    utterance: str, hidden_spec: str, gt_ids: list[str], cfg: dict
) -> LeakVerdict:
    """Classify one simulator utterance against its own hidden spec."""
    size = cfg["leak_shingle_tokens"]
    shared = _shingles(utterance, size) & _shingles(hidden_spec, size)
    if shared:
        return LeakVerdict(True, "shingle", " ".join(sorted(shared)[0]))

    lowered = utterance.lower()
    for form in cfg["structural_forms"]:
        if form.lower() in lowered:
            return LeakVerdict(True, "structural", form)

    mentioned = [i for i in gt_ids if i in utterance]
    if len(mentioned) > cfg["max_id_mentions"]:
        return LeakVerdict(True, "id_dump", ", ".join(mentioned))

    return LeakVerdict(False, "", "")
```

- [ ] **Step 4: Run the tests and make sure they pass**

Run: `uv run pytest tests/test_leakage.py -q`
Expected: 5 passed.

- [ ] **Step 5: Commit locally**

```bash
git add -A && git commit -m "feat(leakage): детерминированная проверка утечки скрытой спеки"
```

---

### Task B5: the loop driver

**Files:**
- Create: `../discovery-test/l3bench/loop.py`, `prompts/simulator.md`, `prompts/caller.md`
- Test: `../discovery-test/tests/test_loop.py`

**Interfaces:**
- Consumes: `run_role` (B3), `check` (B4), `RunManifest` (B2).
- Produces: `LoopResult(state: str, turns: list[Turn], session: str, brief: Path | None,
  exit_code: int)` with `Turn(index: int, question: str, answer: str, leak: LeakVerdict)`,
  and `run_loop(scenario, run_dir, cfg) -> LoopResult`. Tasks B7–B10 consume `LoopResult`.

Each turn re-invokes both roles from scratch. That is not a limitation to work around: the
runtime's own contract is that an interview survives process boundaries, so a stateless caller
that re-reads `discovery status` every turn exercises the property the runtime advertises.

- [ ] **Step 1: Write `prompts/caller.md`**

```markdown
You drive the `discovery` CLI. You never invent stakeholder facts.

Each invocation you receive one instruction:

- `STATUS` — run `discovery status --session <id>`. Branch on the exit code, never on
  `&&`: `20` means a question is pending — print it between `<QUESTION>` and `</QUESTION>`
  and nothing else. `0`, `10`, `11` mean the interview is over — print `<DONE code=NN>`.
  `2` is a refused precondition and `1` means an axis was undecidable — print
  `<ERROR code=NN>` with the envelope's `operation.reason`.
- `ANSWER <path>` — the stakeholder's reply is in that file. Turn it into an answer payload:
  free-text `text`, plus typed `entries` for every goal, job, function, constraint or
  disagreement the reply actually states. `traces` is always a YAML list. Write the payload to
  a file in your own directory and submit it with
  `discovery answer --session <id> --role stakeholder --file <payload>`. If the runtime
  refuses with exit 2 because the answer conflicts with a previous one, re-submit with
  `--supersede`. Print `<SUBMITTED>` when the runtime accepts.

Rules: read only your own directory; never paste the stakeholder's text into a shell
command — it goes through the file you write; never edit a brief by hand.
```

The methodology half of this prompt (what counts as a `G`, a `J`, an `FR`, when to raise an
`X-NN`) is copied from the pinned `SKILL.md` recorded in `PINNED.txt`. Copy the relevant
sections in, do not resolve the neighbour's path at run time.

- [ ] **Step 2: Write `prompts/simulator.md`**

```markdown
You are a stakeholder being interviewed. Your product knowledge is in the SPEC below.

Answer as a person speaks: concretely, from experience, one topic at a time. You may complain,
digress briefly, and be imprecise about numbers you would not know by heart.

You must never: quote the SPEC verbatim, enumerate its requirements, mention that a
specification exists, or use its identifiers. If asked something the SPEC does not cover, say
what a person would say — that you do not know, or give a plausible answer consistent with
what you have already said, and stay consistent for the rest of the interview.

SPEC:
{hidden_spec}
```

- [ ] **Step 3: Write the failing test**

```python
# tests/test_loop.py
from __future__ import annotations

from pathlib import Path

from l3bench import loop


def test_a_pending_question_reaches_the_simulator(tmp_path, monkeypatch):
    calls: list[tuple[str, str]] = []

    def fake_run(spec, user_text, run_dir):
        calls.append((spec.name, user_text))
        if spec.name == "caller" and user_text.startswith("STATUS"):
            return loop.RoleResult("<QUESTION>Какую проблему решаем?</QUESTION>",
                                   "m", {}, tmp_path / "t.jsonl")
        if spec.name == "simulator":
            return loop.RoleResult("курьеры срываются", "m", {}, tmp_path / "t.jsonl")
        return loop.RoleResult("<SUBMITTED>", "m", {}, tmp_path / "t.jsonl")

    monkeypatch.setattr(loop, "run_role", fake_run)
    result = loop.run_loop(_scenario(tmp_path), tmp_path, _cfg(max_turns=1))
    assert ("simulator", "Какую проблему решаем?") in calls
    assert result.turns[0].answer == "курьеры срываются"


def test_a_leaking_utterance_invalidates_the_run(tmp_path, monkeypatch):
    def fake_run(spec, user_text, run_dir):
        if spec.name == "caller" and user_text.startswith("STATUS"):
            return loop.RoleResult("<QUESTION>вопрос</QUESTION>", "m", {}, tmp_path / "t")
        if spec.name == "simulator":
            return loop.RoleResult(_scenario(tmp_path).hidden_spec, "m", {}, tmp_path / "t")
        return loop.RoleResult("<SUBMITTED>", "m", {}, tmp_path / "t")

    monkeypatch.setattr(loop, "run_role", fake_run)
    result = loop.run_loop(_scenario(tmp_path), tmp_path, _cfg())
    assert result.state == "invalid_leak"


def test_a_loop_that_will_not_end_is_a_harness_error(tmp_path, monkeypatch):
    def fake_run(spec, user_text, run_dir):
        if spec.name == "caller" and user_text.startswith("STATUS"):
            return loop.RoleResult("<QUESTION>ещё вопрос</QUESTION>", "m", {}, tmp_path / "t")
        if spec.name == "simulator":
            return loop.RoleResult("ответ", "m", {}, tmp_path / "t")
        return loop.RoleResult("<SUBMITTED>", "m", {}, tmp_path / "t")

    monkeypatch.setattr(loop, "run_role", fake_run)
    result = loop.run_loop(_scenario(tmp_path), tmp_path, _cfg(max_turns=3))
    assert result.state == "harness_error"


def test_a_finished_interview_ends_ok(tmp_path, monkeypatch):
    def fake_run(spec, user_text, run_dir):
        if spec.name == "caller":
            return loop.RoleResult("<DONE code=0>", "m", {}, tmp_path / "t")
        return loop.RoleResult("ответ", "m", {}, tmp_path / "t")

    monkeypatch.setattr(loop, "run_role", fake_run)
    result = loop.run_loop(_scenario(tmp_path), tmp_path, _cfg())
    assert result.state == "ok" and result.exit_code == 0
```

Write `_scenario(tmp_path)` and `_cfg(**kw)` as module-level helpers in the same test file:
`_scenario` returns `loop.Scenario(name="S-test", frame="customer", hidden_spec="секретная
формулировка про повтор вызова", gt_ids=[])`, and `_cfg(**kw)` returns the `config.toml` mapping plus the
two keys the harness injects at run time — `prompts` (a `{role: path}` map pointing at
`prompts/*.md`) and `limits.max_turns`, overridable per test.

- [ ] **Step 4: Run it to make sure it fails**

Run: `uv run pytest tests/test_loop.py -q`
Expected: FAIL — no module `l3bench.loop`.

- [ ] **Step 5: Implement**

```python
# l3bench/loop.py
"""Simulator ↔ reference caller, relayed by the harness (spec §4).

The two never touch: the harness carries one utterance at a time, writes the
stakeholder's reply to a file inside the caller's own directory, and asks the
caller to submit it. Both roles are re-invoked per turn — the runtime's own
promise is that an interview survives process boundaries, so a caller that
re-reads `discovery status` every turn exercises exactly that.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from l3bench.leakage import LeakVerdict, check
from l3bench.roles import RoleResult, RoleSpec, run_role

QUESTION_RE = re.compile(r"<QUESTION>(.*?)</QUESTION>", re.DOTALL)
DONE_RE = re.compile(r"<DONE code=(\d+)>")
ERROR_RE = re.compile(r"<ERROR code=(\d+)>")


@dataclass(frozen=True)
class Scenario:
    """One benchmark case: its frame, its hidden spec, its ground-truth ids."""

    name: str
    frame: str
    hidden_spec: str
    gt_ids: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class Turn:
    """One question relayed to the stakeholder and the reply it produced."""

    index: int
    question: str
    answer: str
    leak: LeakVerdict


@dataclass(frozen=True)
class LoopResult:
    """How the interview ended, and everything said on the way."""

    state: str
    turns: list[Turn]
    session: str
    brief: Path | None
    exit_code: int


def run_loop(scenario: Scenario, run_dir: Path, cfg: dict) -> LoopResult:
    """Drive one interview to its end, or to the first reason it cannot finish."""
    caller_dir = run_dir / "roles" / "caller"
    caller_dir.mkdir(parents=True, exist_ok=True)
    caller = RoleSpec(
        name="caller",
        model=cfg["models"]["caller"],
        prompt=Path(cfg["prompts"]["caller"]),
        allowed_tools=["Bash(discovery:*)"],
        workdir=caller_dir,
    )
    simulator = RoleSpec(
        name="simulator",
        model=cfg["models"]["simulator"],
        prompt=Path(cfg["prompts"]["simulator"]),
    )

    turns: list[Turn] = []
    for index in range(1, cfg["limits"]["max_turns"] + 1):
        status = run_role(caller, f"STATUS session={scenario.name}", run_dir)
        if (done := DONE_RE.search(status.text)) is not None:
            return LoopResult("ok", turns, scenario.name,
                              _brief_path(caller_dir), int(done.group(1)))
        if (error := ERROR_RE.search(status.text)) is not None:
            return LoopResult("harness_error", turns, scenario.name, None,
                              int(error.group(1)))
        question_match = QUESTION_RE.search(status.text)
        if question_match is None:
            return LoopResult("harness_error", turns, scenario.name, None, 1)

        question = question_match.group(1).strip()
        reply = run_role(simulator, question, run_dir)
        verdict = check(reply.text, scenario.hidden_spec, scenario.gt_ids, cfg["leakage"])
        turns.append(Turn(index, question, reply.text, verdict))
        if verdict.leaked:
            return LoopResult("invalid_leak", turns, scenario.name, None, 1)

        inbox = caller_dir / "inbox" / f"turn-{index:02d}.txt"
        inbox.parent.mkdir(parents=True, exist_ok=True)
        inbox.write_text(reply.text, encoding="utf-8")
        run_role(caller, f"ANSWER {inbox}", run_dir)

    return LoopResult("harness_error", turns, scenario.name, None, 1)


def _brief_path(caller_dir: Path) -> Path | None:
    """The brief the caller wrote, if it wrote one."""
    briefs = sorted(caller_dir.glob("**/*brief*.md"))
    return briefs[-1] if briefs else None
```

- [ ] **Step 6: Run the tests and make sure they pass**

Run: `uv run pytest tests/test_loop.py -q && uv run ruff check . && uv run ruff format --check .`
Expected: 4 passed.

- [ ] **Step 7: Commit locally**

```bash
git add -A && git commit -m "feat(loop): петля симулятор↔caller через посредника"
```

---

### Task B6: scenario S1 and its annotation

**Files:**
- Create: `../discovery-test/scenarios/S1-customer/source/`,
  `scenarios/S1-customer/annotation/llm-draft.yaml`,
  `scenarios/S1-customer/annotation/human-draft.yaml`,
  `prompts/annotator.md`, `tools/annotate.py`

**Interfaces:**
- Consumes: `run_role` (B3).
- Produces: `scenarios/S1-customer/ground-truth.yaml` after CP-1, in the shape
  `requirements: [{id, type, priority, statement, anchor}]`.

- [ ] **Step 1: Pin the source**

Choose a document satisfying the spec's four criteria (§6): it predates this benchmark, no
discovery interview produced it, it pins by SHA, and it is long enough to carry requirements
the bank does not ask for. Copy it into `scenarios/S1-customer/source/` and record the origin:

```
# scenarios/S1-customer/source/ORIGIN.txt
repo   <neighbour repo name>
commit <sha>
path   <path inside that repo>
sha256 <digest of the copied file>
```

Copy the bytes with `git -C <repo> show <sha>:<path>` — from the commit's tree, not from a
working copy, so the provenance holds.

- [ ] **Step 2: Write `prompts/annotator.md`**

```markdown
Extract every atomic requirement stated in the SOURCE below.

Atomic means one obligation per item: if a sentence states two, emit two. Record only what the
SOURCE states — never what a reasonable product would also need.

For each requirement emit: `id` (R-01, R-02, …), `type` (goal | job | function | constraint |
quality), `priority` (must | should | could | unstated — only if the SOURCE says so),
`statement` (one sentence, your words), `anchor` (a verbatim quotation from the SOURCE, long
enough to locate it).

Output YAML with a single top-level key `requirements`. No commentary.

SOURCE:
{source}
```

The annotator sees the source and this instruction and **nothing else**: no bank, no
methodology, no human draft, no loop output (spec §6.1). An annotator that has seen the bank
extracts what the bank can ask, which is the poisoning this scenario exists to avoid.

- [ ] **Step 3: Produce the LLM draft**

```bash
uv run python tools/annotate.py --scenario S1-customer --out annotation/llm-draft.yaml
```

```python
# tools/annotate.py
"""Produce the blind LLM annotation draft for one scenario (spec §6.1).

The annotator sees the pinned source and the extraction instruction and nothing
else — no bank, no methodology, no human draft, no loop output.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from l3bench.roles import RoleSpec, run_role  # noqa: E402

STAND = Path(__file__).resolve().parents[1]


def main() -> int:
    """Render the annotator prompt over the source and write its reply verbatim."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scenario", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--model", default="sonnet")
    args = parser.parse_args()

    scenario = STAND / "scenarios" / args.scenario
    sources = sorted((scenario / "source").glob("*.md"))
    if not sources:
        print(f"no source document under {scenario / 'source'}")
        return 1
    text = "\n\n".join(s.read_text(encoding="utf-8") for s in sources)

    rendered = (STAND / "prompts" / "annotator.md").read_text(encoding="utf-8")
    prompt = scenario / "annotation" / ".annotator.rendered.md"
    prompt.parent.mkdir(parents=True, exist_ok=True)
    prompt.write_text(rendered.replace("{source}", text), encoding="utf-8")

    spec = RoleSpec(name="annotator", model=args.model, prompt=prompt)
    result = run_role(spec, "Extract the requirements now.", scenario / "annotation")
    (scenario / args.out).write_text(result.text + "\n", encoding="utf-8")
    print(f"wrote {scenario / args.out} ({result.reported_model})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

Do not clean up its output — a draft that needed cleaning is evidence about the prompt, and
editing it destroys the blindness the whole denominator rests on.

- [ ] **Step 4: Produce the human draft — blind**

The owner extracts requirements from the same source **without reading `llm-draft.yaml`**, in
the same schema, into `annotation/human-draft.yaml`. This is the point of the exercise: a
denominator agreed after seeing the machine's answer is not independent.

- [ ] **Step 5: Commit both drafts before adjudication**

```bash
git add -A && git commit -m "feat(S1): источник на пине и две слепые разметки"
```

Both drafts are committed **before** adjudication so the diff between them survives in history.

---

## Checkpoint CP-1 — human adjudication of the ground truth

**This is a gate. Nothing downstream of it may run until the owner has adjudicated.**

- [ ] **Step 1: Produce the diff**

```bash
uv run python tools/adjudicate.py --scenario S1-customer --report
```

```python
# tools/adjudicate.py
"""Align two blind annotation drafts, then emit the canonical denominator.

`--report` writes nothing: it prints the three buckets a human adjudicates.
`--emit` writes `ground-truth.yaml` from the agreed set plus every item the
adjudication marked `keep`. Both drafts stay on disk untouched (spec §6.1).
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import yaml

STAND = Path(__file__).resolve().parents[1]
_WORD_RE = re.compile(r"\w+", re.UNICODE)


def _shingles(text: str, size: int = 6) -> set[tuple[str, ...]]:
    tokens = [w.lower() for w in _WORD_RE.findall(text)]
    return {tuple(tokens[i : i + size]) for i in range(0, max(0, len(tokens) - size + 1))}


def _aligned(human: list[dict], llm: list[dict]) -> list[tuple[dict, dict]]:
    """Pair items whose anchors share a 6-token shingle; greedy, one-to-one."""
    pairs, taken = [], set()
    for h in human:
        h_sh = _shingles(h["anchor"])
        for i, l in enumerate(llm):
            if i in taken:
                continue
            if h_sh & _shingles(l["anchor"]):
                pairs.append((h, l))
                taken.add(i)
                break
    return pairs


def main() -> int:
    """Report the buckets, or emit the canonical ground truth."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scenario", required=True)
    parser.add_argument("--report", action="store_true")
    parser.add_argument("--emit", action="store_true")
    args = parser.parse_args()

    base = STAND / "scenarios" / args.scenario / "annotation"
    human = yaml.safe_load((base / "human-draft.yaml").read_text(encoding="utf-8"))[
        "requirements"
    ]
    llm = yaml.safe_load((base / "llm-draft.yaml").read_text(encoding="utf-8"))[
        "requirements"
    ]
    pairs = _aligned(human, llm)
    paired_human = {id(h) for h, _ in pairs}
    paired_llm = {id(l) for _, l in pairs}
    human_only = [h for h in human if id(h) not in paired_human]
    llm_only = [l for l in llm if id(l) not in paired_llm]

    if args.report:
        print(f"agreed:     {len(pairs)}")
        print(f"human-only: {len(human_only)}")
        print(f"llm-only:   {len(llm_only)}")
        for label, items in (("HUMAN-ONLY", human_only), ("LLM-ONLY", llm_only)):
            for item in items:
                print(f"\n[{label}] {item['id']} ({item['type']}) {item['statement']}")
                print(f"    anchor: {item['anchor'][:120]}")
        agreement = len(pairs) / (len(pairs) + len(human_only) + len(llm_only))
        print(f"\nhuman–LLM agreement: {agreement:.2f}")
        return 0

    if args.emit:
        decisions_path = base / "adjudication.md"
        kept = _kept_ids(decisions_path)
        requirements = [h for h, _ in pairs]
        requirements += [i for i in human_only + llm_only if i["id"] in kept]
        for n, item in enumerate(requirements, start=1):
            item["id"] = f"R-{n:02d}"
        target = STAND / "scenarios" / args.scenario / "ground-truth.yaml"
        target.write_text(
            yaml.safe_dump({"requirements": requirements}, allow_unicode=True,
                           sort_keys=False),
            encoding="utf-8",
        )
        print(f"wrote {target}: {len(requirements)} requirement(s)")
        return 0

    parser.error("choose --report or --emit")
    return 2


def _kept_ids(path: Path) -> set[str]:
    """Ids the adjudication marked `keep`, one decision per line."""
    if not path.exists():
        raise SystemExit(f"adjudication missing: {path}. CP-1 is a gate, not a formality.")
    return {
        line.split()[0].strip("-* ")
        for line in path.read_text(encoding="utf-8").splitlines()
        if " keep" in line.lower()
    }


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 2: The owner adjudicates**

For every item outside "agreed", the owner records a decision and a reason in
`annotation/adjudication.md`: **keep** (it is in the source), **drop** (it is not),
**merge** (the two drafts say the same thing differently), **split** (it is not atomic).

- [ ] **Step 3: Emit the canonical denominator**

```bash
uv run python tools/adjudicate.py --scenario S1-customer --emit
```

Writes `ground-truth.yaml` from the agreed set plus every kept item. Both drafts stay on disk
untouched.

- [ ] **Step 4: Record the agreement number**

Append to `annotation/adjudication.md`: the counts, and the agreement figure computed as
`|agreed| / |union|`. Call it **human–LLM agreement**. It is not inter-annotator agreement and
must never be reported as such.

- [ ] **Step 5: Commit**

```bash
git add -A && git commit -m "feat(S1): canonical ground truth после adjudication"
```

**Gate condition:** `ground-truth.yaml` exists, `adjudication.md` explains every non-agreed
item, and the agreement figure is recorded. Until then, no recall metric may be computed, and
no threshold may be proposed — the spec forbids thresholds before the annotation is
adjudicated.

---

### Task B7: extraction recall and the three matcher classes

**Files:**
- Create: `../discovery-test/l3bench/metrics/extraction.py`, `prompts/matcher.md`
- Test: `../discovery-test/tests/test_extraction.py`

**Interfaces:**
- Consumes: `ground-truth.yaml` (CP-1), the produced brief (B5), `run_role` (B3).
- Produces: `Match(gt_id: str, entry_id: str | None, verdict: str, evidence: str)` with
  `verdict in {"supported", "unsupported", "ambiguous"}`, and
  `score(matches, entries) -> ExtractionScore` where `ExtractionScore(recall: float,
  invention_rate: float, ambiguous_rate: float, unmatched: list[str])`. Task B10 consumes
  `score`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_extraction.py
from __future__ import annotations

from l3bench.metrics import extraction as ex


def test_recall_counts_only_supported_matches():
    matches = [
        ex.Match("R-01", "FR-01", "supported", "…"),
        ex.Match("R-02", None, "unsupported", ""),
        ex.Match("R-03", "FR-02", "ambiguous", "…"),
    ]
    score = ex.score(matches, entries=["FR-01", "FR-02"])
    assert score.recall == 1 / 3


def test_ambiguous_is_published_separately_and_is_not_invention():
    matches = [ex.Match("R-01", "FR-01", "ambiguous", "…")]
    score = ex.score(matches, entries=["FR-01", "FR-09"])
    assert score.ambiguous_rate == 1.0
    assert score.invention_rate == 1 / 2, "only FR-09 is unanchored"


def test_an_entry_matched_by_nobody_is_invention():
    score = ex.score([ex.Match("R-01", "FR-01", "supported", "…")],
                     entries=["FR-01", "FR-77"])
    assert score.invention_rate == 1 / 2


def test_unmatched_ground_truth_is_named_for_the_report():
    score = ex.score([ex.Match("R-02", None, "unsupported", "")], entries=[])
    assert score.unmatched == ["R-02"]


def test_an_empty_denominator_is_refused_not_scored():
    import pytest

    with pytest.raises(ValueError, match="empty ground truth"):
        ex.score([], entries=["FR-01"])
```

- [ ] **Step 2: Run it to make sure it fails**

Run: `uv run pytest tests/test_extraction.py -q`
Expected: FAIL — no module `l3bench.metrics.extraction`.

- [ ] **Step 3: Write `prompts/matcher.md`**

```markdown
You decide whether a brief captured a requirement. You never decide whether the requirement is
good, and you never invent requirements.

For each GROUND TRUTH item you receive the BRIEF's entries. Emit exactly one verdict per item:

- `supported` — an entry states the same obligation. Give its id and a verbatim quotation.
- `unsupported` — no entry states it.
- `ambiguous` — an entry is close but the correspondence is arguable: partial overlap, wider or
  narrower scope, or the same topic with a different obligation. Say in one line what makes it
  arguable.

`ambiguous` is a real answer, not a fallback for effort. It is reported separately and is never
counted as an invented requirement, because an incomplete ground truth would otherwise become a
false accusation.

Output YAML: `matches: [{gt_id, entry_id, verdict, evidence}]`. No commentary.
```

- [ ] **Step 4: Implement**

```python
# l3bench/metrics/extraction.py
"""Transition T1: source → customer brief (spec §7).

Recall counts supported matches only. `ambiguous` is published on its own axis
and never counted as invention: an incomplete canonical ground truth would
otherwise be charged to the model as a hallucination.
"""

from __future__ import annotations

from dataclasses import dataclass

VERDICTS = ("supported", "unsupported", "ambiguous")


@dataclass(frozen=True)
class Match:
    """One ground-truth item and what the brief did with it."""

    gt_id: str
    entry_id: str | None
    verdict: str
    evidence: str


@dataclass(frozen=True)
class ExtractionScore:
    """The T1 numbers, each on its own axis."""

    recall: float
    invention_rate: float
    ambiguous_rate: float
    unmatched: list[str]


def score(matches: list[Match], entries: list[str]) -> ExtractionScore:
    """Project matcher verdicts into the T1 metrics."""
    if not matches:
        raise ValueError("empty ground truth: nothing to score against")
    supported = [m for m in matches if m.verdict == "supported"]
    ambiguous = [m for m in matches if m.verdict == "ambiguous"]
    anchored = {m.entry_id for m in matches if m.entry_id}
    unanchored = [e for e in entries if e not in anchored]
    return ExtractionScore(
        recall=len(supported) / len(matches),
        invention_rate=len(unanchored) / len(entries) if entries else 0.0,
        ambiguous_rate=len(ambiguous) / len(matches),
        unmatched=[m.gt_id for m in matches if m.verdict == "unsupported"],
    )
```

- [ ] **Step 5: Run the tests and make sure they pass**

Run: `uv run pytest tests/test_extraction.py -q`
Expected: 5 passed.

- [ ] **Step 6: Commit locally**

```bash
git add -A && git commit -m "feat(metrics): extraction-recall и три класса matcher'а"
```

---

### Task B8: the approval fixture and the T2 metrics

**Files:**
- Create: `../discovery-test/l3bench/approval.py`, `l3bench/metrics/feasibility.py`
- Test: `../discovery-test/tests/test_approval.py`, `tests/test_feasibility.py`

**Interfaces:**
- Consumes: `LoopResult.brief` (B5), `discovery.contract.gate_check`.
- Produces: `build_fixture(brief: Path, out: Path, actor: str, when: str) -> FixtureRecord`
  with `FixtureRecord(source_sha: str, approved_sha: str, diff: list[str], actor: str,
  when: str)`; `must_fr_ids(brief_text: str) -> list[str]`;
  `coverage(upstream: Path, engineer: Path) -> FeasibilityScore` with
  `FeasibilityScore(ratio: float, missing: list[str], linter_findings: list[dict])`.

- [ ] **Step 1: Write the failing test for the fixture**

```python
# tests/test_approval.py
from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from l3bench import approval

BRIEF = """---
status: draft
approved_by: null
approved_at: null
approver: null
conflicts: 0
---

## Функции
- `FR-01` retry a timed-out call — **Priority**: Must
"""


def test_only_approval_metadata_changes(tmp_path):
    src = tmp_path / "brief.md"
    src.write_text(BRIEF, encoding="utf-8")
    record = approval.build_fixture(src, tmp_path / "approved.md",
                                    actor="l3bench-harness", when="2026-08-21T00:00:00Z")
    assert sorted(record.diff) == ["approved_at", "approved_by", "approver", "status"]


def test_the_body_is_byte_identical(tmp_path):
    src = tmp_path / "brief.md"
    src.write_text(BRIEF, encoding="utf-8")
    out = tmp_path / "approved.md"
    approval.build_fixture(src, out, actor="l3bench-harness", when="2026-08-21T00:00:00Z")
    body_in = BRIEF.split("---", 2)[2]
    body_out = out.read_text(encoding="utf-8").split("---", 2)[2]
    assert body_in == body_out


def test_the_source_brief_is_left_untouched(tmp_path):
    src = tmp_path / "brief.md"
    src.write_text(BRIEF, encoding="utf-8")
    before = src.read_bytes()
    approval.build_fixture(src, tmp_path / "approved.md",
                           actor="l3bench-harness", when="2026-08-21T00:00:00Z")
    assert src.read_bytes() == before


def test_editing_content_is_refused(tmp_path):
    src = tmp_path / "brief.md"
    src.write_text(BRIEF, encoding="utf-8")
    with pytest.raises(ValueError, match="content"):
        approval.build_fixture(src, tmp_path / "approved.md", actor="x", when="y",
                               extra={"conflicts": 3})


def test_the_approval_is_recorded_as_synthetic(tmp_path):
    src = tmp_path / "brief.md"
    src.write_text(BRIEF, encoding="utf-8")
    record = approval.build_fixture(src, tmp_path / "approved.md",
                                    actor="l3bench-harness", when="2026-08-21T00:00:00Z")
    meta = yaml.safe_load((tmp_path / "approved.md").read_text(encoding="utf-8")
                          .split("---")[1])
    assert meta["approved_by"] == "l3bench-harness"
    assert record.actor == "l3bench-harness"
```

- [ ] **Step 2: Run it to make sure it fails**

Run: `uv run pytest tests/test_approval.py -q`
Expected: FAIL — no module `l3bench.approval`.

- [ ] **Step 3: Implement the fixture builder**

```python
# l3bench/approval.py
"""The derived approval fixture (spec §6.2).

The contract calls `status`/`approved_by`/`approver` a mirror of git state. In
the stand there is no PR merge behind them, so the mirror reflects nothing: the
manifest records a synthetic approval by the harness actor, never evidence of
review. The permitted diff is those four keys and nothing else.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

from l3bench.hashes import sha256_file

APPROVAL_KEYS = ("status", "approved_by", "approved_at", "approver")


@dataclass(frozen=True)
class FixtureRecord:
    """What was built, from what, by whom, and exactly what changed."""

    source_sha: str
    approved_sha: str
    diff: list[str]
    actor: str
    when: str


def build_fixture(
    brief: Path, out: Path, actor: str, when: str, extra: dict | None = None
) -> FixtureRecord:
    """Write an approved copy of `brief`, touching approval metadata only."""
    if extra:
        forbidden = [k for k in extra if k not in APPROVAL_KEYS]
        if forbidden:
            raise ValueError(f"content edit refused: {forbidden}")

    raw = brief.read_text(encoding="utf-8")
    _, front, body = raw.split("---", 2)
    meta = yaml.safe_load(front) or {}
    changed = []
    for key, value in (
        ("status", "approved"),
        ("approved_by", actor),
        ("approved_at", when),
        ("approver", actor),
    ):
        if meta.get(key) != value:
            meta[key] = value
            changed.append(key)

    out.write_text(
        "---\n"
        + yaml.safe_dump(meta, allow_unicode=True, sort_keys=False)
        + "---"
        + body,
        encoding="utf-8",
    )
    return FixtureRecord(sha256_file(brief), sha256_file(out), sorted(changed), actor, when)
```

- [ ] **Step 4: Write the failing test for T2**

```python
# tests/test_feasibility.py
from __future__ import annotations

from l3bench.metrics import feasibility


UPSTREAM = """---
status: approved
---
## Функции
- `FR-01` повтор вызова — **Priority**: Must
- `FR-02` отчёт — **Priority**: Should
- `FR-03` алерт — **Priority**: Must
"""


def test_only_must_requirements_form_the_denominator(tmp_path):
    assert feasibility.must_fr_ids(UPSTREAM) == ["FR-01", "FR-03"]


def test_ratio_is_mentioned_over_all_must(tmp_path):
    upstream = tmp_path / "upstream.md"
    upstream.write_text(UPSTREAM, encoding="utf-8")
    engineer = tmp_path / "engineer.md"
    engineer.write_text("FR-01 реализуемо; про остальное молчим", encoding="utf-8")
    score = feasibility.coverage(upstream, engineer)
    assert score.ratio == 1 / 2
    assert score.missing == ["FR-03"]


def test_traceability_counts_frs_whose_traces_resolve(tmp_path):
    engineer = tmp_path / "engineer.md"
    engineer.write_text(
        "## Функции\n"
        "- `FR-10` адаптер — **Priority**: Must — traces: [G-01]\n"
        "- `FR-11` кеш — **Priority**: Should — traces: [G-99]\n"
        "## Цели\n- `G-01` снизить отказы\n",
        encoding="utf-8",
    )
    score = feasibility.traceability(engineer)
    assert score.ratio == 1 / 2
    assert score.dangling == ["FR-11"]


def test_a_brief_without_frs_has_no_traceability_ratio(tmp_path):
    engineer = tmp_path / "engineer.md"
    engineer.write_text("## Цели\n- `G-01` снизить отказы\n", encoding="utf-8")
    assert feasibility.traceability(engineer).ratio == 0.0


def test_the_linter_stays_the_normative_check(tmp_path):
    upstream = tmp_path / "upstream.md"
    upstream.write_text(UPSTREAM, encoding="utf-8")
    engineer = tmp_path / "engineer.md"
    engineer.write_text("FR-01 реализуемо", encoding="utf-8")
    score = feasibility.coverage(upstream, engineer)
    assert isinstance(score.linter_findings, list), (
        "the ratio is a projection; findings come from gate_check, not from us"
    )
```

- [ ] **Step 5: Implement T2 on top of the vendored linter**

```python
# l3bench/metrics/feasibility.py
"""Transition T2: approved customer brief → engineer brief (spec §7).

GC-05(engineer) is the normative rule and stays where it is — in the vendored
linter. This module projects the same id set into a ratio so the report can say
"half the Must-FRs got a verdict", and never re-implements the rule.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from discovery.contract import gate_check


@dataclass(frozen=True)
class FeasibilityScore:
    """The T2 numbers plus the linter's own findings, unmodified."""

    ratio: float
    missing: list[str]
    linter_findings: list[dict]


def must_fr_ids(brief_text: str) -> list[str]:
    """Ids of the upstream Must functional requirements, in document order."""
    entries = gate_check.parse_entries(brief_text)
    return [
        entry.eid
        for entry in entries
        if entry.prefix == "FR" and entry.priority() == "Must"
    ]


def coverage(upstream: Path, engineer: Path) -> FeasibilityScore:
    """Share of upstream Must-FRs mentioned by id in the engineer brief."""
    must = must_fr_ids(upstream.read_text(encoding="utf-8"))
    body = engineer.read_text(encoding="utf-8")
    missing = [eid for eid in must if eid not in body]
    findings = gate_check.check(engineer)
    return FeasibilityScore(
        ratio=(len(must) - len(missing)) / len(must) if must else 0.0,
        missing=missing,
        linter_findings=list(findings),
    )


@dataclass(frozen=True)
class TraceScore:
    """Share of the engineer brief's FRs whose `traces` resolve in-document."""

    ratio: float
    dangling: list[str]


def traceability(engineer: Path) -> TraceScore:
    """An FR traces when every id in its `traces` list exists in the brief."""
    text = engineer.read_text(encoding="utf-8")
    entries = gate_check.parse_entries(text)
    present = {entry.eid for entry in entries}
    frs = [entry for entry in entries if entry.prefix == "FR"]
    dangling = [
        entry.eid
        for entry in frs
        if not entry.traces() or any(t not in present for t in entry.traces())
    ]
    return TraceScore(
        ratio=(len(frs) - len(dangling)) / len(frs) if frs else 0.0,
        dangling=dangling,
    )
```

`entry.traces()` is the vendored linter's own accessor — check its exact name in
`src/discovery/contract/gate_check.py` before writing this, and adapt this module if it
differs. The rule that an untraced FR is a finding stays GC-06/GC-07's, in the linter; this
function only counts.

`gate_check.parse_entries` and `gate_check.check` are the vendored linter's own names — read
`src/discovery/contract/gate_check.py` before writing this file and use the exact signatures it
exposes. If a name differs, adapt this module, never the vendored file.

- [ ] **Step 6: Run the tests and make sure they pass**

Run: `uv run pytest tests/test_approval.py tests/test_feasibility.py -q`
Expected: 8 passed.

- [ ] **Step 7: Wire the S2 chain**

```python
# append to l3bench/loop.py
@dataclass(frozen=True)
class ChainResult:
    """The S2 chain: an upstream run, an approval fixture, a downstream run."""

    state: str
    upstream: LoopResult
    fixture: object | None
    downstream: LoopResult | None


def run_chain(
    upstream_scenario: Scenario,
    downstream_scenario: Scenario,
    run_dir: Path,
    cfg: dict,
) -> ChainResult:
    """Run customer → approve → engineer, refusing to fake a missing upstream."""
    from l3bench.approval import build_fixture

    upstream = run_loop(upstream_scenario, run_dir / "upstream", cfg)
    usable = (
        upstream.state == "ok"
        and upstream.brief is not None
        and upstream.exit_code in (0, 11)
    )
    if not usable:
        return ChainResult("blocked_by_upstream_run", upstream, None, None)

    approved = run_dir / "artifacts" / "approved" / "brief.md"
    approved.parent.mkdir(parents=True, exist_ok=True)
    fixture = build_fixture(
        upstream.brief, approved, actor=cfg["actor"], when=cfg["now"]
    )
    downstream = run_loop(
        Scenario(
            name=downstream_scenario.name,
            frame="engineer",
            hidden_spec=downstream_scenario.hidden_spec,
            gt_ids=downstream_scenario.gt_ids,
        ),
        run_dir / "downstream",
        {**cfg, "traces_to": str(approved)},
    )
    return ChainResult(downstream.state, upstream, fixture, downstream)
```

`exit_code in (0, 11)` is deliberate: `11` is `gate: pass, readiness: incomplete` — a brief that
lints clean but is substantively thin. It is still a real brief the engineer frame can trace to,
and excluding it would silently narrow the chain to perfect runs only. `10` (`gate: fail`) is not
usable, and GC-12 would refuse it downstream anyway.

The caller prompt gains one line for the engineer frame: `STATUS` and the first `discovery
start` must pass `--traces-to <path>` from `cfg["traces_to"]`.

Test it with the same monkeypatched `run_role` pattern:

```python
# tests/test_chain.py
def test_a_failed_upstream_blocks_instead_of_scoring_zero(tmp_path, monkeypatch):
    monkeypatch.setattr(loop, "run_loop", lambda s, d, c: loop.LoopResult(
        "harness_error", [], s.name, None, 1))
    result = loop.run_chain(_s1(), _s2(), tmp_path, _cfg())
    assert result.state == "blocked_by_upstream_run"
    assert result.downstream is None


def test_a_thin_but_clean_upstream_still_chains(tmp_path, monkeypatch):
    calls = []

    def fake_loop(scenario, run_dir, cfg):
        calls.append(scenario.frame)
        brief = tmp_path / "b.md"
        brief.write_text("---\nstatus: draft\n---\n## Функции\n", encoding="utf-8")
        return loop.LoopResult("ok", [], scenario.name, brief, 11)

    monkeypatch.setattr(loop, "run_loop", fake_loop)
    result = loop.run_chain(_s1(), _s2(), tmp_path, _cfg())
    assert calls == ["customer", "engineer"]
    assert result.fixture is not None
```

- [ ] **Step 8: Commit locally**

```bash
git add -A && git commit -m "feat(metrics): approval-fixture и feasibility-coverage через линтер"
```

---

### Task B9: S3, the judge, and contradiction recall

**Files:**
- Create: `../discovery-test/scenarios/S3-contradiction/`, `prompts/judge.md`,
  `l3bench/metrics/contradiction.py`
- Test: `../discovery-test/tests/test_contradiction.py`

**Interfaces:**
- Consumes: the produced brief (B5), `run_role` (B3).
- Produces: `recall(brief_text: str, seeded: list[str], judge) -> ContradictionScore` with
  `ContradictionScore(raised: list[str], missed: list[str], recall: float)`.

- [ ] **Step 1: Author the S3 hidden spec**

Write `scenarios/S3-contradiction/source/spec.md` containing at least two obligations that
cannot both hold — e.g. "любой отчёт отдаётся за 50 мс" against "отчёт содержит полную
выгрузку за год". Record each seeded contradiction in
`scenarios/S3-contradiction/seeded.yaml` as `{id, first, second, why}`. The synthetic scenario
exists because seeding a contradiction into someone else's document is both harder and less
honest.

- [ ] **Step 2: Write the failing test**

```python
# tests/test_contradiction.py
from __future__ import annotations

from l3bench.metrics import contradiction as c

BRIEF_WITH = "## Открытые вопросы\n- `X-01` latency vs полная выгрузка — `status: open`\n"
BRIEF_WITHOUT = "## Функции\n- `FR-01` отчёт — **Priority**: Must\n"


def test_an_open_x_is_detected_deterministically():
    assert c.open_conflicts(BRIEF_WITH) == ["X-01"]
    assert c.open_conflicts(BRIEF_WITHOUT) == []


def test_the_judge_decides_only_whether_it_is_the_seeded_one():
    calls = []

    def judge(x_id, brief, seed):
        calls.append((x_id, seed["id"]))
        return True

    score = c.recall(BRIEF_WITH, [{"id": "C-01", "first": "a", "second": "b"}], judge)
    assert calls == [("X-01", "C-01")]
    assert score.recall == 1.0


def test_a_swallowed_contradiction_is_missed_not_forgiven():
    score = c.recall(BRIEF_WITHOUT, [{"id": "C-01", "first": "a", "second": "b"}],
                     lambda *_: True)
    assert score.recall == 0.0 and score.missed == ["C-01"]


def test_an_unrelated_x_does_not_count_as_a_catch():
    score = c.recall(BRIEF_WITH, [{"id": "C-01", "first": "a", "second": "b"}],
                     lambda *_: False)
    assert score.recall == 0.0
```

- [ ] **Step 3: Run it to make sure it fails, then implement**

Run: `uv run pytest tests/test_contradiction.py -q` — expected FAIL.

```python
# l3bench/metrics/contradiction.py
"""S3: was the seeded contradiction raised, or swallowed (spec §7)?

Whether an `X-NN` exists is deterministic — it is in the brief or it is not.
Whether it is *the seeded* contradiction is a judgement, and only that part is
delegated to the judge.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass

_OPEN_X_RE = re.compile(r"`(X-\d+)`[^\n]*`status:\s*open`")


@dataclass(frozen=True)
class ContradictionScore:
    """Which seeded contradictions were raised, and which were swallowed."""

    raised: list[str]
    missed: list[str]
    recall: float


def open_conflicts(brief_text: str) -> list[str]:
    """Ids of `X-NN` entries the brief marks `status: open`."""
    return _OPEN_X_RE.findall(brief_text)


def recall(
    brief_text: str,
    seeded: list[dict],
    judge: Callable[[str, str, dict], bool],
) -> ContradictionScore:
    """Match open conflicts against seeded ones; the judge rules on identity."""
    open_ids = open_conflicts(brief_text)
    raised, missed = [], []
    for seed in seeded:
        if any(judge(x_id, brief_text, seed) for x_id in open_ids):
            raised.append(seed["id"])
        else:
            missed.append(seed["id"])
    return ContradictionScore(raised, missed, len(raised) / len(seeded) if seeded else 0.0)
```

- [ ] **Step 4: Write `prompts/judge.md`**

```markdown
You are given one open conflict from a brief and one seeded contradiction. Decide a single
question: does the conflict name the same incompatibility as the seed?

Answer `yes` only if both sides of the seed are recognisable in the conflict. A conflict about
one of the two obligations alone is `no`. A conflict about an unrelated topic is `no`.

Output one word: `yes` or `no`. No commentary.
```

- [ ] **Step 5: Run the tests, then commit locally**

```bash
uv run pytest -q && uv run ruff check . && uv run ruff format --check .
git add -A && git commit -m "feat(S3): засеянное противоречие, судья и contradiction-recall"
```

---

### Task B10: the first calibration run

**Files:**
- Create: `../discovery-test/l3bench/report.py`, `tools/run_benchmark.py`
- Test: `../discovery-test/tests/test_report.py`

**Interfaces:**
- Consumes: everything above.
- Produces: `aggregate(runs: list[RunOutcome]) -> Report` with
  `Report(valid_run_rate, invalid_leak_rate, harness_error_rate, upstream_completion_rate,
  distributions: dict[str, Distribution])` and `Distribution(median, low, high, n)`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_report.py
from __future__ import annotations

from l3bench import report


def _outcome(state: str, **metrics):
    return report.RunOutcome(run_id=state, state=state, metrics=metrics)


def test_validity_rates_are_published_not_hidden():
    r = report.aggregate([
        _outcome("ok", recall=0.8),
        _outcome("invalid_leak"),
        _outcome("harness_error"),
        _outcome("ok", recall=0.6),
    ])
    assert r.valid_run_rate == 0.5
    assert r.invalid_leak_rate == 0.25
    assert r.harness_error_rate == 0.25


def test_only_valid_runs_enter_a_distribution():
    r = report.aggregate([_outcome("ok", recall=0.8), _outcome("invalid_leak", recall=1.0)])
    assert r.distributions["recall"].n == 1
    assert r.distributions["recall"].median == 0.8


def test_a_distribution_carries_its_spread():
    r = report.aggregate([_outcome("ok", recall=x) for x in (0.2, 0.5, 0.9)])
    d = r.distributions["recall"]
    assert (d.median, d.low, d.high) == (0.5, 0.2, 0.9)


def test_upstream_completion_is_its_own_rate():
    r = report.aggregate([_outcome("ok"), _outcome("blocked_by_upstream_run")])
    assert r.upstream_completion_rate == 0.5


def test_no_threshold_is_applied_anywhere():
    r = report.aggregate([_outcome("ok", recall=0.01)])
    assert not hasattr(r, "passed"), "v1 publishes numbers, it does not judge them"
```

- [ ] **Step 2: Implement `l3bench/report.py`**

```python
# l3bench/report.py
"""Aggregate many runs into publishable numbers (spec §7.2).

Validity rates are computed over *all* runs and distributions over valid ones,
so a caller that leaks or fails cannot improve the headline by having its bad
runs discarded. Nothing here decides pass or fail: v1 publishes numbers.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass, field


@dataclass(frozen=True)
class RunOutcome:
    """One run: how it ended and what it measured, if anything."""

    run_id: str
    state: str
    metrics: dict[str, float] = field(default_factory=dict)


@dataclass(frozen=True)
class Distribution:
    """One metric across the valid runs: median and the spread around it."""

    median: float
    low: float
    high: float
    n: int


@dataclass(frozen=True)
class Report:
    """Validity rates over every run, distributions over the valid ones."""

    valid_run_rate: float
    invalid_leak_rate: float
    harness_error_rate: float
    upstream_completion_rate: float
    distributions: dict[str, Distribution]


def aggregate(runs: list[RunOutcome]) -> Report:
    """Project run outcomes into rates and distributions, judging nothing."""
    total = len(runs) or 1
    valid = [r for r in runs if r.state == "ok"]
    blocked = [r for r in runs if r.state == "blocked_by_upstream_run"]

    names = {name for r in valid for name in r.metrics}
    distributions = {}
    for name in sorted(names):
        values = [r.metrics[name] for r in valid if name in r.metrics]
        distributions[name] = Distribution(
            median=statistics.median(values),
            low=min(values),
            high=max(values),
            n=len(values),
        )

    return Report(
        valid_run_rate=len(valid) / total,
        invalid_leak_rate=len([r for r in runs if r.state == "invalid_leak"]) / total,
        harness_error_rate=len([r for r in runs if r.state == "harness_error"]) / total,
        upstream_completion_rate=(total - len(blocked)) / total,
        distributions=distributions,
    )
```

- [ ] **Step 3: Write `tools/run_benchmark.py`**

```python
# tools/run_benchmark.py
"""Run the benchmark: N loops per scenario, one manifest each, one report.

A run directory is never deleted, whatever the state — `invalid_leak`,
`blocked_by_upstream_run` and `harness_error` are results too, and their rates
are published (spec §7.2).
"""

from __future__ import annotations

import argparse
import json
import sys
import tomllib
from datetime import datetime, timezone
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

sys.path.insert(0, str(Path(__file__).resolve().parent))

from freshness import current_state  # noqa: E402
from l3bench import manifest, report  # noqa: E402
from l3bench.loop import Scenario, run_loop  # noqa: E402

STAND = Path(__file__).resolve().parents[1]


def _scenario(name: str) -> Scenario:
    """Load one scenario's frame, hidden spec and ground-truth ids."""
    base = STAND / "scenarios" / name
    meta = yaml.safe_load((base / "scenario.yaml").read_text(encoding="utf-8"))
    spec_text = "\n\n".join(
        s.read_text(encoding="utf-8") for s in sorted((base / "source").glob("*.md"))
    )
    gt_path = base / "ground-truth.yaml"
    if not gt_path.exists():
        raise SystemExit(
            f"{name}: no ground-truth.yaml. CP-1 is a gate: adjudicate first."
        )
    gt = yaml.safe_load(gt_path.read_text(encoding="utf-8"))["requirements"]
    return Scenario(name, meta["frame"], spec_text, [r["id"] for r in gt])


def _run_id(index: int) -> str:
    """Sortable run id: timestamp plus an index within this invocation."""
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + f"-{index:02d}"


def main() -> int:
    """Run every requested scenario `repetitions` times and print the report."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scenario", action="append", dest="scenarios")
    parser.add_argument("--all", action="store_true")
    parser.add_argument("--repetitions", type=int)
    args = parser.parse_args()

    cfg = tomllib.loads((STAND / "config.toml").read_text(encoding="utf-8"))
    cfg["prompts"] = {
        role: str(STAND / "prompts" / f"{role}.md") for role in cfg["models"]
    }
    cfg["actor"] = "l3bench-harness"
    cfg["now"] = datetime.now(timezone.utc).isoformat()
    names = (
        [p.name for p in sorted((STAND / "scenarios").iterdir()) if p.is_dir()]
        if args.all
        else (args.scenarios or [])
    )
    if not names:
        parser.error("pass --scenario NAME or --all")

    files, values = current_state()
    outcomes: list[report.RunOutcome] = []
    for name in names:
        scenario = _scenario(name)
        for index in range(args.repetitions or cfg["repetitions"]):
            run_id = _run_id(index)
            run_dir = STAND / "runs" / run_id
            result = run_loop(scenario, run_dir, cfg)
            reported = _reported_models(run_dir)
            manifest.RunManifest(
                run_id=run_id,
                files=files,
                values={**values, **reported, "scenario": name},
                counters=_counters(run_dir),
                transcripts={
                    role.name: str(role.relative_to(run_dir))
                    for role in sorted((run_dir / "roles").glob("*/stream.jsonl"))
                },
                state=result.state,
            ).write(run_dir)
            outcomes.append(
                report.RunOutcome(run_id, result.state, _metrics(result, run_dir))
            )
            print(f"{run_id} {name}: {result.state} ({len(result.turns)} turn(s))")

    final = report.aggregate(outcomes)
    print(json.dumps(final.__dict__, default=lambda o: o.__dict__, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

`_reported_models`, `_counters` and `_metrics` are three small readers over the run directory:
the first walks each `stream.jsonl` for the `model` identifier the role reported (this is the
half of the model selection the CLI argument cannot give you), the second sums `usage` across
roles, the third calls the metric modules of Tasks B7–B9 and returns their numbers as a flat
dict together with the two the loop itself produces — `turns` (interview length) and
`output_tokens` (cost) — so length and cost end up as distributions like every other metric
rather than as prose in a log. Write them in this file with tests in `tests/test_run_benchmark.py`, using the fake
`claude` fixture — no run of this script in tests may spend a token.

- [ ] **Step 4: Dry-run against the fake `claude` first**

```bash
L3BENCH_CLAUDE=tests/fake_claude/claude uv run python tools/run_benchmark.py --scenario S1-customer --repetitions 1
```

Expected: a run directory with a manifest, a transcript per role, and a report. **No tokens are
spent.** Fix everything that breaks here before spending any.

- [ ] **Step 5: Run S1 for real, once**

```bash
uv run python tools/run_benchmark.py --scenario S1-customer --repetitions 1
```

Read the transcript end to end. Expect problems in the caller's payloads, not in the metrics —
that is what a first run is for. Record what you found in `runs/<ULID>/NOTES.md`.

- [ ] **Step 6: Run the full first pass**

```bash
uv run python tools/run_benchmark.py --all
```

Three scenarios × `repetitions = 5`. Long-running: launch it detached from the session, not as
a backgrounded shell job, and watch the log — a harness that dies mid-run leaves a half-written
manifest and no result.

- [ ] **Step 7: Commit the runs**

```bash
git add -A && git commit -m "feat(run): первый калибровочный прогон L3"
```

---

## Checkpoint CP-2 — human–LLM calibration of matcher and judge

**This is a gate. The baseline may not be published until it closes.**

- [ ] **Step 1: Draw the sample**

```bash
uv run python tools/calibrate.py --sample 20 --out calibration/<date>/sample.yaml
```

```python
# tools/calibrate.py
"""Human–LLM calibration of matcher and judge (spec §7.3).

`--sample` draws a stratified sample and writes it with the machine's verdicts
REMOVED — blind labelling is the whole point. `--compare` puts the two side by
side and reports agreement per verdict class, plus the sensitivity of recall to
the disputed items.
"""

from __future__ import annotations

import argparse
import random
import sys
from collections import Counter, defaultdict
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

STAND = Path(__file__).resolve().parents[1]
CLASSES = ("supported", "unsupported", "ambiguous")


def _all_matches() -> list[dict]:
    """Every matcher decision from every valid run, with its run id attached."""
    decisions = []
    for path in sorted(STAND.glob("runs/*/matches.yaml")):
        run_id = path.parent.name
        for match in yaml.safe_load(path.read_text(encoding="utf-8"))["matches"]:
            decisions.append({**match, "run_id": run_id})
    return decisions


def _draw(decisions: list[dict], size: int, seed: int) -> list[dict]:
    """Stratified draw: every verdict class represented, then filled at random."""
    rng = random.Random(seed)
    by_class = defaultdict(list)
    for d in decisions:
        by_class[d["verdict"]].append(d)
    quota = max(1, size // len(CLASSES))
    drawn: list[dict] = []
    for verdict in CLASSES:
        pool = by_class.get(verdict, [])
        drawn += rng.sample(pool, min(quota, len(pool)))
    rest = [d for d in decisions if d not in drawn]
    drawn += rng.sample(rest, min(size - len(drawn), len(rest)))
    return drawn


def main() -> int:
    """Draw the blind sample, or compare it against the human labels."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sample", type=int)
    parser.add_argument("--compare", action="store_true")
    parser.add_argument("--out", required=True)
    parser.add_argument("--seed", type=int, default=20260821)
    args = parser.parse_args()
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)

    if args.sample:
        drawn = _draw(_all_matches(), args.sample, args.seed)
        out.write_text(
            yaml.safe_dump(
                {
                    "seed": args.seed,
                    "decisions": [
                        {k: v for k, v in d.items() if k != "verdict"} for d in drawn
                    ],
                },
                allow_unicode=True, sort_keys=False,
            ),
            encoding="utf-8",
        )
        (out.parent / ".machine.yaml").write_text(
            yaml.safe_dump({"decisions": drawn}, allow_unicode=True, sort_keys=False),
            encoding="utf-8",
        )
        print(f"wrote {out} ({len(drawn)} decision(s)); label it without opening .machine.yaml")
        return 0

    machine = {
        (d["run_id"], d["gt_id"]): d["verdict"]
        for d in yaml.safe_load(
            (out.parent / ".machine.yaml").read_text(encoding="utf-8")
        )["decisions"]
    }
    human = {
        (d["run_id"], d["gt_id"]): d["verdict"]
        for d in yaml.safe_load(
            (out.parent / "human.yaml").read_text(encoding="utf-8")
        )["decisions"]
    }
    shared = sorted(set(machine) & set(human))
    agreed = [k for k in shared if machine[k] == human[k]]
    per_class = Counter(
        (machine[k], machine[k] == human[k]) for k in shared
    )

    lines = [
        "# Human–LLM calibration",
        "",
        f"Sample: {len(shared)} decision(s). This is human–LLM agreement, "
        "not inter-human agreement.",
        "",
        f"Overall agreement: {len(agreed) / len(shared):.2f}" if shared else "empty sample",
        "",
        "| verdict | agreed | disagreed |",
        "|---|---:|---:|",
    ]
    for verdict in CLASSES:
        lines.append(
            f"| {verdict} | {per_class[(verdict, True)]} | {per_class[(verdict, False)]} |"
        )
    lines += ["", "## Disagreements", ""]
    for key in shared:
        if machine[key] != human[key]:
            lines.append(f"- `{key[0]}` {key[1]}: machine `{machine[key]}`, human `{human[key]}`")
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

Twenty matcher decisions drawn across all valid runs, stratified so that `supported`,
`unsupported` and `ambiguous` are all represented, plus every judge decision from S3 (there are
few). The sample file carries the inputs and hides the machine's verdict; the machine's answers
sit in a sibling dotfile that the labeller does not open.

- [ ] **Step 2: The owner labels the sample blind**

Into `calibration/<date>/human.yaml`, in the same schema. Blind means the machine's verdicts are
not visible while labelling — the file written in step 1 is the one to open.

- [ ] **Step 3: Compute agreement and disagreement structure**

```bash
uv run python tools/calibrate.py --compare --out calibration/<date>/report.md
```

The comparison reads `calibration/<date>/human.yaml` and the sibling `.machine.yaml` written in
step 1; if either is missing it fails loudly rather than reporting an agreement of zero.

The report states: overall human–LLM agreement, agreement per verdict class, and every
disagreement with both labels and the evidence. Agreement per class matters more than the
overall figure — a matcher that agrees on `supported` and diverges on `ambiguous` is telling you
where the ground truth is thin.

- [ ] **Step 4: Report the sensitivity of the result**

Recompute recall twice: once counting every disputed item as supported, once as unsupported.
The gap between the two is the honest error bar on the headline number, and it goes into the
baseline report next to it.

- [ ] **Step 5: Publish the baseline**

Write `BASELINE.md` in the stand: the distributions, the validity rates, the human–LLM
agreement figures for annotation (CP-1) and for matching (CP-2), the sensitivity gap, and the
manifest ids of the runs it summarises. State plainly that no threshold is derived from it.

- [ ] **Step 6: Commit**

```bash
git add -A && git commit -m "feat(baseline): калибровка matcher/judge и первый baseline L3"
```

**Gate condition:** `BASELINE.md` exists, both agreement figures are in it, and the sensitivity
gap is stated. Only now may the phase-3 decision cite these numbers.

---

## After the plan

- Update `TODO.md` in `discovery`: close `@id:l3-quality-benchmark` with the PR numbers of
  Part A and the stand's commit range, and record where `BASELINE.md` lives.
- `@id:phase-3-grounding` keeps its `@blocked_by:todo://discovery/l3-quality-benchmark` until
  the baseline exists; once it does, replace the blocker with the numbers that argue for or
  against grounding.
- Findings from the runs are attributed by layer (spec §3): runtime → an item in `discovery`;
  wording, bank composition, methodology → a handoff issue in `discovery-toolkit`; scenario,
  caller, judge, matcher → the stand.
