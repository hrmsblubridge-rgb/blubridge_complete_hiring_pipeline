"""Phase 7C-B1: booking-link + last-4 consent renewal, retention preview (no deletion), mock worker hardening.
SCRATCH DB only (helpers from phase 7C-A tests); Bolna is monkeypatched to fail if touched."""
import asyncio
from datetime import datetime, timedelta, timezone

import pytest
from bson import ObjectId

from ai_calling import consent, live_prep
from tests.test_ai_calling_phase7ca import IV, NOW, SCHED, H, V, _book, _setup_job, reg, run


async def _renew(tc, digits, token=SCHED):
    return await tc.post("/public/consent/renew/booking", json={"schedule_token": token, "phone_last4": digits})


def test_renewal_issues_new_token_revokes_old_keeps_consent(monkeypatch):
    async def case(tc, d):
        rid, old = await _book(tc, d, granted=False)
        r = await _renew(tc, "0301")
        assert r.status_code == 200 and r.json()["consent_changed"] is False
        new = r.json()["manage_token"]
        assert (await tc.get("/public/consent/manage", headers=H(old))).status_code == 404
        info = (await tc.get("/public/consent/manage", headers=H(new))).json()
        assert info["consent_status"] == "not_given" and info["expired"] is False
        assert await d.ai_consent_tokens.count_documents({"registration_id": rid, "revoked_at": None}) == 1
        assert new not in str(await d.ai_consent_tokens.find({}).to_list(10))
        b = await d.bb_registrations.find_one({})
        assert b["schedule_token"] == SCHED and b["status"] == "Interview Scheduled"
    run(monkeypatch, case)


def test_renewal_wrong_digits_generic_and_lockout(monkeypatch):
    async def case(tc, d):
        rid, _ = await _book(tc, d)
        bad = await _renew(tc, "9999")
        unknown = await _renew(tc, "0301", token="q" * 24)
        assert bad.status_code == unknown.status_code == 400 and bad.json()["detail"] == unknown.json()["detail"]
        for _ in range(consent.RENEW_MAX_FAILURES - 1):
            await _renew(tc, "1111")
        assert (await _renew(tc, "0301")).status_code == 400  # locked even with the right digits; same generic reply
        g = await d.ai_consent_renew_guard.find_one({"_id": rid})
        assert g["locked_until"] > datetime.now(timezone.utc).isoformat()
    monkeypatch.setattr(consent, "RATE_MAX_FAILURES", 100)
    run(monkeypatch, case)


def test_renewal_rate_limited_by_ip(monkeypatch):
    async def case(tc, d):
        for i in range(consent.RATE_MAX_FAILURES):
            await _renew(tc, "0301", token=f"{i:02d}" * 12)
        assert (await _renew(tc, "0301")).status_code == 429
    run(monkeypatch, case)


def test_renewal_bad_input_and_no_booking(monkeypatch):
    async def case(tc, d):
        await d.bb_registrations.insert_one(reg(schedule_date=None))
        assert (await _renew(tc, "0301")).status_code == 400
        assert (await _renew(tc, "03a1")).status_code == 400
        assert (await tc.post("/public/consent/renew/booking", json={})).status_code == 400
    run(monkeypatch, case)


def test_renewal_cross_candidate_isolated(monkeypatch):
    async def case(tc, d):
        rid_a, tok_a = await _book(tc, d)
        other = await d.bb_registrations.insert_one(reg(schedule_token="o" * 24, phone="+919876545678"))
        assert (await _renew(tc, "5678")).status_code == 400  # B's digits with A's booking link
        r = await _renew(tc, "5678", token="o" * 24)
        tok_b = r.json()["manage_token"]
        assert (await tc.get("/public/consent/manage", headers=H(tok_a))).status_code == 200  # A untouched
        await tc.post("/public/consent/manage/withdraw", headers=H(tok_b))
        assert (await d.ai_candidate_consents.find_one({"registration_id": rid_a}))["consent_status"] == "granted"
        assert await d.ai_consent_tokens.count_documents({"registration_id": str(other.inserted_id), "revoked_at": None}) == 1
    run(monkeypatch, case)


def test_concurrent_renewals_leave_one_active_token(monkeypatch):
    async def case(tc, d):
        rid, _ = await _book(tc, d)
        rs = await asyncio.gather(*[_renew(tc, "0301") for _ in range(4)])
        assert all(r.status_code == 200 for r in rs)
        assert await d.ai_consent_tokens.count_documents({"registration_id": rid, "revoked_at": None}) == 1
    run(monkeypatch, case)


def test_renewed_link_after_expiry_can_grant_but_expired_cannot(monkeypatch):
    async def case(tc, d):
        rid, old = await _book(tc, d, granted=False)
        await d.ai_consent_tokens.update_one({"registration_id": rid}, {"$set": {"expires_at": "2000-01-01T00:00:00+00:00"}})
        assert (await tc.post("/public/consent/manage/grant", headers=H(old), json={"text_version": V})).status_code == 403
        new = (await _renew(tc, "0301")).json()["manage_token"]
        assert (await tc.post("/public/consent/manage/withdraw", headers=H(old))).status_code == 404  # replaced
        r = await tc.post("/public/consent/manage/grant", headers=H(new), json={"text_version": V})
        assert r.status_code == 200 and r.json()["consent_status"] == "granted"
    run(monkeypatch, case)


# ---------- retention ----------

async def _call(d, days_old, **kw):
    at = (datetime.now(timezone.utc) - timedelta(days=days_old)).isoformat()
    doc = {"mode": "testing", "candidate_name": "Synthetic", "created_at": at, "completed_at": at, "state": "finished",
           "status": "completed", "transcript": "hello", "recording_url": "https://provider.invalid/r.mp3", "execution_id": "e1",
           "extracted_data_raw": {"x": 1}, "response": {"attendance_status": "CONFIRMED", "candidate_questions": ["q"],
                                                        "call_summary": "s", "rejection_reason": None}}
    doc.update(kw)
    return str((await d.ai_calls.insert_one(doc)).inserted_id)


def test_retention_preview_marks_without_deleting(monkeypatch):
    async def case(tc, d):
        old, new = await _call(d, 120), await _call(d, 10)
        empty = await _call(d, 200, transcript=None, recording_url=None, extracted_data_raw=None, response={"attendance_status": "UNKNOWN"})
        snap = await d.ai_calls.find({}).to_list(10)
        p = (await tc.get("/retention/preview")).json()
        by = {r["call_id"]: r for r in p["rows"]}
        assert p["dry_run"] and p["deleted"] == 0 and p["days"] == 90
        assert by[old]["status"] == "eligible" and "Full transcript" in by[old]["fields"] and by[old]["actions"]
        assert "provider deletion UNVERIFIED" in by[old]["provider_copy"]
        assert by[new]["status"] == "not_yet_due" and by[empty]["status"] == "nothing_sensitive"
        assert await d.ai_calls.find({}).to_list(10) == snap
        assert (await tc.post("/retention/execute")).status_code == 423
        assert await d.ai_calls.find({}).to_list(10) == snap
    run(monkeypatch, case)


def test_retention_legal_hold_and_policy_versions(monkeypatch):
    async def case(tc, d):
        cid = await _call(d, 120)
        assert (await tc.post("/retention/holds", json={"call_id": cid})).status_code == 400
        assert (await tc.post("/retention/holds", json={"call_id": cid, "reason": "dispute"})).status_code == 200
        rows = (await tc.get("/retention/preview")).json()["rows"]
        assert rows[0]["status"] == "on_hold"
        assert (await tc.post(f"/retention/holds/{cid}/release")).status_code == 200
        assert (await tc.post("/retention/holds", json={"call_id": str(ObjectId()), "reason": "x"})).status_code == 404
        assert (await tc.post("/retention/policy", json={"days": 10})).status_code == 400
        pol = (await tc.post("/retention/policy", json={"days": 120, "notes": "draft"})).json()
        assert pol["policy"]["version"] == 2 and pol["policy"]["status"] == "proposed" and pol["policy"]["deletion_enabled"] is False
        assert len(pol["history"]) == 2
        audits = [a async for a in d.ai_call_audit.find({"action": {"$regex": "^retention"}})]
        assert audits and not any("hello" in str(a) for a in audits)
    run(monkeypatch, case)


def test_retention_manage_requires_top_admin(monkeypatch):
    async def case(tc, d):
        cid = await _call(d, 120)
        assert (await tc.post("/retention/holds", json={"call_id": cid, "reason": "x"})).status_code == 403
        assert (await tc.post("/retention/policy", json={"days": 120})).status_code == 403
        assert (await tc.get("/retention/preview")).status_code == 200
    run(monkeypatch, case, user="junior-admin", top="someone-else")


# ---------- worker ----------

def test_backlog_never_dialled_late(monkeypatch):
    async def case(tc, d):
        await _setup_job(tc, d)
        late = IV - timedelta(days=1) + timedelta(hours=2)
        r = await live_prep.mock_tick("w1", now=late)
        assert r["claimed"] is None and r["expired_backlog"] == 1
        assert (await d.ai_live_mock_jobs.find_one({}))["status"] == "expired_backlog"
    run(monkeypatch, case)


def test_bolna_live_provider_refuses_and_worker_never_starts(monkeypatch):
    async def case(tc, d):
        await _setup_job(tc, d)
        with pytest.raises(PermissionError):
            await live_prep.mock_tick("w1", now=IV - timedelta(days=1), provider=live_prep.BolnaLiveProvider())
        assert (await d.ai_live_mock_jobs.find_one({}))["status"] == "needs_review"
        assert (await d.ai_live_counters.find_one({"_id": "mock:concurrency"}))["active"] == 0
        monkeypatch.setenv("AI_LIVE_WORKER_ENABLED", "true")
        assert live_prep.worker_enabled() is False and live_prep.start_live_worker() is False
        st = await live_prep.worker_status()
        assert st["running"] is False and st["banner"] == "LIVE CALLING DISABLED — PREPARATION ONLY"
    run(monkeypatch, case)


def test_multi_worker_claims_are_exclusive(monkeypatch):
    async def case(tc, d):
        await _setup_job(tc, d)
        rs = await asyncio.gather(*[live_prep.mock_tick(f"w{i}", now=IV - timedelta(days=1)) for i in range(5)])
        assert sum(1 for r in rs if r["claimed"]) == 1
        assert await d.ai_live_mock_jobs.count_documents({"status": "completed"}) == 1
    run(monkeypatch, case)


def test_uncertain_call_counts_toward_daily_until_reconciled(monkeypatch):
    async def case(tc, d):
        await _setup_job(tc, d)
        due = IV - timedelta(days=1)
        await live_prep.mock_tick("w1", now=due, outcome="timeout")
        c = await d.ai_live_counters.find_one({"_id": f"mock:daily:{due.astimezone(live_prep.IST).date().isoformat()}"})
        assert c["count"] == 1
    run(monkeypatch, case)


def test_startup_does_not_start_worker():
    import inspect
    from ai_calling import router
    src = inspect.getsource(router.ensure_ai_indexes)
    assert "mock_tick" not in src and "start_live_worker" not in src
    assert NOW  # fixtures imported
