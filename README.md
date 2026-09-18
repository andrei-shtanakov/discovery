# discovery

Runtime for the discovery/elicitation stage: it conducts a structured
stakeholder interview and authors a `discovery-brief` that governance gates
consume (BR/FRD in the customer frame, 0b/0a in the engineer frame).

`discovery-toolkit` owns the methodology, the question bank, and the
`DISCOVERY-BRIEF-CONTRACT.md`; this repo runs them. The contract, the linter
(`gate_check.py`) and the frames are **vendored** here as a pinned copy under
`src/discovery/contract/` — the runtime resolves no path outside this
repository. Two checks keep the copy honest: copy-integrity against the
upstream tree at the pinned commit, and a scheduled upstream-drift check. An
unreachable upstream reports `unknown`, never `pass`.

**The boundary is authoring-only.** `discovery` produces a brief for review and
stops. It does not write `tasks.md`, design documents, or execution plans, and
it does not open the pull request that carries the brief — that is *execute*,
and it belongs to whoever drives the run. The boundary is enforced as a
capability, not by string search: writes are permitted only under the session
root and to the single `--out` path, and the core's import graph contains no
network or process-launch adapter.

## Using it

```
discovery start  --frame {customer,engineer} --target <repo> [--traces-to <path>]...
                 [--upstream <customer_brief>] [--session-id <id>]
discovery status --session <id>
discovery answer --session <id> [--question <id>] --role <role> --file <path> [--supersede]
discovery brief  --session <id> --out <brief_path>
```

`--file -` reads the payload from stdin. Omitting `--question` answers whichever
question the session is currently waiting on.

`--session-id` assigns the session's id instead of letting `start` generate one,
which is what lets an orchestrating caller write the id down **before** the call
and never end up with a session it cannot name afterwards. The id is validated
the same way `--session` is, and an id that is already taken is refused with the
existing session untouched — it is never reused or overwritten.

An entry id may be declared again in a **later** answer: that is an explicit new
version and replaces the earlier one whole — no field merging, so a version that
dropped `Priority` or `traces` is a version without them and the linter says so.
The replacement is recorded on the same `answer_recorded` event as
`replaces_entries: [{entry_id, previous_question_id, previous_answer_id}]`.
Declaring one id twice **inside one** payload is a malformed payload (exit 1,
journal unchanged). Render, readiness and the gate all read one projection:
latest answer per question, then the latest version of each entry id.

The interview survives process boundaries: `start` issues the first question
and exits, and a later `status` in a **new** process resumes from the session
journal. State lives under `$DISCOVERY_HOME/sessions/<id>/` (default
`~/.discovery`) as an append-only event journal; the brief is always re-derived
from that journal, never edited in place.

An answer is a YAML document with free-text `text` and an optional list of
typed `entries`:

```yaml
text: retries are the top complaint in support tickets
entries:
  - id: G-01
    body: cut failed courier calls by half
  - id: FR-01
    body: retry a timed-out courier call
    Priority: Must
    Acceptance: a timed-out call is retried within 30s
    traces: [G-01]
```

`traces` is always a YAML list. A scalar is refused at intake: a quoted
`'[J-02, G-01]'` cannot be told apart from a single id, and the contract's body
parser recognises only the bracket form.

## What a caller reads

Every command prints one JSON envelope on stdout and exits with a code that
projects it. There is no `--json` flag — the output is always JSON.

```json
{
  "lifecycle": "awaiting_input | complete | unknown",
  "gate":      "pass | fail | unknown",
  "readiness": "ready | incomplete | unknown",
  "next_action": {},
  "findings": [],
  "readiness_findings": [],
  "operation": {"status": "ok | refused | unknown", "reason": "..."}
}
```

The three axes answer three different questions, and none is derivable from the
others. `lifecycle` — is the conversation finished? `gate` — does the linter
accept the document? `readiness` — is the brief substantively complete, per the
contract's §4 coverage-gate formula? A lint-clean brief can still be a stub, so
`readiness_findings` names the failed clauses (uncovered required topics,
untraced FRs, blocking open questions) separately from the linter's `findings`.

| code | meaning |
|---|---|
| `1` | an axis could not be determined, or the call itself decided nothing |
| `2` | refused precondition: no target question, or a conflicting answer without `--supersede`; state read and **unchanged** |
| `20` | `lifecycle: awaiting_input` — waiting for a human |
| `10` | `lifecycle: complete`, `gate: fail` |
| `11` | `lifecycle: complete`, `gate: pass`, `readiness: incomplete` |
| `0` | `lifecycle: complete`, `gate: pass`, `readiness: ready` |

Priority runs `1 > 2 > 20 > 10 > 11 > 0`, and the function is total: an
envelope whose axes are not a shape the protocol defines is `1`, never `0`.

> **`exit 20` breaks `&&`.** `awaiting_input` is a successful state, not a
> failure — but it is a non-zero code, so `discovery start ... && next-step`
> stops there. A caller that chains commands must branch on the code rather
> than rely on `&&`:
>
> ```bash
> discovery status --session "$id"; code=$?
> case $code in
>   0)  ;;                       # brief is ready
>   20) ;;                       # hand the question to a human, then resume
>   *)  exit $code ;;
> esac
> ```

**The engineer frame** needs a resolvable reference to an upstream customer
brief with `status: approved`, and it needs the feasibility topic answered. The
runtime marks `coverage.feasibility_review` covered once that question has an
answer; the vendored linter then checks the claim against the upstream brief and
fails the gate, naming the requirement, if any upstream Must-FR received no
verdict.

`--upstream <file>` is how that reference is established. A caller may not write
into `$DISCOVERY_HOME`, and `traces_to` is resolved from the session directory,
so a path into some other repository is not resolvable from a session at all.
`start` therefore copies the file into the session under the fixed name
`upstream.md` and puts that name first in `traces_to`. The name is fixed rather
than taken from the source: a basename that collided with the brief's own file
name would make `traces_to` resolve to the brief itself, and the gate would
check the document against its own body.

The source is validated before the session exists — it must be a `.md`
`discovery-brief`, `interview.frame: customer`, `status: approved`, and clean
under the vendored linter — so an interview cannot be half-run against the wrong
source. Two names are consequently reserved: `--traces-to upstream.md` alongside
`--upstream` is refused as ambiguous, and `brief --out` may not be named
`upstream.md` for such a session.

The rendered brief carries the same portable `traces_to`, so a caller that keeps
its own durable copy of that file **beside** the brief it wrote with `--out` gets
a reference that resolves from the brief, in its own repository, with no path
back into the session:

```
brief-input/00-discovery/
  brief.md      <- discovery brief --out
  upstream.md   <- the caller's durable copy of the same upstream file
```

## Development

`uv` only. `uv run pytest`, `uv run ruff format .`, `uv run ruff check .`,
`uv run pyrefly check` — all four run in CI on every push and pull request.

- Design: `docs/superpowers/specs/2026-08-18-discovery-runtime-design.md`
- Acceptance evidence: `docs/evidence/`
- Orchestrated-run preflight and traps: `docs/runbooks/orchestrated-run-preflight.md`
- Plan of record: `TODO.md`
