"""RED checkpoint for TASK-003: marker-driven parser in `discovery.bank`.

Hermetic: the fixture is a synthetic in-memory frame string, not a read of
the real vendored `src/discovery/contract/frames/*.md` — those are covered
separately once `parse_frame`/`BankQuestionSource` exist (DESIGN-010).
"""

import pytest

FRAME = """# Frame: bank test fixture

### A. Something else entirely
<!-- coverage_key: goals; produces: G -->
- What problem are we solving?
- Walk me through two or three real situations from
  your week.

### B. Heading with no marker
- Poison: a bare heading close must drop this bullet, not extend the
  goals topic

### C. Yet another heading
<!-- coverage_key: personas; produces: P -->
- Who uses this?

## Coverage
- Poison: `## Coverage` must close the personas topic, not extend it

### D. Final heading
<!-- coverage_key: none; produces: X,Q -->
- Who else must we ask?

## Правила извлечения
- Poison: `## Правила извлечения` must close the closing topic, not
  extend it
"""


class TestBankParseFrameRed:
    def test_marker_driven_coverage_key_and_heading_closes_topic(self):
        try:
            from discovery.bank import parse_frame
        except ModuleNotFoundError as exc:
            pytest.fail(
                f"discovery.bank does not exist yet (parse_frame unimplemented): {exc}"
            )

        topics = parse_frame(FRAME)

        # (a) coverage_key comes from the marker, never from the heading text
        # ("Something else entirely" names nothing); `none` is a legitimate
        # topic, not skipped and not an error.
        assert len(topics) == 3, (
            "a bare heading with no marker opens no topic — only 3 markers "
            f"exist, got {len(topics)} topics"
        )
        assert topics[0].coverage_key == "goals"
        assert topics[0].produces == ["G"]
        assert topics[2].coverage_key is None
        assert topics[2].produces == ["X", "Q"]

        # (b) a continuation bullet (indented, no leading "- ") joins the
        # preceding question instead of truncating or opening a new one.
        assert topics[0].questions == [
            "What problem are we solving?",
            "Walk me through two or three real situations from your week.",
        ]

        # (c) a topic closes at the next heading of ANY level — a bare
        # "### next topic", "## Coverage", and "## Правила извлечения" each
        # tested separately — so trailing bullets never leak into the prior
        # topic's questions.
        assert topics[1].coverage_key == "personas"
        assert topics[1].questions == ["Who uses this?"], (
            "`## Coverage` must close the personas topic before its own "
            "poison bullet is read"
        )
        assert topics[2].questions == ["Who else must we ask?"], (
            "`## Правила извлечения` must close the closing topic before "
            "its own poison bullet is read"
        )
