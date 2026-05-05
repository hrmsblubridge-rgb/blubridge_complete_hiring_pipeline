"""
Iteration 36 — Global column sorting tests.

Covers:
- /api/applicants  sort_by={name,email,...}, sort_dir={asc,desc}, invalid sort_by fallback
- /api/attended    sort_by=schedule_date desc
- /api/role        sort_by=name desc
- /api/bb/interview-reports  sort_by=name asc
- /api/bb/attended-for-scores sort_by=schedule_date asc

Auth: cookie-based via POST /api/login  (creds in /app/memory/test_credentials.md)
"""

import os
import re
import pytest
import requests

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL').rstrip('/')
ADMIN_USER = "Admin User"
ADMIN_PASS = "Admin User"


@pytest.fixture(scope="module")
def session():
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/login",
               json={"username": ADMIN_USER, "password": ADMIN_PASS},
               timeout=20)
    if r.status_code != 200:
        pytest.skip(f"Login failed: {r.status_code} {r.text}")
    return s


def _names(data_list):
    # Mongo sorts case-sensitively by default — preserve raw case for comparison
    return [(d.get("name") or "").strip() for d in data_list if d.get("name")]


def _is_sorted(values, reverse=False):
    """Lenient sort check — ignores '-' placeholder values, allows ties.
    Compares using Mongo-like case-sensitive byte order (Python default str sort).
    """
    cleaned = [v for v in values if v and v != '-']
    if len(cleaned) < 2:
        return True
    return cleaned == sorted(cleaned, reverse=reverse)


# ============ /api/applicants ============

class TestApplicantsSort:
    def test_sort_by_name_asc(self, session):
        r = session.get(f"{BASE_URL}/api/applicants",
                        params={"sort_by": "name", "sort_dir": "asc", "limit": 50}, timeout=30)
        assert r.status_code == 200, r.text
        data = r.json().get("data", [])
        assert _is_sorted(_names(data), reverse=False), f"Names not asc-sorted: {_names(data)[:5]}"

    def test_sort_by_name_desc(self, session):
        r1 = session.get(f"{BASE_URL}/api/applicants",
                         params={"sort_by": "name", "sort_dir": "asc", "limit": 50}, timeout=30)
        r2 = session.get(f"{BASE_URL}/api/applicants",
                         params={"sort_by": "name", "sort_dir": "desc", "limit": 50}, timeout=30)
        assert r1.status_code == 200 and r2.status_code == 200
        d1 = r1.json().get("data", [])
        d2 = r2.json().get("data", [])
        assert _is_sorted(_names(d2), reverse=True)
        # First row must differ between asc and desc when at least 2 distinct names exist
        if len(d1) >= 2 and len(d2) >= 2 and len(set(_names(d1))) > 1:
            assert d1[0].get("name") != d2[0].get("name"), "asc and desc first rows should differ"

    def test_sort_by_email_desc(self, session):
        r = session.get(f"{BASE_URL}/api/applicants",
                        params={"sort_by": "email", "sort_dir": "desc", "limit": 50}, timeout=30)
        assert r.status_code == 200
        emails = [(d.get("email") or "") for d in r.json().get("data", []) if d.get("email") and d.get("email") != '-']
        assert _is_sorted(emails, reverse=True), f"emails not desc: {emails[:5]}"

    def test_invalid_sort_by_falls_back(self, session):
        # Should NOT 400/500; should silently fall back to default (name asc)
        r_inv = session.get(f"{BASE_URL}/api/applicants",
                            params={"sort_by": "__hack__; DROP", "sort_dir": "desc", "limit": 50}, timeout=30)
        assert r_inv.status_code == 200, f"invalid sort_by should fallback, got {r_inv.status_code} {r_inv.text}"
        r_def = session.get(f"{BASE_URL}/api/applicants",
                            params={"limit": 50}, timeout=30)
        assert r_def.status_code == 200
        # default = name asc → first-row name should match the bare default call
        d_inv = r_inv.json().get("data", [])
        d_def = r_def.json().get("data", [])
        if d_inv and d_def:
            assert d_inv[0].get("name") == d_def[0].get("name"), "invalid sort_by must fall back to default"


# ============ /api/attended ============

class TestAttendedSort:
    def test_sort_by_schedule_date_desc(self, session):
        r_asc = session.get(f"{BASE_URL}/api/attended",
                            params={"sort_by": "schedule_date", "sort_dir": "asc", "limit": 50}, timeout=30)
        r_desc = session.get(f"{BASE_URL}/api/attended",
                             params={"sort_by": "schedule_date", "sort_dir": "desc", "limit": 50}, timeout=30)
        assert r_asc.status_code == 200 and r_desc.status_code == 200, f"{r_asc.text} | {r_desc.text}"
        d_asc = r_asc.json().get("data", [])
        d_desc = r_desc.json().get("data", [])
        # If we have at least 2 rows with distinct schedule_dates, first row must differ
        sd_asc = [d.get("schedule_date") for d in d_asc if d.get("schedule_date") and d.get("schedule_date") != '-']
        sd_desc = [d.get("schedule_date") for d in d_desc if d.get("schedule_date") and d.get("schedule_date") != '-']
        if len(set(sd_asc)) > 1:
            assert d_asc[0].get("schedule_date") != d_desc[0].get("schedule_date"), \
                "asc/desc first row schedule_date should differ"


# ============ /api/role ============

class TestRoleSort:
    def _pick_a_role(self, session):
        r = session.get(f"{BASE_URL}/api/applicants", params={"limit": 5}, timeout=30)
        if r.status_code != 200:
            return None
        for d in r.json().get("data", []):
            jr = d.get("job_role") or d.get("job_title")
            if jr and jr != '-':
                return jr
        return None

    def test_sort_by_name_desc(self, session):
        role = self._pick_a_role(session)
        if not role:
            pytest.skip("No job role found in /api/applicants")
        r_asc = session.get(f"{BASE_URL}/api/role",
                            params={"jobRole": role, "sort_by": "name", "sort_dir": "asc", "limit": 50}, timeout=30)
        r_desc = session.get(f"{BASE_URL}/api/role",
                             params={"jobRole": role, "sort_by": "name", "sort_dir": "desc", "limit": 50}, timeout=30)
        assert r_asc.status_code == 200 and r_desc.status_code == 200, f"{r_asc.text} | {r_desc.text}"
        n_desc = _names(r_desc.json().get("data", []))
        assert _is_sorted(n_desc, reverse=True), f"role names not desc: {n_desc[:5]}"


# ============ /api/bb/interview-reports ============

class TestBBInterviewReportsSort:
    def test_sort_by_name_asc(self, session):
        r = session.get(f"{BASE_URL}/api/bb/interview-reports",
                        params={"sort_by": "name", "sort_dir": "asc", "limit": 50}, timeout=30)
        # Endpoint may legitimately return 200 with empty data
        assert r.status_code == 200, r.text
        data = r.json().get("data", [])
        assert _is_sorted(_names(data), reverse=False)

    def test_invalid_sort_by_falls_back(self, session):
        r = session.get(f"{BASE_URL}/api/bb/interview-reports",
                        params={"sort_by": "__hack__", "sort_dir": "desc", "limit": 20}, timeout=30)
        assert r.status_code == 200, r.text


# ============ /api/bb/attended-for-scores ============

class TestBBAttendedForScoresSort:
    def test_sort_by_schedule_date_asc(self, session):
        r = session.get(f"{BASE_URL}/api/bb/attended-for-scores",
                        params={"sort_by": "schedule_date", "sort_dir": "asc", "limit": 50}, timeout=30)
        assert r.status_code == 200, r.text
        data = r.json().get("data", [])
        sd = [d.get("schedule_date") for d in data if d.get("schedule_date") and d.get("schedule_date") != '-']
        assert _is_sorted(sd, reverse=False)

    def test_sort_by_name_desc(self, session):
        r = session.get(f"{BASE_URL}/api/bb/attended-for-scores",
                        params={"sort_by": "name", "sort_dir": "desc", "limit": 50}, timeout=30)
        assert r.status_code == 200
        assert _is_sorted(_names(r.json().get("data", [])), reverse=True)


# ============ Regression: pagination + filters still work with sort ============

class TestRegressionWithSort:
    def test_pagination_with_sort(self, session):
        r1 = session.get(f"{BASE_URL}/api/applicants",
                         params={"sort_by": "name", "sort_dir": "asc", "page": 1, "limit": 5}, timeout=30)
        r2 = session.get(f"{BASE_URL}/api/applicants",
                         params={"sort_by": "name", "sort_dir": "asc", "page": 2, "limit": 5}, timeout=30)
        assert r1.status_code == 200 and r2.status_code == 200
        d1 = r1.json().get("data", [])
        d2 = r2.json().get("data", [])
        if d1 and d2 and len(d1) >= 1 and len(d2) >= 1:
            # last of page 1 <= first of page 2 (asc, case-sensitive Mongo order)
            last_p1 = (d1[-1].get("name") or "")
            first_p2 = (d2[0].get("name") or "")
            if last_p1 and first_p2:
                assert last_p1 <= first_p2, \
                    f"pagination broke sort: p1.last={last_p1} > p2.first={first_p2}"
