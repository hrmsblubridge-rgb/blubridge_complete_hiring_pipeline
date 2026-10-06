"""Iter45 — Exact Score Mapping with Round Detection.

Tests the score-matching helpers + new endpoint:
    1. _norm_round canonicalises aliases ('Technical 1' → 'Round 1', 'Accounts1'
       → 'Accounts 1').
    2. _build_round_wise_scores groups by round + picks latest by default.
    3. /api/bb/candidate-score-summary returns the structured Iter45 payload.
    4. /api/bb/attended-for-scores includes round_wise_scores + latest_*.
    5. _detect_score_phone_conflict flags same-phone-different-email.
"""
import asyncio
import os
import sys
import time
from datetime import datetime, timezone, timedelta

import pytest
import requests
from dotenv import load_dotenv
from pymongo import MongoClient

load_dotenv("/app/backend/.env")
sys.path.insert(0, "/app/backend")

import bb_modules
from bb_modules import (
    _norm_round, _build_round_wise_scores,
    _detect_score_phone_conflict, init_bb,
)
from server import _build_college_rank_lookup, _classify_college


def _run(coro_fn):
    """Each test gets a fresh event loop AND a fresh motor client bound to
    that loop. Otherwise pytest's per-test loop teardown closes the motor
    client we share across tests."""
    from motor.motor_asyncio import AsyncIOMotorClient
    loop = asyncio.new_event_loop()
    try:
        cli = AsyncIOMotorClient(os.environ["MONGO_URL"], io_loop=loop)
        fresh_db = cli[os.environ["DB_NAME"]]
        init_bb(fresh_db, None, _build_college_rank_lookup, _classify_college)
        return loop.run_until_complete(coro_fn())
    finally:
        try:
            cli.close()
        except Exception:
            pass
        loop.close()


# ---------- canonicalisation ----------

def test_round_canonicalisation():
    assert _norm_round("Technical 1") == "Round 1"
    assert _norm_round("technical1") == "Round 1"
    assert _norm_round("Round 2") == "Round 2"
    assert _norm_round("HR Interview") == "HR Round"
    assert _norm_round("Final Discussion") == "Final Round"
    # Unknown round names pass through (whitespace-collapsed)
    assert _norm_round("BP") == "BP"
    assert _norm_round("  C++ ") == "C++"
    # Spacing normalisation
    assert _norm_round("Accounts1") == "Accounts 1"
    assert _norm_round("Accounts 2") == "Accounts 2"
    assert _norm_round(None) == ""
    assert _norm_round("") == ""


# ---------- resolver ----------

def test_build_round_wise_scores_picks_latest():
    """Seed 3 BP entries for one candidate at different timestamps; resolver
    must return the most-recent one and lift it to latest_round."""
    test_email = f"score_iter45_{int(time.time())}@example.test"
    test_phone = "9990012345"
    sync = MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
    base = datetime.now(timezone.utc)
    seeds = [
        {"email": test_email, "phone": test_phone, "name": "T",
         "round_name": "BP", "score": 5,
         "created_at": (base - timedelta(days=2)).isoformat()},
        {"email": test_email, "phone": test_phone, "name": "T",
         "round_name": "BP", "score": 9,
         "created_at": (base - timedelta(days=1)).isoformat()},
        {"email": test_email, "phone": test_phone, "name": "T",
         "round_name": "Mensa", "score": 7,
         "created_at": base.isoformat()},
    ]
    sync.score_sheet.insert_many([dict(s) for s in seeds])
    try:
        rws = _run(lambda: _build_round_wise_scores(test_email, test_phone))
        assert "BP" in rws["round_wise_scores"]
        assert "Mensa" in rws["round_wise_scores"]
        assert rws["round_wise_scores"]["BP"]["score"] == 9
        assert rws["latest_round"] == "Mensa"
        assert rws["latest_score"] == 7
        assert rws["total_score"] == 16
        assert sorted(rws["rounds"]) == ["BP", "Mensa"]
    finally:
        sync.score_sheet.delete_many({"email": test_email})


def test_build_round_wise_scores_pick_highest():
    test_email = f"score_high_{int(time.time())}@example.test"
    sync = MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
    base = datetime.now(timezone.utc)
    sync.score_sheet.insert_many([
        {"email": test_email, "phone": "9990099001", "name": "T",
         "round_name": "Round 1", "score": 4,
         "created_at": base.isoformat()},
        {"email": test_email, "phone": "9990099001", "name": "T",
         "round_name": "Technical 1", "score": 12,
         "created_at": (base - timedelta(days=1)).isoformat()},
    ])
    try:
        rws = _run(lambda: _build_round_wise_scores(test_email, "9990099001", pick="highest"))
        # Both records canonicalise to "Round 1"; highest is 12
        assert rws["round_wise_scores"]["Round 1"]["score"] == 12
    finally:
        sync.score_sheet.delete_many({"email": test_email})


def test_resolver_empty_for_unknown_candidate():
    rws = _run(lambda: _build_round_wise_scores("nope-iter45@nowhere.test", "0000000000"))
    assert rws["round_wise_scores"] == {}
    assert rws["latest_round"] is None


# ---------- conflict detection ----------

def test_phone_conflict_detection():
    sync = MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
    em_a = f"conflict_a_{int(time.time())}@x.test"
    em_b = f"conflict_b_{int(time.time())}@x.test"
    ph = "9990077777"
    sync.score_sheet.insert_one({"email": em_a, "phone": ph, "name": "A",
                                  "round_name": "BP", "score": 1,
                                  "created_at": datetime.now(timezone.utc).isoformat()})
    try:
        conflict = _run(lambda: _detect_score_phone_conflict(em_b, ph))
        assert conflict and "different email" in conflict
        assert _run(lambda: _detect_score_phone_conflict(em_a, ph)) is None
    finally:
        sync.score_sheet.delete_many({"email": em_a})


# ---------- end-to-end endpoint ----------

def test_candidate_score_summary_endpoint():
    api_url = os.environ.get("REACT_APP_BACKEND_URL_INTERNAL", "http://localhost:8001")
    s = requests.Session()
    s.post(f"{api_url}/api/login",
           json={"username": "Admin User", "password": "Admin User"}, timeout=10)
    r = s.get(f"{api_url}/api/bb/candidate-score-summary",
              params={"email": "rajlearn06@gmail.com"}, timeout=15)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body.get("email") == "rajlearn06@gmail.com"
    assert isinstance(body.get("round_wise_scores"), dict)
    # rajlearn06 has many rounds in score_sheet — should pick at least 1
    assert body["round_wise_scores"], body
    assert body.get("latest_round")
    assert body.get("latest_score") is not None
    assert body.get("total_score", 0) > 0
    # Accounts1 / Accounts 1 must merge into a single canonical bucket
    rounds = body["round_wise_scores"]
    assert not ("Accounts1" in rounds and "Accounts 1" in rounds), \
        "Accounts1 and 'Accounts 1' should merge into one canonical bucket"


def test_attended_for_scores_includes_round_wise():
    api_url = os.environ.get("REACT_APP_BACKEND_URL_INTERNAL", "http://localhost:8001")
    s = requests.Session()
    s.post(f"{api_url}/api/login",
           json={"username": "Admin User", "password": "Admin User"}, timeout=10)
    r = s.get(f"{api_url}/api/bb/attended-for-scores",
              params={"limit": 5}, timeout=20)
    assert r.status_code == 200, r.text
    body = r.json()
    for row in body.get("data", []):
        # New iter45 fields must be present (may be None/empty for records without scores)
        assert "round_wise_scores" in row
        assert "latest_round" in row
        assert "latest_score" in row
        assert "total_score" in row
        # Backward compat: legacy `scores` array still present
        assert "scores" in row
