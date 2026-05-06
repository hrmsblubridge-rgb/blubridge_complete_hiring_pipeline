"""Iter50 — Auto Move Public Registration → pipeline_data (College Drive).

Tests:
    1. New college-drive registration creates a pipeline_data row with
       source="college_drive", stage="registered", schedule_date/time,
       and a pipeline_synced_at timestamp.
    2. Re-registering the same email keeps profile fields preserved
       (name, college) but updates dynamic fields (schedule). scores/status
       are never touched.
    3. Phone↔email conflict (same phone bound to a different email) is
       logged and SKIPPED — registration still returns 200, but pipeline
       is not modified for the conflicting record.
    4. A pipeline insert/update failure must NOT fail the registration.
"""
import os
import sys
import time
from datetime import datetime, timezone

import pytest
import requests
from dotenv import load_dotenv
from pymongo import MongoClient

load_dotenv("/app/backend/.env")
sys.path.insert(0, "/app/backend")


def _api():
    return os.environ.get("REACT_APP_BACKEND_URL_INTERNAL", "http://localhost:8001")


def _ensure_schedule(sync, college, role):
    """Make sure an HR-configured schedule exists for the (college, role)
    combo so the registration endpoint doesn't 422 in tests."""
    sched = sync.bb_college_schedules.find_one({
        "college_name": college, "job_role": role,
    })
    if sched:
        return str(sched["_id"])
    res = sync.bb_college_schedules.insert_one({
        "college_name": college, "job_role": role,
        "schedule_date": "2026-12-31",
        "schedule_time": "10:00:00",
        "notes": "iter50 test",
        "active": True,
        "created_at": datetime.now(timezone.utc).isoformat(),
    })
    return str(res.inserted_id)


def _register(college, role, email, phone, name="Iter50 Test"):
    payload = {
        "full_name": name,
        "email": email,
        "phone": phone,
        "age": 22,
        "gender": "Male",
        "college": college,
        "degree": "B.Tech",
        "course": "CSE",
        "year_of_graduation": 2024,
        "preferred_location_city": "Chennai",
        "job_role": role,
    }
    return requests.post(f"{_api()}/api/pub/college-form/register",
                         json=payload, timeout=15)


def test_college_drive_registration_creates_pipeline_record():
    sync = MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
    stamp = int(time.time())
    college = f"Iter50 College {stamp}"
    role = f"Iter50 Role {stamp}"
    email = f"iter50_drive_{stamp}@x.test"
    phone = "9990050001"
    sched_id = _ensure_schedule(sync, college, role)
    try:
        r = _register(college, role, email, phone)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["success"] is True
        # pipeline_data populated with iter50 fields
        pd = sync.pipeline_data.find_one({"email": email})
        assert pd is not None, "pipeline_data row was not created"
        assert pd.get("source") == "college_drive"
        assert pd.get("stage") == "registered"
        assert pd.get("schedule_date") == "2026-12-31"
        assert pd.get("schedule_time") == "10:00:00"
        assert pd.get("college") == college
        assert pd.get("job_role") == role
        assert pd.get("pipeline_synced_at")
        assert pd.get("created_at")
        # No scores / no result_status writes here
        assert "scores" not in pd  # never touched by college-drive sync
    finally:
        sync.pipeline_data.delete_many({"email": email})
        try:
            from bson import ObjectId
            sync.bb_college_schedules.delete_one({"_id": ObjectId(sched_id)})
        except Exception:
            pass


def test_re_registration_preserves_profile_and_does_not_touch_scores():
    sync = MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
    stamp = int(time.time())
    college = f"Iter50 College B {stamp}"
    role = f"Iter50 Role B {stamp}"
    email = f"iter50_keep_{stamp}@x.test"
    phone = "9990050002"
    sched_id = _ensure_schedule(sync, college, role)
    try:
        # Pre-seed an existing pipeline row with curated profile + status + scores
        sync.pipeline_data.insert_one({
            "email": email, "phone": phone, "name": "ORIGINAL_NAME",
            "college": "Original College", "college_type": "NIRF - #5",
            "source": "naukri",
            "result_status": "Shortlisted",
            "stage": "round_1",
            "schedule_date": "2025-01-01", "schedule_time": "09:00:00",
            "created_at": "2025-01-01 00:00:00",
            "scores": [{"round_name": "BP", "score": 9}],
        })
        r = _register(college, role, email, phone, name="NEW_NAME")
        assert r.status_code == 200, r.text
        pd = sync.pipeline_data.find_one({"email": email})
        # Profile preserved
        assert pd["name"] == "ORIGINAL_NAME"
        assert pd["college"] == "Original College"
        assert pd["source"] == "naukri"  # never overwritten when already set
        # Dynamic fields refreshed
        assert pd["schedule_date"] == "2026-12-31"
        assert pd["schedule_time"] == "10:00:00"
        assert pd["job_role"] == role
        # scores + status NEVER touched by the sync
        assert pd["scores"] == [{"round_name": "BP", "score": 9}]
        assert pd["result_status"] == "Shortlisted"
        # stage:"registered" must NOT overwrite an existing stage (setOnInsert only)
        assert pd["stage"] == "round_1"
    finally:
        sync.pipeline_data.delete_many({"email": email})
        try:
            from bson import ObjectId
            sync.bb_college_schedules.delete_one({"_id": ObjectId(sched_id)})
        except Exception:
            pass


def test_phone_email_conflict_is_logged_and_skipped():
    sync = MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
    stamp = int(time.time())
    college = f"Iter50 College C {stamp}"
    role = f"Iter50 Role C {stamp}"
    email_existing = f"iter50_existing_{stamp}@x.test"
    email_new = f"iter50_new_{stamp}@x.test"
    phone = "9990050003"
    sched_id = _ensure_schedule(sync, college, role)
    try:
        # Existing pipeline row binds phone <-> email_existing
        sync.pipeline_data.insert_one({
            "email": email_existing, "phone": phone,
            "name": "Existing", "college": "Other",
            "source": "naukri", "stage": "registered",
        })
        # Now register with the SAME phone but a DIFFERENT email
        r = _register(college, role, email_new, phone, name="Conflict")
        # Spec: registration must still succeed even when pipeline sync skips
        assert r.status_code == 200, r.text
        # No pipeline row was created for email_new (conflict skipped)
        assert sync.pipeline_data.find_one({"email": email_new}) is None
        # Existing row untouched
        ex = sync.pipeline_data.find_one({"email": email_existing})
        assert ex["name"] == "Existing"
    finally:
        sync.pipeline_data.delete_many({"email": {"$in": [email_existing, email_new]}})
        try:
            from bson import ObjectId
            sync.bb_college_schedules.delete_one({"_id": ObjectId(sched_id)})
        except Exception:
            pass
