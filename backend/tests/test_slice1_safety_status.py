"""Slice 1 regression tests for the unified authoritative safety-status endpoint and the
Emergency Stop engage/release contract.

These exercise the endpoint handlers directly, not over HTTP, so they run without a live server
and without touching the real production DB.
"""
import asyncio
import os
import sys

import mongomock_motor
import pytest

sys.path.insert(0, '/app/backend')

from fastapi import HTTPException  # noqa: E402

# noinspection PyProtectedMember
from ai_calling import router as ai_router_mod  # noqa: E402
from ai_calling import store, modes, provider  # noqa: E402
from ai_calling.router import emergency_stop as emergency_stop_endpoint, safety_status, StopBody  # noqa: E402

# Hard-pin "testing" env so no real AI_CALLING_ENABLED leaks in.
os.environ["AI_CALLING_ENABLED"] = "false"


class _Req:
    """FastAPI Request stand-in with CSRF + headers the endpoints use."""
    def __init__(self, headers=None):
        self.headers = {"X-CSRF-Intent": "ai-calling", **(headers or {})}


async def _fake_auth(_request):
    return "test-admin"


def _wire(db_):
    store._state["db"] = db_
    store._state["auth"] = _fake_auth
    ai_router_mod._state["db"] = db_
    ai_router_mod._state["auth"] = _fake_auth


@pytest.fixture()
def db_():
    # Use a pure in-memory Mongo so the real hiring_ai_testing DB is never touched.
    client = mongomock_motor.AsyncMongoMockClient()
    database = client["slice1_test"]
    _wire(database)
    yield database


@pytest.fixture(autouse=True)
def _overall_test_true(monkeypatch):
    # Overall-test-mode read is a module-level function — stub so tests don't depend on messaging.
    monkeypatch.setattr(modes, "overall_test_mode", lambda: True)
    yield


def run(coro):
    return asyncio.get_event_loop().run_until_complete(coro) if sys.version_info < (3, 10) else asyncio.run(coro)


def test_safety_status_shape_when_all_safe(db_):
    async def go():
        await db_.ai_call_settings.update_one({"_id": "global"},
            {"$set": {**store.SETTINGS_DEFAULTS, "emergency_stop": True, "ai_test_enabled": True,
                      "ai_live_enabled": False, "live_dispatch_authorized": False}}, upsert=True)
        r = await safety_status(_Req())
        assert r["authoritative"] is True
        assert r["emergency_stop"]["active"] is True
        assert r["switches"]["ai_test_enabled"] is True
        assert r["switches"]["ai_live_enabled"] is False
        assert r["switches"]["live_dispatch_authorized"] is False
        assert r["server"]["outbound_calling_enabled"] is False  # AI_CALLING_ENABLED=false
        assert r["server"]["env_flag_is_runtime_editable"] is False
        # Both test and live must be BLOCKED while Emergency Stop is ON + server flag off.
        assert r["effective"]["can_place_test_call"] is False
        assert r["effective"]["can_place_live_call"] is False
        test_keys = {b["key"] for b in r["effective"]["test_blockers"]}
        assert "emergency_stop" in test_keys and "server_disabled" in test_keys
    run(go())


def test_engage_emergency_stop_writes_audit_and_separate_timestamp(db_):
    async def go():
        await db_.ai_call_settings.update_one({"_id": "global"},
            {"$set": {**store.SETTINGS_DEFAULTS, "emergency_stop": False}}, upsert=True)
        await emergency_stop_endpoint(StopBody(active=True, reason="unit-test"), _Req())
        doc = await db_.ai_call_settings.find_one({"_id": "global"})
        assert doc["emergency_stop"] is True
        assert doc["emergency_stop_at"]
        assert doc["emergency_stop_by"] == "test-admin"
        assert doc["emergency_stop_reason"] == "unit-test"
        audit = await db_.ai_call_audit.find_one({"action": "emergency_stop_engaged"})
        assert audit and audit["previous"] is False and audit["current"] is True
    run(go())


def test_release_requires_typed_phrase(db_):
    async def go():
        await db_.ai_call_settings.update_one({"_id": "global"},
            {"$set": {**store.SETTINGS_DEFAULTS, "emergency_stop": True}}, upsert=True)
        with pytest.raises(HTTPException) as e:
            await emergency_stop_endpoint(StopBody(active=False, reason="r"), _Req())
        assert e.value.status_code == 400
        assert "RELEASE EMERGENCY STOP" in e.value.detail
        # confirmation present → succeeds
        await emergency_stop_endpoint(
            StopBody(active=False, reason="r", confirmation="RELEASE EMERGENCY STOP"), _Req())
        doc = await db_.ai_call_settings.find_one({"_id": "global"})
        assert doc["emergency_stop"] is False
        assert doc["emergency_stop_released_at"]
        assert doc["emergency_stop_released_by"] == "test-admin"
    run(go())


def test_release_does_not_modify_other_gates(db_):
    """Releasing Emergency Stop must leave AI Test/Live, server flag and Live Dispatch untouched."""
    async def go():
        await db_.ai_call_settings.update_one({"_id": "global"},
            {"$set": {**store.SETTINGS_DEFAULTS, "emergency_stop": True, "ai_test_enabled": False,
                      "ai_live_enabled": False, "live_dispatch_authorized": False}}, upsert=True)
        before = await db_.ai_call_settings.find_one({"_id": "global"})
        await emergency_stop_endpoint(
            StopBody(active=False, reason="r", confirmation="RELEASE EMERGENCY STOP"), _Req())
        after = await db_.ai_call_settings.find_one({"_id": "global"})
        for k in ("ai_test_enabled", "ai_live_enabled", "live_dispatch_authorized",
                  "live_daily_call_limit", "live_pilot_daily_cap"):
            assert before[k] == after[k], f"{k} changed on release"
    run(go())


def test_engage_is_idempotent_no_duplicate_audit(db_):
    async def go():
        await db_.ai_call_settings.update_one({"_id": "global"},
            {"$set": {**store.SETTINGS_DEFAULTS, "emergency_stop": True}}, upsert=True)
        await emergency_stop_endpoint(StopBody(active=True, reason="dup"), _Req())
        await emergency_stop_endpoint(StopBody(active=True, reason="dup"), _Req())
        n = await db_.ai_call_audit.count_documents({"action": "emergency_stop_engaged"})
        assert n == 0  # already ON → no audit entry
    run(go())


def test_engage_cancels_pending_jobs_only(db_):
    async def go():
        await db_.ai_call_settings.update_one({"_id": "global"},
            {"$set": {**store.SETTINGS_DEFAULTS, "emergency_stop": False}}, upsert=True)
        await db_.ai_call_jobs.insert_many([
            {"status": "pending", "mode": "testing"},
            {"status": "pending", "mode": "live"},
            {"status": "completed", "mode": "testing"},
        ])
        await emergency_stop_endpoint(StopBody(active=True, reason="cancel"), _Req())
        pending = await db_.ai_call_jobs.count_documents({"status": "pending"})
        cancelled = await db_.ai_call_jobs.count_documents({"status": "cancelled"})
        completed = await db_.ai_call_jobs.count_documents({"status": "completed"})
        assert pending == 0 and cancelled == 2 and completed == 1
    run(go())


def test_safety_status_is_authoritative_false_on_db_error(db_, monkeypatch):
    async def go():
        async def boom(*_a, **_kw):
            raise RuntimeError("db down")
        # The endpoint resolves get_settings via the router module's import, so patch there.
        monkeypatch.setattr(ai_router_mod, "get_settings", boom)
        r = await safety_status(_Req())
        assert r["authoritative"] is False
        assert "Safety status unavailable" in r["error"]
    run(go())
