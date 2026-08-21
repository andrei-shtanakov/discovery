# L3 — interview quality benchmark

Status: approved in discussion 2026-08-21 (owner: Andrei); this document is the
written record. Implementation plan: `docs/plans/` (written next, from this
document). Closes the design half of `TODO.md` `@id:l3-quality-benchmark`, whose
`@trigger:"появился работающий runtime"` fired on 2026-08-19.

What this repository contributes: the static bank audit (§5) and one
observability item in `TODO.md` (§9). Everything that runs a language model —
simulator, reference caller, judge, matcher, annotator, harness, scenarios,
hidden specs, run logs — lives in `discovery-test`, a **local git repository
without a remote**, and no runtime path ever resolves into it.

Ancestry: `_cowork_output/plans/2026-07-13-discovery-agent-flow-and-test-strategy.md`
§3 (the L0→L3 pyramid), a dev-only document reference. Two of its assumptions no
longer hold and are corrected here — §2.

---

## 1. What the benchmark is for

It produces the baseline that decides `@id:phase-3-grounding`. Grounding
promises "do not ask what is already known" — a claim about coverage-recall,
interview length and cost. None of those are measured today, so the phase would
otherwise be designed before its problem is demonstrated and without a criterion
for improvement.

It is not a gate. v1 sets **no pass/fail threshold on any loop metric**. The one
regression threshold that does exist is the static leading-question baseline of
§5, which lives in CI and is deliberately cheap.

## 2. Two corrections to the 2026-07-13 plan

**The runtime does not interview.** `next_question` in
`src/discovery/lifecycle.py` is a deterministic sequencer over a vendored bank: a pending question is rebuilt from its own `question_asked` event, and
only the "nothing pending" branch consults `source.questions(frame)` for the
first unissued question. No model runs inside the runtime, and none can:
`tests/test_boundary.py` forbids network and process-launch imports anywhere in
`src/discovery/**`. So the plan's three metrics target three different
artifacts: leading-question rate is a property of the **bank**, anti-sycophancy
is a property of the **calling agent** (an `X-NN` reaches the brief only through
an answer payload's `entries`), and coverage-recall is split between the two.

**The shipped loop does not exist yet.** The neighbour's skill
(`discovery-toolkit/.claude/skills/discovery-interview/SKILL.md`, 142 lines)
conducts the interview and authors the brief itself; it never calls the runtime
CLI. Its single mention of the runtime explains why the bank carries machine
markers "for the bank's consumer". Two stages therefore ship today: the v0
skill-only path, in which the runtime plays no part, and the runtime path, whose
caller is documented in `README.md` but exists as no artifact.

Measuring the first would say nothing about the runtime. Asking the neighbour to
teach the skill to drive the CLI would make this item wait on
`discovery-toolkit`, which is the property the item was chosen for. So the
benchmark supplies its own caller (§3) and is explicit that it is a bench
artifact.

**Consequently the stand is versioned, not scratch.** The plan placed the run in
an untracked bench "like `spec-runner-test` / `agents-for-game`". Scratch cannot
carry a pinned methodology, a reproducible ground truth or a provable reference
caller — a single `rm -rf` and the denominators are gone. `discovery-test` is a
local git repository with no remote, the precedent being `spec-runner-tasks`. It
is not registered in the fleet manifest and is not presented as a shipped
project.

## 3. Boundaries and ownership

| Artifact | Where | Why there |
|---|---|---|
| Static bank audit | `tests/`, this repo | the bank is vendored here; a re-pin that worsens wording must fail CI, cheaply |
| Runtime invariants | `tests/`, this repo (existing) | not duplicated; extended only when a run finds something |
| Simulator, reference caller, judge, matcher, annotator, harness, scenarios, ground truth, run logs | the `discovery-test` stand | hidden specs and model logs do not leave the machine; pins are needed, publication is not |

The **reference caller** is a benchmark artifact, not a product one. It calls
only the public CLI contract (`start` / `status` / `answer` / `brief` and the
exit-code branching of `README.md`), it is never imported by the runtime, and it
does not weaken `tests/test_boundary.py`. `README.md` may reference it as a
worked integration example with that qualification stated. Promoting it to a
production interviewer is a separate decision about ownership and about
synchronisation with `discovery-toolkit`; this document does not take it.

Findings are attributed by the layer that reproduces them: runtime → an item
here; question wording, bank composition, methodology → a handoff issue in
`discovery-toolkit`; scenario, caller, judge, matcher → the stand.

## 4. Run architecture

Three roles, three processes, three contexts, and **no direct channel between
them**: the harness is the only place all three meet. It relays one utterance at
a time.

- **simulator** — `claude -p --model <selection>` with every tool disallowed.
  The hidden spec exists only in its system prompt and only in its process.
- **reference caller** — `claude -p --model <selection>`, `Bash` limited to the
  `discovery` executable, `cwd` and `--add-dir` limited to its own role
  directory, `$DISCOVERY_HOME` inside it.
- **judge** and **matcher** — `claude -p`, no tools, transcript in, verdict out,
  each with its own pinned prompt and model selection.

**Isolation is filesystem-level, not merely contextual.** `source/`, ground
truth, the simulator prompt and judge artifacts lie outside every path the
caller is allowed to read. Stakeholder text is never interpolated into a shell
command: the harness writes the payload to a file and the caller passes
`--file <path>`.

**Absence of tools is not absence of leakage.** A simulator can quote its hidden
spec verbatim in an ordinary reply. A deterministic leakage check compares each
simulator utterance against the hidden spec — a shared shingle of at least N
tokens, or structural disclosure (dumping the requirement list or its ids) — and
its parameters are pinned in the stand's `config.toml`. This document fixes the
method and the requirement that the parameters be pinned and versioned; the
implementation plan chooses the shingle length and enumerates the structural
forms, and changing either is a configuration change with its own SHA in the run
manifest. A detected leak marks the run `invalid_leak`. It never improves
recall.

**`--model` is a selection, not an immutable pin**, until the provider exposes a
finer revision. The manifest stores both the CLI argument and the `model`
identifier actually reported in `stream-json`, and the protocol calls it model
selection.

Repetitions: N = 5 per scenario in v1. Results are distributions — median and
spread — never a single score.

## 5. Layer A — static bank audit (this repository, CI)

Input is `parse_frame` in `src/discovery/bank.py` over the vendored frames: `Topic.coverage_key`,
`Topic.produces`, `Topic.questions`.

- **Potential coverage** — which required keys of a frame are claimed by which
  topics. The fail-closed completeness invariant already exists; this adds a
  **report**, not a second check.
- **Leading-question rate** — the share of leading formulations, computed by a
  **deterministic heuristic**, not a model: a CI test may not reach the network
  (the same boundary the core obeys) and must be reproducible. A baseline number
  is recorded in the repository; a re-pin that worsens it fails CI here rather
  than surfacing inside an expensive run.

The heuristic is not a judge. The stand's judge scores wording too and will
disagree; both numbers are published and neither is presented as the other.

## 6. Scenarios and ground truth

Three scenarios in v1:

- **S1 customer** — an external specification pinned by commit SHA, written
  neither by this methodology nor for this bank. Which document that is, the
  implementation plan decides; the criteria are fixed here: it predates this
  benchmark, it was not produced by a discovery interview, it is stable enough to
  pin by SHA, and it is long enough to carry requirements the bank does not ask
  for. The workspace's own product docs and ADRs satisfy all four and are read
  as a source, never resolved as a runtime path.
- **S2 engineer** — chained from S1 (§6.2).
- **S3 synthetic** — one job only: a seeded contradiction and whether an `X-NN`
  is raised.

Real `dispatcher` briefs are a historical baseline only, never a recall
denominator: they were produced by this same methodology, so whatever the bank
never asks is absent from them, and the denominator would silently shrink to the
numerator.

### 6.1 Annotation protocol

Layers, versioned separately: `source/` with the source SHA →
`annotation/human-draft.yaml` and `annotation/llm-draft.yaml` →
`annotation/adjudication.md` → `ground-truth.yaml`, the canonical denominator:
atomic requirements with an id, a type, a priority and an anchoring quotation
into the source.

The LLM annotator receives the pinned source and an extraction instruction and
**nothing else** — no bank, no methodology, no human draft, no loop output. An
annotator that has seen the bank extracts what the bank can ask, which is the
`dispatcher` poisoning through a different door.

The protocol calls this **human–LLM agreement**, not inter-human agreement. A
second human is not waited for. Two LLM annotators with different prompts may be
run as a diagnostic for prompt stability; that number never forms a denominator.
No recall threshold is set before the annotation is adjudicated.

### 6.2 The S2 chain and the approval fixture

`external source → customer loop → brief → derived approval fixture → engineer
loop --traces-to`.

The contract requires an upstream brief with `status: approved` (GC-12), so the
fixture is built, not asserted:

- the produced customer brief is stored unchanged;
- the harness creates a separate approved copy;
- the permitted diff is confined to approval metadata — `status`,
  `approved_by`, `approved_at`, `approver` — and nothing else: no `G`/`J`/`FR`,
  no coverage, no validation block;
- the manifest records both SHAs, the diff, the actor and the timestamp.

The contract calls these fields a mirror of git state. In the stand there is no
PR merge behind them, so the mirror reflects nothing: the manifest records the
fixture as a **synthetic approval by the harness actor**, never as evidence of
review.

If the customer loop produces no usable brief (`gate: fail` or
`readiness: incomplete`), S2 is recorded as `blocked_by_upstream_run` — not a
zero score and not a hand-written substitute input.

## 7. Metrics

Ground truth stays independent of the produced brief, and the two transitions
are **never summed into one recall**: a requirement lost at T1 and a Must-FR
left without a verdict at T2 are different defects with different owners.

| Metric | Transition | Computed by | Denominator |
|---|---|---|---|
| extraction-recall | source → customer brief | matcher, mapping `GT-id → entry-id` with an evidence quotation | canonical ground truth |
| invention-rate | same | matcher classification (§7.1) | brief entries |
| feasibility-coverage | approved customer brief → engineer brief | the **vendored linter's** GC-05(engineer) id set, projected to a ratio | upstream Must-FRs |
| traceability | same | linter: `traces` resolve | engineer-brief FRs |
| contradiction-recall | S3 | `X-NN` with `status: open` — deterministic; whether it is the seeded contradiction — judge | seeded contradictions |
| length and cost | all | utterances, questions issued, tokens per role, wall time | — |

GC-05(engineer) remains the **normative** pass/fail check and the source of
findings: each upstream Must-FR (`prefix == FR`, `priority == Must`) must be
mentioned by id in the engineer brief's body. The harness only projects that
same id set into a ratio — mentioned Must-FRs over all upstream Must-FRs — and
never redefines the rule.

### 7.1 Matcher classes

The matcher returns three classes, not two: **supported**, **unsupported**,
**ambiguous**. `ambiguous` is published separately and is never counted as
invention automatically — an incomplete canonical ground truth would otherwise
become a false accusation against the model.

### 7.2 Validity metrics

Unsuccessful runs are excluded from the metric distributions but **published as
rates of their own**: `valid_run_rate`, `invalid_leak_rate`,
`harness_error_rate`, and for S2 `upstream_completion_rate`. Without them, a
caller that frequently leaks the spec or fails to produce a customer brief would
improve the headline numbers by having its bad runs discarded.

### 7.3 The judge does not set truth alone

The first run includes human labelling of a sample, covering both the source
annotation and the `GT-id → entry-id` matching — the second is no less
contestable than the first — and reports human–LLM agreement for both, plus the
sensitivity of the result to the disputed requirements. No automatic pass/fail
threshold is derived from the judge in v1.

## 8. Artifacts and reproducibility

```
discovery-test/
  prompts/{simulator,caller,judge,matcher,annotator}.md
  PINNED.txt                      # discovery-toolkit methodology @ sha
  config.toml                     # leakage shingle N, structural-disclosure rules, N repetitions
  scenarios/S1-customer/{source/, annotation/{human-draft,llm-draft}.yaml,
                        adjudication.md, ground-truth.yaml}
  runs/<ULID>/{run-manifest.json, roles/*/stream.jsonl,
               artifacts/{brief.md, approved/brief.md}, metrics.json}
```

`run-manifest.json` carries every effective input by SHA: `claude --version`,
each role's model selection (argument **and** reported identifier), prompt SHAs,
methodology pin, `discovery` revision and `src/discovery/contract/PINNED.txt`, scenario and
ground-truth SHAs, harness revision, token and call counters, and paths to the
full `stream-json` of every role. Money is not stored: tokens and calls are, and
a separately pinned price table converts them.

Run states: `ok`, `invalid_leak`, `blocked_by_upstream_run`, `harness_error`.
The last three are retained in full.

## 9. The observability item

A stand without a remote and without CI goes stale silently, so `TODO.md` gets
one item with an `@owner:`, the command that reads the stand's last commit and
its newest `run-manifest.json`, and a freshness criterion computed **by SHA over
every effective input of the manifest** — bank/contract pin, caller, simulator,
matcher and judge prompts, methodology pin, scenario, ground truth, harness
revision, model selections. Any mismatch means "no run exists for the current
configuration"; a date proves nothing. The item's `@trigger:` names changes to
those inputs, not only to the bank and the caller.

## 10. Not in v1

Thresholds or a regression gate on loop metrics (the static leading-question
baseline of §5 is the only regression threshold, and it is in CI); CI for the
stand; ATP and any neighbour's `.env`; an API backend for the harness — possible
later, never a precondition for starting L3; model comparison; a fourth
scenario; and measuring grounding itself, since phase 3 is this baseline's
**consumer**, not part of it.
