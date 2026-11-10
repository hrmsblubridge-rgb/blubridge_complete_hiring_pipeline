"""Phase 4B live-API safety regression. NEVER sends a matching confirm_name — no real call is ever placed."""
import os
import uuid

import pytest
import requests
from bson import ObjectId

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")
API = f"{BASE_URL}/api/ai-calling"
CSRF = {"X-CSRF-Intent": "ai-calling"}


@pytest.fixture(scope="module")
def s():
    sess = requests.Session()
    for pw in ("QAZwsx##123", "Admin User"):
        r = sess.post(f"{BASE_URL}/api/login", json={"username": "Admin User", "password": pw})
        if r.status_code == 200:
            return sess
    pytest.skip("login failed")


@pytest.fixture(scope="module")
def candidates(s):
    r = s.get(f"{API}/test-candidates", params={"page_size": 100})
    assert r.status_code == 200
    d = r.json()
    return d.get("items", d) if isinstance(d, dict) else d


def _key():
    return uuid.uuid4().hex  # 32 chars, valid format


# Status endpoint
def test_status(s):
    r = s.get(f"{API}/test-calls/status")
    assert r.status_code == 200
    d = r.json()
    assert d["single_call_enabled"] is True
    assert d["mode"] == "testing"
    assert d["emergency_stop"] is True
    assert d["live_mode_locked"] is True
    assert d["batch_calling_enabled"] is False
    assert d["blocking_call"] is None
    assert d["dispatch_in_progress"] is False
    assert d["poll_seconds"] == 150


# Call history list + recording proxy
def test_calls_list_empty(s):
    r = s.get(f"{API}/calls", params={"mode": "testing"})
    assert r.status_code == 200
    d = r.json()
    assert "items" in d and d["items"] == []


def test_recording_random_404(s):
    r = s.get(f"{API}/calls/{ObjectId()}/recording")
    assert r.status_code == 404


def test_recording_bad_id_404(s):
    r = s.get(f"{API}/calls/not-an-id/recording")
    assert r.status_code == 404


@pytest.mark.parametrize("path", ["/test-calls/status", "/calls?mode=testing", f"/calls/{ObjectId()}/recording"])
def test_unauthenticated_401(path):
    r = requests.get(f"{API}{path}")
    assert r.status_code == 401


def test_call_now_unauth_401():
    r = requests.post(f"{API}/test-candidates/{ObjectId()}/call-now", headers=CSRF,
                      json={"idempotency_key": _key(), "confirm_name": "wrong name"})
    assert r.status_code == 401


# Call-now refusal paths (never a matching name)
def test_call_now_wrong_name_400(s, candidates):
    approved = [c for c in candidates if c.get("approved")]
    if not approved:
        pytest.skip("no approved candidate")
    c = approved[0]
    r = s.post(f"{API}/test-candidates/{c['id']}/call-now", headers=CSRF,
               json={"idempotency_key": _key(), "confirm_name": "wrong name"})
    assert r.status_code == 400
    assert "exact name" in r.json().get("detail", "")


def test_call_now_missing_csrf_403(s, candidates):
    c = candidates[0]
    r = s.post(f"{API}/test-candidates/{c['id']}/call-now",
               json={"idempotency_key": _key(), "confirm_name": "wrong name"})
    assert r.status_code == 403


@pytest.mark.parametrize("key", ["", "short", "x" * 65, "bad key with spaces!!", None])
def test_call_now_bad_idempotency_400(s, candidates, key):
    c = candidates[0]
    r = s.post(f"{API}/test-candidates/{c['id']}/call-now", headers=CSRF,
               json={"idempotency_key": key, "confirm_name": "wrong name"})
    assert r.status_code == 400


def test_call_now_unknown_candidate_404(s):
    r = s.post(f"{API}/test-candidates/{ObjectId()}/call-now", headers=CSRF,
               json={"idempotency_key": _key(), "confirm_name": "wrong name"})
    assert r.status_code == 404


# Locked controls
def test_initiate_423(s):
    r = s.post(f"{API}/calls/initiate", headers=CSRF, json={})
    assert r.status_code == 423


def test_mode_live_403(s):
    r = s.post(f"{API}/mode", headers=CSRF, json={"mode": "live"})
    assert r.status_code == 403


def test_batch_start_423(s):
    r = s.get(f"{API}/test-batches")
    assert r.status_code == 200
    d = r.json()
    items = d.get("items", d) if isinstance(d, dict) else d
    if not items:
        r = s.post(f"{API}/test-batches/{ObjectId()}/start", headers=CSRF)
        assert r.status_code == 404
        pytest.skip("no existing batch; random id -> 404")
    r = s.post(f"{API}/test-batches/{items[0]['id']}/start", headers=CSRF)
    assert r.status_code == 423


# Resolve-review / check on unknown call
def test_resolve_review_unknown_404(s):
    r = s.post(f"{API}/test-calls/{ObjectId()}/resolve-review", headers=CSRF, json={"confirmation": "REVIEWED"})
    assert r.status_code == 404


def test_resolve_review_wrong_confirmation_400(s):
    r = s.post(f"{API}/test-calls/{ObjectId()}/resolve-review", headers=CSRF, json={"confirmation": "nope"})
    assert r.status_code == 400


def test_check_unknown_404(s):
    r = s.post(f"{API}/test-calls/{ObjectId()}/check", headers=CSRF)
    assert r.status_code == 404


# Final: safety state unchanged after all refusals
def test_status_still_safe_after(s):
    d = s.get(f"{API}/test-calls/status").json()
    assert d["emergency_stop"] is True and d["blocking_call"] is None and d["dispatch_in_progress"] is False
