"""Phase 6: DRY-RUN interview-call planner. Never dispatches: this module does not import the Bolna client.

Reads ONLY the synthetic fixture collection `ai_dry_run_bookings` (same field names as bb_registrations)
and writes ONLY `ai_dry_run_jobs` / `ai_dry_run_state`. Planning runs only when an admin clicks.
"""
import uuid
from datetime import date, datetime, time, timedelta, timezone

from bson import ObjectId
from fastapi import APIRouter, HTTPException, Request
from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError

from .provider import _auth, _csrf
from .store import IST, db, get_settings, mask_phone, normalize_phone, now_iso

dryrun_router = APIRouter(prefix="/dry-run")
WARNING = "DRY RUN — NO PHONE CALLS WILL BE PLACED."
TRUTHY_OTP = (1, 1.0, "1", "1.0", True, "true", "True", "yes", "Yes")  # mirrors bb_modules.TRUTHY_OTP
BOOKED_STATUSES = ("Interview Scheduled",)  # set by bb_modules.submit_schedule (book + reschedule)
STATUS_REASON = {"Rejected": "REJECTED", "Attended": "ATTENDED", "Missed": "MISSED",
                 "Interview Not Scheduled": "NOT_BOOKED", "Cancelled": "CANCELLED"}
MIN_LEAD = timedelta(hours=2)
RETRY_GAP = timedelta(minutes=60)
LOCK_STALE = timedelta(minutes=5)


def _window(cfg: dict):
    s, e = cfg["call_window_start"], cfg["call_window_end"]
    return time.fromisoformat(s), time.fromisoformat(e)


def into_window(dt: datetime, cfg: dict) -> datetime:
    """Move dt FORWARD to the first permitted IST moment (owner choice: 'later', never earlier)."""
    ws, we = _window(cfg)
    dt = dt.astimezone(IST)
    if dt.time() < ws:
        return datetime.combine(dt.date(), ws, IST)
    if dt.time() >= we:
        return datetime.combine(dt.date() + timedelta(days=1), ws, IST)
    return dt


def _ceil5(dt: datetime) -> datetime:
    dt = dt.replace(second=0, microsecond=0) + timedelta(minutes=1)
    return dt + timedelta(minutes=(-dt.minute) % 5)


def interview_at(b: dict):
    d, t = str(b.get("schedule_date") or "").strip(), str(b.get("schedule_time") or "").strip()
    if not d or not t:
        return None
    return datetime.combine(date.fromisoformat(d), time.fromisoformat(t[:5]), IST)


def eligibility(b: dict) -> list:
    """Return exclusion reasons (empty = eligible), in the order a reviewer should read them."""
    r = []
    if b.get("superseded") is True:
        r.append("SUPERSEDED")
    if b.get("isTest") is True:
        r.append("TEST_RECORD")
    st = b.get("status") or ""
    if st not in BOOKED_STATUSES:
        r.append(STATUS_REASON.get(st, "MANUAL_ALERT_BOOKING" if st == "Scheduled" else "UNKNOWN_STATUS"))
    elif b.get("is_shortlisted") is not True:
        r.append("NOT_SHORTLISTED")
    if b.get("otp_verified") in TRUTHY_OTP and "ATTENDED" not in r:
        r.append("ATTENDED")
    if b.get("missed_marked") is True and "MISSED" not in r:
        r.append("MISSED")
    if b.get("ai_confirmation") == "CONFIRMED":
        r.append("ALREADY_CONFIRMED")
    if b.get("do_not_call") is True:
        r.append("DO_NOT_CALL")
    consent = (b.get("ai_call_consent") or {}).get("status")
    if consent != "granted":
        r.append({"refused": "CONSENT_REFUSED", "withdrawn": "CONSENT_WITHDRAWN"}.get(consent, "NO_CALLING_CONSENT"))
    try:
        normalize_phone(b.get("phone"))
    except ValueError:
        r.append("INVALID_PHONE")
    return r


def plan_booking(b: dict, now: datetime, cfg: dict) -> dict:
    """Pure function: compute status, reasons, original target, planned call and retry plan for one booking."""
    now = now.astimezone(IST)
    reasons = eligibility(b)
    out = {"reasons": reasons, "interview_at": None, "target_at": None, "planned_at": None, "adjustments": [],
           "short_notice": False, "retry": {"allowed_in_live": int(cfg.get("live_retry_no_answer", 1)), "eligible": False,
                                            "planned_at": None, "executed": False}}
    try:
        iv = interview_at(b)
    except ValueError:
        iv, reasons = None, reasons + ["INVALID_SCHEDULE"]
    if iv is None:
        out["reasons"] = reasons if "INVALID_SCHEDULE" in reasons else reasons + ["NO_SCHEDULE"]
        out["status"] = "SKIPPED"
        return out
    out["interview_at"] = iv.isoformat()
    if iv <= now:
        out["reasons"], out["status"] = reasons + ["INTERVIEW_PASSED"], "SKIPPED"
        return out
    target = iv - timedelta(hours=int(cfg.get("live_call_hours_before", 24)))
    out["target_at"] = target.isoformat()
    planned = target
    if target < now:
        out["short_notice"] = True
        planned = _ceil5(now)
        out["adjustments"].append("Booked less than 24 h ahead: next permitted time after now")
    moved = into_window(planned, cfg)
    if moved != planned:
        out["adjustments"].append(f"Moved forward into the {cfg['call_window_start']}–{cfg['call_window_end']} IST window")
    planned = moved
    out["planned_at"] = planned.isoformat()
    if reasons:
        out["status"], out["planned_at"] = "SKIPPED", None
        return out
    if iv - planned < MIN_LEAD:
        out["reasons"], out["status"] = ["INSUFFICIENT_LEAD_TIME"], "NEEDS_REVIEW"
        return out
    retry = into_window(planned + RETRY_GAP, cfg)
    if out["retry"]["allowed_in_live"] > 0 and iv - retry >= MIN_LEAD:
        out["retry"].update(eligible=True, planned_at=retry.isoformat())
    out["status"] = "SCHEDULED"
    return out


def booking_key(b: dict) -> str:
    """Changes whenever the interview slot changes, so outdated plans are invalidated."""
    return f"{b.get('schedule_date') or ''}|{str(b.get('schedule_time') or '')[:5]}|{int(b.get('reschedule_count') or 0)}"


async def ensure_dry_run_indexes():
    await db().ai_dry_run_jobs.create_index([("booking_id", 1), ("booking_key", 1)], unique=True)
    await db().ai_dry_run_jobs.create_index("status")


async def _acquire(run_id: str):
    stale = (datetime.now(timezone.utc) - LOCK_STALE).isoformat()
    await db().ai_dry_run_state.update_one({"_id": "planner"}, {"$setOnInsert": {"lock": None}}, upsert=True)
    return await db().ai_dry_run_state.find_one_and_update(
        {"_id": "planner", "$or": [{"lock": None}, {"lock.at": {"$lt": stale}}]},
        {"$set": {"lock": {"id": run_id, "at": now_iso()}}}, return_document=ReturnDocument.AFTER)


async def run_planning(user: str, now: datetime = None) -> dict:
    run_id = uuid.uuid4().hex
    if not await _acquire(run_id):
        raise HTTPException(409, "Dry-run planning is already running")
    try:
        now = now or datetime.now(IST)
        cfg = await get_settings()
        bookings = await db().ai_dry_run_bookings.find({"synthetic": True}).to_list(2000)
        counts = {"SCHEDULED": 0, "SKIPPED": 0, "NEEDS_REVIEW": 0, "INVALIDATED": 0}
        live_keys = {}
        for b in bookings:
            bid, key = str(b["_id"]), booking_key(b)
            live_keys[bid] = key
            p = plan_booking(b, now, cfg)
            counts[p["status"]] += 1
            doc = {"mode": "DRY_RUN", "dry_run": True, "status": p["status"], "reasons": p["reasons"],
                   "candidate_name": b.get("full_name"), "phone_masked": _mask(b.get("phone")), "job_role": b.get("job_role"),
                   "interview_at": p["interview_at"], "target_at": p["target_at"], "planned_at": p["planned_at"],
                   "adjustments": p["adjustments"], "short_notice": p["short_notice"], "retry": p["retry"],
                   "reschedule_count": int(b.get("reschedule_count") or 0), "last_run_id": run_id, "updated_at": now_iso()}
            try:
                await db().ai_dry_run_jobs.update_one(
                    {"booking_id": bid, "booking_key": key},
                    {"$set": doc, "$setOnInsert": {"created_at": now_iso(), "attempt": 1}, "$inc": {"times_planned": 1}},
                    upsert=True)
            except DuplicateKeyError:
                pass  # concurrent upsert of the same (booking, slot): already planned
            res = await db().ai_dry_run_jobs.update_many(
                {"booking_id": bid, "booking_key": {"$ne": key}, "status": {"$ne": "INVALIDATED"}},
                {"$set": {"status": "INVALIDATED", "reasons": ["RESCHEDULED"], "invalidated_at": now_iso()}})
            counts["INVALIDATED"] += res.modified_count
        res = await db().ai_dry_run_jobs.update_many(
            {"booking_id": {"$nin": list(live_keys)}, "status": {"$ne": "INVALIDATED"}},
            {"$set": {"status": "INVALIDATED", "reasons": ["BOOKING_REMOVED"], "invalidated_at": now_iso()}})
        counts["INVALIDATED"] += res.modified_count
        summary = {"run_id": run_id, "at": now_iso(), "by": user, "bookings": len(bookings), "counts": counts,
                   "eligible": counts["SCHEDULED"], "ineligible": counts["SKIPPED"] + counts["NEEDS_REVIEW"]}
        await db().ai_dry_run_state.update_one({"_id": "planner"}, {"$set": {"last_run": summary}})
        return summary
    finally:
        await db().ai_dry_run_state.update_one({"_id": "planner", "lock.id": run_id}, {"$set": {"lock": None}})


async def claim_due_dry_run_job(now: datetime, worker: str):
    """Future-phase claim design (atomic, single owner). Only marks DRY_RUN jobs SIMULATED — never dispatches."""
    return await db().ai_dry_run_jobs.find_one_and_update(
        {"mode": "DRY_RUN", "status": "SCHEDULED", "planned_at": {"$lte": now.astimezone(IST).isoformat()}},
        {"$set": {"status": "SIMULATED_CLAIMED", "claimed_by": worker, "claimed_at": now_iso()}},
        sort=[("planned_at", 1)], return_document=ReturnDocument.AFTER)


def _mask(p) -> str:
    try:
        return mask_phone(normalize_phone(p))
    except ValueError:
        return "invalid"


def _fixtures(now: datetime) -> list:
    """Synthetic bookings only (fake names, +91 90000 000xx numbers, example.invalid emails)."""
    d = lambda days: (now + timedelta(days=days)).date().isoformat()  # noqa: E731
    soon = now + timedelta(hours=5)
    granted = {"status": "granted", "source": "synthetic_fixture", "at": now_iso(), "withdrawn_at": None}
    base = {"synthetic": True, "status": "Interview Scheduled", "is_shortlisted": True, "otp_verified": False,
            "missed_marked": False, "superseded": False, "reschedule_count": 0, "isTest": False,
            "job_role": "Data Analyst", "ai_call_consent": granted, "do_not_call": False}
    rows = [
        ("Synthetic A — 3 days ahead", {"schedule_date": d(3), "schedule_time": "11:00:00"}),
        ("Synthetic B — 9 AM interview", {"schedule_date": d(3), "schedule_time": "09:00:00"}),
        ("Synthetic C — evening interview", {"schedule_date": d(3), "schedule_time": "20:30:00"}),
        ("Synthetic D — short notice", {"schedule_date": soon.date().isoformat(), "schedule_time": soon.strftime("%H:%M:00")}),
        ("Synthetic E — rescheduled", {"schedule_date": d(4), "schedule_time": "14:00:00", "reschedule_count": 1}),
        ("Synthetic F — no consent", {"schedule_date": d(3), "schedule_time": "12:00:00", "ai_call_consent": None}),
        ("Synthetic G — consent withdrawn", {"schedule_date": d(3), "schedule_time": "12:00:00",
                                             "ai_call_consent": {**granted, "status": "withdrawn", "withdrawn_at": now_iso()}}),
        ("Synthetic H — opted out", {"schedule_date": d(3), "schedule_time": "12:00:00", "do_not_call": True}),
        ("Synthetic I — invalid phone", {"schedule_date": d(3), "schedule_time": "12:00:00", "phone": "12345"}),
        ("Synthetic J — superseded", {"schedule_date": d(3), "schedule_time": "12:00:00", "superseded": True}),
        ("Synthetic K — attended", {"schedule_date": d(-1), "schedule_time": "11:00:00", "status": "Attended", "otp_verified": True}),
        ("Synthetic L — already confirmed", {"schedule_date": d(3), "schedule_time": "15:00:00", "ai_confirmation": "CONFIRMED"}),
        ("Synthetic M — cancelled", {"schedule_date": d(3), "schedule_time": "16:00:00", "status": "Cancelled"}),
        ("Synthetic N — not booked", {"schedule_date": None, "schedule_time": None, "status": "Interview Not Scheduled"}),
        ("Synthetic O — too close to call", {"schedule_date": (now + timedelta(minutes=90)).date().isoformat(),
                                             "schedule_time": (now + timedelta(minutes=90)).strftime("%H:%M:00")}),
    ]
    out = []
    for i, (name, extra) in enumerate(rows, start=1):
        out.append({**base, "full_name": name, "email": f"synthetic{i:02d}@example.invalid",
                    "phone": f"+9190000000{i:02d}", **extra, "created_at": now_iso()})
    return out


@dryrun_router.post("/fixtures/seed")
async def seed_fixtures(request: Request):
    await _auth(request)
    _csrf(request)
    await db().ai_dry_run_bookings.delete_many({"synthetic": True})
    res = await db().ai_dry_run_bookings.insert_many(_fixtures(datetime.now(IST)))
    return {"seeded": len(res.inserted_ids)}


@dryrun_router.post("/fixtures/{booking_id}/reschedule")
async def simulate_reschedule(booking_id: str, request: Request):
    await _auth(request)
    _csrf(request)
    b = await db().ai_dry_run_bookings.find_one({"_id": ObjectId(booking_id), "synthetic": True}) if ObjectId.is_valid(booking_id) else None
    if not b or not b.get("schedule_date"):
        raise HTTPException(404, "Synthetic booking not found")
    new_date = (date.fromisoformat(b["schedule_date"]) + timedelta(days=1)).isoformat()
    await db().ai_dry_run_bookings.update_one({"_id": b["_id"]}, {"$set": {"schedule_date": new_date},
                                                                  "$inc": {"reschedule_count": 1}})
    return {"rescheduled_to": new_date}


@dryrun_router.post("/plan")
async def plan(request: Request):
    user = await _auth(request)
    _csrf(request)
    return await run_planning(user)


@dryrun_router.get("/preview")
async def preview(request: Request):
    await _auth(request)
    state = await db().ai_dry_run_state.find_one({"_id": "planner"}) or {}
    jobs = await db().ai_dry_run_jobs.find({}).sort([("status", 1), ("planned_at", 1)]).to_list(500)
    fixtures = await db().ai_dry_run_bookings.find({"synthetic": True}, {"_id": 1, "full_name": 1}).to_list(2000)
    cfg = await get_settings()
    return {"warning": WARNING, "last_run": state.get("last_run"), "planning_in_progress": bool(state.get("lock")),
            "fixtures": len(fixtures), "jobs": [{**{k: v for k, v in j.items() if k != "_id"}, "id": str(j["_id"])} for j in jobs],
            "rules": {"hours_before": cfg["live_call_hours_before"], "window": f"{cfg['call_window_start']}–{cfg['call_window_end']} IST",
                      "min_lead_hours": MIN_LEAD.total_seconds() / 3600, "retry_gap_minutes": RETRY_GAP.total_seconds() / 60,
                      "no_answer_retries_in_live": cfg["live_retry_no_answer"]}}
