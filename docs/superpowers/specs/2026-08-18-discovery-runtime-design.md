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
where a brief eventually lands — is outside that scope; the one run that must
write there, the live acceptance run, declares its own expanded scope
beforehand and does not extend it to anything else (§12).

## 2. Scope

**In:** session state that survives process exit; a status protocol a run can
read; deterministic assembly of a `discovery-brief` from the session journal; the
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

Vendored into `contract/`, and the surface arrives in two instalments — A1 does
not provide all of it:

| artifact | what it carries | lands in |
|---|---|---|
| `DISCOVERY-BRIEF-CONTRACT.md` | the canon of the output artifact | A1 |
| `gate_check.py` | rules GC-01…GC-16 and `FRAMES` — the executable form of the required coverage keys per frame (contract §4) | A1 |
| `PINNED.txt` | upstream repo, commit, vendored paths | A1 |
| `frames/customer.md`, `frames/engineer.md` | the question bank for `QuestionSource.bank` | A2, after `discovery-toolkit#4` |

**Two guarantees, neither substituting for the other:**

| | what it proves | where it runs |
|---|---|---|
| copy-integrity | the vendored bytes are the bytes of the upstream tree **at the commit in `PINNED.txt`** | PR gate |
| upstream-drift | the pin has not fallen behind upstream | scheduled workflow |

A test that compares the copy against a stored checksum proves the copy's
internal consistency, not its provenance — so copy-integrity resolves the
upstream tree at the pinned commit. Upstream unreachable ⇒ `unknown`, never
`pass`. The drift watch carries an explicit expiry: no successful run in the
last **8 days** ⇒ `unknown`. On a weekly schedule that means **the first missed
slot already turns the state unknown** — stated plainly rather than dressed up
as tolerance, because the threshold is chosen fail-closed: a watch whose silence
is indistinguishable from a clean result is the defect it exists to prevent.
Both checks are CI-side; the runtime performs neither and never reads the
sibling directory.

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

## 5. State — the transcript is an event journal

A session is an append-only JSONL journal plus a header (`frame`, target repo,
`traces_to`, the upstream customer brief for the engineer frame, and the
`question_source` pin — the vendored bank's upstream commit). It records
**events, not answers only** — otherwise suspend/resume works for the file and
not for the conversation:

```json
{"event":"question_asked","question_id":"customer.goals.01","coverage_key":"goals","question_text":"…","source_pin":"…","ts":"…"}
{"event":"answer_recorded","question_id":"customer.goals.01","answer_id":"sha256:…","participant_role":"product","text":"…","ts":"…"}
{"event":"answer_superseded","question_id":"customer.goals.01","from":"sha256:…","to":"sha256:…","ts":"…"}
{"event":"source_pin_changed","from":"…","to":"…","ts":"…"}
```

**A session survives a bank update.** `question_asked` stores the question's
actual text and the pin it came from, and `next_action` is reconstructed **from
the journal**, never by re-resolving a stored id against the current bank.
Without this, a re-pin between `start` and resume would silently change what a
question id means — or drop it — and the answer already recorded against it
would attach to a different question. A pin that differs from the header's at
the next call is appended as `source_pin_changed`, so a brief assembled across
two bank versions can say so instead of looking uniform.

**Issuance is recorded before the command returns.** `start` / `status` persist
`question_asked` and only then emit `next_action`. A crash in the other order
would let a re-run ask a different question, leaving the arriving answer
unattributable.

**Answers target a question, not a key.** `answer` takes `--question <id>`; with
it omitted the target is `next_action.question_id`, and the command refuses if
that is unset. Answering an open question that is not the current one is
allowed — real interviews jump around, and the bank is a checklist, not a
railway.

**Idempotency and conflict.** `answer_id` is the SHA-256 of
(`session_id`, `question_id`, `participant_role`, canonical answer bytes), the
four fields NUL-separated so no concatenation can be read two ways. The
canonical form is fixed rather than "normalised": UTF-8 bytes with `CRLF` and
`CR` folded to `LF`, and **no** trimming or other transformation of the content.
`participant_role` is part of the identity because the same words from a
different role are a different fact — without it, an answer whose attribution
changed would be swallowed as a no-op. Replaying the same
`answer_id` — the ordinary case after a transport timeout — is a no-op that
returns the same status. A *different* answer to a question that already has one
is refused unless `--supersede` is passed; with it, both
`answer_superseded` and the new `answer_recorded` are appended, render uses the
latest, and the journal keeps the history. Silent overwrite is the one behaviour
excluded: it would make the transcript unable to explain its own brief.

**Lifecycle is a function of the journal**, and it is about the conversation,
never about the artifact:

| state | rule |
|---|---|
| `awaiting_input` | some required topic of the frame still has an unissued question, **or** some issued question has no recorded answer |
| `complete` | every required topic of the frame is exhausted **and** no issued question is unanswered |
| `unknown` | the journal cannot be read or parsed |

`complete` does **not** imply `gate: pass`. A conversation can end with thin
answers that render empty sections and fail GC-05 — which is exactly why the two
axes never collapse into one (§7).

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
- the brief is written to a temporary file in the same directory, moved into
  place with `os.replace`, and the containing **directory** is fsynced
  afterwards — without that the rename itself can be lost on power failure,
  which is inside the durability we promise.

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

Every command returns the same envelope — including when it refuses:

```json
{
  "lifecycle": "awaiting_input | complete | unknown",
  "gate":      "pass | fail | unknown",
  "next_action": {},
  "findings": [],
  "operation": {
    "status": "ok | refused | unknown",
    "reason": "no_target_question | answer_conflict"
  }
}
```

`operation` describes the call; `lifecycle` and `gate` describe the session. A
refusal does not blank them: at exit `2` the state was readable and left
unchanged, so the axes carry the current computed values and the caller learns
both what it asked for and where the session stands. Only exit `1` may report
`unknown` axes.

| code | meaning | priority |
|---|---|---|
| `1` | state or tool unknown — nothing was decided (`operation.status: unknown`) | highest |
| `2` | refused precondition: no target question, or a conflicting answer without `--supersede`; state readable and **unchanged** | |
| `20` | `lifecycle: awaiting_input` (§5) | |
| `10` | `lifecycle: complete`, `gate: fail` | |
| `0` | `lifecycle: complete`, `gate: pass` | lowest |

Codes `0` / `10` / `20` project the two axes; `1` and `2` are outcomes of the
call itself.

The priority is load-bearing: an incomplete transcript almost always also yields
linter findings, so without it the same transcript could return `20` on one call
and `10` on the next. `findings` are returned even at `20` — otherwise a person
cannot see that the brief is also defective, only that it is unfinished. `2` is
kept distinct from `1` because a refusal is a known state, and folding it into
"unknown" would make a retry look reasonable when it is not.

`20` is the shape that makes the stage callable by a run: waiting is a state,
not a failure and not a command. Unreadable state is `unknown` (`lifecycle`
*and* exit `1`) and never renders as "nothing to wait for" — the tri-state rule
already established by dispatcher's `merged` / `created`.

CLI surface, four commands, all emitting the status above:

```
start  --frame {customer,engineer} --target <repo> [--traces-to <path>...]
status --session <id> [--json]
answer --session <id> [--question <id>] --role <participant_role> --file <path>|- [--supersede]
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

**L1 — the deterministic core.** Frozen journal → assertions on `coverage`,
counters and `gate_passed` per the contract's §4 formula; the two-pass GC-15
rule; the exit-code table exercised across every outcome; the tri-state rule for
unreadable state. The protocol invariants of §5 are tested as such: issuance is
persisted before the command returns (kill between the two must not lose
attribution); replaying an `answer_id` is a no-op, while the same text under a
different `participant_role` is a distinct answer, not a replay; a conflicting
answer without `--supersede` is refused with the state unchanged **and** with
the axes still populated; with `--supersede` both events survive and render uses
the latest; `complete` is reached exactly by the rule, including the case
`complete` + `gate: fail`. One test re-pins the vendored bank mid-session and
asserts that resume still reproduces the issued questions from the journal —
the failure mode it guards is an id silently changing meaning. `QuestionSource` is a fake
throughout; no model participates at any level of this suite.

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
| B | session journal (locked append-only JSONL, fsync) + render | A1 |
| C | gate wrapper + status protocol + exit-code priority | A1 |
| D1 | CLI transport and state contract: commands, status JSON, capability boundary — against a fake `QuestionSource` | B, C |
| D2 | `QuestionSource.bank`, the full interview flow, live acceptance | A2, D1 |

B and C are the parallel pair, hence `max_concurrent: 2`. The D split keeps the
external dependency off the critical path without pretending half a CLI is a
deliverable: D1 fixes the transport and state contract and is fully testable
with a fake source, D2 makes it usable. runtime-v1 is not accepted without D2
and the live run (§12).

Two items require neighbouring repos and therefore travel as handoffs, not as
our edits: the bank markers (`discovery-toolkit#4`, filed) and registration in
`workspace-manifest.toml` (`ai-orchestrators-workspace`).

## 11. The orchestrated run

`spec/tasks.md` holds the canonical backlog (`TASK-NNN`, `Depends on:`
references pointing only inside the file). `project.yaml` describes the DAG:

```yaml
# workstreams are omitted here — they are generated from the implementation plan
project: discovery-runtime-v1
repo_url: https://github.com/andrei-shtanakov/discovery
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
  extra_executor_config:           # overlay onto the whole executor.config.yaml
    executor:                      # …so non-mirrored fields must sit under `executor:`
      execution_mode: tdd
      tdd_runner: pytest
```

`project` and `repo_url` are required by `OrchestratorConfig`. The overlay is
deep-merged onto the document produced by `to_executor_config()`, which nests
everything under an `executor` key — an overlay written at top level would
create keys spec-runner never reads.

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
call the stage.

**Precondition — a recorded authority expansion.** The implementation arc runs
with `write_scope = {discovery}`, but the evidence run writes a brief into the
target repository. That expansion is declared and recorded for the acceptance
run specifically (`write_scope = {discovery, <target>}`), before it starts, and
it does not carry over to any later run. An acceptance run that quietly wrote
outside the arc's declared scope would violate the very rule this design cites
as its authority model (ADR-ECO-007 D2).

The live evidence, in order:

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
