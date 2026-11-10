"""Phase 5: candidate-profile call history isolation tests on a SCRATCH DB. No Bolna requests at all."""
import asyncio

import httpx
from bson import ObjectId
from fastapi import FastAPI
from motor.motor_asyncio import AsyncIOMotorClient

from ai_calling import bolna_client as bc
from ai_calling import dispatch, gate, store

SCRATCH = "ai_phase5_pytest_scratch"
H = {"X-CSRF-Intent": "ai-calling"}


def run(monkeypatch, case, authed=True):
    async def main():
        client = AsyncIOMotorClient("mongodb://localhost:27017")
        db = client[SCRATCH]
        await client.drop_database(SCRATCH)

        async def auth(_r):
            if not authed:
                from fastapi import HTTPException
                raise HTTPException(401, "Not authenticated")
            return "pytest-admin"

        async def boom(*_a, **_k):
            raise AssertionError("Bolna must not be called in Phase 5")
        monkeypatch.setitem(store._state, "db", db)
        monkeypatch.setitem(store._state, "auth", auth)
        monkeypatch.setattr(bc, "place_call", boom)
        monkeypatch.setattr(bc, "_get", boom)
        app = FastAPI()
        app.include_router(dispatch.dispatch_router)
        try:
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as tc:
                await case(tc, db)
        finally:
            await client.drop_database(SCRATCH)
    asyncio.run(main())


def _call(**kw):
    d = {"mode": "live", "state": "finished", "status": "completed", "candidate_name": "Synthetic", "phone_masked": "+91*****0000",
         "recipient_e164": "+919999900000", "recording_url": "https://rec.invalid/x.mp3", "transcript": "assistant: hi",
         "response": {"attendance_status": "CONFIRMED", "wants_reschedule": False}, "created_at": "2026-06-01T10:00:00+00:00"}
    d.update(kw)
    return d


def test_only_live_calls_for_exact_registration(monkeypatch):
    async def case(tc, db):
        reg = (await db.bb_registrations.insert_one({"email": "real@example.com", "phone": "9999900000"})).inserted_id
        other = str(ObjectId())
        await db.ai_calls.insert_many([
            _call(registration_id=str(reg)),
            _call(registration_id=other),
            _call(mode="testing", registration_id=str(reg), test_candidate_id="t1"),
            _call(mode="testing", test_candidate_id="t2"),  # same phone as the real candidate
            _call(registration_id=None),
        ])
        ids = (await tc.get("/registrations/lookup", params={"email": " REAL@example.com "})).json()["registration_ids"]
        assert ids == [str(reg)]
        r = (await tc.get(f"/calls/by-registration/{reg}")).json()
        assert r["total"] == 1 and r["items"][0]["mode"] == "live"
        item = r["items"][0]
        assert "recording_url" not in item and "recipient_e164" not in item and item["has_recording"] is True
        assert (await tc.get(f"/calls/by-registration/{other}")).json()["total"] == 1
        assert (await tc.get(f"/calls/by-registration/{ObjectId()}")).json() == {"items": [], "total": 0, "page": 1, "page_size": 10}
        assert (await tc.get("/calls/by-registration/not-an-id")).status_code == 400
        assert (await tc.get("/registrations/lookup", params={"email": "x"})).status_code == 400
        assert (await tc.get("/registrations/lookup", params={"email": "nobody@example.com"})).json()["registration_ids"] == []
        assert (await tc.get(f"/calls/by-registration/{reg}", params={"page_size": 500})).json()["page_size"] == 20
        assert await db.bb_registrations.count_documents({}) == 1
    run(monkeypatch, case)


def test_auth_required(monkeypatch):
    async def case(tc, db):
        cid = (await db.ai_calls.insert_one(_call(registration_id=str(ObjectId())))).inserted_id
        for url in (f"/calls/by-registration/{ObjectId()}", "/registrations/lookup?email=a@b.c", f"/calls/{cid}/recording"):
            assert (await tc.get(url)).status_code == 401, url
    run(monkeypatch, case, authed=False)


def test_call_now_locked_server_side(monkeypatch):
    async def case(tc, db):
        cid = (await db.ai_test_candidates.insert_one({"mode": "testing", "candidate_name": "X"})).inserted_id
        r = await tc.post(f"/test-candidates/{cid}/call-now", json={"idempotency_key": "idem-key-phase5-00001", "confirm_name": "X"}, headers=H)
        assert r.status_code == 423
        assert await db.ai_call_jobs.count_documents({}) == 0 and await db.ai_calls.count_documents({}) == 0
        assert await db.ai_call_settings.count_documents({}) == 0  # lock is checked before any settings change
    assert gate.SINGLE_TEST_CALL_APPROVED is False and gate.BOLNA_INTEGRATION_APPROVED is False and gate.LIVE_MODE_LOCKED is True
    run(monkeypatch, case)
