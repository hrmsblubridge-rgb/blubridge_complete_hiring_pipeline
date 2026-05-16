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
    get_otp_for_schedule,
)
from _fmt import to_24h_db

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


# iter95 — Partial / substring search across pipeline_data. Returns a
# lightweight summary list for the multi-card picker. Distinct from
# `_find_applicant` which is exact-match (email primary) for the detail view.
async def _search_applicants(q: str, limit: int = 25) -> list:
    """Case-insensitive substring search on name, email, phone.
    `q` is whatever the admin typed (any length >= 2). Phone match strips
    non-digits and matches as a substring (so "7890" matches "1234567890").
    Email/name match using `re.escape(q)` so special chars are inert.
    Returns at most `limit` summary dicts: {name, email, phone, job_role,
    registered_status}. Empty list when q is too short or no matches.

    iter97 — Pure numeric inputs require at least 6 digits before we fire
    a phone substring scan. Shorter digit inputs return [] without touching
    Mongo. Letter-containing inputs keep the 2-char minimum since they hit
    indexed text fields (name, email).
    """
    import re
    q = (q or "").strip()
    if len(q) < 2 or _db is None:
        return []
    # iter97 — minimum 6 digits for phone-style queries.
    if q.isdigit() and len(q) < 6:
        return []
    safe = re.escape(q)
    digits = "".join(ch for ch in q if ch.isdigit())
    clauses = [
        {"name":  {"$regex": safe, "$options": "i"}},
        {"email": {"$regex": safe, "$options": "i"}},
    ]
    if digits:
        clauses.append({"phone": {"$regex": re.escape(digits)}})
    cursor = _db.pipeline_data.find(
        {"$or": clauses},
        {"_id": 0, "name": 1, "email": 1, "phone": 1, "job_role": 1,
         "job_title": 1, "schedule_date": 1, "schedule_time": 1,
         "email_type": 1, "otp_verified": 1, "result_status": 1},
    ).limit(limit + 1)
    docs = await cursor.to_list(length=limit + 1)
    items = []
    for d in docs[:limit]:
        items.append({
            "name":  d.get("name") or "",
            "email": d.get("email") or "",
            "phone": d.get("phone") or "",
            "job_role": d.get("job_role") or d.get("job_title") or "",
            "registered_status": _derive_registered_status(d),
        })
    return items


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


@manual_router.get("/applicant/search")
async def search_applicants(request: Request, q: str = Query(""), limit: int = Query(25, ge=1, le=50)):
    """iter95 — Substring/regex search returning a list of summary cards
    for the multi-result picker. The detail view still uses /applicant/lookup
    with exact email/phone once the admin clicks a card.
    Returns: { items: [...], truncated: bool }. Empty items when q < 2 chars."""
    await _get_user(request)
    items = await _search_applicants(q, limit=limit)
    # Truncated marker — fetch one extra and check if we hit the cap.
    return {"items": items, "truncated": len(items) >= limit}


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
    # iter86 — Manual OTP Verify must ALWAYS show the candidate's LATEST OTP.
    # Previously we called `get_otp_for_schedule(email, phone, schedule_date)`
    # which preferred a date-matched historical OTP. That caused a critical
    # bug: when an admin used "Reschedule & Verify" to revert schedule_date
    # to an earlier value, the OLD OTP for that date got re-surfaced and
    # appeared to overwrite the candidate's actual current OTP.
    #
    # New resolution order:
    #   1) pipeline_data.otp (if non-empty)
    #   2) most-recent bb_registrations.otp by otp_sent_at desc (any date)
    # iter100 — Defensive coercion. CSV/XLSX imports occasionally store the
    # OTP column as a numeric (float) — calling `.strip()` directly on it
    # crashes with `AttributeError: 'float' object has no attribute 'strip'`,
    # which surfaces as a 500 on /applicant/lookup and breaks the preview-card
    # click flow on Manual Alerts + Manual OTP Verify. Cast to string first,
    # then trim, and drop any trailing `.0` that float→str produces.
    _otp_raw = rec.get("otp")
    if _otp_raw is None or _otp_raw == "":
        otp_value = ""
    else:
        otp_value = str(_otp_raw).strip()
        if otp_value.endswith(".0"):
            otp_value = otp_value[:-2]
    if not otp_value:
        otp_value = await get_otp_for_schedule(
            rec.get("email") or "", rec.get("phone") or "",
            # Empty schedule_date forces the "latest overall" branch.
            "",
        )    # Surface the fields the UI needs (drop legacy/internal-only keys).
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
    # iter71 — Centralized OTP resolution: NEVER generate a new OTP from
    # any "send" path. The OTP worker (3h pre-interview) and registration
    # flow are the only writers. If no OTP exists yet, fail with a clear
    # error so the recruiter knows to wait for the auto-generation window.
    sched_date = rec.get("schedule_date") or ""
    otp = await get_otp_for_schedule(rec.get("email") or "", rec.get("phone") or "", sched_date)
    if not otp:
        raise HTTPException(
            400,
            "No OTP exists yet for this applicant. The OTP worker auto-generates "
            "the OTP up to 3 hours before the scheduled interview. Please retry "
            "closer to the interview slot or check the interview schedule_date.",
        )
    to_email = rec.get("email") or ""
    to_phone = rec.get("phone") or ""
    _logger.info(f"[ManualAlerts:otp] by={user} → email={to_email} phone={to_phone} otp_reused={otp}")
    wa_ok, em_ok = await notify_otp(
        rec.get("name") or "", to_phone, to_email,
        rec.get("job_role") or rec.get("job_title") or "Interview",
        otp,
        sched_date,
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
        job_role=rec.get("job_role") or rec.get("job_title") or "",
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

    # iter82 — Date-based Verify restriction REMOVED per spec.
    # Verify is now ALWAYS allowed regardless of schedule_date (past/future/today).
    # Future-date Reschedule edits go through the separate /otp/reschedule-verify
    # endpoint which updates schedule_date/time before verifying.
    #
    # iter86 — But we MUST block verify when the applicant has not scheduled
    # at all (no schedule_date AND no schedule_time). Without a schedule there
    # is nothing to verify against.
    full_for_sched = await _db.pipeline_data.find_one(
        {"_id": rec["_id"]}, {"_id": 0, "schedule_date": 1, "schedule_time": 1}
    )
    sd = (full_for_sched or {}).get("schedule_date") or ""
    st = (full_for_sched or {}).get("schedule_time") or ""
    if not sd.strip() and not st.strip():
        raise HTTPException(status_code=400, detail="Applicant has not scheduled their interview")

    now_iso = datetime.now(timezone.utc).isoformat()
    await _db.pipeline_data.update_one(
        {"_id": rec["_id"]},
        {"$set": {"otp_verified": True, "otp_verified_at": now_iso, "last_update": now_iso}},
    )
    # Mirror to bb_registrations — iter86 scopes to the most-recent row only
    # (matches the same fix applied to /otp/reschedule-verify).
    try:
        latest_reg = await _db.bb_registrations.find_one(
            {"$or": [{"email": e}, {"phone": {"$regex": f"{re.escape(p)}$"}}]},
            sort=[("registered_at", -1)],
            projection={"_id": 1},
        )
        if latest_reg:
            await _db.bb_registrations.update_one(
                {"_id": latest_reg["_id"]},
                {"$set": {"otp_verified": True, "otp_verified_at": now_iso, "last_update": now_iso}},
            )
    except Exception as _e:
        _logger.warning(f"[ManualOTP:verify] bb_registrations mirror skipped: {_e}")
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


# ============ RESCHEDULE & VERIFY (iter82) ============

class RescheduleVerifyBody(BaseModel):
    # Anchor — identifies the existing applicant we will overwrite
    original_email: str
    original_phone: str
    # New values (any subset; missing keys are left untouched)
    phone: Optional[str] = None
    email: Optional[str] = None
    job_role: Optional[str] = None
    schedule_date: Optional[str] = None
    schedule_time: Optional[str] = None


@manual_router.post("/otp/reschedule-verify")
async def manual_otp_reschedule_verify(body: RescheduleVerifyBody, request: Request):
    """iter82 — Update an applicant's contact/schedule fields AND mark
    otp_verified=True in a single transaction. Matches the existing record by
    original email OR phone (no duplicate creation). Used by the
    "Reschedule & Verify" button in Manual OTP Verify when the candidate
    arrives BEFORE their scheduled date.
    """
    user = await _get_user(request)
    import re as _re
    orig_e = _norm_email(body.original_email)
    orig_p = _norm_phone(body.original_phone)
    if not (orig_e or orig_p):
        raise HTTPException(400, "Anchor email or phone required")

    clauses = []
    if orig_e:
        clauses.append({"email": orig_e})
    if orig_p:
        clauses.append({"phone": {"$regex": f"{_re.escape(orig_p)}$"}})
    rec = await _db.pipeline_data.find_one(
        {"$or": clauses} if len(clauses) > 1 else clauses[0],
        {"_id": 1},
    )
    if not rec:
        raise HTTPException(404, "Applicant not found")

    now_iso = datetime.now(timezone.utc).isoformat()
    set_fields = {"otp_verified": True, "otp_verified_at": now_iso, "last_update": now_iso}
    if body.phone is not None:
        set_fields["phone"] = _norm_phone(body.phone)
    if body.email is not None:
        set_fields["email"] = _norm_email(body.email)
    if body.job_role is not None:
        new_role = (body.job_role or "").strip()
        set_fields["job_role"] = new_role
        # iter84 — Mirror to `job_title` and `_normalized_job_role` so every
        # downstream surface (Score & Round, Update Scores, View Attended,
        # exports, analytics) sees the same value. Otherwise pages that fall
        # back to job_title display the OLD role even after a successful
        # reschedule.
        set_fields["job_title"] = new_role
        set_fields["_normalized_job_role"] = new_role
    if body.schedule_date is not None:
        set_fields["schedule_date"] = (body.schedule_date or "").strip()
    if body.schedule_time is not None:
        # iter83 — Always normalize to strict 24-hour HH:MM:SS before write.
        # Rejects malformed values so we never persist garbage like "1 PM" raw.
        try:
            set_fields["schedule_time"] = to_24h_db(body.schedule_time)
        except ValueError as e:
            raise HTTPException(400, f"Invalid schedule_time: {e}")

    await _db.pipeline_data.update_one({"_id": rec["_id"]}, {"$set": set_fields})

    # Mirror onto bb_registrations so OTP / Reminder workers and the public
    # schedule page reflect the new values. iter85 — Scope to the SINGLE most
    # recent registration row (by `registered_at` desc) instead of update_many
    # across every legacy row that ever shared this email/phone. The previous
    # broad mirror polluted historical rows with `otp_verified=True`, which
    # then blocked future reschedule attempts on fresh schedule tokens.
    try:
        latest_reg = await _db.bb_registrations.find_one(
            {"$or": clauses} if len(clauses) > 1 else clauses[0],
            sort=[("registered_at", -1)],
            projection={"_id": 1},
        )
        if latest_reg:
            await _db.bb_registrations.update_one(
                {"_id": latest_reg["_id"]},
                {"$set": set_fields},
            )
    except Exception as _e:
        _logger.warning(f"[ManualOTP:reschedule-verify] bb_registrations mirror skipped: {_e}")

    # iter84 — Re-link bb_applicant_updates + score_sheet when email/phone
    # changed. These collections are joined by email (primary) / phone
    # (fallback) on every Score & Round / Update Scores / View Attended read.
    # If we leave the OLD email/phone on those docs, the join breaks and the
    # candidate appears to have lost their scores / status.
    new_email = set_fields.get("email")
    new_phone = set_fields.get("phone")
    email_changed = (new_email is not None) and (new_email != orig_e)
    phone_changed = (new_phone is not None) and (new_phone != orig_p)
    if email_changed or phone_changed:
        link_set = {}
        if new_email is not None:
            link_set["email"] = new_email
        if new_phone is not None:
            link_set["phone"] = new_phone
        for coll in ("bb_applicant_updates", "score_sheet"):
            try:
                await _db[coll].update_many(
                    {"$or": clauses} if len(clauses) > 1 else clauses[0],
                    {"$set": link_set},
                )
            except Exception as _e:
                _logger.warning(f"[ManualOTP:reschedule-verify] {coll} relink skipped: {_e}")

    full = await _db.pipeline_data.find_one({"_id": rec["_id"]}, {"_id": 0})
    # iter86 — Surface the LATEST OTP using the same resolution order as
    # /manual/applicant/lookup. Never returns an old date-matched OTP, and
    # never blanks the display when pipeline_data.otp is empty.
    otp_value = (full.get("otp") or "").strip()
    if not otp_value:
        otp_value = await get_otp_for_schedule(
            full.get("email") or "", full.get("phone") or "", "",
        )
    _logger.info(
        f"[ManualOTP:reschedule-verify] by={user} orig_email={orig_e} orig_phone={orig_p} "
        f"-> email={full.get('email')} phone={full.get('phone')} "
        f"sched={full.get('schedule_date')} {full.get('schedule_time')}"
    )
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
            "otp":           otp_value,
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
