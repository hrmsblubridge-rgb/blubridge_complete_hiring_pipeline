"""Phase 7B: optional candidate AI-call consent (booking page + private manage link) and the
read-only Real Bookings dry-run preview. Nothing here dispatches calls or edits bookings."""
import logging
from datetime import datetime

from fastapi import APIRouter, Body, HTTPException, Request

from .dryrun import WARNING, _mask, booking_key, plan_booking
from .modes import CONSENT_TEXT, CONSENT_TEXT_VERSION
from .provider import _auth
from .store import IST, db, get_settings, now_iso

_logger = logging.getLogger("ai_calling.consent")
public_router = APIRouter(prefix="/public/consent")
admin_router = APIRouter()
ACCESS = "schedule_token"  # existing unguessable per-candidate booking link (64 random bits)


async def _reg_by_token(token: str) -> dict:
    reg = await db().bb_registrations.find_one({ACCESS: token}, {"_id": 1, "full_name": 1, "schedule_date": 1}) \
        if token and len(token) >= 16 else None
    if not reg:
        raise HTTPException(404, "Invalid or expired link")
    return reg


async def record_consent(reg_id: str, status: str, source: str, actor: str) -> dict:
    now = now_iso()
    st = {"consent_status": status, "consent_source": source, "consent_text_version": CONSENT_TEXT_VERSION, "updated_at": now}
    if status == "granted":
        st.update(consent_timestamp=now, consent_withdrawn_at=None)
    elif status == "withdrawn":
        st["consent_withdrawn_at"] = now
    await db().ai_candidate_consents.update_one(
        {"registration_id": reg_id},
        {"$set": st, "$setOnInsert": {"registration_id": reg_id, "do_not_call": False, "created_at": now},
         "$push": {"history": {"status": status, "source": source, "by": actor, "at": now, "text_version": CONSENT_TEXT_VERSION}}},
        upsert=True)
    if status != "granted":  # immediately ineligible: cancel any pending live work for this exact registration
        await db().ai_call_jobs.update_many({"mode": "live", "registration_id": reg_id, "status": "pending"},
                                            {"$set": {"status": "cancelled", "cancel_reason": f"consent_{status}"}})
    return await db().ai_candidate_consents.find_one({"registration_id": reg_id}, {"_id": 0, "history": 0})


async def _safe_record(reg_id: str, status: str, source: str):
    try:
        return await record_consent(reg_id, status, source, "candidate")
    except Exception as e:  # noqa: BLE001 — never claim it was saved; booking is unaffected
        _logger.error(f"[Consent] persist failed reg={reg_id}: {type(e).__name__}")
        try:
            await db().ai_call_audit.insert_one({"action": "consent_persist_failed", "registration_id": reg_id,
                                                 "intended_status": status, "source": source, "error": type(e).__name__, "at": now_iso()})
        except Exception:  # noqa: BLE001
            pass
        raise HTTPException(503, "Your interview is booked, but your AI call preference could not be saved. It counts as NOT given.") from None


@public_router.get("/{token}")
async def consent_info(token: str):
    reg = await _reg_by_token(token)
    c = await db().ai_candidate_consents.find_one({"registration_id": str(reg["_id"])}) or {}
    return {"first_name": (reg.get("full_name") or "").split(" ")[0], "has_booking": bool(reg.get("schedule_date")),
            "consent_status": c.get("consent_status", "not_given"), "do_not_call": bool(c.get("do_not_call")),
            "text": CONSENT_TEXT, "version": CONSENT_TEXT_VERSION}


@public_router.post("/{token}")
async def consent_decision(token: str, body: dict = Body(...)):  # noqa: B008
    """Booking-page decision (checked or unchecked). Called only after the booking itself succeeded."""
    reg = await _reg_by_token(token)
    if not reg.get("schedule_date"):
        raise HTTPException(409, "No interview booking found for this link")
    if body.get("text_version") != CONSENT_TEXT_VERSION:
        raise HTTPException(409, "Consent wording changed. Your preference was not saved.")
    status = "granted" if body.get("granted") is True else "not_given"
    c = await _safe_record(str(reg["_id"]), status, str(body.get("source") or "booking_form")[:30])
    return {"saved": True, "consent_status": c["consent_status"]}


@public_router.post("/{token}/withdraw")
async def consent_withdraw(token: str):
    reg = await _reg_by_token(token)
    c = await _safe_record(str(reg["_id"]), "withdrawn", "consent_page")
    return {"saved": True, "consent_status": c["consent_status"], "interview_unchanged": True}


@admin_router.get("/dry-run/real-preview")
async def real_preview(request: Request):
    """Read-only plan for existing bb_registrations bookings. Writes nothing, creates no jobs."""
    await _auth(request)
    cfg, now = await get_settings(), datetime.now(IST)
    regs = await db().bb_registrations.find(
        {"schedule_date": {"$nin": [None, ""]}},
        {"full_name": 1, "phone": 1, "job_role": 1, "status": 1, "is_shortlisted": 1, "schedule_date": 1, "schedule_time": 1,
         "otp_verified": 1, "missed_marked": 1, "superseded": 1, "reschedule_count": 1, "isTest": 1}).sort("schedule_date", 1).to_list(500)
    ids = [str(r["_id"]) for r in regs]
    consents = {c["registration_id"]: c async for c in db().ai_candidate_consents.find({"registration_id": {"$in": ids}})}
    rows, counts = [], {"SCHEDULED": 0, "SKIPPED": 0, "NEEDS_REVIEW": 0}
    for r in regs:
        c = consents.get(str(r["_id"]), {})
        b = {**r, "ai_call_consent": {"status": c.get("consent_status")}, "do_not_call": c.get("do_not_call") is True}
        p = plan_booking(b, now, cfg)
        counts[p["status"]] += 1
        rows.append({"registration_id": str(r["_id"]), "candidate_name": r.get("full_name"), "phone_masked": _mask(r.get("phone")),
                     "job_role": r.get("job_role"), "booking_key": booking_key(r), "consent_status": c.get("consent_status", "none"),
                     **{k: p[k] for k in ("status", "reasons", "interview_at", "target_at", "planned_at", "adjustments", "retry")}})
    return {"warning": WARNING, "generated_at": now_iso(), "source": "bb_registrations (read-only)", "bookings": len(rows),
            "counts": counts, "eligible": counts["SCHEDULED"], "ineligible": counts["SKIPPED"] + counts["NEEDS_REVIEW"], "rows": rows}
