"""Tests for `discovery.payload`, exercising [DESIGN-013]-[DESIGN-015]."""

import pytest

from discovery.payload import Entry, PayloadInvalid, parse_payload


def test_text_only_payload_has_no_entries():
    payload = parse_payload("text: just some free text\n")

    assert payload.text == "just some free text"
    assert payload.entries == []


def test_multi_entry_payload_preserves_document_order():
    raw = """
text: |
  we lose orders when the courier app times out
entries:
  - id: G-01
    body: cut order loss from courier timeouts
  - id: FR-01
    body: retry a timed-out courier call
"""
    payload = parse_payload(raw)

    assert [e.eid for e in payload.entries] == ["G-01", "FR-01"]
    assert payload.entries[0] == Entry(
        eid="G-01", body="cut order loss from courier timeouts"
    )
    assert payload.entries[1] == Entry(
        eid="FR-01", body="retry a timed-out courier call"
    )


def test_non_reserved_fields_are_preserved_verbatim():
    raw = """
text: hi
entries:
  - id: FR-01
    body: retry a timed-out courier call
    owner_role: product
    Priority: Must
    Acceptance: a timed-out call is retried twice before the order is failed
"""
    payload = parse_payload(raw)

    entry = payload.entries[0]
    assert "id" not in entry.fields
    assert "body" not in entry.fields
    assert entry.fields == {
        "owner_role": "product",
        "Priority": "Must",
        "Acceptance": ("a timed-out call is retried twice before the order is failed"),
    }


def test_missing_text_is_invalid():
    with pytest.raises(PayloadInvalid):
        parse_payload("entries: []\n")


def test_entry_without_id_is_invalid():
    with pytest.raises(PayloadInvalid):
        parse_payload("text: hi\nentries:\n  - body: no id here\n")


def test_entry_with_lowercase_id_is_invalid():
    with pytest.raises(PayloadInvalid):
        parse_payload("text: hi\nentries:\n  - id: lowercase-01\n    body: b\n")


def test_syntactically_broken_yaml_is_invalid():
    with pytest.raises(PayloadInvalid):
        parse_payload("text: [unclosed\n")


def test_null_entries_is_treated_as_empty():
    payload = parse_payload("text: hi\nentries:\n")

    assert payload.entries == []


def test_non_list_entries_is_invalid():
    with pytest.raises(PayloadInvalid):
        parse_payload("text: hi\nentries: 5\n")


class TestTracesType:
    def test_string_traces_are_refused(self):
        raw = (
            "text: an answer\n"
            "entries:\n"
            "  - id: FR-01\n"
            "    body: a function\n"
            "    traces: '[J-02, G-01]'\n"
        )
        with pytest.raises(PayloadInvalid) as exc:
            parse_payload(raw)
        assert "traces" in str(exc.value)
        assert "FR-01" in str(exc.value)

    def test_list_traces_are_accepted(self):
        raw = (
            "text: an answer\n"
            "entries:\n"
            "  - id: FR-01\n"
            "    body: a function\n"
            "    traces: [J-02, G-01]\n"
        )
        payload = parse_payload(raw)
        assert payload.entries[0].eid == "FR-01"

    def test_explicit_null_traces_is_refused(self):
        """An explicit YAML null is ambiguous (a scalar "not yet set" or an
        empty list?) and is refused, distinct from a `traces` key that is
        simply absent (see `render`'s missing-traces test: that renders as
        a readiness finding, never an error)."""
        raw = (
            "text: an answer\n"
            "entries:\n"
            "  - id: FR-01\n"
            "    body: a function\n"
            "    traces:\n"
        )
        with pytest.raises(PayloadInvalid) as exc:
            parse_payload(raw)
        assert "traces" in str(exc.value)
        assert "FR-01" in str(exc.value)


class TestTranslations:
    """Contract v1.3: rows of the customer brief's `## Translation table`."""

    def test_rows_are_kept_as_mappings_in_document_order(self):
        payload = parse_payload(
            "text: t\n"
            "translations:\n"
            "  - words: «мгновенно»\n"
            "    category: стоить\n"
            "    constraint: [NFR-01]\n"
            "  - words: «ничего не трогать»\n"
            "    category: не делать\n"
            "    constraint: OUT-01\n"
        )

        assert [row["words"] for row in payload.translations] == [
            "«мгновенно»",
            "«ничего не трогать»",
        ]

    def test_absent_translations_is_empty(self):
        assert parse_payload("text: t\n").translations == []

    def test_non_list_translations_is_invalid(self):
        with pytest.raises(PayloadInvalid, match="translations"):
            parse_payload("text: t\ntranslations: «быстро»\n")

    def test_a_row_that_is_not_a_mapping_is_invalid(self):
        with pytest.raises(PayloadInvalid, match="translations"):
            parse_payload("text: t\ntranslations:\n  - «быстро»\n")

    def test_an_unknown_column_is_invalid(self):
        """A misspelt column would silently render as `—` and pass as
        "no assumption" — refuse it instead."""
        with pytest.raises(PayloadInvalid, match="confirms"):
            parse_payload(
                "text: t\ntranslations:\n"
                "  - words: w\n    category: делать\n    constraint: FR-01\n"
                "    confirms: product-owner\n"
            )

    @pytest.mark.parametrize("cell", ["a | b", "a\\nb"])
    def test_a_cell_that_would_break_the_table_row_is_invalid(self, cell):
        """The linter splits rows on `|` and reads them line by line; a pipe
        or a newline inside a cell would shift the columns it checks."""
        with pytest.raises(PayloadInvalid, match="words"):
            parse_payload(
                "text: t\ntranslations:\n"
                f'  - words: "{cell}"\n    category: делать\n    constraint: FR-01\n'
            )
