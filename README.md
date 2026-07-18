# discovery

Runtime scaffold for discovery interviews and structured brief authoring.

`discovery` is the planned executable counterpart to `discovery-toolkit`: the
toolkit owns the methodology, frames, and `discovery-brief` contract; this repo
will host the runtime that conducts interviews and authors approved briefs.

Current state is intentionally small: `main.py` is still a placeholder and the
implementation has not yet been wired. The boundary remains authoring-only:
`discovery` should produce a brief for review/PR and must not generate or run
downstream `tasks.md`, design, or execution plans.

Canonical upstream inputs (expected as sibling directories in the same workspace):

- `../discovery-toolkit/DISCOVERY-BRIEF-CONTRACT.md`
- `../discovery-toolkit/.claude/skills/discovery-interview/`
- `../_cowork_output/decisions/2026-07-13-adr-discovery-interview-agent.md`
