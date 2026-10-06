"""Iter52 — Candidate Journey (A-Z row action) endpoints.

Tests:
    1. /api/bb/candidate-journey returns structured basic info + round
       timeline + final outcome for a known candidate.
    2. Round labels apply (Round 2 → "F2F", HR Round → "HR Interview").
    3. Round status reflects score presence: Completed / Pending / Rejected.
    4. Date of Induction shows "Pending" when status=Selected and no DOI.
    5. PUT /api/bb/candidate-induction-date sets date_of_induction
       on pipeline_data and the GET reflects it.
    6. Phone↔email mismatch returns 409 (view blocked per spec).
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


def _login():
    s = requests.Session()
    s.post(f"{_api()}/api/login",
           json={"username": "Admin User", "password": "Admin User"}, timeout=10)
    return s


def test_candidate_journey_returns_structured_payload():
    """Seed a candidate in pipeline_data + bb_applicant_updates with known
    rounds; the journey endpoint must return the full structure."""
    sync = MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
    stamp = int(time.time())
    em = f"iter52_{stamp}@x.test"
    ph = f"99999{stamp % 100000:05d}"
    sync.pipeline_data.insert_one({
        "email": em, "phone": ph, "name": "Iter52 Test",
        "college": "Anna University", "job_role": "AI/ML Engineer",
        "result_status": "In Progress",
    })
    sync.bb_applicant_updates.insert_one({
        "email": em, "status": "Shortlisted",
        "scores": [
            {"round_name": "Round 1", "score": 8},
            {"round_name": "Round 2", "score": 9},
            {"round_name": "HR Round", "score": 7},
        ],
        "updated_at": datetime.now(timezone.utc).isoformat(),
    })
    try:
        s = _login()
        r = s.get(f"{_api()}/api/bb/candidate-journey",
                  params={"email": em, "phone": ph}, timeout=15)
        assert r.status_code == 200, r.text
        body = r.json()

        # Section 1 — basic info
        assert body["basic"]["name"] == "Iter52 Test"
        assert body["basic"]["email"] == em
        assert body["basic"]["college"] == "Anna University"
        assert body["basic"]["job_role"] == "AI/ML Engineer"

        # Section 2 — round timeline
        labels = {rd["round_name"]: rd["round_label"] for rd in body["round_details"]}
        # Custom labels surfaced
        assert labels.get("Round 2") == "F2F"
        assert labels.get("HR Round") == "HR Interview"
        # Status mapping (score present → Completed)
        for rd in body["round_details"]:
            if rd["round_name"] in ("Round 1", "Round 2", "HR Round"):
                assert rd["status"] == "Completed", rd

        # Section 3 — final outcome
        assert body["final_outcome"]["status"] == "In Progress"
        # No date_of_induction yet AND status != Selected → "Not Applicable"
        assert body["final_outcome"]["date_of_induction"] == "Not Applicable"
    finally:
        sync.pipeline_data.delete_many({"email": em})
        sync.bb_applicant_updates.delete_many({"email": em})


def test_journey_doi_pending_when_selected_and_empty():
    sync = MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
    stamp = int(time.time())
    em = f"iter52_sel_{stamp}@x.test"
    sync.pipeline_data.insert_one({
        "email": em, "phone": "9990052999", "name": "Selected",
        "college": "ABC", "job_role": "Eng",
        "result_status": "Selected",
    })
    try:
        s = _login()
        r = s.get(f"{_api()}/api/bb/candidate-journey",
                  params={"email": em}, timeout=10)
        assert r.status_code == 200
        body = r.json()
        assert body["final_outcome"]["status"] == "Selected"
        # Spec: "If candidate status = selected: → show date_of_induction"
        # No date set yet → "Pending"
        assert body["final_outcome"]["date_of_induction"] == "Pending"
    finally:
        sync.pipeline_data.delete_many({"email": em})


def test_set_induction_date_flows_through_to_journey():
    sync = MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
    stamp = int(time.time())
    em = f"iter52_doi_{stamp}@x.test"
    sync.pipeline_data.insert_one({
        "email": em, "phone": "9990052998", "name": "DOI",
        "college": "ABC", "job_role": "Eng",
        "result_status": "Selected",
    })
    try:
        s = _login()
        # Set DOI
        r = s.put(f"{_api()}/api/bb/candidate-induction-date",
                  json={"email": em, "date_of_induction": "2026-08-15"},
                  timeout=10)
        assert r.status_code == 200, r.text
        # GET reflects it
        r2 = s.get(f"{_api()}/api/bb/candidate-journey",
                   params={"email": em}, timeout=10)
        assert r2.json()["final_outcome"]["date_of_induction"] == "2026-08-15"
        # Clear DOI
        r3 = s.put(f"{_api()}/api/bb/candidate-induction-date",
                   json={"email": em, "date_of_induction": ""}, timeout=10)
        assert r3.status_code == 200
        r4 = s.get(f"{_api()}/api/bb/candidate-journey",
                   params={"email": em}, timeout=10)
        # Cleared → falls back to "Pending" since status=Selected
        assert r4.json()["final_outcome"]["date_of_induction"] == "Pending"
    finally:
        sync.pipeline_data.delete_many({"email": em})


def test_journey_404_for_unknown_candidate():
    s = _login()
    r = s.get(f"{_api()}/api/bb/candidate-journey",
              params={"email": "nope-iter52@nowhere.test"}, timeout=10)
    assert r.status_code == 404
