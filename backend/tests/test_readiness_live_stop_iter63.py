# Regression (iter63): readiness/authorize expose live_calling_stop_off; independence matrix across safety-status, /switches, readiness
import os
import pytest
import requests
from pymongo import MongoClient
from dotenv import load_dotenv

load_dotenv("/app/backend/.env")
BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
API = f"{BASE_URL}/api/ai-calling"
PW = "QAZwsx##123"
DB_NAME = os.environ["DB_NAME"]
assert DB_NAME == "hiring_ai_testing", "refusing to run against non-testing DB"


@pytest.fixture(scope="module")
def mdb():
    c = MongoClient(os.environ["MONGO_URL"])
    yield c[DB_NAME]
    c.close()


@pytest.fixture(scope="module")
def admin():
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/login", json={"username": "Admin User", "password": PW}, timeout=15)
    if r.status_code != 200:
        pytest.skip("login failed")
    s.headers.update({"X-CSRF-Intent": "ai-calling", "Origin": BASE_URL})
    yield s
    # always restore SAFE defaults
    s.post(f"{API}/live-calling-stop", json={"active": True, "reason": "TEST_restore"}, timeout=15)
    s.post(f"{API}/test-calling-permitted", json={"permitted": False, "reason": "TEST_restore"}, timeout=15)
    s.post(f"{API}/emergency-stop", json={"active": True, "reason": "TEST_restore"}, timeout=15)


def _keys(lst):
    return {b["key"] for b in lst}


def _st(s):
    r = s.get(f"{API}/safety-status", timeout=15)
    assert r.status_code == 200
    return r.json()


def _sw(s):
    r = s.get(f"{API}/switches", timeout=15)
    assert r.status_code == 200
    return r.json()


def _rd(s):
    r = s.get(f"{API}/live-dispatch/readiness", timeout=15)
    assert r.status_code == 200
    return {c["key"]: c["ok"] for c in r.json()["checks"]}


def _es(s, on):
    body = {"active": True, "reason": "TEST_es"} if on else {"active": False, "confirmation": "RELEASE EMERGENCY STOP"}
    assert s.post(f"{API}/emergency-stop", json=body, timeout=15).status_code == 200


def _ls(s, on):
    body = {"active": True, "reason": "TEST_ls"} if on else {"active": False, "confirmation": "RELEASE LIVE CALLING STOP"}
    assert s.post(f"{API}/live-calling-stop", json=body, timeout=15).status_code == 200


def _tp(s, on):
    body = {"permitted": True, "confirmation": "PERMIT TEST CALLING"} if on else {"permitted": False, "reason": "TEST_tp"}
    assert s.post(f"{API}/test-calling-permitted", json=body, timeout=15).status_code == 200


# readiness exposes the check with correct bool
def test_readiness_check_toggles(admin):
    _ls(admin, True)
    r = admin.get(f"{API}/live-dispatch/readiness", timeout=15).json()
    item = [c for c in r["checks"] if c["key"] == "live_calling_stop_off"]
    assert len(item) == 1 and item[0]["ok"] is False and item[0]["label"]
    assert r["ready"] is False and r["phase_locked"] is True
    _ls(admin, False)
    assert _rd(admin)["live_calling_stop_off"] is True
    _ls(admin, True)
    assert _rd(admin)["live_calling_stop_off"] is False


# non-False values (missing / truthy string / None) must be treated as stop ON
@pytest.mark.parametrize("val", ["false", None, 0, "unset"])
def test_readiness_non_false_values(admin, mdb, val):
    _ls(admin, True)
    if val == "unset":
        mdb.ai_call_settings.update_one({"_id": "global"}, {"$unset": {"live_calling_stop": ""}})
    else:
        mdb.ai_call_settings.update_one({"_id": "global"}, {"$set": {"live_calling_stop": val}})
    try:
        assert _rd(admin)["live_calling_stop_off"] is False
        assert "live_calling_stop" in _keys(_st(admin)["effective"]["live_blockers"])
    finally:
        mdb.ai_call_settings.update_one({"_id": "global"}, {"$set": {"live_calling_stop": True}})


# authorize: auth + CSRF + 423 + audit preconditions include live_calling_stop_off
def test_authorize_requires_auth():
    r = requests.post(f"{API}/live-dispatch/authorize", json={}, headers={"X-CSRF-Intent": "ai-calling", "Origin": BASE_URL}, timeout=15)
    assert r.status_code in (401, 403)


def test_authorize_requires_csrf(admin):
    r = admin.post(f"{API}/live-dispatch/authorize", json={}, headers={"X-CSRF-Intent": ""}, timeout=15)
    assert r.status_code == 403
    r = admin.post(f"{API}/live-dispatch/authorize", json={}, headers={"Origin": "https://evil.example.com"}, timeout=15)
    assert r.status_code == 403


@pytest.mark.parametrize("stop_on", [True, False])
def test_authorize_audit_precondition(admin, mdb, stop_on):
    _ls(admin, stop_on)
    r = admin.post(f"{API}/live-dispatch/authorize", json={"confirmation": "AUTHORIZE LIVE DISPATCH"}, timeout=15)
    assert r.status_code == 423
    row = mdb.ai_call_audit.find_one({"action": "live_dispatch_authorize_attempt"}, sort=[("_id", -1)])
    assert row and row["result"] == "refused_phase_lock"
    assert "live_calling_stop_off" in row["preconditions"]
    assert row["preconditions"]["live_calling_stop_off"] is (not stop_on)
    assert row["preconditions"]["typed_confirmation"] is True
    _ls(admin, True)
    assert _st(admin)["switches"]["live_dispatch_authorized"] is False


# matrix (a)/(d): emergency stop ON blocks both on all surfaces
def test_matrix_emergency_overrides(admin):
    _ls(admin, False); _tp(admin, True); _es(admin, True)
    e = _st(admin)["effective"]
    assert "emergency_stop" in _keys(e["test_blockers"]) and "emergency_stop" in _keys(e["live_blockers"])
    assert e["can_place_test_call"] is False and e["can_place_live_call"] is False
    sw = _sw(admin)
    assert any("Emergency stop" in b for b in sw["test"]["blockers"])
    assert any("Emergency stop" in b for b in sw["live"]["blockers"])
    assert sw["test"]["can_call"] is False and sw["live"]["can_call"] is False
    assert _rd(admin)["emergency_stop_off"] is False
    _ls(admin, True); _tp(admin, False)


# matrix (b): ES off, LS on, TP on, ai_test on -> test has no LS blocker; live does
def test_matrix_b(admin):
    _es(admin, False); _ls(admin, True); _tp(admin, True)
    st = _st(admin)
    assert st["switches"]["ai_test_enabled"] is True
    e = st["effective"]
    assert "live_calling_stop" not in _keys(e["test_blockers"])
    assert "test_calling_permitted_off" not in _keys(e["test_blockers"])
    assert "live_calling_stop" in _keys(e["live_blockers"])
    sw = _sw(admin)
    assert not any("Live Calling Stop" in b for b in sw["test"]["blockers"])
    assert any("Live Calling Stop" in b for b in sw["live"]["blockers"])
    assert _rd(admin)["live_calling_stop_off"] is False
    _tp(admin, False); _es(admin, True)


# matrix (c): LS off, TP off -> test blocked by test_calling_permitted_off; live not blocked by LS
def test_matrix_c(admin):
    _es(admin, False); _ls(admin, False); _tp(admin, False)
    e = _st(admin)["effective"]
    assert "test_calling_permitted_off" in _keys(e["test_blockers"])
    assert "live_calling_stop" not in _keys(e["live_blockers"])
    assert "test_calling_permitted_off" not in _keys(e["live_blockers"])
    sw = _sw(admin)
    assert any("Test Calling Permitted is OFF" in b for b in sw["test"]["blockers"])
    assert not any("Live Calling Stop" in b for b in sw["live"]["blockers"])
    assert _rd(admin)["live_calling_stop_off"] is True
    _ls(admin, True); _es(admin, True)


# switch endpoints: wrong phrase rejected, persisted, audited
def test_switch_wrong_phrases_and_audit(admin, mdb):
    _ls(admin, True); _tp(admin, False)
    assert admin.post(f"{API}/live-calling-stop", json={"active": False, "confirmation": "release"}, timeout=15).status_code == 400
    assert admin.post(f"{API}/test-calling-permitted", json={"permitted": True, "confirmation": "nope"}, timeout=15).status_code == 400
    assert admin.post(f"{API}/emergency-stop", json={"active": False, "confirmation": "x"}, timeout=15).status_code == 400
    doc = mdb.ai_call_settings.find_one({"_id": "global"})
    assert doc["live_calling_stop"] is True and doc["test_calling_permitted"] is False
    before = mdb.ai_call_audit.count_documents({"action": "test_calling_permitted"})
    _tp(admin, True)
    assert mdb.ai_call_settings.find_one({"_id": "global"})["test_calling_permitted"] is True
    assert mdb.ai_call_audit.count_documents({"action": "test_calling_permitted"}) == before + 1
    _tp(admin, False)


def test_switches_require_auth_csrf(admin):
    h = {"X-CSRF-Intent": "ai-calling", "Origin": BASE_URL}
    assert requests.post(f"{API}/live-calling-stop", json={"active": True}, headers=h, timeout=15).status_code in (401, 403)
    assert requests.post(f"{API}/test-calling-permitted", json={"permitted": False}, headers=h, timeout=15).status_code in (401, 403)
    assert admin.post(f"{API}/live-calling-stop", json={"active": True}, headers={"X-CSRF-Intent": ""}, timeout=15).status_code == 403
    assert admin.post(f"{API}/test-calling-permitted", json={"permitted": False}, headers={"X-CSRF-Intent": ""}, timeout=15).status_code == 403
