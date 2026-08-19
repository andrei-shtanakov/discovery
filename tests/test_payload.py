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
    traces: G-01
    Priority: Must
    Acceptance: a timed-out call is retried twice before the order is failed
"""
    payload = parse_payload(raw)

    entry = payload.entries[0]
    assert "id" not in entry.fields
    assert "body" not in entry.fields
    assert entry.fields == {
        "traces": "G-01",
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
