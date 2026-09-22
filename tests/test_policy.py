"""`discovery.policy` — the approver allowlist from its trusted source.

The list is read from the `approval-policy` repository at the last commit
touching the policy file, through the forge; the executing process's
environment never supplies it. Each case isolates one claim: the vendored
coordinates parse and name the devtools SSOT; the env format is read
fail-closed (absent, duplicate and empty are refusals, look-alikes are not
definitions); the allowlist is comma-separated with blanks dropped and an
empty list refused; a set `AUTHORIZED_APPROVER_ACCOUNTS` is refused before
the forge is asked; a source without history or without the file is
refused; and an unreachable forge is not a refusal but an unknown.
"""

from __future__ import annotations

import pytest

from discovery import policy
from discovery.forge import ForgeUnavailable


class TestVendoredSource:
    def test_names_the_devtools_ssot_coordinates(self):
        repo, ref, path = policy.source()

        assert repo == "andrei-shtanakov/approval-policy"
        assert ref == "main"
        assert path == "policy/approvers.env"

    def test_the_vendored_file_records_its_pin(self):
        text = policy.SOURCE_FILE.read_text(encoding="utf-8")

        assert "devtools@" in text


class TestEnvFormat:
    def test_reads_the_one_definition(self):
        assert policy.read_key("# c\nK=v\n", "K", "f") == "v"

    def test_absent_key_is_refused(self):
        with pytest.raises(policy.PolicyRefused):
            policy.read_key("OTHER=v\n", "K", "f")

    def test_duplicate_key_is_refused(self):
        with pytest.raises(policy.PolicyRefused, match="2 times"):
            policy.read_key("K=a\nK=b\n", "K", "f")

    def test_empty_value_is_refused(self):
        with pytest.raises(policy.PolicyRefused):
            policy.read_key("K=\n", "K", "f")

    @pytest.mark.parametrize("line", ["K =v", "export K=v", "k=v", "#K=v"])
    def test_look_alikes_are_not_definitions(self, line):
        assert policy.definition_lines(f"{line}\n", "K") == []


class TestAllowlist:
    def test_comma_separated_with_blanks_dropped(self):
        text = f"{policy.ALLOWLIST_KEY}= alice , bob,,\n"

        assert policy.parse_allowlist(text, "f") == frozenset({"alice", "bob"})

    def test_nobody_is_refused(self):
        with pytest.raises(policy.PolicyRefused, match="nobody"):
            policy.parse_allowlist(f"{policy.ALLOWLIST_KEY}= , ,\n", "f")


class _Forge:
    def __init__(self, sha, text, down=False):
        self.sha, self.text, self.down, self.asked = sha, text, down, False

    def _up(self):
        self.asked = True
        if self.down:
            raise ForgeUnavailable("down")

    def latest_commit_touching(self, repo, ref, path):
        self._up()
        return self.sha

    def file_at(self, repo, commit, path):
        self._up()
        return self.text

    def pull_request(self, repo, number):  # pragma: no cover - protocol only
        raise NotImplementedError

    def pull_request_files(self, repo, number):  # pragma: no cover
        raise NotImplementedError


class TestFromForge:
    def test_reads_the_list_at_the_latest_touching_commit(self, monkeypatch):
        monkeypatch.delenv(policy.ALLOWLIST_KEY, raising=False)
        forge = _Forge("abc", f"{policy.ALLOWLIST_KEY}=alice\n")

        assert policy.allowlist(forge) == frozenset({"alice"})

    def test_environment_is_refused_before_the_forge_is_asked(self, monkeypatch):
        monkeypatch.setenv(policy.ALLOWLIST_KEY, "alice")
        forge = _Forge("abc", f"{policy.ALLOWLIST_KEY}=alice\n")

        with pytest.raises(policy.PolicyRefused, match="no longer a source"):
            policy.allowlist(forge)
        assert forge.asked is False

    def test_source_without_history_is_refused(self, monkeypatch):
        monkeypatch.delenv(policy.ALLOWLIST_KEY, raising=False)

        with pytest.raises(policy.PolicyRefused, match="no history"):
            policy.allowlist(_Forge(None, None))

    def test_source_without_the_file_is_refused(self, monkeypatch):
        monkeypatch.delenv(policy.ALLOWLIST_KEY, raising=False)

        with pytest.raises(policy.PolicyRefused, match="has no"):
            policy.allowlist(_Forge("abc", None))

    def test_unreachable_forge_is_unknown_not_refused(self, monkeypatch):
        monkeypatch.delenv(policy.ALLOWLIST_KEY, raising=False)

        with pytest.raises(ForgeUnavailable):
            policy.allowlist(_Forge("abc", "x", down=True))
