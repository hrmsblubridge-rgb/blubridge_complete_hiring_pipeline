# Live API regression: two-purpose AI calling (scheduling settings, single-call status, call-now gates, alerts, mock jobs)
import os
import uuid
import pytest
import requests
from pymongo import MongoClient
from dotenv import load_dotenv

load_dotenv("/app/backend/.env")
BASE_URL = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")
API = f"{BASE_URL}/api/ai-calling"
CSRF = {"X-CSRF-Intent": "ai-calling"}
DEFAULTS = {"confirm_offset_days": 1, "missed_offset_minutes": 60, "live_daily_call_limit": 20,
            "live_pilot_daily_cap": 5, "live_max_concurrent_calls": 1, "live_queue_capacity": 50}


@pytest.fixture(scope="module")
def s():
    sess = requests.Session()
    r = sess.post(f"{BASE_URL}/api/login", json={"username": "Admin User", "password": "QAZwsx##123"})
    if r.status_code != 200:
        pytest.skip("login failed")
    yield sess
    sess.put(f"{API}/scheduling", json=DEFAULTS, headers=CSRF)


@pytest.fixture(scope="module")
def mdb():
    c = MongoClient(os.environ["MONGO_URL"])
    return c[os.environ["DB_NAME"]]


# Scheduling settings
class TestScheduling:
    def test_get(self, s):
        r = s.get(f"{API}/scheduling")
        assert r.status_code == 200
        d = r.json()
        assert d["interview_confirmation"]["offset_range"] == [1, 7]
        assert d["interview_confirmation"]["window"] == ["10:00", "19:00"]
        assert d["missed_interview_followup"]["offset_range_minutes"] == [60, 10080]
        assert d["missed_interview_followup"]["window"] == ["10:00", "19:30"]
        assert d["missed_interview_followup"]["retry_minutes"] == 30
        assert d["interview_confirmation"]["retry_minutes"] == 60
        assert set(d["capacity"]) == {"live_daily_call_limit", "live_pilot_daily_cap", "live_max_concurrent_calls", "live_queue_capacity"}

    @pytest.mark.parametrize("body", [{"confirm_offset_days": 8}, {"confirm_offset_days": 0}, {"missed_offset_minutes": 59},
                                      {"missed_offset_minutes": 10081}, {"live_max_concurrent_calls": 0},
                                      {"live_max_concurrent_calls": 51}, {"live_queue_capacity": 1001}, {"bogus_key": 1},
                                      {"confirm_offset_days": "2"}, {"confirm_enabled": 1}, {}])
    def test_put_rejects(self, s, body):
        r = s.put(f"{API}/scheduling", json=body, headers=CSRF)
        assert r.status_code == 400, (body, r.text)

    def test_put_requires_csrf(self, s):
        r = s.put(f"{API}/scheduling", json={"confirm_offset_days": 2})
        assert r.status_code in (400, 403)

    def test_put_valid_audited_and_restore(self, s, mdb):
        before = mdb.ai_call_audit.count_documents({"action": "scheduling_updated"})
        r = s.put(f"{API}/scheduling", json={"confirm_offset_days": 2}, headers=CSRF)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["interview_confirmation"]["offset_days"] == 2
        assert "recalculated" in d
        assert s.get(f"{API}/scheduling").json()["interview_confirmation"]["offset_days"] == 2
        assert mdb.ai_call_audit.count_documents({"action": "scheduling_updated"}) == before + 1
        last = mdb.ai_call_audit.find_one({"action": "scheduling_updated"}, sort=[("_id", -1)])
        assert last["detail"]["confirm_offset_days"]["to"] == 2
        r = s.put(f"{API}/scheduling", json=DEFAULTS, headers=CSRF)
        assert r.status_code == 200
        cap = r.json()["capacity"]
        assert cap == {k: DEFAULTS[k] for k in cap}
        assert r.json()["interview_confirmation"]["offset_days"] == 1
        assert r.json()["missed_interview_followup"]["offset_minutes"] == 60


# Single-call status + call-now gates
class TestSingleCall:
    def test_status(self, s):
        d = s.get(f"{API}/test-calls/status").json()
        assert d["single_call_enabled"] is False
        assert d["min_recipients"] == 1
        assert "Emergency Stop is ON" in d["block_reasons"]
        assert any("AI_CALLING_ENABLED" in x for x in d["block_reasons"])
        assert d["emergency_stop"] is True

    def _syed(self, s):
        items = s.get(f"{API}/test-candidates").json()
        items = items.get("items", items.get("candidates", items)) if isinstance(items, dict) else items
        for c in items:
            if "syed" in str(c.get("candidate_name", "")).lower():
                return c
        pytest.skip("Syed not found")

    def test_call_now_wrong_name_then_correct(self, s, mdb):
        n0 = mdb.ai_calls.count_documents({})
        c = self._syed(s)
        cid = c.get("id") or c.get("_id")
        r = s.post(f"{API}/test-candidates/{cid}/call-now", headers=CSRF,
                   json={"idempotency_key": uuid.uuid4().hex, "confirm_name": "Wrong Name"})
        assert r.status_code == 400, r.text
        r = s.post(f"{API}/test-candidates/{cid}/call-now", headers=CSRF,
                   json={"idempotency_key": uuid.uuid4().hex, "confirm_name": c["candidate_name"]})
        assert r.status_code == 409, r.text
        assert mdb.ai_calls.count_documents({}) == n0 == 1


# Alerts, mock jobs, worker status, live dispatch lock
class TestAlertsAndMock:
    def test_alerts_list(self, s):
        r = s.get(f"{API}/alerts")
        assert r.status_code == 200 and isinstance(r.json()["alerts"], list)

    def test_resolve_bogus(self, s):
        assert s.post(f"{API}/alerts/bogus/resolve", json={}, headers=CSRF).status_code == 404
        assert s.post(f"{API}/alerts/0123456789abcdef01234567/resolve", json={}, headers=CSRF).status_code == 404

    def test_process_unknown_job(self, s):
        r = s.post(f"{API}/live-prep/mock-jobs/0123456789abcdef01234567/process", json={}, headers=CSRF)
        assert r.status_code == 409, r.text
        r = s.post(f"{API}/live-prep/mock-jobs/bogus/process", json={}, headers=CSRF)
        assert r.status_code == 409, r.text

    def test_mock_run(self, s):
        r = s.post(f"{API}/live-prep/mock-run", json={}, headers=CSRF)
        assert r.status_code == 200, r.text

    def test_worker_status(self, s):
        r = s.get(f"{API}/live-prep/worker-status")
        assert r.status_code == 200
        d = r.json()
        assert d["enabled"] is False and d["provider"]
        assert "pending_by_purpose" in d

    def test_authorize_locked(self, s):
        r = s.post(f"{API}/live-dispatch/authorize", json={}, headers=CSRF)
        assert r.status_code == 423
