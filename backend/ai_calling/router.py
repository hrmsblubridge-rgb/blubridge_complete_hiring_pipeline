"""AI Calling API (/api/ai-calling). Admin-only except nothing public in Phase 2."""
import io
import logging
import re
from typing import List, Optional

import pandas as pd
from bson import ObjectId
from fastapi import APIRouter, File, HTTPException, Query, Request, UploadFile
from fastapi.responses import StreamingResponse
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill
from pydantic import BaseModel

from . import bolna_client, gate
from .store import (
    COLUMNS, EDITABLE_SETTINGS, MODES, SETTINGS_ID, _state, db, get_settings,
    mask_phone, now_iso, serialize, validate_row,
)

_logger = logging.getLogger("ai_calling")
ai_router = APIRouter(prefix="/api/ai-calling", tags=["AI Calling"])
MAX_UPLOAD_BYTES = 2 * 1024 * 1024
MAX_UPLOAD_ROWS = 500


def init_ai_calling(database, auth_fn):
    _state["db"] = database
    _state["auth"] = auth_fn


async def ensure_ai_indexes():
    d = db()
    await d.ai_test_candidates.create_index("phone_e164", unique=True)
    await d.ai_call_jobs.create_index(
        [("mode", 1), ("batch_id", 1), ("test_candidate_id", 1), ("attempt", 1)], unique=True)
    await d.ai_call_jobs.create_index([("status", 1), ("created_at", 1)])
    await d.ai_calls.create_index("execution_id", unique=True, sparse=True)
    await d.ai_calls.create_index([("mode", 1), ("created_at", -1)])
    await get_settings()


async def _auth(request: Request) -> str:
    return await _state["auth"](request)


def _oid(v: str) -> ObjectId:
    if not ObjectId.is_valid(v):
        raise HTTPException(404, "Not found")
    return ObjectId(v)


async def _existing(coll, v: str) -> ObjectId:
    oid = _oid(v)
    if not await coll.find_one({"_id": oid}, {"_id": 1}):
        raise HTTPException(404, "Not found")
    return oid


# ---------------- summary / settings / mode ----------------

@ai_router.get("/summary")
async def summary(request: Request):
    await _auth(request)
    s = await get_settings()
    c = db().ai_test_candidates
    return {
        "mode": s["mode"], "mode_version": s["mode_version"], "emergency_stop": s["emergency_stop"],
        "server_calling_enabled": gate.server_calling_enabled(),
        "bolna_integration_approved": gate.BOLNA_INTEGRATION_APPROVED,
        "live_mode_locked": gate.LIVE_MODE_LOCKED,
        "test_candidates": await c.count_documents({}),
        "approved_candidates": await c.count_documents({"approved": True}),
        "opted_out": await c.count_documents({"opted_out": True}),
        "batches": await db().ai_test_batches.count_documents({}),
        "calls_total": await db().ai_calls.count_documents({}),
        "calls_testing": await db().ai_calls.count_documents({"mode": "testing"}),
        "calls_live": await db().ai_calls.count_documents({"mode": "live"}),
    }


@ai_router.get("/settings")
async def read_settings(request: Request):
    await _auth(request)
    s = await get_settings()
    return {**s, "server_calling_enabled": gate.server_calling_enabled(),
            "bolna_integration_approved": gate.BOLNA_INTEGRATION_APPROVED,
            "live_mode_locked": gate.LIVE_MODE_LOCKED, "bolna_config": bolna_client.config_status()}


class SettingsBody(BaseModel):
    daily_call_limit: Optional[int] = None
    max_concurrent_calls: Optional[int] = None
    call_window_start: Optional[str] = None
    call_window_end: Optional[str] = None
    default_company_name: Optional[str] = None
    default_office_address: Optional[str] = None


@ai_router.put("/settings")
async def update_settings(body: SettingsBody, request: Request):
    user = await _auth(request)
    upd = {k: v for k, v in body.model_dump().items() if v is not None and k in EDITABLE_SETTINGS}
    if "daily_call_limit" in upd and not (0 <= upd["daily_call_limit"] <= 200):
        raise HTTPException(400, "daily_call_limit must be 0–200")
    if "max_concurrent_calls" in upd and not (1 <= upd["max_concurrent_calls"] <= 5):
        raise HTTPException(400, "max_concurrent_calls must be 1–5")
    for k in ("call_window_start", "call_window_end"):
        if k in upd and not re.fullmatch(r"([01]\d|2[0-3]):[0-5]\d", upd[k]):
            raise HTTPException(400, f"{k} must be HH:MM")
    cur = await get_settings()
    if upd.get("call_window_start", cur["call_window_start"]) >= upd.get("call_window_end", cur["call_window_end"]):
        raise HTTPException(400, "call_window_start must be before call_window_end")
    await db().ai_call_settings.update_one({"_id": SETTINGS_ID}, {"$set": {**upd, "updated_by": user, "updated_at": now_iso()}})
    return await read_settings(request)


class ModeBody(BaseModel):
    mode: str


@ai_router.post("/mode")
async def set_mode(body: ModeBody, request: Request):
    user = await _auth(request)
    if body.mode not in MODES:
        raise HTTPException(400, "mode must be off, testing or live")
    if body.mode == "live" and gate.LIVE_MODE_LOCKED:
        raise HTTPException(403, "Live Mode activation is locked in this phase")
    s = await get_settings()
    if s["mode"] != body.mode:
        # Single `mode` field ⇒ Testing and Live can never be active together.
        # Version bump invalidates every job created under the previous mode.
        await db().ai_call_settings.update_one({"_id": SETTINGS_ID}, {
            "$set": {"mode": body.mode, "mode_changed_by": user, "mode_changed_at": now_iso()},
            "$inc": {"mode_version": 1}})
        await db().ai_call_jobs.update_many({"status": "pending"}, {"$set": {"status": "cancelled", "cancel_reason": "mode_changed"}})
    return await read_settings(request)


class StopBody(BaseModel):
    active: bool


@ai_router.post("/emergency-stop")
async def emergency_stop(body: StopBody, request: Request):
    user = await _auth(request)
    await get_settings()
    await db().ai_call_settings.update_one({"_id": SETTINGS_ID}, {"$set": {
        "emergency_stop": body.active, "emergency_stop_by": user, "emergency_stop_at": now_iso()}})
    if body.active:
        await db().ai_call_jobs.update_many({"status": "pending"}, {"$set": {"status": "cancelled", "cancel_reason": "emergency_stop"}})
        await db().ai_test_batches.update_many({"status": "running"}, {"$set": {"status": "stopped"}})
    return await read_settings(request)


# ---------------- template ----------------

EXAMPLE_ROWS = [
    ["Test Candidate One", "9000000001", "Data Analyst", "2026-12-15", "10:30", "English", "BluBridge", "BluBridge Office, Chennai", "yes"],
    ["Test Candidate Two", "9000000002", "AI/ML Engineer", "2026-12-16", "14:00", "Tamil", "BluBridge", "BluBridge Office, Chennai", "no"],
]
INSTRUCTIONS = [
    "Fill one row per TEST recipient. Use only numbers of people who agreed to receive test calls.",
    "Do NOT enter real candidate data. Example rows use dummy numbers — replace or delete them.",
    "candidate_name: full name (required).",
    "phone_number: 10-digit Indian mobile, e.g. 9876543210 (+91 added automatically).",
    "job_role: role mentioned on the call (required).",
    "interview_date: YYYY-MM-DD or DD-MM-YYYY, must not be in the past.",
    "interview_time: HH:MM 24-hour (14:00) or h:mm AM/PM (2:00 PM).",
    "language: English or Tamil.",
    "company_name / office_address: leave blank to use the defaults from AI Calling Settings.",
    "approved_for_test_call: yes/no — informational only. An administrator must still approve every",
    "  recipient inside the app; uploading a file NEVER starts calls.",
    "Limits: up to 500 rows, file size up to 2 MB. Accepted formats: .xlsx, .csv",
]


@ai_router.get("/template")
async def download_template(request: Request, format: str = Query("xlsx")):
    await _auth(request)
    if format == "csv":
        buf = io.StringIO()
        pd.DataFrame(EXAMPLE_ROWS, columns=COLUMNS).to_csv(buf, index=False)
        return StreamingResponse(io.BytesIO(buf.getvalue().encode()), media_type="text/csv",
                                 headers={"Content-Disposition": "attachment; filename=ai_test_candidates_template.csv"})
    wb = Workbook()
    ws = wb.active
    ws.title = "Test Candidates"
    ws.append(COLUMNS)
    for c in ws[1]:
        c.font = Font(bold=True, color="FFFFFF")
        c.fill = PatternFill("solid", fgColor="0F766E")
    for r in EXAMPLE_ROWS:
        ws.append(r)
    for col in "ABCDEFGHI":
        ws.column_dimensions[col].width = 24
    for row in ws.iter_rows(min_row=2, min_col=2, max_col=2):
        for c in row:
            c.number_format = "@"
    ins = wb.create_sheet("Instructions")
    ins.append(["AI Calling — Test Candidate Upload Instructions"])
    ins["A1"].font = Font(bold=True, size=13)
    for line in INSTRUCTIONS:
        ins.append([line])
    ins.column_dimensions["A"].width = 110
    out = io.BytesIO()
    wb.save(out)
    out.seek(0)
    return StreamingResponse(out, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                             headers={"Content-Disposition": "attachment; filename=ai_test_candidates_template.xlsx"})


# ---------------- test candidates ----------------

def _public(doc: dict) -> dict:
    d = serialize(doc)
    d["phone_masked"] = mask_phone(d.get("phone_e164", ""))
    d.pop("approved_phone", None)
    return d


def _new_doc(clean: dict, source: str, user: str, batch_ref: str = "") -> dict:
    return {
        **clean, "mode": "testing", "source": source, "upload_ref": batch_ref,
        "approved": False, "approved_phone": None, "approved_by": None, "approved_at": None,
        "consent_confirmed": False, "opted_out": False,
        "created_by": user, "created_at": now_iso(), "updated_at": now_iso(),
    }


@ai_router.get("/test-candidates")
async def list_candidates(request: Request):
    await _auth(request)
    docs = await db().ai_test_candidates.find({}).sort("created_at", -1).to_list(1000)
    return {"items": [_public(d) for d in docs]}


def _read_sheet(content: bytes, filename: str) -> pd.DataFrame:
    name = (filename or "").lower()
    try:
        if name.endswith(".xlsx"):
            return pd.read_excel(io.BytesIO(content), dtype=str, sheet_name=0)
        if name.endswith(".csv"):
            return pd.read_csv(io.BytesIO(content), dtype=str)
    except Exception as e:
        raise HTTPException(400, f"Could not read file: {e}")
    raise HTTPException(400, "Only .xlsx and .csv files are accepted")


@ai_router.post("/test-candidates/upload")
async def upload_candidates(request: Request, file: UploadFile = File(...), commit: bool = Query(False)):
    """Preview (commit=false) or import (commit=true). NEVER initiates calls or approves rows."""
    user = await _auth(request)
    content = await file.read()
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(400, "File too large (max 2 MB)")
    df = _read_sheet(content, file.filename)
    df.columns = [str(c).strip().lower() for c in df.columns]
    missing = [c for c in COLUMNS if c not in df.columns]
    unknown = [c for c in df.columns if c not in COLUMNS]
    if missing or unknown:
        raise HTTPException(400, f"Column mismatch. Missing: {missing or '-'}; Unexpected: {unknown or '-'}. Use the sample template.")
    df = df.dropna(how="all")
    if len(df) > MAX_UPLOAD_ROWS:
        raise HTTPException(400, f"Too many rows (max {MAX_UPLOAD_ROWS})")
    settings = await get_settings()
    existing = {d["phone_e164"] for d in await db().ai_test_candidates.find({}, {"phone_e164": 1}).to_list(None)}
    seen, rows = set(), []
    for i, rec in enumerate(df.to_dict("records"), start=2):
        clean, errors = validate_row(rec, settings)
        ph = clean.get("phone_e164")
        if ph in existing:
            errors.append("phone already exists in test candidates")
        elif ph in seen:
            errors.append("duplicate phone in this file")
        seen.add(ph)
        rows.append({"row": i, **clean, "phone_masked": mask_phone(ph), "errors": errors, "valid": not errors})
    valid = [r for r in rows if r["valid"]]
    imported = 0
    if commit and valid:
        ref = f"upload:{now_iso()}"
        docs = [_new_doc({k: r[k] for k in r if k not in ("row", "errors", "valid", "phone_masked")}, "upload", user, ref) for r in valid]
        res = await db().ai_test_candidates.insert_many(docs)
        imported = len(res.inserted_ids)
        _logger.info(f"[AICalling] imported {imported} test candidates by {user} (no calls triggered)")
    for r in rows:
        r.pop("phone_e164", None)
    return {"total": len(rows), "valid": len(valid), "invalid": len(rows) - len(valid),
            "imported": imported, "committed": commit, "rows": rows}


class CandidateBody(BaseModel):
    candidate_name: str = ""
    phone_number: str = ""
    job_role: str = ""
    interview_date: str = ""
    interview_time: str = ""
    language: str = ""
    company_name: str = ""
    office_address: str = ""


@ai_router.post("/test-candidates")
async def create_candidate(body: CandidateBody, request: Request):
    user = await _auth(request)
    clean, errors = validate_row(body.model_dump(), await get_settings())
    if errors:
        raise HTTPException(400, "; ".join(errors))
    if await db().ai_test_candidates.find_one({"phone_e164": clean["phone_e164"]}):
        raise HTTPException(409, "A test candidate with this phone already exists")
    clean["sheet_approved_flag"] = False
    doc = _new_doc(clean, "manual", user)
    res = await db().ai_test_candidates.insert_one(doc)
    doc["_id"] = res.inserted_id
    return _public(doc)


@ai_router.put("/test-candidates/{cid}")
async def update_candidate(cid: str, body: CandidateBody, request: Request):
    await _auth(request)
    cur = await db().ai_test_candidates.find_one({"_id": _oid(cid)})
    if not cur:
        raise HTTPException(404, "Not found")
    clean, errors = validate_row(body.model_dump(), await get_settings())
    if errors:
        raise HTTPException(400, "; ".join(errors))
    dup = await db().ai_test_candidates.find_one({"phone_e164": clean["phone_e164"], "_id": {"$ne": cur["_id"]}})
    if dup:
        raise HTTPException(409, "A test candidate with this phone already exists")
    clean.pop("sheet_approved_flag", None)
    upd = {**clean, "updated_at": now_iso()}
    if clean["phone_e164"] != cur.get("phone_e164"):
        upd.update({"approved": False, "approved_phone": None, "consent_confirmed": False,
                    "approved_by": None, "approved_at": None, "approval_revoked_reason": "phone_changed"})
    await db().ai_test_candidates.update_one({"_id": cur["_id"]}, {"$set": upd})
    return _public(await db().ai_test_candidates.find_one({"_id": cur["_id"]}))


@ai_router.delete("/test-candidates/{cid}")
async def delete_candidate(cid: str, request: Request):
    await _auth(request)
    res = await db().ai_test_candidates.delete_one({"_id": await _existing(db().ai_test_candidates, cid)})
    await db().ai_test_batches.update_many({}, {"$pull": {"candidate_ids": cid}})
    return {"deleted": res.deleted_count}


class ApproveBody(BaseModel):
    consent_confirmed: bool
    phone_last4: str


@ai_router.post("/test-candidates/{cid}/approve")
async def approve_candidate(cid: str, body: ApproveBody, request: Request):
    user = await _auth(request)
    cur = await db().ai_test_candidates.find_one({"_id": _oid(cid)})
    if not cur:
        raise HTTPException(404, "Not found")
    if cur.get("opted_out"):
        raise HTTPException(400, "Recipient has opted out; clear opt-out first")
    if not body.consent_confirmed:
        raise HTTPException(400, "You must confirm the recipient agreed to receive test calls")
    if (body.phone_last4 or "").strip() != cur["phone_e164"][-4:]:
        raise HTTPException(400, "Last 4 digits do not match the stored phone number")
    _, errors = validate_row({**cur, "phone_number": cur["phone_e164"], "approved_for_test_call": ""}, await get_settings())
    if errors:
        raise HTTPException(400, "Fix validation errors before approval: " + "; ".join(errors))
    await db().ai_test_candidates.update_one({"_id": cur["_id"]}, {"$set": {
        "approved": True, "approved_phone": cur["phone_e164"], "consent_confirmed": True,
        "approved_by": user, "approved_at": now_iso(), "updated_at": now_iso()}})
    return _public(await db().ai_test_candidates.find_one({"_id": cur["_id"]}))


@ai_router.post("/test-candidates/{cid}/revoke")
async def revoke_candidate(cid: str, request: Request):
    await _auth(request)
    oid = await _existing(db().ai_test_candidates, cid)
    await db().ai_test_candidates.update_one({"_id": oid}, {"$set": {
        "approved": False, "approved_phone": None, "consent_confirmed": False, "updated_at": now_iso()}})
    return _public(await db().ai_test_candidates.find_one({"_id": oid}))


class OptOutBody(BaseModel):
    opted_out: bool


@ai_router.post("/test-candidates/{cid}/opt-out")
async def opt_out_candidate(cid: str, body: OptOutBody, request: Request):
    await _auth(request)
    oid = await _existing(db().ai_test_candidates, cid)
    upd = {"opted_out": body.opted_out, "updated_at": now_iso()}
    if body.opted_out:
        upd.update({"approved": False, "approved_phone": None, "consent_confirmed": False})
    await db().ai_test_candidates.update_one({"_id": oid}, {"$set": upd})
    return _public(await db().ai_test_candidates.find_one({"_id": oid}))


# ---------------- batches ----------------

class BatchBody(BaseModel):
    name: str = ""
    candidate_ids: List[str]


@ai_router.get("/test-batches")
async def list_batches(request: Request):
    await _auth(request)
    docs = await db().ai_test_batches.find({}).sort("created_at", -1).to_list(200)
    return {"items": [serialize(d) for d in docs]}


@ai_router.post("/test-batches")
async def create_batch(body: BatchBody, request: Request):
    user = await _auth(request)
    ids = list(dict.fromkeys(body.candidate_ids))
    if not ids:
        raise HTTPException(400, "Select at least one approved test candidate")
    oids = [_oid(i) for i in ids]
    approved = await db().ai_test_candidates.count_documents({"_id": {"$in": oids}, "approved": True, "opted_out": {"$ne": True}})
    if approved != len(ids):
        raise HTTPException(400, "Only approved, non-opted-out test candidates can be added to a batch")
    s = await get_settings()
    doc = {"name": body.name.strip() or f"Test batch {now_iso()[:16]}", "candidate_ids": ids, "mode": "testing",
           "status": "draft", "mode_version": s["mode_version"], "created_by": user, "created_at": now_iso()}
    res = await db().ai_test_batches.insert_one(doc)
    doc["_id"] = res.inserted_id
    return serialize(doc)


async def _preflight(batch: dict) -> list:
    out = []
    bid = str(batch["_id"])
    for cid in batch.get("candidate_ids", []):
        cand = await db().ai_test_candidates.find_one({"_id": _oid(cid)}) or {}
        res = await gate.evaluate(mode="testing", test_candidate_id=cid, batch_id=bid,
                                  phone_e164=cand.get("phone_e164", ""), mode_version=batch.get("mode_version", 0))
        out.append({"candidate_id": cid, "candidate_name": cand.get("candidate_name", "(deleted)"),
                    "phone_masked": mask_phone(cand.get("phone_e164", "")), **res})
    return out


@ai_router.post("/test-batches/{bid}/preflight")
async def preflight_batch(bid: str, request: Request):
    await _auth(request)
    batch = await db().ai_test_batches.find_one({"_id": _oid(bid)})
    if not batch:
        raise HTTPException(404, "Not found")
    return {"batch_id": bid, "results": await _preflight(batch)}


@ai_router.post("/test-batches/{bid}/start")
async def start_batch(bid: str, request: Request):
    """Phase 2: always refused — Bolna integration is not approved. No jobs, no network calls."""
    await _auth(request)
    batch = await db().ai_test_batches.find_one({"_id": _oid(bid)})
    if not batch:
        raise HTTPException(404, "Not found")
    if not gate.BOLNA_INTEGRATION_APPROVED:
        raise HTTPException(423, "Start Test Calls is disabled until the Bolna API integration is approved")
    raise HTTPException(501, "Test call dispatch is not implemented yet")


@ai_router.post("/test-batches/{bid}/stop")
async def stop_batch(bid: str, request: Request):
    user = await _auth(request)
    oid = await _existing(db().ai_test_batches, bid)
    await db().ai_test_batches.update_one({"_id": oid}, {"$set": {"status": "stopped", "stopped_by": user, "stopped_at": now_iso()}})
    res = await db().ai_call_jobs.update_many({"batch_id": bid, "status": "pending"},
                                              {"$set": {"status": "cancelled", "cancel_reason": "batch_stopped"}})
    return {"stopped": True, "cancelled_jobs": res.modified_count}


# ---------------- calls (history placeholders) ----------------

@ai_router.get("/calls")
async def list_calls(request: Request, mode: Optional[str] = Query(None)):
    await _auth(request)
    q = {"mode": mode} if mode in ("testing", "live") else {}
    docs = await db().ai_calls.find(q).sort("created_at", -1).to_list(500)
    return {"items": [serialize(d) for d in docs]}


@ai_router.get("/calls/{call_id}")
async def get_call(call_id: str, request: Request):
    await _auth(request)
    doc = await db().ai_calls.find_one({"_id": _oid(call_id)})
    if not doc:
        raise HTTPException(404, "Not found")
    return serialize(doc)


@ai_router.get("/live/status")
async def live_status(request: Request):
    await _auth(request)
    s = await get_settings()
    return {"locked": gate.LIVE_MODE_LOCKED, "active": s["mode"] == "live",
            "call_hours_before": s["live_call_hours_before"], "no_answer_retries": s["live_retry_no_answer"],
            "source": "bb_registrations (read-only, not accessed in this phase)",
            "interview_location": "Offline — Chennai office"}
