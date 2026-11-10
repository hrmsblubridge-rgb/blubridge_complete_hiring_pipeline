"""AI Calling API (/api/ai-calling). Admin-only except nothing public in Phase 2."""
import logging
import re
from typing import List, Optional

from bson import ObjectId
from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel

from . import gate
from .store import (
    EDITABLE_SETTINGS, MODES, SETTINGS_ID, _state, db, get_settings,
    mask_phone, now_iso, serialize,
)

_logger = logging.getLogger("ai_calling")
ai_router = APIRouter(prefix="/api/ai-calling", tags=["AI Calling"])


def init_ai_calling(database, auth_fn):
    _state["db"] = database
    _state["auth"] = auth_fn


async def ensure_ai_indexes():
    d = db()
    await d.ai_test_candidates.create_index("phone_e164", unique=True)
    await d.ai_test_candidates.create_index("test_candidate_id", unique=True, sparse=True)
    await d.ai_upload_batches.create_index("upload_batch_id", unique=True)
    await d.ai_provider_audit.create_index([("provider", 1), ("at", -1)])
    await d.ai_webhook_events.create_index([("execution_id", 1), ("status", 1), ("payload_hash", 1)], unique=True)
    from .candidates import backfill_candidates
    await backfill_candidates()
    await d.ai_call_jobs.create_index(
        [("mode", 1), ("batch_id", 1), ("test_candidate_id", 1), ("attempt", 1)], unique=True)
    await d.ai_call_jobs.create_index([("status", 1), ("created_at", 1)])
    await d.ai_calls.create_index("execution_id", unique=True, sparse=True)
    await d.ai_calls.create_index([("mode", 1), ("created_at", -1)])
    await d.ai_calls.create_index("state")
    await d.ai_call_jobs.create_index("idempotency_key", unique=True, sparse=True)
    await get_settings()
    from .dispatch import startup_recover
    await startup_recover()


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
        "single_test_call_approved": gate.SINGLE_TEST_CALL_APPROVED,
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
            "live_mode_locked": gate.LIVE_MODE_LOCKED}


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
    from .dispatch import public_call
    docs = await db().ai_calls.find(q).sort("created_at", -1).to_list(500)
    return {"items": [public_call(d, full=False) for d in docs]}


@ai_router.get("/calls/{call_id}")
async def get_call(call_id: str, request: Request):
    await _auth(request)
    from .dispatch import public_call
    doc = await db().ai_calls.find_one({"_id": _oid(call_id)})
    if not doc:
        raise HTTPException(404, "Not found")
    return public_call(doc)


@ai_router.get("/live/status")
async def live_status(request: Request):
    await _auth(request)
    s = await get_settings()
    return {"locked": gate.LIVE_MODE_LOCKED, "active": s["mode"] == "live",
            "call_hours_before": s["live_call_hours_before"], "no_answer_retries": s["live_retry_no_answer"],
            "source": "bb_registrations (read-only, not accessed in this phase)",
            "interview_location": "Offline — Chennai office"}


# Phase 3 — Test Candidate Management endpoints (same /api/ai-calling prefix)
from .candidates import cand_router  # noqa: E402
from .provider import provider_router  # noqa: E402
from .calls import calls_router  # noqa: E402
from .dispatch import dispatch_router  # noqa: E402

ai_router.include_router(dispatch_router)
ai_router.include_router(cand_router)
ai_router.include_router(provider_router)
ai_router.include_router(calls_router)
