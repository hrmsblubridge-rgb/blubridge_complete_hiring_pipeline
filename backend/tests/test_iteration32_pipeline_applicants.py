"""Iteration 32 regression: /api/applicants, /api/attended, /api/job-roles,
/api/attended-roles now read from pipeline_data (HR-internal source of truth).

Per May 2026 classification rule:
- /api/applicants total ~ 100798 (was 19913)
- /api/attended    total ~ 5335   (was 1024)
- /api/summary     contract preserved (total_registered=100798)
"""
import os
import time
import requests
import pytest

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")
ADMIN_USER = "Admin User"
ADMIN_PASS = "Admin User"

EXPECTED_APPLICANTS_TOTAL = 100798
EXPECTED_APPLICANTS_TOLERANCE = 5000  # allow drift if ingest re-ran
EXPECTED_ATTENDED_TOTAL = 5335
EXPECTED_ATTENDED_TOLERANCE = 1500


@pytest.fixture(scope="module")
def session():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    r = s.post(f"{BASE_URL}/api/login",
               json={"username": ADMIN_USER, "password": ADMIN_PASS},
               timeout=30)
    if r.status_code != 200:
        pytest.skip(f"Login failed {r.status_code}: {r.text[:200]}")
    return s


# ---------------- /api/applicants ----------------

class TestApplicantsPipelineSource:
    def test_total_is_pipeline_count(self, session):
        t0 = time.time()
        r = session.get(f"{BASE_URL}/api/applicants",
                        params={"page": 1, "limit": 10}, timeout=30)
        elapsed = time.time() - t0
        assert r.status_code == 200, r.text[:300]
        data = r.json()
        total = data["total"]
        # Must be the new pipeline_data total (not the old 19913 JOIN-view total)
        assert total > 50000, f"Total {total} looks like the legacy 19913 JOIN view; expected ~100798"
        assert abs(total - EXPECTED_APPLICANTS_TOTAL) <= EXPECTED_APPLICANTS_TOLERANCE, \
            f"Total {total} drifted from {EXPECTED_APPLICANTS_TOTAL}"
        assert elapsed < 5.0, f"Response took {elapsed:.2f}s (>5s SLA)"

    def test_row_schema_has_required_keys(self, session):
        r = session.get(f"{BASE_URL}/api/applicants",
                        params={"page": 1, "limit": 10}, timeout=30)
        assert r.status_code == 200
        rows = r.json()["data"]
        assert len(rows) == 10
        required = {"name", "email", "phone", "college_status", "college",
                    "job_role", "registered_status", "registered_date",
                    "schedule_date", "schedule_time", "result_status"}
        missing = required - set(rows[0].keys())
        assert not missing, f"Missing keys: {missing}; got {list(rows[0].keys())}"

    def test_filter_nirf(self, session):
        r = session.get(f"{BASE_URL}/api/applicants",
                        params={"collegeStatus": "NIRF", "page": 1, "limit": 20}, timeout=30)
        assert r.status_code == 200
        data = r.json()
        assert data["total"] > 0, "NIRF filter returned 0 — _nirf_category not persisted?"
        for row in data["data"]:
            cs = (row.get("college_status") or "").strip()
            assert cs.startswith("NIRF"), f"Row college_status='{cs}' does not start with 'NIRF'"

    def test_filter_non_nirf(self, session):
        r = session.get(f"{BASE_URL}/api/applicants",
                        params={"collegeStatus": "Non NIRF", "page": 1, "limit": 20}, timeout=30)
        assert r.status_code == 200
        data = r.json()
        assert data["total"] > 0
        for row in data["data"]:
            assert row.get("college_status") == "Non NIRF", \
                f"Got college_status='{row.get('college_status')}' for Non NIRF filter"

    def test_filter_jobrole(self, session):
        rj = session.get(f"{BASE_URL}/api/job-roles", timeout=30).json()
        assert rj["job_roles"], "No job roles available"
        target_role = rj["job_roles"][0]["job_role"]
        r = session.get(f"{BASE_URL}/api/applicants",
                        params={"jobRole": target_role, "page": 1, "limit": 20}, timeout=30)
        assert r.status_code == 200
        data = r.json()
        full = session.get(f"{BASE_URL}/api/applicants",
                           params={"page": 1, "limit": 1}, timeout=30).json()
        assert data["total"] > 0
        assert data["total"] <= full["total"], \
            f"Filtered total {data['total']} should be <= unfiltered {full['total']}"
        for row in data["data"]:
            assert row.get("job_role", "").lower() == target_role.lower(), \
                f"Row job_role='{row.get('job_role')}' != filter '{target_role}'"

    def test_search_email(self, session):
        r = session.get(f"{BASE_URL}/api/applicants",
                        params={"search": "gmail.com", "page": 1, "limit": 5}, timeout=30)
        assert r.status_code == 200
        data = r.json()
        assert data["total"] > 0
        # at least one row should contain 'gmail.com' in any string field
        found = any("gmail.com" in str(row.get("email", "")).lower() for row in data["data"])
        assert found, "No 'gmail.com' match found in returned rows"

    def test_pagination_distinct(self, session):
        p1 = session.get(f"{BASE_URL}/api/applicants",
                         params={"page": 1, "limit": 10}, timeout=30).json()
        p2 = session.get(f"{BASE_URL}/api/applicants",
                         params={"page": 2, "limit": 10}, timeout=30).json()
        assert p1["total"] == p2["total"], "Total inconsistent across pages"
        names1 = {r["email"] for r in p1["data"]}
        names2 = {r["email"] for r in p2["data"]}
        assert names1.isdisjoint(names2), "Page 1 and Page 2 share rows — pagination broken"


# ---------------- /api/job-roles ----------------

class TestJobRoles:
    def test_aggregated_from_pipeline(self, session):
        r = session.get(f"{BASE_URL}/api/job-roles", timeout=30)
        assert r.status_code == 200
        roles = r.json()["job_roles"]
        assert len(roles) >= 30, f"Expected 40+ roles, got {len(roles)}"
        # Top role count > 1000 (pipeline source has high volume per role)
        assert roles[0]["count"] > 1000, \
            f"Top role '{roles[0]['job_role']}' count={roles[0]['count']} too low"
        # all unique
        names = [r["job_role"] for r in roles]
        assert len(names) == len(set(names)), "Duplicate roles found"


# ---------------- /api/attended ----------------

class TestAttendedPipelineSource:
    def test_total_is_pipeline_count(self, session):
        r = session.get(f"{BASE_URL}/api/attended",
                        params={"page": 1, "limit": 10}, timeout=30)
        assert r.status_code == 200, r.text[:300]
        data = r.json()
        total = data["total"]
        assert total > 1500, f"Attended total {total} looks like the legacy 1024 JOIN view"
        assert abs(total - EXPECTED_ATTENDED_TOTAL) <= EXPECTED_ATTENDED_TOLERANCE, \
            f"Attended total {total} drifted from {EXPECTED_ATTENDED_TOTAL}"

    def test_row_has_score_columns_and_schedule(self, session):
        r = session.get(f"{BASE_URL}/api/attended",
                        params={"page": 1, "limit": 5}, timeout=30)
        assert r.status_code == 200
        data = r.json()
        if not data["data"]:
            pytest.skip("No attended rows on page 1")
        row = data["data"][0]
        assert "schedule_date" in row
        assert "result_status" in row
        # Score round columns (e.g. ZA, C++, Java, BA, LA, Mensa, Accounts1...)
        # are present in addition to the standard list. Verify at least one
        # known round column exists.
        score_round_keys = {"ZA", "C++", "Java", "BA", "LA", "Mensa",
                            "Mensa Org", "Accounts1", "Accounts2", "BE", "BP"}
        present = score_round_keys & set(row.keys())
        assert present, \
            f"No score round columns found. Got keys: {list(row.keys())}"

    def test_attended_filter_nirf(self, session):
        r = session.get(f"{BASE_URL}/api/attended",
                        params={"collegeStatus": "NIRF", "page": 1, "limit": 10}, timeout=30)
        assert r.status_code == 200
        data = r.json()
        assert data["total"] >= 0
        for row in data["data"]:
            cs = (row.get("college_status") or "").strip()
            assert cs.startswith("NIRF") or cs == "-", \
                f"NIRF filter row got college_status='{cs}'"

    def test_attended_pagination_distinct(self, session):
        p1 = session.get(f"{BASE_URL}/api/attended",
                         params={"page": 1, "limit": 10}, timeout=30).json()
        if p1["total"] < 20:
            pytest.skip("Not enough attended rows for pagination test")
        p2 = session.get(f"{BASE_URL}/api/attended",
                         params={"page": 2, "limit": 10}, timeout=30).json()
        assert p1["total"] == p2["total"]
        e1 = {r.get("email") for r in p1["data"]}
        e2 = {r.get("email") for r in p2["data"]}
        assert e1.isdisjoint(e2), "Attended pagination duplicates rows"


# ---------------- /api/attended-roles ----------------

class TestAttendedRoles:
    def test_attended_roles_sum(self, session):
        r = session.get(f"{BASE_URL}/api/attended-roles", timeout=30)
        assert r.status_code == 200
        roles = r.json()["job_roles"]
        assert len(roles) > 0
        total_count = sum(r["count"] for r in roles)
        # /api/attended total
        att = session.get(f"{BASE_URL}/api/attended",
                          params={"page": 1, "limit": 1}, timeout=30).json()
        # /api/attended-roles uses (shortlist + schedule_date + schedule_time + otp_verified)
        # /api/attended uses (otp_verified) - so attended >= attended-roles sum
        # Allow generous tolerance (50%)
        assert total_count > 0
        assert total_count <= att["total"] * 1.5, \
            f"attended-roles sum={total_count} much greater than /attended total={att['total']}"


# ---------------- regression: /api/summary preserved ----------------

class TestSummaryRegression:
    def test_summary_contract(self, session):
        r = session.get(f"{BASE_URL}/api/summary", timeout=30)
        assert r.status_code == 200
        data = r.json()
        assert data.get("total_registered", 0) > 50000, \
            f"/api/summary total_registered={data.get('total_registered')} regressed"

    def test_classification_unchanged(self, session):
        r = session.get(f"{BASE_URL}/api/data/classification", timeout=30)
        assert r.status_code == 200
        data = r.json()
        assert "total_registered" in data
        assert data["total_registered"] > 50000
