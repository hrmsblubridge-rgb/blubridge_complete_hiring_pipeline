"""Iteration 28 regression tests:
- May 2026 classification rule (Registered = pipeline_data, Unregistered = naukri without match)
- /api/data/classification, /api/data/registered, /api/data/unregistered endpoints
- /api/summary extended fields (total_registered_hr, total_unregistered_naukri)
- OTP worker camelCase aliases (otpGeneratedAt, otpExpiry)
- isTest safety (test rows excluded from counts)
- Regression for iteration_27 endpoints
"""
import os
import time
import uuid
import pytest
import requests
from datetime import datetime, timezone, timedelta
from pymongo import MongoClient

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://applicant-details.preview.emergentagent.com").rstrip("/")
MONGO_URL = os.environ.get("MONGO_URL") or "mongodb+srv://rishinayak_db_user:wZklvHcJ14pCK5x6@cluster0.ek8almy.mongodb.net/hr_analytics?retryWrites=true&w=majority"
DB_NAME = os.environ.get("DB_NAME") or "hr_analytics"


# ============ Fixtures ============

@pytest.fixture(scope="session")
def mongo_db():
    """Direct MongoDB connection for seed/cleanup of test data."""
    client = MongoClient(MONGO_URL, serverSelectionTimeoutMS=10000)
    db = client[DB_NAME]
    yield db
    client.close()


@pytest.fixture(scope="session")
def auth_session():
    """Login once and reuse cookie session across all tests."""
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/login",
               json={"username": "Admin User", "password": "Admin User"},
               timeout=30)
    assert r.status_code == 200, f"Login failed: {r.status_code} {r.text}"
    data = r.json()
    assert data.get("success") is True
    assert "access_token" in s.cookies, "access_token cookie not set"
    return s


# ============ Auth ============

class TestAuth:
    def test_login_returns_cookie(self, auth_session):
        r = auth_session.get(f"{BASE_URL}/api/auth/check", timeout=30)
        assert r.status_code == 200
        assert r.json().get("authenticated") is True


# ============ Classification endpoint ============

class TestClassification:
    def test_classification_shape_and_counts(self, auth_session, mongo_db):
        r = auth_session.get(f"{BASE_URL}/api/data/classification", timeout=60)
        assert r.status_code == 200, r.text
        data = r.json()
        # required keys
        for k in ["total_registered", "total_unregistered", "total_naukri", "matched", "note"]:
            assert k in data, f"{k} missing in response"

        # Cross-check against DB directly
        exclude_test = {"isTest": {"$ne": True}}
        expected_registered = mongo_db.pipeline_data.count_documents(exclude_test)
        expected_naukri = mongo_db.naukri_applies.count_documents(exclude_test)
        expected_unreg = mongo_db.naukri_applies.count_documents({**exclude_test, "_is_registered": {"$ne": True}})
        expected_matched = mongo_db.naukri_applies.count_documents({**exclude_test, "_is_registered": True})

        assert data["total_registered"] == expected_registered, (
            f"total_registered {data['total_registered']} != pipeline_data count {expected_registered}"
        )
        assert data["total_naukri"] == expected_naukri
        assert data["total_unregistered"] == expected_unreg
        assert data["matched"] == expected_matched
        # sanity: numbers reasonable (per task brief tolerance)
        assert data["total_registered"] > 10000
        assert data["total_naukri"] > 10000


# ============ Registered / Unregistered drill-down endpoints ============

class TestDrillDowns:
    EXPECTED_COLUMNS = {"name", "email", "phone", "job_title", "date_of_application",
                        "gender", "date_of_birth"}

    def test_registered_endpoint(self, auth_session, mongo_db):
        r = auth_session.get(f"{BASE_URL}/api/data/registered?page=1&limit=10", timeout=60)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["page"] == 1
        assert body["limit"] == 10
        assert body["total"] == mongo_db.pipeline_data.count_documents({"isTest": {"$ne": True}})
        assert isinstance(body["data"], list)
        assert len(body["data"]) <= 10
        # Columns declared
        assert set(body["columns"]) == self.EXPECTED_COLUMNS
        if body["data"]:
            row = body["data"][0]
            # All expected columns present in row
            for c in self.EXPECTED_COLUMNS:
                assert c in row, f"column {c} missing in registered row"

    def test_unregistered_endpoint(self, auth_session, mongo_db):
        r = auth_session.get(f"{BASE_URL}/api/data/unregistered?page=1&limit=10", timeout=60)
        assert r.status_code == 200, r.text
        body = r.json()
        expected = mongo_db.naukri_applies.count_documents(
            {"isTest": {"$ne": True}, "_is_registered": {"$ne": True}}
        )
        assert body["total"] == expected
        assert set(body["columns"]) == self.EXPECTED_COLUMNS
        assert len(body["data"]) <= 10
        if body["data"]:
            for c in self.EXPECTED_COLUMNS:
                assert c in body["data"][0]


# ============ isTest safety ============

class TestIsTestSafety:
    def test_registered_excludes_isTest(self, auth_session, mongo_db):
        # baseline
        r = auth_session.get(f"{BASE_URL}/api/data/registered?page=1&limit=1", timeout=60)
        baseline = r.json()["total"]

        # insert test pipeline doc
        test_id = f"TEST_iter28_pipeline_{uuid.uuid4().hex[:8]}"
        mongo_db.pipeline_data.insert_one({
            "name": test_id,
            "email": f"{test_id}@example.com",
            "phone": "9999999999",
            "job_role": "TEST_ROLE",
            "isTest": True,
            "schedule_date": "2026-01-01",
        })
        try:
            time.sleep(1)
            r2 = auth_session.get(f"{BASE_URL}/api/data/registered?page=1&limit=1", timeout=60)
            after = r2.json()["total"]
            assert after == baseline, f"isTest row leaked: {after} vs {baseline}"

            # classification endpoint also unchanged
            rc = auth_session.get(f"{BASE_URL}/api/data/classification", timeout=60)
            assert rc.json()["total_registered"] == baseline
        finally:
            mongo_db.pipeline_data.delete_many({"name": test_id})

    def test_unregistered_excludes_isTest(self, auth_session, mongo_db):
        r = auth_session.get(f"{BASE_URL}/api/data/classification", timeout=60)
        baseline_unreg = r.json()["total_unregistered"]

        test_id = f"TEST_iter28_naukri_{uuid.uuid4().hex[:8]}"
        mongo_db.naukri_applies.insert_one({
            "name": test_id,
            "email": f"{test_id}@example.com",
            "phone": "8888888888",
            "job_title": "TEST_ROLE",
            "isTest": True,
            "_is_registered": False,
        })
        try:
            time.sleep(1)
            r2 = auth_session.get(f"{BASE_URL}/api/data/classification", timeout=60)
            after_unreg = r2.json()["total_unregistered"]
            assert after_unreg == baseline_unreg, (
                f"isTest naukri row leaked into unregistered: {after_unreg} vs {baseline_unreg}"
            )

            # also /data/unregistered
            r3 = auth_session.get(f"{BASE_URL}/api/data/unregistered?page=1&limit=1", timeout=60)
            assert r3.json()["total"] == baseline_unreg
        finally:
            mongo_db.naukri_applies.delete_many({"name": test_id})


# ============ /api/summary new top-level fields ============

class TestSummaryExtended:
    def test_summary_has_new_fields(self, auth_session, mongo_db):
        r = auth_session.get(f"{BASE_URL}/api/summary", timeout=120)
        assert r.status_code == 200, r.text
        body = r.json()
        assert "data" in body and isinstance(body["data"], list)
        # Legacy fields still present
        assert "total_registered" in body
        # New May 2026 fields
        assert "total_registered_hr" in body, "missing total_registered_hr"
        assert "total_unregistered_naukri" in body, "missing total_unregistered_naukri"

        exclude_test = {"isTest": {"$ne": True}}
        assert body["total_registered_hr"] == mongo_db.pipeline_data.count_documents(exclude_test)
        assert body["total_unregistered_naukri"] == mongo_db.naukri_applies.count_documents(
            {**exclude_test, "_is_registered": {"$ne": True}}
        )


# ============ Regression: iteration_27 endpoints still work ============

class TestRegressionIter27:
    def test_applicants_basic(self, auth_session):
        r = auth_session.get(f"{BASE_URL}/api/applicants?page=1&limit=50", timeout=60)
        assert r.status_code == 200, r.text
        body = r.json()
        assert isinstance(body.get("data"), list)
        assert len(body["data"]) == 50 or len(body["data"]) > 0
        assert body.get("total", 0) > 100

    def test_applicants_nirf_filter(self, auth_session):
        r = auth_session.get(f"{BASE_URL}/api/applicants?collegeStatus=NIRF&page=1&limit=20", timeout=60)
        assert r.status_code == 200
        body = r.json()
        for row in body["data"]:
            cs = str(row.get("college_status") or "")
            assert cs.startswith("NIRF"), f"non-NIRF row leaked: {cs}"

    def test_applicants_pagination_distinct(self, auth_session):
        r1 = auth_session.get(f"{BASE_URL}/api/applicants?page=1&limit=10", timeout=60).json()
        r2 = auth_session.get(f"{BASE_URL}/api/applicants?page=2&limit=10", timeout=60).json()
        emails1 = {row.get("email") for row in r1["data"]}
        emails2 = {row.get("email") for row in r2["data"]}
        # pages should be mostly distinct
        overlap = emails1 & emails2
        assert len(overlap) < len(emails1), "pagination returning same rows"

    def test_applicants_job_role_filter(self, auth_session):
        jr = auth_session.get(f"{BASE_URL}/api/job-roles", timeout=60).json()
        assert "job_roles" in jr and len(jr["job_roles"]) > 0
        role = jr["job_roles"][0]["job_role"]
        r = auth_session.get(f"{BASE_URL}/api/applicants",
                             params={"jobRole": role, "page": 1, "limit": 10},
                             timeout=60)
        assert r.status_code == 200
        assert len(r.json()["data"]) >= 1

    def test_job_roles(self, auth_session):
        r = auth_session.get(f"{BASE_URL}/api/job-roles", timeout=60)
        assert r.status_code == 200
        body = r.json()
        assert "job_roles" in body and len(body["job_roles"]) > 0
        # sorted desc
        counts = [x["count"] for x in body["job_roles"]]
        assert counts == sorted(counts, reverse=True)

    def test_attended(self, auth_session):
        r = auth_session.get(f"{BASE_URL}/api/attended?page=1&limit=50", timeout=120)
        assert r.status_code == 200, r.text


# ============ OTP worker camelCase aliases ============

class TestOtpWorkerCamelCase:
    def test_otp_worker_writes_camelcase_aliases(self, mongo_db):
        """Insert a test bb_registration within the 3h-1min send window, wait for
        worker, assert both snake_case + camelCase fields present, verify
        otpExpiry equals the interview datetime ISO."""
        now = datetime.now(timezone.utc)
        today_str = now.strftime("%Y-%m-%d")

        # Schedule 2h from now -> inside [now+3h to now+1min] inverse = now within window
        interview_dt = (now + timedelta(hours=2)).replace(second=0, microsecond=0)
        # Must be same calendar day UTC — if it crosses midnight, shift back
        if interview_dt.strftime("%Y-%m-%d") != today_str:
            interview_dt = now.replace(hour=23, minute=59, second=0, microsecond=0)
        schedule_time_str = interview_dt.strftime("%H:%M")

        test_email = f"TEST_iter28_otp_{uuid.uuid4().hex[:8]}@example.com"
        doc = {
            "full_name": "TEST_iter28_otp",
            "email": test_email,
            "phone": "7777777777",
            "job_role": "TEST_ROLE",
            "schedule_date": today_str,
            "schedule_time": schedule_time_str,
            "is_shortlisted": True,
            "otp_sent": False,
            "isTest": True,
        }
        inserted = mongo_db.bb_registrations.insert_one(doc)
        inserted_id = inserted.inserted_id

        try:
            # Worker runs every 30s — wait up to ~75s
            found = None
            for _ in range(15):
                time.sleep(5)
                found = mongo_db.bb_registrations.find_one({"_id": inserted_id})
                if found and found.get("otp_sent") is True:
                    break

            assert found is not None, "test doc disappeared"
            if not found.get("otp_sent"):
                pytest.fail(f"OTP worker did not process within ~75s; doc={found}")

            # snake_case fields
            assert found.get("otp"), "otp missing"
            assert found.get("otp_sent_at"), "otp_sent_at missing"
            # camelCase aliases
            assert found.get("otpGeneratedAt"), "otpGeneratedAt (camelCase) missing"
            assert found.get("otpExpiry"), "otpExpiry (camelCase) missing"

            # otpExpiry should equal interview datetime ISO
            expected_expiry = interview_dt.isoformat()
            assert found["otpExpiry"] == expected_expiry, (
                f"otpExpiry {found['otpExpiry']} != expected {expected_expiry}"
            )

            # otpGeneratedAt should roughly equal otp_sent_at
            assert found["otpGeneratedAt"] == found["otp_sent_at"], (
                "otpGeneratedAt should alias otp_sent_at"
            )
        finally:
            mongo_db.bb_registrations.delete_one({"_id": inserted_id})
            # Cleanup any registered_candidates side-effect
            mongo_db.registered_candidates.update_many(
                {"email": test_email},
                {"$unset": {"otp": "", "otp_send": "", "otpGeneratedAt": "", "otpExpiry": ""}}
            )
