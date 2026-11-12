# Regression: independent Live Calling Stop + Test Calling Permitted switches (HTTP, public URL)
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
API = f"{BASE_URL}/api/ai-calling"
PW = "QAZwsx##123"


def _login():
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/login", json={"username": "Admin User", "password": PW}, timeout=15)
    if r.status_code != 200:
        pytest.skip(f"login failed {r.status_code} {r.text[:120]}")
    s.headers.update({"X-CSRF-Intent": "ai-calling", "Origin": BASE_URL})
    return s


@pytest.fixture(scope="module")
def admin():
    s = _login()
    snap = s.get(f"{API}/safety-status", timeout=15).json()
    yield s
    # restore snapshot
    sw = snap["switches"]
    est = snap["emergency_stop"]["active"]
    s.post(f"{API}/live-calling-stop", json={"active": True, "reason": "TEST_restore"}, timeout=15)
    if not sw["live_calling_stop"]:
        s.post(f"{API}/live-calling-stop", json={"active": False, "confirmation": "RELEASE LIVE CALLING STOP"}, timeout=15)
    s.post(f"{API}/test-calling-permitted", json={"permitted": False, "reason": "TEST_restore"}, timeout=15)
    if sw["test_calling_permitted"]:
        s.post(f"{API}/test-calling-permitted", json={"permitted": True, "confirmation": "PERMIT TEST CALLING"}, timeout=15)
    if est:
        s.post(f"{API}/emergency-stop", json={"active": True, "reason": "TEST_restore"}, timeout=15)
    else:
        s.post(f"{API}/emergency-stop", json={"active": False, "confirmation": "RELEASE EMERGENCY STOP"}, timeout=15)


def _status(s):
    r = s.get(f"{API}/safety-status", timeout=15)
    assert r.status_code == 200
    return r.json()


def _keys(lst):
    return {b["key"] for b in lst}


# Auth
def test_unauthenticated_blocked():
    for m, p in (("get", "/safety-status"), ("post", "/live-calling-stop"), ("post", "/test-calling-permitted")):
        r = getattr(requests, m)(f"{API}{p}", json={"active": True, "permitted": False},
                                 headers={"X-CSRF-Intent": "ai-calling"}, timeout=15)
        assert r.status_code in (401, 403), (p, r.status_code)


# safety-status shape
def test_safety_status_shape(admin):
    d = _status(admin)
    assert d["authoritative"] is True
    assert isinstance(d["switches"]["live_calling_stop"], bool)
    assert isinstance(d["switches"]["test_calling_permitted"], bool)
    assert "active" in d["live_calling_stop"] and "active" in d["test_calling_permitted"]


# Live Calling Stop
def test_live_stop_csrf_required(admin):
    r = admin.post(f"{API}/live-calling-stop", json={"active": True}, headers={"X-CSRF-Intent": None}, timeout=15)
    assert r.status_code == 403


def test_test_permit_csrf_required(admin):
    r = admin.post(f"{API}/test-calling-permitted", json={"permitted": False}, headers={"X-CSRF-Intent": None}, timeout=15)
    assert r.status_code == 403


def test_live_stop_bad_origin_rejected(admin):
    r = admin.post(f"{API}/live-calling-stop", json={"active": True}, headers={"Origin": "https://evil.example"}, timeout=15)
    assert r.status_code == 403


def test_live_stop_engage_release_audit(admin):
    from pymongo import MongoClient
    from dotenv import load_dotenv
    load_dotenv("/app/backend/.env")
    d = MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
    # ensure engaged (idempotent)
    r = admin.post(f"{API}/live-calling-stop", json={"active": True}, timeout=15)
    assert r.status_code == 200
    assert _status(admin)["switches"]["live_calling_stop"] is True
    # release w/o phrase -> 400
    r = admin.post(f"{API}/live-calling-stop", json={"active": False}, timeout=15)
    assert r.status_code == 400 and "RELEASE LIVE CALLING STOP" in r.text
    assert _status(admin)["switches"]["live_calling_stop"] is True
    # wrong phrase -> 400
    r = admin.post(f"{API}/live-calling-stop", json={"active": False, "confirmation": "release live calling stop"}, timeout=15)
    assert r.status_code == 400
    # release with phrase
    r = admin.post(f"{API}/live-calling-stop", json={"active": False, "reason": "TEST_rel",
                                                     "confirmation": "RELEASE LIVE CALLING STOP"}, timeout=15)
    assert r.status_code == 200
    st = _status(admin)
    assert st["switches"]["live_calling_stop"] is False
    assert st["live_calling_stop"]["released_by"] == "Admin User"
    assert "live_calling_stop" not in _keys(st["effective"]["live_blockers"])
    # re-engage, audit row
    n_before = d.ai_call_audit.count_documents({"action": "live_calling_stop_engaged"})
    r = admin.post(f"{API}/live-calling-stop", json={"active": True, "reason": "TEST_eng"}, timeout=15)
    assert r.status_code == 200
    assert d.ai_call_audit.count_documents({"action": "live_calling_stop_engaged"}) == n_before + 1
    row = d.ai_call_audit.find_one({"action": "live_calling_stop_engaged"}, sort=[("at", -1)])
    assert row["by"] == "Admin User" and row["reason"] == "TEST_eng" and row["current"] is True
    # idempotent: no new audit
    admin.post(f"{API}/live-calling-stop", json={"active": True}, timeout=15)
    assert d.ai_call_audit.count_documents({"action": "live_calling_stop_engaged"}) == n_before + 1
    assert d.ai_call_audit.find_one({"action": "live_calling_stop_released", "reason": "TEST_rel"}) is not None


# Test Calling Permitted
def test_test_permit_flow(admin):
    admin.post(f"{API}/test-calling-permitted", json={"permitted": False}, timeout=15)
    r = admin.post(f"{API}/test-calling-permitted", json={"permitted": True}, timeout=15)
    assert r.status_code == 400 and "PERMIT TEST CALLING" in r.text
    assert _status(admin)["switches"]["test_calling_permitted"] is False
    r = admin.post(f"{API}/test-calling-permitted", json={"permitted": True, "confirmation": "PERMIT TEST CALLING"}, timeout=15)
    assert r.status_code == 200
    st = _status(admin)
    assert st["switches"]["test_calling_permitted"] is True
    assert st["test_calling_permitted"]["permitted_by"] == "Admin User"
    r = admin.post(f"{API}/test-calling-permitted", json={"permitted": False}, timeout=15)
    assert r.status_code == 200
    assert _status(admin)["switches"]["test_calling_permitted"] is False


def test_invalid_body_422(admin):
    r = admin.post(f"{API}/live-calling-stop", json={}, timeout=15)
    assert r.status_code == 422
    r = admin.post(f"{API}/test-calling-permitted", json={"permitted": "maybe"}, timeout=15)
    assert r.status_code == 422


# Gate independence (emergency stop released temporarily)
def test_independence_live_stop(admin):
    admin.post(f"{API}/emergency-stop", json={"active": False, "confirmation": "RELEASE EMERGENCY STOP"}, timeout=15)
    admin.post(f"{API}/live-calling-stop", json={"active": True}, timeout=15)
    st = _status(admin)
    assert st["emergency_stop"]["active"] is False
    assert "live_calling_stop" in _keys(st["effective"]["live_blockers"])
    assert "live_calling_stop" not in _keys(st["effective"]["test_blockers"])
    assert "emergency_stop" not in _keys(st["effective"]["test_blockers"])


def test_independence_test_permit_symmetric(admin):
    """test_calling_permitted OFF should appear in test_blockers and never in live_blockers."""
    admin.post(f"{API}/emergency-stop", json={"active": False, "confirmation": "RELEASE EMERGENCY STOP"}, timeout=15)
    admin.post(f"{API}/test-calling-permitted", json={"permitted": False}, timeout=15)
    st = _status(admin)
    tk, lk = _keys(st["effective"]["test_blockers"]), _keys(st["effective"]["live_blockers"])
    assert not any(k.startswith("test_calling") for k in lk)
    assert any(k.startswith("test_calling") for k in tk), f"test_blockers missing test_calling_permitted: {tk}"


def test_emergency_stop_overrides_both(admin):
    admin.post(f"{API}/live-calling-stop", json={"active": False, "confirmation": "RELEASE LIVE CALLING STOP"}, timeout=15)
    admin.post(f"{API}/test-calling-permitted", json={"permitted": True, "confirmation": "PERMIT TEST CALLING"}, timeout=15)
    r = admin.post(f"{API}/emergency-stop", json={"active": True, "reason": "TEST_es"}, timeout=15)
    assert r.status_code == 200
    st = _status(admin)
    assert st["emergency_stop"]["active"] is True
    assert st["effective"]["can_place_test_call"] is False
    assert st["effective"]["can_place_live_call"] is False
    assert "emergency_stop" in _keys(st["effective"]["test_blockers"])
    assert "emergency_stop" in _keys(st["effective"]["live_blockers"])
    # restore switches immediately
    admin.post(f"{API}/live-calling-stop", json={"active": True}, timeout=15)
    admin.post(f"{API}/test-calling-permitted", json={"permitted": False}, timeout=15)
