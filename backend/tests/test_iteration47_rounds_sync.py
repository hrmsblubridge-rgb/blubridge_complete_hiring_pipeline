"""Iter47 — Scores import syncs imported round names into bb_rounds so the
rounds UI (tabs/cards) shows manual + imported rounds together.

Tests:
    1. Confirming an import registers NEW round names in bb_rounds
       (alphabetical, case-insensitive dedupe, no duplicate of existing).
    2. Zero/empty score values are skipped (per spec).
    3. Soft-deleted rounds get restored if the same name is re-imported.
"""
import asyncio
import os
import sys
import time
import pytest
import requests
from datetime import datetime, timezone
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
    assert r.status_code == 200, r.text
    return s


def test_import_scores_syncs_rounds_into_bb_rounds():
    sync = MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
    # Unique test round names so we can clean up safely
    stamp = int(time.time())
    r1 = f"Iter47 A {stamp}"
    r2 = f"Iter47 B {stamp}"
    test_email = f"iter47_import_{stamp}@x.test"

    s = _login()
    payload = {"rows": [{
        "name": "Iter47 Test",
        "email": test_email,
        "phone": "9990047001",
        "job_role": "Tester",
        "status": "On hold",
        "schedule_date": "",
        "scores": [
            {"round_name": r1, "score": 8},
            {"round_name": r2, "score": 5},
            {"round_name": "Should Be Skipped", "score": 0},   # zero → skipped
            {"round_name": "Also Skipped", "score": None},     # empty → skipped
        ],
    }]}
    try:
        r = s.post(f"{_api()}/api/bb/import-scores/confirm", json=payload, timeout=20)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["success"] is True
        assert body["imported"] == 1
        # Both new rounds auto-registered; zero/empty skipped → NOT in bb_rounds
        registered = set(body.get("round_names") or [])
        assert r1 in registered and r2 in registered
        assert "Should Be Skipped" not in registered
        assert "Also Skipped" not in registered

        # bb_rounds persisted both
        r1_doc = sync.bb_rounds.find_one({"name": r1})
        r2_doc = sync.bb_rounds.find_one({"name": r2})
        assert r1_doc and r1_doc.get("active") is True and r1_doc.get("source") == "imported"
        assert r2_doc and r2_doc.get("active") is True

        # bb_applicant_updates captured non-zero scores only
        upd = sync.bb_applicant_updates.find_one({"email": test_email})
        assert upd is not None
        round_names_stored = {s["round_name"] for s in upd.get("scores", [])}
        assert round_names_stored == {r1, r2}

        # ---- Re-import the SAME rounds → no duplicates in bb_rounds ----
        r = s.post(f"{_api()}/api/bb/import-scores/confirm", json=payload, timeout=20)
        assert r.status_code == 200
        body2 = r.json()
        # Already registered → rounds_registered should be 0 the second time
        assert body2["rounds_registered"] == 0
        assert sync.bb_rounds.count_documents({"name": r1}) == 1

        # ---- Soft-delete then re-import → should reactivate ----
        sync.bb_rounds.update_one({"name": r1}, {"$set": {"active": False}})
        r = s.post(f"{_api()}/api/bb/import-scores/confirm", json=payload, timeout=20)
        r1_doc_after = sync.bb_rounds.find_one({"name": r1})
        assert r1_doc_after.get("active") is True
    finally:
        # Cleanup test artefacts
        sync.bb_rounds.delete_many({"name": {"$in": [r1, r2]}})
        sync.bb_applicant_updates.delete_many({"email": test_email})


def test_notify_missed_reminder_uses_5_params():
    """Regression: WhatsApp 'Candidate FollowUp' campaign must now get 5
    template params ([name, role, date, time, schedule_link])."""
    import inspect
    from messaging import notify_missed_reminder
    src = inspect.getsource(notify_missed_reminder)
    # Quick structural assertion — the 5-param call shape is present.
    assert '"Candidate FollowUp"' in src
    assert 'schedule_link' in src
    # Both the schedule_link build + the send_whatsapp call must reference it
    assert src.count("schedule_link") >= 2
