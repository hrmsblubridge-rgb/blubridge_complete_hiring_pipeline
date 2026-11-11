"""Phase 6 dry-run planner tests: pure timing rules + scratch-DB planning. No provider, no messaging, no real data."""
import asyncio
import sys
from datetime import datetime, timedelta

import pytest
from fastapi import HTTPException
from motor.motor_asyncio import AsyncIOMotorClient

from ai_calling import dryrun, store
from ai_calling.store import IST, SETTINGS_DEFAULTS

CFG = {**SETTINGS_DEFAULTS}
SCRATCH = "ai_phase6_pytest_scratch"
NOW = datetime(2026, 7, 1, 12, 0, tzinfo=IST)  # Wednesday 12:00 IST


def bk(**kw):
    b = {"synthetic": True, "full_name": "Synthetic", "phone": "+919000000001", "status": "Interview Scheduled",
         "is_shortlisted": True, "otp_verified": False, "missed_marked": False, "superseded": False, "reschedule_count": 0,
         "isTest": False, "ai_call_consent": {"status": "granted"}, "do_not_call": False,
         "schedule_date": "2026-07-04", "schedule_time": "11:00:00", "job_role": "Analyst"}
    b.update(kw)
    return b


def p(**kw):
    return dryrun.plan_booking(bk(**kw), NOW, CFG)


def test_more_than_24h_ahead_plans_exactly_24h_before():
    r = p()
    assert r["status"] == "SCHEDULED" and r["planned_at"] == "2026-07-03T11:00:00+05:30" and r["adjustments"] == []
    assert r["retry"] == {"allowed_in_live": 1, "eligible": True, "planned_at": "2026-07-03T12:00:00+05:30", "executed": False}


def test_outside_window_moves_forward_never_earlier():
    early = p(schedule_time="09:00:00")
    assert early["target_at"] == "2026-07-03T09:00:00+05:30" and early["planned_at"] == "2026-07-03T10:00:00+05:30"
    late = p(schedule_time="20:30:00")
    assert late["planned_at"] == "2026-07-04T10:00:00+05:30" and late["status"] == "SCHEDULED"
    assert any("window" in a for a in late["adjustments"])


def test_date_boundary_and_needs_review():
    r = p(schedule_date="2026-07-04", schedule_time="00:30:00")  # target 03 00:30 -> 03 10:00
    assert r["planned_at"] == "2026-07-03T10:00:00+05:30" and r["status"] == "SCHEDULED"
    r = p(schedule_date="2026-07-04", schedule_time="11:30:00")  # 24h target 03 11:30 fine
    assert r["status"] == "SCHEDULED"
    r = dryrun.plan_booking(bk(schedule_date="2026-07-02", schedule_time="11:00:00"), datetime(2026, 7, 1, 19, 30, tzinfo=IST), CFG)
    assert r["short_notice"] and r["planned_at"] == "2026-07-02T10:00:00+05:30" and r["status"] == "NEEDS_REVIEW"
    assert r["reasons"] == ["INSUFFICIENT_LEAD_TIME"]


def test_short_notice_next_permitted_time():
    r = p(schedule_date="2026-07-01", schedule_time="17:00:00")
    assert r["short_notice"] and r["planned_at"] == "2026-07-01T12:05:00+05:30" and r["status"] == "SCHEDULED"
    assert datetime.fromisoformat(r["planned_at"]) >= NOW
    r = p(schedule_date="2026-07-01", schedule_time="13:30:00")
    assert r["status"] == "NEEDS_REVIEW"


def test_retry_not_eligible_when_too_close():
    r = p(schedule_date="2026-07-01", schedule_time="15:00:00")  # planned 12:05, retry 13:05 -> <2h before 15:00
    assert r["status"] == "SCHEDULED" and r["retry"]["eligible"] is False and r["retry"]["executed"] is False


@pytest.mark.parametrize("kw,reason", [
    ({"superseded": True}, "SUPERSEDED"), ({"status": "Cancelled"}, "CANCELLED"), ({"status": "Rejected"}, "REJECTED"),
    ({"status": "Attended", "otp_verified": True}, "ATTENDED"), ({"otp_verified": "1"}, "ATTENDED"),
    ({"status": "Missed", "missed_marked": True}, "MISSED"), ({"status": "Interview Not Scheduled"}, "NOT_BOOKED"),
    ({"status": "Scheduled"}, "MANUAL_ALERT_BOOKING"), ({"is_shortlisted": False}, "NOT_SHORTLISTED"),
    ({"isTest": True}, "TEST_RECORD"), ({"phone": "12345"}, "INVALID_PHONE"), ({"phone": None}, "INVALID_PHONE"),
    ({"ai_call_consent": None}, "NO_CALLING_CONSENT"), ({"ai_call_consent": {"status": "refused"}}, "CONSENT_REFUSED"),
    ({"ai_call_consent": {"status": "withdrawn"}}, "CONSENT_WITHDRAWN"), ({"do_not_call": True}, "DO_NOT_CALL"),
    ({"ai_confirmation": "CONFIRMED"}, "ALREADY_CONFIRMED"), ({"schedule_date": None}, "NO_SCHEDULE"),
    ({"schedule_time": "banana"}, "INVALID_SCHEDULE"), ({"schedule_date": "2026-06-30"}, "INTERVIEW_PASSED"),
])
def test_ineligible_reasons(kw, reason):
    r = p(**kw)
    assert r["status"] == "SKIPPED" and reason in r["reasons"]


def test_module_has_no_dispatch_path():
    src = open(dryrun.__file__).read()
    assert "bolna_client" not in src and "place_call" not in src and "messaging" not in src
    assert "bb_registrations" not in src.split('"""', 2)[2]  # only mentioned in the docstring


def run(monkeypatch, case):
    async def main():
        client = AsyncIOMotorClient("mongodb://localhost:27017")
        d = client[SCRATCH]
        await client.drop_database(SCRATCH)
        monkeypatch.setitem(store._state, "db", d)
        await d.ai_call_settings.insert_one({"_id": "global", **SETTINGS_DEFAULTS, "mode": "testing", "emergency_stop": True})
        await dryrun.ensure_dry_run_indexes()
        try:
            await case(d)
        finally:
            await client.drop_database(SCRATCH)
    asyncio.run(main())


def test_idempotent_reschedule_and_removal(monkeypatch):
    async def case(d):
        ids = (await d.ai_dry_run_bookings.insert_many([bk(), bk(full_name="B", status="Cancelled")])).inserted_ids
        s1 = await dryrun.run_planning("t", NOW)
        s2 = await dryrun.run_planning("t", NOW)
        assert s1["counts"] == s2["counts"] == {"SCHEDULED": 1, "SKIPPED": 1, "NEEDS_REVIEW": 0, "INVALIDATED": 0}
        assert await d.ai_dry_run_jobs.count_documents({}) == 2
        assert (await d.ai_dry_run_jobs.find_one({"booking_id": str(ids[0])}))["times_planned"] == 2
        await d.ai_dry_run_bookings.update_one({"_id": ids[0]}, {"$set": {"schedule_date": "2026-07-05"}, "$inc": {"reschedule_count": 1}})
        s3 = await dryrun.run_planning("t", NOW)
        assert s3["counts"]["INVALIDATED"] == 1
        jobs = await d.ai_dry_run_jobs.find({"booking_id": str(ids[0])}).to_list(10)
        assert sorted(j["status"] for j in jobs) == ["INVALIDATED", "SCHEDULED"]
        assert [j for j in jobs if j["status"] == "INVALIDATED"][0]["reasons"] == ["RESCHEDULED"]
        await d.ai_dry_run_bookings.delete_one({"_id": ids[1]})
        assert (await dryrun.run_planning("t", NOW))["counts"]["INVALIDATED"] == 1
        assert all(j["mode"] == "DRY_RUN" and j["dry_run"] for j in await d.ai_dry_run_jobs.find().to_list(10))
        assert await d.ai_call_jobs.count_documents({}) == 0 and await d.ai_calls.count_documents({}) == 0
        s = await d.ai_call_settings.find_one({"_id": "global"})
        assert s["mode"] == "testing" and s["emergency_stop"] is True
    run(monkeypatch, case)


def test_two_planners_concurrently(monkeypatch):
    async def case(d):
        await d.ai_dry_run_bookings.insert_many([bk(full_name=f"S{i}", phone=f"+91900000{i:04d}") for i in range(30)])
        rs = await asyncio.gather(*[dryrun.run_planning("t", NOW) for _ in range(4)], return_exceptions=True)
        ok = [r for r in rs if isinstance(r, dict)]
        assert ok and all(isinstance(r, HTTPException) and r.status_code == 409 for r in rs if not isinstance(r, dict))
        assert await d.ai_dry_run_jobs.count_documents({}) == 30
        assert (await d.ai_dry_run_state.find_one({"_id": "planner"}))["lock"] is None
        # concurrent upserts without the lock still cannot duplicate (unique booking_id+booking_key)
        await asyncio.gather(*[d.ai_dry_run_jobs.update_one({"booking_id": "x", "booking_key": "k"}, {"$set": {"status": "SKIPPED"}},
                                                            upsert=True) for _ in range(5)], return_exceptions=True)
        assert await d.ai_dry_run_jobs.count_documents({"booking_id": "x"}) == 1
        claims = await asyncio.gather(*[dryrun.claim_due_dry_run_job(NOW + timedelta(days=10), f"w{i}") for i in range(40)])
        got = [c["booking_id"] for c in claims if c]
        assert len(got) == len(set(got)) == 30  # every due job claimed exactly once, simulation only
    run(monkeypatch, case)


def test_stale_lock_is_recovered(monkeypatch):
    async def case(d):
        await d.ai_dry_run_state.insert_one({"_id": "planner", "lock": {"id": "dead", "at": "2000-01-01T00:00:00+00:00"}})
        assert (await dryrun.run_planning("t", NOW))["bookings"] == 0
    run(monkeypatch, case)


def test_no_provider_or_messaging_imported_by_planner():
    assert "messaging" not in sys.modules or not hasattr(dryrun, "messaging")
