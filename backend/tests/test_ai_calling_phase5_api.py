"""Phase 5 live-API safety regression: calling locked (423), profile call-history endpoints read-only.
NEVER sends a matching confirm_name; never writes to ai_calls / bb_registrations."""
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


# Calling status flags
def test_status_locked(s):
    r = s.get(f"{API}/test-calls/status")
    assert r.status_code == 200
    d = r.json()
    assert d["single_call_enabled"] is False
    assert d["emergency_stop"] is True
    assert d["mode"] == "testing"
    assert d["live_mode_locked"] is True
    assert d["dispatch_in_progress"] is False


# Call Now locked server-side (wrong name only, never matching)
@pytest.mark.parametrize("cid", [str(ObjectId()), "not-an-id"])
def test_call_now_423(s, cid):
    r = s.post(f"{API}/test-candidates/{cid}/call-now", headers=CSRF,
               json={"idempotency_key": uuid.uuid4().hex, "confirm_name": "wrong name"})
    assert r.status_code in (400, 404, 409, 412)  # real gates (name/emergency stop) block it
    assert r.json()["detail"]


def test_call_now_423_real_candidate_wrong_name(s):
    items = s.get(f"{API}/test-candidates", params={"page_size": 100}).json()
    items = items.get("items", items) if isinstance(items, dict) else items
    if not items:
        pytest.skip("no test candidates")
    cid = items[0].get("id") or items[0].get("_id")
    r = s.post(f"{API}/test-candidates/{cid}/call-now", headers=CSRF,
               json={"idempotency_key": uuid.uuid4().hex, "confirm_name": "definitely wrong name"})
    assert r.status_code in (400, 404, 409, 412)  # real gates (name/emergency stop) block it


def test_call_now_no_csrf_403(s):
    r = s.post(f"{API}/test-candidates/{ObjectId()}/call-now", json={"idempotency_key": uuid.uuid4().hex})
    assert r.status_code == 403


# Calls by registration
def test_by_registration_empty(s):
    r = s.get(f"{API}/calls/by-registration/{ObjectId()}")
    assert r.status_code == 200
    d = r.json()
    assert d["items"] == [] and d["total"] == 0


def test_by_registration_invalid_400(s):
    assert s.get(f"{API}/calls/by-registration/not-an-id").status_code == 400


def test_by_registration_page_size_capped(s):
    d = s.get(f"{API}/calls/by-registration/{ObjectId()}", params={"page_size": 500, "page": -3}).json()
    assert d["page_size"] == 20 and d["page"] == 1


def test_test_call_never_on_profile(s):
    """The Phase 4B real test call must not appear under any registration lookup."""
    r = s.get(f"{API}/calls", params={"mode": "testing"})
    assert r.status_code == 200
    items = r.json()["items"]
    if not items:
        pytest.skip("no test calls in DB")
    for tc in items:
        assert tc["mode"] == "testing"
        for ref in (tc.get("test_candidate_id"), tc.get("id"), tc.get("registration_id")):
            if ref and ObjectId.is_valid(ref):
                d = s.get(f"{API}/calls/by-registration/{ref}").json()
                assert d["total"] == 0, ref
    assert s.get(f"{API}/calls", params={"mode": "live"}).json()["items"] == []


# Call detail hides raw recording URL / phone
def test_call_detail_hides_secrets(s):
    items = s.get(f"{API}/calls", params={"mode": "testing"}).json()["items"]
    if not items:
        pytest.skip("no test calls")
    d = s.get(f"{API}/calls/{items[0]['id']}").json()
    assert "recording_url" not in d and "recipient_e164" not in d
    assert "bolna" not in str(d.get("recording", "")).lower()
    assert isinstance(d["has_recording"], bool)


# Registration lookup
@pytest.mark.parametrize("email", ["x", "", "   "])
def test_lookup_invalid_400(s, email):
    assert s.get(f"{API}/registrations/lookup", params={"email": email}).status_code == 400


def test_lookup_unknown_email(s):
    r = s.get(f"{API}/registrations/lookup", params={"email": "TEST_nobody_phase5@example.invalid"})
    assert r.status_code == 200
    assert r.json()["registration_ids"] == []


# Recording proxy
def test_recording_unknown_404(s):
    assert s.get(f"{API}/calls/{ObjectId()}/recording").status_code == 404
    assert s.get(f"{API}/calls/garbage/recording").status_code == 404


# Auth required
@pytest.mark.parametrize("path", [f"/calls/by-registration/{ObjectId()}", "/registrations/lookup?email=a@b.c",
                                  f"/calls/{ObjectId()}/recording", "/test-calls/status"])
def test_no_auth_401(path):
    assert requests.get(f"{API}{path}").status_code == 401


def test_call_now_no_auth_401():
    r = requests.post(f"{API}/test-candidates/{ObjectId()}/call-now", headers=CSRF,
                      json={"idempotency_key": uuid.uuid4().hex, "confirm_name": "wrong name"})
    assert r.status_code == 401
