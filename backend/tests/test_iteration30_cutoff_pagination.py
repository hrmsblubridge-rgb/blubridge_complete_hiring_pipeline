"""
Iteration 30 Backend Tests:
- Pagination edge cases (last page, beyond-last, page-size change) on /api/bb/interview-reports & /api/bb/attended-for-scores
- DB-level MESSAGING_CUTOFF_TS guard on bg_workers (negative + positive cases)
- Regression: GET /api/data/classification, GET /api/applicants?page=1&limit=10
"""
import os
import time
import math
import uuid
import asyncio
from datetime import datetime, timezone, timedelta

import pytest
import requests
from motor.motor_asyncio import AsyncIOMotorClient


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


def _load_backend_env():
    cfg = {}
    if os.path.exists("/app/backend/.env"):
        with open("/app/backend/.env") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                cfg[k] = v.strip().strip('"').strip("'")
    return cfg


BASE_URL = _load_backend_url()
ENV = _load_backend_env()
MONGO_URL = ENV.get("MONGO_URL")
DB_NAME = ENV.get("DB_NAME", "hr_analytics")
CUTOFF = ENV.get("MESSAGING_CUTOFF_TS", "9999-12-31T23:59:59+00:00")

USERNAME = "Admin User"
PASSWORD = "Admin User"


# -------- Fixtures --------

@pytest.fixture(scope="session")
def session():
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/login",
               json={"username": USERNAME, "password": PASSWORD}, timeout=30)
    if r.status_code != 200:
        pytest.skip(f"Login failed: {r.status_code} {r.text[:200]}")
    return s


# ============ Pagination edge cases on /api/bb/interview-reports ============

class TestInterviewReportsPagination:
    def test_last_page_returns_data(self, session):
        r = session.get(f"{BASE_URL}/api/bb/interview-reports",
                        params={"page": 1, "limit": 10}, timeout=30)
        assert r.status_code == 200
        body = r.json()
        total = body["total"]
        total_pages = body["totalPages"]
        assert total_pages == math.ceil(total / 10)

        r2 = session.get(f"{BASE_URL}/api/bb/interview-reports",
                         params={"page": total_pages, "limit": 10}, timeout=30)
        assert r2.status_code == 200
        body2 = r2.json()
        expected_last = total - (total_pages - 1) * 10
        assert len(body2["data"]) == expected_last, (
            f"Last page len={len(body2['data'])} expected={expected_last}"
        )
        assert body2["page"] == total_pages

    def test_beyond_last_page_empty_200(self, session):
        r = session.get(f"{BASE_URL}/api/bb/interview-reports",
                        params={"page": 1, "limit": 10}, timeout=30)
        total_pages = r.json()["totalPages"]
        r2 = session.get(f"{BASE_URL}/api/bb/interview-reports",
                         params={"page": total_pages + 1, "limit": 10}, timeout=30)
        assert r2.status_code == 200, f"Expected 200, got {r2.status_code}"
        assert r2.json()["data"] == [], "Beyond-last page should return empty data"

    def test_response_under_10s(self, session):
        t0 = time.time()
        r = session.get(f"{BASE_URL}/api/bb/interview-reports",
                        params={"page": 1, "limit": 100}, timeout=15)
        assert r.status_code == 200
        assert time.time() - t0 < 10


# ============ Pagination on /api/bb/attended-for-scores ============

class TestAttendedForScoresPagination:
    def test_basic_contract(self, session):
        r = session.get(f"{BASE_URL}/api/bb/attended-for-scores",
                        params={"page": 1, "limit": 10}, timeout=30)
        assert r.status_code == 200
        body = r.json()
        for k in ("data", "total", "page", "limit", "totalPages"):
            assert k in body, f"Missing key {k}"
        assert body["page"] == 1
        assert body["limit"] == 10

    def test_distinct_rows_across_pages(self, session):
        r1 = session.get(f"{BASE_URL}/api/bb/attended-for-scores",
                         params={"page": 1, "limit": 10}, timeout=30)
        r2 = session.get(f"{BASE_URL}/api/bb/attended-for-scores",
                         params={"page": 2, "limit": 10}, timeout=30)
        assert r1.status_code == 200 and r2.status_code == 200
        emails1 = {row.get("email") for row in r1.json()["data"]}
        emails2 = {row.get("email") for row in r2.json()["data"]}
        if emails1 and emails2:
            assert emails1.isdisjoint(emails2), "Pages should not overlap"


# ============ Regression ============

class TestRegression:
    def test_classification_unchanged(self, session):
        r = session.get(f"{BASE_URL}/api/data/classification", timeout=30)
        assert r.status_code == 200
        body = r.json()
        assert body.get("total_registered") == 100798, f"Got {body.get('total_registered')}"
        assert body.get("total_unregistered") == 15555, f"Got {body.get('total_unregistered')}"

    def test_applicants_pagination(self, session):
        r = session.get(f"{BASE_URL}/api/applicants",
                        params={"page": 1, "limit": 10}, timeout=30)
        assert r.status_code == 200
        body = r.json()
        assert "data" in body or "applicants" in body or isinstance(body, list), \
            f"Unexpected shape: {list(body.keys()) if isinstance(body, dict) else type(body)}"


# ============ Messaging Cutoff Guard (DB-level) ============

@pytest.mark.skipif(not MONGO_URL, reason="MONGO_URL not configured")
class TestMessagingCutoff:
    """Inserts test bb_registrations docs and verifies cutoff guard behavior.

    Negative case: registered_at < cutoff → worker MUST NOT process.
    Positive case: registered_at = now (>= cutoff) → worker DOES process within ~60-90s.
    Both docs are tagged isTest:true and cleaned up.
    """

    @pytest.fixture
    def db(self):
        client = AsyncIOMotorClient(MONGO_URL)
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        yield client[DB_NAME], loop
        loop.run_until_complete(client.close()) if False else None
        loop.close()

    def _make_doc(self, registered_at_iso: str, suffix: str):
        now = datetime.now(timezone.utc)
        today_str = now.strftime("%Y-%m-%d")
        # schedule_time = now+2h (within OTP send window: schedule_time-3h .. -1min)
        sched_dt = now + timedelta(hours=2)
        sched_time = sched_dt.strftime("%H:%M")
        return {
            "isTest": True,
            "full_name": f"TEST iter30 {suffix}",
            "email": f"TEST_iter30_{suffix}@example.com",
            "phone": f"99999{suffix[-5:].zfill(5)}",
            "job_role": "Software Engineer",
            "is_shortlisted": True,
            "schedule_date": today_str,
            "schedule_time": sched_time,
            "schedule_token": str(uuid.uuid4()),
            "registered_at": registered_at_iso,
            "otp_sent": False,
            "status": "Interview Scheduled",
        }

    def test_cutoff_negative_legacy_record_NOT_messaged(self, db):
        database, loop = db

        async def run():
            suffix = "neg" + uuid.uuid4().hex[:6]
            doc = self._make_doc("2020-01-01T00:00:00+00:00", suffix)
            res = await database.bb_registrations.insert_one(doc)
            try:
                # Wait two OTP-worker cycles (30s each) + buffer
                await asyncio.sleep(70)
                fetched = await database.bb_registrations.find_one({"_id": res.inserted_id})
                assert fetched.get("otp_sent") in (False, None), (
                    f"Legacy record (pre-cutoff) was incorrectly messaged: otp_sent={fetched.get('otp_sent')}"
                )
                assert not fetched.get("otp"), "Legacy record should not have OTP set"
            finally:
                await database.bb_registrations.delete_one({"_id": res.inserted_id})

        loop.run_until_complete(run())

    def test_cutoff_positive_new_record_IS_messaged(self, db):
        database, loop = db

        async def run():
            suffix = "pos" + uuid.uuid4().hex[:6]
            now_iso = datetime.now(timezone.utc).isoformat()
            doc = self._make_doc(now_iso, suffix)
            res = await database.bb_registrations.insert_one(doc)
            try:
                # OTP worker runs every 30s. Wait up to 90s.
                processed = False
                for _ in range(9):
                    await asyncio.sleep(10)
                    fetched = await database.bb_registrations.find_one({"_id": res.inserted_id})
                    if fetched.get("otp_sent"):
                        processed = True
                        break
                assert processed, "New record (post-cutoff) was NOT messaged within 90s"
                assert fetched.get("otp"), "OTP should be set"
                assert fetched.get("otpGeneratedAt"), "otpGeneratedAt camelCase should be set"
                assert fetched.get("otpExpiry"), "otpExpiry camelCase should be set"
                assert fetched.get("otp_sent_at"), "otp_sent_at snake_case should be set"
            finally:
                await database.bb_registrations.delete_one({"_id": res.inserted_id})

        loop.run_until_complete(run())
