"""Test Candidate Management (Testing Mode only).

Reads/writes ONLY ai_test_candidates, ai_upload_batches, ai_test_batches.
Never reads bb_registrations / pipeline_data. Never places calls.
"""
import io
import logging
import re
import uuid
from datetime import datetime, timedelta

import pandas as pd
from bson import ObjectId
from fastapi import APIRouter, File, HTTPException, Query, Request, UploadFile
from fastapi.responses import StreamingResponse
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill
from pydantic import BaseModel

from .store import (
    COLUMNS, ERROR_CATEGORIES, IST, TIMEZONE, _clean, _state, db, error_text,
    mask_phone, now_iso, serialize, validate_row,
)

_logger = logging.getLogger("ai_calling")
cand_router = APIRouter()
CALLING_DISABLED_MSG = "AI Calling will be enabled after Bolna API integration and testing are completed."
MAX_UPLOAD_BYTES = 2 * 1024 * 1024
MAX_UPLOAD_ROWS = 500
INVALIDATE = {"approved": False, "approved_phone": None, "approved_by": None, "approved_at": None,
              "consent_confirmed": False, "consent_status": "not_confirmed"}


async def _auth(request: Request) -> str:
    return await _state["auth"](request)


async def _get(cid: str) -> dict:
    doc = await db().ai_test_candidates.find_one({"_id": ObjectId(cid)}) if ObjectId.is_valid(cid) else None
    if not doc:
        raise HTTPException(404, "Test candidate not found")
    return doc


def _audit(action: str, user: str, phone: str = "", note: str = "") -> dict:
    return {"action": action, "by": user, "at": now_iso(), "phone_masked": mask_phone(phone), "note": note}


def readiness(d: dict) -> str:
    if d.get("opted_out"):
        return "opted_out"
    if not d.get("approved") or d.get("approved_phone") != d.get("phone_e164") or not d.get("consent_confirmed"):
        return "not_approved"
    if (d.get("interview_date") or "") < datetime.now(IST).date().isoformat():
        return "interview_passed"
    return "ready_calling_disabled"


def _public(doc: dict) -> dict:
    d = serialize(doc)
    d["phone_masked"] = mask_phone(d.get("phone_e164", ""))
    d["readiness"] = readiness(doc)
    d.pop("approved_phone", None)
    return d


def _new_doc(clean: dict, source: str, user: str, upload_batch_id=None) -> dict:
    now = now_iso()
    return {
        **clean, "test_candidate_id": "TC-" + uuid.uuid4().hex[:10].upper(), "mode": "testing",
        "interview_timezone": TIMEZONE, "source": source, "upload_batch_id": upload_batch_id,
        **INVALIDATE, "opted_out": False, "approval_audit": [],
        "created_by": user, "created_at": now, "updated_at": now,
    }


async def backfill_candidates():
    """Give Phase 2 test records the Phase 3 fields (test collection only)."""
    async for d in db().ai_test_candidates.find({"test_candidate_id": {"$exists": False}}):
        await db().ai_test_candidates.update_one({"_id": d["_id"]}, {"$set": {
            "test_candidate_id": "TC-" + uuid.uuid4().hex[:10].upper(), "interview_timezone": TIMEZONE,
            "consent_status": "confirmed" if d.get("consent_confirmed") else "not_confirmed",
            "upload_batch_id": d.get("upload_ref") or None, "approval_audit": d.get("approval_audit", [])}})


# ---------------- template ----------------

INSTRUCTIONS = [
    "Fill one row per TEST recipient who has agreed to receive AI test calls. Never enter real candidate data.",
    "The two yellow EXAMPLE rows are samples only. Delete or overwrite them — rows named 'EXAMPLE…' are rejected.",
    "candidate_name: full name (required).",
    "phone_number: +91XXXXXXXXXX, e.g. +919876543210 (cells are text so Excel keeps the + and digits).",
    "job_role: role mentioned on the call (required).",
    "interview_date: YYYY-MM-DD, not in the past.",
    "interview_time: HH in 24-hour IST, e.g. 10 or 14 (HH:MM also accepted).",
    "language: English or Tamil.",
    "company_name and office_address: required (interviews are offline at the Chennai office).",
    "approved_for_test_call: YES or NO. Informational only — an administrator must still approve every",
    "  recipient in the app. Uploading a sheet NEVER approves anyone and NEVER starts calls.",
    f"Limits: .xlsx or .csv, up to {MAX_UPLOAD_ROWS} rows, up to 2 MB.",
]


def _example_rows():
    d1 = (datetime.now(IST).date() + timedelta(days=30)).isoformat()
    d2 = (datetime.now(IST).date() + timedelta(days=31)).isoformat()
    return [
        ["EXAMPLE - Test Candidate One", "+919000000001", "Data Analyst", d1, "10", "English", "BluBridge", "BluBridge Office, Chennai", "YES"],
        ["EXAMPLE - Test Candidate Two", "+919000000002", "AI/ML Engineer", d2, "14", "Tamil", "BluBridge", "BluBridge Office, Chennai", "NO"],
    ]


@cand_router.get("/template")
async def download_template(request: Request, format: str = Query("xlsx")):
    await _auth(request)
    if format == "csv":
        buf = io.StringIO()
        pd.DataFrame(_example_rows(), columns=COLUMNS).to_csv(buf, index=False)
        return StreamingResponse(io.BytesIO(buf.getvalue().encode()), media_type="text/csv",
                                 headers={"Content-Disposition": "attachment; filename=ai_test_candidates_sample.csv"})
    wb = Workbook()
    ws = wb.active
    ws.title = "Test Candidates"
    ws.append(COLUMNS)
    for c in ws[1]:
        c.font = Font(bold=True, color="FFFFFF")
        c.fill = PatternFill("solid", fgColor="0F766E")
    for r in _example_rows():
        ws.append(r)
    yellow = PatternFill("solid", fgColor="FFF3B0")
    for row in ws.iter_rows(min_row=2, max_row=1 + MAX_UPLOAD_ROWS, max_col=len(COLUMNS)):
        for c in row:
            c.number_format = "@"
            if c.row <= 3:
                c.fill = yellow
    for i in range(len(COLUMNS)):
        ws.column_dimensions[chr(65 + i)].width = 26
    ins = wb.create_sheet("Instructions")
    ins.append(["AI Calling — Test Candidate Sample Sheet"])
    ins["A1"].font = Font(bold=True, size=13)
    for line in INSTRUCTIONS:
        ins.append([line])
    ins.column_dimensions["A"].width = 115
    out = io.BytesIO()
    wb.save(out)
    out.seek(0)
    return StreamingResponse(out, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                             headers={"Content-Disposition": "attachment; filename=ai_test_candidates_sample.xlsx"})


# ---------------- upload: preview → correct/exclude → import ----------------

def _read_sheet(content: bytes, filename: str) -> pd.DataFrame:
    name = (filename or "").lower()
    if not name.endswith((".xlsx", ".csv")):
        raise HTTPException(400, "Unsupported file type. Upload .xlsx or .csv only")
    try:
        if name.endswith(".xlsx"):
            return pd.read_excel(io.BytesIO(content), dtype=str, sheet_name=0)
        return pd.read_csv(io.BytesIO(content), dtype=str)
    except Exception as e:  # noqa: BLE001 — surface parser errors to the admin
        raise HTTPException(400, f"Could not read file: {e}") from e


async def _validate_rows(rows: list) -> dict:
    """rows: [{row, values{col: str}}] → per-row errors + category summary."""
    existing = {d["phone_e164"] for d in await db().ai_test_candidates.find({}, {"phone_e164": 1}).to_list(None)}
    seen, out = set(), []
    for r in rows:
        clean, errors = validate_row(r["values"], require_flag=True)
        ph = clean.get("phone_e164")
        if ph and not any(e["category"] == "invalid_phone" for e in errors) and "phone_number" not in {e["field"] for e in errors}:
            if ph in existing:
                errors.append({"field": "phone_number", "category": "duplicate_existing", "message": "phone already imported as a test candidate"})
            elif ph in seen:
                errors.append({"field": "phone_number", "category": "duplicate_in_file", "message": "duplicate phone in this file"})
            seen.add(ph)
        out.append({"row": r["row"], "values": r["values"], "phone_masked": mask_phone(ph), "errors": errors, "valid": not errors})
    summary = {c: sum(1 for r in out if any(e["category"] == c for e in r["errors"])) for c in ERROR_CATEGORIES}
    valid = sum(1 for r in out if r["valid"])
    return {"total": len(out), "valid": valid, "invalid": len(out) - valid, "by_category": summary, "rows": out}


@cand_router.post("/test-candidates/upload")
async def upload_preview(request: Request, file: UploadFile = File(...)):  # noqa: B008
    """Parse + validate only. Saves nothing, approves nothing, never calls."""
    await _auth(request)
    content = await file.read()
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(400, "File too large (max 2 MB)")
    df = _read_sheet(content, file.filename)
    df.columns = [str(c).strip().lower() for c in df.columns]
    missing = [c for c in COLUMNS if c not in df.columns]
    unknown = [c for c in df.columns if c not in COLUMNS]
    if missing or unknown:
        raise HTTPException(400, f"Column mismatch. Missing: {missing or '-'}; Unexpected: {unknown or '-'}. Use the sample sheet.")
    df = df.dropna(how="all")
    if df.empty:
        raise HTTPException(400, "The file has no data rows")
    if len(df) > MAX_UPLOAD_ROWS:
        raise HTTPException(400, f"Too many rows (max {MAX_UPLOAD_ROWS})")
    rows = [{"row": i, "values": {c: _clean(rec.get(c)) for c in COLUMNS}}
            for i, rec in enumerate(df.to_dict("records"), start=2)]
    return {"filename": file.filename, **await _validate_rows(rows)}


class RowIn(BaseModel):
    row: int
    values: dict


class RowsBody(BaseModel):
    rows: list[RowIn]
    filename: str = ""
    excluded_count: int = 0


def _rows(body: RowsBody) -> list:
    if not body.rows:
        raise HTTPException(400, "No rows to process")
    if len(body.rows) > MAX_UPLOAD_ROWS:
        raise HTTPException(400, f"Too many rows (max {MAX_UPLOAD_ROWS})")
    return [{"row": r.row, "values": {c: _clean(r.values.get(c)) for c in COLUMNS}} for r in body.rows]


@cand_router.post("/test-candidates/validate-rows")
async def validate_rows(body: RowsBody, request: Request):
    await _auth(request)
    return await _validate_rows(_rows(body))


@cand_router.post("/test-candidates/import")
async def import_rows(body: RowsBody, request: Request):
    """Import corrected rows. Rejects the whole import if ANY row is still invalid."""
    user = await _auth(request)
    res = await _validate_rows(_rows(body))
    if res["invalid"]:
        raise HTTPException(400, f"{res['invalid']} row(s) are still invalid. Fix or exclude them before importing.")
    ubid = "UP-" + uuid.uuid4().hex[:10].upper()
    docs = []
    for r in res["rows"]:
        clean, _ = validate_row(r["values"], require_flag=True)
        docs.append(_new_doc(clean, "upload", user, ubid))
    await db().ai_test_candidates.insert_many(docs)
    await db().ai_upload_batches.insert_one({
        "upload_batch_id": ubid, "filename": body.filename, "imported": len(docs),
        "excluded": body.excluded_count, "created_by": user, "created_at": now_iso()})
    _logger.info(f"[AICalling] {user} imported {len(docs)} test candidates ({ubid}); no calls triggered")
    return {"imported": len(docs), "upload_batch_id": ubid}


# ---------------- list / manual CRUD ----------------

@cand_router.get("/test-candidates")
async def list_candidates(request: Request, search: str = "", approval: str = "all", source: str = "",
                          language: str = "", ready: str = "", page: int = 1, page_size: int = 20):
    await _auth(request)
    q = {}
    if search.strip():
        s = re.escape(search.strip())
        ors = [{"candidate_name": {"$regex": s, "$options": "i"}}, {"job_role": {"$regex": s, "$options": "i"}},
               {"test_candidate_id": {"$regex": s, "$options": "i"}}]
        digits = re.sub(r"\D", "", search)
        if len(digits) >= 4:
            ors.append({"phone_e164": {"$regex": digits[-10:]}})
        q["$or"] = ors
    if approval == "approved":
        q.update({"approved": True, "opted_out": {"$ne": True}})
    elif approval == "pending":
        q.update({"approved": {"$ne": True}, "opted_out": {"$ne": True}})
    elif approval == "opted_out":
        q["opted_out"] = True
    if source in ("manual", "upload"):
        q["source"] = source
    if language in ("English", "Tamil"):
        q["language"] = language
    docs = await db().ai_test_candidates.find(q).sort("created_at", -1).to_list(5000)
    items = [_public(d) for d in docs]
    if ready:
        items = [i for i in items if i["readiness"] == ready]
    page_size = max(1, min(page_size, 100))
    page = max(1, page)
    total = len(items)
    return {"items": items[(page - 1) * page_size: page * page_size], "total": total,
            "page": page, "page_size": page_size, "pages": max(1, -(-total // page_size))}


class CandidateBody(BaseModel):
    candidate_name: str = ""
    phone_number: str = ""
    job_role: str = ""
    interview_date: str = ""
    interview_time: str = ""
    language: str = ""
    company_name: str = ""
    office_address: str = ""


@cand_router.post("/test-candidates")
async def create_candidate(body: CandidateBody, request: Request):
    user = await _auth(request)
    clean, errors = validate_row(body.model_dump())
    if errors:
        raise HTTPException(400, error_text(errors))
    if await db().ai_test_candidates.find_one({"phone_e164": clean["phone_e164"]}):
        raise HTTPException(409, "A test candidate with this phone number already exists")
    clean["sheet_approved_flag"] = False
    doc = _new_doc(clean, "manual", user)
    doc["_id"] = (await db().ai_test_candidates.insert_one(doc)).inserted_id
    return _public(doc)


@cand_router.put("/test-candidates/{cid}")
async def update_candidate(cid: str, body: CandidateBody, request: Request):
    user = await _auth(request)
    cur = await _get(cid)
    clean, errors = validate_row(body.model_dump())
    if errors:
        raise HTTPException(400, error_text(errors))
    if await db().ai_test_candidates.find_one({"phone_e164": clean["phone_e164"], "_id": {"$ne": cur["_id"]}}):
        raise HTTPException(409, "A test candidate with this phone number already exists")
    clean.pop("sheet_approved_flag", None)
    upd = {**clean, "updated_at": now_iso()}
    op = {"$set": upd}
    changed = [f for f in ("phone_e164", "candidate_name") if clean[f] != cur.get(f)]
    if changed and (cur.get("approved") or cur.get("consent_confirmed")):
        upd.update(INVALIDATE)
        op["$push"] = {"approval_audit": _audit("approval_invalidated", user, clean["phone_e164"], f"{', '.join(changed)} changed")}
    await db().ai_test_candidates.update_one({"_id": cur["_id"]}, op)
    return _public(await _get(cid))


@cand_router.delete("/test-candidates/{cid}")
async def delete_candidate(cid: str, request: Request):
    await _auth(request)
    cur = await _get(cid)
    await db().ai_test_candidates.delete_one({"_id": cur["_id"]})
    await db().ai_test_batches.update_many({}, {"$pull": {"candidate_ids": cid}})
    return {"deleted": 1}


# ---------------- approval ----------------

class ApproveBody(BaseModel):
    consent_confirmed: bool
    phone_last4: str


async def _approve(cur: dict, user: str) -> str:
    """Return '' on success or a reason string."""
    if cur.get("opted_out"):
        return "recipient has opted out"
    _, errors = validate_row({**cur, "phone_number": cur.get("phone_e164")})
    if errors:
        return "fix validation errors first: " + error_text(errors)
    await db().ai_test_candidates.update_one({"_id": cur["_id"]}, {
        "$set": {"approved": True, "approved_phone": cur["phone_e164"], "approved_by": user, "approved_at": now_iso(),
                 "consent_confirmed": True, "consent_status": "confirmed", "updated_at": now_iso()},
        "$push": {"approval_audit": _audit("approved", user, cur["phone_e164"], "consent confirmed by admin")}})
    return ""


async def _revoke(cur: dict, user: str, note: str = ""):
    await db().ai_test_candidates.update_one({"_id": cur["_id"]}, {
        "$set": {**INVALIDATE, "updated_at": now_iso()},
        "$push": {"approval_audit": _audit("revoked", user, cur.get("phone_e164", ""), note)}})


@cand_router.post("/test-candidates/{cid}/approve")
async def approve_candidate(cid: str, body: ApproveBody, request: Request):
    user = await _auth(request)
    cur = await _get(cid)
    if not body.consent_confirmed:
        raise HTTPException(400, "Confirm that the recipient agreed to receive test calls")
    if (body.phone_last4 or "").strip() != cur["phone_e164"][-4:]:
        raise HTTPException(400, "Last 4 digits do not match the stored phone number")
    reason = await _approve(cur, user)
    if reason:
        raise HTTPException(400, reason[0].upper() + reason[1:])
    return _public(await _get(cid))


@cand_router.post("/test-candidates/{cid}/revoke")
async def revoke_candidate(cid: str, request: Request):
    user = await _auth(request)
    await _revoke(await _get(cid), user)
    return _public(await _get(cid))


class OptOutBody(BaseModel):
    opted_out: bool


@cand_router.post("/test-candidates/{cid}/opt-out")
async def opt_out_candidate(cid: str, body: OptOutBody, request: Request):
    user = await _auth(request)
    cur = await _get(cid)
    upd = {"opted_out": body.opted_out, "updated_at": now_iso(), **(INVALIDATE if body.opted_out else {})}
    await db().ai_test_candidates.update_one({"_id": cur["_id"]}, {
        "$set": upd, "$push": {"approval_audit": _audit("opted_out" if body.opted_out else "opt_out_cleared", user, cur["phone_e164"])}})
    return _public(await _get(cid))


class BulkBody(BaseModel):
    ids: list[str]
    consent_confirmed: bool = False
    confirmation: str = ""


async def _bulk_docs(ids: list) -> list:
    ids = list(dict.fromkeys(ids))
    if not ids or len(ids) > 500:
        raise HTTPException(400, "Select between 1 and 500 test candidates")
    oids = [ObjectId(i) for i in ids if ObjectId.is_valid(i)]
    return await db().ai_test_candidates.find({"_id": {"$in": oids}}).to_list(None)


@cand_router.post("/test-candidates/bulk-approve")
async def bulk_approve(body: BulkBody, request: Request):
    user = await _auth(request)
    if body.confirmation != "APPROVE" or not body.consent_confirmed:
        raise HTTPException(400, "Bulk approval needs consent confirmation and the word APPROVE")
    docs = await _bulk_docs(body.ids)
    results = []
    for d in docs:
        reason = "already approved" if d.get("approved") else await _approve(d, user)
        results.append({"id": str(d["_id"]), "candidate_name": d.get("candidate_name"), "ok": not reason, "reason": reason})
    return {"approved": sum(r["ok"] for r in results), "skipped": [r for r in results if not r["ok"]],
            "not_found": len(set(body.ids)) - len(docs)}


@cand_router.post("/test-candidates/bulk-revoke")
async def bulk_revoke(body: BulkBody, request: Request):
    user = await _auth(request)
    docs = await _bulk_docs(body.ids)
    for d in docs:
        await _revoke(d, user, "bulk revoke")
    return {"revoked": len(docs)}


@cand_router.post("/test-candidates/bulk-delete")
async def bulk_delete(body: BulkBody, request: Request):
    await _auth(request)
    if body.confirmation != "DELETE":
        raise HTTPException(400, "Bulk delete needs the word DELETE")
    docs = await _bulk_docs(body.ids)
    ids = [d["_id"] for d in docs]
    await db().ai_test_candidates.delete_many({"_id": {"$in": ids}})
    await db().ai_test_batches.update_many({}, {"$pull": {"candidate_ids": {"$in": [str(i) for i in ids]}}})
    return {"deleted": len(ids)}


# ---------------- calling controls (disabled) ----------------

@cand_router.post("/calls/initiate")
async def initiate_calls(request: Request):
    """Call Now / Call Selected. Always refused in this phase — no jobs, no network."""
    await _auth(request)
    raise HTTPException(423, CALLING_DISABLED_MSG)


@cand_router.post("/calls/stop")
async def stop_calls(request: Request):
    user = await _auth(request)
    jobs = await db().ai_call_jobs.update_many({"status": "pending"}, {"$set": {"status": "cancelled", "cancel_reason": "stop_calls"}})
    batches = await db().ai_test_batches.update_many({"status": "running"}, {"$set": {"status": "stopped", "stopped_by": user, "stopped_at": now_iso()}})
    return {"cancelled_jobs": jobs.modified_count, "stopped_batches": batches.modified_count}
