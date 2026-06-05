"""iter142 — Applicants Summary Statistics keyword-mapping rollup.

The /api/summary endpoint must collapse rows whose raw `_normalized_job_role`
maps to the same canonical title via `job_keyword_mapping`. Previously,
the page showed one row per raw role even after the recruiter created a
mapping, because `_normalized_job_role` is persisted at ingestion-time
and isn't re-derived on mapping changes.

Test plan:
  1. Insert two synthetic pipeline_data rows under DIFFERENT raw roles
     ("Iter142 Sr Eng" and "Iter142 Senior Software Engineer").
  2. Create a job_keyword_mapping that points BOTH keywords to canonical
     "Iter142 Canonical Senior Engineer".
  3. Call /api/summary?startDate=…&endDate=… and assert the response
     contains exactly ONE row for the canonical title, with totals
     summed across the two raw entries.
  4. Search by the canonical title should still surface the rows even
     when raw `_normalized_job_role` doesn't contain that substring.
"""

import asyncio
import os
import sys
from datetime import datetime, timezone

import pytest
import pytest_asyncio
from dotenv import load_dotenv
from httpx import AsyncClient, ASGITransport

load_dotenv("/app/backend/.env")
sys.path.insert(0, "/app/backend")

from motor.motor_asyncio import AsyncIOMotorClient

TAG = "_iter142_keyword_rollup_test"
CANON = "Iter142 Canonical Senior Engineer"
KW1 = "Iter142 Sr Eng"
KW2 = "Iter142 Senior Software Engineer"


@pytest_asyncio.fixture
async def db():
    client = AsyncIOMotorClient(os.environ["MONGO_URL"])
    d = client[os.environ["DB_NAME"]]
    yield d


@pytest_asyncio.fixture
async def http_client():
    from server import app, get_current_user
    # Bypass auth at the dependency level — this test is exercising
    # /api/summary's logic, not its auth contract.
    app.dependency_overrides[get_current_user] = lambda: "iter142-test"
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client
    app.dependency_overrides.clear()


async def _seed_rows(db, today_iso):
    """Two synthetic rows under DIFFERENT raw roles + a tag for cleanup."""
    await db.pipeline_data.delete_many({TAG: True})
    docs = [
        {
            TAG: True,
            "email": "iter142_a@example.com",
            "phone": "9999900001",
            "name": "Iter142 A",
            "submitted_at": today_iso + " 10:00:00",
            "last_update": today_iso + "T10:00:00+00:00",
            "email_type": "shortlist",
            "schedule_date": today_iso,
            "schedule_time": "10:00",
            "otp_verified": 1,
            "_normalized_job_role": KW1,
            "_nirf_category": "Non NIRF",
            "job_role": KW1,
        },
        {
            TAG: True,
            "email": "iter142_b@example.com",
            "phone": "9999900002",
            "name": "Iter142 B",
            "submitted_at": today_iso + " 11:00:00",
            "last_update": today_iso + "T11:00:00+00:00",
            "email_type": "rejected",
            "schedule_date": None,
            "schedule_time": None,
            "otp_verified": None,
            "_normalized_job_role": KW2,
            "_nirf_category": "Non NIRF",
            "job_role": KW2,
        },
    ]
    await db.pipeline_data.insert_many(docs)


async def _seed_mapping(db):
    """Create a job_keyword_mapping pointing both raw roles → canonical."""
    await db.job_keyword_mapping.delete_many({"job_role": CANON})
    await db.job_keyword_mapping.insert_one({
        "job_role": CANON,
        "keywords": [KW1, KW2],
    })


async def _cleanup(db):
    await db.pipeline_data.delete_many({TAG: True})
    await db.job_keyword_mapping.delete_many({"job_role": CANON})


@pytest.mark.asyncio
async def test_summary_rolls_up_via_keyword_mapping_and_search(db, http_client):
    """Combined test — rollup + canonical-token search expansion.

    Two scenarios in one test to side-step the motor + pytest-asyncio
    "event loop is closed" cross-test issue (the motor client gets bound
    to the first event loop and breaks on the next test's fresh loop).
    """
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    try:
        await _seed_rows(db, today)
        await _seed_mapping(db)

        # ── Scenario 1: pure rollup, no search ────────────────────────
        r = await http_client.get(
            "/api/summary", params={"startDate": today, "endDate": today}
        )
        assert r.status_code == 200, r.text
        rows = r.json()["data"]
        canon_rows = [x for x in rows if x["job_role"].startswith(CANON)]
        assert canon_rows, (
            f"Canonical role {CANON!r} not in summary; got rows: "
            f"{[r['job_role'] for r in rows]}"
        )
        assert len(canon_rows) == 1, (
            f"Expected exactly one row for the canonical title; got "
            f"{[r['job_role'] for r in canon_rows]}"
        )
        row = canon_rows[0]
        assert row["total_registered"] == 2, row
        assert row["shortlisted"] == 1, row
        assert row["rejected"] == 1, row
        assert row["scheduled"] == 1, row
        assert row["not_scheduled"] == 1, row
        assert row["attended"] == 1, row
        for raw in (KW1, KW2):
            offenders = [x for x in rows if x["job_role"].startswith(raw + " -")]
            assert not offenders, (
                f"Raw role {raw!r} surfaced as its own row instead of "
                f"being rolled up into {CANON!r}: {offenders}"
            )

        # ── Scenario 2: search by a token only present in the canonical
        # title. Neither raw keyword contains "Canonical", so the OLD
        # code returned zero rows.
        r = await http_client.get(
            "/api/summary",
            params={
                "startDate": today, "endDate": today,
                "search": "Iter142 Canonical",
            },
        )
        assert r.status_code == 200, r.text
        rows = r.json()["data"]
        canon_rows = [x for x in rows if x["job_role"].startswith(CANON)]
        assert canon_rows, (
            f"Searching by canonical token failed to surface mapped raw "
            f"rows; got: {[x['job_role'] for x in rows]}"
        )
        assert canon_rows[0]["total_registered"] == 2
    finally:
        await _cleanup(db)
