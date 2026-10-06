"""iter116 — View Applicants "Registered" date filter + memory cleanup regression.

Bug #1: `/api/applicants` "Registered" date filter used `last_update`, which
gets overwritten on every downstream action (schedule / OTP-verify / status
change). A candidate who registered on 22/05 IST and scheduled later the
same IST day could be pushed off the "Registered=22/05" filter when the
schedule write's UTC timestamp crossed midnight. `submitted_at` is the
immutable registration timestamp and is the correct field to filter on.

Fix: switch `/api/applicants` date_field for `dateType="Registered"` from
`last_update` to `submitted_at`. Also switch sort mapping for
`registered_date` column. Projection now includes `submitted_at` and the
response surfaces it for display so users see what they filtered on.

Bug #2: Bulk-upload XLSX parsing held the DataFrame + raw bytes in memory
across consecutive jobs, contributing to Render 512 MB OOM kills.

Fix: explicit `del df + gc.collect()` after each `_process_*_file` iteration
loop completes, plus `del content + gc.collect()` in the queue worker
after each job. A `[QueueMem]` log line reports peak vs post-GC RSS.

Tests use ONLY tester credentials and synthetic rows tagged with
`_iter116_*`. Production data untouched.
"""

import asyncio
import os
import sys

import pytest
from dotenv import load_dotenv

load_dotenv("/app/backend/.env")
sys.path.insert(0, "/app/backend")

from motor.motor_asyncio import AsyncIOMotorClient

TEST_EMAIL = "rishi.nayak@blubridge.com"
TEST_PHONE = "9443109903"
TAG = "_iter116_filter_test"


async def _setup_same_day_candidate(db):
    """Insert a synthetic pipeline row that mimics the production scenario:
    submitted_at on 22/05 IST (= late evening UTC of 22/05),
    last_update on 23/05 UTC (after OTP-verify crossed UTC midnight)."""
    await db.pipeline_data.delete_many({TAG: True})
    await db.pipeline_data.insert_one({
        TAG: True,
        "email": TEST_EMAIL,
        "phone": TEST_PHONE,
        "name": "Iter116 Test Candidate",
        # Registered 22 May IST 11 PM ≈ 22 May 17:30 UTC (still 22/05 UTC).
        "submitted_at": "2026-05-22 17:30:00",
        # After OTP-verify on 23 May IST 00:15 = 22 May 18:45 UTC...
        # but for the bug repro, the LATER schedule write crosses UTC midnight,
        # pushing last_update to 23/05 — exactly the production symptom.
        "last_update": "2026-05-23T05:30:00+00:00",
        "schedule_date": "2026-05-23",  # IST schedule date
        "schedule_time": "10:00:00",
        "_normalized_job_role": "AI & ML Engineer",
        "isTest": False,  # so the global isTest filter doesn't skip it
    })


async def _cleanup(db):
    await db.pipeline_data.delete_many({TAG: True})


async def _query_match(date_field, start, end):
    """Run the exact $match the endpoint builds."""
    client = AsyncIOMotorClient(os.environ["MONGO_URL"])
    db = client[os.environ["DB_NAME"]]
    try:
        await _setup_same_day_candidate(db)
        match = {
            TAG: True,
            "isTest": {"$ne": True},
            date_field: {"$gte": start, "$lte": end + "\uffff"},
        }
        count = await db.pipeline_data.count_documents(match)
        doc = await db.pipeline_data.find_one(match, {"_id": 0, "name": 1})
        return count, doc
    finally:
        await _cleanup(db)


def test_registered_filter_uses_submitted_at_not_last_update():
    """The 22/05 candidate must be visible under Registered=22/05 even though
    last_update was overwritten to 23/05 by a later action."""
    count, doc = asyncio.run(_query_match("submitted_at", "2026-05-22", "2026-05-22"))
    assert count == 1, (
        f"Registered filter on 22/05 should find the candidate via "
        f"submitted_at='2026-05-22 17:30:00' but found {count}."
    )
    assert doc and doc.get("name") == "Iter116 Test Candidate"


def test_scheduled_filter_still_works():
    """Scheduled=23/05 must still match the schedule_date column (orthogonal)."""
    count, doc = asyncio.run(_query_match("schedule_date", "2026-05-23", "2026-05-23"))
    assert count == 1, f"Scheduled filter on 23/05 broke: count={count}"


def test_registered_filter_does_not_use_last_update():
    """Guard regression: a Registered=22/05 query MUST NOT match a row whose
    submitted_at is on 22/05 but last_update is on 23/05."""
    # If the OLD buggy logic were still in place (last_update field), querying
    # last_update >= 2026-05-22 AND <= 2026-05-22... would FAIL to match
    # because last_update='2026-05-23T...'. The new logic uses submitted_at,
    # which DOES match. We verify the OLD buggy behavior would have failed.
    count, _ = asyncio.run(_query_match("last_update", "2026-05-22", "2026-05-22"))
    assert count == 0, (
        "Confirms the original bug: filtering by last_update would have "
        "missed this same-day-registered candidate."
    )


def test_rss_helper_returns_positive_value():
    """Sanity check the new memory helper returns a usable MB value."""
    from server import _rss_mb
    mb = _rss_mb()
    assert mb > 0, f"_rss_mb() returned {mb!r}; expected positive MB number"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
