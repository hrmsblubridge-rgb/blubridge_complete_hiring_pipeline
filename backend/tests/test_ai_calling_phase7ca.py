"""Phase 7C-A: hashed expiring consent tokens, withdrawal/renewal, Do Not Call, mock live scheduler/worker.
SCRATCH DB only; Bolna and messaging are monkeypatched to fail if touched."""
import asyncio
import uuid
from datetime import datetime, timedelta, timezone

import httpx
import pytest
from bson import ObjectId
from fastapi import FastAPI
from motor.motor_asyncio import AsyncIOMotorClient
from pymongo.errors import AutoReconnect

from ai_calling import bolna_client as bc
from ai_calling import consent, live_prep, modes, retention, store
from ai_calling.store import IST, SETTINGS_DEFAULTS

SCRATCH = "ai_phase7ca_pytest_scratch"
V = modes.CONSENT_TEXT_VERSION
NOW = datetime.now(IST).replace(hour=12, minute=0, second=0, microsecond=0)
IV = NOW + timedelta(days=2)  # interview 2 days ahead, 12:00 IST
SCHED = "sched_" + "b" * 24


def reg(**kw):
    d = {"full_name": "Synthetic Person", "phone": "+919000000301", "email": "s1@example.invalid", "status": "Interview Scheduled",
         "is_shortlisted": True, "schedule_date": IV.date().isoformat(), "schedule_time": "12:00:00", "otp_verified": False,
         "missed_marked": False, "superseded": False, "reschedule_count": 0, "isTest": False, "schedule_token": SCHED, "job_role": "Analyst"}
    d.update(kw)
    return d


def run(monkeypatch, case, user="pytest-admin", top="pytest-admin", settings=None):
    calls = {"bolna": 0}

    async def main():
        client = AsyncIOMotorClient("mongodb://localhost:27017")
        name = f"{SCRATCH}_{uuid.uuid4().hex[:8]}"
        d = client[name]
        await d.ai_call_settings.insert_one({"_id": "global", **SETTINGS_DEFAULTS, "missed_enabled": False, **(settings or {})})
        await d.ai_candidate_consents.create_index("registration_id", unique=True)

        async def auth(_r):
            return user

        async def boom(*_a, **_k):
            calls["bolna"] += 1
            raise AssertionError("no provider request in Phase 7C-A")
        monkeypatch.setitem(store._state, "db", d)
        monkeypatch.setitem(store._state, "auth", auth)
        monkeypatch.setattr(bc, "place_call", boom)
        monkeypatch.setattr(bc, "_get", boom)
        monkeypatch.setattr(modes, "overall_test_mode", lambda: True)
        monkeypatch.setattr(live_prep, "overall_test_mode", lambda: True)
        monkeypatch.setenv("AI_TOP_LEVEL_ADMINS", top)
        monkeypatch.setenv("FRONTEND_URL", "http://t")
        await consent.ensure_consent_indexes()
        await live_prep.ensure_live_prep_indexes()
        app = FastAPI()
        from ai_calling import purposes, dispatch
        for r in (consent.public_router, consent.admin_router, modes.modes_router, live_prep.live_prep_router,
                  retention.retention_router, purposes.purposes_router, dispatch.dispatch_router):
            app.include_router(r)
        try:
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t",
                                         headers={"X-CSRF-Intent": "ai-calling"}) as tc:
                await case(tc, d)
        finally:
            await client.drop_database(name)
            client.close()
    for attempt in range(3):  # local mongod occasionally drops a fresh connection (infra flake, not app logic)
        try:
            asyncio.run(main())
            break
        except AutoReconnect:
            if attempt == 2:
                raise
    assert calls["bolna"] == 0


async def _book(tc, d, granted=True):
    rid = str((await d.bb_registrations.insert_one(reg())).inserted_id)
    r = await tc.post(f"/public/booking-consent/{SCHED}", json={"granted": granted, "text_version": V})
    assert r.status_code == 200, r.text
    return rid, r.json()["manage_token"]


def H(tok):
    return {"X-Consent-Token": tok}


def test_token_hashed_not_plaintext_and_headers(monkeypatch):
    async def case(tc, d):
        rid, tok = await _book(tc, d)
        t = await d.ai_consent_tokens.find_one({"registration_id": rid})
        assert t["token_hash"] == consent.hash_token(tok) and tok not in str(t)
        assert t["purpose"] == consent.PURPOSE
        exp = datetime.fromisoformat(t["expires_at"]) - datetime.fromisoformat(t["created_at"])
        assert exp == timedelta(days=30)
        audits = [str(a) async for a in d.ai_call_audit.find({})]
        assert not any(tok in a for a in audits)
        r = await tc.get("/public/consent/manage", headers=H(tok))
        assert r.status_code == 200 and r.json()["consent_status"] == "granted"
        assert r.headers["cache-control"].startswith("no-store") and r.headers["referrer-policy"] == "no-referrer"
        assert SCHED not in str(await d.ai_consent_tokens.find_one({}))
    run(monkeypatch, case)


def test_booking_token_cannot_manage_and_one_decision_per_slot(monkeypatch):
    async def case(tc, d):
        await _book(tc, d, granted=False)
        assert (await tc.get("/public/consent/manage", headers=H(SCHED + "x" * 10))).status_code == 404
        r = await tc.post(f"/public/booking-consent/{SCHED}", json={"granted": True, "text_version": V})
        assert r.status_code == 409
        assert (await tc.post("/public/booking-consent/" + "z" * 24, json={"granted": True, "text_version": V})).status_code == 404
    run(monkeypatch, case)


def test_booking_without_consent_and_wrong_version(monkeypatch):
    async def case(tc, d):
        await d.bb_registrations.insert_one(reg())
        assert (await tc.post(f"/public/booking-consent/{SCHED}", json={"granted": True, "text_version": "old"})).status_code == 409
        rid, _ = await _book_existing(tc, d, granted=False)
        c = await d.ai_candidate_consents.find_one({"registration_id": rid})
        assert c["consent_status"] == "not_given" and c["consent_text_version"] == V
    run(monkeypatch, case)


async def _book_existing(tc, d, granted):
    r = await tc.post(f"/public/booking-consent/{SCHED}", json={"granted": granted, "text_version": V})
    reg_ = await d.bb_registrations.find_one({"schedule_token": SCHED})
    return str(reg_["_id"]), r.json().get("manage_token")


def test_persistence_failure_counts_as_not_given(monkeypatch):
    async def case(tc, d):
        await d.bb_registrations.insert_one(reg())

        async def fail(*_a, **_k):
            raise RuntimeError("db down")
        monkeypatch.setattr(consent, "record_consent", fail)
        r = await tc.post(f"/public/booking-consent/{SCHED}", json={"granted": True, "text_version": V})
        assert r.status_code == 503 and "NOT given" in r.json()["detail"]
        assert await d.ai_candidate_consents.count_documents({"consent_status": "granted"}) == 0
        assert await d.ai_call_audit.count_documents({"action": "consent_persist_failed"}) == 1
        assert (await d.bb_registrations.find_one({}))["status"] == "Interview Scheduled"
    run(monkeypatch, case)


def test_expired_token_withdraw_only(monkeypatch):
    async def case(tc, d):
        rid, tok = await _book(tc, d)
        await d.ai_consent_tokens.update_one({"registration_id": rid}, {"$set": {"expires_at": "2000-01-01T00:00:00+00:00"}})
        info = (await tc.get("/public/consent/manage", headers=H(tok))).json()
        assert info["expired"] and info["can_withdraw"] and not info["can_grant"]
        assert (await tc.post("/public/consent/manage/rotate", headers=H(tok))).status_code == 403
        r = await tc.post("/public/consent/manage/withdraw", headers=H(tok))
        assert r.status_code == 200
        c = await d.ai_candidate_consents.find_one({"registration_id": rid})
        assert c["consent_status"] == "withdrawn" and c["consent_source"] == "consent_page_expired_link" and c["consent_withdrawn_at"]
        assert (await tc.post("/public/consent/manage/grant", headers=H(tok), json={"text_version": V})).status_code == 403
        assert (await d.bb_registrations.find_one({}))["schedule_date"] == IV.date().isoformat()
    run(monkeypatch, case)


def test_rotation_and_revocation(monkeypatch):
    async def case(tc, d):
        rid, tok = await _book(tc, d)
        new = (await tc.post("/public/consent/manage/rotate", headers=H(tok))).json()["manage_token"]
        assert (await tc.get("/public/consent/manage", headers=H(tok))).status_code == 404
        assert (await tc.post("/public/consent/manage/withdraw", headers=H(tok))).status_code == 404
        assert (await tc.get("/public/consent/manage", headers=H(new))).status_code == 200
        assert (await tc.post(f"/consent/admin/{rid}/revoke-links")).json()["revoked"] == 1
        assert (await tc.get("/public/consent/manage", headers=H(new))).status_code == 404
    run(monkeypatch, case)


def test_cross_candidate_and_forged(monkeypatch):
    async def case(tc, d):
        rid_a, tok_a = await _book(tc, d)
        other = await d.bb_registrations.insert_one(reg(schedule_token="sched_" + "c" * 24, phone="+919000000302", full_name="Other"))
        rid_b = str(other.inserted_id)
        await consent.record_consent(rid_b, "granted", "test", "t")
        await tc.post("/public/consent/manage/withdraw", headers=H(tok_a))
        assert (await d.ai_candidate_consents.find_one({"registration_id": rid_b}))["consent_status"] == "granted"
        assert (await tc.get("/public/consent/manage", headers=H("A" * 43))).status_code == 404
        assert (await tc.get("/public/consent/manage")).status_code == 404
        await d.ai_consent_tokens.update_one({"registration_id": rid_a}, {"$set": {"purpose": "other"}})
        assert (await tc.get("/public/consent/manage", headers=H(tok_a))).status_code == 404
    run(monkeypatch, case)


def test_invalid_token_rate_limited(monkeypatch):
    async def case(tc, d):
        for _ in range(consent.RATE_MAX_FAILURES):
            assert (await tc.get("/public/consent/manage", headers=H("B" * 43))).status_code == 404
        assert (await tc.get("/public/consent/manage", headers=H("B" * 43))).status_code == 429
    run(monkeypatch, case)


def test_otp_renewal_prepared_not_sent(monkeypatch):
    async def case(tc, d):
        rid, tok = await _book(tc, d)
        assert (await tc.post("/public/consent/renew/request", json={})).status_code == 501
        cid, code = await consent.create_otp(rid)
        otp = await d.ai_consent_otps.find_one({"_id": cid})
        assert code not in str(otp)
        bad = "000000" if code != "000000" else "111111"
        assert (await tc.post("/public/consent/renew/verify", json={"challenge_id": cid, "code": bad})).status_code == 400
        r = await tc.post("/public/consent/renew/verify", json={"challenge_id": cid, "code": code})
        assert r.status_code == 200 and r.json()["manage_token"]
        assert (await tc.post("/public/consent/renew/verify", json={"challenge_id": cid, "code": code})).status_code == 400
        assert (await tc.get("/public/consent/manage", headers=H(tok))).status_code == 404  # rotated
    run(monkeypatch, case)


def test_admin_dnc_mark_remove_rules(monkeypatch):
    async def case(tc, d):
        rid, tok = await _book(tc, d)
        await d.ai_call_jobs.insert_one({"mode": "live", "registration_id": rid, "status": "pending"})
        assert (await tc.post(f"/consent/admin/{rid}/dnc", json={"action": "mark"})).status_code == 400
        r = await tc.post(f"/consent/admin/{rid}/dnc", json={"action": "mark", "reason": "asked HR", "confirm": True})
        assert r.status_code == 200 and r.json()["do_not_call"] and r.json()["dnc_sources"] == ["ADMIN"]
        assert (await d.ai_call_jobs.find_one({}))["status"] == "cancelled"
        assert (await tc.post(f"/consent/admin/{rid}/dnc", json={"action": "remove", "confirm": True})).status_code == 400
        r = await tc.post(f"/consent/admin/{rid}/dnc", json={"action": "remove", "reason": "error", "confirm": True})
        assert r.status_code == 200 and not r.json()["do_not_call"] and r.json()["consent_status"] == "granted"
        assert await d.ai_call_audit.count_documents({"action": {"$in": ["dnc_marked", "dnc_removed"]}, "registration_id": rid}) == 2
        assert (await tc.post(f"/consent/admin/{ObjectId()}/dnc", json={"action": "mark", "confirm": True})).status_code == 404
    run(monkeypatch, case)


def test_candidate_dnc_not_removable_and_withdrawal_not_restored(monkeypatch):
    async def case(tc, d):
        rid, tok = await _book(tc, d)
        await tc.post("/public/consent/manage/withdraw", headers=H(tok))
        await tc.post("/public/consent/manage/do-not-call", headers=H(tok))
        await tc.post(f"/consent/admin/{rid}/dnc", json={"action": "mark", "confirm": True})
        r = await tc.post(f"/consent/admin/{rid}/dnc", json={"action": "remove", "reason": "x", "confirm": True})
        c = r.json()
        assert c["do_not_call"] and c["dnc_sources"] == ["CANDIDATE"] and c["consent_status"] == "withdrawn"
        assert (await tc.post(f"/consent/admin/{rid}/dnc", json={"action": "remove", "reason": "x", "confirm": True})).status_code == 409
        b = {**reg(), "ai_call_consent": {"status": c["consent_status"]}, "do_not_call": c["do_not_call"]}
        assert "DO_NOT_CALL" in live_prep.eligibility(b) and "CONSENT_WITHDRAWN" in live_prep.eligibility(b)
    run(monkeypatch, case)


def test_non_top_admin_cannot_remove(monkeypatch):
    async def case(tc, d):
        rid, _ = await _book(tc, d)
        await tc.post(f"/consent/admin/{rid}/dnc", json={"action": "mark", "confirm": True})
        r = await tc.post(f"/consent/admin/{rid}/dnc", json={"action": "remove", "reason": "x", "confirm": True})
        assert r.status_code == 403
        assert (await tc.get(f"/consent/admin/{rid}")).json()["can_remove_dnc"] is False
    run(monkeypatch, case, user="junior-admin", top="someone-else")


def test_admin_requires_csrf(monkeypatch):
    async def case(tc, d):
        rid, _ = await _book(tc, d)
        r = await tc.post(f"/consent/admin/{rid}/dnc", json={"action": "mark", "confirm": True}, headers={"X-CSRF-Intent": ""})
        assert r.status_code == 403
    run(monkeypatch, case)


# ---------- mock scheduler / worker ----------

async def _setup_job(tc, d, **kw):
    rid = str((await d.bb_registrations.insert_one(reg(**kw))).inserted_id)
    await consent.record_consent(rid, "granted", "test", "t")
    res = await live_prep.plan_live("t", "bb_registrations", now=NOW)
    return rid, res


def test_plan_idempotent_and_reschedule_invalidates(monkeypatch):
    async def case(tc, d):
        rid, res = await _setup_job(tc, d)
        assert res["counts"]["planned"] == 1
        again = await live_prep.plan_live("t", "bb_registrations", now=NOW)
        assert again["counts"]["unchanged"] == 1 and await d.ai_live_mock_jobs.count_documents({}) == 1
        j = await d.ai_live_mock_jobs.find_one({})
        assert j["dispatchable"] is False and j["planned_at"].startswith((IV - timedelta(days=1)).date().isoformat())
        await d.bb_registrations.update_one({}, {"$set": {"schedule_time": "15:00:00"}, "$inc": {"reschedule_count": 1}})
        r3 = await live_prep.plan_live("t", "bb_registrations", now=NOW)
        assert r3["counts"]["invalidated"] == 1 and r3["counts"]["planned"] == 1
        await d.bb_registrations.update_one({}, {"$set": {"status": "Cancelled"}})
        r4 = await live_prep.plan_live("t", "bb_registrations", now=NOW)
        assert r4["counts"]["invalidated"] == 1
        assert await d.ai_live_mock_jobs.count_documents({"status": "planned"}) == 0
    run(monkeypatch, case)


def test_mock_tick_confirmed_zero_requests(monkeypatch):
    async def case(tc, d):
        rid, _ = await _setup_job(tc, d)
        due = IV - timedelta(days=1)
        r = await live_prep.mock_tick("w1", now=due, outcome="CONFIRMED")
        assert r["result"] == "completed" and r["provider_request_sent"] is False
        assert set(r["gate"]["mock_bypassed"]) >= {"server_enabled", "emergency_stop_off", "authorized", "dispatch_implemented"}
        assert r["gate"]["allowed_live"] is False
        j = await d.ai_live_mock_jobs.find_one({})
        mc = j["mock_call"]
        assert mc["registration_id"] == rid and mc["mode"] == "live" and mc["execution_id"].startswith("mock_")
        assert set(mc["user_data"]) == {"candidate_name", "company_name", "job_role", "interview_date", "interview_time", "office_address", "call_purpose"}
        assert set(mc["extracted"]) == set(live_prep.EXTRACTION_FIELDS) and mc["confirmed_attendance"] is True
        assert await d.ai_calls.count_documents({}) == 0  # mock never pollutes Candidate Profile history
        assert (await live_prep.mock_tick("w1", now=due))["claimed"] is None  # no duplicate
    run(monkeypatch, case)


def test_mock_no_answer_one_retry_only(monkeypatch):
    async def case(tc, d):
        await _setup_job(tc, d)
        due = IV - timedelta(days=1)
        r = await live_prep.mock_tick("w1", now=due, outcome="no_answer")
        assert r["result"] == "no_answer" and r["retry_job"]
        rj = await d.ai_live_mock_jobs.find_one({"attempt": 2})
        assert datetime.fromisoformat(rj["planned_at"]) == due + timedelta(minutes=60)
        r2 = await live_prep.mock_tick("w1", now=due + timedelta(minutes=61), outcome="no_answer")
        assert r2["result"] == "no_answer" and r2["retry_job"] is None
        assert await d.ai_live_mock_jobs.count_documents({}) == 2
    run(monkeypatch, case)


def test_mock_timeout_pending_reconciliation_never_confirmed(monkeypatch):
    async def case(tc, d):
        await _setup_job(tc, d)
        due = IV - timedelta(days=1)
        r = await live_prep.mock_tick("w1", now=due, outcome="timeout")
        assert r["result"] == "pending_reconciliation" and r["retry_job"] is None
        j = await d.ai_live_mock_jobs.find_one({})
        assert j["mock_call"]["confirmed_attendance"] is False
        assert (await d.ai_live_counters.find_one({"_id": "mock:concurrency"}))["active"] == 1  # slot held
        out = await live_prep.mock_reconcile(str(j["_id"]), "needs_review")
        assert out["redialled"] is False
        assert (await d.ai_live_counters.find_one({"_id": "mock:concurrency"}))["active"] == 0
    run(monkeypatch, case)


def test_mock_gate_blocks_withdrawn_dnc_and_snapshot(monkeypatch):
    async def case(tc, d):
        rid, _ = await _setup_job(tc, d)
        due = IV - timedelta(days=1)
        await consent.set_dnc(rid, "ADMIN", "t", True)
        assert (await d.ai_live_mock_jobs.find_one({}))["status"] == "invalidated"  # invalidated at once
        await d.ai_live_mock_jobs.update_one({}, {"$set": {"status": "planned"}})
        r = await live_prep.mock_tick("w1", now=due)
        assert r["result"] == "invalidated" and "NOT_DNC" in (await d.ai_live_mock_jobs.find_one({}))["reasons"]
        await consent.set_dnc(rid, "ADMIN", "t", False)
        await d.ai_live_mock_jobs.update_one({}, {"$set": {"status": "planned"}})
        await d.bb_registrations.update_one({}, {"$set": {"schedule_time": "16:00:00"}})
        r = await live_prep.mock_tick("w1", now=due)
        assert r["result"] == "invalidated" and "SNAPSHOT" in (await d.ai_live_mock_jobs.find_one({}))["reasons"]
    run(monkeypatch, case)


def test_mock_daily_and_concurrency_limits_atomic(monkeypatch):
    async def case(tc, d):
        await d.ai_call_settings.update_one({"_id": "global"}, {"$set": {"live_pilot_daily_cap": 1}})
        for i in range(3):
            rid = str((await d.bb_registrations.insert_one(reg(phone=f"+91900000040{i}", schedule_token=f"s{i}" * 10))).inserted_id)
            await consent.record_consent(rid, "granted", "test", "t")
        await live_prep.plan_live("t", "bb_registrations", now=NOW)
        due = IV - timedelta(days=1)
        results = await asyncio.gather(*[live_prep.mock_tick(f"w{i}", now=due) for i in range(3)])
        res = sorted(r["result"] for r in results)
        assert res.count("completed") == 1 and all(x in ("completed", "daily_limit", "concurrency_limit") for x in res)
        assert (await d.ai_live_counters.find_one({"_id": f"mock:daily:{due.date().isoformat()}"}))["count"] == 1
    run(monkeypatch, case)


def test_stale_claim_recovery(monkeypatch):
    async def case(tc, d):
        await _setup_job(tc, d)
        due = IV - timedelta(days=1)
        await d.ai_live_mock_jobs.update_one({}, {"$set": {"status": "claimed", "lease_until": (due - timedelta(minutes=10)).isoformat()}})
        assert await live_prep.recover_stale(due) == 1 and (await d.ai_live_mock_jobs.find_one({}))["status"] == "planned"
        await d.ai_live_mock_jobs.update_one({}, {"$set": {"status": "claimed", "provider_request_sent": True,
                                                            "lease_until": (due - timedelta(minutes=10)).isoformat()}})
        await live_prep.recover_stale(due)
        assert (await d.ai_live_mock_jobs.find_one({}))["status"] == "pending_reconciliation"
    run(monkeypatch, case)


def test_authorization_refused_and_readiness(monkeypatch):
    async def case(tc, d):
        r = await tc.post("/live-dispatch/authorize", json={"confirmation": modes.LIVE_AUTH_PHRASE})
        assert r.status_code == 423
        rd = (await tc.get("/live-dispatch/readiness")).json()
        keys = {c["key"]: c["ok"] for c in rd["checks"]}
        assert rd["ready"] is False and keys["deployment_approved"] is False and keys["dispatch_implemented"] is False
        s = await store.get_settings()
        assert s["live_dispatch_authorized"] is False and modes.live_daily_cap(s) == 5
    run(monkeypatch, case)


@pytest.mark.parametrize("o,t,lv,test_calls,live_calls", [
    (True, False, False, False, False), (True, True, False, True, False), (True, False, True, False, True),
    (True, True, True, True, True), (False, False, False, False, False), (False, True, False, True, False),
    (False, False, True, False, False), (False, True, True, True, False)])
def test_eight_modes_unchanged(o, t, lv, test_calls, live_calls):
    e = modes.effective(o, t, lv)
    assert (e["test_calls"], e["live_calls"]) == (test_calls, live_calls)


def test_place_call_refuses_live_payload():
    async def main():
        with pytest.raises(PermissionError):
            await bc.place_call(gate_result={"allowed": True, "source": "live"}, api_key="x", body={})
    asyncio.run(main())


def test_rate_limit_ignores_spoofed_forwarded_for(monkeypatch):
    monkeypatch.setenv("AI_TRUSTED_PROXY_HOPS", "2")

    async def case(tc, d):
        for i in range(consent.RATE_MAX_FAILURES):
            h = {**H("C" * 43), "X-Forwarded-For": f"9.9.9.{i}, 1.2.3.4, 10.0.0.1"}
            assert (await tc.get("/public/consent/manage", headers=h)).status_code == 404
        h = {**H("C" * 43), "X-Forwarded-For": "8.8.8.8, 1.2.3.4, 10.0.0.1"}
        assert (await tc.get("/public/consent/manage", headers=h)).status_code == 429
    run(monkeypatch, case)


def test_grant_blocked_after_candidate_dnc(monkeypatch):
    async def case(tc, d):
        rid, tok = await _book(tc, d, granted=False)
        await tc.post("/public/consent/manage/do-not-call", headers=H(tok))
        assert (await tc.get("/public/consent/manage", headers=H(tok))).json()["can_grant"] is False
        assert (await tc.post("/public/consent/manage/grant", headers=H(tok), json={"text_version": V})).status_code == 409
    run(monkeypatch, case)
