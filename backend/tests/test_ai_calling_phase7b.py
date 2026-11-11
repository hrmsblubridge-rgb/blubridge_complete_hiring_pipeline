"""Phase 7B: candidate consent via booking token, withdrawal, failure handling, real-booking dry-run preview.
SCRATCH DB only; Bolna and messaging are never touched."""
import asyncio
from datetime import date, timedelta

import httpx
import pytest
from fastapi import FastAPI
from motor.motor_asyncio import AsyncIOMotorClient

from ai_calling import bolna_client as bc
from ai_calling import consent, modes, store
from ai_calling.store import SETTINGS_DEFAULTS

SCRATCH = "ai_phase7b_pytest_scratch"
TOKEN = "tok_" + "a" * 24
FUT = (date.today() + timedelta(days=4)).isoformat()
V = modes.CONSENT_TEXT_VERSION


def reg(**kw):
    d = {"full_name": "Synthetic Person", "phone": "+919000000301", "email": "s1@example.invalid", "status": "Interview Scheduled",
         "is_shortlisted": True, "schedule_date": FUT, "schedule_time": "11:00:00", "otp_verified": False, "missed_marked": False,
         "superseded": False, "reschedule_count": 0, "isTest": False, "schedule_token": TOKEN, "job_role": "Analyst"}
    d.update(kw)
    return d


def run(monkeypatch, case):
    async def main():
        client = AsyncIOMotorClient("mongodb://localhost:27017")
        d = client[SCRATCH]
        await client.drop_database(SCRATCH)
        await d.ai_call_settings.insert_one({"_id": "global", **SETTINGS_DEFAULTS})
        await d.ai_candidate_consents.create_index("registration_id", unique=True)

        async def auth(_r):
            return "pytest-admin"

        async def boom(*_a, **_k):
            raise AssertionError("no provider request in Phase 7B")
        monkeypatch.setitem(store._state, "db", d)
        monkeypatch.setitem(store._state, "auth", auth)
        monkeypatch.setattr(bc, "place_call", boom)
        monkeypatch.setattr(bc, "_get", boom)
        monkeypatch.setattr(modes, "overall_test_mode", lambda: True)
        app = FastAPI()
        for r in (consent.public_router, consent.admin_router, modes.modes_router):
            app.include_router(r)
        try:
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as tc:
                await case(tc, d)
        finally:
            await client.drop_database(SCRATCH)
    asyncio.run(main())


@pytest.mark.skip(reason="Phase 7C-A replaced schedule-token consent management with dedicated hashed tokens; covered by test_ai_calling_phase7ca.py")
def test_info_defaults_and_token_required(monkeypatch):
    async def case(tc, d):
        await d.bb_registrations.insert_one(reg())
        r = (await tc.get(f"/public/consent/{TOKEN}")).json()
        assert r["consent_status"] == "not_given" and r["version"] == V and "withdraw" in r["text"]
        assert "phone" not in r and "email" not in r
        assert (await tc.get("/public/consent/short")).status_code == 404
        assert (await tc.get("/public/consent/" + "b" * 24)).status_code == 404
        assert await d.ai_candidate_consents.count_documents({}) == 0  # historical: nothing assumed
    run(monkeypatch, case)


@pytest.mark.skip(reason="Phase 7C-A replaced schedule-token consent management with dedicated hashed tokens; covered by test_ai_calling_phase7ca.py")
@pytest.mark.parametrize("granted,expect", [(True, "granted"), (False, "not_given")])
def test_booking_decision_linked_to_registration(monkeypatch, granted, expect):
    async def case(tc, d):
        rid = str((await d.bb_registrations.insert_one(reg())).inserted_id)
        before = await d.bb_registrations.find_one({})
        for _ in range(3):  # duplicate submissions are idempotent
            r = await tc.post(f"/public/consent/{TOKEN}", json={"granted": granted, "text_version": V})
            assert r.status_code == 200 and r.json() == {"saved": True, "consent_status": expect}
        c = await d.ai_candidate_consents.find_one({})
        assert c["registration_id"] == rid and c["consent_text_version"] == V and c["consent_source"] == "booking_form"
        assert await d.ai_candidate_consents.count_documents({}) == 1 and len(c["history"]) == 3
        assert await d.bb_registrations.find_one({}) == before  # booking record untouched
    run(monkeypatch, case)


@pytest.mark.skip(reason="Phase 7C-A replaced schedule-token consent management with dedicated hashed tokens; covered by test_ai_calling_phase7ca.py")
def test_stale_version_and_no_booking(monkeypatch):
    async def case(tc, d):
        await d.bb_registrations.insert_one(reg(schedule_date=None))
        assert (await tc.post(f"/public/consent/{TOKEN}", json={"granted": True, "text_version": V})).status_code == 409
        await d.bb_registrations.update_one({}, {"$set": {"schedule_date": FUT}})
        assert (await tc.post(f"/public/consent/{TOKEN}", json={"granted": True, "text_version": "old"})).status_code == 409
        assert await d.ai_candidate_consents.count_documents({}) == 0
    run(monkeypatch, case)


@pytest.mark.skip(reason="Phase 7C-A replaced schedule-token consent management with dedicated hashed tokens; covered by test_ai_calling_phase7ca.py")
def test_persist_failure_never_claims_saved(monkeypatch):
    async def case(tc, d):
        await d.bb_registrations.insert_one(reg())

        async def broken(*_a, **_k):
            raise RuntimeError("db down")
        monkeypatch.setattr(consent, "record_consent", broken)
        r = await tc.post(f"/public/consent/{TOKEN}", json={"granted": True, "text_version": V})
        assert r.status_code == 503 and "NOT given" in r.json()["detail"]
        assert await d.ai_candidate_consents.count_documents({}) == 0
        assert (await d.ai_call_audit.find_one({}))["action"] == "consent_persist_failed"
    run(monkeypatch, case)


@pytest.mark.skip(reason="Phase 7C-A replaced schedule-token consent management with dedicated hashed tokens; covered by test_ai_calling_phase7ca.py")
def test_withdraw_cancels_pending_and_keeps_interview(monkeypatch):
    async def case(tc, d):
        rid = str((await d.bb_registrations.insert_one(reg())).inserted_id)
        await tc.post(f"/public/consent/{TOKEN}", json={"granted": True, "text_version": V})
        await d.ai_call_jobs.insert_many([{"mode": "live", "registration_id": rid, "status": "pending"},
                                          {"mode": "live", "registration_id": "other", "status": "pending"}])
        r = (await tc.post(f"/public/consent/{TOKEN}/withdraw")).json()
        assert r["consent_status"] == "withdrawn" and r["interview_unchanged"]
        assert (await d.ai_call_jobs.find_one({"registration_id": rid}))["status"] == "cancelled"
        assert (await d.ai_call_jobs.find_one({"registration_id": "other"}))["status"] == "pending"
        assert (await d.bb_registrations.find_one({}))["schedule_date"] == FUT
        k = {c["key"]: c for c in (await modes.evaluate_live(registration_id=rid, job_mode_version=1, overall=True))["checks"]}
        assert "CONSENT_WITHDRAWN" in k["eligible"]["detail"]
    run(monkeypatch, case)


def test_real_preview_read_only_and_reasons(monkeypatch):
    async def case(tc, d):
        ids = (await d.bb_registrations.insert_many([
            reg(), reg(full_name="No consent", schedule_token="t2" + "x" * 20, phone="+919000000302"),
            reg(full_name="Attended", status="Attended", otp_verified=True, schedule_token="t3" + "x" * 20),
            reg(full_name="Superseded", superseded=True, schedule_token="t4" + "x" * 20),
            reg(full_name="Bad phone", phone="123", schedule_token="t5" + "x" * 20),
            reg(full_name="Not booked", schedule_date=None, schedule_token="t6" + "x" * 20)])).inserted_ids
        await d.ai_candidate_consents.insert_many([{"registration_id": str(i), "consent_status": "granted"} for i in ids[:1] + ids[2:5]])
        snap = await d.bb_registrations.find().to_list(10)
        r = (await tc.get("/dry-run/real-preview")).json()
        assert r["bookings"] == 5 and r["eligible"] == 1 and "DRY RUN" in r["warning"]
        by = {x["candidate_name"]: x for x in r["rows"]}
        assert by["Synthetic Person"]["status"] == "SCHEDULED" and by["Synthetic Person"]["registration_id"] == str(ids[0])
        assert "NO_CALLING_CONSENT" in by["No consent"]["reasons"] and "ATTENDED" in by["Attended"]["reasons"]
        assert "SUPERSEDED" in by["Superseded"]["reasons"] and "INVALID_PHONE" in by["Bad phone"]["reasons"]
        assert await d.bb_registrations.find().to_list(10) == snap
        assert await d.ai_call_jobs.count_documents({}) == 0 and await d.ai_dry_run_jobs.count_documents({}) == 0
    run(monkeypatch, case)


def test_live_authorization_stays_disabled_and_audited(monkeypatch):
    async def case(tc, d):
        h = {"X-CSRF-Intent": "ai-calling"}
        r = await tc.post("/live-dispatch/authorize", json={"confirmation": modes.LIVE_AUTH_PHRASE}, headers=h)
        assert r.status_code == 423
        a = await d.ai_call_audit.find_one({"action": "live_dispatch_authorize_attempt"})
        assert a["preconditions"]["typed_confirmation"] is True and a["preconditions"]["dispatch_implemented"] is False
        s = await d.ai_call_settings.find_one({"_id": "global"})
        assert s["live_dispatch_authorized"] is False and s["emergency_stop"] is True
        st = (await tc.get("/switches")).json()
        assert st["live_limits"]["daily"] == 20 and st["live_limits"]["concurrent"] == 1
    run(monkeypatch, case)
