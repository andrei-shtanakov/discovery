"""render_and_gate — two-pass render/check, second pass GC-15-clean (DESIGN-006).

`GC-15` fires when a brief's declared `validation` disagrees with whether the
linter found any error-level finding — the "mirror, don't predict" principle
(DESIGN-P3) from the linter's own side. A single render/check pass cannot
satisfy it: before checking, the real verdict is unknown, so pass 1 can only
ever claim `validation="pending"`. Pass 2 re-renders with the verdict pass 1
derived, so its own check-pass mirrors exactly what pass 1 already computed
and can never disagree with itself. Only the second pass's `GateResult` is
returned.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from discovery.contract.gate_check import check
from discovery.render import SessionHeaderLike, render_brief


@dataclass(frozen=True)
class GateResult:
    """The accepted (second-pass) outcome of `render_and_gate`."""

    status: str  # "pass" | "fail"
    findings: list[str]
    text: str


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

    final_text = render_brief(
        header,
        events,
        validation=status,
        findings=[str(f) for f in real_findings],
    )
    pass_2_findings = check(final_text, base_dir=base_dir)
    return GateResult(
        status=status, findings=[str(f) for f in pass_2_findings], text=final_text
    )
