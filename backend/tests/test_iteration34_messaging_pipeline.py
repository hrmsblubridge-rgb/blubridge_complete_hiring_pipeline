"""Iteration 34 backend tests.

Coverage:
  - messaging._resolve_recipient routing (real vs is_test=True)
  - schedule_interview 12h→24h time normalization (+ pipeline_data sync)
  - register_applicant writes to pipeline_data with normalized fields
  - notify_schedule_confirmation fires unconditionally on schedule POST (cutoff-aware)
  - GET /api/summary, /api/applicants, /api/data/classification still work (back-compat)

ALL test seed data is tagged isTest=True with email pattern test_iter34_*@example.com
and explicitly cleaned up at module teardown.
"""
import os
import sys
import time
import asyncio
import secrets
from datetime import datetime, timezone, timedelta

import pytest
import requests
from bson import ObjectId

# Make backend importable for direct module checks
sys.path.insert(0, "/app/backend")

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")
API = f"{BASE_URL}/api"

TEST_EMAIL_PREFIX = "test_iter34_"


# ---------- Mongo client (module scope) ----------
@pytest.fixture(scope="module")
def db():
    from motor.motor_asyncio import AsyncIOMotorClient
    mongo_url = os.environ["MONGO_URL"]
    db_name = os.environ["DB_NAME"]
    client = AsyncIOMotorClient(mongo_url)
    yield client[db_name]
    client.close()


@pytest.fixture(scope="module")
def loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="module", autouse=True)
def cleanup(db, loop):
    yield
    async def _clean():
        await db.bb_registrations.delete_many({"email": {"$regex": TEST_EMAIL_PREFIX}})
        await db.pipeline_data.delete_many({"email": {"$regex": TEST_EMAIL_PREFIX}})
    loop.run_until_complete(_clean())


# ============================================================
# 1) messaging._resolve_recipient routing
# ============================================================
class TestResolveRecipient:
    def test_real_recipient_passthrough(self):
        from messaging import _resolve_recipient
        p, e = _resolve_recipient("9999988888", "real@example.com", is_test=False)
        assert p == "9999988888"
        assert e == "real@example.com"

    def test_is_test_overrides(self):
        from messaging import _resolve_recipient
        p, e = _resolve_recipient("9999988888", "real@example.com", is_test=True)
        assert p == os.environ.get("TEST_PHONE", "9443109903")
        assert e == os.environ.get("TEST_EMAIL", "rishi.nayak@blubridge.com")

    def test_test_mode_env_no_op(self):
        """TEST_MODE=true must NOT override anymore (only is_test flag does)."""
        from messaging import _resolve_recipient
        os.environ["TEST_MODE"] = "true"   # explicit set
        p, e = _resolve_recipient("9999988888", "real@example.com", is_test=False)
        assert p == "9999988888"
        assert e == "real@example.com"


# ============================================================
# 2) schedule_interview 12h→24h normalization
# ============================================================
class TestScheduleTimeNormalization:
    def test_schedule_converts_1pm_to_13(self, db, loop):
        token = secrets.token_urlsafe(16)
        email = f"{TEST_EMAIL_PREFIX}sched1@example.com"

        async def setup():
            await db.bb_registrations.insert_one({
                "schedule_token": token,
                "email": email,
                "phone": "9000000001",
                "full_name": "Sched Test 1",
                "isTest": True,
                "is_shortlisted": True,
                "status": "Interview Not Scheduled",
                "registered_at": datetime.now(timezone.utc).isoformat(),
                "schedule_date": None,
                "schedule_time": None,
                "reschedule_count": 0,
            })
            await db.pipeline_data.insert_one({
                "email": email,
                "name": "Sched Test 1",
                "phone": "9000000001",
                "schedule_date": "",
                "schedule_time": "",
                "isTest": True,
            })
        loop.run_until_complete(setup())

        r = requests.post(f"{API}/pub/schedule/{token}",
                          json={"date": "2026-06-01", "time": "1:00 PM"}, timeout=30)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body.get("success") is True

        async def verify():
            reg = await db.bb_registrations.find_one({"schedule_token": token})
            pdoc = await db.pipeline_data.find_one({"email": email})
            return reg, pdoc
        reg, pdoc = loop.run_until_complete(verify())

        assert reg["schedule_time"] == "13:00:00", f"got {reg['schedule_time']!r}"
        assert reg["schedule_date"] == "2026-06-01"
        assert reg["status"] == "Interview Scheduled"
        assert pdoc["schedule_time"] == "13:00:00"
        assert pdoc["schedule_date"] == "2026-06-01"

    @pytest.mark.parametrize("inp,expected", [
        ("9:30 AM", "09:30:00"),
        ("12:00 PM", "12:00:00"),  # noon
        ("12:00 AM", "00:00:00"),  # midnight
        ("11 PM", "23:00:00"),
        ("13:45", "13:45:00"),
    ])
    def test_24h_helper_via_schedule(self, db, loop, inp, expected):
        token = secrets.token_urlsafe(16)
        email = f"{TEST_EMAIL_PREFIX}t_{secrets.token_hex(4)}@example.com"

        async def setup():
            await db.bb_registrations.insert_one({
                "schedule_token": token, "email": email, "phone": "9000000002",
                "full_name": "T", "isTest": True, "is_shortlisted": True,
                "status": "Interview Not Scheduled",
                "registered_at": datetime.now(timezone.utc).isoformat(),
                "schedule_date": None, "schedule_time": None, "reschedule_count": 0,
            })
        loop.run_until_complete(setup())

        r = requests.post(f"{API}/pub/schedule/{token}",
                          json={"date": "2026-06-15", "time": inp}, timeout=30)
        assert r.status_code == 200, r.text

        async def get():
            return await db.bb_registrations.find_one({"schedule_token": token})
        reg = loop.run_until_complete(get())
        assert reg["schedule_time"] == expected, f"input={inp!r} expected={expected!r} got={reg['schedule_time']!r}"


# ============================================================
# 3) Registration writes to pipeline_data
# ============================================================
class TestRegistrationPipelineData:
    def test_register_creates_pipeline_record(self, db, loop):
        # Pick an active form
        async def get_form():
            f = await db.bb_hiring_forms.find_one({})
            return f
        form = loop.run_until_complete(get_form())
        if not form:
            pytest.skip("No hiring form in DB to register against")
        form_id = str(form["_id"])

        email = f"{TEST_EMAIL_PREFIX}reg1@example.com"
        payload = {
            "form_id": form_id,
            "full_name": "Iter34 Reg",
            "email": email,
            "phone": "9000099999",
            "age": 24,
            "current_location_state": "Tamil Nadu",
            "preferred_location_city": "Chennai",
            "year_of_graduation": 2024,
            "degree": "B.E",
            "course": "CSE",
            "college": "IIT Madras",
            "location_change": "Yes",
            "attend_in_person": "Yes",
        }
        r = requests.post(f"{API}/pub/register", json=payload, timeout=30)
        assert r.status_code == 200, r.text
        data = r.json()
        assert "is_shortlisted" in data

        async def get_pipeline():
            return await db.pipeline_data.find_one({"email": email})
        pdoc = loop.run_until_complete(get_pipeline())
        assert pdoc is not None, "pipeline_data row not created"

        # Required fields
        assert pdoc["name"] == "Iter34 Reg"
        assert pdoc["email"] == email
        assert pdoc["phone"] == "9000099999"
        assert pdoc["age"] == 24
        assert pdoc["college"] == "IIT Madras"
        assert pdoc["degree"] == "B.E"
        assert pdoc["course"] == "CSE"
        assert pdoc["location"] == "Chennai"
        # college_type must be either NIRF - #N or "Non NIRF"
        ct = pdoc.get("college_type", "")
        assert ct.startswith("NIRF - #") or ct == "Non NIRF", f"college_type={ct!r}"
        # submitted_at format yyyy-mm-dd HH:mm:ss
        sa = pdoc["submitted_at"]
        datetime.strptime(sa, "%Y-%m-%d %H:%M:%S")  # raises if bad
        assert pdoc.get("_normalized_job_role") is not None
        assert pdoc.get("_nirf_category") in ("NIRF", "Non NIRF")
        assert pdoc.get("source") == "registration_form"


# ============================================================
# 4) WhatsApp/Email post-schedule unconditional fire
# ============================================================
class TestScheduleConfirmationFires:
    def test_post_cutoff_record_triggers_message(self, db, loop):
        """For a brand-new (post-cutoff) test record, schedule_interview must
        invoke notify_schedule_confirmation regardless of shortlist_mail_sent.
        We verify by tailing backend log for [Email]/[WhatsApp]/[TEST_ROUTE]
        within ~6s after the API call."""
        token = secrets.token_urlsafe(16)
        email = f"{TEST_EMAIL_PREFIX}fire@example.com"
        # registered_at must be >= MESSAGING_CUTOFF_TS for _is_new_record check
        now_iso = datetime.now(timezone.utc).isoformat()

        async def setup():
            await db.bb_registrations.insert_one({
                "schedule_token": token, "email": email, "phone": "9000000003",
                "full_name": "Fire Test", "isTest": True, "is_shortlisted": True,
                "status": "Interview Not Scheduled",
                "registered_at": now_iso,
                "schedule_date": None, "schedule_time": None, "reschedule_count": 0,
                "shortlist_mail_sent": False,   # critical: was the gate before
            })
        loop.run_until_complete(setup())

        # Record log size before
        log_path = "/var/log/supervisor/backend.err.log"
        before = 0
        try:
            before = os.path.getsize(log_path)
        except OSError:
            pytest.skip("Backend log not accessible")

        r = requests.post(f"{API}/pub/schedule/{token}",
                          json={"date": "2026-07-01", "time": "2:30 PM"}, timeout=30)
        assert r.status_code == 200, r.text

        # Wait up to 8s for async messaging to complete
        deadline = time.time() + 8
        log_tail = ""
        while time.time() < deadline:
            try:
                with open(log_path, "rb") as f:
                    f.seek(before)
                    log_tail += f.read().decode("utf-8", errors="ignore")
            except OSError:
                pass
            if any(k in log_tail for k in ("[TEST_ROUTE]", "[Email]", "campaign=Schedule",
                                           "Schedule confirmation", "[SKIP]")):
                break
            time.sleep(0.5)

        # Must observe SOME messaging activity (test-route override OR send attempt)
        observed = any(k in log_tail for k in (
            "[TEST_ROUTE]", "[Email] SENT", "campaign=Schedule",
            "[SKIP]", "Schedule confirmation",
        ))
        assert observed, (
            f"Expected messaging log within 8s of schedule POST. "
            f"Tail (last 500 chars):\n{log_tail[-500:]}"
        )

        # And interview_mail_sent flag must be set
        async def check():
            return await db.bb_registrations.find_one({"schedule_token": token})
        reg = loop.run_until_complete(check())
        assert reg.get("interview_mail_sent") in (True, False)  # set either way; ensure key present
        assert "interview_mail_sent" in reg


# ============================================================
# 5) Backwards-compat: summary / applicants / classification
# ============================================================
class TestBackCompat:
    @pytest.fixture(scope="class")
    def session(self):
        s = requests.Session()
        r = s.post(f"{API}/login",
                   json={"username": "Admin User", "password": "Admin User"},
                   timeout=30)
        if r.status_code != 200:
            pytest.skip(f"Login failed: {r.status_code} {r.text[:200]}")
        return s

    def test_summary_has_total_registered(self, session):
        r = session.get(f"{API}/summary", timeout=60)
        assert r.status_code == 200, r.text
        data = r.json()
        assert "total_registered" in data
        assert data["total_registered"] > 100_000, f"got {data['total_registered']}"

    def test_applicants_returns_rows(self, session):
        # Try a few shapes
        for path in ("/applicants?limit=10", "/applicants", "/data/registered?limit=10"):
            r = session.get(f"{API}{path}", timeout=60)
            if r.status_code == 200:
                data = r.json()
                rows = data.get("data") or data.get("applicants") or data.get("rows") or data
                assert isinstance(rows, list) and len(rows) > 0
                return
        pytest.fail(f"No applicants endpoint returned 200")

    def test_classification_endpoint_ok(self, session):
        r = session.get(f"{API}/data/classification", timeout=60)
        assert r.status_code < 500, r.text
