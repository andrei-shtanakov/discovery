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
