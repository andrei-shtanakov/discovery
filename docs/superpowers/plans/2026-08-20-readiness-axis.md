# readiness axis — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: use `superpowers:subagent-driven-development`
> (or `superpowers:executing-plans`) when running this plan by hand. As with the runtime-v1
> plan, it can instead be derived one-to-one into `spec/tasks.md` for maestro + spec-runner
> (one `TASK-NNN` per task below). Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** project the contract's §4 coverage-gate formula into the status envelope as a
third axis (`readiness`) and into exit code `11`, so a caller can no longer mistake a
lint-valid stub for a finished brief.

**Architecture:** one public function in `render` computes the §4 verdict and the clauses
that failed it; the brief's `gate_passed`, `GateResult`, and the `readiness` axis are all
projections of that single result. Nothing recomputes the formula downstream. Before the
projection lands, the formula is made incapable of a false verdict: a `traces` field of the
wrong type is refused instead of silently iterated character by character.

**Tech Stack:** Python ≥3.12, `uv`, pytest, ruff, pyrefly, PyYAML.

**Spec:** `docs/superpowers/specs/2026-08-18-discovery-runtime-design.md` §6–§7 (revised
2026-08-20) — read them first; this plan argues from them and does not repeat the reasoning.

## Global Constraints

- Python `>=3.12`; package layout `src/discovery/`; line length 88; type hints on all code.
- `uv` only: `uv add <pkg>`, `uv run <tool>`. Never `pip`, never `uv pip install`.
- Test command: `uv run pytest`. Lint: `uv run ruff check . && uv run ruff format --check .`.
  Types: `uv run pyrefly check`. All three must be green before every commit.
- **Never edit `src/discovery/contract/gate_check.py` or `src/discovery/contract/frames/*`.**
  They are vendored bytes; editing them destroys what copy-integrity proves.
- **The formula lives in exactly one place.** No task may add a second implementation of §4.
  If a value is needed elsewhere, it is passed through, never recomputed.
- New tests go into the existing per-module test files. If a task's RED checkpoint is frozen
  as its own file, name it `tests/test_rd_00N_red.py` — the `task_`, `a2_` and `d2_` number
  spaces are already taken by earlier arcs and collide silently.
- Direct commits to `master` are forbidden; this plan runs on branch `spec/readiness-axis`
  and lands through a pull request a human merges.

## Vocabulary

- **readiness** — the §4 verdict over the derived brief: `ready` | `incomplete` | `unknown`.
- **readiness diagnostics** — the deterministic list of failed §4 clauses. They travel in
  their own envelope key, `readiness_findings`, never merged into linter `findings`.
- **`gate`** — unchanged: the linter's verdict, mirror of the brief's own `validation`.

---

### Task 1: `traces` of the wrong type is refused, never guessed

`render._fr_all_traced` does `[str(t) for t in (entry.fields.get("traces") or [])]`. For a
YAML list this yields the ids; for the string `"[J-02, G-01]"` it yields single characters,
`'J'` and `'G'` survive the prefix filter, neither is an id, and the function returns
`False` — a wrong answer instead of a refusal. This must be fixed **before** the formula is
projected, or the projection publishes that wrong answer as an exit code.

Two sides: `parse_payload` refuses such a payload at intake, so it never enters a journal;
`render` refuses it on read, so journals recorded before this fix produce
`operation.status: unknown` + exit `1` (§7: an axis the runtime cannot determine is never
answered by guessing) rather than a false verdict. `cli.main` already catches
`PayloadInvalid` and turns it into `protocol.unknown(...)`.

**Files:**
- Modify: `src/discovery/payload.py` (`_parse_entry`)
- Modify: `src/discovery/render.py` (`_fr_all_traced`)
- Test: `tests/test_payload.py`, `tests/test_render.py`, `tests/test_cli.py`

**Interfaces:**
- Consumes: `discovery.payload.PayloadInvalid` (already exists).
- Produces: `render._traces_of(entry: Entry) -> list[str]` — the only reader of the
  `traces` field; raises `PayloadInvalid` on any non-list value. Task 2 calls it.

- [ ] **Step 1: Write the failing tests**

In `tests/test_payload.py`:

```python
class TestTracesType:
    def test_string_traces_are_refused(self):
        raw = (
            "text: an answer\n"
            "entries:\n"
            "  - id: FR-01\n"
            "    body: a function\n"
            "    traces: '[J-02, G-01]'\n"
        )
        with pytest.raises(PayloadInvalid) as exc:
            parse_payload(raw)
        assert "traces" in str(exc.value)
        assert "FR-01" in str(exc.value)

    def test_list_traces_are_accepted(self):
        raw = (
            "text: an answer\n"
            "entries:\n"
            "  - id: FR-01\n"
            "    body: a function\n"
            "    traces: [J-02, G-01]\n"
        )
        payload = parse_payload(raw)
        assert payload.entries[0].eid == "FR-01"
```

In `tests/test_render.py` (a journal recorded before the intake check existed):

```python
class TestTracesTypeOnRead:
    def test_string_traces_raise_instead_of_yielding_a_false_verdict(self):
        events = [
            answer(
                "customer.functions.01",
                "product",
                "entries:\n"
                "  - id: G-01\n"
                "    body: a goal\n"
                "  - id: FR-01\n"
                "    body: a function\n"
                "    traces: '[G-01]'\n",
            )
        ]
        with pytest.raises(PayloadInvalid) as exc:
            render_brief(CUSTOMER, events, validation="pending")
        assert "FR-01" in str(exc.value)
```

In `tests/test_cli.py` (the process-level consequence). The event is appended straight to
the journal, bypassing `cmd_answer`, because intake validation now rejects such a payload —
the case under test is a journal written before that check existed:

```python
class TestMalformedTracesInJournal:
    def test_status_reports_unknown_and_exits_1(self, capsys, monkeypatch, tmp_path):
        session_id, _, _ = _start(capsys, monkeypatch, tmp_path, ONE_QUESTION)
        cli._journal(session_id).append(
            {
                "event": "answer_recorded",
                "question_id": "customer.g.01",
                "participant_role": "customer",
                "answer_id": "sha256:legacy",
                "payload": (
                    "text: an answer\n"
                    "entries:\n"
                    "  - id: G-01\n"
                    "    body: a goal\n"
                    "  - id: FR-01\n"
                    "    body: a function\n"
                    "    traces: '[G-01]'\n"
                ),
            }
        )

        code, envelope = _run(capsys, ["status", "--session", session_id])

        assert code == 1
        assert envelope["operation"]["status"] == "unknown"
        assert "traces" in envelope["operation"]["reason"]
```

`_start`, `_run` and `ONE_QUESTION` are the existing fixtures at the top of
`tests/test_cli.py`. `tests/test_render.py` needs `import pytest` and
`from discovery.payload import PayloadInvalid` added to its imports.

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_payload.py::TestTracesType tests/test_render.py::TestTracesTypeOnRead tests/test_cli.py::TestMalformedTracesInJournal -v`
Expected: FAIL — `parse_payload` accepts the string, `render_brief` returns a brief with
`gate_passed: false`, `status` exits `0`/`10`.

- [ ] **Step 3: Refuse at intake**

In `src/discovery/payload.py`, above `_parse_entry`:

```python
LIST_FIELDS = {"traces"}
```

and inside `_parse_entry`, after `body` is read and before `fields` is built:

```python
    for key, value in item.items():
        if key in LIST_FIELDS and not isinstance(value, list):
            raise PayloadInvalid(
                f"{eid}: {key!r} must be a YAML list, got "
                f"{type(value).__name__}: {value!r}"
            )
```

Only the exact lowercase `traces` is checked — that is the single spelling `render` reads.
A differently-cased key is simply not a trace, and shows up as an untraced FR in Task 2's
diagnostics rather than as a false verdict.

- [ ] **Step 4: Refuse on read**

In `src/discovery/render.py`, add the import `from discovery.payload import PayloadInvalid`
(no cycle: `payload` imports neither `render` nor anything that reaches it), then replace
`_fr_all_traced` with:

```python
def _traces_of(entry: Entry) -> list[str]:
    """The entry's `traces` as ids, refusing any other type.

    A string is not a one-element list: iterating `"[J-02, G-01]"` yields
    characters, two of which survive the G/J prefix filter and match no id,
    so the old code answered `False` where it knew nothing. §7 forbids that
    trade — an undeterminable axis is `unknown`, never a guess.
    """
    raw = entry.fields.get("traces")
    if raw is None:
        return []
    if not isinstance(raw, list):
        raise PayloadInvalid(
            f"{entry.eid}: 'traces' must be a list, got "
            f"{type(raw).__name__}: {raw!r}"
        )
    return [str(t) for t in raw]


def _fr_all_traced(entries: list[Entry]) -> bool:
    """Every FR entry traces to at least one existing G/J entry (GC-06 mirror)."""
    ids = {e.eid for e in entries}
    for entry in (e for e in entries if e.prefix == "FR"):
        targets = _traces_of(entry)
        matched = [t for t in targets if t.split("-", 1)[0] in ("G", "J")]
        if not matched or any(t not in ids for t in matched):
            return False
    return True
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `uv run pytest tests/test_payload.py tests/test_render.py tests/test_cli.py -v`
Expected: PASS, including every pre-existing case in those files.

- [ ] **Step 6: Full suite, lint, types**

Run: `uv run pytest && uv run ruff format --check . && uv run ruff check . && uv run pyrefly check`
Expected: all green.

- [ ] **Step 7: Commit**

```bash
git add src/discovery/payload.py src/discovery/render.py tests/test_payload.py tests/test_render.py tests/test_cli.py
git commit -m "fix(render): traces неверного типа — отказ, а не ложный вердикт"
```

---

### Task 2: one public `readiness()` — the §4 formula and its diagnostics

**Files:**
- Modify: `src/discovery/render.py`
- Test: `tests/test_render.py`

**Interfaces:**
- Consumes: `render._traces_of` (Task 1), `render._entries`, `render._coverage`,
  `gate_check.FRAMES`.
- Produces:
  - `render.READY = "ready"`, `render.INCOMPLETE = "incomplete"`
  - `render.ReadinessResult(verdict: str, findings: list[str])` with a
    `gate_passed: bool` property (`verdict == READY`)
  - `render.readiness(events: list[dict], frame: str) -> ReadinessResult`

  Tasks 3–5 consume `readiness()` and never re-derive it.

- [ ] **Step 1: Write the failing tests**

In `tests/test_render.py`:

```python
class TestReadiness:
    def test_empty_transcript_is_incomplete_and_names_every_required_topic(self):
        result = readiness([], "customer")

        assert result.verdict == "incomplete"
        assert result.gate_passed is False
        assert len(result.findings) == 8
        assert any("goals" in f for f in result.findings)
        assert any("out_of_scope" in f for f in result.findings)

    def test_full_customer_brief_is_ready_with_no_findings(self):
        result = readiness([answer("q", "product", _ALL_REQUIRED_COVERED)], "customer")

        assert result.verdict == "ready"
        assert result.gate_passed is True
        assert result.findings == []

    def test_untraced_fr_is_named_by_id(self):
        payload = _ALL_REQUIRED_COVERED.replace("    traces: [G-01]\n", "", 1)
        result = readiness([answer("q", "product", payload)], "customer")

        assert result.verdict == "incomplete"
        assert any("FR-01" in f for f in result.findings)

    def test_blocking_open_question_is_named_by_id(self):
        payload = _ALL_REQUIRED_COVERED + (
            "  - id: Q-01\n"
            "    body: an unresolved question\n"
            "    owner_role: product\n"
            "    blocking: true\n"
        )
        result = readiness([answer("q", "product", payload)], "customer")

        assert result.verdict == "incomplete"
        assert any("Q-01" in f for f in result.findings)

    def test_findings_are_deterministic_across_calls(self):
        events = [answer("q", "product", "entries:\n  - id: G-01\n    body: a goal\n")]

        assert readiness(events, "customer").findings == (
            readiness(events, "customer").findings
        )

    def test_frontmatter_gate_passed_equals_the_readiness_verdict(self):
        events = [answer("q", "product", _ALL_REQUIRED_COVERED)]
        meta = _frontmatter(render_brief(CUSTOMER, events, validation="pending"))

        assert meta["coverage"]["gate_passed"] is readiness(events, "customer").gate_passed
```

`_ALL_REQUIRED_COVERED` is the fixture string already used by `tests/test_gate.py`; copy it
into `tests/test_render.py` verbatim (both files already keep their own local fixtures) and
extend the import line to `from discovery.render import readiness, render_brief`.

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_render.py::TestReadiness -v`
Expected: FAIL with `ImportError: cannot import name 'readiness'`.

- [ ] **Step 3: Implement the single formula**

In `src/discovery/render.py`, replace `_gate_passed` with the public result. Keep
`_fr_all_traced` as the GC-06 mirror used by the traces clause:

```python
READY = "ready"
INCOMPLETE = "incomplete"


@dataclass(frozen=True)
class ReadinessResult:
    """The §4 coverage-gate verdict plus the clauses that failed it.

    The one source of both the brief's `gate_passed` and the protocol's
    `readiness` axis (§6, §7): a caller that needs the verdict receives this
    object, never a second evaluation of the formula.
    """

    verdict: str
    findings: list[str]

    @property
    def gate_passed(self) -> bool:
        return self.verdict == READY


def readiness(events: list[dict], frame: str) -> ReadinessResult:
    """`gate_passed` (contract §4), mirrored rather than predicted, with the
    failed clauses named in a deterministic order: uncovered required topics
    in frame order, then untraced FRs and blocking open questions in answer
    order."""
    entries = _entries(events)
    coverage = _coverage(entries, frame)
    ids = {e.eid for e in entries}
    findings: list[str] = []

    for key in FRAMES[frame]["required"]:
        if coverage.get(key) != "covered":
            findings.append(f"required topic {key!r} is not covered")

    for entry in entries:
        if entry.prefix != "FR":
            continue
        targets = _traces_of(entry)
        matched = [t for t in targets if t.split("-", 1)[0] in ("G", "J")]
        if not matched or any(t not in ids for t in matched):
            findings.append(f"{entry.eid} has no trace to an existing G/J entry")

    for entry in entries:
        if (
            entry.prefix == "Q"
            and not _is_true(entry.fields.get("resolved"))
            and _is_true(entry.fields.get("blocking"))
        ):
            findings.append(f"{entry.eid} is a blocking open question")

    return ReadinessResult(
        verdict=INCOMPLETE if findings else READY, findings=findings
    )
```

Then, in `render_brief`, take `gate_passed` from that one result:

```python
        "coverage": {
            **coverage,
            "gate_passed": readiness(events, frame).gate_passed,
        },
```

`readiness()` re-derives `entries` and `coverage` that `render_brief` already has. That is
deliberate: both are pure functions of the same events, and one formula with one entry point
is worth more than one avoided parse. Do **not** "optimise" it by inlining the clauses.

Delete `_fr_all_traced` if nothing else calls it (`grep -rn "_fr_all_traced" src tests`); the
traces clause above is now its only consumer.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/test_render.py -v`
Expected: PASS, including the pre-existing frontmatter cases.

- [ ] **Step 5: Full suite, lint, types**

Run: `uv run pytest && uv run ruff format --check . && uv run ruff check . && uv run pyrefly check`
Expected: all green.

- [ ] **Step 6: Commit**

```bash
git add src/discovery/render.py tests/test_render.py
git commit -m "feat(render): публичный readiness() — формула §4 и её диагностики в одном месте"
```

---

### Task 3: `GateResult` carries the readiness verdict

**Files:**
- Modify: `src/discovery/gate.py`
- Test: `tests/test_gate.py`

**Interfaces:**
- Consumes: `render.readiness`, `render.ReadinessResult` (Task 2).
- Produces: `GateResult` gains `readiness: str` and `readiness_findings: list[str]`.
  Task 5 reads both.

- [ ] **Step 1: Write the failing tests**

In `tests/test_gate.py`:

```python
class TestReadinessOnGateResult:
    def test_thin_brief_is_lint_clean_but_not_ready(self, tmp_path):
        result = render_and_gate(CUSTOMER, [], tmp_path)

        assert result.readiness == "incomplete"
        assert result.readiness_findings != []

    def test_full_brief_is_ready_with_no_readiness_findings(self, tmp_path):
        events = [answer("q", "product", _ALL_REQUIRED_COVERED)]

        result = render_and_gate(CUSTOMER, events, tmp_path)

        assert result.status == "pass"
        assert result.readiness == "ready"
        assert result.readiness_findings == []

    def test_readiness_findings_are_not_mixed_into_linter_findings(self, tmp_path):
        result = render_and_gate(CUSTOMER, [], tmp_path)

        assert not set(result.readiness_findings) & set(result.findings)
```

Note: `render_and_gate(CUSTOMER, [], tmp_path)` — the empty transcript — is exactly the
finding's case. Assert its `status` in the first test only if the existing suite already
pins it; the point here is `readiness`, not the linter.

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_gate.py::TestReadinessOnGateResult -v`
Expected: FAIL with `AttributeError: 'GateResult' object has no attribute 'readiness'`.

- [ ] **Step 3: Implement**

In `src/discovery/gate.py`:

```python
from discovery.render import SessionHeaderLike, readiness, render_brief


@dataclass(frozen=True)
class GateResult:
    """The accepted (second-pass) outcome of `render_and_gate`."""

    status: str  # "pass" | "fail"
    findings: list[str]
    text: str
    readiness: str  # "ready" | "incomplete"
    readiness_findings: list[str]
```

and at the end of `render_and_gate`:

```python
    verdict = readiness(events, header.frame)
    return GateResult(
        status=status,
        findings=[str(f) for f in pass_2_findings],
        text=final_text,
        readiness=verdict.verdict,
        readiness_findings=verdict.findings,
    )
```

Extend the module docstring with one sentence: the §4 verdict travels on the same result as
the linter's, taken from `render.readiness`, so §7's two verdicts are computed once each and
never re-derived by the protocol layer.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/test_gate.py -v`
Expected: PASS.

- [ ] **Step 5: Full suite, lint, types**

Run: `uv run pytest && uv run ruff format --check . && uv run ruff check . && uv run pyrefly check`
Expected: all green. `tests/test_cli.py` may fail here only if it constructs `GateResult`
positionally — if so, update those call sites to keyword arguments in this task.

- [ ] **Step 6: Commit**

```bash
git add src/discovery/gate.py tests/test_gate.py
git commit -m "feat(gate): GateResult несёт вердикт §4 и его диагностики"
```

---

### Task 4: the third axis in the envelope, and exit `11`

**Files:**
- Modify: `src/discovery/protocol.py`
- Test: `tests/test_protocol.py`

**Interfaces:**
- Produces:
  - `Envelope` gains `readiness: str` and `readiness_findings: list[str]`;
    `to_json` emits seven keys in the §7 order: `lifecycle`, `gate`, `readiness`,
    `next_action`, `findings`, `readiness_findings`, `operation`.
  - `ok(lifecycle, gate, readiness, next_action=None, findings=None, readiness_findings=None)`
  - `refused(reason, lifecycle, gate, readiness, next_action=None, findings=None, readiness_findings=None)`
  - `unknown(detail)` — sets all three axes to `"unknown"`.
  - `exit_code` gains rank `11`.

  `readiness` is a **positional** parameter on `ok`/`refused`, directly after `gate`: a
  default would let a caller forget the axis and silently ship `ready`.

- [ ] **Step 1: Write the failing tests**

In `tests/test_protocol.py`:

```python
class TestReadinessAxis:
    def test_to_json_emits_the_seven_contract_keys_in_order(self):
        payload = json.loads(ok("complete", "pass", "ready").to_json())

        assert list(payload) == [
            "lifecycle",
            "gate",
            "readiness",
            "next_action",
            "findings",
            "readiness_findings",
            "operation",
        ]

    def test_unknown_collapses_all_three_axes(self):
        envelope = unknown("journal unreadable")

        assert envelope.lifecycle == "unknown"
        assert envelope.gate == "unknown"
        assert envelope.readiness == "unknown"
        assert envelope.readiness_findings == []

    def test_refusal_carries_the_readiness_axis_through(self):
        envelope = refused(
            ANSWER_CONFLICT,
            "complete",
            "pass",
            "incomplete",
            readiness_findings=["required topic 'goals' is not covered"],
        )

        assert envelope.readiness == "incomplete"
        assert exit_code(envelope) == 2


class TestExitCodePriority:
    def test_lint_valid_stub_is_11(self):
        assert exit_code(ok("complete", "pass", "incomplete")) == 11

    def test_ready_brief_is_0(self):
        assert exit_code(ok("complete", "pass", "ready")) == 0

    def test_gate_fail_outranks_incomplete_readiness(self):
        assert exit_code(ok("complete", "fail", "incomplete")) == 10

    def test_awaiting_input_outranks_incomplete_readiness(self):
        assert exit_code(ok("awaiting_input", "pass", "incomplete")) == 20

    def test_refusal_outranks_incomplete_readiness(self):
        assert exit_code(refused(ANSWER_CONFLICT, "complete", "pass", "incomplete")) == 2

    def test_unknown_readiness_is_1_even_when_the_other_axes_are_known(self):
        assert exit_code(ok("complete", "pass", "unknown")) == 1
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_protocol.py -v`
Expected: FAIL — `ok()` takes 2 positional arguments, `readiness` does not exist.

- [ ] **Step 3: Implement**

In `src/discovery/protocol.py`, add `readiness: str` and
`readiness_findings: list[str] = field(default_factory=list)` to `Envelope`, emit them in
`to_json` in the order above, thread the parameter through `ok` and `refused`, set
`readiness="unknown"` in `unknown()`, and extend `exit_code`:

```python
def exit_code(envelope: Envelope) -> int:
    """
    1  (highest) — operation.status == "unknown" OR any axis == "unknown"
    2            — operation.status == "refused"       (axes still readable)
    20           — lifecycle == "awaiting_input"        (even if gate == "fail")
    10           — lifecycle == "complete" and gate == "fail"
    11           — lifecycle == "complete", gate == "pass", readiness == "incomplete"
    0  (lowest)  — lifecycle == "complete", gate == "pass", readiness == "ready"
    """
    if (
        envelope.operation.get("status") == "unknown"
        or envelope.lifecycle == "unknown"
        or envelope.gate == "unknown"
        or envelope.readiness == "unknown"
    ):
        return 1
    if envelope.operation.get("status") == "refused":
        return 2
    if envelope.lifecycle == "awaiting_input":
        return 20
    if envelope.lifecycle == "complete" and envelope.gate == "fail":
        return 10
    if envelope.readiness == INCOMPLETE:
        return 11
    return 0
```

Compare against the literal `"incomplete"`, as `exit_code` already does for
`"awaiting_input"` / `"complete"` / `"unknown"`: in this codebase the axis vocabulary is
defined by the module that computes it (`lifecycle.AWAITING_INPUT`, and now
`render.READY` / `render.INCOMPLETE`), and `protocol` reads the wire values. Do **not**
import `render` into `protocol` — `protocol` is a leaf with no core dependencies, and
`tests/test_boundary.py` asserts things about the core's import graph.

Update the module docstring: three axes, priority `1 > 2 > 20 > 10 > 11 > 0`, and one
sentence on why `10` outranks `11` (a document that fails the linter may be failing GC-11
itself — its own claim about the very formula `readiness` projects).

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/test_protocol.py -v`
Expected: PASS.

- [ ] **Step 5: Full suite**

Run: `uv run pytest`
Expected: `tests/test_cli.py` and `tests/test_end_to_end.py` FAIL — they call `ok`/`refused`
without the new axis. That is Task 5; do not patch them here.

- [ ] **Step 6: Commit**

```bash
git add src/discovery/protocol.py tests/test_protocol.py
git commit -m "feat(protocol): третья ось readiness, readiness_findings и exit 11"
```

---

### Task 5: wire the CLI, and pin the finding as an end-to-end test

**Files:**
- Modify: `src/discovery/cli.py` (`_status_envelope`, `_refuse`, `cmd_brief`)
- Test: `tests/test_cli.py`, `tests/test_end_to_end.py`

**Interfaces:**
- Consumes: `GateResult.readiness` / `.readiness_findings` (Task 3),
  `protocol.ok` / `refused` (Task 4).
- Produces: no new names — every command emits the seven-key envelope.

- [ ] **Step 1: Write the failing test**

Rewrite the tail of
`tests/test_end_to_end.py::TestCustomerInterviewEndToEnd::test_full_customer_interview_reaches_complete_brief_and_gate_check`.
Its answer loop supplies `text:` only and no entries, so the brief it produces **is** the
lint-valid stub from the finding. Replace the deliberately weak final assertions
("gate: fail is an acceptable outcome here") with:

```python
        code, envelope = drive(["status", "--session", session_id], capsys)
        assert envelope["lifecycle"] == "complete"
        # The finding of 2026-08-19, pinned: every bank question was answered
        # and the linter has nothing to object to, yet the brief is a stub.
        # Before the readiness axis this returned exit 0.
        assert envelope["gate"] == "pass"
        assert envelope["readiness"] == "incomplete"
        assert code == 11
        assert any("goals" in f for f in envelope["readiness_findings"])
        assert envelope["findings"] == []

        out_path = tmp_path / "brief.md"
        code, envelope = drive(
            ["brief", "--session", session_id, "--out", str(out_path)], capsys
        )
        assert code == 11
        assert out_path.exists()

        findings = gate_check.check(
            out_path.read_text(encoding="utf-8"), base_dir=out_path.parent
        )
        assert isinstance(findings, list)
        assert all(f.level in {"error", "warning"} and f.message for f in findings)
```

And in `tests/test_cli.py`, two edits. First the module-level set every envelope case
checks against:

```python
ENVELOPE_KEYS = {
    "lifecycle",
    "gate",
    "readiness",
    "next_action",
    "findings",
    "readiness_findings",
    "operation",
}
```

Then, in
`TestAnswerConflict::test_conflicting_answer_without_supersede_is_refused`, add two
assertions next to the existing `envelope["gate"] != "unknown"` — a refusal reads state
successfully, so none of the three axes may collapse (§7):

```python
        assert envelope["readiness"] != "unknown"
        assert envelope["readiness_findings"] != []
```

`readiness_findings` is non-empty there because the session holds a single one-line answer:
the brief is a stub, and every required customer topic is uncovered.

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_end_to_end.py tests/test_cli.py -v`
Expected: FAIL — `TypeError` from `protocol.ok(...)` missing the third axis.

- [ ] **Step 3: Implement**

In `src/discovery/cli.py`, `_status_envelope`:

```python
    return protocol.ok(
        lifecycle,
        result.status,
        result.readiness,
        next_action,
        result.findings,
        result.readiness_findings,
    )
```

`_refuse` carries the axis from the envelope it already builds:

```python
    return protocol.refused(
        reason,
        envelope.lifecycle,
        envelope.gate,
        envelope.readiness,
        envelope.next_action,
        envelope.findings,
        envelope.readiness_findings,
    )
```

and `cmd_brief`:

```python
    return _emit(
        protocol.ok(
            lifecycle,
            result.status,
            result.readiness,
            next_action,
            result.findings,
            result.readiness_findings,
        )
    )
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest -v`
Expected: PASS, whole suite.

- [ ] **Step 5: Lint and types**

Run: `uv run ruff format --check . && uv run ruff check . && uv run pyrefly check`
Expected: all green.

- [ ] **Step 6: Commit**

```bash
git add src/discovery/cli.py tests/test_cli.py tests/test_end_to_end.py
git commit -m "feat(cli): readiness во всех четырёх командах; exit 11 закреплён e2e-тестом"
```

---

### Task 6: bookkeeping — close what landed, name what did not

**Files:**
- Modify: `TODO.md`
- Modify: `docs/evidence/2026-08-19-live-acceptance-run.md`

- [ ] **Step 1: Close the two finished items in `TODO.md`**

Mark `@id:gate-passed-not-projected` and `@id:traces-string-silently-wrong` as `[x]` with
the PR number, keeping their prose (the rule of this file: a closed line is never deleted,
because delta counters read a vanished line as "closed"). Add one line to each recording
what actually shipped — the `readiness` axis, `readiness_findings`, exit `11`, and the
type refusal on both the intake and the read side.

- [ ] **Step 2: Add the engineer-frame item**

Append to the runtime section of `TODO.md`, on one line with its tags:

```markdown
- [ ] Engineer-фрейм не может достичь `readiness: ready`: `feasibility_review` рантайм не выводит @owner:github:andrei-shtanakov @id:feasibility-review-not-derived
      В `FRAMES` у ключа префикс `None` («процесс, не секция»), а `render._coverage`
      считает `covered` только по наличию записей с префиксом — значит для engineer этот
      required-ключ всегда `missing` и `gate_passed` всегда `false`. Линтер трактует его
      иначе: GC-05(engineer) считает `feasibility_review: covered` законным заявлением и
      проверяет по делу — каждый Must-FR upstream-брифа упомянут по id в теле engineer-брифа.
      До этого правила рантайм зеркалит §4 не полностью. Проекция оси не создала провал, а
      сделала его видимым: он и сегодня лежит в `gate_passed: false`, но после exit 11
      engineer-прогон перестанет возвращать 0 когда бы то ни было. Чинить зеркалированием
      GC-05(engineer): резолвить upstream-бриф по `traces_to` от `base_dir` и считать ключ
      `covered`, когда каждый upstream Must-FR упомянут в теле.
```

- [ ] **Step 3: Note the outcome in the acceptance ledger**

In `docs/evidence/2026-08-19-live-acceptance-run.md`, under findings 1 and 2, add one line
each pointing at the PR that closed them. Do **not** rewrite the findings themselves: the
ledger records what the run saw on 2026-08-19, and rewriting history there destroys the only
account of how these were found.

- [ ] **Step 4: Commit**

```bash
git add TODO.md docs/evidence/2026-08-19-live-acceptance-run.md
git commit -m "docs: закрыть находки 1-2 приёмки, завести feasibility-review-not-derived"
```

- [ ] **Step 5: Open the pull request**

```bash
git push -u origin spec/readiness-axis
gh pr create --fill
```

Then read the GitHub Copilot review: fix valid remarks with new commits on the same branch,
answer invalid ones with reasoning, never apply blindly. Request the review explicitly if it
does not appear. **Do not merge** — a human merges.

---

## Out of scope

- **Deriving `feasibility_review` coverage** (Task 6 records it as
  `@id:feasibility-review-not-derived`). It needs upstream-brief resolution inside the
  render path and its own fixtures; folding it in here would mean shipping the axis and a
  new file-reading capability under one review.
- **Documenting the exit codes for callers** (`@id:exit-20-breaks-and`). The README says
  nothing about the CLI today; the table it needs now has six rows instead of five, so the
  item gets cheaper by waiting, not more expensive.
- **Re-issuing questions on `readiness: incomplete`** — rejected in the spec (§7), with the
  reasons recorded there. Not a backlog item.
