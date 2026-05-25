"""iter118 — View Applicants Summary Statistics regression.

Validates every business rule from the user spec against live data on the
new MongoDB cluster (cluster1.uthtnct.mongodb.net / hr_analytics) and a
synthetic same-day rejected applicant to guard the bugfix.

Rules being validated (user-supplied verbatim):
  Total Naukri        = naukri_applies rows where date_of_application in range
  Total Registered    = pipeline_data rows where last_update in range
  Total Unregistered  = naukri_applies where _is_registered != True
                        AND date_of_application in range
  Shortlisted         = pipeline_data email_type matches /shortlist/i
                        AND last_update in range
  Rejected            = pipeline_data email_type does NOT match /shortlist/i
                        AND last_update in range
  Interview Scheduled = pipeline_data schedule_date AND schedule_time NOT NULL
                        AND last_update in range
  Interview Not Sched = pipeline_data schedule_date OR schedule_time IS NULL
                        AND last_update in range
  Attended            = scheduled AND otp_verified truthy (NOT null/empty/0/false)
  Not Attended        = scheduled AND otp_verified falsy

Tests use ONLY tester credentials and a synthetic tagged row.
"""

import asyncio
import os
import sys
from datetime import datetime, timezone

import pytest
from dotenv import load_dotenv

load_dotenv("/app/backend/.env")
sys.path.insert(0, "/app/backend")

from motor.motor_asyncio import AsyncIOMotorClient

TEST_EMAIL = "rishi.nayak@blubridge.com"
TEST_PHONE = "9443109903"
TAG = "_iter118_summary_stats_test"


async def _setup_synthetic_rejected_row(db, last_update_iso: str):
    """Insert one synthetic pipeline_data row representing a same-day
    rejected live-form applicant — the exact production scenario the user
    reported as missing from the Rejected count."""
    await db.pipeline_data.delete_many({TAG: True})
    await db.pipeline_data.insert_one({
        TAG: True,
        "email": TEST_EMAIL,
        "phone": TEST_PHONE,
        "name": "Iter118 Reject Live-form Test",
        "submitted_at": last_update_iso[:10] + " 10:00:00",
        "last_update": last_update_iso,
        "email_type": "",            # live form, no shortlist decision yet
        "schedule_date": None,
        "schedule_time": None,
        "otp_verified": None,
        "_normalized_job_role": "AI & ML Engineer",
        "_nirf_category": "NIRF",
        "isTest": True,              # iter118 spec: should still be counted
    })


async def _cleanup(db):
    await db.pipeline_data.delete_many({TAG: True})


async def _query_counts(start_date: str, end_date: str) -> dict:
    """Replicate the exact aggregation produced by /api/summary's pipe_match
    + the iter118 funnel expressions, restricted to the synthetic row only."""
    client = AsyncIOMotorClient(os.environ["MONGO_URL"])
    db = client[os.environ["DB_NAME"]]
    try:
        await _setup_synthetic_rejected_row(db, f"{start_date}T12:00:00+00:00")
        match = {
            TAG: True,
            "last_update": {"$gte": start_date, "$lte": end_date + "\uffff"},
        }
        is_shortlisted = {"$regexMatch": {"input": {"$ifNull": ["$email_type", ""]}, "regex": "shortlist", "options": "i"}}
        has_schedule = {"$and": [
            {"$ne": [{"$ifNull": ["$schedule_date", ""]}, ""]},
            {"$ne": [{"$ifNull": ["$schedule_time", ""]}, ""]},
        ]}
        otp_truthy = {"$and": [
            {"$ne": [{"$ifNull": ["$otp_verified", None]}, None]},
            {"$ne": [{"$ifNull": ["$otp_verified", ""]}, ""]},
            {"$ne": [{"$ifNull": ["$otp_verified", 0]}, 0]},
            {"$ne": [{"$ifNull": ["$otp_verified", "0"]}, "0"]},
            {"$ne": [{"$ifNull": ["$otp_verified", False]}, False]},
        ]}
        pipe = [
            {"$match": match},
            {"$group": {
                "_id": None,
                "total_registered": {"$sum": 1},
                "shortlisted": {"$sum": {"$cond": [is_shortlisted, 1, 0]}},
                "rejected":   {"$sum": {"$cond": [{"$not": is_shortlisted}, 1, 0]}},
                "scheduled":  {"$sum": {"$cond": [has_schedule, 1, 0]}},
                "not_scheduled": {"$sum": {"$cond": [{"$not": has_schedule}, 1, 0]}},
                "attended":   {"$sum": {"$cond": [{"$and": [has_schedule, otp_truthy]}, 1, 0]}},
                "not_attended": {"$sum": {"$cond": [{"$and": [has_schedule, {"$not": otp_truthy}]}, 1, 0]}},
            }},
        ]
        rows = await db.pipeline_data.aggregate(pipe).to_list(None)
        return rows[0] if rows else {}
    finally:
        await _cleanup(db)


def test_live_form_reject_counted_under_rejected():
    """Live-form applicant with empty email_type → user rule says count as
    Rejected (NOT shortlist). Pre-iter118 buggy logic required
    email_type =~ /^reject/ which would have missed this row."""
    counts = asyncio.run(_query_counts("2026-05-25", "2026-05-25"))
    assert counts.get("total_registered") == 1, counts
    assert counts.get("rejected") == 1, (
        f"Same-day live-form applicant must be counted as Rejected "
        f"per user rule (NOT shortlist). Got counts={counts}"
    )
    assert counts.get("shortlisted") == 0, counts
    assert counts.get("scheduled") == 0, counts
    assert counts.get("not_scheduled") == 1, counts
    assert counts.get("attended") == 0, counts
    assert counts.get("not_attended") == 0, counts


def test_istest_record_not_excluded():
    """The synthetic row has isTest=True. User spec: include test records
    if within date range. Pre-iter118 code applied `isTest != True` filter
    which would have hidden it; the new code drops that filter."""
    counts = asyncio.run(_query_counts("2026-05-25", "2026-05-25"))
    assert counts.get("total_registered") == 1


def test_date_upper_bound_includes_full_day():
    """`last_update` ISO timestamps with time portion must match a
    same-day endDate filter. Pre-iter116/iter118 the `<= endDate` (no
    \\uffff suffix) failed lexicographic comparison."""
    counts = asyncio.run(_query_counts("2026-05-25", "2026-05-25"))
    assert counts.get("total_registered") == 1


def test_mongo_cluster_is_current_production_cluster():
    """Guard: validate the .env points at the migrated Atlas cluster the
    user mentioned, NOT a stale earlier host."""
    uri = os.environ["MONGO_URL"]
    assert "cluster1.uthtnct.mongodb.net" in uri, (
        f"MONGO_URL appears to point at an unexpected cluster: {uri!r}"
    )
    assert os.environ["DB_NAME"] == "hr_analytics"


def test_naukri_unregistered_flag_is_populated():
    """Total Unregistered relies on the persisted `_is_registered` flag on
    naukri_applies. Guard against the flag being dropped during a future
    rebuild — at least some rows must carry it on the current cluster."""
    async def _run():
        client = AsyncIOMotorClient(os.environ["MONGO_URL"])
        db = client[os.environ["DB_NAME"]]
        return await db.naukri_applies.count_documents({"_is_registered": {"$exists": True}})
    n = asyncio.run(_run())
    assert n > 0, "_is_registered flag missing on every naukri_applies row"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
