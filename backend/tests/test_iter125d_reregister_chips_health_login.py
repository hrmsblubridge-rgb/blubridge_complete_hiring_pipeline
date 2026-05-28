"""iter125d regression — Three production fixes:

ISSUE 1: Re-registration round-score reset didn't fully clear stale
  identity in `bb_applicant_updates`. The reset cleared `scores: []` but
  left `name`, `job_role`, `isImported`, `import_batch_id`,
  `imported_at`, `schedule_date` intact. A subsequent Update-Scores
  upsert found the doc by email, saw the stale identity + the previous
  cycle's rounds, and re-added them via the "preserve existing rounds"
  merge — user observed "old round names/scores persisting".
  Fix: centralized `_clear_applicant_round_state` helper that
    * resets `scores: []`, `status`, `result_status`
    * overwrites identity (`name`, `phone`, `job_role`) to the NEW values
    * `$unset`s `isImported`, `import_batch_id`, `imported_at`,
      `schedule_date`, plus any DYNAMIC round-prefixed field discovered
      from `bb_rounds` + heuristic scan of the doc keys
  Helper used by ALL three re-register paths (tester direct register,
  non-tester direct register, college-drive flow).

ISSUE 2: Interview Schedule Reports chips for new roles hidden behind
  "SHOW ALL". User saw role in dropdown + records existed, but chip
  button was missing because frontend defaulted to top-5 only and the
  "All Records" handler didn't auto-expand. Fix: All Records and Reset
  now both set `showAllRoles=true`.

ISSUE 3: Health endpoint `/health` (GET + HEAD) added immediately before
  `@app.on_event("shutdown")`. Lightweight — no DB, no auth, no logging.

ISSUE 4: "Default credentials: Admin User / Admin User" helper text
  removed from Login page UI.
"""
import asyncio
import inspect
import os
import sys

from dotenv import load_dotenv

load_dotenv("/app/backend/.env")
sys.path.insert(0, "/app/backend")

from motor.motor_asyncio import AsyncIOMotorClient  # noqa: E402
import server  # noqa: E402
import bb_modules  # noqa: E402


def _fresh_db():
    client = AsyncIOMotorClient(os.environ["MONGO_URL"])
    return client[os.environ["DB_NAME"]], client


# ─────────────────── ISSUE 1: re-registration round reset ───────────────────

def test_clear_applicant_round_state_helper_exists():
    """Centralized helper must exist and be wired into all three paths."""
    assert hasattr(bb_modules, "_clear_applicant_round_state")
    # All three paths use it
    src = inspect.getsource(bb_modules)
    # tester direct path
    register_src = inspect.getsource(bb_modules.register_applicant)
    assert "_clear_applicant_round_state" in register_src
    # college-drive path
    college_src = inspect.getsource(bb_modules.register_college_applicant)
    assert "_clear_applicant_round_state" in college_src


def test_re_registration_clears_scores_and_stale_identity():
    """Functional simulation: seed `bb_applicant_updates` with stale
    Round 1/2 scores + old identity, run helper, verify both scores
    cleared AND identity overwritten AND import flags removed."""

    async def _run():
        db, client = _fresh_db()
        original_db = bb_modules._db
        bb_modules._db = db
        try:
            test_email = "iter125d_reset@example.com"
            await db.bb_applicant_updates.delete_many({"email": test_email})
            await db.bb_applicant_updates.insert_one({
                "email": test_email,
                "name": "OLD NAME — Stale Identity",
                "phone": "9000125901",
                "job_role": "OLD ROLE — From Previous Cycle",
                "scores": [
                    {"round_name": "Round 1", "score": 15.0},
                    {"round_name": "Coding", "score": 22.5},
                ],
                "status": "Rejected",
                "result_status": "Rejected",
                "isImported": True,
                "import_batch_id": "OLD-BATCH-XYZ",
                "imported_at": "2026-01-01T00:00:00+00:00",
                "schedule_date": "2026-01-01",
                "rejection_sent": True,
                # custom dynamic round field
                "Coding_score": 22.5,
                "Round_1_status": "fail",
            })

            res = await bb_modules._clear_applicant_round_state(
                {"email": test_email},
                new_identity={
                    "name": "NEW NAME — Fresh Re-registration",
                    "phone": "9000125902",
                    "job_role": "NEW ROLE — Fresh Cycle",
                },
            )
            assert res["matched"] >= 1
            assert res["modified"] >= 1
            # At least the dynamic Coding_score / Round_1_status keys were unset
            assert "Coding_score" in res["unset_fields"] or "Round_1_status" in res["unset_fields"]

            doc = await db.bb_applicant_updates.find_one({"email": test_email})
            # Scores wiped
            assert doc["scores"] == []
            # Status / result_status cleared
            assert doc["status"] == ""
            assert doc["result_status"] == ""
            # Identity overwritten with NEW values
            assert doc["name"] == "NEW NAME — Fresh Re-registration"
            assert doc["phone"] == "9000125902"
            assert doc["job_role"] == "NEW ROLE — Fresh Cycle"
            # Stale import flags removed
            assert "isImported" not in doc
            assert "import_batch_id" not in doc
            assert "imported_at" not in doc
            assert "schedule_date" not in doc
            # Stale dynamic round fields removed
            assert "Coding_score" not in doc
            assert "Round_1_status" not in doc
            # Rejection flag reset
            assert doc["rejection_sent"] is False
            # Reset timestamp marker stamped
            assert "scores_reset_at" in doc

            await db.bb_applicant_updates.delete_many({"email": test_email})
        finally:
            bb_modules._db = original_db
            client.close()

    asyncio.run(_run())


def test_dynamic_round_field_discovery_from_bb_rounds():
    """Helper must build unset list from `bb_rounds` (no hardcoding)."""

    async def _run():
        db, client = _fresh_db()
        original_db = bb_modules._db
        bb_modules._db = db
        try:
            test_email = "iter125d_dyn@example.com"
            await db.bb_applicant_updates.delete_many({"email": test_email})
            # Drop a candidate doc with a field that bb_rounds derives a name for
            sample_round = await db.bb_rounds.find_one({}) or {"name": "Round 1"}
            base = "".join(c if c.isalnum() else "_" for c in str(sample_round.get("name") or "Round 1")).strip("_")
            field_name = f"{base}_score"
            await db.bb_applicant_updates.insert_one({
                "email": test_email,
                "name": "iter125d-dyn",
                "phone": "9000125903",
                "scores": [],
                field_name: 42.0,
            })
            res = await bb_modules._clear_applicant_round_state(
                {"email": test_email},
                new_identity={"name": "new", "phone": "9000125903", "job_role": "Test"},
            )
            doc = await db.bb_applicant_updates.find_one({"email": test_email})
            # The dynamic field must be unset (caught either by bb_rounds
            # synthesis or by the heuristic doc-key scan).
            assert field_name not in doc, (
                f"Dynamic round field {field_name!r} should be removed; "
                f"unset_fields={res['unset_fields']}"
            )
            await db.bb_applicant_updates.delete_many({"email": test_email})
        finally:
            bb_modules._db = original_db
            client.close()

    asyncio.run(_run())


# ─────────────────── ISSUE 2: chip buttons auto-expand on All Records ───────────────────

def test_all_records_and_reset_auto_expand_show_all_roles():
    """Frontend guard: handleAllRecords AND resetFilters must call
    setShowAllRoles(true) so every role with scheduled candidates
    surfaces as a chip button. Top-5 cutoff was production-reported
    as "chips not generated for new roles"."""
    path = "/app/frontend/src/pages/InterviewReports.js"
    with open(path, "r") as f:
        src = f.read()
    # Both handlers must explicitly expand chip view
    handle_idx = src.find("handleAllRecords =")
    reset_idx = src.find("resetFilters =")
    assert handle_idx > 0 and reset_idx > 0
    # Grab a window after each handler definition
    win_all = src[handle_idx:handle_idx + 300]
    win_rst = src[reset_idx:reset_idx + 400]
    assert "setShowAllRoles(true)" in win_all, (
        "handleAllRecords must auto-expand chips with setShowAllRoles(true)"
    )
    assert "setShowAllRoles(true)" in win_rst, (
        "resetFilters must auto-expand chips with setShowAllRoles(true)"
    )


# ─────────────────── ISSUE 3: /health endpoint ───────────────────

def test_health_endpoint_route_exists():
    """Source-code guard: /health endpoint mounted directly on `app`
    with both GET and HEAD methods, placed immediately before the
    shutdown event handler."""
    src = inspect.getsource(server)
    assert '@app.api_route("/health"' in src
    assert '"GET"' in src and '"HEAD"' in src
    # Must be placed BEFORE the shutdown handler
    h_idx = src.find('@app.api_route("/health"')
    s_idx = src.find('@app.on_event("shutdown")')
    assert h_idx > 0 and s_idx > 0 and h_idx < s_idx, (
        "/health endpoint must be defined BEFORE @app.on_event('shutdown')"
    )
    # No DB query, no auth, no logging inside the handler
    handler_window = src[h_idx:s_idx]
    assert "db." not in handler_window
    assert "Depends" not in handler_window
    assert "logger." not in handler_window


# ─────────────────── ISSUE 4: Login default-credentials text removed ───────────────────

def test_login_page_has_no_default_credentials_text():
    path = "/app/frontend/src/pages/Login.js"
    with open(path, "r") as f:
        src = f.read()
    assert "Default credentials" not in src
    assert "Admin User / Admin User" not in src
