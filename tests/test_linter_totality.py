"""The vendored linter is total on a foreign brief — the premise of calling it bare.

`approve` (`cli._lint_brief`) and `start --upstream` (`upstream.admit`) lint a
brief this runtime did not render, without a `try`. That holds only while
`gate_check.check` answers every input with findings. Three re-pins in a row
(discovery-toolkit#34, #38, #40) each closed one more raise, and each was found
by a different axis of input. This sweeps all of them at once, so the next
re-pin is checked by the suite instead of by a one-off script:

- every frontmatter key, top-level and inside `interview`/`coverage`, set to a
  hostile value;
- hostile `traces_to` strings (NUL, surrogates, huge, absolute, traversal);
- hostile target files (not UTF-8, broken frontmatter, no permission) and
  filesystem shapes (symlink loop, self-link, directory, dangling link);
- body mutations.

Python matters: on 3.12 `Path.resolve()` raises `RuntimeError` on a symlink
loop where 3.13 does not (#40). CI runs 3.12, the `requires-python` floor.
"""

from __future__ import annotations

import copy
import os
from collections.abc import Iterator
from pathlib import Path

import pytest
import yaml

from discovery.contract.gate_check import check, split_frontmatter
from discovery.render import render_brief
from discovery.session import SessionHeader

VALUES: list[object] = [
    None,
    0,
    -1,
    3.5,
    True,
    "",
    "x",
    "approved",
    [],
    [None],
    [1, "a"],
    {},
    {"a": 1},
    "\x00",
    "\ud800",
    "a" * 10000,
    [[[]]],
    {"frame": {}},
]
REFS = [
    "x\x00.md",
    "\ud800.md",
    "\udcff.md",
    "a" * 5000 + ".md",
    "a/" * 2000 + "x.md",
    "../../../../etc/x.md",
    "/abs.md",
    "~/x.md",
    "x\n.md",
    ".md",
    "loop/x.md",
    "self.md",
    "b/c/d.md",
    "dir.md",
    "dangling.md",
    "noperm.md",
    "nonutf8.md",
    "badfm.md",
    "ok.md",
]
FILES = {
    "nonutf8.md": b"\xff\xfe\x00bad",
    "badfm.md": b"---\n: : [\n---\n",
    "ok.md": b"---\nstatus: approved\n---\n- **FR-01** x\n  Priority: Must\n",
}
BODIES = [
    "",
    "\x00",
    "- **FR-01**\n  N/A: «x»\n",
    "## Translation table\n|a|\n|-|\n|" + "|" * 50,
    "- **NFR-01** x\n  **Category**: perf\n  **N/A**: \n",
]


@pytest.fixture
def hostile_dir(tmp_path: Path) -> Iterator[Path]:
    """A brief directory holding every hostile file and filesystem shape."""
    os.symlink(tmp_path / "b", tmp_path / "loop")
    os.symlink(tmp_path / "loop", tmp_path / "b")
    os.symlink(tmp_path / "self.md", tmp_path / "self.md")
    (tmp_path / "dir.md").mkdir()
    os.symlink(tmp_path / "nowhere", tmp_path / "dangling.md")
    for name, data in FILES.items():
        (tmp_path / name).write_bytes(data)
    noperm = tmp_path / "noperm.md"
    noperm.write_bytes(b"---\nstatus: approved\n---\n")
    noperm.chmod(0)
    yield tmp_path
    noperm.chmod(0o644)


def _render(meta: dict, body: str) -> str | None:
    """`meta` + `body` as a brief, or `None` when YAML cannot emit `meta`."""
    try:
        frontmatter = yaml.safe_dump(meta, allow_unicode=True, sort_keys=False)
    except yaml.YAMLError:
        return None
    return f"---\n{frontmatter}---\n{body}"


def _variants(frame: str, profile: str | None) -> Iterator[str]:
    """Every hostile brief derived from the runtime's own empty-session brief."""
    header = SessionHeader(
        session_id="s-totality",
        frame=frame,
        target="org/repo",
        traces_to=[],
        source_pin="pin",
        created_at="2026-11-19T00:00:00Z",
    )
    meta, body = split_frontmatter(render_brief(header, [], validation="pending"))
    assert meta is not None
    base = copy.deepcopy(meta)
    if profile is not None:
        base["interview"]["profile"] = profile
    metas = [base]
    for key in list(base):
        for value in VALUES:
            metas.append({**copy.deepcopy(base), key: value})
    for section in ("interview", "coverage"):
        for key in [*base[section], "extra"]:
            for value in VALUES:
                mutated = copy.deepcopy(base)
                mutated[section][key] = value
                metas.append(mutated)
    for ref in REFS:
        metas.append({**copy.deepcopy(base), "traces_to": [ref]})
        metas.append({**copy.deepcopy(base), "traces_to": ref})
    for mutated in metas:
        if (text := _render(mutated, body)) is not None:
            yield text
    for hostile_body in BODIES:
        if (text := _render(base, hostile_body)) is not None:
            yield text


@pytest.mark.parametrize("profile", [None, "full", "feature", "bogus"])
@pytest.mark.parametrize("frame", ["customer", "engineer"])
def test_check_answers_every_hostile_brief_with_findings(
    hostile_dir: Path, frame: str, profile: str | None
) -> None:
    raised: dict[tuple[str, str], int] = {}
    for text in _variants(frame, profile):
        try:
            check(text, base_dir=hostile_dir)
        except Exception as exc:  # noqa: BLE001 — collecting every raise is the point
            signature = (type(exc).__name__, str(exc)[:80])
            raised[signature] = raised.get(signature, 0) + 1
    assert raised == {}


@pytest.mark.parametrize("text", ["", "---\n---\n", "---\n[\n---\n", "\x00---\n"])
def test_check_answers_a_brief_without_usable_frontmatter(
    hostile_dir: Path, text: str
) -> None:
    check(text, base_dir=hostile_dir)
