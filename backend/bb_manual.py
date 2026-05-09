"""
Manual Operations module (iter67)
=================================
Provides three admin-driven flows that complement the automated pipeline:

  • Manual Applicant Alerts (#2) — search by email+phone → re-fire any of the
    5 messaging templates (shortlist, schedule detail, OTP, follow-up, reject).
  • Manual OTP Verify (#4)      — set otp_verified=1 on a matched record.
  • Tester Credentials (#5)     — manage `bb_test_credentials` (email OR phone
    match → cooldown bypass on registration form).

All three reuse the existing `messaging.py` allowlist + AiSensy/SMTP clients.
No new outbound channels, no destructive DB updates.
"""
import logging
import uuid
import secrets
from typing import Optional, List
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Request, Depends, Query
from pydantic import BaseModel, EmailStr
from motor.motor_asyncio import AsyncIOMotorDatabase

from messaging import (
    notify_shortlisted,
    notify_schedule_confirmation,
    notify_otp,
    notify_missed_reminder,
    notify_rejected,
)

_logger = logging.getLogger("bb_manual")

manual_router = APIRouter(prefix="/api/bb/manual", tags=["ManualOps"])

_db: Optional[AsyncIOMotorDatabase] = None
_get_user = None


def init_manual(db: AsyncIOMotorDatabase, get_user_dep):
    global _db, _get_user
    _db = db
    _get_user = get_user_dep


# ---------- helpers ----------
def _norm_email(v) -> str:
    return (v or "").strip().lower()


def _norm_phone(v) -> str:
    digits = "".join(ch for ch in str(v or "") if ch.isdigit())
    return digits[-10:] if len(digits) >= 10 else digits


async def _find_applicant(email: str, phone: str) -> Optional[dict]:
    """Find pipeline_data record by email OR phone (last 10 digits match)."""
    e = _norm_email(email)
    p = _norm_phone(phone)
    if not (e or p):
        return None
    import re
    clauses = []
    if e:
        clauses.append({"email": e})
    if p:
        clauses.append({"phone": {"$regex": f"{re.escape(p)}$"}})
    return await _db.pipeline_data.find_one({"$or": clauses}, {"_id": 0})


def _parse_schedule_date_iso(raw) -> str:
    """Coerce DB schedule_date into 'YYYY-MM-DD' (DATE-ONLY).
    Accepted inputs: 'YYYY-MM-DD', 'DD-MM-YYYY', 'DD/MM/YYYY', 'YYYY/MM/DD',
    or any of the above with an embedded time (e.g. '2026-05-08 13:00:00',
    '2026-05-08T13:00:00+00:00'). Time component is dropped.
    Empty / unparseable → '' so the caller can show 'unknown' state."""
    s = str(raw or "").strip()
    if not s:
        return ""
    # iter69d — Strip any time component so the comparison is DATE-ONLY.
    # Splits on the first space OR the 'T' (ISO datetime) so we keep just
    # the calendar-date portion before parsing.
    head = s.split("T", 1)[0].split(" ", 1)[0]
    for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y", "%Y/%m/%d"):
        try:
            from datetime import datetime as _dt
            return _dt.strptime(head, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return ""


def _interview_status_today(schedule_date_iso: str) -> str:
    """Compare normalized schedule date with TODAY (local system date, date-only).
    Returns 'today' | 'past' | 'future' | 'unknown'."""
    if not schedule_date_iso:
        return "unknown"
    try:
        from datetime import datetime as _dt, date as _date
        target = _dt.strptime(schedule_date_iso, "%Y-%m-%d").date()
        today = _date.today()  # LOCAL SYSTEM DATE
        if target == today:   return "today"
        if target < today:    return "past"
        return "future"
    except Exception:
        return "unknown"


def _derive_registered_status(rec: dict) -> str:
    """Derive the recruiter-facing registration status from pipeline_data.
    Rules (per spec #6):
      - email_type == 'reject'                    → "Rejected"
      - email_type == 'shortlist' AND no schedule → "Interview not scheduled"
      - schedule present AND otp_verified=1       → "Attended"
      - schedule present AND interview_date<today → "Not Attended"
      - schedule present AND otp_verified!=1      → "Interview scheduled"
      - default                                   → ""  (unknown)
    """
    et = (rec.get("email_type") or "").strip().lower()
    if et == "reject":
        return "Rejected"
    has_sched = bool((rec.get("schedule_date") or "").strip()) and bool((rec.get("schedule_time") or "").strip())
    is_verified = bool(rec.get("otp_verified"))
    if has_sched and is_verified:
        return "Attended"
    if et == "shortlist" and not has_sched:
        return "Interview not scheduled"
    if has_sched and not is_verified:
        sched_iso = _parse_schedule_date_iso(rec.get("schedule_date"))
        if _interview_status_today(sched_iso) == "past":
            return "Not Attended"
        return "Interview scheduled"
    return ""


async def _ensure_default_test_credentials():
    """Seed the two default tester rows on first call (idempotent)."""
    defaults = [
        {"email": "rishi.nayak@blubridge.com", "phone": "9443109903"},
        {"email": "rajlearn@gmail.com",        "phone": "8883847098"},
    ]
    for d in defaults:
        existing = await _db.bb_test_credentials.find_one(
            {"$or": [{"email": d["email"]}, {"phone": d["phone"]}]}
        )
        if not existing:
            await _db.bb_test_credentials.insert_one({
                "id": uuid.uuid4().hex,
                "email": d["email"],
                "phone": d["phone"],
                "created_at": datetime.now(timezone.utc).isoformat(),
                "is_default": True,
            })


# ===========================================================================
# Module #2 — Manual Applicant Alerts
# ===========================================================================
class AlertSendBody(BaseModel):
    email: str
    phone: str


@manual_router.get("/applicant/lookup")
async def lookup_applicant(request: Request, email: Optional[str] = None, phone: Optional[str] = None):
    await _get_user(request)
    if not (email or phone):
        raise HTTPException(400, "email or phone required")
    rec = await _find_applicant(email or "", phone or "")
    if not rec:
        raise HTTPException(404, "Applicant not found in pipeline_data")
    sched_iso = _parse_schedule_date_iso(rec.get("schedule_date"))
    interview_status = _interview_status_today(sched_iso)
    # iter70 — OTP resolution: prefer pipeline_data.otp; fall back to the
    # latest bb_registrations.otp for the same applicant if pipeline_data.otp
    # is null/empty (the OTP worker writes only to bb_registrations). Ensures
    # the Manual OTP Verify page ALWAYS shows the OTP if one exists, even
    # when otp_verified is already true.
    otp_value = rec.get("otp") or ""
    if not otp_value:
        e = _norm_email(rec.get("email") or "")
        p = _norm_phone(rec.get("phone") or "")
        clauses = []
        if e:
            clauses.append({"email": e})
        if p:
            import re as _re
            clauses.append({"phone": {"$regex": f"{_re.escape(p)}$"}})
        if clauses:
            reg = await _db.bb_registrations.find_one(
                {"$or": clauses, "otp": {"$exists": True, "$nin": [None, ""]}},
                {"_id": 0, "otp": 1},
                sort=[("otp_sent_at", -1)],
            )
            if reg and reg.get("otp"):
                otp_value = str(reg["otp"])
    # Surface the fields the UI needs (drop legacy/internal-only keys).
    return {
        "name":            rec.get("name") or "",
        "email":           rec.get("email") or "",
        "phone":           rec.get("phone") or "",
        "job_role":        rec.get("job_role") or rec.get("job_title") or "",
        "college_type":    rec.get("college_type") or "",
        "college":         rec.get("college") or "",
        "degree":          rec.get("degree") or "",
        "course":          rec.get("course") or "",
        "year_of_graduation": rec.get("year_of_graduation") or "",
        "schedule_date":   rec.get("schedule_date") or "",
        "schedule_date_iso": sched_iso,
        "schedule_time":   rec.get("schedule_time") or "",
        "interview_status": interview_status,  # 'today' | 'past' | 'future' | 'unknown'
        "registered_status": _derive_registered_status(rec),
        "attended":        bool(rec.get("otp_verified")),
        "result_status":   rec.get("result_status") or "",
        "hr_team":         rec.get("hr_team") or "",
        "otp":             otp_value,
        "otp_verified":    bool(rec.get("otp_verified")),
    }


async def _resolve_or_404(email: str, phone: str) -> dict:
    rec = await _find_applicant(email, phone)
    if not rec:
        raise HTTPException(404, "Applicant not found")
    return rec


async def _ensure_schedule_token(rec: dict) -> str:
    """Re-use bb_registrations token if present; else mint and persist one."""
    e = _norm_email(rec.get("email"))
    p = _norm_phone(rec.get("phone"))
    if e or p:
        clauses = []
        if e:
            clauses.append({"email": e})
        if p:
            import re
            clauses.append({"phone": {"$regex": f"{re.escape(p)}$"}})
        reg = await _db.bb_registrations.find_one(
            {"$or": clauses, "schedule_token": {"$exists": True, "$ne": ""}},
            {"_id": 0, "schedule_token": 1},
            sort=[("schedule_date", -1)],
        )
        if reg and reg.get("schedule_token"):
            return reg["schedule_token"]

    token = uuid.uuid4().hex
    await _db.bb_registrations.insert_one({
        "name": rec.get("name") or "",
        "email": e,
        "phone": p,
        "job_role": rec.get("job_role") or rec.get("job_title") or "",
        "schedule_date": rec.get("schedule_date") or "",
        "schedule_time": rec.get("schedule_time") or "",
        "schedule_token": token,
        "status": "Scheduled",
        "reschedule_count": 0,
        "created_via": "manual_alerts_module",
        "created_at": datetime.now(timezone.utc).isoformat(),
    })
    return token


@manual_router.post("/alerts/send-shortlist")
async def alert_send_shortlist(body: AlertSendBody, request: Request):
    user = await _get_user(request)
    rec = await _resolve_or_404(body.email, body.phone)
    token = await _ensure_schedule_token(rec)
    to_email = rec.get("email") or ""
    to_phone = rec.get("phone") or ""
    _logger.info(f"[ManualAlerts:shortlist] by={user} → email={to_email} phone={to_phone}")
    wa_ok, em_ok = await notify_shortlisted(
        rec.get("name") or "", to_phone, to_email, token,
    )
    success = bool(wa_ok or em_ok)
    if not success:
        raise HTTPException(502, "Failed to send via WhatsApp and Email — check messaging credentials/logs")
    return {"success": True, "action": "shortlist", "to": to_email, "wa_ok": wa_ok, "em_ok": em_ok}


@manual_router.post("/alerts/send-schedule-detail")
async def alert_send_schedule_detail(body: AlertSendBody, request: Request):
    user = await _get_user(request)
    rec = await _resolve_or_404(body.email, body.phone)
    date = rec.get("schedule_date") or ""
    time = rec.get("schedule_time") or ""
    if not (date and time):
        raise HTTPException(400, "Applicant has no schedule_date / schedule_time")
    to_email = rec.get("email") or ""
    to_phone = rec.get("phone") or ""
    _logger.info(f"[ManualAlerts:schedule_detail] by={user} → email={to_email} phone={to_phone}")
    wa_ok, em_ok = await notify_schedule_confirmation(
        rec.get("name") or "", to_phone, to_email, date, time,
    )
    success = bool(wa_ok or em_ok)
    if not success:
        raise HTTPException(502, "Failed to send via WhatsApp and Email — check messaging credentials/logs")
    return {"success": True, "action": "schedule_detail", "to": to_email, "wa_ok": wa_ok, "em_ok": em_ok}


@manual_router.post("/alerts/send-otp")
async def alert_send_otp(body: AlertSendBody, request: Request):
    user = await _get_user(request)
    rec = await _resolve_or_404(body.email, body.phone)
    otp = (rec.get("otp") or "").strip()
    if not otp:
        otp = "".join(secrets.choice("0123456789") for _ in range(6))
        await _db.pipeline_data.update_one(
            {"email": rec.get("email"), "phone": rec.get("phone")},
            {"$set": {"otp": otp, "otp_sent_at": datetime.now(timezone.utc).isoformat()}}
        )
    to_email = rec.get("email") or ""
    to_phone = rec.get("phone") or ""
    _logger.info(f"[ManualAlerts:otp] by={user} → email={to_email} phone={to_phone}")
    wa_ok, em_ok = await notify_otp(
        rec.get("name") or "", to_phone, to_email,
        rec.get("job_role") or rec.get("job_title") or "Interview",
        otp,
        rec.get("schedule_date") or "",
        rec.get("schedule_time") or "",
    )
    success = bool(wa_ok or em_ok)
    if not success:
        raise HTTPException(502, "Failed to send via WhatsApp and Email — check messaging credentials/logs")
    return {"success": True, "action": "otp", "to": to_email, "otp": otp, "wa_ok": wa_ok, "em_ok": em_ok}


@manual_router.post("/alerts/send-followup")
async def alert_send_followup(body: AlertSendBody, request: Request):
    user = await _get_user(request)
    rec = await _resolve_or_404(body.email, body.phone)
    token = await _ensure_schedule_token(rec)
    to_email = rec.get("email") or ""
    to_phone = rec.get("phone") or ""
    _logger.info(f"[ManualAlerts:followup] by={user} → email={to_email} phone={to_phone}")
    wa_ok, em_ok = await notify_missed_reminder(
        rec.get("name") or "", to_phone, to_email,
        rec.get("job_role") or rec.get("job_title") or "Interview",
        rec.get("schedule_date") or "",
        rec.get("schedule_time") or "",
        token,
    )
    success = bool(wa_ok or em_ok)
    if not success:
        raise HTTPException(502, "Failed to send via WhatsApp and Email — check messaging credentials/logs")
    return {"success": True, "action": "followup", "to": to_email, "wa_ok": wa_ok, "em_ok": em_ok}


@manual_router.post("/alerts/send-reject")
async def alert_send_reject(body: AlertSendBody, request: Request):
    user = await _get_user(request)
    rec = await _resolve_or_404(body.email, body.phone)
    to_email = rec.get("email") or ""
    to_phone = rec.get("phone") or ""
    _logger.info(f"[ManualAlerts:reject] by={user} → email={to_email} phone={to_phone}")
    ok = await notify_rejected(
        rec.get("name") or "", to_phone, to_email,
    )
    if not ok:
        raise HTTPException(502, "Failed to send via WhatsApp and Email — check messaging credentials/logs")
    return {"success": True, "action": "reject", "to": to_email}


# ===========================================================================
# Module #4 — Manual OTP Verify
# ===========================================================================
class ManualVerifyBody(BaseModel):
    email: str
    phone: str


@manual_router.post("/otp/verify")
async def manual_otp_verify(body: ManualVerifyBody, request: Request):
    user = await _get_user(request)
    e = _norm_email(body.email)
    p = _norm_phone(body.phone)
    if not (e and p):
        raise HTTPException(400, "Both email and phone are required")
    # Same-applicant check: email + phone must point to ONE pipeline_data doc.
    import re
    rec = await _db.pipeline_data.find_one(
        {"email": e, "phone": {"$regex": f"{re.escape(p)}$"}},
        {"_id": 1},
    )
    if not rec:
        raise HTTPException(404, "Email and phone do not belong to the same applicant")

    # Date guard — interview must be TODAY (matches the new UI rule). Past or
    # future schedules cannot be OTP-verified manually.
    full_for_date = await _db.pipeline_data.find_one(
        {"_id": rec["_id"]}, {"_id": 0, "schedule_date": 1}
    )
    sched_iso = _parse_schedule_date_iso((full_for_date or {}).get("schedule_date"))
    status_today = _interview_status_today(sched_iso)
    if status_today == "past":
        raise HTTPException(400, "Your interview is over !")
    if status_today == "future":
        raise HTTPException(400, "Your interview is in future !")
    # 'today' or 'unknown' (no schedule_date set) → allow verify

    now_iso = datetime.now(timezone.utc).isoformat()
    await _db.pipeline_data.update_one(
        {"_id": rec["_id"]},
        {"$set": {"otp_verified": True, "otp_verified_at": now_iso, "last_update": now_iso}},
    )
    # Mirror to bb_registrations (best-effort) so analytics views stay aligned.
    await _db.bb_registrations.update_many(
        {"$or": [{"email": e}, {"phone": {"$regex": f"{re.escape(p)}$"}}]},
        {"$set": {"otp_verified": True, "otp_verified_at": now_iso, "last_update": now_iso}},
    )
    _logger.info(f"[ManualOTP:verify] by={user} email={e} phone={p}")

    full = await _db.pipeline_data.find_one({"_id": rec["_id"]}, {"_id": 0})
    return {
        "success": True,
        "applicant": {
            "name":          full.get("name") or "",
            "phone":         full.get("phone") or "",
            "email":         full.get("email") or "",
            "job_role":      full.get("job_role") or full.get("job_title") or "",
            "college_type":  full.get("college_type") or "",
            "source":        full.get("hr_team") or "",
            "schedule_date": full.get("schedule_date") or "",
            "schedule_time": full.get("schedule_time") or "",
            "otp":           full.get("otp") or "",
            "otp_verified":  True,
        },
    }


# ===========================================================================
# Module #5 — Tester Credentials
# ===========================================================================
class TestCredBody(BaseModel):
    email: str
    phone: str


@manual_router.get("/test-credentials")
async def list_test_credentials(request: Request):
    await _get_user(request)
    await _ensure_default_test_credentials()
    cursor = _db.bb_test_credentials.find({}, {"_id": 0}).sort("created_at", 1)
    return {"items": await cursor.to_list(length=500)}


@manual_router.post("/test-credentials")
async def add_test_credential(body: TestCredBody, request: Request):
    user = await _get_user(request)
    e = _norm_email(body.email)
    p = _norm_phone(body.phone)
    if not (e and p):
        raise HTTPException(400, "Both email and phone are required")
    dup = await _db.bb_test_credentials.find_one(
        {"$or": [{"email": e}, {"phone": p}]}
    )
    if dup:
        raise HTTPException(409, f"Tester already exists (matched on {'email' if dup.get('email') == e else 'phone'})")
    doc = {
        "id": uuid.uuid4().hex,
        "email": e,
        "phone": p,
        "created_by": user,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "is_default": False,
    }
    await _db.bb_test_credentials.insert_one(doc)
    doc.pop("_id", None)
    return doc


@manual_router.put("/test-credentials/{tc_id}")
async def update_test_credential(tc_id: str, body: TestCredBody, request: Request):
    user = await _get_user(request)
    e = _norm_email(body.email)
    p = _norm_phone(body.phone)
    if not (e and p):
        raise HTTPException(400, "Both email and phone are required")
    dup = await _db.bb_test_credentials.find_one(
        {"id": {"$ne": tc_id}, "$or": [{"email": e}, {"phone": p}]}
    )
    if dup:
        raise HTTPException(409, f"Another tester already uses this {'email' if dup.get('email') == e else 'phone'}")
    res = await _db.bb_test_credentials.update_one(
        {"id": tc_id},
        {"$set": {"email": e, "phone": p, "updated_by": user, "updated_at": datetime.now(timezone.utc).isoformat()}},
    )
    if res.matched_count == 0:
        raise HTTPException(404, "Tester not found")
    return {"success": True}


@manual_router.delete("/test-credentials/{tc_id}")
async def delete_test_credential(tc_id: str, request: Request):
    await _get_user(request)
    res = await _db.bb_test_credentials.delete_one({"id": tc_id})
    if res.deleted_count == 0:
        raise HTTPException(404, "Tester not found")
    return {"success": True}
