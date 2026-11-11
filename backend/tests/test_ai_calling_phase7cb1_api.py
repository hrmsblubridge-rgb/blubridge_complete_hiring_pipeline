# Phase 7C-B1 live API: booking-link consent renewal (generic errors), retention preview (read-only), worker-status.
# SAFETY: never places calls, never toggles switches, never writes bb_registrations, never deletes ai_calls.
import os

import pytest
import requests
from pymongo import MongoClient

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")
API = f"{BASE_URL}/api/ai-calling"
CSRF = {"X-CSRF-Intent": "ai-calling"}
GENERIC = "We could not verify these details"


def _env(key):
    for line in open("/app/backend/.env"):
        if line.startswith(key + "="):
            return line.split("=", 1)[1].strip().strip('"')


@pytest.fixture(scope="module")
def admin():
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/login", json={"username": "Admin User", "password": "QAZwsx##123"})
    if r.status_code != 200:
        pytest.skip(f"login failed {r.status_code}")
    tok = (r.json() or {}).get("token") or (r.json() or {}).get("access_token")
    if tok:
        s.headers["Authorization"] = f"Bearer {tok}"
    return s


@pytest.fixture(scope="module")
def mdb():
    return MongoClient(_env("MONGO_URL"))[_env("DB_NAME")]


# ---- public renewal (max 4 invalid attempts to stay below IP limit) ----
class TestRenewPublic:
    def test_unknown_vs_malformed_same_generic(self):
        unknown = requests.post(f"{API}/public/consent/renew/booking", json={"schedule_token": "z" * 32, "phone_last4": "1234"})
        malformed = requests.post(f"{API}/public/consent/renew/booking", json={"schedule_token": "z" * 32, "phone_last4": "12a4"})
        short = requests.post(f"{API}/public/consent/renew/booking", json={"schedule_token": "z" * 32, "phone_last4": "123"})
        for r in (unknown, malformed, short):
            assert r.status_code in (400, 429), r.text
        if unknown.status_code == 400:
            assert GENERIC in unknown.json()["detail"]
            assert unknown.json()["detail"] == malformed.json()["detail"] == short.json()["detail"]
        assert "no-store" in unknown.headers.get("Cache-Control", "")

    def test_empty_body(self):
        r = requests.post(f"{API}/public/consent/renew/booking", json={})
        assert r.status_code in (400, 429)


# ---- retention ----
class TestRetention:
    def test_policy(self, admin):
        r = admin.get(f"{API}/retention/policy")
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["policy"]["days"] == 90 and d["policy"]["status"] == "proposed" and d["policy"]["deletion_enabled"] is False
        assert "Full transcript" in d["sensitive_fields"] and len(d["sensitive_fields"]) >= 6
        assert d["retained_fields"] and d["can_manage"] is True and d["deletion_approved"] is False
        bolna = [s for s in d["storage_map"] if s["where"].startswith("Bolna")][0]
        assert "No documented per-execution DELETE" in bolna["note"]

    def test_preview_readonly(self, admin, mdb):
        snap = list(mdb.ai_calls.find({}))
        p = admin.get(f"{API}/retention/preview")
        assert p.status_code == 200, p.text
        d = p.json()
        assert d["dry_run"] is True and d["deleted"] == 0 and d["days"] == 90
        assert d["counts"]["records"] == len(snap) == len(d["rows"])
        print("PREVIEW", d["counts"], [(r["status"], r["age_days"], r["fields"]) for r in d["rows"]])
        p1 = admin.get(f"{API}/retention/preview", params={"days": 1}).json()
        assert p1["days"] == 1
        print("PREVIEW1", p1["counts"], [r["status"] for r in p1["rows"]])
        if p1["rows"] and d["rows"]:
            assert p1["rows"][0]["eligible_from"] != d["rows"][0]["eligible_from"]
        assert list(mdb.ai_calls.find({})) == snap

    def test_preview_bad_days(self, admin):
        assert admin.get(f"{API}/retention/preview", params={"days": 0}).status_code in (400, 422)

    def test_execute_423(self, admin, mdb):
        n = mdb.ai_calls.count_documents({})
        r = admin.post(f"{API}/retention/execute", headers=CSRF)
        assert r.status_code == 423
        assert mdb.ai_calls.count_documents({}) == n

    def test_policy_invalid_days(self, admin):
        assert admin.post(f"{API}/retention/policy", json={"days": 10}, headers=CSRF).status_code == 400

    def test_hold_and_release(self, admin, mdb):
        call = mdb.ai_calls.find_one({})
        if not call:
            pytest.skip("no calls")
        cid = str(call["_id"])
        assert admin.post(f"{API}/retention/holds", json={"call_id": cid}, headers=CSRF).status_code == 400
        r = admin.post(f"{API}/retention/holds", json={"call_id": cid, "reason": "TEST_hold"}, headers=CSRF)
        assert r.status_code == 200, r.text
        try:
            rows = admin.get(f"{API}/retention/preview").json()["rows"]
            assert [x for x in rows if x["call_id"] == cid][0]["status"] == "on_hold"
        finally:
            rel = admin.post(f"{API}/retention/holds/{cid}/release", headers=CSRF)
        assert rel.status_code == 200
        rows = admin.get(f"{API}/retention/preview").json()["rows"]
        assert [x for x in rows if x["call_id"] == cid][0]["status"] != "on_hold"

    def test_csrf_and_unauth(self, admin):
        assert admin.post(f"{API}/retention/execute").status_code in (400, 403)
        assert requests.get(f"{API}/retention/policy").status_code == 401
        assert requests.get(f"{API}/retention/preview").status_code == 401


# ---- worker status + regression ----
class TestWorker:
    def test_worker_status(self, admin):
        r = admin.get(f"{API}/live-prep/worker-status")
        assert r.status_code == 200, r.text
        d = r.json()
        print("WORKER", {k: v for k, v in d.items() if k not in ("readiness", "monitoring")})
        assert d["running"] is False and d["enabled"] is False and d["provider"] == "mock"
        assert d["banner"] == "LIVE CALLING DISABLED — PREPARATION ONLY"
        assert "exclusions" in d and "monitoring" in d and d["readiness"]["ready"] is False

    def test_worker_status_unauth(self):
        assert requests.get(f"{API}/live-prep/worker-status").status_code == 401

    def test_switches_unchanged(self, admin):
        d = admin.get(f"{API}/switches").json()
        assert d["ai_test_enabled"] is True and d["ai_live_enabled"] is False and d["emergency_stop"] is True
