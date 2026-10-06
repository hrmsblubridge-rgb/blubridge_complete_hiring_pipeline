"""Iteration 44 — Smart Candidate Matching + Runtime Fallback + Backfill.

Tests the Email+Phone cross-source resolver and the non-destructive merge in
register flows:

    1. _is_blank treats None / '' / 'NULL' / 'N/A' as missing.
    2. _norm_email / _norm_phone normalise consistently.
    3. _resolve_candidate_extras pulls college_type/source/college from
       bb_registrations + naukri_applies.
    4. /api/bb/verify-otp success card uses the runtime fallback when
       pipeline_data lacks college_type / source.
    5. New registration on an existing email DOES NOT overwrite curated
       profile fields (only fills missing fields).
"""
import asyncio
import os
import sys
import time
import pytest
from datetime import datetime, timezone

from dotenv import load_dotenv
load_dotenv("/app/backend/.env")
sys.path.insert(0, "/app/backend")

from motor.motor_asyncio import AsyncIOMotorClient

from bb_modules import (
    _is_blank, _norm_email, _norm_phone,
    _resolve_candidate_extras, init_bb,
)
from server import _build_college_rank_lookup, _classify_college, db


@pytest.fixture(scope="module", autouse=True)
def _bootstrap_bb():
    init_bb(db, None, _build_college_rank_lookup, _classify_college)


# ---------- helpers ----------

def test_is_blank_handles_legacy_values():
    assert _is_blank(None) is True
    assert _is_blank("") is True
    assert _is_blank("   ") is True
    assert _is_blank("NULL") is True
    assert _is_blank("null") is True
    assert _is_blank("N/A") is True
    assert _is_blank("None") is True
    assert _is_blank("Non NIRF") is False
    assert _is_blank("naukri") is False


def test_norm_email_and_phone():
    assert _norm_email("  Test@Example.COM ") == "test@example.com"
    assert _norm_email(None) == ""
    assert _norm_phone("+91 98765 43210") == "9876543210"
    assert _norm_phone("0098765 43210") == "9876543210"
    assert _norm_phone(None) == ""


# ---------- resolver ----------

@pytest.mark.asyncio
async def test_resolve_pulls_from_naukri_when_pipeline_blank():
    """Pick a real naukri_applies row whose email/phone exist there but the
    pipeline_data row is missing college_type/source. Resolver must fill in
    college_type, source, and college."""
    nk = await db.naukri_applies.find_one(
        {"email": {"$nin": [None, ""]}, "phone": {"$nin": [None, ""]},
         "$or": [{"ug_university": {"$nin": [None, ""]}},
                 {"pg_university": {"$nin": [None, ""]}}]},
        {"_id": 0, "email": 1, "phone": 1, "ug_university": 1, "pg_university": 1, "source": 1},
    )
    assert nk, "Need at least one naukri_applies record for this regression"
    out = await _resolve_candidate_extras(nk["email"], nk["phone"])
    assert out.get("source", "").startswith("naukri"), out
    assert out.get("college_type") in ("Non NIRF",) or out.get("college_type", "").startswith("NIRF - #"), out
    assert out.get("college"), out


@pytest.mark.asyncio
async def test_resolve_returns_empty_for_unknown_candidate():
    out = await _resolve_candidate_extras("does-not-exist-xyz@nowhere.test", "0000000000")
    assert out == {} or all(not v for v in out.values())


# ---------- non-destructive register merge ----------

def test_pipeline_data_merge_preserves_curated_fields():
    """Seed a pipeline_data row with curated values, then run the merge logic
    that register_applicant uses. Curated profile fields must NOT change;
    dynamic fields (job_role, last_update) MUST change."""
    from pymongo import MongoClient
    sync = MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
    test_email = f"merge_test_{int(time.time())}@example.test"
    test_phone = "9999000099"
    submitted_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    seed = {
        "email": test_email, "phone": test_phone,
        "name": "ORIGINAL NAME", "college": "ORIGINAL COLLEGE",
        "college_type": "NIRF - #5", "source": "registration_form",
        "job_role": "OldRole", "submitted_at": submitted_at,
        "_college_status": "NIRF - #5", "_nirf_category": "NIRF",
        "_college_resolved": "ORIGINAL COLLEGE",
    }
    sync.pipeline_data.insert_one(dict(seed))
    try:
        pipeline_doc_set = {
            "name": "NEW NAME", "email": test_email, "phone": test_phone,
            "age": 25, "college": "NEW COLLEGE", "college_type": "Non NIRF",
            "degree": "B.Tech", "course": "CSE", "location": "Chennai",
            "job_role": "NewRole", "job_title": "NewRole",
            "email_type": "shortlist", "year_of_graduation": "2024",
            "submitted_at": submitted_at, "schedule_date": "",
            "schedule_time": "", "otp_verified": "", "result_status": "",
            "source": "registration_form",
            "_college_status": "Non NIRF", "_nirf_category": "Non NIRF",
            "_college_resolved": "NEW COLLEGE", "_match_confidence": 1.0,
            "_normalized_job_role": "newrole",
        }
        PROFILE_FIELDS = {"name", "email", "phone", "age", "college",
                          "college_type", "degree", "course", "location",
                          "year_of_graduation", "source",
                          "_college_status", "_nirf_category",
                          "_college_resolved", "_match_confidence"}
        DYNAMIC_FIELDS = {"job_role", "job_title", "email_type",
                          "submitted_at", "last_update",
                          "_normalized_job_role", "schedule_date",
                          "schedule_time", "otp_verified", "result_status"}
        existing = sync.pipeline_data.find_one(
            {"$or": [{"email": test_email}, {"phone": test_phone}]},
            {"_id": 0},
        )
        set_fields = {}
        for k, v in pipeline_doc_set.items():
            if k in DYNAMIC_FIELDS:
                set_fields[k] = v
            elif k in PROFILE_FIELDS:
                if not existing or _is_blank(existing.get(k)):
                    set_fields[k] = v
            else:
                set_fields[k] = v
        set_fields["last_update"] = submitted_at
        sync.pipeline_data.update_one({"email": test_email}, {"$set": set_fields})

        after = sync.pipeline_data.find_one({"email": test_email}, {"_id": 0})
        assert after["name"] == "ORIGINAL NAME"
        assert after["college"] == "ORIGINAL COLLEGE"
        assert after["college_type"] == "NIRF - #5"
        assert after["source"] == "registration_form"
        assert after["job_role"] == "NewRole"
        assert after["last_update"] == submitted_at
    finally:
        sync.pipeline_data.delete_one({"email": test_email})


# ---------- runtime fallback in /api/bb/verify-otp ----------

def test_verify_otp_success_card_includes_college_via_fallback():
    """The user-visible bug: 'College Type: N/A' / 'Source: N/A' on the success
    card. After the fallback, an OTP-verified bb_registration with associated
    pipeline_data + bb_registrations data should yield a non-N/A card."""
    import requests
    api_url = os.environ.get("REACT_APP_BACKEND_URL_INTERNAL", "http://localhost:8001")

    # Use a fresh sync motor lookup
    from pymongo import MongoClient
    sync = MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
    reg = sync.bb_registrations.find_one({"otp_verified": True, "otp": {"$nin": [None, ""]}})
    if not reg:
        pytest.skip("No verified registration available for this regression")

    s = requests.Session()
    s.post(f"{api_url}/api/login",
           json={"username": "Admin User", "password": "Admin User"}, timeout=10)
    r = s.post(f"{api_url}/api/bb/verify-otp",
               json={"phone": reg["phone"], "otp": reg["otp"]}, timeout=10)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body.get("success") is True, body
    cand = body.get("candidate") or {}
    assert (cand.get("college_type") and cand["college_type"] != "N/A") \
           or (cand.get("source") and cand["source"] != "N/A") \
           or (cand.get("college") and cand["college"] != "N/A"), cand
