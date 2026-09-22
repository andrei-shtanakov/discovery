"""Envelope and exit_code — DESIGN-007, DESIGN-008, DESIGN-ADR-003.

Every discovery command returns the same seven-key `Envelope` so a caller
has exactly one response contract to parse. `lifecycle`, `gate` and
`readiness` always describe *the session* and are never blanked on
refusal; only `unknown()` collapses all three axes to the literal string
`"unknown"`, which is inseparable from exit code 1. `exit_code` applies
that priority as one ranked function — `1 > 2 > 20 > 10 > 11 > 0` — so two
callers projecting the same `Envelope` can never disagree, even in the
adversarial case where `operation.status == "unknown"` on an otherwise
`complete`/`fail` envelope (rank 1 must still short-circuit rank 4).

`10` outranks `11`: a document that fails the linter may be failing GC-11
itself — its own claim about the very formula `readiness` projects — so an
invalid document is repaired before a merely thin one is acted on.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field

NO_TARGET_QUESTION = "no_target_question"
ANSWER_CONFLICT = "answer_conflict"
# `approve` refusals — facts established at the forge that deny the mirror.
PR_NOT_MERGED = "pr_not_merged"
APPROVER_NOT_AUTHORIZED = "approver_not_authorized"
BRIEF_NOT_IN_PR = "brief_not_in_pr"
BRIEF_BYTES_DIVERGED = "brief_bytes_diverged"

INCOMPLETE = "incomplete"
UNKNOWN = "unknown"

# The §7 vocabulary of each axis, minus `unknown` (rank 1 covers that).
# `exit_code` is total: a value outside these sets is a shape the runtime
# cannot project, and an unprojectable envelope is `1`, never `0`.
LIFECYCLE_VALUES = {"awaiting_input", "complete"}
GATE_VALUES = {"pass", "fail"}
READINESS_VALUES = {"ready", INCOMPLETE}


@dataclass
class Envelope:
    """The one response shape for every discovery command outcome."""

    lifecycle: str
    gate: str
    readiness: str
    next_action: dict = field(default_factory=dict)
    findings: list[str] = field(default_factory=list)
    readiness_findings: list[str] = field(default_factory=list)
    operation: dict = field(default_factory=lambda: {"status": "ok"})

    def to_json(self) -> str:
        """Serialize exactly the seven contract keys, in §7 order."""
        return json.dumps(
            {
                "lifecycle": self.lifecycle,
                "gate": self.gate,
                "readiness": self.readiness,
                "next_action": self.next_action,
                "findings": self.findings,
                "readiness_findings": self.readiness_findings,
                "operation": self.operation,
            }
        )


def ok(
    lifecycle: str,
    gate: str,
    readiness: str,
    next_action: dict | None = None,
    findings: list[str] | None = None,
    readiness_findings: list[str] | None = None,
) -> Envelope:
    """Success envelope: `operation` is exactly `{"status": "ok"}`."""
    return Envelope(
        lifecycle=lifecycle,
        gate=gate,
        readiness=readiness,
        next_action=next_action if next_action is not None else {},
        findings=findings if findings is not None else [],
        readiness_findings=(
            readiness_findings if readiness_findings is not None else []
        ),
        operation={"status": "ok"},
    )


def refused(
    reason: str,
    lifecycle: str,
    gate: str,
    readiness: str,
    next_action: dict | None = None,
    findings: list[str] | None = None,
    readiness_findings: list[str] | None = None,
    detail: str | None = None,
) -> Envelope:
    """Refusal envelope: axes carry the actual computed values, never
    defaulted to "unknown" — a refusal means state was read successfully.

    `reason` is a machine token; `detail`, when given, is the human-readable
    circumstance (which login, which hashes) and rides in `operation` too.
    """
    operation = {"status": "refused", "reason": reason}
    if detail is not None:
        operation["detail"] = detail
    return Envelope(
        lifecycle=lifecycle,
        gate=gate,
        readiness=readiness,
        next_action=next_action if next_action is not None else {},
        findings=findings if findings is not None else [],
        readiness_findings=(
            readiness_findings if readiness_findings is not None else []
        ),
        operation=operation,
    )


def unknown(detail: str) -> Envelope:
    """Unreadable journal/session: all three axes collapse to "unknown"."""
    return Envelope(
        lifecycle="unknown",
        gate="unknown",
        readiness="unknown",
        operation={"status": "unknown", "reason": detail},
    )


def exit_code(envelope: Envelope) -> int:
    """
    1  (highest) — operation.status == "unknown", any axis == "unknown", or
                   any axis carrying a value §7 does not define
    2            — operation.status == "refused"       (axes still readable)
    20           — lifecycle == "awaiting_input"        (even if gate == "fail")
    10           — lifecycle == "complete" and gate == "fail"
    11           — lifecycle == "complete", gate == "pass", readiness == "incomplete"
    0  (lowest)  — lifecycle == "complete", gate == "pass", readiness == "ready"

    Rank 1 also covers an envelope whose axes are not a shape §7 defines.
    Without that, the ranked function's tail answered `0` — success — for
    input it did not understand, and `11` for combinations its own docstring
    described as `complete`/`pass`. Reporting success for an unrecognised
    state is the defect this axis exists to remove, one level up.
    """
    if (
        envelope.operation.get("status") == UNKNOWN
        or envelope.lifecycle == UNKNOWN
        or envelope.gate == UNKNOWN
        or envelope.readiness == UNKNOWN
    ):
        return 1
    if (
        envelope.lifecycle not in LIFECYCLE_VALUES
        or envelope.gate not in GATE_VALUES
        or envelope.readiness not in READINESS_VALUES
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
