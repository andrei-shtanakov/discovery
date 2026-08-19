"""RED: TASK-002 — build_source() on the vendored bank.

`build_source()` is still the D1 placeholder — an empty `StaticQuestionSource`
pinned `"unpinned"`. D2 replaces its body with a `BankQuestionSource` over
`discovery/contract/frames`, pinned to the commit recorded in
`discovery/contract/PINNED.txt`.
"""

from pathlib import Path

from discovery import cli
from discovery.bank import BankQuestionSource

PINNED_TXT = (
    Path(__file__).resolve().parent.parent
    / "src"
    / "discovery"
    / "contract"
    / "PINNED.txt"
)


def _pinned_commit() -> str:
    for line in PINNED_TXT.read_text(encoding="utf-8").splitlines():
        if line.startswith("commit:"):
            return line.removeprefix("commit:").strip()
    raise AssertionError("PINNED.txt has no commit: line")


class TestDefaultQuestionSourceRed:
    def test_build_source_is_bank_backed_and_pinned_to_pinned_txt_commit(self):
        source = cli.build_source()

        assert isinstance(source, BankQuestionSource)
        assert source.pin == _pinned_commit()
