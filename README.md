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
discovery status --session <id>
discovery answer --session <id> [--question <id>] --role <role> --file <payload.yaml>|-  [--supersede]
discovery brief  --session <id> --out <brief_path>
```

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

**Known limitation.** The engineer frame cannot currently reach
`readiness: ready`: the required `feasibility_review` key is a process rather
than a section, and the runtime does not yet mirror the linter's GC-05 rule for
it, so an engineer run always exits `11`. Tracked as
`@id:feasibility-review-not-derived` in `TODO.md`.

## Development

`uv` only. `uv run pytest`, `uv run ruff format .`, `uv run ruff check .`,
`uv run pyrefly check` — all four run in CI on every push and pull request.

- Design: `docs/superpowers/specs/2026-08-18-discovery-runtime-design.md`
- Acceptance evidence: `docs/evidence/`
- Plan of record: `TODO.md`
