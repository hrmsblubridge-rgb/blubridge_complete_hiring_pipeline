"""
Iteration 27 - Performance optimization regression tests.

Validates that the persisted derived fields and DB-level
filtering refactor of /api/summary, /api/applicants, /api/job-roles,
/api/attended, /api/attended-roles do not regress functionality.
"""
import os
import time
import pytest
import requests

def _load_backend_url():
    v = os.environ.get("REACT_APP_BACKEND_URL")
    if not v:
        # read from frontend/.env
        try:
            with open("/app/frontend/.env") as f:
                for line in f:
                    if line.startswith("REACT_APP_BACKEND_URL="):
                        v = line.strip().split("=", 1)[1]
                        break
        except Exception:
            pass
    assert v, "REACT_APP_BACKEND_URL not set"
    return v.rstrip("/")


BASE_URL = _load_backend_url()
API = f"{BASE_URL}/api"

# Login uses 'Admin User'/'Admin User' per task brief
ADMIN_USER = "Admin User"
ADMIN_PASS = "Admin User"

PERF_BUDGET_S = 12  # generous regression budget (manual curls were 1-5s)


# ------------- fixtures -------------
@pytest.fixture(scope="session")
def session():
    s = requests.Session()
    r = s.post(f"{API}/login", json={"username": ADMIN_USER, "password": ADMIN_PASS}, timeout=20)
    assert r.status_code == 200, f"Login failed: {r.status_code} {r.text}"
    return s


# ------------- AUTH -------------
class TestAuth:
    def test_login_admin_user(self):
        r = requests.post(f"{API}/login", json={"username": ADMIN_USER, "password": ADMIN_PASS}, timeout=20)
        assert r.status_code == 200
        # cookie should be set
        assert any(c.name for c in r.cookies) or "session" in (r.headers.get("set-cookie", "").lower())


# ------------- SUMMARY -------------
class TestSummary:
    def test_summary_basic_and_perf(self, session):
        t0 = time.time()
        r = session.get(f"{API}/summary", timeout=30)
        elapsed = time.time() - t0
        assert r.status_code == 200, r.text
        assert elapsed < PERF_BUDGET_S, f"/api/summary too slow: {elapsed:.2f}s"
        data = r.json()
        # accept either list rows or dict containing total_registered
        total = None
        if isinstance(data, dict):
            total = data.get("total_registered") or data.get("totalRegistered")
            if total is None:
                # maybe nested funnel
                for k in ("funnel", "summary", "data"):
                    v = data.get(k)
                    if isinstance(v, dict):
                        total = v.get("total_registered") or v.get("totalRegistered")
                        if total:
                            break
        # primary expectation per task
        if total is not None:
            assert int(total) == 19913, f"total_registered expected 19913, got {total}"

    def test_summary_with_date_range(self, session):
        r = session.get(f"{API}/summary", params={"startDate": "2026-01-01", "endDate": "2026-12-31"}, timeout=30)
        assert r.status_code == 200, r.text
        # Should still return valid shape (not 500)
        assert r.json() is not None

    def test_summary_with_search_AI(self, session):
        r = session.get(f"{API}/summary", params={"search": "AI"}, timeout=30)
        assert r.status_code == 200, r.text
        body = r.json()
        # try to find rows list with job_role column
        rows = None
        if isinstance(body, list):
            rows = body
        elif isinstance(body, dict):
            for key in ("rows", "data", "items", "results", "summary"):
                v = body.get(key)
                if isinstance(v, list):
                    rows = v
                    break
        if rows:
            for row in rows[:25]:
                jr = (row.get("job_role") or row.get("jobRole") or "")
                # search filter must keep AI rows
                assert "AI" in str(jr).upper() or "AI" in str(jr), f"row missing AI in job_role: {row}"


# ------------- APPLICANTS -------------
class TestApplicants:
    expected_keys = [
        "name", "email", "phone", "college_status", "college", "match_confidence",
        "degree", "job_role", "registered_status", "registered_date",
        "schedule_date", "schedule_time", "attended_or_not", "result_status",
    ]

    def _rows(self, body):
        if isinstance(body, list):
            return body, None
        if isinstance(body, dict):
            for k in ("data", "items", "applicants", "rows", "results"):
                if isinstance(body.get(k), list):
                    return body[k], body.get("total") or body.get("count")
        return [], None

    def test_applicants_page1_limit100(self, session):
        t0 = time.time()
        r = session.get(f"{API}/applicants", params={"page": 1, "limit": 100}, timeout=30)
        elapsed = time.time() - t0
        assert r.status_code == 200, r.text
        assert elapsed < PERF_BUDGET_S
        body = r.json()
        rows, total = self._rows(body)
        assert len(rows) == 100, f"expected 100 rows, got {len(rows)}"
        if total is not None:
            assert total > 0
        # check key set on first row
        sample = rows[0]
        missing = [k for k in self.expected_keys if k not in sample]
        assert not missing, f"missing keys in applicants response: {missing}; sample keys: {list(sample.keys())}"

    def test_applicants_filter_nirf(self, session):
        r = session.get(f"{API}/applicants", params={"collegeStatus": "NIRF", "page": 1, "limit": 50}, timeout=30)
        assert r.status_code == 200, r.text
        rows, _ = self._rows(r.json())
        assert rows, "expected NIRF applicants"
        bad = [row for row in rows if not str(row.get("college_status", "")).startswith("NIRF - #")]
        assert not bad, f"non-NIRF rows leaked: {bad[:2]}"

    def test_applicants_filter_non_nirf(self, session):
        r = session.get(f"{API}/applicants", params={"collegeStatus": "Non NIRF", "page": 1, "limit": 50}, timeout=30)
        assert r.status_code == 200, r.text
        rows, _ = self._rows(r.json())
        assert rows, "expected Non NIRF applicants"
        bad = [row for row in rows if str(row.get("college_status", "")).startswith("NIRF - #")]
        assert not bad, f"NIRF rows leaked into Non NIRF filter: {bad[:2]}"

    def test_applicants_filter_jobrole(self, session):
        # get a real job role
        jr_resp = session.get(f"{API}/job-roles", timeout=30)
        assert jr_resp.status_code == 200, jr_resp.text
        jr_body = jr_resp.json()
        jr_list = jr_body if isinstance(jr_body, list) else jr_body.get("data") or jr_body.get("job_roles") or []
        assert jr_list, "no job roles to filter by"
        target = jr_list[0]
        role_name = target.get("job_role") or target.get("jobRole") or target.get("name")
        assert role_name
        r = session.get(f"{API}/applicants", params={"jobRole": role_name, "page": 1, "limit": 50}, timeout=30)
        assert r.status_code == 200, r.text
        rows, _ = self._rows(r.json())
        # Allow normalization - just ensure non-empty (because job-roles came from same DB)
        assert rows, f"no applicants for jobRole={role_name}"

    def test_applicants_search_email(self, session):
        # find a sample email
        first = session.get(f"{API}/applicants", params={"page": 1, "limit": 5}, timeout=30).json()
        rows, _ = self._rows(first)
        assert rows
        email = rows[0].get("email") or ""
        assert "@" in email, f"no email to use for search test: {rows[0]}"
        substr = email.split("@")[0][:5]
        r = session.get(f"{API}/applicants", params={"search": substr, "page": 1, "limit": 25}, timeout=30)
        assert r.status_code == 200, r.text
        rrows, _ = self._rows(r.json())
        assert rrows, f"search for {substr} returned no rows"
        assert any(substr.lower() in (str(x.get("email", "")) + str(x.get("name", "")) + str(x.get("phone", ""))).lower() for x in rrows)

    def test_applicants_pagination(self, session):
        r1 = session.get(f"{API}/applicants", params={"page": 1, "limit": 50}, timeout=30)
        r2 = session.get(f"{API}/applicants", params={"page": 2, "limit": 50}, timeout=30)
        assert r1.status_code == 200 and r2.status_code == 200
        rows1, total1 = self._rows(r1.json())
        rows2, total2 = self._rows(r2.json())
        assert rows1 and rows2
        # different rows
        ids1 = {(r.get("email"), r.get("phone"), r.get("name")) for r in rows1}
        ids2 = {(r.get("email"), r.get("phone"), r.get("name")) for r in rows2}
        overlap = ids1 & ids2
        assert len(overlap) < len(rows1) // 2, f"too much overlap between page1 and page2: {len(overlap)}"
        if total1 is not None and total2 is not None:
            assert total1 == total2


# ------------- JOB-ROLES -------------
class TestJobRoles:
    def test_job_roles_list_and_sorted(self, session):
        t0 = time.time()
        r = session.get(f"{API}/job-roles", timeout=30)
        elapsed = time.time() - t0
        assert r.status_code == 200, r.text
        assert elapsed < PERF_BUDGET_S
        body = r.json()
        rows = body if isinstance(body, list) else body.get("data") or body.get("job_roles") or []
        assert rows, "no job roles returned"
        sample = rows[0]
        assert ("job_role" in sample or "jobRole" in sample)
        assert "count" in sample
        counts = [int(x.get("count", 0)) for x in rows]
        assert counts == sorted(counts, reverse=True), "job-roles not sorted desc by count"


# ------------- ATTENDED -------------
class TestAttended:
    def _rows(self, body):
        if isinstance(body, list):
            return body
        if isinstance(body, dict):
            for k in ("data", "items", "rows", "results", "attended"):
                if isinstance(body.get(k), list):
                    return body[k]
        return []

    def test_attended_basic(self, session):
        t0 = time.time()
        r = session.get(f"{API}/attended", timeout=30)
        elapsed = time.time() - t0
        assert r.status_code == 200, r.text
        assert elapsed < PERF_BUDGET_S, f"/api/attended too slow: {elapsed:.2f}s"
        rows = self._rows(r.json())
        assert rows, "no attended rows"
        sample = rows[0]
        assert "schedule_date" in sample, f"schedule_date missing in {list(sample.keys())}"
        # round score columns are dynamic (round names like ZA, C++, Java, BA, etc.)
        # so we just verify there are extra columns beyond the standard set
        standard = {"name", "email", "phone", "college_status", "college", "match_confidence",
                    "degree", "course", "year_of_graduation", "job_role", "schedule_date",
                    "schedule_time", "attended_or_not", "result_status", "registered_status",
                    "registered_date"}
        extra = [k for k in sample.keys() if k not in standard]
        assert extra, f"no round score columns found; keys={list(sample.keys())}"

    def test_attended_filter_nirf(self, session):
        r = session.get(f"{API}/attended", params={"collegeStatus": "NIRF"}, timeout=30)
        assert r.status_code == 200, r.text
        rows = self._rows(r.json())
        # may legitimately be empty if no NIRF attended
        for row in rows:
            cs = str(row.get("college_status", ""))
            assert cs.startswith("NIRF - #") or cs == "", f"non-NIRF leaked: {row}"


# ------------- ATTENDED-ROLES -------------
class TestAttendedRoles:
    def test_attended_roles_list(self, session):
        r = session.get(f"{API}/attended-roles", timeout=30)
        assert r.status_code == 200, r.text
        body = r.json()
        rows = body if isinstance(body, list) else body.get("data") or body.get("attended_roles") or []
        # may be empty but must be a list-like
        assert isinstance(rows, list)


# ------------- ROLE (not refactored) -------------
class TestRoleNotRefactored:
    def test_role_endpoint_still_works(self, session):
        jr_resp = session.get(f"{API}/job-roles", timeout=30).json()
        rows = jr_resp if isinstance(jr_resp, list) else jr_resp.get("data") or jr_resp.get("job_roles") or []
        assert rows
        role = rows[0].get("job_role") or rows[0].get("jobRole") or rows[0].get("name")
        r = session.get(f"{API}/role", params={"jobRole": role, "page": 1, "limit": 100}, timeout=60)
        assert r.status_code == 200, r.text


# ------------- SMOKE -------------
class TestSmoke:
    @pytest.mark.parametrize("path", ["/bb/holidays", "/bb/job-roles", "/bb/hiring-forms"])
    def test_bb_endpoints(self, session, path):
        r = session.get(f"{API}{path}", timeout=30)
        assert r.status_code == 200, f"{path} -> {r.status_code} {r.text[:200]}"
