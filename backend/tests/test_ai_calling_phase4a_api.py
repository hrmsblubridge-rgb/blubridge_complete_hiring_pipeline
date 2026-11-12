# Phase 4A — Bolna verification/dry-run API regression (NO real calls, NO credential overwrite).
# Uses ONLY dummy phones +9190000003xx; deletes only ids it created. Does NOT call test-connection
# with a valid CSRF header (to limit real Bolna API traffic) and never saves credentials successfully.
import os
from datetime import date, timedelta

import pytest
import requests

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL').rstrip('/')
API = f"{BASE_URL}/api/ai-calling"
CSRF = {"X-CSRF-Intent": "ai-calling"}
FUT = (date.today() + timedelta(days=20)).isoformat()
CREATED = []


@pytest.fixture(scope="module")
def s():
    sess = requests.Session()
    r = sess.post(f"{BASE_URL}/api/login", json={"username": "Admin User", "password": "QAZwsx##123"})
    if r.status_code != 200:
        pytest.skip("login failed")
    yield sess
    for cid in CREATED:
        sess.delete(f"{API}/test-candidates/{cid}")


def _mk(s, name, phone, time="15:30"):
    r = s.post(f"{API}/test-candidates", json=dict(
        candidate_name=name, phone_number=phone, job_role="QA Engineer", interview_date=FUT, interview_time=time,
        language="English", company_name="BluBridge", office_address="Chennai Office"))
    assert r.status_code == 200, r.text
    CREATED.append(r.json()["id"])
    return r.json()


# --- provider: masking & secrets ---
class TestProviderSecurity:
    def test_get_provider_no_secret(self, s):
        r = s.get(f"{API}/provider")
        assert r.status_code == 200
        assert "gAAAA" not in r.text and "api_key_encrypted" not in r.text and "webhook_token_hash" not in r.text
        d = r.json()
        assert d["has_api_key"] is True and d["api_key_masked"].startswith("••••••••")

    def test_test_connection_requires_csrf(self, s):
        assert s.post(f"{API}/provider/test-connection").status_code == 403

    def test_webhook_token_requires_csrf(self, s):
        assert s.post(f"{API}/provider/webhook-token").status_code == 403

    def test_test_connection_unauth(self):
        assert requests.post(f"{API}/provider/test-connection", headers=CSRF).status_code in (401, 403)

    def test_invalid_caller_does_not_change_config(self, s):
        before = s.get(f"{API}/provider").json()
        r = s.put(f"{API}/provider/settings", json={"caller_number": "12ab"}, headers=CSRF)
        assert r.status_code == 400
        after = s.get(f"{API}/provider").json()
        for k in ("config_version", "api_key_masked", "caller_number_masked", "agent_id", "status"):
            assert before[k] == after[k], k

    def test_last_verification_shape(self, s):
        lv = s.get(f"{API}/provider").json().get("last_verification")
        assert lv, "no verification stored"
        keys = {c["key"] for c in lv["checks"]}
        assert {"auth", "agent", "caller_number", "extraction", "outbound_authorization"} <= keys
        states = {c["state"] for c in lv["checks"]}
        assert states <= {"verified", "failed", "warning", "unverified", "cannot_verify"}
        assert next(c for c in lv["checks"] if c["key"] == "outbound_authorization")["state"] == "cannot_verify"


# --- dry run ---
class TestDryRun:
    def test_dry_run_requires_csrf(self, s):
        c = _mk(s, "TEST_dry_csrf", "+919000000301")
        assert s.post(f"{API}/test-candidates/{c['id']}/dry-run").status_code == 403

    def test_dry_run_404(self, s):
        assert s.post(f"{API}/test-candidates/notanid/dry-run", headers=CSRF).status_code == 404
        assert s.post(f"{API}/test-candidates/000000000000000000000000/dry-run", headers=CSRF).status_code == 404

    def test_dry_run_pending_blocked(self, s):
        c = _mk(s, "TEST_dry_pending", "+919000000302")
        r = s.post(f"{API}/test-candidates/{c['id']}/dry-run", headers=CSRF)
        assert r.status_code == 200
        d = r.json()
        assert d["prepared"] is False and d["would_send"] is False and "body" not in d
        assert next(x for x in d["checks"] if x["key"] == "consent")["ok"] is False

    def test_dry_run_approved_masked(self, s):
        c = _mk(s, "TEST_dry_ok", "+919000000303", time="14:00")
        a = s.post(f"{API}/test-candidates/{c['id']}/consent", json={"granted": True})
        assert a.status_code == 200
        r = s.post(f"{API}/test-candidates/{c['id']}/dry-run", headers=CSRF)
        assert r.status_code == 200
        d = r.json()
        assert d["would_send"] is False
        if not next(x for x in d["checks"] if x["key"] == "provider_validated")["ok"]:
            pytest.skip("provider not verified; cannot prepare")
        assert d["prepared"] is True and d["method"] == "POST" and d["url"] == "https://api.bolna.ai/call"
        assert d["headers"]["Authorization"] == "Bearer ••••••••"
        b = d["body"]
        assert b["recipient_phone_number"] == "+91*****0303"
        assert "*" in b["from_phone_number"]
        assert set(b["user_data"]) == {"candidate_name", "company_name", "job_role", "interview_date", "interview_time", "office_address", "call_purpose"}
        assert b["user_data"]["interview_time"] == "2 PM IST"
        assert "," in b["user_data"]["interview_date"]
        assert "9000000303" not in r.text and "gAAAA" not in r.text


# --- webhook & calling gates ---
class TestWebhookAndCalls:
    def test_webhook_wrong_token_404(self):
        r = requests.post(f"{API}/webhook/bolna/wrongtoken", json={"id": "x", "status": "completed"})
        assert r.status_code == 404

    def test_initiate_423(self, s):
        assert s.post(f"{API}/calls/initiate", json={}).status_code == 423

    def test_no_calls_and_stop_active(self, s):
        sm = s.get(f"{API}/summary").json()
        assert sm["emergency_stop"] is True and sm["live_mode_locked"] is True
        assert sm["bolna_integration_approved"] is False
