"""iter125b regression — Interview Schedule Reports chip dynamic detection.

Validates the fix where role chips on the Interview Schedule Reports page
now surface NEW roles immediately — even when the candidate row has not
yet had `_normalized_job_role` persisted (i.e. fresh upload, background
reprocess pending).

Root cause: `role_counts` aggregation grouped on
`{"$ifNull": ["$_normalized_job_role", "Unknown"]}` only. Rows where
that field was null/empty/"Unknown" were bucketed as "Unknown" and then
filtered out — yet those exact same rows DID appear in the data table
(which uses a `_normalized_job_role → job_role → job_title` fallback).
So a new role's candidate would show in the table but its chip button
was missing — exactly the symptom the user reported.

Fix in `bb_modules.py::get_interview_reports`: replaced the simple
`$ifNull` with a `$let / $cond` chain that mirrors the data-table
fallback. Now chips and rows stay consistent.
"""
import asyncio
import inspect
import os
import sys

from dotenv import load_dotenv

load_dotenv("/app/backend/.env")
sys.path.insert(0, "/app/backend")

from motor.motor_asyncio import AsyncIOMotorClient  # noqa: E402
import server  # noqa: E402
import bb_modules  # noqa: E402

TEST_EMAIL = "iter125b_chip@example.com"
NEW_ROLE = "Iter125b-Brand-New-Role-Chip"
SCHEDULE_DATE = "2026-05-27"
SCHEDULE_TIME = "12:00"


def _fresh_db():
    client = AsyncIOMotorClient(os.environ["MONGO_URL"])
    return client[os.environ["DB_NAME"]], client


async def _cleanup(db):
    await db.pipeline_data.delete_many({"email": TEST_EMAIL})


def test_chip_aggregation_includes_new_role_without_normalized_field():
    """A pipeline_data row inserted with a NEW raw role and NO
    `_normalized_job_role` field must still appear in the chip aggregation."""

    async def _run():
        db, client = _fresh_db()
        original_db = bb_modules._db
        bb_modules._db = db
        try:
            await _cleanup(db)
            await db.pipeline_data.insert_one({
                "email": TEST_EMAIL,
                "phone": "9000125888",
                "name": "iter125b-chip",
                "job_role": NEW_ROLE,
                "schedule_date": SCHEDULE_DATE,
                "schedule_time": SCHEDULE_TIME,
                "isTest": True,
                # intentionally no _normalized_job_role
            })

            # Build the exact aggregation pipeline used by the endpoint
            from server import _build_canonical_index, _canonicalize_job_role, _get_job_keyword_mappings
            kw_to_canonical, _ = await _build_canonical_index()
            raw_mappings = await _get_job_keyword_mappings()
            match = bb_modules._build_interview_reports_match(
                SCHEDULE_DATE, SCHEDULE_DATE, None, None, None,
                _canonical_index=kw_to_canonical, _mappings=raw_mappings,
            )
            role_pipeline = [
                {"$match": match},
                {"$group": {
                    "_id": {
                        "$let": {
                            "vars": {
                                "norm": {"$ifNull": ["$_normalized_job_role", ""]},
                                "jr": {"$ifNull": ["$job_role", ""]},
                                "jt": {"$ifNull": ["$job_title", ""]},
                            },
                            "in": {
                                "$cond": [
                                    {"$and": [
                                        {"$ne": ["$$norm", ""]},
                                        {"$ne": ["$$norm", "Unknown"]},
                                    ]},
                                    "$$norm",
                                    {"$cond": [
                                        {"$ne": ["$$jr", ""]}, "$$jr",
                                        {"$cond": [{"$ne": ["$$jt", ""]}, "$$jt", "Unknown"]},
                                    ]},
                                ],
                            },
                        },
                    },
                    "count": {"$sum": 1},
                }},
            ]
            results = await db.pipeline_data.aggregate(role_pipeline).to_list(None)
            chips = {r["_id"]: r["count"] for r in results if r["_id"] not in (None, "", "Unknown")}
            assert NEW_ROLE in chips, (
                f"New role {NEW_ROLE!r} must appear in chip aggregation when "
                f"_normalized_job_role is missing. Got chips: {list(chips.keys())[:10]}"
            )
            assert chips[NEW_ROLE] >= 1
        finally:
            await _cleanup(db)
            bb_modules._db = original_db
            client.close()

    asyncio.run(_run())


def test_endpoint_uses_fallback_chain_for_chip_id():
    """Source-code guard: the get_interview_reports endpoint must use a
    `$let / $cond` fallback chain for the role chip aggregation, not a
    simple `$ifNull` on `_normalized_job_role` only."""
    src = inspect.getsource(bb_modules.get_interview_reports)
    # The fix uses $let with $cond — old buggy version was simple $ifNull
    assert "$let" in src and "$cond" in src and "$$norm" in src, (
        "get_interview_reports must use $let/$cond fallback chain in chip aggregation"
    )
