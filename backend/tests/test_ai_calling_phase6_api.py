"""Phase 6 DRY-RUN planner live-API tests. NEVER places calls: touches only ai_dry_run_* fixture collections.
Never sends a matching confirm_name to call-now; never changes settings/mode/emergency stop."""
import os
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

import pytest
import requests
from bson import ObjectId

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")
API = f"{BASE_URL}/api/ai-calling"
DR = f"{API}/dry-run"
CSRF = {"X-CSRF-Intent": "ai-calling"}
IST = timezone(timedelta(hours=5, minutes=30))
WARN = "DRY RUN — NO PHONE CALLS WILL BE PLACED."


def _login():
    sess = requests.Session()
    for pw in ("QAZwsx##123", "Admin User"):
        r = sess.post(f"{BASE_URL}/api/login", json={"username": "Admin User", "password": pw})
        if r.status_code == 200:
            return sess
    return None


@pytest.fixture(scope="module")
def s():
    sess = _login()
    if not sess:
        pytest.skip("login failed")
    return sess


@pytest.fixture(scope="module")
def planned(s):
    r = s.post(f"{DR}/fixtures/seed", headers=CSRF)
    assert r.status_code == 200, r.text
    assert r.json() == {"seeded": 15}
    r = s.post(f"{DR}/plan", headers=CSRF)
    assert r.status_code == 200, r.text
    return r.json()


def _current(s):
    jobs = s.get(f"{DR}/preview").json()["jobs"]
    return [j for j in jobs if j["status"] != "INVALIDATED"]


def _by_letter(jobs):
    return {j["candidate_name"].split("Synthetic ")[1][0]: j for j in jobs}


# Auth / CSRF guards
@pytest.mark.parametrize("method,path", [("post", "/fixtures/seed"), ("post", "/plan"), ("get", "/preview"),
                                         ("post", f"/fixtures/{ObjectId()}/reschedule")])
def test_401_without_auth(method, path):
    r = getattr(requests, method)(f"{DR}{path}", headers=CSRF)
    assert r.status_code == 401, r.text


@pytest.mark.parametrize("path", ["/fixtures/seed", "/plan", f"/fixtures/{ObjectId()}/reschedule"])
def test_403_without_csrf(s, path):
    r = s.post(f"{DR}{path}")
    assert r.status_code == 403, r.text


# Seed + plan + preview
def test_plan_counts_and_preview(s, planned):
    assert planned["bookings"] == 15
    c = planned["counts"]
    assert c["SCHEDULED"] + c["SKIPPED"] + c["NEEDS_REVIEW"] == 15
    assert planned["eligible"] == c["SCHEDULED"]
    assert planned["by"] == "Admin User"
    d = s.get(f"{DR}/preview").json()
    assert d["warning"] == WARN
    assert d["last_run"]["run_id"] == planned["run_id"]
    assert d["fixtures"] == 15
    assert d["jobs"] and all(j["mode"] == "DRY_RUN" and j["dry_run"] is True for j in d["jobs"])
    assert all("_id" not in j for j in d["jobs"])


def test_expected_reasons(s, planned):
    m = _by_letter(_current(s))
    assert len(m) == 15
    exp = {"F": "NO_CALLING_CONSENT", "G": "CONSENT_WITHDRAWN", "H": "DO_NOT_CALL", "I": "INVALID_PHONE",
           "J": "SUPERSEDED", "L": "ALREADY_CONFIRMED", "M": "CANCELLED"}
    for k, reason in exp.items():
        assert m[k]["status"] == "SKIPPED" and reason in m[k]["reasons"], (k, m[k])
    assert m["K"]["status"] == "SKIPPED" and "ATTENDED" in m["K"]["reasons"] and "INTERVIEW_PASSED" in m["K"]["reasons"]
    assert m["N"]["status"] == "SKIPPED" and "NOT_BOOKED" in m["N"]["reasons"] and "NO_SCHEDULE" in m["N"]["reasons"]
    assert m["O"]["status"] == "NEEDS_REVIEW" and m["O"]["reasons"] == ["INSUFFICIENT_LEAD_TIME"]
    for k in "ABCE":
        assert m[k]["status"] == "SCHEDULED", (k, m[k])
    now = datetime.now(IST)
    in_window = 10 <= now.hour < 19
    # D: 5 h ahead; SCHEDULED if planning can happen within the window with >=2 h lead
    assert m["D"]["status"] in ("SCHEDULED", "NEEDS_REVIEW")
    if in_window and now.hour < 17:
        assert m["D"]["status"] == "SCHEDULED", m["D"]
    for j in m.values():
        if j["status"] == "SKIPPED":
            assert j["planned_at"] is None, j


def test_timing_rules(s, planned):
    m = _by_letter(_current(s))
    b_iv = datetime.fromisoformat(m["B"]["interview_at"])
    assert datetime.fromisoformat(m["B"]["planned_at"]) == datetime.combine((b_iv - timedelta(days=1)).date(),
                                                                             datetime.min.time().replace(hour=10), IST)
    c_iv = datetime.fromisoformat(m["C"]["interview_at"])
    assert datetime.fromisoformat(m["C"]["planned_at"]) == datetime.combine(c_iv.date(),
                                                                             datetime.min.time().replace(hour=10), IST)
    a_iv = datetime.fromisoformat(m["A"]["interview_at"])
    assert datetime.fromisoformat(m["A"]["planned_at"]) == a_iv - timedelta(hours=24)
    now = datetime.now(IST) - timedelta(minutes=2)
    for j in m.values():
        if j["planned_at"]:
            p = datetime.fromisoformat(j["planned_at"]).astimezone(IST)
            assert p >= now, j
            assert (10, 0) <= (p.hour, p.minute) and (p.hour, p.minute) < (19, 0), j


def test_idempotent_plan(s, planned):
    before = s.get(f"{DR}/preview").json()["jobs"]
    tp = {j["id"]: j["times_planned"] for j in before}
    r = s.post(f"{DR}/plan", headers=CSRF)
    assert r.status_code == 200
    after = s.get(f"{DR}/preview").json()["jobs"]
    assert len(after) == len(before)
    cur = [j for j in after if j["status"] != "INVALIDATED"]
    assert all(j["times_planned"] == tp[j["id"]] + 1 for j in cur)


def test_reschedule_invalidates(s, planned):
    m = _by_letter(_current(s))
    a = m["A"]
    r = s.post(f"{DR}/fixtures/{a['booking_id']}/reschedule", headers=CSRF)
    assert r.status_code == 200, r.text
    r = s.post(f"{DR}/plan", headers=CSRF)
    assert r.status_code == 200 and r.json()["counts"]["INVALIDATED"] >= 1
    jobs = [j for j in s.get(f"{DR}/preview").json()["jobs"] if j["booking_id"] == a["booking_id"]]
    old = [j for j in jobs if j["id"] == a["id"]][0]
    assert old["status"] == "INVALIDATED" and old["reasons"] == ["RESCHEDULED"]
    new = [j for j in jobs if j["status"] == "SCHEDULED"]
    assert len(new) == 1 and new[0]["id"] != a["id"] and new[0]["reschedule_count"] == 1


def test_reschedule_404(s):
    assert s.post(f"{DR}/fixtures/{ObjectId()}/reschedule", headers=CSRF).status_code == 404
    assert s.post(f"{DR}/fixtures/not-an-id/reschedule", headers=CSRF).status_code == 404


def test_concurrent_plan_no_duplicates(s, planned):
    n_before = len(s.get(f"{DR}/preview").json()["jobs"])
    with ThreadPoolExecutor(3) as ex:
        codes = list(ex.map(lambda _: s.post(f"{DR}/plan", headers=CSRF).status_code, range(3)))
    assert all(c in (200, 409) for c in codes) and 200 in codes, codes
    d = s.get(f"{DR}/preview").json()
    assert len(d["jobs"]) == n_before
    keys = [(j["booking_id"], j.get("booking_key")) for j in d["jobs"]]
    assert len(set(keys)) == len(keys)
    assert d["planning_in_progress"] is False


# Regression: calling stays locked
def test_calling_still_locked(s):
    d = s.get(f"{API}/test-calls/status").json()
    assert d["single_call_enabled"] is False and d["emergency_stop"] is True and d["mode"] == "testing"


def test_call_now_423_wrong_name(s):
    r = s.post(f"{API}/test-candidates/{ObjectId()}/call-now", headers=CSRF,
               json={"idempotency_key": uuid.uuid4().hex, "confirm_name": "definitely wrong name"})
    assert r.status_code == 423
