"""Iter48 — Score Import bug fixes + append-only merge + score sheet sync.

Tests:
    1. CSV with UTF-8 BOM (Excel default) parses successfully.
    2. CSV with case-mismatched headers ("name" instead of "Name") parses.
    3. Import preview returns the correct round_columns + parsed rows.
    4. Import confirm APPENDS new round scores to existing applicants
       without overwriting their previous (round, score) entries.
    5. Score sheet upload appends into bb_applicant_updates.scores[] AND
       auto-registers the round into bb_rounds.
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


def _csv_with_bom(headers, rows):
    """Build a CSV byte payload with a UTF-8 BOM, like Excel's "Save as CSV"."""
    out = "\ufeff" + ",".join(headers) + "\n"
    for r in rows:
        out += ",".join("" if v is None else str(v) for v in r) + "\n"
    return out.encode("utf-8")


def test_import_preview_handles_utf8_bom():
    """Root cause of past import failure — Excel CSVs add \\ufeff to the first
    header. The parser must strip it; otherwise 'Name' header validation fails."""
    s = _login()
    headers = ["Name", "Schedule Date", "College", "Degree", "Course",
               "Year of Graduation", "Email", "Phone", "Job Role", "Status",
               "Round Alpha", "Round Beta"]
    stamp = int(time.time())
    em = f"iter48_bom_{stamp}@x.test"
    rows = [["BOMTest", "2026-05-01", "ABC College", "B.Tech", "CSE",
             "2024", em, "9990048001", "Engineer", "On hold", "8", "9"]]
    csv_bytes = _csv_with_bom(headers, rows)

    r = s.post(f"{_api()}/api/bb/import-scores/preview",
               files={"file": ("with_bom.csv", csv_bytes, "text/csv")},
               timeout=15)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["total"] == 1
    assert body["rows"][0]["email"] == em
    assert sorted(body["round_columns"]) == ["Round Alpha", "Round Beta"]
    assert {s["round_name"] for s in body["rows"][0]["scores"]} == {"Round Alpha", "Round Beta"}


def test_import_preview_case_insensitive_headers():
    """User-edited file with lowercase headers must still validate."""
    s = _login()
    headers = ["name", "schedule date", "college", "degree", "course",
               "year of graduation", "email", "phone", "job role", "status",
               "Round X"]
    stamp = int(time.time())
    em = f"iter48_caseins_{stamp}@x.test"
    rows = [["LCTest", "", "", "", "", "", em, "9990048002", "", "", "7"]]
    csv = ",".join(headers) + "\n" + ",".join(rows[0]) + "\n"
    r = s.post(f"{_api()}/api/bb/import-scores/preview",
               files={"file": ("lowercase.csv", csv.encode(), "text/csv")},
               timeout=15)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["total"] == 1
    assert body["rows"][0]["email"] == em
    assert body["rows"][0]["scores"] == [{"round_name": "Round X", "score": 7.0}]


def test_import_confirm_appends_new_rounds_preserves_existing():
    """Import must NOT overwrite existing scores. If applicant already has
    `BP=8`, importing `BP=10` keeps the original `8` and adds nothing for BP.
    But importing a NEW round `Mensa=6` must append it.
    """
    sync = MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
    stamp = int(time.time())
    em = f"iter48_merge_{stamp}@x.test"
    # Pre-seed bb_applicant_updates with one round
    sync.bb_applicant_updates.insert_one({
        "email": em, "phone": "9990048003", "name": "MergeTest",
        "status": "Shortlisted",
        "scores": [{"round_name": "BP", "score": 8}],
        "updated_at": datetime.now(timezone.utc).isoformat(),
    })
    test_round = f"Iter48Mensa_{stamp}"
    try:
        s = _login()
        r = s.post(f"{_api()}/api/bb/import-scores/confirm",
                   json={"rows": [{
                       "name": "MergeTest", "email": em, "phone": "9990048003",
                       "job_role": "Eng", "status": "On hold", "schedule_date": "",
                       "scores": [
                           {"round_name": "BP", "score": 99},      # try to overwrite
                           {"round_name": test_round, "score": 6}, # new round → append
                       ],
                   }]}, timeout=15)
        assert r.status_code == 200, r.text
        doc = sync.bb_applicant_updates.find_one({"email": em})
        scores = doc.get("scores") or []
        rounds_map = {sc["round_name"]: sc["score"] for sc in scores}
        assert rounds_map["BP"] == 8, f"Existing BP should be preserved, got {rounds_map['BP']}"
        assert rounds_map[test_round] == 6
        # No duplicate BP entries
        assert sum(1 for sc in scores if sc["round_name"] == "BP") == 1
        # Status preserved (existing 'Shortlisted' wins over imported 'On hold')
        assert doc.get("status") == "Shortlisted"
        # Round was registered into bb_rounds
        assert sync.bb_rounds.find_one({"name": test_round})
    finally:
        sync.bb_applicant_updates.delete_many({"email": em})
        sync.bb_rounds.delete_many({"name": test_round})


def test_score_sheet_upload_syncs_into_applicant_updates_and_rounds():
    """Uploading a score sheet must (a) insert into score_sheet, (b) append
    the (round, score) into bb_applicant_updates.scores[], and (c) register
    the round into bb_rounds — without overwriting an existing score."""
    sync = MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
    stamp = int(time.time())
    em = f"iter48_sheet_{stamp}@x.test"
    test_round = f"Iter48Sheet_{stamp}"
    headers = ["name", "email", "phone", "score", "round_name"]
    csv_bytes = (",".join(headers) + "\n" +
                 f"SheetTest,{em},9990048004,15,{test_round}\n").encode()
    s = _login()
    try:
        r = s.post(f"{_api()}/api/upload/scoresheet",
                   files={"file": ("score.csv", csv_bytes, "text/csv")},
                   timeout=20)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["success"] is True
        # bb_applicant_updates picked up the score
        upd = sync.bb_applicant_updates.find_one({"email": em})
        assert upd is not None
        assert any(sc.get("round_name") == test_round and sc.get("score") == 15
                   for sc in upd.get("scores", []))
        # bb_rounds got the new round registered
        assert sync.bb_rounds.find_one({"name": test_round})
        # score_sheet got the row
        assert sync.score_sheet.find_one({"email": em, "round_name": test_round})
    finally:
        sync.bb_applicant_updates.delete_many({"email": em})
        sync.bb_rounds.delete_many({"name": test_round})
        sync.score_sheet.delete_many({"email": em})
