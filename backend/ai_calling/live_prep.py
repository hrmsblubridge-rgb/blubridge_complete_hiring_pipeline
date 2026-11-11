"""Phase 7C-A: future Live scheduler + dispatch worker architecture, MOCK ONLY.

Jobs live in `ai_live_mock_jobs` (dispatchable=False) and are never visible to the real dispatcher.
This module never imports bolna_client.place_call and never sends POST /call. Nothing runs in the
background: planning and worker ticks happen only when an admin clicks (or a test calls them).
"""
import uuid
from datetime import datetime, timedelta, timezone

from bson import ObjectId
from fastapi import APIRouter, Body, HTTPException, Request
from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError

from . import gate
from .dryrun import MIN_LEAD, RETRY_GAP, _mask, booking_key, eligibility, interview_at, into_window, plan_booking
from .execution import spoken_date, spoken_time
from .modes import LIVE_DISPATCH_IMPLEMENTED, deployment_approved, effective, live_daily_cap, overall_test_mode
from .provider import _auth, _csrf
from .store import IST, db, get_settings, mask_phone, normalize_phone, now_iso

live_prep_router = APIRouter(prefix="/live-prep")
WARNING = "MOCK ONLY — NO PHONE CALLS WILL BE PLACED. Jobs are non-dispatchable."
SOURCES = {"bb_registrations": "bb_registrations", "fixtures": "ai_dry_run_bookings"}
LEASE = timedelta(minutes=5)
OUTCOMES = ("CONFIRMED", "RESCHEDULE_REQUESTED", "DECLINED", "DO_NOT_CALL", "no_answer", "timeout", "failed")
EXTRACTION_FIELDS = ("attendance_status", "wants_reschedule", "requested_virtual", "rejection_reason",
                     "candidate_questions", "call_summary")
GLOBAL_KEYS = ("dispatch_implemented", "server_enabled", "emergency_stop_off", "effective_live", "authorized",
               "deployment_approved")


async def ensure_live_prep_indexes():
    await db().ai_live_mock_jobs.create_index([("registration_id", 1), ("booking_key", 1), ("attempt", 1)], unique=True)
    await db().ai_live_mock_jobs.create_index([("status", 1), ("planned_at", 1)])


def _iso(dt: datetime) -> str:
    return dt.astimezone(IST).isoformat()


async def _bookings(source: str) -> list:
    """(registration_id, booking-with-consent) pairs. Real consent always comes from ai_candidate_consents."""
    if source == "fixtures":
        docs = await db().ai_dry_run_bookings.find({"synthetic": True}).to_list(2000)
        return [(f"fixture:{d['_id']}", d) for d in docs]
    regs = await db().bb_registrations.find({"schedule_date": {"$nin": [None, ""]}}).to_list(2000)
    ids = [str(r["_id"]) for r in regs]
    cons = {c["registration_id"]: c async for c in db().ai_candidate_consents.find({"registration_id": {"$in": ids}})}
    out = []
    for r in regs:
        c = cons.get(str(r["_id"]), {})
        out.append((str(r["_id"]), {**r, "ai_call_consent": {"status": c.get("consent_status")}, "do_not_call": c.get("do_not_call") is True}))
    return out


async def _load_one(job: dict):
    rid = job["registration_id"]
    if rid.startswith("fixture:"):
        oid = rid.split(":", 1)[1]
        return await db().ai_dry_run_bookings.find_one({"_id": ObjectId(oid)}) if ObjectId.is_valid(oid) else None
    if not ObjectId.is_valid(rid):
        return None
    reg = await db().bb_registrations.find_one({"_id": ObjectId(rid)})
    if not reg:
        return None
    c = await db().ai_candidate_consents.find_one({"registration_id": rid}) or {}
    return {**reg, "ai_call_consent": {"status": c.get("consent_status")}, "do_not_call": c.get("do_not_call") is True}


def _snapshot(b: dict) -> dict:
    return {k: b.get(k) for k in ("schedule_date", "schedule_time", "reschedule_count", "status")}


async def _acquire(run_id: str):
    stale = (datetime.now(timezone.utc) - LEASE).isoformat()
    await db().ai_dry_run_state.update_one({"_id": "live_prep_planner"}, {"$setOnInsert": {"lock": None}}, upsert=True)
    return await db().ai_dry_run_state.find_one_and_update(
        {"_id": "live_prep_planner", "$or": [{"lock": None}, {"lock.at": {"$lt": stale}}]},
        {"$set": {"lock": {"id": run_id, "at": now_iso()}}}, return_document=ReturnDocument.AFTER)


async def plan_live(user: str, source: str = "bb_registrations", now: datetime = None) -> dict:
    """Idempotent: one job per (registration, booking slot, attempt). Reschedules/ineligibility invalidate."""
    if source not in SOURCES:
        raise HTTPException(400, "source must be bb_registrations or fixtures")
    run_id = uuid.uuid4().hex
    if not await _acquire(run_id):
        raise HTTPException(409, "Planning is already running")
    try:
        now, cfg = (now or datetime.now(IST)), await get_settings()
        counts = {"planned": 0, "needs_review": 0, "skipped": 0, "invalidated": 0, "unchanged": 0}
        seen = []
        for rid, b in await _bookings(source):
            seen.append(rid)
            key, p = booking_key(b), plan_booking(b, now, cfg)
            res = await db().ai_live_mock_jobs.update_many(
                {"registration_id": rid, "booking_key": {"$ne": key}, "status": {"$in": ["planned", "claimed", "needs_review"]}},
                {"$set": {"status": "invalidated", "reasons": ["RESCHEDULED"], "invalidated_at": now_iso()}})
            counts["invalidated"] += res.modified_count
            if p["status"] == "SKIPPED":
                res = await db().ai_live_mock_jobs.update_many(
                    {"registration_id": rid, "status": {"$in": ["planned", "claimed", "needs_review"]}},
                    {"$set": {"status": "invalidated", "reasons": p["reasons"], "invalidated_at": now_iso()}})
                counts["invalidated"] += res.modified_count
                counts["skipped"] += 1
                continue
            status = "planned" if p["status"] == "SCHEDULED" else "needs_review"
            doc = {"mode": "live_mock", "dispatchable": False, "source": source, "registration_id": rid, "booking_key": key,
                   "attempt": 1, "status": status, "reasons": p["reasons"], "planned_at": p["planned_at"],
                   "target_at": p["target_at"], "interview_at": p["interview_at"], "adjustments": p["adjustments"],
                   "retry_plan": p["retry"], "snapshot": _snapshot(b), "candidate_name": b.get("full_name"),
                   "phone_masked": _mask(b.get("phone")), "job_role": b.get("job_role"), "provider_request_sent": False,
                   "mode_version": cfg["mode_version"], "created_by": user, "created_at": now_iso(), "run_id": run_id}
            try:
                r = await db().ai_live_mock_jobs.update_one({"registration_id": rid, "booking_key": key, "attempt": 1},
                                                            {"$setOnInsert": doc}, upsert=True)
                if not r.upserted_id and status == "planned":  # a needs-review slot that is now callable
                    r2 = await db().ai_live_mock_jobs.update_one(
                        {"registration_id": rid, "booking_key": key, "attempt": 1, "status": "needs_review"},
                        {"$set": {"status": "planned", "reasons": [], "planned_at": p["planned_at"]}})
                    status = status if r2.modified_count else "unchanged"
                counts[status if r.upserted_id or status == "planned" else "unchanged"] += 1
            except DuplicateKeyError:
                counts["unchanged"] += 1
        res = await db().ai_live_mock_jobs.update_many(
            {"source": source, "registration_id": {"$nin": seen}, "status": {"$in": ["planned", "claimed", "needs_review"]}},
            {"$set": {"status": "invalidated", "reasons": ["BOOKING_REMOVED"], "invalidated_at": now_iso()}})
        counts["invalidated"] += res.modified_count
        return {"run_id": run_id, "source": source, "counts": counts, "at": now_iso(), "warning": WARNING}
    finally:
        await db().ai_dry_run_state.update_one({"_id": "live_prep_planner", "lock.id": run_id}, {"$set": {"lock": None}})


async def gate_job(job: dict, now: datetime, overall: bool = None) -> dict:
    """Full pre-dispatch checklist, run immediately before any (mock) dispatch."""
    s = await get_settings()
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
    b = await _load_one(job)
    add("booking_exists", "Booking found by exact registration ID", b is not None)
    if b:
        reasons = eligibility(b)
        add("eligible", "Booking eligible", not reasons, ", ".join(reasons))
        add("consent", "AI calling consent valid", (b.get("ai_call_consent") or {}).get("status") == "granted")
        add("not_dnc", "Do Not Call is false", b.get("do_not_call") is not True)
        add("snapshot", "Interview schedule unchanged", booking_key(b) == job["booking_key"] and _snapshot(b) == job["snapshot"])
        iv = interview_at(b)
        add("lead_time", "At least 2 hours before the interview", iv is not None and iv - now >= MIN_LEAD)
    ws, we = s["call_window_start"], s["call_window_end"]
    add("window", "Inside the calling window (IST)", ws <= now.astimezone(IST).strftime("%H:%M") < we, f"{ws}–{we}")
    dup = await db().ai_live_mock_jobs.find_one({"registration_id": job["registration_id"], "booking_key": job["booking_key"],
                                                 "_id": {"$ne": job["_id"]},
                                                 "status": {"$in": ["claimed", "mock_dispatched", "pending_reconciliation"]}})
    add("no_duplicate", "No other active call for this booking", dup is None)
    prov = await db().ai_provider_settings.find_one({"_id": "bolna"}) or {}
    add("provider_verified", "Bolna configuration verified", provider_ready(prov))
    booking_ok = all(c["ok"] for c in checks if not c["global"] and c["key"] != "provider_verified")
    return {"allowed_live": all(c["ok"] for c in checks), "booking_ok": booking_ok, "checks": checks,
            "mock_bypassed": [c["key"] for c in checks if c["global"] and not c["ok"]]}


async def _reserve(counter_id: str, field: str, cap: int) -> bool:
    await db().ai_live_counters.update_one({"_id": counter_id}, {"$setOnInsert": {field: 0}}, upsert=True)
    return bool(await db().ai_live_counters.find_one_and_update({"_id": counter_id, field: {"$lt": cap}}, {"$inc": {field: 1}}))


async def _release_slot():
    await db().ai_live_counters.update_one({"_id": "mock:concurrency", "active": {"$gt": 0}}, {"$inc": {"active": -1}})


def user_data_for_registration(b: dict, cfg: dict) -> dict:
    """The six dynamic variables, from the exact booking only."""
    return {"candidate_name": b.get("full_name") or "", "company_name": cfg.get("default_company_name") or "BluBridge",
            "job_role": b.get("job_role") or "", "interview_date": spoken_date(str(b["schedule_date"])[:10]),
            "interview_time": spoken_time(str(b["schedule_time"])[:5]), "office_address": cfg.get("default_office_address") or ""}


def live_call_record(job: dict, b: dict, user_data: dict, execution_id: str) -> dict:
    """Shape a future Live ai_calls document (compatible with Candidate Profile history). Not inserted in 7C-A."""
    try:
        phone = normalize_phone(b.get("phone"))
    except ValueError:
        phone = ""
    return {"mode": "live", "registration_id": job["registration_id"], "booking_key": job["booking_key"],
            "booking_snapshot": job["snapshot"], "job_id": str(job["_id"]), "attempt": job["attempt"],
            "candidate_name": b.get("full_name"), "phone_masked": mask_phone(phone), "job_role": b.get("job_role"),
            "interview_date": b.get("schedule_date"), "interview_time": str(b.get("schedule_time") or "")[:5],
            "user_data": user_data, "execution_id": execution_id, "state": "dispatching", "status": "",
            "transcript": None, "recording_ref": None, "extracted": {k: None for k in EXTRACTION_FIELDS}, "created_at": now_iso()}


def _mock_extraction(outcome: str) -> dict:
    att = outcome if outcome in ("CONFIRMED", "RESCHEDULE_REQUESTED", "DECLINED", "DO_NOT_CALL") else None
    return {"attendance_status": att, "wants_reschedule": "Yes" if att == "RESCHEDULE_REQUESTED" else ("No" if att else None),
            "requested_virtual": "No" if att else None, "rejection_reason": None, "candidate_questions": None,
            "call_summary": f"Simulated outcome: {outcome}"}


async def mock_tick(worker: str, now: datetime = None, outcome: str = "CONFIRMED", overall: bool = None) -> dict:
    """One worker iteration: recover → claim → gate → reserve limits → MOCK dispatch → record. Never dials."""
    if outcome not in OUTCOMES:
        raise HTTPException(400, f"outcome must be one of {', '.join(OUTCOMES)}")
    now = (now or datetime.now(IST)).astimezone(IST)
    recovered = await recover_stale(now)
    job = await db().ai_live_mock_jobs.find_one_and_update(
        {"mode": "live_mock", "dispatchable": False, "status": "planned", "planned_at": {"$lte": _iso(now)}},
        {"$set": {"status": "claimed", "claimed_by": worker, "claimed_at": now_iso(), "lease_until": _iso(now + LEASE)}},
        sort=[("planned_at", 1)], return_document=ReturnDocument.AFTER)
    if not job:
        return {"claimed": None, "recovered": recovered, "warning": WARNING}
    jid = job["_id"]
    g = await gate_job(job, now, overall)
    if not g["booking_ok"]:
        failed = [c["key"] for c in g["checks"] if not c["ok"] and not c["global"]]
        st = "deferred" if set(failed) <= {"window", "no_duplicate"} else "invalidated"
        await db().ai_live_mock_jobs.update_one({"_id": jid}, {"$set": {
            "status": "planned" if st == "deferred" else "invalidated", "reasons": [f.upper() for f in failed],
            "last_gate": g, "lease_until": None}})
        return {"claimed": str(jid), "result": st, "gate": g, "recovered": recovered, "warning": WARNING}
    s = await get_settings()
    if not await _reserve("mock:concurrency", "active", int(s["live_max_concurrent_calls"])):
        await db().ai_live_mock_jobs.update_one({"_id": jid}, {"$set": {"status": "planned", "reasons": ["CONCURRENCY_LIMIT"],
                                                                         "lease_until": None}})
        return {"claimed": str(jid), "result": "concurrency_limit", "gate": g, "recovered": recovered, "warning": WARNING}
    if not await _reserve(f"mock:daily:{now.date().isoformat()}", "count", live_daily_cap(s)):
        await _release_slot()
        await db().ai_live_mock_jobs.update_one({"_id": jid}, {"$set": {"status": "planned", "reasons": ["DAILY_LIMIT"],
                                                                         "lease_until": None}})
        return {"claimed": str(jid), "result": "daily_limit", "gate": g, "recovered": recovered, "warning": WARNING}
    try:
        b = await _load_one(job)
        rec = live_call_record(job, b, user_data_for_registration(b, s), f"mock_{uuid.uuid4().hex[:16]}")
        rec.update(mock=True, provider_status=outcome if outcome in ("no_answer", "failed", "timeout") else "completed",
                   extracted=_mock_extraction(outcome))
        status = {"no_answer": "no_answer", "timeout": "pending_reconciliation", "failed": "failed"}.get(outcome, "completed")
        rec["confirmed_attendance"] = status == "completed" and outcome == "CONFIRMED"
        await db().ai_live_mock_jobs.update_one({"_id": jid}, {"$set": {
            "status": status, "mock_call": rec, "last_gate": g, "provider_request_sent": False, "finished_at": now_iso(), "lease_until": None}})
    except Exception:
        await _release_slot()
        await db().ai_live_mock_jobs.update_one({"_id": jid}, {"$set": {"status": "needs_review", "reasons": ["WORKER_ERROR"], "lease_until": None}})
        raise
    if status != "pending_reconciliation":  # an uncertain call keeps its slot until reconciled; never redialled
        await _release_slot()
    retry = None
    if status == "no_answer":
        retry = await _plan_retry(job, now, s)
    if outcome == "DO_NOT_CALL" and not job["registration_id"].startswith("fixture:"):
        from .consent import apply_ai_opt_out
        await apply_ai_opt_out(job["registration_id"])
    return {"claimed": str(jid), "result": status, "retry_job": retry, "gate": g, "recovered": recovered,
            "provider_request_sent": False, "warning": WARNING}


async def _plan_retry(job: dict, now: datetime, s: dict):
    """At most ONE no-answer retry, 60 min later inside the window, only with ≥2 h left before the interview."""
    if job["attempt"] >= 1 + int(s["live_retry_no_answer"]):
        return None
    iv = datetime.fromisoformat(job["interview_at"])
    at = into_window(now + RETRY_GAP, s)
    if iv - at < MIN_LEAD:
        await db().ai_live_mock_jobs.update_one({"_id": job["_id"]}, {"$set": {"retry_skipped": "INSUFFICIENT_LEAD_TIME"}})
        return None
    doc = {k: v for k, v in job.items() if k not in ("_id", "claimed_by", "claimed_at", "lease_until", "mock_call", "last_gate")}
    doc.update(attempt=job["attempt"] + 1, status="planned", planned_at=_iso(at), reasons=["NO_ANSWER_RETRY"],
               created_at=now_iso(), retry_of=str(job["_id"]))
    try:
        r = await db().ai_live_mock_jobs.insert_one(doc)
        return str(r.inserted_id)
    except DuplicateKeyError:
        return None


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
            "provider_balance": "not available (no verified read-only Bolna balance API)",
            "limits": {"daily_cap": live_daily_cap(s), "daily_limit": s["live_daily_call_limit"], "pilot_cap": s["live_pilot_daily_cap"],
                       "concurrent": s["live_max_concurrent_calls"], "no_answer_retries": s["live_retry_no_answer"],
                       "mock_used_today": daily.get("count", 0), "mock_active": conc.get("active", 0)}}


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
    jobs = await db().ai_live_mock_jobs.find({}, {"mock_call.user_data": 0}).sort([("planned_at", 1)]).to_list(500)
    return {"warning": WARNING, "readiness": await live_readiness(), "monitoring": await monitoring(),
            "jobs": [{**{k: v for k, v in j.items() if k not in ("_id", "last_gate")}, "id": str(j["_id"]),
                      "gate_failed": [c["key"] for c in (j.get("last_gate") or {}).get("checks", []) if not c["ok"]]} for j in jobs]}
