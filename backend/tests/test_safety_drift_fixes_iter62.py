# Regression (iter62): drift fixes for safety-status test_blockers, /switches flags, readiness live_calling_stop_off, independence matrix
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
API = f"{BASE_URL}/api/ai-calling"
PW = "QAZwsx##123"


@pytest.fixture(scope="module")
def admin():
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/login", json={"username": "Admin User", "password": PW}, timeout=15)
    if r.status_code != 200:
        pytest.skip("login failed")
    s.headers.update({"X-CSRF-Intent": "ai-calling", "Origin": BASE_URL})
    snap = s.get(f"{API}/safety-status", timeout=15).json()
    yield s
    sw = snap["switches"]
    if sw["live_calling_stop"]:
        s.post(f"{API}/live-calling-stop", json={"active": True, "reason": "TEST_restore"}, timeout=15)
    else:
        s.post(f"{API}/live-calling-stop", json={"active": False, "confirmation": "RELEASE LIVE CALLING STOP"}, timeout=15)
    if sw["test_calling_permitted"]:
        s.post(f"{API}/test-calling-permitted", json={"permitted": True, "confirmation": "PERMIT TEST CALLING"}, timeout=15)
    else:
        s.post(f"{API}/test-calling-permitted", json={"permitted": False, "reason": "TEST_restore"}, timeout=15)
    if snap["emergency_stop"]["active"]:
        s.post(f"{API}/emergency-stop", json={"active": True, "reason": "TEST_restore"}, timeout=15)
    else:
        s.post(f"{API}/emergency-stop", json={"active": False, "confirmation": "RELEASE EMERGENCY STOP"}, timeout=15)


def _keys(lst):
    return {b["key"] for b in lst}


def _st(s):
    r = s.get(f"{API}/safety-status", timeout=15)
    assert r.status_code == 200
    return r.json()


def _es(s, on):
    body = {"active": True, "reason": "TEST_es"} if on else {"active": False, "confirmation": "RELEASE EMERGENCY STOP"}
    assert s.post(f"{API}/emergency-stop", json=body, timeout=15).status_code == 200


def _ls(s, on):
    body = {"active": True, "reason": "TEST_ls"} if on else {"active": False, "confirmation": "RELEASE LIVE CALLING STOP"}
    assert s.post(f"{API}/live-calling-stop", json=body, timeout=15).status_code == 200


def _tp(s, on):
    body = {"permitted": True, "confirmation": "PERMIT TEST CALLING"} if on else {"permitted": False, "reason": "TEST_tp"}
    assert s.post(f"{API}/test-calling-permitted", json=body, timeout=15).status_code == 200


def _readiness(s):
    r = s.get(f"{API}/live-dispatch/readiness", timeout=15)
    assert r.status_code == 200
    return {c["key"]: c["ok"] for c in r.json()["checks"]}


# safety-status: test_calling_permitted_off in test_blockers
def test_test_permit_off_in_test_blockers(admin):
    _es(admin, False); _tp(admin, False)
    st = _st(admin)
    assert "test_calling_permitted_off" in _keys(st["effective"]["test_blockers"])
    assert st["effective"]["can_place_test_call"] is False
    _tp(admin, True)
    assert "test_calling_permitted_off" not in _keys(_st(admin)["effective"]["test_blockers"])
    _tp(admin, False)


def test_live_stop_in_live_blockers(admin):
    _es(admin, False); _ls(admin, True)
    st = _st(admin)
    assert "live_calling_stop" in _keys(st["effective"]["live_blockers"])
    assert st["effective"]["can_place_live_call"] is False


# /switches top-level flags + blocker phrases
def test_switches_flags_and_phrases(admin):
    _ls(admin, True); _tp(admin, False)
    d = admin.get(f"{API}/switches", timeout=15).json()
    assert d["live_calling_stop"] is True and d["test_calling_permitted"] is False
    assert any("Test Calling Permitted is OFF" in b for b in d["test"]["blockers"])
    assert any("Live Calling Stop is engaged" in b for b in d["live"]["blockers"])
    assert not any("Live Calling Stop" in b for b in d["test"]["blockers"])
    assert not any("Test Calling Permitted" in b for b in d["live"]["blockers"])
    _ls(admin, False); _tp(admin, True)
    d = admin.get(f"{API}/switches", timeout=15).json()
    assert d["live_calling_stop"] is False and d["test_calling_permitted"] is True
    assert not any("Test Calling Permitted is OFF" in b for b in d["test"]["blockers"])
    assert not any("Live Calling Stop is engaged" in b for b in d["live"]["blockers"])
    _ls(admin, True); _tp(admin, False)


# readiness check live_calling_stop_off
def test_readiness_live_stop_check(admin):
    _ls(admin, True)
    c = _readiness(admin)
    assert "live_calling_stop_off" in c, f"readiness keys: {sorted(c)}"
    assert c["live_calling_stop_off"] is False
    _ls(admin, False)
    assert _readiness(admin)["live_calling_stop_off"] is True
    _ls(admin, True)


# independence matrix
def test_independence_matrix(admin):
    _es(admin, False)
    _tp(admin, False)
    _ls(admin, True); a = _st(admin)["effective"]
    _ls(admin, False); b = _st(admin)["effective"]
    assert _keys(a["test_blockers"]) == _keys(b["test_blockers"])
    _ls(admin, True)
    _tp(admin, False); c = _st(admin)["effective"]
    _tp(admin, True); d = _st(admin)["effective"]
    assert _keys(c["live_blockers"]) == _keys(d["live_blockers"])
    _tp(admin, False)
    _es(admin, True); e = _st(admin)["effective"]
    assert "emergency_stop" in _keys(e["test_blockers"]) and "emergency_stop" in _keys(e["live_blockers"])
