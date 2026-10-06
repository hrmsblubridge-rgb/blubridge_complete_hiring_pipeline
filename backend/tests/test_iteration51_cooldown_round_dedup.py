"""Iter51 — Cooldown bypass for test users + Round dedup (export/import/UI).

Tests:
    1. Test user `rajlearn@gmail.com / 8883847098` (allowlist pair) bypasses
       the 4-month cooldown even after a recently-attended record exists.
    2. Non-allowlisted user with the same recently-attended record is BLOCKED
       (409 cooldown response).
    3. Import preview merges "Accounts1" + "Accounts 1" → single canonical
       column "Accounts 1"; applicant's score lands in the canonical bucket.
    4. Export collapses raw round names (case + spacing variants) into one
       canonical column; CSV/XLSX no longer carries duplicates.
    5. /api/bb/rounds list dedupes case-insensitively at render time as a
       safety net (legacy bad data is masked from the UI).
"""
import io
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


def _login():
    s = requests.Session()
    r = s.post(f"{_api()}/api/login",
               json={"username": "Admin User", "password": "Admin User"}, timeout=10)
    assert r.status_code == 200
    return s


# ---------- 1. Cooldown bypass ----------

def test_cooldown_bypass_for_allowlisted_test_users():
    """Allowlisted (email, phone) pair must skip the 4-month re-registration
    block even when a recently attended bb_registrations row exists."""
    sync = MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
    test_email = "rajlearn@gmail.com"
    test_phone = "8883847098"

    # Need a real form to register against. Use the first available one
    # (form lookup happens before the cooldown check, so we must have one).
    forms = list(sync.bb_hiring_forms.find({}, {"_id": 1, "slug": 1, "form_type_id": 1}).limit(1))
    if not forms:
        pytest.skip("No bb_hiring_forms available for cooldown test")
    form_slug = forms[0].get("slug") or str(forms[0]["_id"])

    # Inject a recently-attended record so the cooldown WOULD trigger
    seeded_id = sync.bb_registrations.insert_one({
        "email": test_email, "phone": test_phone,
        "otp_verified": True,
        "otp_sent_at": datetime.now(timezone.utc).isoformat(),  # very recent
        "iter51_marker": True,
    }).inserted_id
    try:
        payload = {
            "form_id": form_slug,
            "full_name": "Iter51 Cooldown Bypass",
            "email": test_email, "phone": test_phone,
            "age": 25, "current_location_state": "TN",
            "preferred_location_city": "Chennai",
            "year_of_graduation": 2024,
            "degree": "B.Tech", "course": "CSE",
            "college": "Anna University",
            "location_change": "Yes", "attend_in_person": "Yes",
        }
        r = requests.post(f"{_api()}/api/pub/register", json=payload, timeout=20)
        # MUST NOT be the cooldown 409. Other validation rejections (e.g.
        # form conditions) are still acceptable for this regression — we only
        # care that the 4-month block is bypassed.
        if r.status_code == 409:
            assert "already attended" not in (r.json().get("detail") or ""), r.text
        # Confirm the bypass log fired (best-effort: check pipeline_data was
        # at least attempted, OR registration succeeded). The strict assertion
        # above covers the cooldown-specific regression.
    finally:
        sync.bb_registrations.delete_one({"_id": seeded_id})


def test_cooldown_blocks_non_allowlisted_users():
    sync = MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
    forms = list(sync.bb_hiring_forms.find({}, {"_id": 1, "slug": 1}).limit(1))
    if not forms:
        pytest.skip("No bb_hiring_forms available")
    form_slug = forms[0].get("slug") or str(forms[0]["_id"])
    stamp = int(time.time())
    test_email = f"iter51_blocked_{stamp}@x.test"
    test_phone = f"99{stamp % 100000000:08d}"
    seeded_id = sync.bb_registrations.insert_one({
        "email": test_email, "phone": test_phone,
        "otp_verified": True,
        "otp_sent_at": datetime.now(timezone.utc).isoformat(),
        "iter51_marker": True,
    }).inserted_id
    try:
        payload = {
            "form_id": form_slug,
            "full_name": "Iter51 Blocked",
            "email": test_email, "phone": test_phone,
            "age": 25, "current_location_state": "TN",
            "preferred_location_city": "Chennai",
            "year_of_graduation": 2024,
            "degree": "B.Tech", "course": "CSE",
            "college": "Anna University",
            "location_change": "Yes", "attend_in_person": "Yes",
        }
        r = requests.post(f"{_api()}/api/pub/register", json=payload, timeout=20)
        assert r.status_code == 409, f"Expected 409 cooldown, got {r.status_code}: {r.text}"
        assert "already attended" in (r.json().get("detail") or "")
    finally:
        sync.bb_registrations.delete_one({"_id": seeded_id})


# ---------- 2. Round dedup ----------

def test_import_preview_collapses_round_variants():
    """When the imported file has BOTH 'Accounts1' and 'Accounts 1' columns,
    the preview returns ONE canonical column and the applicant's score from
    either column ends up under the same canonical bucket."""
    s = _login()
    headers = ["Name", "Schedule Date", "College", "Degree", "Course",
               "Year of Graduation", "Email", "Phone", "Job Role", "Status",
               "Accounts1", "Accounts 1", "Mensa Org"]
    stamp = int(time.time())
    em = f"iter51_dedup_{stamp}@x.test"
    rows = [["Test", "", "", "", "", "", em, "9990051001", "", "On hold",
             "", "7", "5"]]   # only 'Accounts 1' has value
    csv = (",".join(headers) + "\n" +
           ",".join(rows[0]) + "\n").encode()
    r = s.post(f"{_api()}/api/bb/import-scores/preview",
               files={"file": ("dedup.csv", csv, "text/csv")}, timeout=15)
    assert r.status_code == 200, r.text
    body = r.json()
    # Single canonical "Accounts 1" column (not Accounts1 + Accounts 1)
    assert "Accounts 1" in body["round_columns"]
    assert "Accounts1" not in body["round_columns"]
    # Score lands under canonical bucket
    rscores = {sc["round_name"]: sc["score"] for sc in body["rows"][0]["scores"]}
    assert rscores.get("Accounts 1") == 7
    assert "Accounts1" not in rscores
    # Mensa Org variant also normalized
    assert rscores.get("Mensa Org") == 5


def test_export_collapses_round_variants():
    """Live export must not list 'Accounts1' AND 'Accounts 1' as separate
    columns — both should collapse into one canonical column."""
    sync = MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
    distinct = sync.score_sheet.distinct("round_name")
    if not ("Accounts1" in distinct and "Accounts 1" in distinct):
        pytest.skip("Live data doesn't contain both Accounts1 + Accounts 1 right now")
    s = _login()
    r = s.get(f"{_api()}/api/bb/export-scores", params={"format": "csv"}, timeout=120)
    assert r.status_code == 200, r.text[:200]
    header_line = r.content.split(b"\n", 1)[0].decode("utf-8-sig")
    cols = [c.strip().strip('"') for c in header_line.split(",")]
    # Either canonical "Accounts 1" present, but never both
    has_canon = "Accounts 1" in cols
    has_collapsed = "Accounts1" in cols
    assert not (has_canon and has_collapsed), \
        f"Both spelling variants present: cols={[c for c in cols if 'Account' in c]}"


def test_rounds_list_dedupes_at_render():
    """Inject a duplicate round into bb_rounds, hit /api/bb/rounds, confirm
    only one entry is returned."""
    sync = MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
    stamp = int(time.time())
    base_name = f"Iter51Dup_{stamp}"
    id1 = sync.bb_rounds.insert_one({"name": base_name, "active": True, "order": 0,
                                      "created_at": datetime.now(timezone.utc).isoformat()}).inserted_id
    id2 = sync.bb_rounds.insert_one({"name": base_name + "  ", "active": True, "order": 0,
                                      "created_at": datetime.now(timezone.utc).isoformat()}).inserted_id
    try:
        s = _login()
        r = s.get(f"{_api()}/api/bb/rounds", timeout=10)
        assert r.status_code == 200
        rounds = r.json().get("rounds") or []
        # Only one entry whose canonical name matches base_name
        matches = [x for x in rounds if (x.get("name") or "").strip() == base_name]
        assert len(matches) == 1, f"Expected 1 dedup'd round, got {len(matches)}"
    finally:
        sync.bb_rounds.delete_many({"_id": {"$in": [id1, id2]}})
