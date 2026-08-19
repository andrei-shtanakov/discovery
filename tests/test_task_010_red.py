"""Frozen RED checkpoint for TASK-010.

This file is byte-frozen until the task is done: it exists to prove that, at
the moment the task started, `discovery.gate` did not yet exist, so
`render_and_gate` could not be shown to honour DESIGN-006's two-pass rule —
pass 1 renders with `validation="pending"`, checks it to derive `status` from
error-level findings only, and pass 2 re-renders with that real `status`
embedded so its own check-pass can never find a `GC-15` mismatch (the
declared `validation` is, by construction, exactly what the linter would
derive). Only the second pass's `GateResult` is returned.

`SessionHeader` below is a local stand-in for the field shape WS-B's not-yet
-merged `discovery.session.SessionHeader` (TASK-005) will provide — only the
fields `render_brief` (and so `render_and_gate`) is specified to read, same
stand-in shape as `tests/test_task_009_red.py`.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SessionHeader:
    """Stand-in carrying only the fields `render_and_gate` reads from a header."""

    session_id: str
    frame: str
    target: str
    traces_to: list[str]
    source_pin: str
    created_at: str


THIN_HEADER = SessionHeader(
    session_id="s-001",
    frame="customer",
    target="andrei-shtanakov/dispatcher",
    traces_to=[],
    source_pin="pin-1",
    created_at="2026-08-19T10:00:00Z",
)


class TestRenderAndGateRed:
    def test_thin_brief_fails_with_findings_and_second_pass_is_gc_15_clean(
        self, tmp_path
    ):
        from discovery.gate import render_and_gate

        result = render_and_gate(THIN_HEADER, [], tmp_path)

        assert result.status == "fail"
        assert result.findings
        assert not [f for f in result.findings if f.startswith("GC-15")]
        assert f"validation: {result.status}" in result.text
