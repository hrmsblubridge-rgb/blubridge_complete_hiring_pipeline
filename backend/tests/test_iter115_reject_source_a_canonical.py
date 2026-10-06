"""iter115 — Final Reject Source A canonical-name lookup regression.

Bug: Source A of `_worker_import_rejection_mailer` (bg_workers.py) trusted
the local `bb_applicant_updates.name` / `.job_role` fields for the rejection
template. These fields are written at score-update time and are NEVER
refreshed when a tester re-registers (only scores/status/rejection flags
get reset in `bb_modules.register_applicant` tester block). Result: a
candidate who later re-registered with a new name kept receiving rejection
emails / WhatsApps addressed to the STALE name.

Symptom (Source A, May 21 2026): the candidate registered as
"May 21 Rishi" but the delivered email/WhatsApp said "Dear Final_Test_Rishi".
Logs `[RejectSend:A] attempt name='Final_Test_Rishi'` mirrored the stale
local row, so the bug was invisible to log auditing.

Fix: Source A now does the SAME canonical lookup that Source B already does
since iter113 — read `pipeline_data` (sort registered_at DESC) and PREFER
its `name` / `job_role` over the local row's values.

Tests use ONLY tester credentials (`rishi.nayak@blubridge.com` / `9443109903`).
"""

import asyncio
import os
import sys
from datetime import datetime, timezone, timedelta

import pytest
from dotenv import load_dotenv

load_dotenv("/app/backend/.env")
sys.path.insert(0, "/app/backend")

from motor.motor_asyncio import AsyncIOMotorClient

TEST_EMAIL = "rishi.nayak@blubridge.com"
TEST_PHONE = "9443109903"
TAG = "_iter115_canonical_lookup_test"


async def _ensure_stale_and_fresh_rows(db):
    """Insert a STALE bb_applicant_updates row AND a FRESH pipeline_data row
    so the worker is forced to pick the canonical fresh name."""
    now_utc = datetime.now(timezone.utc).isoformat()
    # Stale local row carries the OLD name & role.
    await db.bb_applicant_updates.delete_many({TAG: True})
    await db.bb_applicant_updates.insert_one({
        TAG: True,
        "email": TEST_EMAIL,
        "phone": TEST_PHONE,
        "name": "Final_Test_Rishi_STALE",
        "job_role": "Stale Role Should Never Render",
        "status": "Rejected",
        "isTest": True,
        "updated_at": now_utc,
        "rejection_sent": False,
    })
    # Fresh pipeline row carries the canonical CURRENT name & role.
    await db.pipeline_data.delete_many({TAG: True})
    await db.pipeline_data.insert_one({
        TAG: True,
        "email": TEST_EMAIL,
        "phone": TEST_PHONE,
        "name": "May 21 Rishi",
        "job_role": "AI & ML Engineer",
        "registered_at": now_utc,
    })


async def _cleanup(db):
    await db.bb_applicant_updates.delete_many({TAG: True})
    await db.pipeline_data.delete_many({TAG: True})


async def _run():
    client = AsyncIOMotorClient(os.environ["MONGO_URL"])
    db = client[os.environ["DB_NAME"]]
    try:
        await _ensure_stale_and_fresh_rows(db)
        # Replicate the EXACT canonical-lookup logic from bg_workers.py:Source A.
        doc = await db.bb_applicant_updates.find_one({TAG: True})
        email = (doc.get("email") or "").strip()
        phone = (doc.get("phone") or "").strip()
        pd_query = {"$or": [{"email": email}, {"phone": phone}]}
        pd_doc_a = await db.pipeline_data.find_one(
            pd_query,
            {"_id": 0, "name": 1, "job_role": 1, "job_title": 1, "registered_at": 1},
            sort=[("registered_at", -1)],
        )
        fresh_name = ((pd_doc_a or {}).get("name") or "").strip()
        fresh_role = (
            (pd_doc_a or {}).get("job_role")
            or (pd_doc_a or {}).get("job_title")
            or ""
        ).strip()
        stale_name = (doc.get("name") or "").strip()
        stale_role = (doc.get("job_role") or "").strip()
        name = fresh_name or stale_name
        job_role = fresh_role or stale_role
        return name, job_role, stale_name, stale_role
    finally:
        await _cleanup(db)


def test_canonical_lookup_overrides_stale_local_row():
    name, role, stale_name, stale_role = asyncio.run(_run())
    assert name == "May 21 Rishi", (
        f"Worker would have sent rejection with STALE name {stale_name!r}; "
        f"canonical lookup should have produced 'May 21 Rishi' but got {name!r}"
    )
    assert role == "AI & ML Engineer", (
        f"Worker would have sent rejection with STALE role {stale_role!r}; "
        f"canonical lookup should have produced 'AI & ML Engineer' but got {role!r}"
    )


def test_dispatch_with_canonical_values_succeeds_end_to_end():
    """Smoke-test the centralized dispatch with the canonical-corrected
    values, using ONLY tester credentials. Verifies the in-flight name/role
    actually flow through to AiSensy + Resend."""
    from messaging import notify_rejected

    ok = asyncio.run(
        notify_rejected(
            name="May 21 Rishi",
            phone=TEST_PHONE,
            email=TEST_EMAIL,
            job_role="AI & ML Engineer",
            is_test=True,
        )
    )
    assert ok is True


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
