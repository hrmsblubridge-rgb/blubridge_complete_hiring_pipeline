"""Phase 7C-A: candidate AI-call consent with dedicated, hashed, expiring consent-management tokens,
candidate/admin Do Not Call, and the read-only Real Bookings preview. Nothing here dispatches calls
or edits bookings, and no WhatsApp/email is sent."""
import hashlib
import logging
import os
import secrets
from datetime import datetime, timedelta, timezone

from bson import ObjectId
from fastapi import APIRouter, Body, HTTPException, Request, Response
from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError

from .dryrun import WARNING, _mask, booking_key, plan_booking
from .modes import CONSENT_TEXT, CONSENT_TITLE, CONSENT_TEXT_VERSION
from .provider import _auth, _csrf
from .store import IST, db, get_settings, now_iso

_logger = logging.getLogger("ai_calling.consent")
public_router = APIRouter(prefix="/public")
admin_router = APIRouter()

PURPOSE = "ai_consent_manage"
TOKEN_HEADER = "X-Consent-Token"
TOKEN_TTL_DAYS = 30
OTP_TTL = timedelta(minutes=10)
OTP_MAX_ATTEMPTS = 5
OTP_DELIVERY_APPROVED = False  # renewal codes need an owner-approved delivery channel (not sent in Phase 7C-A)
RATE_WINDOW = timedelta(minutes=15)
RATE_MAX_FAILURES = 10
DNC_SOURCES = ("ADMIN", "CANDIDATE", "AI_CALL_OPT_OUT")
NO_STORE = {"Cache-Control": "no-store, max-age=0", "Pragma": "no-cache", "Referrer-Policy": "no-referrer",
            "X-Robots-Tag": "noindex"}


def _ttl_days() -> int:
    return int(os.environ.get("AI_CONSENT_TOKEN_TTL_DAYS") or TOKEN_TTL_DAYS)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _now() -> datetime:
    return datetime.now(timezone.utc)


def top_level_admins() -> set:
    return {u.strip() for u in os.environ.get("AI_TOP_LEVEL_ADMINS", "").split(",") if u.strip()}


async def ensure_consent_indexes():
    await db().ai_consent_tokens.create_index("token_hash", unique=True)
    await db().ai_consent_tokens.create_index([("registration_id", 1), ("revoked_at", 1)])
    await db().ai_consent_rate.create_index("expires_at", expireAfterSeconds=0)
    await db().ai_consent_otps.create_index("expires_at", expireAfterSeconds=0)


# ---------- tokens ----------

async def issue_token(reg_id: str, reason: str) -> str:
    """New 256-bit token; every OLDER active token for this registration is revoked (rotation).
    Ordering by _id makes concurrent issuance converge on exactly one active token. Only the hash is stored."""
    token = secrets.token_urlsafe(32)
    now = _now()
    h = hash_token(token)
    res = await db().ai_consent_tokens.insert_one({"token_hash": h, "registration_id": reg_id, "purpose": PURPOSE,
                                                   "created_at": now.isoformat(), "issued_reason": reason,
                                                   "expires_at": (now + timedelta(days=_ttl_days())).isoformat(), "revoked_at": None})
    await db().ai_consent_tokens.update_many({"registration_id": reg_id, "revoked_at": None, "_id": {"$lt": res.inserted_id}},
                                             {"$set": {"revoked_at": now.isoformat(), "revoke_reason": "replaced"}})
    if await db().ai_consent_tokens.count_documents({"registration_id": reg_id, "revoked_at": None, "_id": {"$gt": res.inserted_id}}):
        await db().ai_consent_tokens.update_one({"_id": res.inserted_id}, {"$set": {"revoked_at": now_iso(), "revoke_reason": "replaced"}})
    await _audit("consent_token_issued", "system", reg_id, {"reason": reason, "token_ref": h[:8]})
    return token


async def revoke_tokens(reg_id: str, reason: str) -> int:
    res = await db().ai_consent_tokens.update_many({"registration_id": reg_id, "revoked_at": None},
                                                   {"$set": {"revoked_at": now_iso(), "revoke_reason": reason}})
    return res.modified_count


def _ip_key(request: Request) -> str:
    """Client IP = the X-Forwarded-For entry appended by the first trusted proxy (counted from the right),
    so client-supplied left-hand entries cannot rotate the rate-limit key."""
    hops = int(os.environ.get("AI_TRUSTED_PROXY_HOPS") or 0)
    chain = [x.strip() for x in (request.headers.get("x-forwarded-for") or "").split(",") if x.strip()]
    ip = chain[-hops] if hops and len(chain) >= hops else (chain[0] if chain and not hops else "")
    ip = ip or (request.client.host if request.client else "")
    return hashlib.sha256(f"consent-rl|{ip}".encode()).hexdigest()[:32]


async def _check_rate(request: Request):
    doc = await db().ai_consent_rate.find_one({"_id": _ip_key(request)})
    if doc and doc.get("failures", 0) >= RATE_MAX_FAILURES:
        raise HTTPException(429, "Too many invalid attempts. Please try again later.")


async def _fail(request: Request, status: int = 404, msg: str = "Invalid or expired link"):
    exp = _now() + RATE_WINDOW
    await db().ai_consent_rate.update_one({"_id": _ip_key(request)},
                                          {"$inc": {"failures": 1}, "$setOnInsert": {"expires_at": exp}}, upsert=True)
    raise HTTPException(status, msg)


async def resolve_token(request: Request) -> dict:
    """Authentic, unrevoked, correct-purpose token → {reg_id, expired}. Expired tokens are returned flagged."""
    await _check_rate(request)
    token = request.headers.get(TOKEN_HEADER) or ""
    if not (32 <= len(token) <= 128):
        await _fail(request)
    t = await db().ai_consent_tokens.find_one({"token_hash": hash_token(token)})
    if not t or t.get("purpose") != PURPOSE or t.get("revoked_at") or not ObjectId.is_valid(t.get("registration_id", "")):
        await _fail(request)
    reg = await db().bb_registrations.find_one({"_id": ObjectId(t["registration_id"])},
                                               {"_id": 1, "full_name": 1, "schedule_date": 1, "schedule_time": 1,
                                                "reschedule_count": 1})
    if not reg:
        await _fail(request)
    return {"reg": reg, "reg_id": t["registration_id"], "expired": t["expires_at"] <= _now().isoformat(),
            "expires_at": t["expires_at"]}


# ---------- consent + Do Not Call ----------

async def _audit(action: str, actor: str, reg_id: str, detail: dict = None):
    await db().ai_call_audit.insert_one({"action": action, "by": actor, "registration_id": reg_id,
                                         "detail": detail or {}, "at": now_iso()})


async def invalidate_pending(reg_id: str, reason: str) -> int:
    """Cancel pending live work (real and mock) for this exact registration only. Interviews are never touched."""
    n = (await db().ai_call_jobs.update_many({"mode": "live", "registration_id": reg_id, "status": "pending"},
                                             {"$set": {"status": "cancelled", "cancel_reason": reason}})).modified_count
    n += (await db().ai_live_mock_jobs.update_many(
        {"registration_id": reg_id, "status": {"$in": ["planned", "claimed"]}},
        {"$set": {"status": "invalidated", "reasons": [reason.upper()], "invalidated_at": now_iso()}})).modified_count
    return n


async def record_consent(reg_id: str, status: str, source: str, actor: str, bkey: str = None) -> dict:
    now = now_iso()
    st = {"consent_status": status, "consent_source": source, "consent_text_version": CONSENT_TEXT_VERSION,
          "updated_at": now, "last_change_at": now}
    if status == "granted":
        st.update(consent_timestamp=now, consent_withdrawn_at=None)
    elif status == "withdrawn":
        st["consent_withdrawn_at"] = now
    upd = {"$set": st, "$setOnInsert": {"registration_id": reg_id, "do_not_call": False, "dnc_sources": [], "created_at": now},
           "$push": {"history": {"type": "consent", "status": status, "source": source, "by": actor, "at": now,
                                 "text_version": CONSENT_TEXT_VERSION}}}
    if bkey:
        upd["$addToSet"] = {"booking_form_keys": bkey}
    await db().ai_candidate_consents.update_one({"registration_id": reg_id}, upd, upsert=True)
    if status != "granted":
        await invalidate_pending(reg_id, f"consent_{status}")
    await _audit(f"consent_{status}", actor, reg_id, {"source": source, "text_version": CONSENT_TEXT_VERSION})
    return await db().ai_candidate_consents.find_one({"registration_id": reg_id}, {"_id": 0, "history": 0})


async def set_dnc(reg_id: str, source: str, actor: str, add: bool, reason: str = "") -> dict:
    """Do Not Call is the union of sources. Removing one source never removes another, never restores consent."""
    assert source in DNC_SOURCES
    now = now_iso()
    await db().ai_candidate_consents.update_one(
        {"registration_id": reg_id},
        {"$setOnInsert": {"registration_id": reg_id, "consent_status": "not_given", "created_at": now, "dnc_sources": []}},
        upsert=True)
    op = {"$addToSet": {"dnc_sources": source}} if add else {"$pull": {"dnc_sources": source}}
    await db().ai_candidate_consents.update_one({"registration_id": reg_id}, {**op, "$push": {"history": {
        "type": "dnc", "action": "mark" if add else "remove", "source": source, "by": actor, "reason": reason[:300], "at": now}}})
    doc = await db().ai_candidate_consents.find_one_and_update(
        {"registration_id": reg_id}, [{"$set": {"do_not_call": {"$gt": [{"$size": {"$ifNull": ["$dnc_sources", []]}}, 0]},
                                                 "updated_at": now, "last_change_at": now,
                                                 **({"dnc_at": now, "dnc_by": actor, "dnc_reason": reason[:300]} if add else {})}}],
        return_document=ReturnDocument.AFTER, projection={"_id": 0, "history": 0})
    if add:
        await invalidate_pending(reg_id, f"do_not_call_{source.lower()}")
    await _audit("dnc_marked" if add else "dnc_removed", actor, reg_id, {"source": source, "reason": reason[:300]})
    return doc


async def apply_ai_opt_out(reg_id: str) -> dict:
    """For future live results: an AI call that extracted DO_NOT_CALL blocks all further AI calls."""
    return await set_dnc(reg_id, "AI_CALL_OPT_OUT", "ai_call", True, "Candidate asked not to be called during an AI call")


async def _safe(coro_fn, reg_id: str, intended: str):
    try:
        return await coro_fn()
    except Exception as e:  # noqa: BLE001 — never claim it was saved; the booking is unaffected
        _logger.error(f"[Consent] persist failed reg={reg_id}: {type(e).__name__}")
        try:
            await _audit("consent_persist_failed", "candidate", reg_id, {"intended": intended, "error": type(e).__name__})
        except Exception:  # noqa: BLE001
            pass
        raise HTTPException(503, "Your interview is booked, but your AI call preference could not be saved. It counts as NOT given.") from None


# ---------- public (candidate) routes ----------

@public_router.get("/consent-text")
async def consent_text(response: Response):
    response.headers.update(NO_STORE)
    return {"title": CONSENT_TITLE, "text": CONSENT_TEXT, "version": CONSENT_TEXT_VERSION, "optional": True, "default_checked": False}


@public_router.post("/booking-consent/{schedule_token}")
async def booking_decision(schedule_token: str, request: Request, response: Response, body: dict = Body(...)):  # noqa: B008
    """Booking page only: one decision per booked slot, made right after booking. Returns the dedicated
    consent-management token ONCE; the booking token can never manage or withdraw consent afterwards."""
    response.headers.update(NO_STORE)
    await _check_rate(request)
    reg = await db().bb_registrations.find_one({"schedule_token": schedule_token}, {"_id": 1, "schedule_date": 1, "schedule_time": 1,
                                                                                    "reschedule_count": 1}) \
        if schedule_token and len(schedule_token) >= 16 else None
    if not reg:
        await _fail(request)
    if not reg.get("schedule_date"):
        raise HTTPException(409, "No interview booking found for this link")
    if body.get("text_version") != CONSENT_TEXT_VERSION:
        raise HTTPException(409, "Consent wording changed. Your preference was not saved.")
    rid, bkey = str(reg["_id"]), booking_key(reg)
    status = "granted" if body.get("granted") is True else "not_given"
    try:  # atomic one-decision-per-booked-slot claim (unique registration_id index)
        await db().ai_candidate_consents.update_one(
            {"registration_id": rid, "booking_form_keys": {"$ne": bkey}},
            {"$addToSet": {"booking_form_keys": bkey},
             "$setOnInsert": {"consent_status": "not_given", "do_not_call": False, "dnc_sources": [], "created_at": now_iso()}},
            upsert=True)
    except DuplicateKeyError:
        raise HTTPException(409, "A preference was already recorded for this booking. Use your consent-management link.") from None

    async def save():
        c = await record_consent(rid, status, "booking_form", "candidate")
        return c, await issue_token(rid, "booking")
    c, token = await _safe(save, rid, status)
    return {"saved": True, "consent_status": c["consent_status"], "manage_token": token,
            "manage_expires_days": _ttl_days()}


def _info(t: dict, c: dict) -> dict:
    status = c.get("consent_status", "not_given")
    return {"first_name": (t["reg"].get("full_name") or "").split(" ")[0], "has_booking": bool(t["reg"].get("schedule_date")),
            "consent_status": status, "do_not_call": bool(c.get("do_not_call")),
            "candidate_dnc": "CANDIDATE" in (c.get("dnc_sources") or []), "expired": t["expired"],
            "expires_at": t["expires_at"], "can_withdraw": status == "granted",
            "can_grant": not t["expired"] and status != "granted" and bool(t["reg"].get("schedule_date"))
            and not set(c.get("dnc_sources") or []) & {"CANDIDATE", "AI_CALL_OPT_OUT"},
            "renewal_available": OTP_DELIVERY_APPROVED,
            "title": CONSENT_TITLE, "text": CONSENT_TEXT, "version": CONSENT_TEXT_VERSION}


@public_router.get("/consent/manage")
async def manage_info(request: Request, response: Response):
    response.headers.update(NO_STORE)
    t = await resolve_token(request)
    return _info(t, await db().ai_candidate_consents.find_one({"registration_id": t["reg_id"]}) or {})


@public_router.post("/consent/manage/withdraw")
async def manage_withdraw(request: Request, response: Response):
    """Allowed with an authentic token even after expiry (withdraw-only); never with a revoked/replaced one."""
    response.headers.update(NO_STORE)
    t = await resolve_token(request)
    src = "consent_page_expired_link" if t["expired"] else "consent_page"
    c = await _safe(lambda: record_consent(t["reg_id"], "withdrawn", src, "candidate"), t["reg_id"], "withdrawn")
    return {"saved": True, "consent_status": c["consent_status"], "interview_unchanged": True}


@public_router.post("/consent/manage/do-not-call")
async def manage_dnc(request: Request, response: Response):
    response.headers.update(NO_STORE)
    t = await resolve_token(request)
    c = await _safe(lambda: set_dnc(t["reg_id"], "CANDIDATE", "candidate", True, "Candidate request via consent page"),
                    t["reg_id"], "do_not_call")
    return {"saved": True, "do_not_call": c["do_not_call"], "interview_unchanged": True}


@public_router.post("/consent/manage/grant")
async def manage_grant(request: Request, response: Response, body: dict = Body(...)):  # noqa: B008
    response.headers.update(NO_STORE)
    t = await resolve_token(request)
    if t["expired"]:
        raise HTTPException(403, "This link has expired. It can only be used to withdraw consent.")
    if not t["reg"].get("schedule_date"):
        raise HTTPException(409, "No interview booking found")
    if body.get("text_version") != CONSENT_TEXT_VERSION:
        raise HTTPException(409, "Consent wording changed. Please reload.")
    cur = await db().ai_candidate_consents.find_one({"registration_id": t["reg_id"]}, {"dnc_sources": 1}) or {}
    if set(cur.get("dnc_sources") or []) & {"CANDIDATE", "AI_CALL_OPT_OUT"}:
        raise HTTPException(409, "You asked not to receive AI calls. That request stays in place.")
    c = await record_consent(t["reg_id"], "granted", "consent_page", "candidate")
    return {"saved": True, "consent_status": c["consent_status"], "do_not_call": bool(c.get("do_not_call"))}


@public_router.post("/consent/manage/rotate")
async def manage_rotate(request: Request, response: Response):
    response.headers.update(NO_STORE)
    t = await resolve_token(request)
    if t["expired"]:
        raise HTTPException(403, "This link has expired. It can only be used to withdraw consent.")
    return {"manage_token": await issue_token(t["reg_id"], "rotation"), "manage_expires_days": _ttl_days()}


# ---------- prepared one-time-code renewal (delivery NOT approved: nothing is sent) ----------

async def create_otp(reg_id: str) -> tuple:
    """Prepared for an owner-approved delivery channel. Returns (challenge_id, code); only the code hash is stored."""
    cid, code = secrets.token_urlsafe(16), f"{secrets.randbelow(10**6):06d}"
    await db().ai_consent_otps.insert_one({"_id": cid, "registration_id": reg_id, "code_hash": hash_token(f"{cid}|{code}"),
                                           "attempts": 0, "used": False, "expires_at": _now() + OTP_TTL})
    return cid, code


@public_router.post("/consent/renew/request")
async def renew_request(response: Response):
    response.headers.update(NO_STORE)
    raise HTTPException(501, "New consent links cannot be sent yet. To stop AI calls, use your existing link "
                             "(it can always withdraw consent) or contact the HR team.")


@public_router.post("/consent/renew/verify")
async def renew_verify(request: Request, response: Response, body: dict = Body(...)):  # noqa: B008
    response.headers.update(NO_STORE)
    await _check_rate(request)
    cid, code = str(body.get("challenge_id") or ""), str(body.get("code") or "")
    ch = await db().ai_consent_otps.find_one_and_update(
        {"_id": cid, "used": False, "attempts": {"$lt": OTP_MAX_ATTEMPTS}, "expires_at": {"$gt": _now()}},
        {"$inc": {"attempts": 1}}, return_document=ReturnDocument.AFTER)
    if not ch or not secrets.compare_digest(ch["code_hash"], hash_token(f"{cid}|{code}")):
        await _fail(request, 400, "Invalid or expired code")
    used = await db().ai_consent_otps.update_one({"_id": cid, "used": False}, {"$set": {"used": True}})
    if not used.modified_count:
        await _fail(request, 400, "Invalid or expired code")
    return {"manage_token": await issue_token(ch["registration_id"], "otp_renewal"), "manage_expires_days": _ttl_days()}


# ---------- renewal via the existing private booking link + last 4 mobile digits ----------
RENEW_MAX_FAILURES = 5
RENEW_LOCKOUT = timedelta(minutes=30)
RENEW_GENERIC = "We could not verify these details. Please check and try again."


async def _renew_fail(request: Request, rid: str = None):
    if rid:
        g = await db().ai_consent_renew_guard.find_one_and_update(
            {"_id": rid}, {"$inc": {"failures": 1}, "$set": {"last_failure_at": now_iso()}}, upsert=True,
            return_document=ReturnDocument.AFTER)
        if g["failures"] >= RENEW_MAX_FAILURES:
            await db().ai_consent_renew_guard.update_one(
                {"_id": rid}, {"$set": {"failures": 0, "locked_until": (_now() + RENEW_LOCKOUT).isoformat()}})
            await _audit("consent_renewal_locked", "candidate", rid, {})
    await _fail(request, 400, RENEW_GENERIC)


@public_router.post("/consent/renew/booking")
async def renew_with_booking(request: Request, response: Response, body: dict = Body(...)):  # noqa: B008
    """Booking link (something they were sent) + last 4 digits of the registered mobile (something they know).
    Issues a NEW consent token only; never changes consent, the booking, or the booking token. Sends nothing."""
    response.headers.update(NO_STORE)
    await _check_rate(request)
    stoken, last4 = str(body.get("schedule_token") or ""), str(body.get("phone_last4") or "")
    if not (16 <= len(stoken) <= 128) or not (len(last4) == 4 and last4.isdigit()):
        await _renew_fail(request)
    reg = await db().bb_registrations.find_one({"schedule_token": stoken}, {"_id": 1, "phone": 1, "schedule_date": 1})
    if not reg or not reg.get("schedule_date"):
        await _renew_fail(request)
    rid = str(reg["_id"])
    g = await db().ai_consent_renew_guard.find_one({"_id": rid}) or {}
    if (g.get("locked_until") or "") > _now().isoformat():
        await _fail(request, 400, RENEW_GENERIC)  # same response as any other failure; counts toward the IP limit
    digits = "".join(ch for ch in str(reg.get("phone") or "") if ch.isdigit())
    if len(digits) < 4 or not secrets.compare_digest(digits[-4:], last4):
        await _renew_fail(request, rid)
    await db().ai_consent_renew_guard.update_one({"_id": rid}, {"$set": {"failures": 0}})
    token = await issue_token(rid, "booking_link_renewal")
    return {"manage_token": token, "manage_expires_days": _ttl_days(), "consent_changed": False}


# ---------- admin routes ----------

async def _reg_or_404(reg_id: str) -> dict:
    reg = await db().bb_registrations.find_one({"_id": ObjectId(reg_id)}, {"_id": 1, "full_name": 1}) \
        if ObjectId.is_valid(reg_id) else None
    if not reg:
        raise HTTPException(404, "Registration not found")
    return reg


def _admin_view(reg_id: str, c: dict, user: str, tok: dict) -> dict:
    sources = c.get("dnc_sources") or []
    hist = [{k: h.get(k) for k in ("type", "status", "action", "source", "by", "reason", "at")} for h in (c.get("history") or [])][-10:]
    return {"registration_id": reg_id, "consent_status": c.get("consent_status", "none"),
            "consent_timestamp": c.get("consent_timestamp"), "consent_source": c.get("consent_source"),
            "consent_text_version": c.get("consent_text_version"), "consent_withdrawn_at": c.get("consent_withdrawn_at"),
            "do_not_call": bool(c.get("do_not_call")), "dnc_sources": sources, "dnc_at": c.get("dnc_at"),
            "dnc_by": c.get("dnc_by"), "dnc_reason": c.get("dnc_reason"), "last_change_at": c.get("last_change_at") or c.get("updated_at"),
            "history": list(reversed(hist)), "is_top_level_admin": user in top_level_admins(),
            "can_remove_dnc": user in top_level_admins() and "ADMIN" in sources,
            "manage_link": {"active": bool(tok), "expires_at": (tok or {}).get("expires_at")}}


@admin_router.get("/consent/admin/{reg_id}")
async def admin_consent(reg_id: str, request: Request):
    user = await _auth(request)
    await _reg_or_404(reg_id)
    c = await db().ai_candidate_consents.find_one({"registration_id": reg_id}) or {}
    tok = await db().ai_consent_tokens.find_one({"registration_id": reg_id, "revoked_at": None}, {"expires_at": 1})
    return _admin_view(reg_id, c, user, tok)


@admin_router.post("/consent/admin/{reg_id}/dnc")
async def admin_dnc(reg_id: str, request: Request, body: dict = Body(...)):  # noqa: B008
    """Any admin may mark; only a designated top-level admin may remove, and only an ADMIN-sourced restriction."""
    user = await _auth(request)
    _csrf(request)
    await _reg_or_404(reg_id)
    action, reason = body.get("action"), str(body.get("reason") or "").strip()
    if body.get("confirm") is not True:
        raise HTTPException(400, "Confirmation required")
    if action == "mark":
        await set_dnc(reg_id, "ADMIN", user, True, reason or "Marked by admin")
    elif action == "remove":
        if user not in top_level_admins():
            raise HTTPException(403, "Only a top-level administrator can remove Do Not Call")
        c = await db().ai_candidate_consents.find_one({"registration_id": reg_id}) or {}
        if "ADMIN" not in (c.get("dnc_sources") or []):
            raise HTTPException(409, "There is no admin-imposed Do Not Call to remove")
        if not reason:
            raise HTTPException(400, "A reason is required to remove Do Not Call")
        await set_dnc(reg_id, "ADMIN", user, False, reason)
    else:
        raise HTTPException(400, "action must be mark or remove")
    return await admin_consent(reg_id, request)


@admin_router.post("/consent/admin/{reg_id}/revoke-links")
async def admin_revoke_links(reg_id: str, request: Request):
    user = await _auth(request)
    _csrf(request)
    await _reg_or_404(reg_id)
    n = await revoke_tokens(reg_id, f"admin_revoked:{user}")
    await _audit("consent_tokens_revoked", user, reg_id, {"count": n})
    return {"revoked": n}


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
