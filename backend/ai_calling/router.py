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
    await d.ai_candidate_consents.create_index("registration_id", unique=True)
    await d.ai_call_settings.update_one(  # Phase 7A one-time switch migration: AI Test ON, AI Live OFF, stop ON
        {"_id": SETTINGS_ID, "ai_test_enabled": {"$exists": False}},
        {"$set": {"ai_test_enabled": True, "ai_live_enabled": False, "live_dispatch_authorized": False,
                  "emergency_stop": True, "switches_migrated_at": now_iso()}, "$inc": {"mode_version": 1}})
    await get_settings()
    from .dispatch import startup_recover
    from .dryrun import ensure_dry_run_indexes
    await ensure_dry_run_indexes()
    from .consent import ensure_consent_indexes
    from .live_prep import ensure_live_prep_indexes
    await ensure_consent_indexes()
    await ensure_live_prep_indexes()
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
        "consented_candidates": await c.count_documents({"consent_status": "granted", "opted_out": {"$ne": True}}),
        "ai_test_enabled": s["ai_test_enabled"], "ai_live_enabled": s["ai_live_enabled"],
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
    from .modes import overall_test_mode
    return {**s, "server_calling_enabled": gate.server_calling_enabled(), "overall_test_mode": overall_test_mode(),
            "bolna_integration_approved": gate.BOLNA_INTEGRATION_APPROVED,
            "live_mode_locked": gate.LIVE_MODE_LOCKED}


class SettingsBody(BaseModel):
    daily_call_limit: Optional[int] = None
    max_concurrent_calls: Optional[int] = None
    call_window_start: Optional[str] = None
    call_window_end: Optional[str] = None
    default_company_name: Optional[str] = None
    default_office_address: Optional[str] = None
    live_daily_call_limit: Optional[int] = None
    live_max_concurrent_calls: Optional[int] = None
    live_pilot_daily_cap: Optional[int] = None


@ai_router.put("/settings")
async def update_settings(body: SettingsBody, request: Request):
    user = await _auth(request)
    upd = {k: v for k, v in body.model_dump().items() if v is not None and k in EDITABLE_SETTINGS}
    if "daily_call_limit" in upd and not (0 <= upd["daily_call_limit"] <= 200):
        raise HTTPException(400, "daily_call_limit must be 0–200")
    if "live_daily_call_limit" in upd and not (0 <= upd["live_daily_call_limit"] <= 100000):
        raise HTTPException(400, "live_daily_call_limit must be 0–100000")
    if "live_pilot_daily_cap" in upd and not (0 <= upd["live_pilot_daily_cap"] <= 100000):
        raise HTTPException(400, "live_pilot_daily_cap must be 0–100000")
    if "live_max_concurrent_calls" in upd and not (1 <= upd["live_max_concurrent_calls"] <= 50):
        raise HTTPException(400, "live_max_concurrent_calls must be 1–50")
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
    if body.mode == "live":
        raise HTTPException(403, "Use the AI Live Mode switch (POST /switches); this legacy endpoint only sets AI Test Mode")
    from .modes import set_switches
    await set_switches(user, ai_test=body.mode == "testing")  # legacy: testing ⇒ AI Test ON, off ⇒ AI Test OFF
    return await read_settings(request)


class StopBody(BaseModel):
    active: bool
    reason: Optional[str] = None
    confirmation: Optional[str] = None  # "RELEASE EMERGENCY STOP" required when active=False


@ai_router.post("/emergency-stop")
async def emergency_stop(body: StopBody, request: Request):
    """Engage or release Emergency Stop. Timestamp fields are kept distinct so no observer has to
    guess the current state from timestamp drift:
      - emergency_stop_at         → set only when engaging (active=True)
      - emergency_stop_released_at → set only when releasing (active=False)
    A release never enables calling on its own — all other gates remain in force."""
    user = await _auth(request)
    s = await get_settings()
    if bool(body.active) == bool(s.get("emergency_stop")):
        return await read_settings(request)  # idempotent: no change, no audit noise
    if not body.active and body.confirmation != "RELEASE EMERGENCY STOP":
        raise HTTPException(400, "Releasing Emergency Stop requires typing: RELEASE EMERGENCY STOP")
    ts = now_iso()
    if body.active:
        upd = {"emergency_stop": True, "emergency_stop_by": user, "emergency_stop_at": ts,
               "emergency_stop_reason": (body.reason or "").strip()[:280] or None}
    else:
        upd = {"emergency_stop": False, "emergency_stop_released_by": user, "emergency_stop_released_at": ts,
               "emergency_stop_release_reason": (body.reason or "").strip()[:280] or None}
    await db().ai_call_settings.update_one({"_id": SETTINGS_ID}, {"$set": upd})
    if body.active:
        await db().ai_call_jobs.update_many({"status": "pending"}, {"$set": {"status": "cancelled", "cancel_reason": "emergency_stop"}})
        await db().ai_test_batches.update_many({"status": "running"}, {"$set": {"status": "stopped"}})
    await db().ai_call_audit.insert_one({
        "action": "emergency_stop_engaged" if body.active else "emergency_stop_released",
        "by": user, "at": ts, "previous": bool(s.get("emergency_stop")), "current": bool(body.active),
        "reason": upd.get("emergency_stop_reason") or upd.get("emergency_stop_release_reason"),
        "side_effects_note": ("cancelled pending test jobs + stopped running batches" if body.active else
                              "release does NOT enable calling; other gates still apply"),
    })
    return await read_settings(request)


# ---------------- unified authoritative safety status ----------------

@ai_router.get("/safety-status")
async def safety_status(request: Request):
    """Single source of truth consumed by every AI Calling screen. If any sub-check cannot be read
    the response's `authoritative` flag flips to False and the UI must block calling."""
    await _auth(request)
    try:
        s = await get_settings()
        from .modes import overall_test_mode, live_daily_cap
        from .provider import provider_ready
        prov = await db().ai_provider_settings.find_one({"_id": "bolna"}) or {}
        prov_ready = provider_ready(prov)
        prov_status = prov.get("status", "not_configured")
        env_enabled = gate.server_calling_enabled()
        emer = bool(s["emergency_stop"])
        ai_test = bool(s["ai_test_enabled"])
        ai_live = bool(s["ai_live_enabled"])
        live_auth = bool(s.get("live_dispatch_authorized"))
        overall = overall_test_mode()
        # Effective permissions — single computation re-used everywhere.
        test_blockers = []
        if not ai_test: test_blockers.append(("ai_test_off", "AI Test Mode is OFF"))
        if emer: test_blockers.append(("emergency_stop", "Emergency Stop is ON"))
        if not env_enabled: test_blockers.append(("server_disabled", "Server outbound calling is disabled (AI_CALLING_ENABLED=false)"))
        if not prov_ready: test_blockers.append(("provider_unverified", f"Bolna provider not verified (status: {prov_status})"))
        live_blockers = []
        if not ai_live: live_blockers.append(("ai_live_off", "AI Live Mode is OFF"))
        if not overall: live_blockers.append(("overall_test_off", "Overall Website Test Mode is OFF — Live calls blocked by policy"))
        if emer: live_blockers.append(("emergency_stop", "Emergency Stop is ON"))
        if not env_enabled: live_blockers.append(("server_disabled", "Server outbound calling is disabled (AI_CALLING_ENABLED=false)"))
        if not live_auth: live_blockers.append(("live_dispatch_unauth", "Live Dispatch Authorization is OFF"))
        if not prov_ready: live_blockers.append(("provider_unverified", f"Bolna provider not verified (status: {prov_status})"))
        from .modes import LIVE_DISPATCH_IMPLEMENTED
        if not LIVE_DISPATCH_IMPLEMENTED:
            live_blockers.append(("code_locked", "Live dispatch not yet implemented in code"))
        return {
            "authoritative": True, "fetched_at": now_iso(),
            "emergency_stop": {
                "active": emer,
                "engaged_at": s.get("emergency_stop_at") if emer else None,
                "engaged_by": s.get("emergency_stop_by") if emer else None,
                "engaged_reason": s.get("emergency_stop_reason") if emer else None,
                "released_at": s.get("emergency_stop_released_at") if not emer else None,
                "released_by": s.get("emergency_stop_released_by") if not emer else None,
                "release_reason": s.get("emergency_stop_release_reason") if not emer else None,
            },
            "switches": {
                "ai_test_enabled": ai_test, "ai_live_enabled": ai_live,
                "overall_test_mode": overall, "mode_version": s["mode_version"],
                "live_dispatch_authorized": live_auth,
                "live_dispatch_implemented": LIVE_DISPATCH_IMPLEMENTED,
            },
            "server": {
                "outbound_calling_env_flag": "AI_CALLING_ENABLED",
                "outbound_calling_enabled": env_enabled,
                "env_flag_is_runtime_editable": False,  # changed only via deployment config
            },
            "provider": {
                "ready": prov_ready, "status": prov_status,
                "config_version": prov.get("config_version"),
                "has_api_key": bool(prov.get("api_key_encrypted")),
            },
            "effective": {
                "can_place_test_call": not test_blockers,
                "test_blockers": [{"key": k, "reason": r} for k, r in test_blockers],
                "can_place_live_call": not live_blockers,
                "live_blockers": [{"key": k, "reason": r} for k, r in live_blockers],
            },
            "limits": {
                "test_daily_limit": s["daily_call_limit"],
                "test_max_concurrent": s["max_concurrent_calls"],
                "live_daily_limit": s["live_daily_call_limit"],
                "live_pilot_cap": s["live_pilot_daily_cap"],
                "live_effective_daily": live_daily_cap(s),
                "live_max_concurrent": s["live_max_concurrent_calls"],
            },
        }
    except Exception as e:  # noqa: BLE001
        _logger.exception("safety-status read failed")
        return {"authoritative": False, "fetched_at": now_iso(),
                "error": "Safety status unavailable — calling blocked.",
                "error_detail": str(e)[:200]}


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
        raise HTTPException(400, "Select at least one consented test candidate")
    oids = [_oid(i) for i in ids]
    ok = await db().ai_test_candidates.count_documents({"_id": {"$in": oids}, "consent_status": "granted", "opted_out": {"$ne": True}})
    if ok != len(ids):
        raise HTTPException(400, "Only consented, non-opted-out test candidates can be added to a batch")
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
    return {"locked": gate.LIVE_MODE_LOCKED, "active": s["ai_live_enabled"], "dispatch_authorized": s["live_dispatch_authorized"],
            "call_hours_before": s["live_call_hours_before"], "no_answer_retries": s["live_retry_no_answer"],
            "source": "bb_registrations (read-only, not accessed in this phase)",
            "interview_location": "Offline — Chennai office"}


# Phase 3 — Test Candidate Management endpoints (same /api/ai-calling prefix)
from .candidates import cand_router  # noqa: E402
from .provider import provider_router  # noqa: E402
from .calls import calls_router  # noqa: E402
from .dispatch import dispatch_router  # noqa: E402
from .dryrun import dryrun_router  # noqa: E402
from .modes import modes_router  # noqa: E402
from .consent import admin_router as consent_admin_router, public_router as consent_public_router  # noqa: E402

from .live_prep import live_prep_router  # noqa: E402
from .retention import retention_router  # noqa: E402
from .purposes import purposes_router  # noqa: E402

ai_router.include_router(purposes_router)

ai_router.include_router(retention_router)
ai_router.include_router(live_prep_router)
ai_router.include_router(dispatch_router)
ai_router.include_router(dryrun_router)
ai_router.include_router(modes_router)
ai_router.include_router(consent_admin_router)
ai_router.include_router(consent_public_router)
ai_router.include_router(cand_router)
ai_router.include_router(provider_router)
ai_router.include_router(calls_router)
