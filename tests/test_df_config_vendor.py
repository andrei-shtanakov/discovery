"""Tests for the vendored DarkFactory config loader and its checker.

Modeled on test_vendored_copy.py. Nothing here touches the network:
provenance and drift take an injected fetcher, and consistency failures are
shown on a tmp copy, never on the real vendored file.
"""

import hashlib
import shutil
import sys
from pathlib import Path

import pytest

from discovery.darkfactory import df_config

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

import check_df_config_vendor as checker  # noqa: E402
import check_vendor  # noqa: E402

DARKFACTORY_DIR = (
    Path(__file__).resolve().parent.parent / "src" / "discovery" / "darkfactory"
)


def _pin() -> tuple[str, dict[str, str]]:
    return check_vendor.read_pinned(DARKFACTORY_DIR)


def _tmp_copy(tmp_path: Path) -> Path:
    for name in ("PINNED.txt", "df_config.py"):
        shutil.copy(DARKFACTORY_DIR / name, tmp_path / name)
    return tmp_path


def test_pin_is_a_full_sha_and_covers_the_surface():
    commit, manifest = _pin()

    assert len(commit) == 40
    assert checker.SURFACE <= set(manifest)


def test_copy_sha_matches_pin():
    _, manifest = _pin()
    actual = hashlib.sha256((DARKFACTORY_DIR / "df_config.py").read_bytes())

    assert actual.hexdigest() == manifest["df_config.py"]


def test_real_copy_passes_consistency():
    assert checker.run("consistency").status == "ok"


def test_consistency_fails_on_a_modified_byte(tmp_path):
    copy = _tmp_copy(tmp_path)
    target = copy / "df_config.py"
    target.write_bytes(target.read_bytes() + b"#")

    assert checker.run("consistency", dest=copy).status == "failed"


def test_consistency_cli_exits_1_on_a_modified_byte(tmp_path, monkeypatch):
    copy = _tmp_copy(tmp_path)
    target = copy / "df_config.py"
    target.write_bytes(target.read_bytes() + b"#")
    monkeypatch.setenv("DF_CONFIG_VENDOR_DEST", str(copy))
    monkeypatch.setattr(sys, "argv", ["check_df_config_vendor", "consistency"])

    assert checker.main() == 1


def test_consistency_fails_when_manifest_drops_the_file(tmp_path):
    copy = _tmp_copy(tmp_path)
    (copy / "PINNED.txt").write_text("commit: " + "a" * 40 + "\n", encoding="utf-8")

    assert checker.run("consistency", dest=copy).status == "failed"


def test_provenance_uses_governance_path_and_passes_on_identical_bytes():
    seen: list[str] = []

    def fetch(commit: str, rel: str) -> bytes:
        seen.append(rel)
        return (DARKFACTORY_DIR / "df_config.py").read_bytes()

    assert checker.run("provenance", fetch=fetch).status == "ok"
    assert seen == ["governance/df_config.py"]


def test_provenance_unreachable_is_unknown():
    assert checker.run("provenance", fetch=lambda c, r: None).status == "unknown"


def test_provenance_mismatch_fails():
    verdict = checker.run("provenance", fetch=lambda c, r: b"other")

    assert verdict.status == "failed"


def test_drift_compares_the_file_digest_not_the_repo_head():
    _, manifest = _pin()
    seen: list[tuple[str, str]] = []

    def fetch(commit, rel):
        seen.append((commit, rel))
        return (DARKFACTORY_DIR / "df_config.py").read_bytes()

    assert manifest["df_config.py"]
    assert checker.run("drift", fetch=fetch).status == "ok"
    assert seen == [("HEAD", "governance/df_config.py")]


def test_drift_changed_upstream_fails_with_both_digests():
    verdict = checker.run("drift", fetch=lambda *_: b"changed")

    assert verdict.status == "failed"
    assert "upstream df_config.py changed: pinned " in verdict.detail
    assert ", HEAD " in verdict.detail


def test_drift_unreachable_is_unknown():
    assert checker.run("drift", fetch=lambda *_: None).status == "unknown"


def test_check_vendor_defaults_still_target_the_contract_copy():
    assert check_vendor.REPO == "andrei-shtanakov/discovery-toolkit"
    assert checker.UPSTREAM_REPO != check_vendor.REPO


def test_vendored_loader_reads_the_fixture_strict_config():
    cfg = df_config.load()

    assert cfg.mode == "strict"
    assert cfg.accounts.human == "fixture-human"
    assert cfg.accounts.agent == "fixture-agent"
    assert cfg.policy is not None
    assert cfg.policy.repo == "andrei-shtanakov/approval-policy"
    assert cfg.author_model == "claude-opus-5"


@pytest.mark.no_df_config
def test_no_df_config_marker_leaves_no_config():
    with pytest.raises(df_config.ConfigError):
        df_config.load()
