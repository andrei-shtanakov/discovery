# discovery runtime v1 — a pipeline-callable Need stage

Status: approved in discussion 2026-08-18 (owner: Andrei); this document is the
written record. Implementation plan: `docs/plans/` (written next, from this
document). Canon it consumes: `../discovery-toolkit/DISCOVERY-BRIEF-CONTRACT.md`
v1.1 and `gate_check.py` (vendored, §4). Decision it descends from:
`../_cowork_output/decisions/2026-07-13-adr-discovery-interview-agent.md`
("Где живёт", option B).

---

## 1. Why now — the start decision

`TODO.md` carried one blocking item, `start-decision`: fill the runtime, or park
the repo until the trigger fires. The ADR permits a separate repo only when the
contract is stable **and** state / multi-user / UI are needed. The first
condition has held since 2026-07-14; the second was never met — both live
interviews ran through the `discovery-interview` skill and neither hit the
absence of a runtime.

The trigger that actually fires is a different one, and naming it honestly is
what keeps this scope small:

> **The Need stage must be callable by a run, and it needs state precisely
> because the stage must be able to wait for a human.**

Multi-user and a web UI are **not** the reason and are out of scope (§2). A
stakeholder-agent that would let a run complete the stage unattended is also out
of scope: it belongs to the L3 interview-quality benchmark, which has its own
trigger (`todo://discovery/l3-quality-benchmark`), and as a default it would
turn discovery into self-interrogation.

Mode and authority for the implementation arc (ADR-ECO-007): mode
`ecosystem-development`, `write_scope = {discovery}`. The target repository —
where a brief eventually lands — enters `write_scope` only for runs that *use*
the stage, never for this arc.

## 2. Scope

**In:** session state that survives process exit; a status protocol a run can
read; deterministic assembly of a `discovery-brief` from a transcript; the
vendored contract and linter with their two guarantees; a CLI; the author ≠
execute boundary enforced by tests.

**Out:** multi-user sessions; web or HTTP surface; MCP server; the
stakeholder-agent; any downstream compilation (`tasks.md`, design, execution
plans) — that boundary is the ADR's, not a v1 simplification; opening the PR
that carries the brief (the run driver does that, §8).

## 3. Approach — deterministic core plus one port

The core holds state, computes what coverage is still missing, renders the
brief, and runs the gate. It never calls a model. Adaptivity lives behind a
single port, `QuestionSource`, with two implementations:

- `bank` — questions from the vendored frame profile. The only implementation
  enabled in v1.
- `llm` — interface and test fake only in v1; a later implementation is a
  plug-in, not a rewrite of the core.

Rejected: a full agent harness inside the runtime. It would put the
methodology in two places — the toolkit's skill files and this repo's code —
and the two would drift. Same shape as ADR-ECO-007 D1's rule about not building
two git mechanisms: what has to be built twice marks a boundary drawn wrong.

## 4. Vendored surface and its two guarantees

`discovery-toolkit` is deliberately not a package (`pyproject.toml`,
`[tool.uv] package = false`), so a dependency would have to invent a release
surface it does not have. `CLAUDE.md` already requires the alternative: a
pinned copy inside this repo.

Vendored into `contract/`:

- `DISCOVERY-BRIEF-CONTRACT.md` — the canon of the output artifact.
- `gate_check.py` — rules GC-01…GC-16, and `FRAMES`: the executable form of the
  required coverage keys per frame (§4 of the contract).
- `frames/customer.md`, `frames/engineer.md` — the question bank for
  `QuestionSource.bank`.
- `PINNED.txt` — upstream repo, commit, and the vendored paths.

**Two guarantees, neither substituting for the other:**

| | what it proves | where it runs |
|---|---|---|
| copy-integrity | the vendored bytes are the bytes of the upstream tree **at the commit in `PINNED.txt`** | PR gate |
| upstream-drift | the pin has not fallen behind upstream | scheduled workflow |

A test that compares the copy against a stored checksum proves the copy's
internal consistency, not its provenance — so copy-integrity resolves the
upstream tree at the pinned commit. Upstream unreachable ⇒ `unknown`, never
`pass`; a missing or stale scheduled run is likewise `unknown`. Both are
CI-side; the runtime performs neither check and never reads the sibling
directory.

**Joining questions to coverage keys.** A topic's coverage key cannot be derived
from the ID prefix in its heading — not inconveniently, but by construction:
`X-NN` / `Q-NN` are cross-cutting (produced by `### 6. Feasibility-проход …` in
engineer and `### Завершение (всегда)` in customer), and `feasibility_review` is
a required engineer key whose prefix in `FRAMES` is deliberately `None`
("процесс, не секция"). The runtime therefore reads an explicit machine marker
per topic, requested upstream in `discovery-toolkit#4`. Until that lands, WS-A2
is blocked (§10); no heading heuristic and no second `topic → key` table are
introduced on this side.

**Fail-closed invariant over the bank**, stated in the direction that catches
loss: every required key of a frame is claimed by at least one topic marker, and
where the key's prefix in `FRAMES` is not `None`, the topic's `produces`
contains it. Violation is an error, not a warning — a bank incomplete relative
to the coverage gate makes `gate_passed` unreachable, and silence about that
reproduces the class of defect where a green gate sits over an unread source.

## 5. State — the transcript is the source of truth

A session is an append-only JSONL transcript plus a header (`frame`, target
repo, `traces_to`, and for the engineer frame the upstream customer brief). Each
record: timestamp, `coverage_key`, `participant_role`, question id, answer text.

The brief is **derived**: re-rendered from the transcript, never edited in
place. Three consequences pay for the choice — resume is a recomputation of
`coverage` over the current transcript; the L2 `transcript → brief` tests get
their frozen input for free; and `coverage` / counters / `gate_passed` /
`validation` cannot drift from the body (GC-10, GC-11, GC-15), because nothing
writes them by hand.

**Durability is promised explicitly**, because suspend/resume across processes
is the whole point and a lost final answer would be silent data loss:

- appends take a file lock, write one complete JSONL line with `O_APPEND`, then
  `flush` + `fsync`;
- the brief is written to a temporary file in the same directory and moved into
  place with an atomic replace.

"Append-only" alone guarantees neither: two processes or a crash mid-write can
still corrupt the file.

Hashes recorded for provenance are SHA-256 (`*_sha256`, the fleet convention).

## 6. Render → gate — the two-pass rule

GC-15 requires `validation: pass` exactly when no other error exists, so a
single pass would either manufacture a GC-15 finding or force the runtime to
predict the linter. The order is fixed:

```
render(validation: pending) → check → render(validation: pass|fail + findings summary) → check
```

Only the second pass's result is accepted, and a dedicated assertion holds that
the second pass is clean with respect to GC-15. The runtime mirrors the linter;
it never anticipates it.

## 7. Status protocol — two axes, one priority order

```json
{
  "lifecycle": "awaiting_input | complete | unknown",
  "gate":      "pass | fail | unknown",
  "next_action": {},
  "findings": []
}
```

Exit codes are a projection of the two axes with a strict priority:

| code | meaning | priority |
|---|---|---|
| `1` | state or tool unknown | highest |
| `20` | session valid, human input needed (`awaiting_input`) | |
| `10` | input complete enough to judge, gate `fail` | |
| `0` | gate `pass` | lowest |

The priority is load-bearing: an incomplete transcript almost always also yields
linter findings, so without it the same transcript could return `20` on one call
and `10` on the next. `findings` are returned even at `20` — otherwise a person
cannot see that the brief is also defective, only that it is unfinished.

`20` is the shape that makes the stage callable by a run: waiting is a state,
not a failure and not a command. Unreadable state is `unknown` (`lifecycle`
*and* exit `1`) and never renders as "nothing to wait for" — the tri-state rule
already established by dispatcher's `merged` / `created`.

CLI surface, four commands, all emitting the status above:

```
start  --frame {customer,engineer} --target <repo> [--traces-to <path>...]
status --session <id> [--json]
answer --session <id> --key <coverage_key> --role <participant_role> --file <path>|-
brief  --session <id> --out <brief_path>
```

## 8. Boundary — author ≠ execute, as a capability

The runtime authors a brief and stops. It does not write `tasks.md`, design, or
execution plans, and it does not open the pull request that carries the brief —
that is execute, and it belongs to whoever drives the run. Approval of the brief
follows the frame's `owner_role` (`product` for customer, `architect` for
engineer).

Enforced as a capability, not by string search: writes are permitted only under
the session root and to the single `brief_path` passed in, and the core's
dependency graph contains no network or process-launch adapter. Grepping for
`tasks.md` / `design` would be brittle and would create false confidence.

## 9. Test pyramid

**L0 — the copy contract.** copy-integrity against the upstream tree at the
pinned commit; the fail-closed bank invariant (§4); and a negative test on the
instrument itself: agreement with a locally stored checksum must not be accepted
as evidence of provenance.

**L1 — the deterministic core.** Frozen transcript → assertions on `coverage`,
counters and `gate_passed` per the contract's §4 formula; the two-pass GC-15
rule; the exit-code priority table exercised across all four outcomes; the
tri-state rule for unreadable state. `QuestionSource` is a fake throughout; no
model participates at any level of this suite.

**L2 — `transcript → brief`.** Assertions on properties of the brief, not on its
text. Synthetic transcripts to start; real frozen ones arrive from live runs and
close `todo://discovery/l2-transcript-brief-tests`, which this arc does not
claim.

**Errors.** Unreadable state ⇒ `lifecycle: unknown` + exit `1`. A missing
upstream customer brief in the engineer frame is GC-12 in the linter, not local
logic. A crash or timeout must not leave a half-written record (lock + whole-line
append + fsync, §5).

## 10. Workstreams and dependencies

| WS | content | depends on |
|---|---|---|
| A1 | vendored contract + linter + `PINNED.txt` + both guarantees | — |
| A2 | vendored bank + marker parsing + fail-closed invariant | A1, `discovery-toolkit#4` |
| B | session (locked append-only JSONL, fsync) + render | A1 |
| C | gate wrapper + status protocol + exit-code priority | A1 |
| D | CLI + capability tests for the boundary | B, C, A2 |

B and C are the parallel pair, hence `max_concurrent: 2`. D depends on A2 as
well: a CLI that cannot ask the next question is not the CLI, so blocking it
whole is more honest than shipping half.

Two items require neighbouring repos and therefore travel as handoffs, not as
our edits: the bank markers (`discovery-toolkit#4`, filed) and registration in
`workspace-manifest.toml` (`ai-orchestrators-workspace`).

## 11. The orchestrated run

`spec/tasks.md` holds the canonical backlog (`TASK-NNN`, `Depends on:`
references pointing only inside the file). `project.yaml` describes the DAG:

```yaml
repo_path: ~/labs/all_ai_orchestrators/discovery
workspace_base: ~/labs/all_ai_orchestrators/discovery-maestro-ws
base_branch: pilot/runtime-v1      # integration branch; master is never touched
branch_prefix: "ws/"
auto_pr: false
max_concurrent: 2
spec_runner:
  claude_model: sonnet             # fixed: a varying model makes results unattributable
  max_retries: 2
  task_timeout_minutes: 30
  test_command: "uv run pytest"
  run_tests_on_done: true
  lint_command: "uv run ruff check . && uv run ruff format --check ."
  run_lint_on_done: true
  extra_executor_config:           # fields SpecRunnerConfig does not mirror
    execution_mode: tdd
    tdd_runner: pytest
```

**Blocking checks before the first agent** (all fail-closed): repository
identity and baseline; `git config --local core.worktree` empty; `spec-runner
run --all --dry-run` reporting zero validation errors; the count of recognised
`TASK-` entries reconciled against the number the spec declares; the spec's
SHA-256 recorded before the run, so a retry has something to compare against.
The repo's governance-gate caller is wired here — its trigger ("code or CI
appeared in the repo") fires with this arc.

The human gate is the final PR `pilot/runtime-v1 → master`. A `NEEDS_REVIEW`
verdict is approved only by consensus of the Claude and Codex critics;
otherwise it escalates to the owner.

## 12. Definition of Done

Implementation green is not the finish line: without one live call the suite
would cover the core but not the property the arc exists for — that a run can
call the stage. The live evidence, in order:

1. `start` returns `awaiting_input`, exit `20`.
2. The process exits; state survives.
3. A **new** process runs `status`, then `answer`.
4. The interview reaches `lifecycle: complete`, `gate: pass`, exit `0`.
5. The brief is written to the permitted `brief_path` in the target repo.
6. An independent invocation of the vendored gate confirms the clean result.
7. A ledger ties together session id, transcript SHA-256, brief SHA-256, and the
   commit / PR in the target repo.

**Honesty rule for the arc's status.** With no stakeholder available the status
is `implementation complete, live acceptance pending` — never `accepted`. An
interview with the owner in the product-stakeholder role does qualify: the
interviewer and stakeholder roles are genuinely separate. A solo run does not
substitute for it; the solo frame needs its own mini-profile, still an open
question in `TODO.md`.

## 13. Risks

- **The bank's format is not yet a contract.** Until `discovery-toolkit#4`
  lands, marker parsing is a guess about someone else's format; A2 stays blocked
  rather than shipping a heuristic.
- **The vendored copy ages.** Mitigated by the two guarantees, whose failure
  mode is `unknown` rather than green.
- **`bank` questions do not adapt** to a specific answer; interview quality
  stays with the skill's method. Accepted for v1 — the `llm` implementation of
  the port is the answer if observation ever demands it.
- **First non-bypass maestro run.** The reasons orchestration was suspended for
  the disputatio wave (maestro#164, #165, #166) are closed, but this is the
  first arc to rely on that. How maestro behaved is a separate line in the
  acceptance report, not an impression.
