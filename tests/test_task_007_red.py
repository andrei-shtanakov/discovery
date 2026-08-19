"""Frozen RED checkpoint for TASK-007.

This file is byte-frozen until the task is done: it exists to prove that,
at the moment the task started, `discovery.questions` did not yet exist, so
`StaticQuestionSource.questions(frame)` could not be shown to return its
catalogue verbatim in declared order — the guarantee DESIGN-001 makes for
every source behind the `QuestionSource` port.
"""


class TestStaticQuestionSourceRed:
    def test_questions_returns_catalogue_verbatim_in_declared_order(self):
        from discovery.questions import Question, StaticQuestionSource

        catalogue = {
            "customer": [
                Question("customer.goals.01", "goals", "What problem are we solving?"),
                Question("customer.jobs.01", "jobs", "Walk me through a recent case."),
            ]
        }
        source = StaticQuestionSource(pin="pin-1", catalogue=catalogue)

        assert source.questions("customer") == catalogue["customer"]
