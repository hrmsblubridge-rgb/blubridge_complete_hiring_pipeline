"""Phase 7A: switch policy, transitions, consent workflow and live-gate tests. SCRATCH DB, no provider calls."""
import asyncio

import httpx
import pytest
from bson import ObjectId
from fastapi import FastAPI, HTTPException
from motor.motor_asyncio import AsyncIOMotorClient

from ai_calling import bolna_client as bc
from ai_calling import candidates, dispatch, gate, modes, store
from ai_calling.store import SETTINGS_DEFAULTS

SCRATCH = "ai_phase7a_pytest_scratch"
H = {"X-CSRF-Intent": "ai-calling"}
TABLE = [  # (overall, ai_test, ai_live) -> (test_calls, live_calls)
    ((True, False, False), (False, False)), ((True, True, False), (True, False)),
    ((True, False, True), (False, True)), ((True, True, True), (True, True)),
    ((False, False, False), (False, False)), ((False, True, False), (True, False)),
    ((False, False, True), (False, False)), ((False, True, True), (True, False)),
]


@pytest.mark.parametrize("inp,out", TABLE)
def test_eight_combinations(inp, out):
    e = modes.effective(*inp)
    assert (e["test_calls"], e["live_calls"]) == out
    assert len(modes.policy_table()) == 8


def run(monkeypatch, case, settings=None):
    async def main():
        client = AsyncIOMotorClient("mongodb://localhost:27017")
        d = client[SCRATCH]
        await client.drop_database(SCRATCH)
        await d.ai_call_settings.insert_one({"_id": "global", **SETTINGS_DEFAULTS, **(settings or {})})
        await d.ai_test_candidates.create_index("phone_e164", unique=True)

        async def auth(_r):
            return "pytest-admin"

        async def boom(*_a, **_k):
            raise AssertionError("no provider request allowed in Phase 7A")
        monkeypatch.setitem(store._state, "db", d)
        monkeypatch.setitem(store._state, "auth", auth)
        monkeypatch.setattr(bc, "place_call", boom)
        monkeypatch.setattr(bc, "_get", boom)
        monkeypatch.setattr(modes, "overall_test_mode", lambda: True)
        app = FastAPI()
        for r in (modes.modes_router, candidates.cand_router, dispatch.dispatch_router):
            app.include_router(r)
        try:
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as tc:
                await case(tc, d)
        finally:
            await client.drop_database(SCRATCH)
    asyncio.run(main())


@pytest.mark.parametrize("overall", [True, False])
def test_status_blockers_and_both_on(monkeypatch, overall):
    async def case(tc, d):
        st = await modes.calling_status(overall=overall)
        assert st["ai_test_enabled"] and not st["ai_live_enabled"] and st["emergency_stop"]
        assert not st["test"]["can_call"] and "Emergency stop is ON" in st["test"]["blockers"]
        await modes.set_switches("t", ai_live=True)
        st = await modes.calling_status(overall=overall)
        assert st["ai_test_enabled"] and st["ai_live_enabled"]  # both may be ON
        assert st["live"]["configured"] is overall and st["live"]["can_call"] is False
        if not overall:
            assert any("Overall Website Test Mode is OFF" in b for b in st["live"]["blockers"])
        assert "Live dispatch is not implemented yet (Phase 7A)" in st["live"]["blockers"]
        assert await d.ai_call_jobs.count_documents({}) == 0  # switching ON never enqueues a backlog
    run(monkeypatch, case)


def test_switch_off_cancels_pending_and_revokes_live_auth(monkeypatch):
    async def case(tc, d):
        await d.ai_call_settings.update_one({"_id": "global"}, {"$set": {"ai_live_enabled": True, "live_dispatch_authorized": True}})
        await d.ai_call_jobs.insert_many([{"mode": "testing", "status": "pending", "batch_id": "a"},
                                          {"mode": "live", "status": "pending", "batch_id": "b"},
                                          {"mode": "live", "status": "in-progress", "batch_id": "c"}])
        await modes.set_switches("t", ai_live=False)
        s = await d.ai_call_settings.find_one({"_id": "global"})
        assert s["live_dispatch_authorized"] is False
        assert (await d.ai_call_jobs.find_one({"batch_id": "b"}))["status"] == "cancelled"
        assert (await d.ai_call_jobs.find_one({"batch_id": "a"}))["status"] == "pending"
        assert (await d.ai_call_jobs.find_one({"batch_id": "c"}))["status"] == "in-progress"  # already running: finishes, results processed
        await modes.set_switches("t", ai_test=False)
        assert (await d.ai_call_jobs.find_one({"batch_id": "a"}))["cancel_reason"] == "ai_test_enabled_off"
    run(monkeypatch, case)


def test_concurrent_switch_changes_optimistic(monkeypatch):
    async def case(tc, d):
        v = (await d.ai_call_settings.find_one({"_id": "global"}))["mode_version"]
        rs = await asyncio.gather(modes.set_switches("a", ai_live=True, expected_version=v),
                                  modes.set_switches("b", ai_test=False, expected_version=v), return_exceptions=True)
        assert sum(isinstance(r, HTTPException) and r.status_code == 409 for r in rs) == 1
        assert (await d.ai_call_settings.find_one({"_id": "global"}))["mode_version"] == v + 1
    run(monkeypatch, case)


def test_live_dispatch_authorize_is_locked(monkeypatch):
    async def case(tc, d):
        assert (await tc.post("/live-dispatch/authorize", headers=H)).status_code == 423
        assert (await tc.post("/switches", json={"ai_live_enabled": True})).status_code == 403  # CSRF
    run(monkeypatch, case)


def _cand_body(**kw):
    b = {"candidate_name": "Colleague", "phone_number": "+919000000077", "job_role": "Analyst", "interview_date": "2099-01-01",
         "interview_time": "10", "language": "English", "company_name": "BluBridge", "office_address": "Chennai"}
    b.update(kw)
    return b


def test_consent_workflow_no_approval(monkeypatch):
    async def case(tc, d):
        r = (await tc.post("/test-candidates", json=_cand_body())).json()
        assert r["consent_status"] == "not_granted" and r["readiness"] == "no_consent" and "approved" not in r
        r2 = (await tc.post("/test-candidates", json=_cand_body(phone_number="+919000000078", consent_for_test_call=True))).json()
        assert r2["consent_status"] == "granted" and r2["readiness"] == "ready" and r2["consent_source"] == "manual_entry"
        assert (await tc.post(f"/test-candidates/{r2['id']}/approve", json={})).status_code in (404, 405)
        # phone change resets consent unless fresh consent is given for the new number
        r3 = (await tc.put(f"/test-candidates/{r2['id']}", json=_cand_body(phone_number="+919000000079"))).json()
        assert r3["consent_status"] == "not_granted"
        r3 = (await tc.put(f"/test-candidates/{r2['id']}", json=_cand_body(phone_number="+919000000080", consent_for_test_call=True))).json()
        assert r3["readiness"] == "ready"
        w = (await tc.post(f"/test-candidates/{r2['id']}/consent", json={"granted": False})).json()
        assert w["consent_status"] == "withdrawn" and w["readiness"] == "no_consent"
        await tc.post(f"/test-candidates/{r2['id']}/consent", json={"granted": True})
        o = (await tc.post(f"/test-candidates/{r2['id']}/opt-out", json={"opted_out": True})).json()
        assert o["readiness"] == "opted_out" and o["consent_status"] == "not_granted"
        assert (await tc.post(f"/test-candidates/{r2['id']}/consent", json={"granted": True})).status_code == 400
        assert await d.ai_call_jobs.count_documents({}) == 0 and await d.ai_calls.count_documents({}) == 0
    run(monkeypatch, case)


def test_sheet_consent_column(monkeypatch):
    async def case(tc, d):
        clean, errs = store.validate_row({**_cand_body(), "consent_for_test_call": "YES"}, require_flag=True)
        assert not errs and clean["sheet_consent"] is True
        _, errs = store.validate_row({**_cand_body(), "consent_for_test_call": "maybe"}, require_flag=True)
        assert errs[0]["field"] == "consent_for_test_call"
        doc = candidates._new_doc({**clean, "sheet_consent": None}, "upload", "t", "UP-1", consent=False)
        assert doc["consent_status"] == "not_granted"
    run(monkeypatch, case)


def test_test_gate_needs_consent_not_approval(monkeypatch):
    async def case(tc, d):
        monkeypatch.setenv("AI_CALLING_ENABLED", "true")
        oid = (await d.ai_test_candidates.insert_one({"mode": "testing", "phone_e164": "+919000000081", "consent_status": "granted",
                                                      "consent_phone": "+919000000081", "opted_out": False, "interview_date": "2099-01-01"})).inserted_id
        v = await gate.evaluate(mode="testing", test_candidate_id=str(oid), batch_id="", phone_e164="+919000000081", mode_version=1, single_call=True)
        keys = {c["key"]: c["ok"] for c in v["checks"]}
        assert "admin_approved" not in keys and keys["consent"] and keys["phone_matches"]
        assert keys["no_emergency_stop"] is False and keys["bolna_approved"] is False and v["allowed"] is False
        await d.ai_test_candidates.update_one({"_id": oid}, {"$set": {"consent_status": "withdrawn"}})
        v = await gate.evaluate(mode="testing", test_candidate_id=str(oid), batch_id="", phone_e164="+919000000081", mode_version=1, single_call=True)
        assert {c["key"]: c["ok"] for c in v["checks"]}["consent"] is False
        r = await tc.post(f"/test-candidates/{oid}/call-now", json={"idempotency_key": "idem-key-phase7a-00001", "confirm_name": "x"}, headers=H)
        assert r.status_code == 423  # Call Now stays locked
    run(monkeypatch, case)


def test_live_gate_never_allows_and_never_mixes_sources(monkeypatch):
    async def case(tc, d):
        reg = (await d.bb_registrations.insert_one({"status": "Interview Scheduled", "is_shortlisted": True, "phone": "+919000000090",
                                                    "schedule_date": "2099-01-05", "schedule_time": "11:00:00"})).inserted_id
        await d.ai_test_candidates.insert_one({"mode": "testing", "phone_e164": "+919000000090", "consent_status": "granted"})  # same phone
        v = await modes.evaluate_live(registration_id=str(reg), job_mode_version=1, overall=True)
        k = {c["key"]: c for c in v["checks"]}
        assert v["allowed"] is False and k["implemented"]["ok"] is False
        assert "NO_CALLING_CONSENT" in k["eligible"]["detail"]  # test-list consent never counts for a real candidate
        await d.ai_candidate_consents.insert_one({"registration_id": str(reg), "status": "granted"})
        k = {c["key"]: c for c in (await modes.evaluate_live(registration_id=str(reg), job_mode_version=1, overall=True))["checks"]}
        assert k["eligible"]["ok"] is True
        await d.ai_candidate_consents.update_one({"registration_id": str(reg)}, {"$set": {"status": "withdrawn"}})
        k = {c["key"]: c for c in (await modes.evaluate_live(registration_id=str(reg), job_mode_version=1, overall=True))["checks"]}
        assert "CONSENT_WITHDRAWN" in k["eligible"]["detail"]
        await d.ai_candidate_consents.update_one({"registration_id": str(reg)}, {"$set": {"status": "granted", "do_not_call": True}})
        k = {c["key"]: c for c in (await modes.evaluate_live(registration_id=str(reg), job_mode_version=1, overall=False))["checks"]}
        assert "DO_NOT_CALL" in k["eligible"]["detail"] and k["overall_test"]["ok"] is False
        assert (await modes.evaluate_live(registration_id=str(ObjectId()), job_mode_version=1, overall=True))["allowed"] is False
        assert await d.bb_registrations.count_documents({}) == 1
    run(monkeypatch, case)
