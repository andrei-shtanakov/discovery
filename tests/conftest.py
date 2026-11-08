"""Shared fixtures: an isolated DarkFactory config for every test.

The vendored loader (`discovery.darkfactory.df_config`) reads
`$XDG_CONFIG_HOME/darkfactory/config.toml`. Tests must never see the
developer's real config, so each test gets a tmp `XDG_CONFIG_HOME` holding a
valid strict config; the `no_df_config` marker leaves it empty instead.
"""

from __future__ import annotations

from pathlib import Path

import pytest

POLICY_SOURCE = (
    Path(__file__).resolve().parent.parent
    / "src"
    / "discovery"
    / "approval_policy_source.env"
)

CONFIG_TEMPLATE = """\
schema = "darkfactory-config/v1"
mode = "strict"

[accounts]
human = "fixture-human"
agent = "fixture-agent"
human_gh_config_dir = "~/.config/gh"
agent_gh_config_dir = "~/.config/review"

[policy]
repo = "{APPROVAL_POLICY_REPO}"
ref = "{APPROVAL_POLICY_REF}"
path = "{APPROVAL_POLICY_PATH}"

[workspace]
root = "{root}"

[harness]
author = "claude"
model = "claude-opus-5"
"""


def pytest_configure(config: pytest.Config) -> None:
    """Register the `no_df_config` marker."""
    config.addinivalue_line(
        "markers", "no_df_config: run with an empty XDG config dir (no config)"
    )


def _policy_coordinates() -> dict[str, str]:
    """Read the vendored policy coordinates so the fixture cannot drift."""
    pairs = (
        line.split("=", 1)
        for line in POLICY_SOURCE.read_text(encoding="utf-8").splitlines()
        if line and not line.startswith("#")
    )
    return {key: value for key, value in pairs}


def write_strict_config(xdg: Path, root: Path) -> Path:
    """Write the fixture's strict config under `xdg`; return its path."""
    path = xdg / "darkfactory" / "config.toml"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        CONFIG_TEMPLATE.format(root=root, **_policy_coordinates()), encoding="utf-8"
    )
    return path


@pytest.fixture(autouse=True)
def _df_config(
    monkeypatch: pytest.MonkeyPatch,
    request: pytest.FixtureRequest,
    tmp_path_factory: pytest.TempPathFactory,
) -> None:
    """Point XDG_CONFIG_HOME at a tmp dir with a strict config (or empty)."""
    xdg = tmp_path_factory.mktemp("xdg-config")
    monkeypatch.setenv("XDG_CONFIG_HOME", str(xdg))
    if request.node.get_closest_marker("no_df_config"):
        return
    write_strict_config(xdg, tmp_path_factory.mktemp("workspace"))
