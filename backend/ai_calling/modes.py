"""Phase 7A: independent AI Test / AI Live switches and the effective-calling policy.

Switches are CONFIGURATION only. Calling also needs every gate (emergency stop, server flag,
Call Now approval / Live Dispatch Authorization, consent, limits). Nothing here dispatches.
"""
from datetime import datetime

from bson import ObjectId
from fastapi import APIRouter, Body, HTTPException, Request

from . import gate
from .dryrun import eligibility, plan_booking, booking_key
from .provider import _auth, _csrf
from .store import IST, SETTINGS_ID, db, get_settings, now_iso

modes_router = APIRouter()
LIVE_DISPATCH_IMPLEMENTED = False  # Phase 7A: no live dispatch code path exists
CONSENT_TEXT_VERSION = "2026-06-v1-draft"
CONSENT_TEXT = ("I agree to receive an automated AI voice call from BluBridge Technologies regarding my scheduled "
                "in-person interview at the Chennai office. I understand that the call may be recorded and that I can "
                "withdraw my consent.")


def overall_test_mode() -> bool:
    """Read-only view of the website's Overall Test Mode (messaging gate). Never written from here."""
    from messaging import is_test_mode
    return bool(is_test_mode())


def effective(overall_test: bool, ai_test: bool, ai_live: bool) -> dict:
    test, live = bool(ai_test), bool(ai_live and overall_test)
    label = ("Both test-list and live eligible candidate calls" if test and live else "Test-list calls only" if test
             else "Live eligible candidate calls" if live else "No calls")
    return {"test_calls": test, "live_calls": live, "label": label}


def policy_table() -> list:
    return [{"overall_test": o, "ai_test": t, "ai_live": lv, **effective(o, t, lv)}
            for o in (True, False) for t, lv in ((False, False), (True, False), (False, True), (True, True))]


async def calling_status(overall: bool = None) -> dict:
    s = await get_settings()
    overall = overall_test_mode() if overall is None else overall
    eff = effective(overall, s["ai_test_enabled"], s["ai_live_enabled"])
    common = (["Emergency stop is ON"] if s["emergency_stop"] else []) + \
             ([] if gate.server_calling_enabled() else ["Server-side calling is disabled (AI_CALLING_ENABLED=false)"])
    test_b = (["AI Test Mode is OFF"] if not s["ai_test_enabled"] else []) + common + \
             ([] if gate.SINGLE_TEST_CALL_APPROVED else ["Call Now is locked on the server"])
    live_b = (["AI Live Mode is OFF"] if not s["ai_live_enabled"] else
              ["Overall Website Test Mode is OFF — Live calls are blocked by policy"] if not overall else []) + common + \
             ([] if s.get("live_dispatch_authorized") else ["Live Dispatch Authorization is OFF"]) + \
             ([] if LIVE_DISPATCH_IMPLEMENTED else ["Live dispatch is not implemented yet (Phase 7A)"])
    return {"overall_test_mode": overall, "ai_test_enabled": s["ai_test_enabled"], "ai_live_enabled": s["ai_live_enabled"],
            "emergency_stop": s["emergency_stop"], "server_calling_enabled": gate.server_calling_enabled(),
            "live_dispatch_authorized": bool(s.get("live_dispatch_authorized")), "live_dispatch_implemented": LIVE_DISPATCH_IMPLEMENTED,
            "switch_version": s["mode_version"], "effective": eff,
            "test": {"configured": eff["test_calls"], "can_call": eff["test_calls"] and not test_b, "blockers": test_b},
            "live": {"configured": eff["live_calls"], "can_call": eff["live_calls"] and not live_b, "blockers": live_b},
            "policy": policy_table()}


async def set_switches(user: str, ai_test=None, ai_live=None, expected_version=None) -> dict:
    s = await get_settings()
    upd = {}
    if ai_test is not None and bool(ai_test) != s["ai_test_enabled"]:
        upd["ai_test_enabled"] = bool(ai_test)
    if ai_live is not None and bool(ai_live) != s["ai_live_enabled"]:
        upd["ai_live_enabled"] = bool(ai_live)
    if not upd:
        return await calling_status()
    if upd.get("ai_live_enabled") is False:
        upd["live_dispatch_authorized"] = False  # turning Live OFF always revokes dispatch authorization
    q = {"_id": SETTINGS_ID}
    if expected_version is not None:
        q["mode_version"] = int(expected_version)
    res = await db().ai_call_settings.update_one(q, {"$set": {**upd, "switches_changed_by": user, "switches_changed_at": now_iso()},
                                                     "$inc": {"mode_version": 1}})
    if not res.matched_count:
        raise HTTPException(409, "Switches were changed by someone else. Reload and try again.")
    # Switching a source OFF cancels its pending work; switching ON never enqueues anything (no backlog).
    for key, mode in (("ai_test_enabled", "testing"), ("ai_live_enabled", "live")):
        if upd.get(key) is False:
            await db().ai_call_jobs.update_many({"mode": mode, "status": "pending"},
                                                {"$set": {"status": "cancelled", "cancel_reason": f"{key}_off"}})
    await db().ai_call_audit.insert_one({"action": "switches_changed", "by": user, "detail": {k: v for k, v in upd.items()}, "at": now_iso()})
    return await calling_status()


async def consent_for(registration_id: str) -> dict:
    return await db().ai_candidate_consents.find_one({"registration_id": registration_id}) or {}


async def evaluate_live(*, registration_id: str, job_mode_version: int, now: datetime = None, overall: bool = None) -> dict:
    """Future live gate, re-run immediately before any dispatch. In Phase 7A it can never return allowed."""
    s = await get_settings()
    now = now or datetime.now(IST)
    overall = overall_test_mode() if overall is None else overall
    checks = []

    def add(key, label, ok, detail=""):
        checks.append({"key": key, "label": label, "ok": bool(ok), "detail": detail})

    add("implemented", "Live dispatch implemented", LIVE_DISPATCH_IMPLEMENTED, "Phase 7A")
    add("overall_test", "Overall Website Test Mode is ON", overall)
    add("ai_live", "AI Live Mode is ON", s["ai_live_enabled"])
    add("authorized", "Live Dispatch Authorization granted", s.get("live_dispatch_authorized"))
    add("no_emergency_stop", "Emergency stop is OFF", not s["emergency_stop"])
    add("server_enabled", "Server-side calling enabled", gate.server_calling_enabled())
    add("mode_version", "Job created under current switch state", job_mode_version == s["mode_version"])
    reg = await db().bb_registrations.find_one({"_id": ObjectId(registration_id)}) if ObjectId.is_valid(registration_id) else None
    add("booking_exists", "Booking found by exact registration ID", reg is not None)
    if reg:
        c = await consent_for(registration_id)
        b = {**reg, "ai_call_consent": {"status": c.get("status")} if c else None, "do_not_call": c.get("do_not_call") is True}
        reasons = eligibility(b)
        add("eligible", "Booking eligible (status, consent, opt-out, phone…)", not reasons, ", ".join(reasons))
        p = plan_booking(b, now, s)
        add("in_plan", "Due under the 24 h plan and inside the calling window", p["status"] == "SCHEDULED" and p["planned_at"]
            and datetime.fromisoformat(p["planned_at"]) <= now, p["status"])
        dup = await db().ai_call_jobs.find_one({"mode": "live", "registration_id": registration_id, "booking_key": booking_key(reg),
                                                "status": {"$nin": ["cancelled"]}})
        add("no_duplicate", "No call already made or queued for this booking slot", dup is None)
    active = await db().ai_call_jobs.count_documents({"status": {"$in": gate.ACTIVE_JOB_STATUSES}})
    add("concurrency", "Concurrency limit not exceeded", active < int(s["max_concurrent_calls"]))
    return {"allowed": all(c["ok"] for c in checks), "checks": checks}


@modes_router.get("/switches")
async def get_switches(request: Request):
    await _auth(request)
    return await calling_status()


@modes_router.post("/switches")
async def post_switches(request: Request, body: dict = Body(...)):  # noqa: B008
    user = await _auth(request)
    _csrf(request)
    return await set_switches(user, body.get("ai_test_enabled"), body.get("ai_live_enabled"), body.get("expected_version"))


@modes_router.post("/live-dispatch/authorize")
async def authorize_live(request: Request):
    await _auth(request)
    _csrf(request)
    raise HTTPException(423, "Live Dispatch Authorization is not available in Phase 7A")


@modes_router.get("/consent/preview")
async def consent_preview(request: Request):
    await _auth(request)
    return {"text": CONSENT_TEXT, "version": CONSENT_TEXT_VERSION, "optional": True, "default_checked": False,
            "storage": {"collection": "ai_candidate_consents", "key": "registration_id (bb_registrations._id)",
                        "fields": ["status (granted|refused|withdrawn)", "consent_at", "source", "text_version", "withdrawn_at", "do_not_call"]}}
