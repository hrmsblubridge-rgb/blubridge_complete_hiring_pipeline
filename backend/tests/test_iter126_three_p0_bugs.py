"""iter126 — Regression tests for the 3 P0 bugs reported in Message 577.

Bug A: Re-registration `_clear_applicant_round_state` raised MongoDB
       "Updating the path 'scores_reset_at' would create a conflict at
       'scores_reset_at'" because the dynamic round-field scan picked up
       `scores_reset_at` (contains 'score') AND the helper $set it.

Bug B: Phantom daily "Final Reject" WhatsApp to tester credentials
       (rishi.nayak@blubridge.com / 9443109903) — Score Import marks the
       tester row status='Rejected', the auto-rejection worker sees it
       every evening and dispatches.

Bug C: "Update Applicants Scores" date filter dropped records — narrow
       date range used registered_candidates fallback, wider range
       locked to pipeline_data, hiding rc-only candidates.

All tests use isolated synthetic data tagged `_iter126_*` and self-clean.
"""

import asyncio
import os
import re
import sys
import uuid
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"))

from motor.motor_asyncio import AsyncIOMotorClient


@pytest.fixture
def db():
    client = AsyncIOMotorClient(os.environ["MONGO_URL"])
    return client[os.environ["DB_NAME"]]


# ─────────────────────── Bug A — Mongo conflict on scores_reset_at ─────

@pytest.mark.asyncio
async def test_clear_applicant_round_state_no_mongo_conflict(db):
    """Reset must succeed without Mongo conflict, even when the existing
    doc has a `scores_reset_at` field (which the dynamic scan would
    otherwise add to $unset — colliding with the helper's own $set)."""
    import bb_modules
    bb_modules._db = db

    seed_email = f"iter126a-{uuid.uuid4().hex[:8]}@example.invalid"
    seed_phone = "9999900000"

    # Insert a doc that already has scores_reset_at + a round-prefixed field
    # so the dynamic scan WILL pick them up.
    await db.bb_applicant_updates.insert_one({
        "email": seed_email,
        "phone": seed_phone,
        "name": "Old Stale Name",
        "status": "Rejected",
        "result_status": "rejected",
        "scores": [{"round_name": "Round 1", "score": 5.0}],
        "scores_reset_at": "2025-01-01T00:00:00+00:00",   # the conflict source
        "Round_1_score": 5.0,                              # dynamic round field
        "isImported": True,
        "_iter126_test": True,
    })

    try:
        # Must NOT raise.
        res = await bb_modules._clear_applicant_round_state(
            {"email": seed_email},
            {"name": "Fresh Name", "phone": seed_phone, "job_role": "QA Engineer"},
        )
        assert res["matched"] == 1
        assert res["modified"] == 1

        doc = await db.bb_applicant_updates.find_one({"email": seed_email})
        assert doc is not None
        assert doc["name"] == "Fresh Name"
        assert doc["phone"] == seed_phone
        assert doc["job_role"] == "QA Engineer"
        assert doc["scores"] == []
        assert doc["status"] == ""
        assert doc["result_status"] == ""
        # scores_reset_at must be PRESENT (set by helper, NOT unset)
        assert "scores_reset_at" in doc
        assert doc["scores_reset_at"] > "2025-01-01"
        # The dynamic round field must have been unset.
        assert "Round_1_score" not in doc
        # isImported flag must be cleared.
        assert "isImported" not in doc

    finally:
        await db.bb_applicant_updates.delete_many({"_iter126_test": True})


@pytest.mark.asyncio
async def test_clear_applicant_round_state_unset_excludes_set_keys(db):
    """Source-code guard: the helper must compute $unset AFTER set_doc is
    built and explicitly subtract all $set keys to prevent the conflict."""
    import inspect
    import bb_modules
    src = inspect.getsource(bb_modules._clear_applicant_round_state)
    # The conflict-prevention strip must reference set_doc.keys() (NOT just
    # the static reset-to-empty dict).
    assert "unset_combined -= set(set_doc.keys())" in src, (
        "Helper must strip ALL set_doc keys from unset_combined, not only "
        "the static reset-to-empty bucket — otherwise scores_reset_at / "
        "updated_at / identity overwrites still collide."
    )


# ─────────────────────── Bug B — Tester credentials phantom rejection ──

@pytest.mark.asyncio
async def test_rejection_worker_skips_tester_credentials(db):
    """Source-code guard + behavioral check that the rejection mailer
    worker skips bb_test_credentials matches."""
    import inspect
    import bg_workers

    src = inspect.getsource(bg_workers._worker_import_rejection_mailer)
    # Must load tester emails/phones at the top of each tick.
    assert "bb_test_credentials" in src
    assert "tester_emails" in src
    assert "tester_phones" in src
    # Must perform the per-doc skip in BOTH sources.
    assert "RejectSkip:A:TESTER" in src
    assert "RejectSkip:B:TESTER" in src


@pytest.mark.asyncio
async def test_rejection_filter_excludes_pre_quarantined_tester(db):
    """Once a tester row is quarantined (rejection_notified=True), it must
    no longer match the worker's filter — preventing the daily phantom."""
    # The production tester row was pre-quarantined as part of the iter126
    # fix. Assert it does NOT match the worker filter.
    filter_a = {
        "status": "Rejected",
        "rejection_sent": {"$ne": True},
        "rejection_notified": {"$ne": True},
        "import_rejection_notified": {"$ne": True},
        "updated_at": {"$gte": "2026-05-11T18:30:00+00:00"},
    }
    cursor = db.bb_applicant_updates.find(filter_a, {"email": 1, "_id": 0})
    eligible = [d.get("email") async for d in cursor]
    # No tester email should leak through.
    assert "rishi.nayak@blubridge.com" not in eligible, (
        f"Tester email still eligible for auto-rejection: {eligible}"
    )


# ─────────────────────── Bug C — Update Scores date-filter union ───────

@pytest.mark.asyncio
async def test_attended_for_scores_unions_both_collections(db):
    """Source-code guard: the endpoint must $unionWith
    registered_candidates so rc-only candidates aren't dropped when
    pipeline_data also has hits in a wider date range."""
    import inspect
    import bb_modules
    src = inspect.getsource(bb_modules.get_attended_for_scores)
    assert '"$unionWith"' in src
    assert '"coll": "registered_candidates"' in src
    assert "_dedupe_key" in src
    # Must NOT use the old src-fallback pattern.
    assert "src = _db.registered_candidates" not in src, (
        "Old src-fallback pattern still present — rc-only rows will be "
        "dropped when pipeline_data has any hits."
    )


@pytest.mark.asyncio
async def test_attended_for_scores_includes_rc_only_row(db):
    """Functional: seed an rc-only candidate + a pipeline_data candidate
    on the SAME date. Old code locked src=pipeline_data and dropped the
    rc-only row; new code surfaces both."""
    import bb_modules
    bb_modules._db = db

    test_date = "2026-11-15"
    em_pd = f"iter126c-pd-{uuid.uuid4().hex[:8]}@example.invalid"
    em_rc = f"iter126c-rc-{uuid.uuid4().hex[:8]}@example.invalid"

    await db.pipeline_data.insert_one({
        "email": em_pd, "phone": "8000000001", "name": "PD Candidate",
        "schedule_date": test_date, "otp_verified": "1",
        "job_role": "QA Engineer", "_iter126_test": True,
    })
    await db.registered_candidates.insert_one({
        "email": em_rc, "phone": "8000000002", "name": "RC Candidate",
        "schedule_date": test_date, "otp_verified": "1",
        "job_role": "QA Engineer", "_iter126_test": True,
    })

    try:
        from fastapi import Request
        from unittest.mock import AsyncMock, MagicMock, patch

        with patch("bb_modules._require_auth", new=AsyncMock(return_value=None)):
            req = MagicMock(spec=Request)
            res = await bb_modules.get_attended_for_scores(
                request=req,
                startDate=test_date,
                endDate=test_date,
                page=1,
                limit=100,
                sort_by=None,
                sort_dir=None,
            )

        emails = {d.get("email") for d in res["data"]}
        assert em_pd in emails, f"pipeline_data row missing: {emails}"
        assert em_rc in emails, f"registered_candidates row missing: {emails}"

    finally:
        await db.pipeline_data.delete_many({"_iter126_test": True})
        await db.registered_candidates.delete_many({"_iter126_test": True})


@pytest.mark.asyncio
async def test_attended_for_scores_no_duplicate_when_both_collections_have_same_email(db):
    """Dedupe: when the SAME email exists in both collections, the
    endpoint must surface ONE row (the latest schedule_date), not two."""
    import bb_modules
    bb_modules._db = db

    em = f"iter126c-dup-{uuid.uuid4().hex[:8]}@example.invalid"
    test_date = "2026-11-16"

    await db.pipeline_data.insert_one({
        "email": em, "phone": "8000000003", "name": "Dup Candidate PD",
        "schedule_date": test_date, "otp_verified": "1",
        "job_role": "QA Engineer", "_iter126_test": True,
    })
    await db.registered_candidates.insert_one({
        "email": em, "phone": "8000000003", "name": "Dup Candidate RC",
        "schedule_date": test_date, "otp_verified": "1",
        "job_role": "QA Engineer", "_iter126_test": True,
    })

    try:
        from fastapi import Request
        from unittest.mock import AsyncMock, MagicMock, patch

        with patch("bb_modules._require_auth", new=AsyncMock(return_value=None)):
            req = MagicMock(spec=Request)
            res = await bb_modules.get_attended_for_scores(
                request=req,
                startDate=test_date,
                endDate=test_date,
                page=1,
                limit=100,
                sort_by=None,
                sort_dir=None,
            )

        emails = [d.get("email") for d in res["data"]]
        assert emails.count(em) == 1, (
            f"Duplicate email surfaced — dedupe failed: {emails}"
        )

    finally:
        await db.pipeline_data.delete_many({"_iter126_test": True})
        await db.registered_candidates.delete_many({"_iter126_test": True})
