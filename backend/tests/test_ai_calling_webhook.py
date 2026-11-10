"""Webhook processing tests on a SCRATCH database (never the app DB). No network: Bolna re-fetch is stubbed."""
import asyncio
import hashlib
import os

import httpx
from fastapi import FastAPI
from motor.motor_asyncio import AsyncIOMotorClient

from ai_calling import calls, store
from ai_calling.provider import DOC_ID

SCRATCH = "ai_webhook_pytest_scratch"  # dropped before/after each test; never the app DB
TOKEN = "pytest-webhook-token-0123456789abcdefghij"
AGENT = "agent-fixture-0001"


def _completed(ex_id, agent=AGENT, attendance="CONFIRMED", status="completed"):
    return {"id": ex_id, "agent_id": agent, "status": status, "transcript": "assistant: hi\nuser: yes",
            "telephony_data": {"duration": 31, "recording_url": "https://example.invalid/rec.mp3", "hangup_reason": "normal"},
            "extracted_data": {"Interview Call Results": {
                "attendance_status": {"objective": attendance, "subjective": None, "status": "completed", "confidence": 0.9},
                "wants_reschedule": {"objective": "No", "status": "completed"},
                "candidate_questions": {"subjective": "Is parking available?", "status": "completed"}}}}


def run_case(monkeypatch, case):
    async def main():
        assert SCRATCH not in (os.environ.get("DB_NAME", ""), "hiring_ai_testing", "hr_analytics")
        client = AsyncIOMotorClient("mongodb://localhost:27017")
        db = client[SCRATCH]
        await client.drop_database(SCRATCH)
        await db.ai_webhook_events.create_index([("execution_id", 1), ("status", 1), ("payload_hash", 1)], unique=True)
        await db.ai_provider_settings.insert_one({"_id": DOC_ID, "api_key_encrypted": "x",
                                                  "webhook_token_hash": hashlib.sha256(TOKEN.encode()).hexdigest()})
        fetched = {}

        async def fake_get_execution(_key, ex_id):
            if ex_id not in fetched:
                raise calls.bc.BolnaError("not_found", 404)
            return fetched[ex_id]
        monkeypatch.setitem(store._state, "db", db)
        monkeypatch.setattr(calls.bc, "get_execution", fake_get_execution)
        monkeypatch.setattr(calls, "decrypt_api_key", lambda _d: "stub-key")
        app = FastAPI()
        app.include_router(calls.calls_router)
        try:
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as tc:
                async def post(body, token=TOKEN, raw=None):
                    if raw is not None:
                        return await tc.post(f"/webhook/bolna/{token}", content=raw, headers={"Content-Type": "application/json"})
                    return await tc.post(f"/webhook/bolna/{token}", json=body)
                await case(post, db, fetched)
        finally:
            await client.drop_database(SCRATCH)
    asyncio.run(main())


def test_bad_token_and_malformed(monkeypatch):
    async def case(post, db, fetched):
        assert (await post({"id": "x"}, token="wrong")).status_code == 404
        assert (await post(None, raw=b"[1,2]")).status_code == 400
        assert (await post(None, raw=b'"text"')).status_code == 400
    run_case(monkeypatch, case)


def test_unmatched_recorded_but_no_effect(monkeypatch):
    async def case(post, db, fetched):
        r = await post(_completed("exec_sample_completed"))
        assert r.status_code == 200 and r.json() == {"received": True, "matched": False}
        assert await db.ai_webhook_events.count_documents({"execution_id": "exec_sample_completed", "matched": False}) == 1
        assert await db.ai_calls.count_documents({}) == 0
    run_case(monkeypatch, case)


def test_matched_applies_only_refetched_data(monkeypatch):
    async def case(post, db, fetched):
        await db.ai_calls.insert_one({"execution_id": "ex-1", "agent_id": AGENT, "status": "initiated", "mode": "testing"})
        fetched["ex-1"] = _completed("ex-1", attendance="CONFIRMED")
        r = await post(_completed("ex-1", attendance="DECLINED"))  # body lies; re-fetch is authoritative
        assert r.json()["applied"] == "completed"
        c = await db.ai_calls.find_one({"execution_id": "ex-1"})
        assert c["response"]["attendance_status"] == "CONFIRMED" and c["duration_seconds"] == 31 and c["last_source"] == "refetch"
        assert c["response"]["candidate_questions"] == ["Is parking available?"] and c["response"]["wants_reschedule"] is False
    run_case(monkeypatch, case)


def test_duplicate_and_out_of_order(monkeypatch):
    async def case(post, db, fetched):
        await db.ai_calls.insert_one({"execution_id": "ex-2", "agent_id": AGENT, "status": "initiated", "mode": "testing"})
        fetched["ex-2"] = _completed("ex-2")
        body = _completed("ex-2")
        assert (await post(body)).json()["applied"] == "completed"
        assert (await post(body)).json() == {"received": True, "duplicate": True}
        fetched["ex-2"] = {**_completed("ex-2"), "status": "ringing"}
        assert (await post({"id": "ex-2", "status": "ringing"})).json()["ignored"] == "out_of_order"
        assert (await db.ai_calls.find_one({"execution_id": "ex-2"}))["status"] == "completed"
    run_case(monkeypatch, case)


def test_agent_mismatch_missing_id_and_refetch_failure(monkeypatch):
    async def case(post, db, fetched):
        for e in ("ex-3", "ex-4", "ex-6"):
            await db.ai_calls.insert_one({"execution_id": e, "agent_id": AGENT, "status": "initiated", "mode": "testing"})
        fetched["ex-3"] = _completed("ex-3", agent="someone-elses-agent")
        assert (await post(_completed("ex-3"))).json()["rejected"] == "execution mismatch"
        fetched["ex-6"] = {k: v for k, v in _completed("ex-6").items() if k != "id"}
        assert (await post(_completed("ex-6"))).json()["rejected"] == "execution mismatch"
        assert (await post(_completed("ex-4"))).json()["refetch"] == "failed"
        for e in ("ex-3", "ex-6"):
            c = await db.ai_calls.find_one({"execution_id": e})
            assert c["status"] == "initiated" and "response" not in c
        assert (await db.ai_calls.find_one({"execution_id": "ex-4"}))["needs_refetch"] is True
    run_case(monkeypatch, case)


def test_unknown_attendance_stays_unknown(monkeypatch):
    async def case(post, db, fetched):
        await db.ai_calls.insert_one({"execution_id": "ex-5", "agent_id": AGENT, "status": "initiated", "mode": "testing"})
        fetched["ex-5"] = {**_completed("ex-5"), "extracted_data": {}}
        await post(_completed("ex-5"))
        assert (await db.ai_calls.find_one({"execution_id": "ex-5"}))["response"]["attendance_status"] == "UNKNOWN"
    run_case(monkeypatch, case)
