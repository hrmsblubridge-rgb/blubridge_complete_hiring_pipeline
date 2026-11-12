# Phase 7C-A live API regression: consent tokens (public), readiness/authorize 423, switches/limits, admin consent, mock live-prep.
# SAFETY: never places calls, never toggles switches/emergency stop, never touches provider settings or bb_registrations.
import os

import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")
API = f"{BASE_URL}/api/ai-calling"
CSRF = {"X-CSRF-Intent": "ai-calling"}


@pytest.fixture(scope="module")
def admin():
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/login", json={"username": "Admin User", "password": "QAZwsx##123"})
    if r.status_code != 200:
        pytest.skip(f"login failed {r.status_code} {r.text[:200]}")
    tok = (r.json() or {}).get("token") or (r.json() or {}).get("access_token")
    if tok:
        s.headers["Authorization"] = f"Bearer {tok}"
    return s


# ---- public consent ----
class TestPublic:
    def test_consent_text(self):
        r = requests.get(f"{API}/public/consent-text")
        assert r.status_code == 200
        d = r.json()
        assert d["title"] == "Optional AI Voice Call Consent"
        assert d["version"] == "2026-06-v4"
        assert d["default_checked"] is False and d["optional"] is True
        assert "no-store" in r.headers.get("Cache-Control", "")
        assert r.headers.get("Referrer-Policy") == "no-referrer"

    def test_manage_bogus_token(self):
        r = requests.get(f"{API}/public/consent/manage", headers={"X-Consent-Token": "x" * 43})
        assert r.status_code in (404, 429)
        assert "no-store" in r.headers.get("Cache-Control", "") or r.status_code == 429

    def test_booking_consent_bogus(self):
        r = requests.post(f"{API}/public/booking-consent/bogus_token_abcdefghijkl", json={"granted": True, "text_version": "2026-06-v4"})
        assert r.status_code in (404, 429)

    def test_renew_request_501(self):
        r = requests.post(f"{API}/public/consent/renew/request", json={})
        assert r.status_code == 501

    def test_old_route_gone(self):
        r = requests.get(f"{API}/public/consent/some_old_schedule_token_123456")
        assert r.status_code in (404, 405)


# ---- admin readiness / switches / settings ----
class TestAdmin:
    def test_readiness(self, admin):
        r = admin.get(f"{API}/live-dispatch/readiness")
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["ready"] is False
        checks = {c["key"]: c["ok"] for c in d["checks"]}
        print("READINESS", checks)
        assert checks["dispatch_implemented"] is False
        assert checks["deployment_approved"] is False
        assert checks["provider_verified"] is True
        assert checks["limits_set"] is True

    def test_authorize_423(self, admin):
        r = admin.post(f"{API}/live-dispatch/authorize", json={"confirmation": "AUTHORIZE LIVE DISPATCH"}, headers=CSRF)
        assert r.status_code == 423, r.text
        s = admin.get(f"{API}/switches").json()
        assert s["live_dispatch_authorized"] is False

    def test_switches(self, admin):
        d = admin.get(f"{API}/switches").json()
        assert d["ai_test_enabled"] is True
        assert d["ai_live_enabled"] is False
        assert d["emergency_stop"] is True
        assert d["live_limits"]["effective_daily"] == 5
        assert d["live_limits"]["pilot_daily_cap"] == 5

    @pytest.mark.parametrize("field,val", [("live_daily_call_limit", 100001), ("live_pilot_daily_cap", 100001),
                                           ("live_max_concurrent_calls", 51)])
    def test_settings_limits_rejected(self, admin, field, val):
        r = admin.put(f"{API}/settings", json={field: val}, headers=CSRF)
        assert r.status_code == 400, r.text

    def test_consent_admin_404(self, admin):
        assert admin.get(f"{API}/consent/admin/not-an-id").status_code == 404
        assert admin.get(f"{API}/consent/admin/0123456789abcdef01234567").status_code == 404

    def test_consent_admin_unauth(self):
        assert requests.get(f"{API}/consent/admin/0123456789abcdef01234567").status_code == 401

    def test_dnc_unauth(self):
        r = requests.post(f"{API}/consent/admin/0123456789abcdef01234567/dnc", json={"action": "mark", "confirm": True}, headers=CSRF)
        assert r.status_code == 401


# ---- mock live-prep ----
class TestLivePrep:
    def _calls(self, admin):
        r = admin.get(f"{API}/calls")
        if r.status_code != 200:
            return None
        d = r.json()
        return d.get("total", len(d.get("calls", d if isinstance(d, list) else [])))

    def test_plan_tick_clear(self, admin):
        before = self._calls(admin)
        r1 = admin.post(f"{API}/live-prep/plan", json={"source": "fixtures"}, headers=CSRF)
        assert r1.status_code == 200, r1.text
        c1 = r1.json()["counts"]
        print("PLAN1", c1)
        r2 = admin.post(f"{API}/live-prep/plan", json={"source": "fixtures"}, headers=CSRF)
        c2 = r2.json()["counts"]
        print("PLAN2", c2)
        assert c2["planned"] == 0 and c2["needs_review"] == 0
        assert c2["unchanged"] == c1["planned"] + c1["needs_review"] + c1["unchanged"]
        ov = admin.get(f"{API}/live-prep/overview").json()
        assert "readiness" in ov and "monitoring" in ov
        assert all(j["dispatchable"] is False and j["mode"] == "live_mock" for j in ov["jobs"])
        print("JOBS", len(ov["jobs"]), {j["status"] for j in ov["jobs"]})
        t = admin.post(f"{API}/live-prep/mock-tick", json={"outcome": "no_answer"}, headers=CSRF)
        assert t.status_code == 200, t.text
        print("TICK", {k: v for k, v in t.json().items() if k != "gate"})
        assert t.json().get("provider_request_sent", False) is False
        bad = admin.post(f"{API}/live-prep/mock-tick", json={"outcome": "bogus"}, headers=CSRF)
        assert bad.status_code == 400
        cl = admin.post(f"{API}/live-prep/mock-jobs/clear", headers=CSRF)
        assert cl.status_code == 200
        assert admin.get(f"{API}/live-prep/overview").json()["jobs"] == []
        assert self._calls(admin) == before

    def test_csrf_required(self, admin):
        r = admin.post(f"{API}/live-prep/plan", json={"source": "fixtures"})
        assert r.status_code in (400, 403)
