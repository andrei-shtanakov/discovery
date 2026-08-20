"""Frozen RED checkpoint for TASK-011.

This file is byte-frozen until the task is done: it exists to prove that, at
the moment the task started, `discovery.protocol` did not yet exist, so
`Envelope`/`exit_code` could not be shown to honour DESIGN-007's five-key
shape and DESIGN-008's / DESIGN-ADR-003's strict ranked priority
`1 > 2 > 20 > 10 > 0` — in particular the adversarial case where an
`operation.status == "unknown"` envelope is *also* `lifecycle: complete`,
`gate: fail`: rank 1 must short-circuit rank 4 (code 10) unconditionally,
never falling through to a lower-ranked match.
"""

from __future__ import annotations

import json


class TestExitCodePriorityRed:
    def test_priority_table_and_envelope_constructors(self):
        from discovery.protocol import Envelope, exit_code, ok, refused, unknown

        # ok(): operation is exactly {"status": "ok"}; to_json carries 5 keys.
        ok_envelope = ok(
            "complete", "pass", "ready", next_action={"kind": "none"}, findings=[]
        )
        assert ok_envelope.operation == {"status": "ok"}
        # Amended 2026-08-20: readiness axis and exit 11 added; key set is now seven.
        assert set(json.loads(ok_envelope.to_json()).keys()) == {
            "lifecycle",
            "gate",
            "readiness",
            "next_action",
            "findings",
            "readiness_findings",
            "operation",
        }
        assert exit_code(ok_envelope) == 0

        # refused(): axes carry the actual caller-supplied values, never
        # defaulted to "unknown"; operation carries the reason.
        refused_envelope = refused(
            "answer_conflict", "awaiting_input", "fail", "incomplete"
        )
        assert refused_envelope.operation == {
            "status": "refused",
            "reason": "answer_conflict",
        }
        assert refused_envelope.lifecycle == "awaiting_input"
        assert refused_envelope.gate == "fail"
        assert exit_code(refused_envelope) == 2

        # unknown(): both axes collapse to "unknown"; operation carries detail.
        unknown_envelope = unknown("journal unreadable")
        assert unknown_envelope.lifecycle == "unknown"
        assert unknown_envelope.gate == "unknown"
        assert unknown_envelope.operation == {
            "status": "unknown",
            "reason": "journal unreadable",
        }
        assert exit_code(unknown_envelope) == 1

        # awaiting_input outranks a failing gate (20, not 10), and findings
        # survive the pending state instead of being suppressed.
        pending_with_fail = Envelope(
            lifecycle="awaiting_input",
            gate="fail",
            readiness="incomplete",
            findings=["GC-04: missing required topic"],
        )
        assert exit_code(pending_with_fail) == 20
        assert pending_with_fail.findings == ["GC-04: missing required topic"]

        # complete/fail ranks below awaiting_input but above complete/pass.
        complete_fail = Envelope(
            lifecycle="complete", gate="fail", readiness="incomplete"
        )
        assert exit_code(complete_fail) == 10

        # Adversarial case: an envelope whose operation.status is "unknown"
        # AND whose axes read complete/fail must still resolve to rank 1,
        # never falling through to rank 4's code 10 — the one scenario
        # DESIGN-ADR-003 calls out by name as requiring a single ranked
        # function instead of scattered conditionals.
        unknown_but_complete_fail = Envelope(
            lifecycle="complete",
            gate="fail",
            readiness="incomplete",
            operation={"status": "unknown", "reason": "forced for test"},
        )
        assert exit_code(unknown_but_complete_fail) == 1
