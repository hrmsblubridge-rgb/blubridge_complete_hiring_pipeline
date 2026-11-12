"""Two calling purposes: pre-interview confirmation and OTP-based missed-interview follow-up.
Pure planning/eligibility + outcome handling + admin scheduling settings + review alerts.
Nothing here dials, edits bookings, or touches otp_verified (read-only source of truth)."""
from datetime import datetime, timedelta

from bson import ObjectId
from fastapi import APIRouter, Body, HTTPException, Request

from .dryrun import IST, MIN_LEAD, STATUS_REASON, TRUTHY_OTP, _ceil5, booking_key, interview_at, into_window, plan_booking
from .provider import _auth, _csrf
from .store import SETTINGS_ID, db, get_settings, normalize_phone, now_iso

purposes_router = APIRouter()
CONFIRM, MISSED = "interview_confirmation", "missed_interview_followup"
PURPOSES = (CONFIRM, MISSED)
MISSED_STATUSES = ("Interview Scheduled", "Missed")  # "Missed" is set automatically by bg_workers WORKER E
RETRY_OUTCOMES = ("no_answer", "busy")  # provider-confirmed, no conversation
MISSED_BLOCKING_ALERTS = ("RESCHEDULE_REQUEST_PENDING", "RUNNING_LATE", "CLAIMS_ATTENDED")
SCHEDULING_KEYS = {"confirm_enabled": bool, "confirm_offset_days": int, "missed_enabled": bool, "missed_offset_minutes": int,
                   "live_daily_call_limit": int, "live_pilot_daily_cap": int, "live_max_concurrent_calls": int,
                   "live_queue_capacity": int}


def otp_state(b: dict) -> str:
    """Read-only view of the employee OTP record. Only '' / False mean 'not verified' (owner decision)."""
    if "otp_verified" not in b:
        return "missing"
    v = b["otp_verified"]
    if v in TRUTHY_OTP or (isinstance(v, str) and v.strip().lower() in ("1", "1.0", "true", "yes")):
        return "verified"
    if v == "" or v is False:
        return "not_verified"
    return "unknown"


def purpose_cfg(s: dict, purpose: str) -> dict:
    if purpose == CONFIRM:
        return {**s, "enabled": s["confirm_enabled"], "live_call_hours_before": 24 * int(s["confirm_offset_days"]),
                "call_window_start": s["confirm_window_start"], "call_window_end": s["confirm_window_end"],
                "retry_gap": timedelta(minutes=int(s["confirm_retry_minutes"]))}
    return {**s, "enabled": s["missed_enabled"], "offset": timedelta(minutes=int(s["missed_offset_minutes"])),
            "call_window_start": s["missed_window_start"], "call_window_end": s["missed_window_end"],
            "retry_gap": timedelta(minutes=int(s["missed_retry_minutes"])),
            "followup_period": timedelta(hours=int(s["missed_followup_hours"]))}


def consent_covers(c: dict, purpose: str) -> bool:
    if (c or {}).get("status") != "granted":
        return False
    from .modes import scope_for
    return purpose in (c.get("scope") or scope_for(c.get("text_version")))


def missed_eligibility(b: dict) -> list:
    r = []
    if b.get("superseded") is True:
        r.append("SUPERSEDED")
    if b.get("isTest") is True:
        r.append("TEST_RECORD")
    st = b.get("status") or ""
    if st not in MISSED_STATUSES:
        r.append(STATUS_REASON.get(st, "UNKNOWN_STATUS") if st != "Missed" else "UNKNOWN_STATUS")
    elif b.get("is_shortlisted") is not True:
        r.append("NOT_SHORTLISTED")
    r += {"verified": ["ATTENDED_OTP_VERIFIED"], "unknown": ["ATTENDANCE_UNKNOWN"],
          "missing": ["OTP_FIELD_MISSING_DATA_ISSUE"]}.get(otp_state(b), [])
    if b.get("do_not_call") is True:
        r.append("DO_NOT_CALL")
    if not consent_covers(b.get("ai_call_consent"), MISSED):
        r.append("NO_FOLLOWUP_CONSENT")
    if b.get("blocked_alerts"):
        r += [f"ALERT_{a}" for a in b["blocked_alerts"]]
    try:
        normalize_phone(b.get("phone"))
    except ValueError:
        r.append("INVALID_PHONE")
    return r


def missed_deadline(iv: datetime, pc: dict) -> datetime:
    return iv + pc["offset"] + pc["followup_period"]


def plan_missed(b: dict, now: datetime, s: dict) -> dict:
    pc, now = purpose_cfg(s, MISSED), now.astimezone(IST)
    out = {"reasons": missed_eligibility(b), "interview_at": None, "target_at": None, "planned_at": None, "adjustments": [],
           "retry": {"eligible": True, "gap_minutes": int(pc["retry_gap"].total_seconds() // 60)}}
    try:
        iv = interview_at(b)
    except ValueError:
        iv = None
    if iv is None:
        out.update(status="SKIPPED", reasons=out["reasons"] + ["NO_SCHEDULE"])
        return out
    target = iv + pc["offset"]
    out.update(interview_at=iv.isoformat(), target_at=target.isoformat())
    if out["reasons"]:
        out["status"] = "SKIPPED"
        return out
    planned = target if target > now else _ceil5(now)
    moved = into_window(planned, pc)
    if moved != planned:
        out["adjustments"].append(f"Moved into the {pc['call_window_start']}–{pc['call_window_end']} IST window")
    if moved > missed_deadline(iv, pc):
        out.update(status="NEEDS_REVIEW", reasons=["FOLLOWUP_PERIOD_EXPIRED"])
        return out
    out.update(status="SCHEDULED", planned_at=moved.isoformat())
    return out


def plan_for(purpose: str, b: dict, now: datetime, s: dict) -> dict:
    if purpose == MISSED:
        return plan_missed(b, now, s)
    b2 = {**b, "ai_call_consent": {**(b.get("ai_call_consent") or {}),
                                   "status": "granted" if consent_covers(b.get("ai_call_consent"), CONFIRM) else
                                   (b.get("ai_call_consent") or {}).get("status")}}
    if "WRONG_NUMBER" in (b.get("blocked_alerts") or []):
        b2["do_not_call"] = True
    return plan_booking(b2, now, purpose_cfg(s, CONFIRM))


def retry_at(purpose: str, job: dict, now: datetime, s: dict):
    """One retry: confirmation +60 min (≥2 h before interview); follow-up +30 min (inside the follow-up period)."""
    pc = purpose_cfg(s, purpose)
    at = into_window(now + pc["retry_gap"], pc)
    iv = datetime.fromisoformat(job["interview_at"])
    if purpose == CONFIRM:
        return at if iv - at >= MIN_LEAD else None
    return at if at <= missed_deadline(iv, pc) else None


# ---------- outcomes (used by the mock worker now and by real result handling later) ----------

def outcome_of(purpose: str, ex: dict) -> str:
    att, mo = ex.get("attendance_status") or "UNKNOWN", ex.get("missed_interview_outcome")
    if "DO_NOT_CALL" in (att, mo):
        return "DO_NOT_CALL"  # opt-out wins over DECLINED or anything else
    if att == "WRONG_NUMBER" or mo == "WRONG_NUMBER":
        return "WRONG_NUMBER"
    if purpose == MISSED and mo:
        return mo
    if ex.get("wants_reschedule") is True or att == "RESCHEDULE_REQUESTED":
        return "RESCHEDULE_REQUESTED"
    return att


async def raise_alert(reg_id: str, bkey: str, purpose: str, kind: str, detail: dict) -> None:
    await db().ai_call_alerts.update_one(
        {"registration_id": reg_id, "booking_key": bkey, "type": kind, "status": "open"},
        {"$setOnInsert": {"registration_id": reg_id, "booking_key": bkey, "type": kind, "status": "open", "purpose": purpose,
                          "detail": detail, "created_at": now_iso(), "needs_hr_review": True}}, upsert=True)


async def cancel_missed(reg_id: str, bkey: str, reason: str) -> int:
    return (await db().ai_live_mock_jobs.update_many(
        {"registration_id": reg_id, "booking_key": bkey, "purpose": MISSED, "status": {"$in": ["planned", "claimed", "needs_review"]}},
        {"$set": {"status": "cancelled", "reasons": [reason], "cancelled_at": now_iso()}})).modified_count


async def apply_outcome(job: dict, ex: dict) -> str:
    """Records alerts/suppression for one finished call. Never edits the booking or otp_verified."""
    rid, bkey, purpose = job["registration_id"], job["booking_key"], job.get("purpose", CONFIRM)
    out, real = outcome_of(purpose, ex), not rid.startswith("fixture:")
    if out == "DO_NOT_CALL" and real:
        from .consent import apply_ai_opt_out
        await apply_ai_opt_out(rid)
    elif out == "WRONG_NUMBER":
        await raise_alert(rid, "*", purpose, "WRONG_NUMBER", {})
        await db().ai_live_mock_jobs.update_many({"registration_id": rid, "status": {"$in": ["planned", "claimed"]}},
                                                 {"$set": {"status": "cancelled", "reasons": ["WRONG_NUMBER"]}})
    elif out == "RESCHEDULE_REQUESTED":
        await raise_alert(rid, bkey, purpose, "RESCHEDULE_REQUEST_PENDING",
                          {"preferred_reschedule_datetime": ex.get("preferred_reschedule_datetime"), "reason": ex.get("missed_interview_reason") or ex.get("rejection_reason")})
        await cancel_missed(rid, bkey, "RESCHEDULE_REQUEST_PENDING")
    elif out == "RUNNING_LATE":
        await raise_alert(rid, bkey, purpose, "RUNNING_LATE", {"expected_arrival_time": ex.get("expected_arrival_time")})
        await cancel_missed(rid, bkey, "RUNNING_LATE")
    elif out == "CLAIMS_ATTENDED":
        await raise_alert(rid, bkey, purpose, "CLAIMS_ATTENDED", {"attendance_dispute": True})
        await cancel_missed(rid, bkey, "CLAIMS_ATTENDED")
    return out


async def open_alerts(reg_ids: list) -> dict:
    """{registration_id: {booking_key|'*': [types]}} for open alerts that block calling."""
    out = {}
    async for a in db().ai_call_alerts.find({"registration_id": {"$in": reg_ids}, "status": "open"}):
        out.setdefault(a["registration_id"], {}).setdefault(a["booking_key"], []).append(a["type"])
    return out


def blocked_for(alerts: dict, bkey: str, purpose: str) -> list:
    types = list(alerts.get("*", []))
    if purpose == MISSED:
        types += [t for t in alerts.get(bkey, []) if t in MISSED_BLOCKING_ALERTS]
    return types


# ---------- admin routes ----------

@purposes_router.get("/scheduling")
async def get_scheduling(request: Request):
    await _auth(request)
    s = await get_settings()
    return {"interview_confirmation": {"enabled": s["confirm_enabled"], "offset_days": s["confirm_offset_days"], "offset_range": [1, 7],
                                       "max_retries": 1, "retry_minutes": s["confirm_retry_minutes"],
                                       "window": [s["confirm_window_start"], s["confirm_window_end"]]},
            "missed_interview_followup": {"enabled": s["missed_enabled"], "offset_minutes": s["missed_offset_minutes"],
                                          "offset_range_minutes": [60, 10080], "max_retries": 1, "retry_minutes": s["missed_retry_minutes"],
                                          "window": [s["missed_window_start"], s["missed_window_end"]],
                                          "followup_period_hours": s["missed_followup_hours"],
                                          "attendance_source": "Existing employee OTP verification (read-only)"},
            "capacity": {k: s[k] for k in ("live_daily_call_limit", "live_pilot_daily_cap", "live_max_concurrent_calls", "live_queue_capacity")}}


@purposes_router.put("/scheduling")
async def put_scheduling(request: Request, body: dict = Body(...)):  # noqa: B008
    user = await _auth(request)
    _csrf(request)
    upd = {}
    for k, v in body.items():
        if k not in SCHEDULING_KEYS:
            raise HTTPException(400, f"Unknown setting {k}")
        if not isinstance(v, SCHEDULING_KEYS[k]) or (SCHEDULING_KEYS[k] is int and isinstance(v, bool)):
            raise HTTPException(400, f"{k} has the wrong type")
        upd[k] = v
    limits = {"confirm_offset_days": (1, 7), "missed_offset_minutes": (60, 10080), "live_daily_call_limit": (0, 100000),
              "live_pilot_daily_cap": (0, 100000), "live_max_concurrent_calls": (1, 50), "live_queue_capacity": (1, 1000)}
    for k, (lo, hi) in limits.items():
        if k in upd and not lo <= upd[k] <= hi:
            raise HTTPException(400, f"{k} must be {lo}–{hi}")
    if not upd:
        raise HTTPException(400, "Nothing to update")
    before = await get_settings()
    await db().ai_call_settings.update_one({"_id": SETTINGS_ID}, {"$set": {**upd, "updated_at": now_iso()}})
    await db().ai_call_audit.insert_one({"action": "scheduling_updated", "by": user, "at": now_iso(),
                                         "detail": {k: {"from": before.get(k), "to": v} for k, v in upd.items()}})
    from .live_prep import replan_pending
    recalculated = await replan_pending(user)  # only planned/needs-review jobs; finished calls are never redialled
    return {**await get_scheduling(request), "recalculated": recalculated}


@purposes_router.get("/alerts")
async def list_alerts(request: Request, registration_id: str = None, status: str = "open"):
    await _auth(request)
    q = {"status": status} if status in ("open", "resolved") else {}
    if registration_id:
        q["registration_id"] = registration_id
    rows = await db().ai_call_alerts.find(q).sort("created_at", -1).to_list(500)
    return {"alerts": [{**{k: v for k, v in a.items() if k != "_id"}, "id": str(a["_id"])} for a in rows]}


@purposes_router.post("/alerts/{alert_id}/resolve")
async def resolve_alert(alert_id: str, request: Request, body: dict = Body(default={})):  # noqa: B008
    user = await _auth(request)
    _csrf(request)
    res = await db().ai_call_alerts.update_one({"_id": ObjectId(alert_id), "status": "open"} if ObjectId.is_valid(alert_id) else {"_id": None},
                                               {"$set": {"status": "resolved", "resolved_by": user, "resolved_at": now_iso(),
                                                         "resolution": str(body.get("note") or "")[:300]}})
    if not res.modified_count:
        raise HTTPException(404, "Open alert not found")
    await db().ai_call_audit.insert_one({"action": "alert_resolved", "by": user, "alert_id": alert_id, "at": now_iso()})
    return {"resolved": True}


__all__ = ["CONFIRM", "MISSED", "PURPOSES", "booking_key"]
