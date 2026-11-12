"""B4 regression: `test_calling_permitted` is strictly enforced on every test-call path.

Covers:
  - gate.evaluate(single_call=True) emits a clear blocker when the flag is not strictly True
    (missing, null, False, 0, 1, "true", "yes" → all fail closed; only True unlocks).
  - dispatch.call_now atomic lock refuses to acquire when the flag is anything other than True.
  - dispatch.call_now succeeds (mocked Bolna) only when the flag is True.
  - Concurrent call_now requests: lock serialises to one dispatch even under race.
  - Permission flipped OFF mid-flight: the next call_now attempt is blocked immediately.
  - Batch start (router.start_batch) is independently refused when the flag is not True —
    cannot bypass through the batch dispatch path.
  - Live permission (`effective_live_permission`) is independent — test flag never unlocks Live.

Everything runs against a scratch Motor DB; Bolna transport is mocked. No real network.
"""
import asyncio
import os
import sys
import uuid

import httpx
import pytest
from bson import ObjectId
from fastapi import FastAPI
from motor.motor_asyncio import AsyncIOMotorClient

sys.path.insert(0, '/app/backend')
from ai_calling import bolna_client as bc  # noqa: E402
from ai_calling import dispatch, gate, provider, store  # noqa: E402
from ai_calling import router as ai_router_mod  # noqa: E402
from ai_calling.safety_flags import effective_live_permission, effective_test_permission  # noqa: E402

SCRATCH = "ai_calling_perm_scratch_test"
AGENT = "agent-b4-test"
H = {"X-CSRF-Intent": "ai-calling"}


def _cand(**over):
    base = {"mode": "testing", "candidate_name": "Test Colleague", "phone_e164": "+919876500001",
            "consent_status": "granted", "consent_phone": "+919876500001", "opted_out": False,
            "interview_date": "2099-01-01", "test_candidate_id": "TC-1",
            "company_name": "BluBridge", "job_role": "Engineer", "interview_time": "11:00",
            "office_address": "Addr", "language": "english"}
    base.update(over)
    return base


async def _fake_admin(_r):
    return "pytest-admin"


def _run(fn):
    async def main():
        assert SCRATCH not in (os.environ.get("DB_NAME", ""), "hiring_ai_testing", "hr_analytics")
        client = AsyncIOMotorClient("mongodb://localhost:27017")
        d = client[SCRATCH]
        await client.drop_database(SCRATCH)
        await d.ai_call_jobs.create_index("idempotency_key", unique=True, sparse=True)
        await d.ai_calls.create_index("execution_id", unique=True, sparse=True)
        try:
            await fn(d)
        finally:
            await client.drop_database(SCRATCH)
    asyncio.run(main())


def _settings_doc(**over):
    base = {**store.SETTINGS_DEFAULTS, "mode": "testing", "emergency_stop": False,
            "ai_test_enabled": True, "test_calling_permitted": True,
            "call_window_start": "00:00", "call_window_end": "23:59"}
    base.update(over)
    return {"_id": "global", **base}


async def _seed(d, *, settings_over=None):
    await d.ai_call_settings.insert_one(_settings_doc(**(settings_over or {})))
    await d.ai_provider_settings.insert_one({"_id": "bolna", "agent_id": AGENT,
                                             "caller_number": "+918000001993", "api_key_encrypted": "x"})


def _mp(monkeypatch, d, *, place=None):
    sent = []

    async def fake_place(*, gate_result, api_key, body):
        sent.append(body)
        await asyncio.sleep(0.02)
        return await place(body) if place else {"execution_id": f"ex-{len(sent)}", "status": "queued"}

    monkeypatch.setitem(store._state, "db", d)
    monkeypatch.setitem(store._state, "auth", _fake_admin)
    monkeypatch.setitem(ai_router_mod._state, "db", d)
    monkeypatch.setitem(ai_router_mod._state, "auth", _fake_admin)
    monkeypatch.setenv("AI_CALLING_ENABLED", "true")
    monkeypatch.setattr(provider, "provider_ready", lambda _d: True)
    monkeypatch.setattr(gate, "SINGLE_TEST_CALL_APPROVED", True)
    monkeypatch.setattr(dispatch, "decrypt_api_key", lambda _d: "stub-key")
    monkeypatch.setattr(dispatch, "ensure_poller", lambda: None)
    monkeypatch.setattr(bc, "place_call", fake_place)
    return sent


def _app():
    app = FastAPI()
    app.include_router(dispatch.dispatch_router, prefix="/api/ai-calling")
    app.include_router(ai_router_mod.ai_router)
    return app


def _key():
    return uuid.uuid4().hex


# ---------------- gate.evaluate strict-True enforcement ----------------

@pytest.mark.parametrize("value", [False, None, 0, 1, "true", "yes", "True", [], {}, "", "false"])
def test_gate_rejects_when_flag_is_not_strictly_true(monkeypatch, value):
    """Fail-closed: anything other than Python True must leave the gate blocking."""
    async def fn(d):
        await _seed(d, settings_over={"test_calling_permitted": value})
        _mp(monkeypatch, d)
        oid = (await d.ai_test_candidates.insert_one(_cand())).inserted_id
        v = await gate.evaluate(mode="testing", test_candidate_id=str(oid), batch_id="",
                                phone_e164="+919876500001", mode_version=1, single_call=True)
        keys = {c["key"]: c["ok"] for c in v["checks"]}
        assert keys["test_calling_permitted"] is False, f"value={value!r} must fail closed"
        assert v["allowed"] is False
    _run(fn)


def test_gate_accepts_when_flag_is_strictly_true(monkeypatch):
    async def fn(d):
        await _seed(d, settings_over={"test_calling_permitted": True})
        _mp(monkeypatch, d)
        oid = (await d.ai_test_candidates.insert_one(_cand())).inserted_id
        v = await gate.evaluate(mode="testing", test_candidate_id=str(oid), batch_id="",
                                phone_e164="+919876500001", mode_version=1, single_call=True)
        keys = {c["key"]: c["ok"] for c in v["checks"]}
        assert keys["test_calling_permitted"] is True
        assert v["allowed"] is True, v
    _run(fn)


def test_gate_batch_path_also_includes_permission_check(monkeypatch):
    """Batch preflight (single_call=False) must still expose the flag so no alternate
    dispatch path can silently proceed without it."""
    async def fn(d):
        await _seed(d, settings_over={"test_calling_permitted": False})
        _mp(monkeypatch, d)
        oid = (await d.ai_test_candidates.insert_one(_cand())).inserted_id
        v = await gate.evaluate(mode="testing", test_candidate_id=str(oid), batch_id=str(ObjectId()),
                                phone_e164="+919876500001", mode_version=1, single_call=False)
        keys = {c["key"]: c["ok"] for c in v["checks"]}
        assert keys["test_calling_permitted"] is False
        assert v["allowed"] is False
    _run(fn)


# ---------------- dispatch atomic-lock enforcement ----------------

async def _call(tc, cid, *, key=None, name="Test Colleague"):
    return await tc.post(f"/api/ai-calling/test-candidates/{cid}/call-now",
                         json={"idempotency_key": key or _key(), "confirm_name": name}, headers=H)


def test_call_now_blocked_when_flag_false(monkeypatch):
    """Atomic lock refuses to acquire → 409 and no provider request is sent."""
    async def fn(d):
        await _seed(d, settings_over={"test_calling_permitted": False})
        sent = _mp(monkeypatch, d)
        oid = str((await d.ai_test_candidates.insert_one(_cand())).inserted_id)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=_app()), base_url="http://t") as tc:
            r = await _call(tc, oid)
            assert r.status_code == 409, r.text
            assert "test-only" in r.json()["detail"].lower()
        assert sent == []
        assert await d.ai_calls.count_documents({}) == 0
        assert await d.ai_call_jobs.count_documents({}) == 0
        s = await d.ai_call_settings.find_one({"_id": "global"})
        assert s.get("dispatch_lock") is None, "lock must not be acquired when flag is False"
    _run(fn)


@pytest.mark.parametrize("bad", [False, None, 0, 1, "true"])
def test_call_now_blocked_on_malformed_flag(monkeypatch, bad):
    async def fn(d):
        await _seed(d, settings_over={"test_calling_permitted": bad})
        sent = _mp(monkeypatch, d)
        oid = str((await d.ai_test_candidates.insert_one(_cand())).inserted_id)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=_app()), base_url="http://t") as tc:
            r = await _call(tc, oid)
            assert r.status_code == 409, (bad, r.text)
        assert sent == []
        assert await d.ai_calls.count_documents({}) == 0
    _run(fn)


def test_call_now_blocked_when_flag_missing(monkeypatch):
    """Absent key in the settings document must also fail closed."""
    async def fn(d):
        # Seed settings explicitly WITHOUT the flag key.
        base = {**store.SETTINGS_DEFAULTS, "mode": "testing", "emergency_stop": False,
                "ai_test_enabled": True, "call_window_start": "00:00", "call_window_end": "23:59"}
        base.pop("test_calling_permitted", None)
        await d.ai_call_settings.insert_one({"_id": "global", **base})
        await d.ai_provider_settings.insert_one({"_id": "bolna", "agent_id": AGENT,
                                                 "caller_number": "+918000001993", "api_key_encrypted": "x"})
        sent = _mp(monkeypatch, d)
        oid = str((await d.ai_test_candidates.insert_one(_cand())).inserted_id)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=_app()), base_url="http://t") as tc:
            r = await _call(tc, oid)
            assert r.status_code == 409, r.text
        assert sent == []
    _run(fn)


def test_call_now_succeeds_when_flag_true(monkeypatch):
    async def fn(d):
        await _seed(d, settings_over={"test_calling_permitted": True})
        sent = _mp(monkeypatch, d)
        oid = str((await d.ai_test_candidates.insert_one(_cand())).inserted_id)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=_app()), base_url="http://t") as tc:
            r = await _call(tc, oid)
            assert r.status_code == 200, r.text
            assert r.json()["state"] == "accepted"
        assert len(sent) == 1
        s = await d.ai_call_settings.find_one({"_id": "global"})
        assert s.get("dispatch_lock") is None, "lock must be released after dispatch"
    _run(fn)


# ---------------- concurrency and mid-flight flag changes ----------------

def test_concurrent_call_now_serialises_to_one_dispatch(monkeypatch):
    """When the flag is True, 10 concurrent attempts must still result in ONE provider call —
    the atomic lock + idempotency key together guarantee single dispatch."""
    async def fn(d):
        await _seed(d, settings_over={"test_calling_permitted": True})
        sent = _mp(monkeypatch, d)
        oid = str((await d.ai_test_candidates.insert_one(_cand())).inserted_id)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=_app()), base_url="http://t") as tc:
            rs = await asyncio.gather(*[_call(tc, oid, key=f"idem-key-concurrent-{i:04d}") for i in range(10)])
        ok = [r for r in rs if r.status_code == 200 and r.json().get("dispatched")]
        assert len(sent) == 1, "exactly one provider call must be placed"
        assert len(ok) == 1, "exactly one dispatch must succeed under race"
        assert await d.ai_calls.count_documents({}) == 1
        s = await d.ai_call_settings.find_one({"_id": "global"})
        assert s.get("dispatch_lock") is None
    _run(fn)


def test_concurrent_call_now_all_blocked_when_flag_false(monkeypatch):
    async def fn(d):
        await _seed(d, settings_over={"test_calling_permitted": False})
        sent = _mp(monkeypatch, d)
        oid = str((await d.ai_test_candidates.insert_one(_cand())).inserted_id)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=_app()), base_url="http://t") as tc:
            rs = await asyncio.gather(*[_call(tc, oid, key=f"idem-key-blocked-{i:04d}") for i in range(10)])
        assert all(r.status_code == 409 for r in rs)
        assert sent == []
        assert await d.ai_calls.count_documents({}) == 0
    _run(fn)


def test_flag_flipped_off_between_requests_blocks_next_attempt(monkeypatch):
    """A successful call does not 'latch' the permission on — flipping the flag OFF must
    immediately block subsequent attempts even if the previous one succeeded."""
    async def fn(d):
        await _seed(d, settings_over={"test_calling_permitted": True})
        sent = _mp(monkeypatch, d)
        oid = str((await d.ai_test_candidates.insert_one(_cand())).inserted_id)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=_app()), base_url="http://t") as tc:
            r1 = await _call(tc, oid, key="idem-key-first-call-0001")
            assert r1.status_code == 200 and r1.json()["state"] == "accepted"
            # mark the finished call as resolved so BLOCKING set is clear
            await d.ai_calls.update_many({}, {"$set": {"state": "finished", "status": "completed"}})
            await d.ai_call_jobs.update_many({}, {"$set": {"status": "finished"}})
            # flip OFF
            await d.ai_call_settings.update_one({"_id": "global"}, {"$set": {"test_calling_permitted": False}})
            r2 = await _call(tc, oid, key="idem-key-second-call-002")
            assert r2.status_code == 409, r2.text
        assert len(sent) == 1, "no second provider call after flag flip"
    _run(fn)


# ---------------- batch dispatch path ----------------

def test_batch_start_blocked_when_flag_false(monkeypatch):
    """The batch dispatch endpoint independently enforces the flag — even if BOLNA integration
    were later approved, the flag must still gate the batch path."""
    async def fn(d):
        await _seed(d, settings_over={"test_calling_permitted": False})
        _mp(monkeypatch, d)
        cid = str((await d.ai_test_candidates.insert_one(_cand())).inserted_id)
        bres = await d.ai_test_batches.insert_one({"name": "B", "candidate_ids": [cid], "mode": "testing",
                                                   "status": "draft", "mode_version": 1})
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=_app()), base_url="http://t") as tc:
            r = await tc.post(f"/api/ai-calling/test-batches/{bres.inserted_id}/start", headers=H)
            assert r.status_code == 423, r.text
            assert "test-only" in r.json()["detail"].lower()
    _run(fn)


def test_batch_start_still_blocked_when_flag_true_due_to_bolna_lock(monkeypatch):
    """Independent-gate invariant: the test-only flag ALONE must not be enough to unlock
    batch calling — BOLNA_INTEGRATION_APPROVED is an independent gate."""
    async def fn(d):
        await _seed(d, settings_over={"test_calling_permitted": True})
        _mp(monkeypatch, d)
        cid = str((await d.ai_test_candidates.insert_one(_cand())).inserted_id)
        bres = await d.ai_test_batches.insert_one({"name": "B", "candidate_ids": [cid], "mode": "testing",
                                                   "status": "draft", "mode_version": 1})
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=_app()), base_url="http://t") as tc:
            r = await tc.post(f"/api/ai-calling/test-batches/{bres.inserted_id}/start", headers=H)
            assert r.status_code == 423, r.text
            assert "bolna" in r.json()["detail"].lower()
    _run(fn)


# ---------------- Live permission isolation ----------------

def test_test_flag_never_unlocks_live_permission():
    """safety_flags.effective_live_permission has its own independent gates. The test-only
    flag must have zero effect on Live permission."""
    s = {**store.SETTINGS_DEFAULTS, "emergency_stop": False, "ai_live_enabled": True,
         "live_dispatch_authorized": True, "test_calling_permitted": True, "ai_test_enabled": True}
    live = effective_live_permission(s, server_enabled=True, provider_ready=True)
    # Live is still blocked by code_locked (LIVE_DISPATCH_IMPLEMENTED == False).
    assert live["permitted"] is False
    keys = {b["key"] for b in live["blockers"]}
    assert "code_locked" in keys
    test = effective_test_permission(s, server_enabled=True, provider_ready=True)
    assert test["permitted"] is True


def test_live_permission_blocks_without_test_flag():
    """And conversely — the live permission result is unchanged whether the test flag is on
    or off (zero cross-effect)."""
    on = {**store.SETTINGS_DEFAULTS, "emergency_stop": False, "ai_live_enabled": True,
          "live_dispatch_authorized": True, "test_calling_permitted": True}
    off = {**on, "test_calling_permitted": False}
    l_on = effective_live_permission(on, server_enabled=True, provider_ready=True)
    l_off = effective_live_permission(off, server_enabled=True, provider_ready=True)
    assert {b["key"] for b in l_on["blockers"]} == {b["key"] for b in l_off["blockers"]}
