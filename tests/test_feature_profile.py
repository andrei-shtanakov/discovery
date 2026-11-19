"""Feature profile of the customer frame — contract v1.4 (inbox #86).

The bank's profile lines pick a short set and yes/no filters; a filter's
answer carries a structured `expand` that the sequencer reads from the
journal; the brief declares `interview.profile: feature`.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from discovery import cli
from discovery.bank import BankInvalid, BankQuestionSource, parse_frame
from discovery.lifecycle import expansions
from discovery.payload import PayloadInvalid, parse_payload

FRAMES_DIR = Path(cli.__file__).resolve().parent / "contract" / "frames"


def _bank() -> BankQuestionSource:
    return BankQuestionSource(pin="pin-test", frames_dir=FRAMES_DIR)


def _filters(source: BankQuestionSource) -> list[str]:
    return [
        q.question_id for q in source.feature_questions("customer", {}) if q.is_filter
    ]


class TestProfileLine:
    def test_short_and_filter_are_read_from_the_line_under_the_marker(self):
        topics = parse_frame(
            "### 4\n"
            "<!-- coverage_key: nfr; produces: NFR -->\n"
            "<!-- profile: feature; short: 1,3; filter: Есть ли? -->\n"
            "- a\n- b\n- c\n"
        )

        assert topics[0].short == (1, 3)
        assert topics[0].filter == "Есть ли?"

    def test_short_none_is_an_empty_set(self):
        topics = parse_frame(
            "<!-- coverage_key: nfr; produces: NFR -->\n"
            "<!-- profile: feature; short: none; filter: Есть ли? -->\n- a\n"
        )

        assert topics[0].short == ()

    def test_a_topic_without_the_line_has_no_profile(self):
        topics = parse_frame("<!-- coverage_key: nfr; produces: NFR -->\n- a\n")

        assert topics[0].short is None and topics[0].filter is None

    @pytest.mark.parametrize(
        "text",
        [
            # malformed: short is not a number list
            "<!-- coverage_key: nfr; produces: NFR -->\n"
            "<!-- profile: feature; short: one -->\n- a\n",
            # misplaced: after the topic's first question
            "<!-- coverage_key: nfr; produces: NFR -->\n- a\n"
            "<!-- profile: feature; short: 1 -->\n",
            # repeated
            "<!-- coverage_key: nfr; produces: NFR -->\n"
            "<!-- profile: feature; short: 1 -->\n"
            "<!-- profile: feature; short: 1 -->\n- a\n",
            # under the keyless closing topic
            "<!-- coverage_key: none; produces: X -->\n"
            "<!-- profile: feature; short: 1 -->\n- a\n",
        ],
    )
    def test_a_profile_line_out_of_grammar_or_place_is_refused(self, text):
        with pytest.raises(BankInvalid):
            parse_frame(text)


def _frame_dir(tmp_path, nfr_profile: str) -> Path:
    """A customer frame passing coverage, whose `nfr` topic has `nfr_profile`."""
    keys = ["goals", "personas", "jobs", "functions", "out_of_scope", "constraints"]
    prefixes = {
        "goals": "G",
        "personas": "P",
        "jobs": "J",
        "functions": "FR",
        "out_of_scope": "OUT",
        "constraints": "CON",
        "success_metrics": "M",
        "nfr": "NFR",
    }
    lines = []
    for key in [*keys, "success_metrics"]:
        lines += [
            f"<!-- coverage_key: {key}; produces: {prefixes[key]} -->",
            "<!-- profile: feature; short: 1 -->",
            f"- {key}?",
        ]
    lines += ["<!-- coverage_key: nfr; produces: NFR -->", *nfr_profile.splitlines()]
    lines += ["- a?", "- b?"]
    (tmp_path / "customer.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return tmp_path


class TestFeatureValidation:
    @pytest.mark.parametrize(
        "nfr_profile",
        [
            "",  # no profile line at all
            "<!-- profile: feature; short: 3 -->",  # number past the topic
            "<!-- profile: feature; short: 2,1 -->",  # not ascending
            "<!-- profile: feature; short: none -->",  # none without a filter
        ],
    )
    def test_a_bank_that_cannot_run_the_profile_is_refused(self, tmp_path, nfr_profile):
        source = BankQuestionSource("pin", _frame_dir(tmp_path, nfr_profile))

        with pytest.raises(BankInvalid):
            source.feature_questions("customer", {})

    def test_the_full_profile_does_not_need_profile_lines(self, tmp_path):
        source = BankQuestionSource("pin", _frame_dir(tmp_path, ""))

        assert len(source.questions("customer")) == 9

    def test_the_profile_is_customer_only(self):
        with pytest.raises(BankInvalid, match="customer-only"):
            _bank().feature_questions("engineer", {})


class TestVendoredBank:
    """Counts match the toolkit's own (PR discovery-toolkit#36)."""

    def test_full_is_unchanged_and_carries_no_filter(self):
        questions = _bank().questions("customer")

        assert len(questions) == 59
        assert not any(q.is_filter for q in questions)

    def test_unanswered_filters_hold_back_the_rest_of_their_topics(self):
        questions = _bank().feature_questions("customer", {})

        assert len(questions) == 15
        assert len(_filters(_bank())) == 5

    def test_every_filter_no_leaves_the_short_set(self):
        source = _bank()
        questions = source.feature_questions(
            "customer", dict.fromkeys(_filters(source), False)
        )

        assert len(questions) == 18  # 13 questions + 5 filters

    def test_every_filter_yes_expands_blocks_4_to_8_whole(self):
        source = _bank()
        questions = source.feature_questions(
            "customer", dict.fromkeys(_filters(source), True)
        )

        assert len(questions) == 48  # 10 short + 33 of blocks 4-8 + 5 filters

    def test_a_question_keeps_its_full_id(self):
        full = {q.question_id: q.text for q in _bank().questions("customer")}
        source = _bank()
        feature = source.feature_questions(
            "customer", dict.fromkeys(_filters(source), True)
        )

        for question in feature:
            if not question.is_filter:
                assert full[question.question_id] == question.text

    def test_filters_precede_their_topic(self):
        source = _bank()
        first_filter = _filters(source)[0]
        questions = source.feature_questions("customer", {first_filter: True})
        ids = [q.question_id for q in questions]

        assert ids.index(first_filter) < ids.index("customer.nfr.01")


class TestExpandPayload:
    def test_expand_is_read_as_a_bool(self):
        assert parse_payload("text: нет\nexpand: false\n").expand is False

    def test_absent_expand_is_none(self):
        assert parse_payload("text: x\n").expand is None

    @pytest.mark.parametrize("value", ["'no'", "1", "[true]"])
    def test_a_non_bool_expand_is_refused(self, value):
        with pytest.raises(PayloadInvalid, match="expand"):
            parse_payload(f"text: x\nexpand: {value}\n")

    def test_the_latest_answer_decides_the_expansion(self):
        events = [
            {"event": "answer_recorded", "question_id": "f", "expand": False},
            {"event": "answer_superseded", "question_id": "f"},
            {"event": "answer_recorded", "question_id": "f", "expand": True},
        ]

        assert expansions(events) == {"f": True}


def _run(capsys, argv):
    code = cli.main(argv)
    return code, json.loads(capsys.readouterr().out)


def _answer(capsys, tmp_path, session_id, text, *extra):
    path = tmp_path / "answer.yaml"
    path.write_text(text, encoding="utf-8")
    return _run(
        capsys,
        [
            "answer",
            "--session",
            session_id,
            "--role",
            "po",
            "--file",
            str(path),
            *extra,
        ],
    )


@pytest.fixture
def feature_session(capsys, monkeypatch, tmp_path):
    monkeypatch.setenv("DISCOVERY_HOME", str(tmp_path / "home"))
    _, envelope = _run(
        capsys,
        [
            "start",
            "--frame",
            "customer",
            "--target",
            "org/repo",
            "--profile",
            "feature",
        ],
    )
    return envelope["next_action"]["session_id"]


def _answer_until_filter(capsys, tmp_path, session_id) -> dict:
    """Answer plain questions until the pending one is a filter."""
    while True:
        _, envelope = _run(capsys, ["show", "--session", session_id])
        action = envelope["next_action"]
        if action.get("is_filter"):
            return action
        _answer(capsys, tmp_path, session_id, "text: ok\n")


class TestFeatureCli:
    def test_the_profile_is_refused_for_the_engineer_frame(
        self, capsys, monkeypatch, tmp_path
    ):
        monkeypatch.setenv("DISCOVERY_HOME", str(tmp_path / "home"))
        code, envelope = _run(
            capsys,
            ["start", "--frame", "engineer", "--target", "o/r", "--profile", "feature"],
        )

        assert code == 1
        assert "customer frame only" in envelope["operation"]["reason"]
        sessions = tmp_path / "home" / "sessions"
        assert not sessions.exists() or not any(sessions.iterdir())

    def test_a_filter_is_marked_in_next_action_and_needs_expand(
        self, capsys, tmp_path, feature_session
    ):
        action = _answer_until_filter(capsys, tmp_path, feature_session)

        assert action["question_id"] == "customer.nfr.filter01"
        _, refused = _answer(capsys, tmp_path, feature_session, "text: нет\n")
        assert refused["lifecycle"] == "unknown"
        assert "expand" in refused["operation"]["reason"]
        _, show = _run(capsys, ["show", "--session", feature_session])
        assert show["next_action"]["question_id"] == "customer.nfr.filter01"

    def test_expand_on_a_plain_question_is_refused(
        self, capsys, tmp_path, feature_session
    ):
        _, refused = _answer(
            capsys, tmp_path, feature_session, "text: x\nexpand: true\n"
        )

        assert "filter question only" in refused["operation"]["reason"]

    def test_no_skips_the_topic_and_yes_expands_it(
        self, capsys, tmp_path, feature_session
    ):
        _answer_until_filter(capsys, tmp_path, feature_session)
        _, after_no = _answer(
            capsys, tmp_path, feature_session, "text: «нет»\nexpand: false\n"
        )
        # Block 4 has `short: none`: the next question is block 5's filter.
        assert after_no["next_action"]["question_id"] == "customer.constraints.filter01"

        _, after_yes = _answer(
            capsys,
            tmp_path,
            feature_session,
            "text: да\nexpand: true\n",
            "--question",
            "customer.nfr.filter01",
            "--supersede",
        )
        assert (
            after_yes["next_action"]["question_id"] == "customer.constraints.filter01"
        )
        _answer(capsys, tmp_path, feature_session, "text: нет\nexpand: false\n")
        _, show = _run(capsys, ["show", "--session", feature_session])
        # The pending block-5 filter went first; block 4 now waits, expanded.
        assert show["next_action"]["question_id"] == "customer.nfr.01"

    def test_the_brief_declares_the_profile_and_show_carries_it(
        self, capsys, tmp_path, feature_session
    ):
        out = tmp_path / "brief.md"
        _run(capsys, ["brief", "--session", feature_session, "--out", str(out)])
        _, show = _run(capsys, ["show", "--session", feature_session])

        assert "  profile: feature\n" in out.read_text(encoding="utf-8")
        assert show["session"]["profile"] == "feature"

    def test_a_full_brief_has_no_profile_field(self, capsys, monkeypatch, tmp_path):
        monkeypatch.setenv("DISCOVERY_HOME", str(tmp_path / "home"))
        _, started = _run(
            capsys, ["start", "--frame", "customer", "--target", "org/repo"]
        )
        out = tmp_path / "brief.md"
        _run(
            capsys,
            [
                "brief",
                "--session",
                started["next_action"]["session_id"],
                "--out",
                str(out),
            ],
        )

        assert "profile:" not in out.read_text(encoding="utf-8")


_NA_NFR = (
    "text: «нет, как у остального приложения»\n"
    "entries:\n"
    "  - id: NFR-01\n"
    "    body: скорость и затраты\n"
    "    category: perf, cost\n"
    "    N/A: «нет, как у остального приложения» — блок 4 отфильтрован\n"
)


class TestNotApplicableReachesTheLinter:
    def test_na_closes_gc20_in_the_feature_profile(
        self, capsys, tmp_path, feature_session
    ):
        _answer(capsys, tmp_path, feature_session, _NA_NFR)
        _, envelope = _run(capsys, ["status", "--session", feature_session])
        about_nfr = [f for f in map(str, envelope["findings"]) if "NFR-01" in f]

        assert about_nfr == []

    def test_na_is_gc22_in_the_full_profile(self, capsys, monkeypatch, tmp_path):
        monkeypatch.setenv("DISCOVERY_HOME", str(tmp_path / "home"))
        _, started = _run(
            capsys, ["start", "--frame", "customer", "--target", "org/repo"]
        )
        session_id = started["next_action"]["session_id"]
        _answer(capsys, tmp_path, session_id, _NA_NFR)
        _, envelope = _run(capsys, ["status", "--session", session_id])
        about_nfr = " ".join(f for f in map(str, envelope["findings"]) if "NFR-01" in f)

        assert "GC-22" in about_nfr
