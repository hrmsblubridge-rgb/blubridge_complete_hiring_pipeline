"""Phase 7B live API tests (public URL): public consent 404s, real-preview, live-authorize 423, live limits. NEVER places calls."""
import os
import secrets
import string

import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
if not BASE_URL:
    for line in open("/app/frontend/.env"):
        if line.startswith("REACT_APP_BACKEND_URL="):
            BASE_URL = line.split("=", 1)[1].strip().rstrip("/")
API = f"{BASE_URL}/api/ai-calling"
H = {"X-CSRF-Intent": "ai-calling"}


def _tok(n=24):
    return "".join(secrets.choice(string.ascii_letters + string.digits) for _ in range(n))


@pytest.fixture(scope="module")
def s():
    sess = requests.Session()
    for pw in ("QAZwsx##123", "Admin User"):
        r = sess.post(f"{BASE_URL}/api/login", json={"username": "Admin User", "password": pw})
        if r.status_code == 200:
            return sess
    pytest.skip("login failed")


# --- public consent endpoints (no auth, token-scoped)
def test_public_consent_get_unknown_404():
    r = requests.get(f"{API}/public/consent/{_tok()}")
    assert r.status_code == 404 and "Invalid" in r.json()["detail"]


def test_public_consent_post_unknown_404():
    r = requests.post(f"{API}/public/consent/{_tok()}", json={"granted": True, "text_version": "2026-06-v2", "source": "booking_form"})
    assert r.status_code == 404


def test_public_consent_withdraw_unknown_404():
    assert requests.post(f"{API}/public/consent/{_tok()}/withdraw").status_code == 404


def test_public_consent_short_token_404():
    assert requests.get(f"{API}/public/consent/abc").status_code == 404


# --- real bookings preview (read-only)
def test_real_preview_requires_auth():
    assert requests.get(f"{API}/dry-run/real-preview").status_code == 401


def test_real_preview_empty(s):
    r = s.get(f"{API}/dry-run/real-preview")
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["bookings"] == 0 and d["rows"] == [] and "DRY RUN" in d["warning"]
    assert d["counts"] == {"SCHEDULED": 0, "SKIPPED": 0, "NEEDS_REVIEW": 0}
    assert "read-only" in d["source"]


# --- live dispatch authorization (always locked)
def test_live_authorize_423_with_phrase(s):
    r = s.post(f"{API}/live-dispatch/authorize", json={"confirmation": "AUTHORIZE LIVE DISPATCH"}, headers=H)
    assert r.status_code == 423
    assert s.get(f"{API}/switches").json()["live_dispatch_authorized"] is False


def test_live_authorize_no_auth_401():
    assert requests.post(f"{API}/live-dispatch/authorize", json={"confirmation": "AUTHORIZE LIVE DISPATCH"}, headers=H).status_code == 401


# --- switches expose live limits + phrase
def test_switches_live_limits(s):
    d = s.get(f"{API}/switches").json()
    assert d["live_limits"] == {"daily": 20, "concurrent": 1}
    assert d["live_auth_phrase"] == "AUTHORIZE LIVE DISPATCH"
    assert d["ai_test_enabled"] is True and d["ai_live_enabled"] is False and d["emergency_stop"] is True


def test_consent_preview_v2(s):
    d = s.get(f"{API}/consent/preview").json()
    assert d["version"] == "2026-06-v2" and d["default_checked"] is False and "withdraw" in d["text"]


# --- settings validation for live limits
@pytest.mark.parametrize("body", [{"live_daily_call_limit": 999}, {"live_daily_call_limit": -1},
                                  {"live_max_concurrent_calls": 0}, {"live_max_concurrent_calls": 6}])
def test_settings_live_limits_invalid_400(s, body):
    assert s.put(f"{API}/settings", json=body, headers=H).status_code == 400


def test_settings_live_limits_valid_restore(s):
    r = s.put(f"{API}/settings", json={"live_daily_call_limit": 20, "live_max_concurrent_calls": 1}, headers=H)
    assert r.status_code == 200, r.text
    assert s.get(f"{API}/switches").json()["live_limits"] == {"daily": 20, "concurrent": 1}


# --- regression
def test_status_single_call_disabled(s):
    assert s.get(f"{API}/test-calls/status").json().get("single_call_enabled") is False
