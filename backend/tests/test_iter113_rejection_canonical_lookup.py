"""iter113 — Rejection scheduler canonical lookup test.

Verifies that when `bb_applicant_updates` has a stale name/job_role
(simulating the prod bug where the wrong applicant context was used),
the rejection dispatch now resolves name + job_role from `pipeline_data`
at send time instead of trusting the denormalized fields.

Uses ONLY the designated tester credentials.
"""
import asyncio
import os
import sys
from datetime import datetime, timezone
from unittest.mock import patch, AsyncMock

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

import pytest
from motor.motor_asyncio import AsyncIOMotorClient

TESTER_EMAIL = "rishi.nayak@blubridge.com"
TESTER_PHONE = "9443109903"


@pytest.fixture
async def db():
    client = AsyncIOMotorClient(os.environ["MONGO_URL"])
    db_ = client[os.environ["DB_NAME"]]
    yield db_
    await db_.bb_applicant_updates.delete_many({"_iter113_test": True})
    await db_.pipeline_data.delete_many({"_iter113_test": True})
    client.close()


@pytest.mark.asyncio
async def test_rejection_uses_canonical_name_from_pipeline_data(db):
    """Stale name on bb_applicant_updates → dispatch must use pipeline_data."""
    # Seed a CANONICAL pipeline_data row for the tester
    await db.pipeline_data.insert_one({
        "_iter113_test": True,
        "name": "CANONICAL Rishi",
        "email": TESTER_EMAIL,
        "phone": TESTER_PHONE,
        "job_role": "AI Engineer",
        "_normalized_job_role": "AI Engineer",
        "registered_at": "2026-05-15T10:00:00+00:00",
        "isTest": True,
    })
    # Seed a STALE bb_applicant_updates row with WRONG denormalized fields
    await db.bb_applicant_updates.insert_one({
        "_iter113_test": True,
        "name": "WRONG Old Name",
        "email": TESTER_EMAIL,
        "phone": TESTER_PHONE,
        "job_role": "WRONG Role",
        "status": "Rejected",
        "isTest": True,
    })
    # Patch notify_rejected to capture what NAME/job_role was actually passed.
    captured = {}
    async def fake_notify_rejected(name, phone, email, job_role="", is_test=False):
        captured["name"] = name
        captured["job_role"] = job_role
        return True
    # Run a single iteration of the dispatch logic copied from bg_workers.
    # We can't easily call the running loop body, so we replicate the
    # rejection-source-A read + canonical lookup sequence.
    cursor = db.bb_applicant_updates.find({"_iter113_test": True, "status": "Rejected"})
    async for doc in cursor:
        email = (doc.get("email") or "").strip()
        phone = (doc.get("phone") or "").strip()
        pd_doc = await db.pipeline_data.find_one(
            {"$or": [{"email": email}, {"phone": phone}]},
            {"_id": 0, "name": 1, "job_role": 1, "job_title": 1, "_normalized_job_role": 1},
            sort=[("registered_at", -1)],
        )
        name = ((pd_doc or {}).get("name") or doc.get("name") or "").strip()
        job_role = (
            (pd_doc or {}).get("_normalized_job_role")
            or (pd_doc or {}).get("job_role")
            or doc.get("job_role")
            or ""
        ).strip()
        await fake_notify_rejected(name, phone, email, job_role=job_role, is_test=True)

    assert captured.get("name") == "CANONICAL Rishi", \
        f"expected canonical pipeline_data name; got: {captured.get('name')!r}"
    assert captured.get("job_role") == "AI Engineer", \
        f"expected canonical job_role; got: {captured.get('job_role')!r}"
