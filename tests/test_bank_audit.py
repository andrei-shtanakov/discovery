from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

import bank_audit  # noqa: E402

FRAMES = (
    Path(__file__).resolve().parents[1] / "src" / "discovery" / "contract" / "frames"
)


class TestClassify:
    def test_tag_question_is_leading(self):
        assert "tag_question" in bank_audit.classify("Это ведь важно, не так ли?")

    def test_answer_menu_is_leading(self):
        text = "Что недопустимо (потеря данных, запись куда-то, простой)?"
        assert "answer_menu" in bank_audit.classify(text)

    def test_instruction_parenthetical_is_not_an_answer_menu(self):
        text = "Что продукт должен уметь? (иди от jobs, не от «списка хотелок»)"
        assert bank_audit.classify(text) == []

    def test_slash_enumeration_is_not_a_signal(self):
        text = "Насколько быстро/надёжно/безопасно это должно работать — в числах?"
        assert bank_audit.classify(text) == []

    def test_presupposition_is_leading(self):
        assert "presupposition" in bank_audit.classify(
            "Почему вы не сделали это раньше?"
        )

    def test_delayed_presupposition_is_leading(self):
        text = "Почему вы до сих пор не автоматизировали?"
        assert "presupposition" in bank_audit.classify(text)

    def test_innocent_pochemu_vy_question_stays_clean(self):
        assert bank_audit.classify("Почему вы выбрали этот стек?") == []

    def test_real_bank_pochemu_question_stays_clean(self):
        # customer.goals.02 — a real bank bullet; the narrow "до сих пор не"
        # alternative must not catch this neighbour.
        text = "Почему сейчас? Что случится, если ничего не делать полгода?"
        assert bank_audit.classify(text) == []

    def test_non_question_is_advisory(self):
        text = "Прогони перед стейкхолдером краткое резюме целей."
        assert bank_audit.classify(text) == ["advisory"]

    def test_plain_question_is_clean(self):
        assert bank_audit.classify("Какую проблему решаем?") == []


class TestAuditFrame:
    @pytest.mark.parametrize("frame,issued", [("customer", 19), ("engineer", 15)])
    def test_audits_exactly_the_issued_questions(self, frame, issued):
        audit = bank_audit.audit_frame(frame, FRAMES)
        assert len(audit.questions) == issued

    def test_reports_topics_that_are_never_issued(self):
        audit = bank_audit.audit_frame("engineer", FRAMES)
        assert audit.unissued_topics, (
            "engineer carries at least one coverage_key: none topic, "
            "whose bullets are never issued to a stakeholder"
        )

    def test_claimed_covers_every_required_key(self):
        from discovery.contract import gate_check

        audit = bank_audit.audit_frame("customer", FRAMES)
        required = set(gate_check.FRAMES["customer"]["required"])
        assert required <= set(audit.claimed)

    @pytest.mark.parametrize("frame", ["customer", "engineer"])
    def test_every_emitted_category_is_registered_in_categories(self, frame):
        # A category classify() emits but CATEGORIES doesn't list would slip
        # past the digest/leading counts silently; this pins the invariant
        # against the whole real bank, not just classify()'s unit cases.
        audit = bank_audit.audit_frame(frame, FRAMES)
        for question in audit.questions:
            assert set(question.categories) <= set(bank_audit.CATEGORIES)

    def test_categories_is_a_tuple_not_a_mutable_list(self):
        # frozen=True only blocks rebinding the attribute; a mutable list
        # field would let an in-place edit silently change an audit result.
        # If `categories` ever reverts to a list, `.append` would succeed
        # instead of raising, and this test would fail loudly.
        audit = bank_audit.audit_frame("customer", FRAMES)
        question = audit.questions[0]
        with pytest.raises(AttributeError):
            question.categories.append("mutated")


BASELINE = Path(__file__).resolve().parent / "data" / "bank_audit_baseline.json"


class TestBaseline:
    def test_snapshot_matches_the_committed_baseline(self):
        import json

        current = bank_audit.snapshot(FRAMES)
        recorded = json.loads(BASELINE.read_text(encoding="utf-8"))
        assert current == recorded, (
            "the bank's wording or composition changed. If the change is "
            "deliberate, refresh with `uv run python tools/bank_audit.py "
            "--emit-baseline` and explain the diff in the pull request; the "
            "leading-question categories are the thing under review."
        )

    def test_snapshot_records_the_contract_pin(self):
        current = bank_audit.snapshot(FRAMES)
        assert current["pin"], "a snapshot without its pin cannot be attributed"

    @pytest.mark.parametrize("frame,issued", [("customer", 19), ("engineer", 15)])
    def test_digests_cover_exactly_the_issued_questions(self, frame, issued):
        current = bank_audit.snapshot(FRAMES)
        assert len(current["frames"][frame]["digests"]) == issued

    def test_leading_count_excludes_advisory_only_questions(self):
        current = bank_audit.snapshot(FRAMES)
        # customer: personas.01 + nfr.02 are answer_menu (leading); jobs.01 is
        # advisory-only and must not be counted.
        assert current["frames"]["customer"]["leading"] == 2
        # engineer: interfaces.01 is answer_menu (leading); feasibility_review
        # .02/.03 are advisory-only and must not be counted.
        assert current["frames"]["engineer"]["leading"] == 1

    def test_rewording_an_unflagged_question_changes_the_snapshot(self, tmp_path):
        """A reworded question that no rule matches must still fail the
        baseline: `snapshot()` digests every issued question, not only the
        flagged ones. Reworded into something a human would call leading
        (a tag question), to prove the hole the reviewer found is closed."""
        rigged = tmp_path / "frames"
        rigged.mkdir()
        for name in ("customer.md", "engineer.md"):
            (rigged / name).write_text(
                (FRAMES / name).read_text(encoding="utf-8"), encoding="utf-8"
            )
        original = (
            "- Какую проблему решаем? Как это болит сегодня — на конкретном "
            "недавнем примере?"
        )
        reworded = "- Это ведь и есть проблема, не так ли?"
        customer_text = (rigged / "customer.md").read_text(encoding="utf-8")
        assert customer_text.count(original) == 1
        (rigged / "customer.md").write_text(
            customer_text.replace(original, reworded, 1), encoding="utf-8"
        )

        rigged_snapshot = bank_audit.snapshot(rigged)
        real_snapshot = bank_audit.snapshot(FRAMES)
        assert rigged_snapshot != real_snapshot
        assert (
            rigged_snapshot["frames"]["customer"]["digests"]["customer.goals.01"]
            != real_snapshot["frames"]["customer"]["digests"]["customer.goals.01"]
        )


class TestCLI:
    def test_documented_invocation_prints_the_report(self, monkeypatch, capsys):
        monkeypatch.setattr(
            sys, "argv", ["bank_audit.py", "report", "--frames", str(FRAMES)]
        )
        assert bank_audit.main() == 0
        assert "issued question(s)" in capsys.readouterr().out

    def test_unknown_positional_is_rejected(self, monkeypatch, capsys):
        monkeypatch.setattr(
            sys, "argv", ["bank_audit.py", "nonsense", "--frames", str(FRAMES)]
        )
        with pytest.raises(SystemExit) as excinfo:
            bank_audit.main()
        assert excinfo.value.code != 0
