"""Live scheduler + dispatch worker for both calling purposes, MOCK ONLY.

Jobs live in `ai_live_mock_jobs` (dispatchable=False, purpose = interview_confirmation | missed_interview_followup)
and are never visible to the real dispatcher. MockProvider never touches the network; BolnaLiveProvider refuses.
Nothing runs in the background: planning and worker runs happen only on an admin click (or in tests).
"""
import os
import uuid
from datetime import datetime, timedelta, timezone

from bson import ObjectId
from fastapi import APIRouter, Body, HTTPException, Request
from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError, OperationFailure

from . import gate
from .dryrun import MIN_LEAD, _mask, booking_key, eligibility, interview_at
from .execution import ALL_FIELDS, spoken_date, spoken_time
from .modes import LIVE_DISPATCH_IMPLEMENTED, deployment_approved, effective, live_daily_cap, overall_test_mode
from .provider import _auth, _csrf
from .purposes import (CONFIRM, MISSED, PURPOSES, RETRY_OUTCOMES, apply_outcome, blocked_for, missed_deadline,
                       missed_eligibility, open_alerts, otp_state, plan_for, purpose_cfg, retry_at)
from .store import IST, db, get_settings, mask_phone, normalize_phone, now_iso

live_prep_router = APIRouter(prefix="/live-prep")
WARNING = "MOCK ONLY — NO PHONE CALLS WILL BE PLACED. Jobs are non-dispatchable."
SOURCES = {"bb_registrations": "bb_registrations", "fixtures": "ai_dry_run_bookings"}
LEASE = timedelta(minutes=5)
OUTCOMES = ("CONFIRMED", "MISSED_CONFIRMED", "RUNNING_LATE", "CLAIMS_ATTENDED", "RESCHEDULE_REQUESTED", "DECLINED",
            "DO_NOT_CALL", "UNKNOWN", "WRONG_NUMBER", "no_answer", "busy", "timeout", "failed")
EXTRACTION_FIELDS = tuple(ALL_FIELDS)
GLOBAL_KEYS = ("dispatch_implemented", "server_enabled", "emergency_stop_off", "effective_live", "authorized",
               "deployment_approved")
STALE_AFTER = timedelta(minutes=30)  # a due job older than this is never dialled late (kept for review)
ACTIVE = ["planned", "claimed", "needs_review"]


class MockProvider:
    """Simulates Bolna. Never touches the network."""
    name = "mock"

    async def place(self, gate_: dict, body: dict, outcome: str) -> dict:
        return {"execution_id": f"mock_{uuid.uuid4().hex[:16]}", "status": outcome, "request_sent": False, "body": body}


class BolnaLiveProvider:
    """Future real provider. Refuses before any network I/O unless every gate allows a real Live call."""
    name = "bolna"

    async def place(self, gate_: dict, body: dict, outcome: str = None) -> dict:
        if not (LIVE_DISPATCH_IMPLEMENTED and gate_.get("allowed_live")):
            raise PermissionError("Live dispatch is disabled in this phase")
        raise PermissionError("Real Live dispatch is not implemented")


def worker_enabled() -> bool:
    return LIVE_DISPATCH_IMPLEMENTED and os.environ.get("AI_LIVE_WORKER_ENABLED", "false").strip().lower() == "true"


def start_live_worker() -> bool:
    """Never called on startup. Always refuses (no real worker loop exists)."""
    return False


async def ensure_live_prep_indexes():
    try:
        await db().ai_live_mock_jobs.drop_index("registration_id_1_booking_key_1_attempt_1")  # superseded by the purpose-aware key
    except OperationFailure:
        pass
    await db().ai_live_mock_jobs.create_index([("registration_id", 1), ("booking_key", 1), ("purpose", 1), ("attempt", 1)], unique=True)
    await db().ai_live_mock_jobs.create_index([("status", 1), ("planned_at", 1), ("interview_at", 1)])
    await db().ai_call_alerts.create_index([("registration_id", 1), ("status", 1)])


def _iso(dt: datetime) -> str:
    return dt.astimezone(IST).isoformat()


def _with_consent(r: dict, c: dict, alerts: dict) -> dict:
    return {**r, "ai_call_consent": {"status": c.get("consent_status"), "text_version": c.get("consent_text_version"),
                                     "scope": c.get("consent_scope")},
            "do_not_call": c.get("do_not_call") is True, "_alerts": alerts}


async def _bookings(source: str) -> list:
    """(registration_id, booking-with-consent) pairs. Real consent always comes from ai_candidate_consents."""
    if source == "fixtures":
        docs = await db().ai_dry_run_bookings.find({"synthetic": True}).to_list(5000)
        return [(f"fixture:{d['_id']}", {**d, "_alerts": {}}) for d in docs]
    regs = await db().bb_registrations.find({"schedule_date": {"$nin": [None, ""]}}).to_list(20000)
    ids = [str(r["_id"]) for r in regs]
    cons = {c["registration_id"]: c async for c in db().ai_candidate_consents.find({"registration_id": {"$in": ids}})}
    alerts = await open_alerts(ids)
    return [(str(r["_id"]), _with_consent(r, cons.get(str(r["_id"]), {}), alerts.get(str(r["_id"]), {}))) for r in regs]


async def _load_one(job: dict):
    rid = job["registration_id"]
    if rid.startswith("fixture:"):
        oid = rid.split(":", 1)[1]
        d = await db().ai_dry_run_bookings.find_one({"_id": ObjectId(oid)}) if ObjectId.is_valid(oid) else None
        return {**d, "_alerts": {}} if d else None
    if not ObjectId.is_valid(rid):
        return None
    reg = await db().bb_registrations.find_one({"_id": ObjectId(rid)})
    if not reg:
        return None
    c = await db().ai_candidate_consents.find_one({"registration_id": rid}) or {}
    return _with_consent(reg, c, (await open_alerts([rid])).get(rid, {}))


def _prep(b: dict, purpose: str) -> dict:
    return {**b, "blocked_alerts": blocked_for(b.get("_alerts") or {}, booking_key(b), purpose)}


def _snapshot(b: dict) -> dict:
    return {k: b.get(k) for k in ("schedule_date", "schedule_time", "reschedule_count", "superseded")}


async def _acquire(run_id: str):
    stale = (datetime.now(timezone.utc) - LEASE).isoformat()
    await db().ai_dry_run_state.update_one({"_id": "live_prep_planner"}, {"$setOnInsert": {"lock": None}}, upsert=True)
    return await db().ai_dry_run_state.find_one_and_update(
        {"_id": "live_prep_planner", "$or": [{"lock": None}, {"lock.at": {"$lt": stale}}]},
        {"$set": {"lock": {"id": run_id, "at": now_iso()}}}, return_document=ReturnDocument.AFTER)


async def _plan_one(rid: str, b: dict, purpose: str, now: datetime, cfg: dict, user: str, run_id: str, source: str, counts: dict):
    key, p = booking_key(b), plan_for(purpose, _prep(b, purpose), now, cfg)
    q = {"registration_id": rid, "purpose": purpose}
    counts["invalidated"] += (await db().ai_live_mock_jobs.update_many(
        {**q, "booking_key": {"$ne": key}, "status": {"$in": ACTIVE}},
        {"$set": {"status": "invalidated", "reasons": ["RESCHEDULED"], "invalidated_at": now_iso()}})).modified_count
    if p["status"] == "SKIPPED":
        st = "cancelled" if "ATTENDED_OTP_VERIFIED" in p["reasons"] else "invalidated"
        counts["invalidated"] += (await db().ai_live_mock_jobs.update_many(
            {**q, "status": {"$in": ACTIVE}}, {"$set": {"status": st, "reasons": p["reasons"], "invalidated_at": now_iso()}})).modified_count
        counts["skipped"] += 1
        return
    status = "planned" if p["status"] == "SCHEDULED" else "needs_review"
    doc = {"mode": "live_mock", "dispatchable": False, "source": source, "purpose": purpose, "registration_id": rid,
           "booking_key": key, "attempt": 1, "status": status, "reasons": p["reasons"], "planned_at": p["planned_at"],
           "target_at": p["target_at"], "interview_at": p["interview_at"], "adjustments": p["adjustments"],
           "snapshot": _snapshot(b), "candidate_name": b.get("full_name"), "phone_masked": _mask(b.get("phone")),
           "job_role": b.get("job_role"), "provider_request_sent": False, "mode_version": cfg["mode_version"],
           "created_by": user, "created_at": now_iso(), "run_id": run_id}
    try:
        r = await db().ai_live_mock_jobs.update_one({**q, "booking_key": key, "attempt": 1}, {"$setOnInsert": doc}, upsert=True)
    except DuplicateKeyError:
        counts["unchanged"] += 1
        return
    if r.upserted_id:
        counts[status] += 1
        return
    # existing attempt-1 job still waiting: recalculate safely (settings may have changed); finished jobs never change
    r2 = await db().ai_live_mock_jobs.update_one(
        {**q, "booking_key": key, "attempt": 1, "status": {"$in": ["planned", "needs_review"]},
         "$or": [{"planned_at": {"$ne": p["planned_at"]}}, {"status": {"$ne": status}}]},
        {"$set": {"status": status, "reasons": p["reasons"], "planned_at": p["planned_at"], "target_at": p["target_at"],
                  "recalculated_at": now_iso()}})
    counts["recalculated" if r2.modified_count else "unchanged"] += 1


async def plan_live(user: str, source: str = "bb_registrations", now: datetime = None) -> dict:
    """Idempotent: one job per (registration, booking slot, purpose, attempt). Reschedules/ineligibility invalidate."""
    if source not in SOURCES:
        raise HTTPException(400, "source must be bb_registrations or fixtures")
    run_id = uuid.uuid4().hex
    if not await _acquire(run_id):
        raise HTTPException(409, "Planning is already running")
    try:
        now, cfg = (now or datetime.now(IST)), await get_settings()
        counts = {"planned": 0, "needs_review": 0, "skipped": 0, "invalidated": 0, "unchanged": 0, "recalculated": 0}
        seen = []
        purposes = [p for p in PURPOSES if purpose_cfg(cfg, p)["enabled"]]
        for rid, b in await _bookings(source):
            seen.append(rid)
            for purpose in purposes:
                await _plan_one(rid, b, purpose, now, cfg, user, run_id, source, counts)
        for purpose in set(PURPOSES) - set(purposes):
            counts["invalidated"] += (await db().ai_live_mock_jobs.update_many(
                {"source": source, "purpose": purpose, "status": {"$in": ["planned", "claimed"]}},
                {"$set": {"status": "invalidated", "reasons": ["PURPOSE_DISABLED"]}})).modified_count
        counts["invalidated"] += (await db().ai_live_mock_jobs.update_many(
            {"source": source, "registration_id": {"$nin": seen}, "status": {"$in": ACTIVE}},
            {"$set": {"status": "invalidated", "reasons": ["BOOKING_REMOVED"], "invalidated_at": now_iso()}})).modified_count
        out = {"run_id": run_id, "source": source, "counts": counts, "at": now_iso(), "by": user, "warning": WARNING}
        await db().ai_dry_run_state.update_one({"_id": "live_prep_planner"}, {"$set": {"last_run": {k: v for k, v in out.items() if k != "warning"}}})
        return out
    finally:
        await db().ai_dry_run_state.update_one({"_id": "live_prep_planner", "lock.id": run_id}, {"$set": {"lock": None}})


async def replan_pending(user: str) -> dict:
    out = {}
    for src in await db().ai_live_mock_jobs.distinct("source", {"status": {"$in": ["planned", "needs_review"]}}):
        out[src] = (await plan_live(user, src))["counts"]
    return out


async def gate_job(job: dict, now: datetime, overall: bool = None, b: dict = None) -> dict:
    """Full pre-dispatch checklist, run immediately before any (mock) dispatch."""
    s = await get_settings()
    purpose = job.get("purpose", CONFIRM)
    pc = purpose_cfg(s, purpose)
    overall = overall_test_mode() if overall is None else overall
    checks = []

    def add(key, label, ok, detail=""):
        checks.append({"key": key, "label": label, "ok": bool(ok), "detail": detail, "global": key in GLOBAL_KEYS})

    from .provider import provider_ready
    add("dispatch_implemented", "Live dispatch enabled in code", LIVE_DISPATCH_IMPLEMENTED)
    add("server_enabled", "Server calling enabled", gate.server_calling_enabled())
    add("emergency_stop_off", "Emergency Stop is OFF", not s["emergency_stop"])
    add("effective_live", "Effective mode permits Live calls", effective(overall, s["ai_test_enabled"], s["ai_live_enabled"])["live_calls"])
    add("authorized", "Live Dispatch Authorization active", s.get("live_dispatch_authorized"))
    add("deployment_approved", "Production deployment approved", deployment_approved())
    add("purpose_enabled", f"{purpose} is enabled", pc["enabled"])
    b = b if b is not None else await _load_one(job)
    add("booking_exists", "Booking found by exact registration ID", b is not None)
    if b:
        bp = _prep(b, purpose)
        iv = interview_at(b)
        add("snapshot", "Interview schedule unchanged", booking_key(b) == job["booking_key"] and _snapshot(b) == job["snapshot"])
        add("not_dnc", "Do Not Call is false", b.get("do_not_call") is not True)
        if purpose == MISSED:
            reasons = missed_eligibility(bp)
            add("eligible", "Booking eligible for follow-up", not reasons, ", ".join(reasons))
            add("otp_not_verified", "Employee OTP attendance not verified (re-read now)", otp_state(b) == "not_verified", otp_state(b))
            add("delay_passed", "Configured delay after the interview has passed", iv is not None and now >= iv + pc["offset"])
            add("within_period", "Within the follow-up period", iv is not None and now <= missed_deadline(iv, pc))
        else:
            reasons = eligibility({**bp, "do_not_call": b.get("do_not_call") or "WRONG_NUMBER" in bp["blocked_alerts"]})
            reasons = [r for r in reasons if r not in ("NO_CALLING_CONSENT",)] + (
                [] if _consent_ok(b, CONFIRM) else ["NO_CALLING_CONSENT"])
            add("eligible", "Booking eligible", not reasons, ", ".join(reasons))
            add("consent", "AI calling consent valid", _consent_ok(b, CONFIRM))
            add("lead_time", "At least 2 hours before the interview", iv is not None and iv - now >= MIN_LEAD)
    ws, we = pc["call_window_start"], pc["call_window_end"]
    add("window", "Inside the calling window (IST)", ws <= now.astimezone(IST).strftime("%H:%M") < we, f"{ws}–{we}")
    dup = await db().ai_live_mock_jobs.find_one({"registration_id": job["registration_id"], "booking_key": job["booking_key"],
                                                 "purpose": purpose, "_id": {"$ne": job["_id"]},
                                                 "status": {"$in": ["claimed", "mock_dispatched", "pending_reconciliation"]}})
    add("no_duplicate", "No other active call for this booking and purpose", dup is None)
    prov = await db().ai_provider_settings.find_one({"_id": "bolna"}) or {}
    add("provider_verified", "Bolna configuration verified", provider_ready(prov))
    booking_ok = all(c["ok"] for c in checks if not c["global"] and c["key"] != "provider_verified")
    return {"allowed_live": all(c["ok"] for c in checks), "booking_ok": booking_ok, "checks": checks,
            "mock_bypassed": [c["key"] for c in checks if c["global"] and not c["ok"]]}


def _consent_ok(b: dict, purpose: str) -> bool:
    from .purposes import consent_covers
    return consent_covers(b.get("ai_call_consent"), purpose)


async def _reserve(counter_id: str, field: str, cap: int) -> bool:
    await db().ai_live_counters.update_one({"_id": counter_id}, {"$setOnInsert": {field: 0}}, upsert=True)
    return bool(await db().ai_live_counters.find_one_and_update({"_id": counter_id, field: {"$lt": cap}}, {"$inc": {field: 1}}))


async def _release_slot():
    await db().ai_live_counters.update_one({"_id": "mock:concurrency", "active": {"$gt": 0}}, {"$inc": {"active": -1}})


def user_data_for_registration(b: dict, cfg: dict, purpose: str = CONFIRM) -> dict:
    """The six dynamic variables + call_purpose, from the exact booking only."""
    return {"candidate_name": b.get("full_name") or "", "company_name": cfg.get("default_company_name") or "BluBridge",
            "job_role": b.get("job_role") or "", "interview_date": spoken_date(str(b["schedule_date"])[:10]),
            "interview_time": spoken_time(str(b["schedule_time"])[:5]), "office_address": cfg.get("default_office_address") or "",
            "call_purpose": purpose}


def live_call_record(job: dict, b: dict, user_data: dict, execution_id: str) -> dict:
    """Shape of a future Live ai_calls document (Candidate Profile compatible). Not inserted while mock-only."""
    try:
        phone = normalize_phone(b.get("phone"))
    except ValueError:
        phone = ""
    return {"mode": "live", "purpose": job.get("purpose", CONFIRM), "registration_id": job["registration_id"],
            "booking_key": job["booking_key"], "booking_snapshot": job["snapshot"], "job_id": str(job["_id"]), "attempt": job["attempt"],
            "candidate_name": b.get("full_name"), "phone_masked": mask_phone(phone), "job_role": b.get("job_role"),
            "interview_date": b.get("schedule_date"), "interview_time": str(b.get("schedule_time") or "")[:5],
            "user_data": user_data, "execution_id": execution_id, "state": "dispatching", "status": "",
            "transcript": None, "recording_ref": None, "extracted": {k: None for k in EXTRACTION_FIELDS}, "created_at": now_iso()}


def _mock_extraction(purpose: str, outcome: str) -> dict:
    ex = {k: None for k in EXTRACTION_FIELDS}
    if outcome in ("no_answer", "busy", "timeout", "failed"):
        return ex
    if purpose == MISSED:
        ex.update(attendance_status="DO_NOT_CALL" if outcome == "DO_NOT_CALL" else "UNKNOWN",
                  missed_interview_outcome=outcome if outcome != "CONFIRMED" else "MISSED_CONFIRMED",
                  attendance_dispute=outcome == "CLAIMS_ATTENDED",
                  expected_arrival_time="11:30 AM" if outcome == "RUNNING_LATE" else None,
                  wants_reschedule=outcome == "RESCHEDULE_REQUESTED",
                  preferred_reschedule_datetime="tomorrow 3 PM" if outcome == "RESCHEDULE_REQUESTED" else None,
                  missed_interview_reason="Simulated reason")
    else:
        ex.update(attendance_status=outcome if outcome in ("CONFIRMED", "RESCHEDULE_REQUESTED", "DECLINED", "DO_NOT_CALL", "WRONG_NUMBER") else "UNKNOWN",
                  wants_reschedule=outcome == "RESCHEDULE_REQUESTED", requested_virtual=False,
                  preferred_reschedule_datetime="tomorrow 3 PM" if outcome == "RESCHEDULE_REQUESTED" else None)
    ex["call_summary"] = f"Simulated {purpose} outcome: {outcome}"
    return ex


async def expire_backlog(now: datetime) -> int:
    """Due jobs more than 30 min late are never dialled late; kept as NEEDS_REVIEW (not deleted)."""
    return (await db().ai_live_mock_jobs.update_many(
        {"status": "planned", "planned_at": {"$lt": _iso(now - STALE_AFTER)}},
        {"$set": {"status": "needs_review", "reasons": ["STALE_BACKLOG"], "expired_at": now_iso()}})).modified_count


async def _cancel(jid, reason: str):
    await db().ai_live_mock_jobs.update_one({"_id": jid}, {"$set": {"status": "cancelled", "reasons": [reason], "lease_until": None}})


async def mock_tick(worker: str, now: datetime = None, outcome: str = "CONFIRMED", overall: bool = None,
                    provider=None, job_id: str = None) -> dict:
    """One worker iteration: recover → expire backlog → claim (earliest due, closest interview) → gate →
    reserve limits → OTP re-read → (mock) dispatch → outcome handling. Never dials."""
    if outcome not in OUTCOMES:
        raise HTTPException(400, f"outcome must be one of {', '.join(OUTCOMES)}")
    provider = provider or MockProvider()
    now = (now or datetime.now(IST)).astimezone(IST)
    recovered, expired = await recover_stale(now), await expire_backlog(now)
    q = {"mode": "live_mock", "dispatchable": False, "status": "planned", "planned_at": {"$lte": _iso(now)}}
    if job_id:
        q["_id"] = ObjectId(job_id) if ObjectId.is_valid(job_id) else None
    job = await db().ai_live_mock_jobs.find_one_and_update(
        q, {"$set": {"status": "claimed", "claimed_by": worker, "claimed_at": now_iso(), "lease_until": _iso(now + LEASE)}},
        sort=[("planned_at", 1), ("interview_at", 1)], return_document=ReturnDocument.AFTER)
    base = {"recovered": recovered, "expired_backlog": expired, "warning": WARNING}
    if not job:
        return {"claimed": None, **base}
    jid, purpose = job["_id"], job.get("purpose", CONFIRM)
    g = await gate_job(job, now, overall)
    if not g["booking_ok"]:
        failed = [c["key"] for c in g["checks"] if not c["ok"] and not c["global"]]
        if "otp_not_verified" in failed and any(c["key"] == "otp_not_verified" and c["detail"] == "verified" for c in g["checks"]):
            await _cancel(jid, "OTP_VERIFIED")
            return {"claimed": str(jid), "result": "cancelled_otp_verified", "gate": g, **base}
        st = "deferred" if set(failed) <= {"window", "no_duplicate", "delay_passed"} else "invalidated"
        await db().ai_live_mock_jobs.update_one({"_id": jid}, {"$set": {
            "status": "planned" if st == "deferred" else "invalidated", "reasons": [f.upper() for f in failed],
            "last_gate": g, "lease_until": None}})
        return {"claimed": str(jid), "result": st, "gate": g, **base}
    s = await get_settings()
    if not await _reserve("mock:concurrency", "active", int(s["live_max_concurrent_calls"])):
        await db().ai_live_mock_jobs.update_one({"_id": jid}, {"$set": {"status": "planned", "reasons": ["CONCURRENCY_LIMIT"], "lease_until": None}})
        return {"claimed": str(jid), "result": "concurrency_limit", "gate": g, **base}
    if not await _reserve(f"mock:daily:{now.date().isoformat()}", "count", live_daily_cap(s)):
        await _release_slot()
        await db().ai_live_mock_jobs.update_one({"_id": jid}, {"$set": {"status": "planned", "reasons": ["DAILY_LIMIT"], "lease_until": None}})
        return {"claimed": str(jid), "result": "daily_limit", "gate": g, **base}
    try:
        b = await _load_one(job)  # final re-read immediately before the provider request
        if purpose == MISSED and (b is None or otp_state(b) != "not_verified"):
            await _release_slot()
            await _cancel(jid, "OTP_VERIFIED" if b and otp_state(b) == "verified" else "ATTENDANCE_UNKNOWN")
            return {"claimed": str(jid), "result": "cancelled_otp_verified", "gate": g, **base}
        ud = user_data_for_registration(b, s, purpose)
        res = await provider.place(g, {"user_data": {**ud, "registration_id": job["registration_id"]}}, outcome)
        rec = live_call_record(job, b, ud, res["execution_id"])
        rec.update(mock=True, provider_status=outcome if outcome in ("no_answer", "busy", "failed", "timeout") else "completed",
                   extracted=_mock_extraction(purpose, outcome), request_body_user_data=res["body"]["user_data"])
        status = {"no_answer": "no_answer", "busy": "busy", "timeout": "pending_reconciliation", "failed": "failed"}.get(outcome, "completed")
        rec["confirmed_attendance"] = purpose == CONFIRM and status == "completed" and outcome == "CONFIRMED"
        await db().ai_live_mock_jobs.update_one({"_id": jid}, {"$set": {
            "status": status, "mock_call": rec, "last_gate": g, "provider_request_sent": False, "finished_at": now_iso(), "lease_until": None}})
    except Exception:
        await _release_slot()
        await db().ai_live_mock_jobs.update_one({"_id": jid}, {"$set": {"status": "needs_review", "reasons": ["WORKER_ERROR"], "lease_until": None}})
        raise
    if status != "pending_reconciliation":  # an uncertain call keeps its slot and counts until reconciled; never redialled
        await _release_slot()
    applied = await apply_outcome(job, rec["extracted"]) if status == "completed" else None
    retry = await _plan_retry(job, now, s) if status in RETRY_OUTCOMES else None
    return {"claimed": str(jid), "result": status, "outcome": applied, "retry_job": retry, "gate": g,
            "provider_request_sent": False, "user_data": rec["request_body_user_data"], **base}


async def _plan_retry(job: dict, now: datetime, s: dict):
    """At most ONE retry, only after a provider-confirmed no-answer/busy, re-gated when it becomes due."""
    if job["attempt"] >= 2:
        return None
    at = retry_at(job.get("purpose", CONFIRM), job, now, s)
    if at is None:
        await db().ai_live_mock_jobs.update_one({"_id": job["_id"]}, {"$set": {"retry_skipped": "OUTSIDE_ALLOWED_PERIOD"}})
        return None
    doc = {k: v for k, v in job.items() if k not in ("_id", "claimed_by", "claimed_at", "lease_until", "mock_call", "last_gate")}
    doc.update(attempt=job["attempt"] + 1, status="planned", planned_at=_iso(at), reasons=["NO_ANSWER_RETRY"],
               created_at=now_iso(), retry_of=str(job["_id"]))
    try:
        return str((await db().ai_live_mock_jobs.insert_one(doc)).inserted_id)
    except DuplicateKeyError:
        return None


async def mock_run(worker: str, now: datetime = None, outcome: str = "CONFIRMED", capacity: int = None) -> dict:
    """Process due jobs up to the queue capacity; stops at the first limit. Remaining jobs stay queued."""
    s = await get_settings()
    cap, results = min(int(capacity or s["live_queue_capacity"]), int(s["live_queue_capacity"])), []
    for _ in range(cap):
        r = await mock_tick(worker, now=now, outcome=outcome)
        if not r["claimed"]:
            break
        results.append(r["result"])
        if r["result"] in ("daily_limit", "concurrency_limit"):
            break
    return {"processed": len(results), "results": {k: results.count(k) for k in set(results)}, "warning": WARNING}


async def recover_stale(now: datetime) -> int:
    """Expired claims: never-sent → re-plan; sent (future real calls) → pending reconciliation, never redialled."""
    q = {"status": "claimed", "lease_until": {"$lt": _iso(now)}}
    n = (await db().ai_live_mock_jobs.update_many({**q, "provider_request_sent": True},
                                                  {"$set": {"status": "pending_reconciliation", "lease_until": None}})).modified_count
    n += (await db().ai_live_mock_jobs.update_many({**q, "provider_request_sent": {"$ne": True}},
                                                   {"$set": {"status": "planned", "lease_until": None, "recovered_at": now_iso()}})).modified_count
    return n


async def mock_reconcile(job_id: str, result: str) -> dict:
    if result not in ("completed", "no_answer", "failed", "needs_review"):
        raise HTTPException(400, "result must be completed, no_answer, failed or needs_review")
    j = await db().ai_live_mock_jobs.find_one_and_update(
        {"_id": ObjectId(job_id), "status": "pending_reconciliation"} if ObjectId.is_valid(job_id) else {"_id": None},
        {"$set": {"status": result, "reconciled_at": now_iso(), "mock_call.confirmed_attendance": False}},
        return_document=ReturnDocument.AFTER)
    if not j:
        raise HTTPException(404, "No pending-reconciliation mock job")
    await _release_slot()
    return {"id": job_id, "status": j["status"], "redialled": False}


async def monitoring() -> dict:
    """Read-only counts. Provider balance is not fetched (no verified read-only Bolna balance API)."""
    d, today = db(), datetime.now(IST).date().isoformat()
    s = await get_settings()
    last = await d.ai_webhook_events.find_one({}, {"received_at": 1, "at": 1}, sort=[("_id", -1)])
    daily = await d.ai_live_counters.find_one({"_id": f"mock:daily:{today}"}) or {}
    conc = await d.ai_live_counters.find_one({"_id": "mock:concurrency"}) or {}
    return {"provider_failures": await d.ai_calls.count_documents({"status": {"$in": ["failed", "error"]}}),
            "webhook_events": await d.ai_webhook_events.count_documents({}),
            "webhook_unmatched": await d.ai_webhook_events.count_documents({"matched": False}),
            "webhook_last_at": (last or {}).get("received_at") or (last or {}).get("at"),
            "pending_reconciliation": await d.ai_calls.count_documents({"state": "pending_reconciliation"})
            + await d.ai_live_mock_jobs.count_documents({"status": "pending_reconciliation"}),
            "needs_review": await d.ai_calls.count_documents({"state": "needs_review"})
            + await d.ai_live_mock_jobs.count_documents({"status": "needs_review"}),
            "open_alerts": await d.ai_call_alerts.count_documents({"status": "open"}),
            "provider_balance": "not available (no verified read-only Bolna balance API)",
            "limits": {"daily_cap": live_daily_cap(s), "daily_limit": s["live_daily_call_limit"], "pilot_cap": s["live_pilot_daily_cap"],
                       "concurrent": s["live_max_concurrent_calls"], "queue_capacity": s["live_queue_capacity"],
                       "no_answer_retries": 1, "mock_used_today": daily.get("count", 0), "mock_active": conc.get("active", 0)}}


async def worker_status() -> dict:
    """Read-only status for the dashboard. The live worker is never running in this phase."""
    d, now = db(), datetime.now(IST)
    by = {r["_id"]: r["n"] async for r in d.ai_live_mock_jobs.aggregate([{"$group": {"_id": "$status", "n": {"$sum": 1}}}])}
    by_purpose = {r["_id"] or CONFIRM: r["n"] async for r in d.ai_live_mock_jobs.aggregate(
        [{"$match": {"status": "planned"}}, {"$group": {"_id": "$purpose", "n": {"$sum": 1}}}])}
    due = await d.ai_live_mock_jobs.count_documents({"status": "planned", "planned_at": {"$lte": _iso(now)}})
    regs = await d.bb_registrations.find({"schedule_date": {"$nin": [None, ""]}}, {"_id": 1}).to_list(20000)
    cons = {c["registration_id"]: c async for c in d.ai_candidate_consents.find({"registration_id": {"$in": [str(r["_id"]) for r in regs]}})}
    no_consent = sum(1 for r in regs if (cons.get(str(r["_id"])) or {}).get("consent_status") != "granted")
    dnc = sum(1 for c in cons.values() if c.get("do_not_call"))
    state = await d.ai_dry_run_state.find_one({"_id": "live_prep_planner"}) or {}
    return {"banner": "LIVE CALLING DISABLED — PREPARATION ONLY", "enabled": worker_enabled(), "running": False,
            "provider": MockProvider.name, "started_on_startup": False, "jobs_by_status": by, "pending_by_purpose": by_purpose,
            "due_now": due, "pending": by.get("planned", 0),
            "unresolved": by.get("pending_reconciliation", 0) + by.get("needs_review", 0),
            "exclusions": {"bookings": len(regs), "no_valid_consent": no_consent, "do_not_call": dnc}, "last_run": state.get("last_run")}


@live_prep_router.get("/worker-status")
async def worker_status_route(request: Request):
    await _auth(request)
    from .modes import live_readiness
    return {**await worker_status(), "monitoring": await monitoring(), "readiness": await live_readiness()}


@live_prep_router.post("/plan")
async def plan_route(request: Request, body: dict = Body(default={})):  # noqa: B008
    user = await _auth(request)
    _csrf(request)
    return await plan_live(user, body.get("source") or "bb_registrations")


@live_prep_router.post("/mock-tick")
async def tick_route(request: Request, body: dict = Body(default={})):  # noqa: B008
    user = await _auth(request)
    _csrf(request)
    return await mock_tick(f"admin:{user}", outcome=body.get("outcome") or "CONFIRMED")


@live_prep_router.post("/mock-run")
async def run_route(request: Request, body: dict = Body(default={})):  # noqa: B008
    user = await _auth(request)
    _csrf(request)
    return await mock_run(f"admin:{user}", outcome=body.get("outcome") or "CONFIRMED", capacity=body.get("capacity"))


@live_prep_router.post("/mock-jobs/{job_id}/process")
async def process_one(job_id: str, request: Request, body: dict = Body(default={})):  # noqa: B008
    """Individual Live call action: same claim + gate path as the worker, only for this job and only when it is due."""
    user = await _auth(request)
    _csrf(request)
    r = await mock_tick(f"admin:{user}", outcome=body.get("outcome") or "CONFIRMED", job_id=job_id)
    if not r["claimed"]:
        raise HTTPException(409, "This job is not due yet, is already being processed, or is no longer planned")
    return r


@live_prep_router.post("/mock-jobs/{job_id}/reconcile")
async def reconcile_route(job_id: str, request: Request, body: dict = Body(...)):  # noqa: B008
    await _auth(request)
    _csrf(request)
    return await mock_reconcile(job_id, body.get("result"))


@live_prep_router.post("/mock-jobs/clear")
async def clear_route(request: Request):
    await _auth(request)
    _csrf(request)
    n = (await db().ai_live_mock_jobs.delete_many({"mode": "live_mock", "dispatchable": False})).deleted_count
    await db().ai_live_counters.delete_many({"_id": {"$regex": "^mock:"}})
    return {"deleted": n}


@live_prep_router.get("/overview")
async def overview(request: Request):
    await _auth(request)
    from .modes import live_readiness
    jobs = await db().ai_live_mock_jobs.find({}, {"mock_call.user_data": 0}).sort([("planned_at", 1), ("interview_at", 1)]).to_list(500)
    total = await db().ai_live_mock_jobs.count_documents({})
    return {"warning": WARNING, "readiness": await live_readiness(), "monitoring": await monitoring(), "total_jobs": total,
            "jobs": [{**{k: v for k, v in j.items() if k not in ("_id", "last_gate")}, "id": str(j["_id"]),
                      "gate_failed": [c["key"] for c in (j.get("last_gate") or {}).get("checks", []) if not c["ok"]]} for j in jobs]}
