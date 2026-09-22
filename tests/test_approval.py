"""`discovery.approval` — the mirror of a human merge, as pure functions.

The contract's mirror rule says `status`/`approved_by`/`approver` are a
machine reflection of git state. This module holds the reflecting half
without any effect: what the approval envelope is, how a brief's own
bytes are hashed *around* that envelope, and how the envelope is stamped
on or withdrawn. Each case isolates one claim:

`self_hash` ignores the envelope, so stamping and withdrawing never move
it, and any edit outside the envelope does; the same content on CRLF and
LF hashes alike. `stamp` writes exactly the four contract fields plus the
self-hash, keeps every other key and the body byte-for-byte, and is
idempotent. `withdraw` returns the brief to `draft` with the signature
fields cleared. `verify` is the honest-approval predicate a reader applies
without the forge: a stamped brief passes, an edited one fails, and a
brief that claims `approved` with no hash is a migration debt, refused.
"""

from __future__ import annotations

import pytest

from discovery import approval
from discovery.contract.gate_check import split_frontmatter
from discovery.render import GENERATED_BY

DRAFT = """---
schema: discovery-brief
schema_version: 1
spec_stage: discovery
status: draft
generated_by: discovery-runtime
generated_at: '2026-09-22T00:00:00Z'
validation: pass
interview:
  frame: customer
  sessions:
  - participant_role: customer
coverage:
  goals: covered
  gate_passed: true
open_questions: 0
blocking_open_questions: 0
conflicts: 0
traces_to: []
---

# Discovery Brief — org/repo (customer-фрейм)

## Goals

- **G-01** cut failed courier calls by half
"""

MERGE = approval.MergeEvent(
    login="andrei-shtanakov",
    merged_at="2026-09-22T10:00:00Z",
    commit="0123456789abcdef0123456789abcdef01234567",
)


class TestSelfHash:
    def test_is_sha256_prefixed(self):
        assert approval.self_hash(DRAFT).startswith("sha256:")

    def test_ignores_every_envelope_key(self):
        stamped = approval.stamp(DRAFT, MERGE)
        assert approval.self_hash(stamped) == approval.self_hash(DRAFT)

    def test_changes_on_a_body_edit(self):
        edited = DRAFT.replace("by half", "by a third")
        assert approval.self_hash(edited) != approval.self_hash(DRAFT)

    def test_changes_on_a_non_envelope_frontmatter_edit(self):
        edited = DRAFT.replace("validation: pass", "validation: fail")
        assert approval.self_hash(edited) != approval.self_hash(DRAFT)

    def test_folds_line_endings(self):
        crlf = DRAFT.replace("\n", "\r\n")
        assert approval.self_hash(crlf) == approval.self_hash(DRAFT)

    def test_refuses_a_document_without_frontmatter(self):
        with pytest.raises(approval.NotABrief):
            approval.self_hash("# just a heading\n")


class TestStamp:
    def test_writes_the_four_contract_fields_and_the_self_hash(self):
        meta, _ = split_frontmatter(approval.stamp(DRAFT, MERGE))
        assert meta is not None
        assert meta["status"] == approval.STATUS_APPROVED
        assert meta["approved_by"] == GENERATED_BY
        assert meta["approved_at"] == MERGE.merged_at
        assert meta["approver"] == MERGE.login
        assert meta[approval.SELF_HASH_KEY] == approval.self_hash(DRAFT)

    def test_places_the_envelope_right_after_status(self):
        meta, _ = split_frontmatter(approval.stamp(DRAFT, MERGE))
        assert meta is not None
        keys = list(meta)
        start = keys.index("status")
        assert keys[start : start + 5] == [
            "status",
            "approved_by",
            "approved_at",
            "approver",
            approval.SELF_HASH_KEY,
        ]

    def test_keeps_the_body_byte_for_byte(self):
        _, body_before = split_frontmatter(DRAFT)
        _, body_after = split_frontmatter(approval.stamp(DRAFT, MERGE))
        assert body_after == body_before

    def test_keeps_every_other_frontmatter_key_and_value(self):
        before, _ = split_frontmatter(DRAFT)
        after, _ = split_frontmatter(approval.stamp(DRAFT, MERGE))
        assert before is not None and after is not None
        for key in approval.ENVELOPE_KEYS:
            after.pop(key, None)
            before.pop(key, None)
        assert after == before

    def test_is_idempotent(self):
        once = approval.stamp(DRAFT, MERGE)
        assert approval.stamp(once, MERGE) == once

    def test_round_trips_a_renderer_shaped_brief_without_reformatting(self):
        """A draft the runtime rendered, split and joined back, is the same
        bytes: the stamp touches the envelope and nothing else."""
        assert approval.withdraw(approval.stamp(DRAFT, MERGE)) == DRAFT


class TestWithdraw:
    def test_returns_to_draft_with_signature_cleared(self):
        meta, _ = split_frontmatter(approval.withdraw(approval.stamp(DRAFT, MERGE)))
        assert meta is not None
        assert meta["status"] == approval.STATUS_DRAFT
        assert "approved_by" not in meta
        assert "approver" not in meta
        assert approval.SELF_HASH_KEY not in meta

    def test_on_a_draft_is_a_no_op(self):
        assert approval.withdraw(DRAFT) == DRAFT


class TestVerify:
    """The reader-side predicate: no forge, only the recorded hash."""

    def test_stamped_brief_passes(self):
        assert approval.verify(approval.stamp(DRAFT, MERGE)) is None

    def test_draft_is_not_approved(self):
        assert approval.verify(DRAFT) == approval.DEBT_STATUS

    def test_edit_after_stamping_lifts_the_signature(self):
        edited = approval.stamp(DRAFT, MERGE).replace("by half", "by a third")
        assert approval.verify(edited) == approval.DEBT_SELF_HASH

    def test_approved_by_hand_without_a_hash_is_migration_debt(self):
        hand_edited = DRAFT.replace(
            "status: draft",
            "status: approved\napproved_by: someone\n"
            "approved_at: '2026-09-14T00:00:00Z'\napprover: someone",
        )
        assert approval.verify(hand_edited) == approval.DEBT_MIGRATION

    def test_approved_without_a_signature_is_unsigned(self):
        stamped = approval.stamp(DRAFT, MERGE).replace(
            f"approver: {MERGE.login}", "approver: null"
        )
        assert approval.verify(stamped) == approval.DEBT_UNSIGNED
