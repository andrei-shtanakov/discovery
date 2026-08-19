"""Tests for discovery.questions — TASK-007."""

from discovery.questions import Question, StaticQuestionSource


def test_questions_returns_known_frame_in_catalogue_order():
    catalogue = {
        "customer": [
            Question("customer.goals.01", "goals", "What problem are we solving?"),
            Question("customer.jobs.01", "jobs", "Walk me through a recent case."),
        ]
    }
    source = StaticQuestionSource(pin="pin-1", catalogue=catalogue)

    assert source.questions("customer") == catalogue["customer"]


def test_questions_returns_empty_list_for_unknown_frame():
    source = StaticQuestionSource(pin="pin-1", catalogue={"customer": []})

    assert source.questions("engineer") == []


def test_questions_does_not_leak_across_frames():
    catalogue = {
        "customer": [Question("customer.goals.01", "goals", "Customer question")],
        "engineer": [Question("engineer.arch.01", "arch", "Engineer question")],
    }
    source = StaticQuestionSource(pin="pin-1", catalogue=catalogue)

    assert source.questions("customer") == catalogue["customer"]
    assert source.questions("engineer") == catalogue["engineer"]


def test_pin_echoes_constructed_value():
    source = StaticQuestionSource(pin="pin-42", catalogue={})

    assert source.pin == "pin-42"


def test_question_is_hashable():
    first = Question("customer.goals.01", "goals", "What problem are we solving?")
    second = Question("customer.goals.01", "goals", "What problem are we solving?")

    assert hash(first) == hash(second)
    assert {first, second} == {first}
