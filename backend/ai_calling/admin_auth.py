"""Slice 3 — Pending Authorization, Consent Editor, Capacity, Synthetic Preview.

New collections (independent of ai_candidate_consents so admin decisions never overwrite candidate records):
  ai_admin_authorizations       — admin alternative-basis grants per registration
  ai_admin_authorization_audit  — append-only audit trail (immutable)
  ai_consent_drafts             — current editable draft (single doc _id='current')
  ai_consent_versions           — immutable published versions

Authorization model (RBAC + ownership). Single-admin app; publish is gated to Admin User only.
Every route is admin-only through the existing _auth dep. authorize() denies by default.
"""
from datetime import datetime, timezone
from typing import List, Optional

from bson import ObjectId
from fastapi import APIRouter, Body, HTTPException, Query, Request
from pydantic import BaseModel

from .provider import _auth, _csrf
from .store import db, now_iso, serialize

admin_auth_router = APIRouter()
TOP_LEVEL_ADMIN = "Admin User"  # publishing permission; drafts are open to any admin
CONFIRM_PURPOSE = "interview_confirmation"
MISSED_PURPOSE = "missed_interview_followup"
PURPOSES = (CONFIRM_PURPOSE, MISSED_PURPOSE)


def _deny(kind: str, msg: str):
    """Deny-by-default helper. FORBIDDEN -> 403, NOT_VISIBLE -> 404."""
    code = 404 if kind == "NOT_VISIBLE" else 403
    raise HTTPException(code, msg)


def _can_publish_consent(principal: str) -> bool:
    return principal == TOP_LEVEL_ADMIN


# ---------------- Pending Authorization ----------------

class ReviewBody(BaseModel):
    registration_ids: List[str]
    purposes: List[str]              # subset of PURPOSES
    policy_id: Optional[str] = None  # approved lawful basis (not activatable until configured)
    evidence_ref: Optional[str] = None
    decision: str = "approve"        # "approve" | "defer" | "deny"
    reason: Optional[str] = None
    expected_version: Optional[int] = None  # frozen selection-snapshot version


async def _list_pending(filters: dict, page: int, page_size: int):
    """Future valid bookings whose admin authorization is absent/partial for at least one purpose."""
    today = datetime.now(timezone.utc).date().isoformat()
    q = {"interview_date": {"$gte": today},
         "booking_status": {"$nin": ["cancelled", "superseded", "replaced"]}}
    if filters.get("job_role"):
        q["job_role"] = filters["job_role"]
    if filters.get("date_from"):
        q["interview_date"] = {**q["interview_date"], "$gte": filters["date_from"]}
    if filters.get("date_to"):
        q["interview_date"] = {**q["interview_date"], "$lte": filters["date_to"]}
    total = await db().bb_registrations.count_documents(q)
    cursor = db().bb_registrations.find(q).sort([("interview_date", 1), ("_id", 1)]) \
        .skip((page - 1) * page_size).limit(page_size)
    regs = await cursor.to_list(page_size)
    out = []
    for r in regs:
        rid = str(r["_id"])
        cons = await db().ai_candidate_consents.find_one({"registration_id": rid}) or {}
        # candidate withdrawal / DNC are absolute — never selectable for override
        if cons.get("do_not_call") is True or cons.get("consent_status") == "withdrawn":
            continue
        auth = await db().ai_admin_authorizations.find_one(
            {"registration_id": rid, "revoked_at": {"$in": [None, False]}}) or {}
        granted = set(auth.get("purposes") or [])
        candidate_scopes = set(cons.get("scopes") or [])
        covered = candidate_scopes | granted
        uncovered = [p for p in PURPOSES if p not in covered]
        if not uncovered:
            continue  # fully covered -> not pending
        out.append({
            "registration_id": rid,
            "candidate_name": r.get("candidate_name") or r.get("name") or "",
            "job_role": r.get("job_role") or "",
            "phone_masked": (r.get("phone_e164", "")[:3] + "*****" + r.get("phone_e164", "")[-4:]) if r.get("phone_e164") else "",
            "interview_date": r.get("interview_date"),
            "interview_time": r.get("interview_time"),
            "booking_status": r.get("booking_status"),
            "consent_version": cons.get("text_version"),
            "consent_status": cons.get("consent_status") or "LEGACY_UNVERIFIED",
            "candidate_scopes": sorted(list(candidate_scopes)),
            "granted_scopes": sorted(list(granted)),
            "uncovered_purposes": uncovered,
            "review_reason": "partial_coverage" if covered else "no_prior_authorization",
        })
    return {"items": out, "total": total, "page": page, "page_size": page_size}


@admin_auth_router.get("/pending-authorization")
async def list_pending(request: Request, page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=200),
                       job_role: Optional[str] = None, date_from: Optional[str] = None, date_to: Optional[str] = None):
    await _auth(request)
    return await _list_pending({"job_role": job_role, "date_from": date_from, "date_to": date_to}, page, page_size)


@admin_auth_router.post("/pending-authorization/review")
async def bulk_review(body: ReviewBody, request: Request):
    """Record admin alternative-basis decisions. NEVER writes to ai_candidate_consents.
    This is NOT a dispatch trigger — the scheduler still re-evaluates every gate."""
    user = await _auth(request)
    _csrf(request)
    if body.decision not in ("approve", "defer", "deny"):
        _deny("FORBIDDEN", "decision must be approve, defer or deny")
    bad = [p for p in body.purposes if p not in PURPOSES]
    if bad:
        _deny("FORBIDDEN", f"invalid purposes: {bad}")
    if not body.registration_ids:
        raise HTTPException(400, "registration_ids is required")
    # Approve requires a policy ID + evidence (even though actual dispatch stays blocked this phase).
    if body.decision == "approve" and not (body.policy_id and body.evidence_ref):
        raise HTTPException(400, "Approval requires policy_id and evidence_ref")
    results = {"approved": [], "deferred": [], "denied": [], "skipped": []}
    now = now_iso()
    for rid in body.registration_ids:
        reg = await db().bb_registrations.find_one({"_id": ObjectId(rid)}) if ObjectId.is_valid(rid) else None
        if not reg:
            results["skipped"].append({"id": rid, "reason": "registration_not_found"}); continue
        cons = await db().ai_candidate_consents.find_one({"registration_id": rid}) or {}
        if cons.get("do_not_call") is True or cons.get("consent_status") == "withdrawn":
            results["skipped"].append({"id": rid, "reason": "candidate_opt_out_or_dnc"}); continue
        today = datetime.now(timezone.utc).date().isoformat()
        if (reg.get("interview_date") or "") < today or reg.get("booking_status") in ("cancelled", "superseded", "replaced"):
            results["skipped"].append({"id": rid, "reason": "booking_no_longer_valid"}); continue
        decision_key = {"approve": "approved", "defer": "deferred", "deny": "denied"}[body.decision]
        audit_doc = {"registration_id": rid, "decision": body.decision, "purposes": list(body.purposes),
                     "policy_id": body.policy_id, "evidence_ref": body.evidence_ref, "reason": (body.reason or "").strip()[:500],
                     "by": user, "at": now, "booking_version": reg.get("booking_version") or 0,
                     "note": "alternative-basis authorization; does NOT create candidate_consent; dispatch still gated by all safety checks"}
        await db().ai_admin_authorization_audit.insert_one(audit_doc)
        if body.decision == "approve":
            await db().ai_admin_authorizations.update_one(
                {"registration_id": rid},
                {"$set": {"registration_id": rid, "purposes": list(body.purposes), "policy_id": body.policy_id,
                          "evidence_ref": body.evidence_ref, "granted_by": user, "granted_at": now, "revoked_at": None,
                          "note": "dispatch-blocked until approved policy is activated"}},
                upsert=True)
        elif body.decision == "deny":
            await db().ai_admin_authorizations.update_one({"registration_id": rid},
                {"$set": {"revoked_at": now, "revoked_by": user, "revocation_reason": body.reason}})
        results[decision_key].append(rid)
    return {**results, "note": "No call was started. Dispatch remains blocked by the existing safety gates."}


@admin_auth_router.get("/pending-authorization/audit")
async def audit_list(request: Request, registration_id: Optional[str] = None, limit: int = Query(100, ge=1, le=500)):
    await _auth(request)
    q = {"registration_id": registration_id} if registration_id else {}
    docs = await db().ai_admin_authorization_audit.find(q, {"_id": 0}).sort("at", -1).to_list(limit)
    return {"items": docs, "total": len(docs)}


# ---------------- Consent Editor ----------------

class ConsentDraftBody(BaseModel):
    title: str
    text: str


class ConsentPublishBody(BaseModel):
    confirmation: str   # "PUBLISH CONSENT VERSION"


def _validate_text(title: str, text: str):
    if not title.strip() or len(title) > 200:
        raise HTTPException(400, "title must be 1–200 chars")
    if len(text.strip()) < 60:
        raise HTTPException(400, "text too short (min 60 chars)")
    if len(text) > 8000:
        raise HTTPException(400, "text too long (max 8000 chars)")


@admin_auth_router.get("/consent/editor")
async def get_editor(request: Request):
    await _auth(request)
    draft = await db().ai_consent_drafts.find_one({"_id": "current"}) or {}
    latest = await db().ai_consent_versions.find_one(sort=[("published_at", -1)])
    return {
        "draft": {"title": draft.get("title", ""), "text": draft.get("text", ""),
                  "saved_by": draft.get("saved_by"), "saved_at": draft.get("saved_at")},
        "latest_published": latest and {"version_id": latest["version_id"], "title": latest["title"],
                                        "text": latest["text"], "published_by": latest["published_by"],
                                        "published_at": latest["published_at"]} or None,
    }


@admin_auth_router.post("/consent/editor/draft")
async def save_draft(body: ConsentDraftBody, request: Request):
    user = await _auth(request)
    _csrf(request)
    _validate_text(body.title, body.text)
    await db().ai_consent_drafts.update_one({"_id": "current"},
        {"$set": {"title": body.title.strip(), "text": body.text.strip(), "saved_by": user, "saved_at": now_iso()}},
        upsert=True)
    return {"saved": True}


@admin_auth_router.get("/consent/versions")
async def list_versions(request: Request):
    await _auth(request)
    docs = await db().ai_consent_versions.find({}, {"_id": 0}).sort("published_at", -1).to_list(100)
    return {"items": docs, "total": len(docs)}


@admin_auth_router.post("/consent/publish")
async def publish_version(body: ConsentPublishBody, request: Request):
    """Only the designated top-level admin may publish. Published versions are immutable."""
    user = await _auth(request)
    _csrf(request)
    if not _can_publish_consent(user):
        _deny("FORBIDDEN", f"Only the top-level admin ({TOP_LEVEL_ADMIN}) may publish consent versions")
    if body.confirmation != "PUBLISH CONSENT VERSION":
        raise HTTPException(400, "Publishing requires typing: PUBLISH CONSENT VERSION")
    draft = await db().ai_consent_drafts.find_one({"_id": "current"})
    if not draft or not draft.get("text"):
        raise HTTPException(400, "No draft to publish")
    _validate_text(draft["title"], draft["text"])
    ts = now_iso()
    # include microseconds to avoid collisions when two publishes happen inside the same second
    version_id = f"consent-{ts[:10]}-{int(datetime.now(timezone.utc).timestamp() * 1_000_000)}"
    doc = {"version_id": version_id, "title": draft["title"], "text": draft["text"],
           "published_by": user, "published_at": ts,
           "note": "immutable; existing candidate consents retain the version they originally accepted"}
    await db().ai_consent_versions.insert_one(doc)
    await db().ai_call_audit.insert_one({"action": "consent_version_published", "by": user, "at": ts,
                                         "version_id": version_id, "title": doc["title"]})
    return {"published": True, "version_id": version_id}


# ---------------- Capacity summary & Preview scenarios ----------------

@admin_auth_router.get("/capacity-summary")
async def capacity_summary(request: Request):
    await _auth(request)
    from .modes import live_daily_cap
    from .store import get_settings
    s = await get_settings()
    eff = live_daily_cap(s)
    return {
        "test": {"daily_limit": s["daily_call_limit"], "max_concurrent": s["max_concurrent_calls"]},
        "live": {
            "configured_daily_maximum": s["live_daily_call_limit"],
            "pilot_daily_cap": s["live_pilot_daily_cap"],
            "effective_daily_maximum": eff,
            "max_concurrent": s["live_max_concurrent_calls"],
            "queue_capacity": s["live_queue_capacity"],
            "explanation": (f"Effective daily throughput is the LOWER of the configured daily maximum "
                            f"({s['live_daily_call_limit']}) and the pilot daily cap ({s['live_pilot_daily_cap']}). "
                            "The pilot cap controls current throughput while production authorization is pending."),
        },
    }


@admin_auth_router.get("/preview/scenarios")
async def preview_scenarios(request: Request, purpose: Optional[str] = None):
    """Synthetic scenarios for Preview & Diagnostics. Uses invented data only — no real records."""
    await _auth(request)
    confirm = [
        {"scenario": "1-day reminder", "due_time_ist": "T-1d 15:00", "eligibility": "ELIGIBLE",
         "blocking_reason": None, "retry_timeline": "one retry +60m if no-answer",
         "simulated_outcome": "CONFIRMED"},
        {"scenario": "Custom 3-day offset", "due_time_ist": "T-3d 10:30", "eligibility": "ELIGIBLE",
         "blocking_reason": None, "retry_timeline": "one retry +60m if no-answer",
         "simulated_outcome": "RESCHEDULE_REQUESTED"},
        {"scenario": "Short-notice booking (<2h)", "due_time_ist": "T-45m", "eligibility": "NEEDS_REVIEW",
         "blocking_reason": "less than 2 hours before interview",
         "retry_timeline": "no retry while under review", "simulated_outcome": "DEFERRED_TO_REVIEW"},
        {"scenario": "One no-answer retry", "due_time_ist": "T-1d 15:00 + retry +60m",
         "eligibility": "ELIGIBLE", "blocking_reason": None,
         "retry_timeline": "second call +60m; no further retries",
         "simulated_outcome": "CONFIRMED_ON_RETRY"},
        {"scenario": "Outside calling window (20:30 IST)", "due_time_ist": "T-1d 20:30",
         "eligibility": "DEFERRED", "blocking_reason": "outside 10:00–19:00 IST window",
         "retry_timeline": "moved to next window start", "simulated_outcome": "DEFERRED_TO_NEXT_WINDOW"},
    ]
    missed = [
        {"scenario": "Interview time passed, OTP empty", "due_time_ist": "T+60m", "otp_interpretation": "unverified",
         "eligibility": "ELIGIBLE", "blocking_reason": None,
         "retry_timeline": "one retry +30m if no-answer", "simulated_outcome": "MISSED_CONFIRMED"},
        {"scenario": "OTP verified at office", "due_time_ist": "T+60m", "otp_interpretation": "verified",
         "eligibility": "BLOCKED", "blocking_reason": "OTP verified — candidate attended; follow-up cancelled",
         "retry_timeline": "no retry", "simulated_outcome": "CANCELLED_ATTENDANCE_VERIFIED"},
        {"scenario": "OTP field missing on record", "due_time_ist": "T+60m", "otp_interpretation": "missing_blocked",
         "eligibility": "BLOCKED", "blocking_reason": "OTP value unexpected/missing — remains blocked rather than assumed false",
         "retry_timeline": "no retry", "simulated_outcome": "NEEDS_REVIEW"},
        {"scenario": "OTP verified before dispatch", "due_time_ist": "T+60m dispatch",
         "otp_interpretation": "verified_just_now", "eligibility": "BLOCKED",
         "blocking_reason": "re-check caught verified status before dispatch",
         "retry_timeline": "no retry", "simulated_outcome": "CANCELLED"},
        {"scenario": "Candidate running late", "due_time_ist": "T+60m",
         "otp_interpretation": "unverified", "eligibility": "ELIGIBLE", "blocking_reason": None,
         "retry_timeline": "no retry after answer", "simulated_outcome": "RUNNING_LATE_ALERT"},
        {"scenario": "Claims attended", "due_time_ist": "T+60m", "otp_interpretation": "unverified",
         "eligibility": "ELIGIBLE", "blocking_reason": None,
         "retry_timeline": "no retry after answer", "simulated_outcome": "ATTENDANCE_DISPUTE_ALERT (OTP unchanged)"},
        {"scenario": "Candidate requests reschedule", "due_time_ist": "T+60m",
         "otp_interpretation": "unverified", "eligibility": "ELIGIBLE", "blocking_reason": None,
         "retry_timeline": "no retry", "simulated_outcome": "RESCHEDULE_REQUEST_FOR_HR_REVIEW"},
        {"scenario": "Candidate requests Do Not Call", "due_time_ist": "T+60m",
         "otp_interpretation": "unverified", "eligibility": "ELIGIBLE", "blocking_reason": None,
         "retry_timeline": "no retry", "simulated_outcome": "DO_NOT_CALL_RECORDED"},
        {"scenario": "One no-answer retry (+30m)", "due_time_ist": "T+60m, retry +30m",
         "otp_interpretation": "unverified", "eligibility": "ELIGIBLE", "blocking_reason": None,
         "retry_timeline": "second call +30m; no further retries",
         "simulated_outcome": "MISSED_CONFIRMED_ON_RETRY"},
        {"scenario": "Window extends to 19:30 IST", "due_time_ist": "19:25 IST",
         "otp_interpretation": "unverified", "eligibility": "ELIGIBLE", "blocking_reason": None,
         "retry_timeline": "retry moves to next day if outside 19:30 boundary",
         "simulated_outcome": "DEFERRED_IF_PAST_WINDOW"},
    ]
    if purpose == CONFIRM_PURPOSE:
        return {"purpose": CONFIRM_PURPOSE, "scenarios": confirm}
    if purpose == MISSED_PURPOSE:
        return {"purpose": MISSED_PURPOSE, "scenarios": missed}
    return {"interview_confirmation": confirm, "missed_interview_followup": missed}


async def ensure_admin_auth_indexes():
    """Create indexes used by this module."""
    await db().ai_admin_authorizations.create_index("registration_id", unique=True)
    await db().ai_admin_authorization_audit.create_index([("registration_id", 1), ("at", -1)])
    await db().ai_consent_versions.create_index("version_id", unique=True)
    await db().ai_consent_versions.create_index("published_at")
