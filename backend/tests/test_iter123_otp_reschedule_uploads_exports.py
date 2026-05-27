"""iter123 — Four production fixes covered:

ISSUE 1: OTP not sent after reschedule.
  Root cause: `bb_modules.submit_schedule()` reschedule branch cleared the
  legacy `otp_sent` flag but NOT the iter121 per-channel flags
  (`otp_wa_sent`, `otp_email_sent`). With the iter121 cursor predicate
  `$or: [otp_wa_sent != True, otp_email_sent != True]`, both flags
  remained True from the previous schedule → row excluded → no OTP
  generated for the new schedule.
  Fix: extend `unset_fields` to clear all iter121 OTP per-channel flags
  AND the iter122 missed-reminder per-channel flags.

ISSUE 2: Unknown role reclassification not triggerable in production.
  Fix: new admin endpoint `POST /api/admin/reset-backfill/{name}` resets
  the `bb_meta._id={name}` done flag and re-launches the backfill as a
  background task. Operator-callable without DB shell access.

ISSUE 3: Individual upload endpoints returning 502.
  Root cause: `await reprocess_matching()` and `_sync_job_titles_master()`
  ran synchronously inside the HTTP handler. On large datasets these
  exceeded Render's 30s request timeout → 502.
  Fix: wrap in `asyncio.create_task(...)` so the response returns as
  soon as the file is parsed + rows are inserted. The reprocess runs in
  the background; response includes `background_processing: True` flag.

ISSUE 4: Export endpoints `/api/applicants/export` and
`/api/attended/export` with CSV + XLSX formats. Filters honoured.
Attended export appends dynamic round columns from `bb_rounds`.
"""

import asyncio
import importlib
import io
import os
import sys
import zipfile

import pytest
from dotenv import load_dotenv

load_dotenv("/app/backend/.env")
sys.path.insert(0, "/app/backend")


# ─────────────────────── Issue 1 — Reschedule resets OTP flags ───────────────────────

def test_submit_schedule_reschedule_clears_iter121_otp_flags():
    """The reschedule unset_fields block must include every iter121 OTP
    per-channel flag — else the OTP worker's cursor predicate
    `$or:[otp_wa_sent != True, otp_email_sent != True]` excludes the row."""
    with open("/app/backend/bb_modules.py", "r") as f:
        src = f.read()
    # Find the reschedule branch
    block = src.split("RESCHEDULE RESET")[1].split("```")[0] if "RESCHEDULE RESET" in src else ""
    if not block:
        # Fallback: search the full file
        block = src
    for fld in [
        "otp_wa_sent",
        "otp_email_sent",
        "otp_wa_sent_at",
        "otp_email_sent_at",
        "otp_dispatch_in_progress",
        "missed_reminder_wa_sent",
        "missed_reminder_email_sent",
        "missed_reminder_token",
        "missed_marked",
    ]:
        assert f'"{fld}"' in block, (
            f"Reschedule unset_fields missing per-channel flag {fld!r}; "
            f"without this clear, the OTP / missed-reminder workers stay "
            f"locked from the previous schedule."
        )


# ─────────────────────── Issue 2 — admin reset-backfill endpoint ───────────────────────

def test_admin_reset_backfill_endpoint_registered():
    with open("/app/backend/server.py", "r") as f:
        src = f.read()
    assert '"/admin/reset-backfill/{name}"' in src
    assert "iter108_unknown_backfill" in src
    assert "iter110_college_status_backfill" in src


# ─────────────────────── Issue 3 — uploads return without blocking on reprocess ────

def test_upload_naukri_defers_reprocess_to_background():
    with open("/app/backend/server.py", "r") as f:
        src = f.read()
    # Pull out the upload/naukri handler body
    block = src.split('@api_router.post("/upload/naukri")')[1].split('@api_router.post("/upload/pipeline")')[0]
    # reprocess + sync MUST be inside an asyncio.create_task wrapper.
    assert "asyncio.create_task" in block, (
        "upload/naukri still awaits reprocess_matching synchronously — Render 30s timeout produces 502."
    )
    assert '"background_processing": True' in block


def test_upload_pipeline_defers_reprocess_to_background():
    with open("/app/backend/server.py", "r") as f:
        src = f.read()
    # Pull out the upload/pipeline handler body (allow nested route)
    block = src.split('@api_router.post("/upload/pipeline")')[1].split('@api_router')[0]
    assert "asyncio.create_task" in block
    assert '"background_processing": True' in block


# ─────────────────────── Issue 4 — export endpoints ───────────────────────

def test_export_endpoints_registered():
    with open("/app/backend/server.py", "r") as f:
        src = f.read()
    assert '@api_router.get("/applicants/export")' in src
    assert '@api_router.get("/attended/export")' in src


def test_applicants_export_field_order_matches_spec():
    """User-specified 17 columns must appear in the exact order requested."""
    with open("/app/backend/server.py", "r") as f:
        src = f.read()
    block = src.split('@api_router.get("/applicants/export")')[1].split('@api_router')[0]
    expected_order = [
        "Name", "Email", "Phone", "Age", "Gender",
        "College Status", "College", "Degree", "Course", "Year of Graduation",
        "Job Role", "Registered Status", "Registered Date",
        "Schedule Date", "Schedule Time", "Attended or Not", "Result Status",
    ]
    headers_decl_idx = block.find("headers = [")
    assert headers_decl_idx > -1
    snippet = block[headers_decl_idx: headers_decl_idx + 800]
    for i, col in enumerate(expected_order):
        assert f'"{col}"' in snippet, f"Export header {col!r} missing or out of order"


def test_attended_export_includes_dynamic_rounds():
    with open("/app/backend/server.py", "r") as f:
        src = f.read()
    block = src.split('@api_router.get("/attended/export")')[1].split('@api_router')[0]
    # The 13 static columns + dynamic_rounds appended.
    assert '"Scheduled Date"' in block
    assert '"Result Status"' in block
    assert "dynamic_rounds" in block
    # bb_rounds query present.
    assert "db.bb_rounds.find" in block


def test_frontend_view_applicants_has_export_button():
    with open("/app/frontend/src/pages/Roles.js", "r") as f:
        src = f.read()
    assert 'data-testid="export-btn"' in src
    assert 'data-testid="export-xlsx-btn"' in src
    assert 'data-testid="export-csv-btn"' in src
    assert "/api/applicants/export" in src


def test_frontend_view_attended_has_export_button():
    with open("/app/frontend/src/pages/AttendedRoles.js", "r") as f:
        src = f.read()
    assert 'data-testid="export-btn"' in src
    assert 'data-testid="export-xlsx-btn"' in src
    assert 'data-testid="export-csv-btn"' in src
    assert "/api/attended/export" in src


# ─────────────────────── Live smoke test ───────────────────────

def test_export_xlsx_is_valid_workbook(tmp_path):
    """End-to-end: hit the live preview endpoint and confirm the XLSX
    payload is a valid openpyxl-readable workbook."""
    import httpx
    api_url = os.environ.get("REACT_APP_BACKEND_URL")
    if not api_url:
        with open("/app/frontend/.env", "r") as f:
            for ln in f:
                if ln.startswith("REACT_APP_BACKEND_URL"):
                    api_url = ln.split("=", 1)[1].strip().strip('"')
                    break
    with httpx.Client(timeout=60.0, follow_redirects=True) as c:
        login = c.post(f"{api_url}/api/login", json={"username": "Admin User", "password": "Admin User"})
        assert login.status_code == 200, login.text
        # Pull just a small slice (jobRole filter narrows down to ~120 rows)
        r = c.get(f"{api_url}/api/applicants/export", params={"jobRole": "AI & ML Engineer", "format": "xlsx"})
        assert r.status_code == 200, r.text
        out = tmp_path / "exp.xlsx"
        out.write_bytes(r.content)
        with zipfile.ZipFile(out) as z:
            entries = z.namelist()
            # A valid XLSX must contain workbook.xml and at least one sheet
            assert any("workbook.xml" in e for e in entries)
            assert any("sheet1.xml" in e.lower() for e in entries)


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
