"""Frozen RED checkpoint for TASK-009.

This file is byte-frozen until the task is done: it exists to prove that, at
the moment the task started, `discovery.render` did not yet exist, so
`render_brief` could not be shown to honour DESIGN-005's supersession rule —
`_latest_answers` must fold `answer_recorded` events by `question_id` the
same way `issued()` folds `question_asked` (DESIGN-002): last write wins, so
a superseded answer's entries never reach the body.

`SessionHeader` below is a local stand-in for the field shape WS-B's not-yet
-merged `discovery.session.SessionHeader` (TASK-005) will provide — only the
fields `render_brief` is specified to read.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SessionHeader:
    """Stand-in carrying only the fields `render_brief` reads from a header."""

    session_id: str
    frame: str
    target: str
    traces_to: list[str]
    source_pin: str
    created_at: str


def answer(question_id: str, role: str, payload: str) -> dict:
    return {
        "event": "answer_recorded",
        "question_id": question_id,
        "answer_id": f"sha256:{question_id}",
        "participant_role": role,
        "payload": payload,
    }


HEADER = SessionHeader(
    session_id="s-001",
    frame="customer",
    target="andrei-shtanakov/dispatcher",
    traces_to=[],
    source_pin="pin-1",
    created_at="2026-08-19T10:00:00Z",
)


class TestRenderBriefRed:
    def test_superseded_answer_entries_never_reach_the_body(self):
        from discovery.render import render_brief

        old = answer(
            "customer.goals.01",
            "product",
            "text: old\nentries:\n  - id: G-01\n    body: stale goal\n",
        )
        new = answer(
            "customer.goals.01",
            "product",
            "text: new\nentries:\n  - id: G-01\n    body: current goal\n",
        )

        text = render_brief(HEADER, [old, new], "pending")

        assert "current goal" in text
        assert "stale goal" not in text
