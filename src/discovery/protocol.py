"""Envelope and exit_code — DESIGN-007, DESIGN-008, DESIGN-ADR-003.

Every discovery command returns the same five-key `Envelope` so a caller has
exactly one response contract to parse. `lifecycle` and `gate` always
describe *the session* and are never blanked on refusal; only `unknown()`
collapses both axes to the literal string `"unknown"`, which is inseparable
from exit code 1. `exit_code` applies that priority as one ranked function —
`1 > 2 > 20 > 10 > 0` — so two callers projecting the same `Envelope` can
never disagree, even in the adversarial case where `operation.status ==
"unknown"` on an otherwise `complete`/`fail` envelope (rank 1 must still
short-circuit rank 4).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field

NO_TARGET_QUESTION = "no_target_question"
ANSWER_CONFLICT = "answer_conflict"


@dataclass
class Envelope:
    """The one response shape for every discovery command outcome."""

    lifecycle: str
    gate: str
    next_action: dict = field(default_factory=dict)
    findings: list[str] = field(default_factory=list)
    operation: dict = field(default_factory=lambda: {"status": "ok"})

    def to_json(self) -> str:
        """Serialize exactly the five contract keys, nothing more."""
        return json.dumps(
            {
                "lifecycle": self.lifecycle,
                "gate": self.gate,
                "next_action": self.next_action,
                "findings": self.findings,
                "operation": self.operation,
            }
        )


def ok(
    lifecycle: str,
    gate: str,
    next_action: dict | None = None,
    findings: list[str] | None = None,
) -> Envelope:
    """Success envelope: `operation` is exactly `{"status": "ok"}`."""
    return Envelope(
        lifecycle=lifecycle,
        gate=gate,
        next_action=next_action if next_action is not None else {},
        findings=findings if findings is not None else [],
        operation={"status": "ok"},
    )


def refused(
    reason: str,
    lifecycle: str,
    gate: str,
    next_action: dict | None = None,
    findings: list[str] | None = None,
) -> Envelope:
    """Refusal envelope: axes carry the actual computed values, never
    defaulted to "unknown" — a refusal means state was read successfully."""
    return Envelope(
        lifecycle=lifecycle,
        gate=gate,
        next_action=next_action if next_action is not None else {},
        findings=findings if findings is not None else [],
        operation={"status": "refused", "reason": reason},
    )


def unknown(detail: str) -> Envelope:
    """Unreadable journal/session: both axes collapse to "unknown"."""
    return Envelope(
        lifecycle="unknown",
        gate="unknown",
        operation={"status": "unknown", "reason": detail},
    )


def exit_code(envelope: Envelope) -> int:
    """
    1  (highest) — operation.status == "unknown" OR lifecycle/gate == "unknown"
    2            — operation.status == "refused"       (axes still readable)
    20           — lifecycle == "awaiting_input"        (even if gate == "fail")
    10           — lifecycle == "complete" and gate == "fail"
    0  (lowest)  — lifecycle == "complete" and gate == "pass"
    """
    if (
        envelope.operation.get("status") == "unknown"
        or envelope.lifecycle == "unknown"
        or envelope.gate == "unknown"
    ):
        return 1
    if envelope.operation.get("status") == "refused":
        return 2
    if envelope.lifecycle == "awaiting_input":
        return 20
    if envelope.lifecycle == "complete" and envelope.gate == "fail":
        return 10
    return 0
