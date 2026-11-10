"""Phase 4B single-call dispatch tests on a SCRATCH database. Bolna POST /call is ALWAYS stubbed — no real calls."""
import asyncio
import os
from datetime import date, datetime, timedelta, timezone

import httpx
from fastapi import FastAPI
from motor.motor_asyncio import AsyncIOMotorClient

from ai_calling import bolna_client as bc
from ai_calling import calls, dispatch, gate, provider, store

SCRATCH = "ai_phase4b_pytest_scratch"
AGENT = "agent-fixture-4b"
H = {"X-CSRF-Intent": "ai-calling"}
FUT = (date.today() + timedelta(days=5)).isoformat()


def _cand(**kw):
    d = {"mode": "testing", "candidate_name": "Test Colleague", "phone_e164": "+919876500001", "approved_phone": "+919876500001",
         "approved": True, "consent_confirmed": True, "opted_out": False, "job_role": "Analyst", "interview_date": FUT,
         "interview_time": "10:00", "language": "English", "company_name": "BluBridge", "office_address": "Chennai"}
    d.update(kw)
    return d


def _ex(ex_id, status="completed"):
    return {"id": ex_id, "agent_id": AGENT, "status": status, "created_at": datetime.now(timezone.utc).isoformat(), "transcript": "assistant: hi\nuser: yes",
            "telephony_data": {"duration": 42, "hangup_reason": "normal", "recording_url": "https://rec.invalid/a.mp3",
                               "to_number": "+919876500001"},
            "extracted_data": {"Interview Call Results": {
                "attendance_status": {"objective": "CONFIRMED", "status": "completed"},
                "wants_reschedule": {"objective": "No", "status": "completed"},
                "requested_virtual": {"objective": "No", "status": "completed"},
                "candidate_questions": {"subjective": "Is parking available?", "status": "completed"}}}}


def run(monkeypatch, case, place=None):
    async def main():
        assert SCRATCH not in (os.environ.get("DB_NAME", ""), "hiring_ai_testing", "hr_analytics")
        client = AsyncIOMotorClient("mongodb://localhost:27017")
        db = client[SCRATCH]
        await client.drop_database(SCRATCH)
        await db.ai_call_jobs.create_index("idempotency_key", unique=True, sparse=True)
        await db.ai_calls.create_index("execution_id", unique=True, sparse=True)
        await db.ai_call_settings.insert_one({"_id": "global", **store.SETTINGS_DEFAULTS, "mode": "testing", "emergency_stop": True,
                                              "call_window_start": "00:00", "call_window_end": "23:59"})
        await db.ai_provider_settings.insert_one({"_id": "bolna", "agent_id": AGENT, "caller_number": "+918000001993", "api_key_encrypted": "x"})
        sent = []

        async def fake_place(*, gate_result, api_key, body):
            assert gate_result["allowed"] and api_key == "stub-key"
            sent.append(body)
            await asyncio.sleep(0.05)
            return await place(body) if place else {"execution_id": f"ex-{len(sent)}", "status": "queued"}

        async def auth(_r):
            return "pytest-admin"
        monkeypatch.setitem(store._state, "db", db)
        monkeypatch.setitem(store._state, "auth", auth)
        monkeypatch.setenv("AI_CALLING_ENABLED", "true")
        monkeypatch.setattr(provider, "provider_ready", lambda _d: True)
        monkeypatch.setattr(dispatch, "decrypt_api_key", lambda _d: "stub-key")
        monkeypatch.setattr(dispatch, "ensure_poller", lambda: None)
        monkeypatch.setattr(bc, "place_call", fake_place)
        app = FastAPI()
        app.include_router(dispatch.dispatch_router)
        try:
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as tc:
                async def call(cid, key="idem-key-0000000000001", name="Test Colleague"):
                    return await tc.post(f"/test-candidates/{cid}/call-now", json={"idempotency_key": key, "confirm_name": name}, headers=H)
                await case(tc, call, db, sent)
        finally:
            await client.drop_database(SCRATCH)
    asyncio.run(main())


async def _safe_state(db):
    s = await db.ai_call_settings.find_one({"_id": "global"})
    assert s["emergency_stop"] is True and s.get("dispatch_lock") is None


def test_name_confirmation_and_csrf(monkeypatch):
    async def case(tc, call, db, sent):
        cid = str((await db.ai_test_candidates.insert_one(_cand())).inserted_id)
        assert (await call(cid, name="Test Colleag")).status_code == 400
        r = await tc.post(f"/test-candidates/{cid}/call-now", json={"idempotency_key": "idem-key-0000000000001", "confirm_name": "Test Colleague"})
        assert r.status_code == 403
        assert (await call("000000000000000000000000")).status_code == 404
        assert sent == [] and await db.ai_call_jobs.count_documents({}) == 0
    run(monkeypatch, case)


def test_happy_path_one_request_idempotent_and_blocking(monkeypatch):
    async def case(tc, call, db, sent):
        cid = str((await db.ai_test_candidates.insert_one(_cand())).inserted_id)
        r = await call(cid)
        assert r.status_code == 200 and r.json()["state"] == "accepted"
        assert len(sent) == 1 and sent[0]["recipient_phone_number"] == "+919876500001"
        assert sent[0]["from_phone_number"] == "+918000001993" and sent[0]["agent_id"] == AGENT
        assert set(sent[0]["user_data"]) == {"candidate_name", "company_name", "job_role", "interview_date", "interview_time", "office_address"}
        c = await db.ai_calls.find_one({})
        assert c["execution_id"] == "ex-1" and c["status"] == "queued" and c["state"] == "accepted" and c["test_candidate_id"] == cid
        assert c.get("completed_at") is None
        await _safe_state(db)
        acts = [a["action"] async for a in db.ai_call_audit.find({}).sort("at", 1)]
        assert acts == ["dispatch_authorized", "dispatch_accepted"]
        again = await call(cid)
        assert again.json()["duplicate"] is True and len(sent) == 1
        assert (await call(cid, key="idem-key-0000000000002")).status_code == 409 and len(sent) == 1
        pub = dispatch.public_call(c)
        assert "recipient_e164" not in pub and "recording_url" not in pub and pub["ui_state"] == "In Progress"
    run(monkeypatch, case)


def test_concurrent_double_click_sends_once(monkeypatch):
    async def case(tc, call, db, sent):
        cid = str((await db.ai_test_candidates.insert_one(_cand())).inserted_id)
        rs = await asyncio.gather(*[call(cid, key=f"idem-key-concurrent-{i:04d}") for i in range(5)],
                                  call(cid), call(cid))
        assert len(sent) == 1
        assert sum(1 for r in rs if r.status_code == 200 and r.json().get("dispatched")) == 1
        assert await db.ai_calls.count_documents({}) == 1
        await _safe_state(db)
    run(monkeypatch, case)


def test_gate_denials_keep_stop_engaged(monkeypatch):
    async def case(tc, call, db, sent):
        for kw in ({"approved": False}, {"consent_confirmed": False}, {"opted_out": True},
                   {"approved_phone": "+919876500099"}, {"interview_date": "2020-01-01"}):
            await db.ai_test_candidates.delete_many({})
            cid = str((await db.ai_test_candidates.insert_one(_cand(**kw))).inserted_id)
            r = await call(cid, key=f"idem-key-deny-{list(kw)[0]}-x"[:60].replace("_", "-"))
            assert r.status_code == 412, kw
            await _safe_state(db)
        await db.ai_call_settings.update_one({"_id": "global"}, {"$set": {"mode": "off"}})
        assert (await call(cid, key="idem-key-mode-off-0001")).status_code == 409
        assert sent == [] and await db.ai_calls.count_documents({}) == 0
    run(monkeypatch, case)


def test_rejected_records_sanitized_error_no_retry(monkeypatch):
    async def place(_b):
        raise bc.BolnaRejected("rate_limited", 429, bc.sanitize("Phone number +918035739222 still activating"))

    async def case(tc, call, db, sent):
        cid = str((await db.ai_test_candidates.insert_one(_cand())).inserted_id)
        r = await call(cid)
        assert r.json()["state"] == "rejected" and len(sent) == 1
        c = await db.ai_calls.find_one({})
        assert "8035739222" not in c["provider_error"]["message"] and c["provider_error"]["http_status"] == 429
        await _safe_state(db)
    run(monkeypatch, case, place)


def test_uncertain_then_reconciled_never_resent(monkeypatch):
    async def place(_b):
        raise bc.DispatchUncertain("network_or_timeout")

    async def case(tc, call, db, sent):
        cid = str((await db.ai_test_candidates.insert_one(_cand())).inserted_id)
        assert (await call(cid)).json()["state"] == "pending_reconciliation"
        assert (await call(cid, key="idem-key-after-uncertain")).status_code == 409
        listed = {"items": []}

        async def lookup(_k, _a, _f, _t):
            return listed["items"]

        async def get_ex(_k, ex_id):
            return _ex(ex_id)
        monkeypatch.setattr(bc, "list_agent_executions", lookup)
        monkeypatch.setattr(bc, "get_execution", get_ex)
        assert await dispatch.reconcile_once() == 1
        listed["items"] = [_ex("ex-found", "in-progress")]
        await dispatch.reconcile_once()
        c = await db.ai_calls.find_one({})
        assert c["execution_id"] == "ex-found"
        assert await dispatch.reconcile_once() == 0
        c = await db.ai_calls.find_one({})
        assert c["state"] == "finished" and c["response"]["attendance_status"] == "CONFIRMED"
        assert c["response"]["wants_reschedule"] is False and c["duration_seconds"] == 42
        assert len(sent) == 1
    run(monkeypatch, case, place)


def test_unresolved_after_30_minutes_needs_review(monkeypatch):
    async def place(_b):
        raise bc.DispatchUncertain("provider_unavailable", 502)

    async def case(tc, call, db, sent):
        cid = str((await db.ai_test_candidates.insert_one(_cand())).inserted_id)
        await call(cid)
        old = (datetime.now(timezone.utc) - timedelta(minutes=31)).isoformat()
        await db.ai_calls.update_one({}, {"$set": {"dispatched_at": old}})

        async def lookup(*_a):
            return []
        monkeypatch.setattr(bc, "list_agent_executions", lookup)
        assert await dispatch.reconcile_once() == 0
        c = await db.ai_calls.find_one({})
        assert c["state"] == "needs_review"
        assert (await call(cid, key="idem-key-after-review-1")).status_code == 409
        assert (await tc.post(f"/test-calls/{c['_id']}/resolve-review", json={"confirmation": "no"}, headers=H)).status_code == 400
        r = await tc.post(f"/test-calls/{c['_id']}/resolve-review", json={"confirmation": "REVIEWED"}, headers=H)
        assert r.status_code == 200 and r.json()["state"] == "reviewed"
        assert len(sent) == 1
    run(monkeypatch, case, place)


def test_concurrent_execution_updates_and_no_regression(monkeypatch):
    async def case(tc, call, db, sent):
        cid = str((await db.ai_test_candidates.insert_one(_cand())).inserted_id)
        await call(cid)
        c = await db.ai_calls.find_one({})
        rs = await asyncio.gather(calls.apply_execution(c, _ex("ex-1"), "webhook"), calls.apply_execution(c, _ex("ex-1", "in-progress"), "poll"))
        assert sum(1 for r in rs if "applied" in r) == 1
        c = await db.ai_calls.find_one({})
        if c["status"] != "completed":
            await calls.apply_execution(c, _ex("ex-1"), "webhook")
            c = await db.ai_calls.find_one({})
        assert c["state"] == "finished" and c["status"] == "completed"
        assert (await calls.apply_execution(c, _ex("ex-1", "ringing"), "late")) == {"ignored": "out_of_order"}
        assert (await db.ai_call_jobs.find_one({}))["status"] == "finished"
        assert dispatch.public_call(c)["ui_state"] == "Completed"
        assert (await call(cid, key="idem-key-second-call-1")).status_code == 200 and len(sent) == 2
    run(monkeypatch, case)


def test_recording_endpoint_validates_call(monkeypatch):
    async def case(tc, call, db, sent):
        assert (await tc.get("/calls/000000000000000000000000/recording")).status_code == 404
        assert (await tc.get("/calls/not-an-id/recording")).status_code == 404
        cid = (await db.ai_calls.insert_one({"mode": "testing", "state": "finished", "recording_url": "http://insecure/a.mp3"})).inserted_id
        assert (await tc.get(f"/calls/{cid}/recording")).status_code == 404
        s = (await tc.get("/test-calls/status")).json()
        assert s["live_mode_locked"] is True and s["batch_calling_enabled"] is False and s["emergency_stop"] is True
    run(monkeypatch, case)


def test_batch_and_live_stay_locked():
    assert gate.BOLNA_INTEGRATION_APPROVED is False and gate.LIVE_MODE_LOCKED is True
