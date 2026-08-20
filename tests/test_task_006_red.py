"""Frozen RED checkpoint for TASK-006.

This file is byte-frozen until the task is done: it exists to prove that,
at the moment the task started, `src/discovery/payload.py` did not yet
exist, so none of REQ-014 (parse a YAML answer payload into
`AnswerPayload`/`Entry`), REQ-015 (non-reserved entry fields preserved
verbatim in `Entry.fields`), or REQ-016 (`PayloadInvalid` on structural
violations) could be checked.
"""

import pytest


class TestPayloadRed:
    def test_parse_payload_follows_req_014_through_016(self):
        try:
            from discovery.payload import Entry, PayloadInvalid, parse_payload
        except ModuleNotFoundError as exc:
            pytest.fail(
                "discovery.payload does not exist yet "
                f"(REQ-014..REQ-016 unimplemented): {exc}"
            )

        # REQ-014: a multi-entry document round-trips text and entries in
        # document order.
        raw = """
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
"""
        payload = parse_payload(raw)

        assert payload.text == "we lose orders when the courier app times out"
        assert [e.eid for e in payload.entries] == ["G-01", "FR-01"]
        assert payload.entries[0] == Entry(
            eid="G-01", body="cut order loss from courier timeouts"
        )

        # REQ-015: fields other than id/body are preserved verbatim as str,
        # id/body themselves are excluded from fields.
        # Amended 2026-08-20: `traces` must be a YAML list (payload.LIST_FIELDS).
        # The REQ-015 example used a bare string, which is now refused at intake.
        fr_entry = payload.entries[1]
        assert fr_entry.fields == {
            "traces": "['G-01']",
            "Priority": "Must",
            "Acceptance": (
                "a timed-out call is retried twice before the order is failed"
            ),
        }

        # REQ-016: an entry id not matching ^[A-Z]+-\\d+$ is rejected, not
        # silently accepted.
        with pytest.raises(PayloadInvalid):
            parse_payload("text: hi\nentries:\n  - id: lowercase-01\n    body: b\n")
