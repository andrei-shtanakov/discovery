"""`upstream.admit` and the approval signature (discovery#55).

`approved` on an upstream brief is a claim; `approved_content_hash` ties
the claim to the bytes. Each case isolates one claim: a brief stamped by
`discovery approve` is admitted; the same brief edited after the stamp is
refused — the hash no longer covers these bytes, and the engineer
interview would run against a document nobody approved; a brief marked
`approved` with no hash at all (stamped by hand before the act existed) is
still admitted, as migration debt named in `TODO.md`, not silently
promoted to a signature.
"""

from __future__ import annotations

import pytest

from discovery import approval
from discovery.upstream import UpstreamRejected, admit

APPROVED_BY_HAND = """---
schema: discovery-brief
schema_version: 1
spec_stage: discovery
status: approved
generated_by: discovery-toolkit
generated_at: '2026-09-14T00:00:00Z'
validation: pass
interview:
  frame: customer
  sessions:
  - participant_role: customer
coverage:
  goals: covered
  personas: covered
  jobs: covered
  functions: covered
  nfr: covered
  constraints: covered
  success_metrics: covered
  out_of_scope: covered
  gate_passed: true
open_questions: 0
blocking_open_questions: 0
conflicts: 0
traces_to: []
---

# Discovery Brief — org/polygon (customer-фрейм)

## Goals

- **G-01** cut failed courier calls by half

## Personas

- **P-01** dispatcher on the night shift

## Jobs-to-be-done

- **J-01** retry a call without leaving the queue view

## Functional Requirements

- **FR-01** retry a timed-out courier call
  **Priority**: Must
  **Acceptance**: a timed-out call is retried within 30s
  traces: [G-01]

## Non-Functional

- **NFR-01** retry latency
  **Target**: p95 under 30s

## Constraints

- **CON-01** no changes to the courier API

## Success Metrics

- **M-01** failed calls per shift
  traces: [G-01]

## Out of Scope

- **OUT-01** courier-side retries
"""

STAMPED = approval.stamp(
    approval.withdraw(APPROVED_BY_HAND),
    approval.MergeEvent("andrei-shtanakov", "2026-09-22T10:00:00Z", "abc"),
)


@pytest.fixture
def upstream(tmp_path):
    def write(text):
        path = tmp_path / "customer.md"
        path.write_text(text, encoding="utf-8")
        return path

    return write


class TestSignature:
    def test_a_stamped_brief_is_admitted(self, upstream):
        assert admit(upstream(STAMPED)) == STAMPED

    def test_a_brief_edited_after_the_stamp_is_refused(self, upstream):
        edited = STAMPED.replace("by half", "by a third")

        with pytest.raises(UpstreamRejected, match=approval.SELF_HASH_KEY):
            admit(upstream(edited))

    def test_a_hand_approved_brief_without_a_hash_is_still_admitted(self, upstream):
        """Migration debt, admitted as before — see TODO.md brief-approval-act."""
        assert admit(upstream(APPROVED_BY_HAND)) == APPROVED_BY_HAND
