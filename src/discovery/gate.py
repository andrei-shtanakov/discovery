"""render_and_gate — two-pass render/check, second pass GC-15-clean (DESIGN-006).

`GC-15` fires when a brief's declared `validation` disagrees with whether the
linter found any error-level finding — the "mirror, don't predict" principle
(DESIGN-P3) from the linter's own side. A single render/check pass cannot
satisfy it: before checking, the real verdict is unknown, so pass 1 can only
ever claim `validation="pending"`. Pass 2 re-renders with the verdict pass 1
derived, so its own check-pass mirrors exactly what pass 1 already computed
and can never disagree with itself. Only the second pass's `GateResult` is
returned. The §4 verdict travels on the same result as the linter's, taken
from `render.readiness`, so §7's two verdicts are computed once each and
never re-derived by the protocol layer.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from discovery.contract.gate_check import check
from discovery.render import SessionHeaderLike, readiness, render_brief


class GateInvariantError(Exception):
    """The two passes disagreed — see §6.

    Raised when the accepted second pass does not see the findings the first
    pass did. That can only mean rendering the verdict changed the facts
    being checked, so there is no verdict to report and the operation fails
    closed rather than reporting one derived from a document that moved
    under it.
    """


@dataclass(frozen=True)
class GateResult:
    """The accepted (second-pass) outcome of `render_and_gate`."""

    status: str  # "pass" | "fail"
    findings: list[str]
    text: str
    readiness: str  # "ready" | "incomplete"
    readiness_findings: list[str]


def render_and_gate(
    header: SessionHeaderLike, events: list[dict], base_dir: Path
) -> GateResult:
    """Render with `validation="pending"`, check, then re-render with the
    real verdict and check again — only the second pass is returned."""
    pending_text = render_brief(header, events, validation="pending")
    pass_1_findings = check(pending_text, base_dir=base_dir)
    # Mirror `check`'s own GC-15 formula: `has_errors` there is computed from
    # every *other* rule's findings before GC-15 is appended, so a spurious
    # GC-15 mismatch against the placeholder "pending" value (never a real
    # verdict) must not itself count as the error that produces "fail", nor
    # be embedded as a real finding in the final brief.
    real_findings = [f for f in pass_1_findings if f.rule != "GC-15"]
    status = "fail" if any(f.level == "error" for f in real_findings) else "pass"

    final_text = render_brief(header, events, validation=status)
    pass_2_findings = check(final_text, base_dir=base_dir)
    # Ordered lists, never sets: a vanished duplicate or a changed order is
    # also a changed result, and normalising it away would hide exactly what
    # this invariant watches for (§6).
    if pass_2_findings != real_findings:
        raise GateInvariantError(
            "two-pass mismatch: rendering the verdict changed the findings — "
            f"pass 1 {[str(f) for f in real_findings]}, "
            f"pass 2 {[str(f) for f in pass_2_findings]}"
        )
    # `readiness()` is evaluated three times per call here (once inside each
    # of the two `render_brief` passes above, once directly on the next
    # line), each re-parsing every answer payload's YAML. Safe only because
    # `readiness` is a pure function of `(events, frame)` — the three results
    # cannot disagree. Keep it that way; do not let it grow hidden state.
    verdict = readiness(events, header.frame)
    return GateResult(
        status=status,
        findings=[str(f) for f in pass_2_findings],
        text=final_text,
        readiness=verdict.verdict,
        readiness_findings=verdict.findings,
    )
