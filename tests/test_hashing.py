"""Tests for discovery.hashing: canonical bytes and content-addressed ids.

Each case isolates one claim from [REQ-001]-[REQ-004]: CRLF/CR fold to the
same hash as LF, whitespace is never trimmed, a role-only change on an
otherwise-identical answer changes the id, and NUL-separated fields cannot
collide via naive concatenation.
"""

import hashlib

from discovery.hashing import answer_id, canonical_answer_bytes, file_sha256


def test_crlf_and_cr_hash_the_same_as_lf():
    lf = answer_id("s1", "q1", "product", "line one\nline two")
    crlf = answer_id("s1", "q1", "product", "line one\r\nline two")
    cr = answer_id("s1", "q1", "product", "line one\rline two")
    assert lf == crlf == cr


def test_leading_and_trailing_whitespace_is_not_trimmed():
    assert canonical_answer_bytes("  padded  ") == b"  padded  "


def test_answer_id_changes_when_only_participant_role_changes():
    product = answer_id("s1", "q1", "product", "same text")
    engineer = answer_id("s1", "q1", "engineer", "same text")
    assert product != engineer


def test_field_concatenation_does_not_collide():
    shifted_into_question_id = answer_id("s1", "q1\x00product", "", "x")
    real_fields = answer_id("s1", "q1", "product", "x")
    assert shifted_into_question_id != real_fields


def test_file_sha256_hashes_raw_bytes_with_no_canonicalization(tmp_path):
    target = tmp_path / "artifact.bin"
    target.write_bytes(b"line one\r\nline two")

    expected = f"sha256:{hashlib.sha256(target.read_bytes()).hexdigest()}"

    assert file_sha256(target) == expected
