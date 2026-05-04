"""
Iteration 29 Backend Tests:
- /api/bb/interview-reports — pagination + filters + sort + summary
- /api/bb/attended-for-scores — pagination + filters
- /api/bb/applicant-score/{email} — PUT still works after pagination refactor
"""
import math
import os
import time
import pytest
import requests

def _load_backend_url():
    url = os.environ.get("REACT_APP_BACKEND_URL")
    if not url:
        env = "/app/frontend/.env"
        if os.path.exists(env):
            with open(env) as f:
                for line in f:
                    if line.startswith("REACT_APP_BACKEND_URL="):
                        url = line.split("=", 1)[1].strip()
                        break
    return url.rstrip("/")

BASE_URL = _load_backend_url()
USERNAME = "Admin User"
PASSWORD = "Admin User"


@pytest.fixture(scope="session")
def session():
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/login",
               json={"username": USERNAME, "password": PASSWORD}, timeout=30)
    if r.status_code != 200:
        pytest.skip(f"Login failed: {r.status_code} {r.text[:200]}")
    return s


# ============ /api/bb/interview-reports ============

class TestInterviewReports:
    def test_basic_pagination(self, session):
        t0 = time.time()
        r = session.get(f"{BASE_URL}/api/bb/interview-reports",
                        params={"page": 1, "limit": 10}, timeout=30)
        elapsed = time.time() - t0
        assert r.status_code == 200, f"Status {r.status_code}: {r.text[:300]}"
        assert elapsed < 10, f"Took {elapsed:.2f}s, expected < 10s"
        body = r.json()
        for k in ("data", "total", "page", "limit", "totalPages", "summary"):
            assert k in body, f"Missing key {k}"
        for k in ("role_counts", "attended", "not_attended", "premium_colleges", "non_premium_colleges"):
            assert k in body["summary"], f"Missing summary key {k}"
        assert body["page"] == 1
        assert body["limit"] == 10
        assert len(body["data"]) == 10
        assert body["total"] >= 4000, f"total={body['total']} (expected ~4919)"
        assert body["totalPages"] == math.ceil(body["total"] / 10)
        row0 = body["data"][0]
        for k in ("name", "email", "date", "time", "job_role", "college_type", "attendance"):
            assert k in row0, f"row missing key {k}"
        # store for other tests
        pytest.IR_TOTAL = body["total"]
        pytest.IR_ROLES = list(body["summary"]["role_counts"].keys())

    def test_filter_premium_attended(self, session):
        r = session.get(f"{BASE_URL}/api/bb/interview-reports",
                        params={"collegeType": "Premium", "attendance": "Attended",
                                "page": 1, "limit": 5}, timeout=30)
        assert r.status_code == 200
        body = r.json()
        for row in body["data"]:
            assert row["attendance"] == "Attended", f"leak: {row}"
            assert "Premium" in row["college_type"] and "Non" not in row["college_type"], f"leak: {row}"

    def test_filter_non_premium(self, session):
        r = session.get(f"{BASE_URL}/api/bb/interview-reports",
                        params={"collegeType": "Non Premium", "page": 1, "limit": 5}, timeout=30)
        assert r.status_code == 200
        for row in r.json()["data"]:
            assert "Non Premium" in row["college_type"], f"leak: {row}"

    def test_filter_not_attended(self, session):
        r = session.get(f"{BASE_URL}/api/bb/interview-reports",
                        params={"attendance": "Not Attended", "page": 1, "limit": 5}, timeout=30)
        assert r.status_code == 200
        for row in r.json()["data"]:
            assert row["attendance"] == "Not Attended", f"leak: {row}"

    def test_filter_job_role(self, session):
        roles = getattr(pytest, "IR_ROLES", [])
        if not roles:
            pytest.skip("No roles available from previous test")
        role = roles[0]
        r = session.get(f"{BASE_URL}/api/bb/interview-reports",
                        params={"jobRole": role, "page": 1, "limit": 5}, timeout=30)
        assert r.status_code == 200
        body = r.json()
        assert len(body["data"]) > 0, f"No rows for role {role}"
        for row in body["data"]:
            assert row["job_role"].lower() == role.lower(), f"leak: {row} expected {role}"

    def test_filter_date_range(self, session):
        r = session.get(f"{BASE_URL}/api/bb/interview-reports",
                        params={"startDate": "2026-01-01", "endDate": "2026-12-31",
                                "page": 1, "limit": 5}, timeout=30)
        assert r.status_code == 200

    def test_distinct_pages(self, session):
        r1 = session.get(f"{BASE_URL}/api/bb/interview-reports",
                         params={"page": 1, "limit": 10}, timeout=30).json()
        r2 = session.get(f"{BASE_URL}/api/bb/interview-reports",
                         params={"page": 2, "limit": 10}, timeout=30).json()
        emails1 = [r["email"] for r in r1["data"]]
        emails2 = [r["email"] for r in r2["data"]]
        # rows should differ as a set (any overlap not all matched)
        overlap = set(emails1) & set(emails2)
        assert len(overlap) < len(emails1), f"page1==page2 emails: {emails1}"
        assert r1["total"] == r2["total"]
        assert r1["totalPages"] == r2["totalPages"]

    def test_sort_desc_by_date(self, session):
        r = session.get(f"{BASE_URL}/api/bb/interview-reports",
                        params={"page": 1, "limit": 10}, timeout=30).json()
        dates = [row["date"] for row in r["data"][:3] if row["date"] != "-"]
        # ISO-style date strings sort lexically same as chronologically
        assert dates == sorted(dates, reverse=True), f"Not DESC sorted: {dates}"


# ============ /api/bb/attended-for-scores ============

class TestAttendedForScores:
    def test_basic_pagination(self, session):
        r = session.get(f"{BASE_URL}/api/bb/attended-for-scores",
                        params={"page": 1, "limit": 10}, timeout=30)
        assert r.status_code == 200, f"{r.status_code}: {r.text[:300]}"
        body = r.json()
        for k in ("data", "total", "page", "limit", "totalPages", "available_rounds"):
            assert k in body, f"missing {k}"
        assert body["page"] == 1
        assert body["limit"] == 10
        assert body["total"] >= 500, f"total={body['total']} (expected ~1024)"
        assert body["totalPages"] == math.ceil(body["total"] / 10)
        if body["data"]:
            row = body["data"][0]
            for k in ("name", "email", "phone", "date_of_interview", "job_role", "status", "scores"):
                assert k in row, f"row missing {k}"
            assert isinstance(row["scores"], list)
            pytest.AFS_FIRST_EMAIL = row["email"]
            pytest.AFS_ORIG_STATUS = row["status"]

    def test_distinct_pages(self, session):
        r1 = session.get(f"{BASE_URL}/api/bb/attended-for-scores",
                         params={"page": 1, "limit": 50}, timeout=30).json()
        r2 = session.get(f"{BASE_URL}/api/bb/attended-for-scores",
                         params={"page": 2, "limit": 50}, timeout=30).json()
        e1 = set(r["email"] for r in r1["data"])
        e2 = set(r["email"] for r in r2["data"])
        assert len(e1 & e2) < len(e1), "pages must differ"
        assert r1["total"] == r2["total"]

    def test_date_filter(self, session):
        r = session.get(f"{BASE_URL}/api/bb/attended-for-scores",
                        params={"startDate": "2026-01-01", "endDate": "2026-12-31",
                                "page": 1, "limit": 10}, timeout=30)
        assert r.status_code == 200


# ============ PUT /api/bb/applicant-score/{email} ============

class TestApplicantScoreUpdate:
    def test_put_still_works(self, session):
        email = getattr(pytest, "AFS_FIRST_EMAIL", None)
        orig_status = getattr(pytest, "AFS_ORIG_STATUS", "On hold")
        if not email:
            r = session.get(f"{BASE_URL}/api/bb/attended-for-scores",
                            params={"page": 1, "limit": 1}, timeout=30).json()
            email = r["data"][0]["email"]
            orig_status = r["data"][0]["status"]

        ts = int(time.time())
        test_status = f"TEST_STATUS_{ts}"
        r = session.put(f"{BASE_URL}/api/bb/applicant-score/{email}",
                        json={"status": test_status,
                              "scores": [{"round_name": "TEST", "score": 99.5}]},
                        timeout=30)
        assert r.status_code == 200, f"PUT failed: {r.status_code} {r.text[:300]}"
        assert r.json().get("success") is True

        # Verify via GET
        r2 = session.get(f"{BASE_URL}/api/bb/attended-for-scores",
                         params={"page": 1, "limit": 200}, timeout=30).json()
        match = next((row for row in r2["data"] if row["email"] == email), None)
        if match:
            assert match["status"] == test_status, f"status not persisted: {match}"
            test_round = next((s for s in match["scores"]
                               if s.get("round_name") == "TEST"), None)
            assert test_round is not None, "TEST round not found"
            assert float(test_round["score"]) == 99.5

        # Revert
        revert = session.put(f"{BASE_URL}/api/bb/applicant-score/{email}",
                             json={"status": orig_status or "On hold"}, timeout=30)
        assert revert.status_code == 200
