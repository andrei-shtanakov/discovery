# discovery runtime v1 — a pipeline-callable Need stage

Status: approved in discussion 2026-08-18 (owner: Andrei); this document is the
written record. Implementation plan: `docs/plans/` (written next, from this
document). What the runtime reads: `contract/` inside this repository — the
pinned copy of the brief contract v1.1 and `gate_check.py` (§4); no runtime path
ever resolves outside this repo. Upstream of that copy, as provenance only:
`discovery-toolkit`. Decision it descends from
`_cowork_output/decisions/2026-07-13-adr-discovery-interview-agent.md` in the
dev-only cowork workspace ("Где живёт", option B) — a document reference, not a
path this repo resolves.

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

**Deriving coverage for a process key.** A required key whose `FRAMES` prefix is
`None` has no section of its own, so no entry can ever evidence it. It is
`covered` when at least one bank question carrying that exact `coverage_key` has
a currently effective answer. A `question_asked` event alone is not enough:
asking is not answering.

The join uses the latest `question_asked` event and the latest `answer_recorded`
event for the same `question_id`. The coverage key comes exclusively from the
persisted `question_asked` event — never from the current bank, and never by
parsing the question id — so a bank re-pin cannot silently reclassify an
existing answer.

The rule is scoped to prefix-`None` keys and to nothing else. A prefix-backed key
stays entry-derived, and must never become closeable by the bare fact of an
answer without the record that answer was supposed to produce — that would be a
fail-open of exactly the kind this section's invariant exists to prevent.

`covered` does not assert that the feasibility review is substantively complete
or correct. It asserts only that a persisted question for that process key has a
currently effective answer. Whether the claim survives the upstream brief is
GC-05's question, and GC-12/GC-16's for the reference itself. The runtime states
the process fact; the vendored linter checks the substantive one; neither
reimplements the other.

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

**An answer arrives already typed.** The brief's body is not prose: `FR-01` carries a
`Priority` and an `Acceptance`, `FR` traces to a `G`/`J`, `M` traces to a `G`. Nothing
deterministic derives those from free text — that step is interpretation, and
interpretation is what the core excludes. So the payload of `answer` is a YAML document
with two parts: `text`, the verbatim answer kept for provenance and the L2 tests, and
`entries`, the typed contract entries. The interviewer — a person, or an agent running the
`discovery-interview` skill — does the interpreting; the runtime formats, counts and gates.
This is the same line the whole design draws: methodology upstream in the toolkit,
determinism here.

```yaml
text: |
  we lose orders when the courier app times out
entries:
  - id: G-01
    body: cut order loss from courier timeouts
  - id: FR-01
    body: retry a timed-out courier call
    traces: [G-01]
    Priority: Must
    Acceptance: a timed-out call is retried twice before the order is failed
```

`traces` is always a YAML list; a scalar is refused at intake, because a quoted
`'[J-02, G-01]'` cannot be told apart from a single id and the linter's body
parser recognises only the bracket form.

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
| `complete` | the source declares at least one question for the frame, every required topic is exhausted, **and** no issued question is unanswered |
| `unknown` | the journal cannot be read or parsed, **or** nothing is pending and the source declares no question at all for the frame |

**An empty source is `unknown`, not `complete`.** Read without the first clause,
the `complete` rule is satisfied before a single question has been asked
whenever the bank serves nothing: no required topic has an unissued question,
and nothing issued is unanswered. The D1 smoke run showed exactly that —
`lifecycle: complete` on a session whose transcript was empty. The runtime would
be asserting that a conversation is finished while holding no evidence that one
ever started, which is the same "report the unknown as a definite state" this
design refuses everywhere else: an unreachable upstream is `unknown` and never
`ok` (§4), and the gate axis keeps its own `unknown` rather than borrowing
`pass` (§7). So `complete` carries a precondition — the source must have
declared at least one question for the frame. A bank that cannot serve it —
unvendored, mis-pinned, or filtered to nothing — leaves the conversation axis
`unknown`, and the exit code says so.

`awaiting_input` still wins over an empty source, and the order of the three
rules is what makes that true. An issued question with no recorded answer is
evidence in the journal that a conversation is under way — evidence the bank
cannot take back by going empty between two calls. Only the `complete` branch
gains the precondition, because `complete` is the claim with nothing behind it.

`complete` does **not** imply `gate: pass`, and neither implies
`readiness: ready`. A conversation can end with thin answers that render empty
sections and fail GC-05, or with answers so thin that nothing renders, the
linter has nothing to object to, and the brief is still a stub — which is
exactly why the three axes never collapse into one (§7).

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
render(validation: pending) → check → render(validation: pass|fail) → check
```

The second pass re-renders **only** the verdict. It writes no diagnostics into
the document: the brief carries the data being checked and the `validation`
claim about it, and nothing else the runtime learned from checking. The
linter's findings belong to the run, not to the artifact, and they travel in
the envelope (§7) where the caller already reads them.

This is not a contract change. `DISCOVERY-BRIEF-CONTRACT.md` defines
`validation`; it never required an embedded diagnostics section. What is removed
is a non-normative runtime annotation, not a contract field, and the brief's
schema version does not move.

Only the second pass's result is accepted, and it is accepted only if the second
pass saw the same facts as the first:

**The accepted second-pass document contains no generated linter diagnostics,
and its findings must equal the first pass's real findings** — excluding only
the provisional GC-15 mismatch that `validation: pending` itself causes. The
comparison is between ordered lists of findings, not sets: a vanished duplicate
or a changed order is also a changed result, and normalising it away would hide
exactly what the invariant is watching for. Any difference means rendering the
verdict changed the facts being checked, and the operation fails closed —
`GateInvariantError`, which the CLI's boundary turns into
`operation.status: unknown` with all three axes `unknown` and exit `1`, rather
than a verdict derived from a document that moved under it.

Asserting equality rather than merely "no GC-15 in pass 2" is deliberate, and
the reason is a live incident. GC-05's engineer rule tests whether each upstream
Must-FR id appears anywhere in the brief — a substring scan over the whole
document. While the second pass embedded the first pass's findings, the finding
*"Must-FR FR-07 received no feasibility verdict"* put `FR-07` into the text, so
the second pass found nothing, GC-15 fired spuriously, and the caller received
`gate: fail` with the reason missing from `findings`. The document was
satisfying the check by quoting its own failure. A GC-15-only assertion cannot
see that; equality can, and it catches the next content-scanning rule without
knowing anything about it.

The invariant holds in all three shapes. Clean: pass 1 carries the provisional
GC-15 alone, pass 2 carries nothing, both real sets empty. Warning-only:
warnings survive unchanged and reach the envelope. Failing: pass 1's GC-05 is
still pass 2's GC-05, naming the same FR.

**Existing briefs.** A brief rendered before this rule that carries a
`## Gate findings` block cannot be treated as safely re-checkable by the
two-pass mechanism: its embedded text is part of what the linter scans. No such
artifact exists — the three briefs shipped to `dispatcher` are all
`validation: pass` with zero findings, and the block was only ever emitted for a
non-empty set — but the rule is stated for the case rather than for the count.
Should one appear, it is a legacy artifact: re-render it from its transcript,
never hand-edit it (§5).

The accepted result also carries the §4 readiness verdict and its diagnostics,
taken from the same public function that supplies the frontmatter's
`gate_passed` — never recomputed downstream, so the `readiness` axis of §7 and
the document it describes cannot drift apart.

## 7. Status protocol — three axes, one priority order

Every command returns the same envelope — including when it refuses:

```json
{
  "lifecycle": "awaiting_input | complete | unknown",
  "gate":      "pass | fail | unknown",
  "readiness": "ready | incomplete | unknown",
  "next_action": {},
  "findings": [],
  "readiness_findings": [],
  "operation": {
    "status": "ok | refused | unknown",
    "reason": "no_target_question | answer_conflict"
  }
}
```

`operation` describes the call; `lifecycle`, `gate` and `readiness` describe the
session. Each answers a different question, and none is derivable from the
others:

- `lifecycle` — is the conversation finished? A fold of the journal against the
  question source (§5).
- `gate` — does the linter accept the document? The mirror of the brief's own
  `validation` (§6): the document is well-formed and does not lie about itself.
- `readiness` — is the brief substantively complete? The §4 coverage-gate
  formula: every required key `covered` with a non-empty section, every FR
  traced to an existing G/J, zero blocking open questions.

**The engineer frame's `feasibility_review`.** The frame's one required key with
no id-prefix is not derivable from entries, and the runtime used to write
`missing` for it unconditionally. That made `readiness: ready` unreachable for
every engineer run and — less visibly — meant GC-05's engineer rule never ran at
all: it fires only when the brief claims `coverage.feasibility_review: covered`.
A key nobody claimed was a check nobody performed.

The runtime now derives it as §4 describes and states the claim. The division is
deliberate: the runtime proves the process fact it can prove from its own
journal, the frontmatter carries the claim, and the vendored linter tests that
claim against the upstream brief. `readiness` projects the same §4 formula as
before, without acquiring a second implementation of GC-05 — which would have
meant resolving `traces_to`, reading the upstream document and re-deriving its
Must-FR set alongside the linter that already does all three.

The cost is named: a thin answer to the feasibility topic now turns a completed
engineer run into `gate: fail`, exit `10`, with a finding naming the Must-FR
that received no verdict. That is not a new strictness of policy but the
activation of a check that already existed and had never run. And passing it is
not proof that each feasibility verdict is any good — only that the formalised
checks hold.

The axis is a projection, never a second implementation: `readiness` and the
frontmatter's `gate_passed` are one public function over the same events, so
the envelope cannot disagree with the document it describes.

`readiness` is deliberately not called `coverage`. `coverage` is already the
frontmatter's per-topic map, and the formula this axis projects also fails on an
untraced FR or a blocking open question — neither of which that map describes.

`gate` and `readiness` are independent in both directions. A brief with full
coverage fails the linter when an FR carries no `Priority` (GC-08). A brief of
three entries passes it: GC-04 requires the `coverage` keys to be present, not
to read `covered`, and GC-11 only requires the declared `gate_passed` to equal
the computed one — which it honestly does, at `false`. Before this axis existed
the second case returned `lifecycle: complete`, `gate: pass`, exit `0`, and no
caller could tell a finished brief from a stub. Found by the live acceptance run
(2026-08-19), not by any synthetic test: the existing tests reached
`lifecycle: complete`, but none distinguished a lint-valid stub from a
substantively ready brief.

A refusal does not blank the axes: at exit `2` the state was readable and left
unchanged, so all three carry the current computed values and the caller learns
both what it asked for and where the session stands. Only exit `1` may report
`unknown` axes.

| code | meaning | priority |
|---|---|---|
| `1` | an axis could not be determined (`lifecycle`, `gate` or `readiness` is `unknown`), or the call itself decided nothing (`operation.status: unknown`) | highest |
| `2` | refused precondition: no target question, or a conflicting answer without `--supersede`; state readable and **unchanged** | |
| `20` | `lifecycle: awaiting_input` (§5) | |
| `10` | `lifecycle: complete`, `gate: fail` | |
| `11` | `lifecycle: complete`, `gate: pass`, `readiness: incomplete` | |
| `0` | `lifecycle: complete`, `gate: pass`, `readiness: ready` | lowest |

Codes `0` / `10` / `11` / `20` project the axes; `1` and `2` are outcomes of the
call itself.

The priority is load-bearing: an incomplete transcript almost always also yields
linter findings, so without it the same transcript could return `20` on one call
and `10` on the next. `findings` are returned even at `20` — otherwise a person
cannot see that the brief is also defective, only that it is unfinished. `2` is
kept distinct from `1` because a refusal is a known state, and folding it into
"unknown" would make a retry look reasonable when it is not.

`10` outranks `11` because an invalid document is repaired before a thin one —
and because one of the rules that may have failed is GC-11 itself, the
document's own claim about the very formula `readiness` projects. A verdict
about completeness is only worth acting on once the document is known not to
lie. `findings` are returned at `11` as they are at `20`: a caller must be able
to see that a brief is both thin and, say, carrying a warning.

An incomplete verdict carries deterministic readiness diagnostics in
`readiness_findings`, identifying the failed clauses: uncovered required keys,
FRs without a trace to an existing G/J, and blocking open questions. They come
from the same public result that supplies `gate_passed` and `readiness`, and are
never reconstructed by the protocol layer. They stay in their own key rather
than joining `findings`: mixing linter errors with the reasons a brief is thin
would blur the very boundary between `gate` and `readiness` that this section
draws — and a lint-valid stub is precisely the case where `findings` is empty
while the brief is unusable.

`readiness` is reported at `20` as well, where `incomplete` is the expected
mid-interview value and carries no verdict about the finished brief.

The two triggers of `1` are not the same event, and the envelope keeps them
apart. An unreadable journal collapses **all three** axes and `operation` —
nothing about the session is known. An empty question source collapses only
`lifecycle`: the session was read, the call succeeded (`operation.status: ok`),
and `gate` and `readiness` are still computed from whatever the transcript
renders. Folding the second case into the first would throw away verdicts the
runtime actually holds, and the axes exist precisely so it does not have to.
`readiness` collapses to `unknown` exactly when `gate` does — both are derived
by the render/check pass over the journal, so no state can leave one known and
the other not.

`20` is the shape that makes the stage callable by a run: waiting is a state,
not a failure and not a command. Unreadable state is `unknown` (`lifecycle`
*and* exit `1`) and never renders as "nothing to wait for" — the tri-state rule
already established by dispatcher's `merged` / `created`.

**Rejected: automatically re-issuing questions on `readiness: incomplete`.**
When the bank is exhausted and the brief remains incomplete, the runtime reports
the failed readiness clauses and returns control; it does not manufacture
another pending question.

An incomplete verdict does not prove that asking a bank question again will
produce new evidence. The missing clause may be an uncovered required key, an
untraced FR, or a blocking open question, and those cases do not share a single
mechanically correct re-ask target. Even where a related bank question exists,
the runtime cannot distinguish a thin answer from a stakeholder who has no
further answer to give, so automatic re-asking has no terminating condition.

Waiting remains a state the runtime can prove: an issued question has no
recorded answer. Readiness remains a deterministic property of the derived
brief, but deciding whether its incompleteness warrants another conversation
belongs to the human caller. This keeps `lifecycle` a pure function of the
journal and question source as required by §5.

CLI surface, four commands, all emitting the status above on stdout. There is
no `--json` flag: the envelope is the only output shape, so a switch to select
it would be a switch with one position.

```
start  --frame {customer,engineer} --target <repo> [--traces-to <path>...]
status --session <id>
answer --session <id> [--question <id>] --role <participant_role> --file <payload.yaml>|- [--supersede]
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

`spec/tasks.md` in this repository holds the canonical backlog for **building
the runtime** (`TASK-NNN`, `Depends on:` references pointing only inside the
file), authored by us from the implementation plan. It is not in tension with
the author ≠ execute boundary of §8: that boundary says the *runtime program*
never writes `tasks.md` for a product it interviewed about. A repository
carrying the backlog of its own construction is the ordinary fleet pattern
(`kapelle/spec/tasks.md`), and nothing in the runtime reads or writes this file.
`project.yaml` describes the DAG:

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
`TASK-` entries reconciled against the number the spec declares; and the
**commit SHA of `pilot/runtime-v1` at launch**, written into the arc's evidence
file *before the first agent starts* — the file is opened at launch, not at the
end — so what the agents were told is a recorded fact rather than a
reconstruction. This is a different record from the live-acceptance ledger of
§12, which is written after a real interview.

One commit sha, not per-file hashes of the backlog and the plan. Those files sit
outside every workstream's scope, so an agent editing them is an out-of-scope
write that the scope gate catches and that git records permanently — with the
diff, which a hash comparison cannot give. Per-file hashes stay only where git
cannot stand in: the live-acceptance ledger (§12), whose artifacts are outside
version control at the moment they are hashed.

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
4. The interview reaches `lifecycle: complete`, `gate: pass`,
   `readiness: ready`, exit `0` — for the **customer** frame. The engineer
   frame cannot produce this outcome today (§7, known limitation).
5. The brief is written to the permitted `brief_path` in the target repo.
6. An independent invocation of the vendored gate confirms the clean result.
7. A ledger ties together session id, transcript SHA-256, brief SHA-256, and the
   commit / PR in the target repo. These two artifacts are the only ones the
   arc hashes, and this step is where it happens: at this moment both are
   outside version control — the journal lives under `$DISCOVERY_HOME` and the
   brief is not yet committed — so a hash is the only thing that ties the brief
   in the pull request to this session. Everything already in git is pinned by
   the launch commit SHA instead (§11).

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
