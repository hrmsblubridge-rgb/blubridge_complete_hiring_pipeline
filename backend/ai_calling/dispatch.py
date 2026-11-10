"""Phase 4B: ONE explicitly authorised Testing-Mode call + read-only reconciliation. No retries, no batches."""
import asyncio
import logging
import re
import uuid
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse

import httpx
from bson import ObjectId
from fastapi import APIRouter, Body, HTTPException, Request
from fastapi.responses import StreamingResponse
from pymongo.errors import DuplicateKeyError

from . import bolna_client as bc
from . import gate
from .calls import apply_execution
from .execution import TERMINAL, user_data_for
from .provider import _auth, _csrf, _doc, decrypt_api_key
from .store import SETTINGS_ID, db, mask_phone, now_iso, serialize

_logger = logging.getLogger("ai_calling.dispatch")
dispatch_router = APIRouter()
IDEM = re.compile(r"[A-Za-z0-9\-]{16,64}")
BLOCKING = ["dispatching", "accepted", "pending_reconciliation", "needs_review"]
POLLED = ["accepted", "pending_reconciliation"]
POLL_SECONDS = 150
REVIEW_AFTER = timedelta(minutes=30)
HIDDEN = ("recipient_e164", "recording_url")
_poller = {"task": None}


def ui_state(c: dict) -> str:
    st = c.get("state")
    if st in ("dispatching", "pending_reconciliation"):
        return "Pending"
    if st == "accepted":
        return "In Progress"
    if st == "finished":
        return "Completed" if c.get("status") == "completed" else "Failed"
    return {"rejected": "Failed", "needs_review": "Needs Review", "reviewed": "Reviewed"}.get(st, st or "Unknown")


def public_call(doc: dict, full: bool = True) -> dict:
    d = {k: v for k, v in serialize(doc).items() if k not in HIDDEN}
    if not full:
        for k in ("transcript", "extracted_data_raw"):
            d.pop(k, None)
    d["has_recording"] = bool(doc.get("recording_url"))
    d["ui_state"] = ui_state(doc)
    return d


async def _audit(action: str, user: str, call_id: str = "", cid: str = "", detail: str = ""):
    await db().ai_call_audit.insert_one({"action": action, "by": user, "call_id": call_id,
                                         "test_candidate_id": cid, "detail": detail, "at": now_iso()})
    _logger.info(f"[SingleCall] {action} call={call_id} candidate={cid} by={user} {detail}")


async def _reengage_stop(auth_id: str):
    await db().ai_call_settings.update_one({"_id": SETTINGS_ID}, {
        "$set": {"emergency_stop": True, "emergency_stop_at": now_iso(), "emergency_stop_by": f"system:single-call:{auth_id}"},
        "$unset": {"emergency_stop_released_for": ""}})


async def _release_lock(auth_id: str):
    await db().ai_call_settings.update_one({"_id": SETTINGS_ID, "dispatch_lock.id": auth_id}, {"$set": {"dispatch_lock": None}})


async def _set_call(call_id, job_id, call_set: dict, job_status: str):
    await db().ai_calls.update_one({"_id": call_id}, {"$set": {**call_set, "updated_at": now_iso()}})
    await db().ai_call_jobs.update_one({"_id": job_id}, {"$set": {"status": job_status, "updated_at": now_iso()}})


@dispatch_router.post("/test-candidates/{cid}/call-now")
async def call_now(cid: str, request: Request, body: dict = Body(...)):  # noqa: B008
    user = await _auth(request)
    _csrf(request)
    key = str(body.get("idempotency_key") or "")
    if not IDEM.fullmatch(key):
        raise HTTPException(400, "Missing or invalid idempotency key")
    if not ObjectId.is_valid(cid):
        raise HTTPException(404, "Test candidate not found")
    prior = await db().ai_call_jobs.find_one({"idempotency_key": key})
    if prior:
        return {"dispatched": False, "duplicate": True, "call_id": prior.get("call_id")}
    cand = await db().ai_test_candidates.find_one({"_id": ObjectId(cid), "mode": "testing"})
    if not cand:
        raise HTTPException(404, "Test candidate not found")
    if str(body.get("confirm_name") or "").strip() != cand["candidate_name"].strip():
        raise HTTPException(400, "Type the candidate's exact name to authorise this call")
    if await db().ai_calls.find_one({"mode": "testing", "state": {"$in": BLOCKING}}, {"_id": 1}):
        raise HTTPException(409, "Another test call is still unresolved. Wait for its result or review it first.")

    auth_id = uuid.uuid4().hex
    s = await db().ai_call_settings.find_one_and_update(
        {"_id": SETTINGS_ID, "mode": "testing", "dispatch_lock": None},
        {"$set": {"dispatch_lock": {"id": auth_id, "by": user, "at": now_iso()}, "emergency_stop": False,
                  "emergency_stop_released_for": auth_id, "emergency_stop_released_at": now_iso()}})
    if not s:
        raise HTTPException(409, "Testing Mode is not active or another call authorisation is in progress")
    try:
        verdict = await gate.evaluate(mode="testing", test_candidate_id=cid, batch_id="", phone_e164=cand["phone_e164"],
                                      mode_version=s["mode_version"], single_call=True)
        if not verdict["allowed"]:
            failed = [c["label"] for c in verdict["checks"] if not c["ok"]]
            await _audit("dispatch_denied", user, cid=cid, detail="; ".join(failed))
            raise HTTPException(412, "Call blocked: " + "; ".join(failed))
        prov = await _doc()
        api_key = decrypt_api_key(prov)
        req = bc.build_call_request(agent_id=prov["agent_id"], recipient=cand["phone_e164"],
                                    from_number=prov["caller_number"], user_data=user_data_for(cand))
        now = now_iso()
        try:
            jres = await db().ai_call_jobs.insert_one({
                "mode": "testing", "batch_id": f"single:{auth_id}", "test_candidate_id": cid, "attempt": 1,
                "idempotency_key": key, "authorization_id": auth_id, "status": "claimed",
                "mode_version": s["mode_version"], "created_by": user, "created_at": now})
        except DuplicateKeyError:
            raise HTTPException(409, "This call was already authorised") from None
        cres = await db().ai_calls.insert_one({
            "mode": "testing", "job_id": str(jres.inserted_id), "authorization_id": auth_id, "test_candidate_id": cid,
            "test_candidate_code": cand.get("test_candidate_id"), "candidate_name": cand["candidate_name"],
            "phone_masked": mask_phone(cand["phone_e164"]), "recipient_e164": cand["phone_e164"],
            "job_role": cand.get("job_role"), "interview_date": cand.get("interview_date"),
            "interview_time": cand.get("interview_time"), "language": cand.get("language"),
            "company_name": cand.get("company_name"), "agent_id": prov["agent_id"],
            "from_masked": mask_phone(prov["caller_number"]), "user_data": req["user_data"],
            "state": "dispatching", "status": "", "authorized_by": user, "authorized_name": cand["candidate_name"],
            "created_at": now, "dispatched_at": now})
        call_id, job_id = cres.inserted_id, jres.inserted_id
        await db().ai_call_jobs.update_one({"_id": job_id}, {"$set": {"call_id": str(call_id)}})
        await _audit("dispatch_authorized", user, str(call_id), cid, "one outbound request authorised")
    except BaseException:
        await _release_lock(auth_id)
        raise
    finally:
        await _reengage_stop(auth_id)

    try:
        res = await bc.place_call(gate_result=verdict, api_key=api_key, body=req)
        await _set_call(call_id, job_id, {"state": "accepted", "execution_id": res["execution_id"],
                                          "status": res["status"], "initial_provider_status": res["status"],
                                          "accepted_at": now_iso()}, "initiated")
        outcome = {"state": "accepted", "status": res["status"]}
    except bc.BolnaRejected as e:
        await _set_call(call_id, job_id, {"state": "rejected", "status": "rejected",
                                          "provider_error": {"kind": e.kind, "http_status": e.status, "message": e.message}}, "rejected")
        outcome = {"state": "rejected", "error": e.message or e.kind}
    except Exception as e:  # noqa: BLE001 — timeout/unclear: the call MAY have been placed; never retry
        kind = getattr(e, "kind", "unexpected_error")
        await _set_call(call_id, job_id, {"state": "pending_reconciliation",
                                          "provider_error": {"kind": kind, "http_status": getattr(e, "status", 0)}}, "pending_reconciliation")
        outcome = {"state": "pending_reconciliation", "error": kind}
    finally:
        await _release_lock(auth_id)
        del api_key
    await _audit(f"dispatch_{outcome['state']}", user, str(call_id), cid, outcome.get("error", ""))
    ensure_poller()
    return {"dispatched": True, "call_id": str(call_id), **outcome}


# ---------------- read-only reconciliation ----------------

def _digits(p) -> str:
    return re.sub(r"\D", "", str(p or ""))[-10:]


def _parse(ts: str):
    try:
        d = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
        return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


async def _lookup_execution(api_key: str, call: dict):
    """No execution ID: documented GET /v2/agent/{id}/executions in a narrow window; accept only a unique match."""
    sent = _parse(call["dispatched_at"])
    fmt = "%Y-%m-%dT%H:%M:%S.000Z"
    items = await bc.list_agent_executions(api_key, call["agent_id"], (sent - timedelta(minutes=2)).strftime(fmt),
                                           (datetime.now(timezone.utc) + timedelta(minutes=1)).strftime(fmt))
    want = _digits(call.get("recipient_e164"))
    hits = [x for x in items if isinstance(x, dict) and x.get("id")
            and _digits((x.get("telephony_data") or {}).get("to_number") or x.get("user_number")) == want
            and (_parse(x.get("created_at") or "") or sent) >= sent - timedelta(minutes=2)]
    return hits[0] if len(hits) == 1 else None


async def reconcile_call(call: dict) -> dict:
    try:
        api_key = decrypt_api_key(await _doc())
        if call.get("execution_id"):
            ex = await bc.get_execution(api_key, call["execution_id"])
        else:
            ex = await _lookup_execution(api_key, call)
    except Exception as e:  # noqa: BLE001
        ex, err = None, getattr(e, "kind", "lookup_failed")
    else:
        err = ""
    upd = {"last_reconciled_at": now_iso(), "reconcile_attempts": int(call.get("reconcile_attempts", 0)) + 1}
    if err:
        upd["last_reconcile_error"] = err
    if ex and ex.get("agent_id") == call.get("agent_id"):
        if not call.get("execution_id"):
            try:
                await db().ai_calls.update_one({"_id": call["_id"], "execution_id": {"$exists": False}},
                                               {"$set": {"execution_id": str(ex["id"]), "state": "accepted"}})
            except DuplicateKeyError:
                ex = None
        elif call.get("state") == "pending_reconciliation":
            upd["state"] = "accepted"
    await db().ai_calls.update_one({"_id": call["_id"]}, {"$set": upd})
    fresh = await db().ai_calls.find_one({"_id": call["_id"]})
    result = await apply_execution(fresh, ex, "reconcile") if ex and fresh.get("execution_id") == str(ex.get("id")) else {}
    fresh = await db().ai_calls.find_one({"_id": call["_id"]})
    created = _parse(fresh.get("dispatched_at") or fresh.get("created_at") or "")
    if fresh.get("state") in POLLED and created and datetime.now(timezone.utc) - created > REVIEW_AFTER:
        await db().ai_calls.update_one({"_id": call["_id"], "state": {"$in": POLLED}},
                                       {"$set": {"state": "needs_review", "needs_review_at": now_iso()}})
        if fresh.get("job_id") and ObjectId.is_valid(fresh["job_id"]):
            await db().ai_call_jobs.update_one({"_id": ObjectId(fresh["job_id"])}, {"$set": {"status": "needs_review"}})
    return {"result": result, "error": err}


async def reconcile_once() -> int:
    calls = await db().ai_calls.find({"mode": "testing", "state": {"$in": POLLED}}).to_list(20)
    for c in calls:
        await reconcile_call(c)
    return await db().ai_calls.count_documents({"mode": "testing", "state": {"$in": POLLED}})


async def _loop():
    while True:
        await asyncio.sleep(POLL_SECONDS)
        try:
            if not await reconcile_once():
                return
        except Exception:  # noqa: BLE001
            _logger.exception("[Reconcile] cycle failed")


def ensure_poller():
    t = _poller["task"]
    if not (t and not t.done()):
        _poller["task"] = asyncio.create_task(_loop())


async def startup_recover():
    """A crash mid-dispatch leaves the outcome unknown: treat as uncertain, never re-send."""
    await db().ai_calls.update_many({"state": "dispatching"}, {"$set": {"state": "pending_reconciliation",
                                                                      "provider_error": {"kind": "interrupted_dispatch"}}})
    await db().ai_call_settings.update_one({"_id": SETTINGS_ID}, {"$set": {"dispatch_lock": None}})
    if await db().ai_calls.count_documents({"state": {"$in": POLLED}}):
        ensure_poller()


# ---------------- admin endpoints ----------------

async def _call_or_404(call_id: str) -> dict:
    doc = await db().ai_calls.find_one({"_id": ObjectId(call_id)}) if ObjectId.is_valid(call_id) else None
    if not doc:
        raise HTTPException(404, "Not found")
    return doc


@dispatch_router.get("/test-calls/status")
async def calling_status(request: Request):
    await _auth(request)
    s = await db().ai_call_settings.find_one({"_id": SETTINGS_ID}) or {}
    blk = await db().ai_calls.find_one({"mode": "testing", "state": {"$in": BLOCKING}}, {"candidate_name": 1, "state": 1})
    return {"single_call_enabled": gate.SINGLE_TEST_CALL_APPROVED and gate.server_calling_enabled(),
            "mode": s.get("mode"), "emergency_stop": s.get("emergency_stop"), "live_mode_locked": gate.LIVE_MODE_LOCKED,
            "batch_calling_enabled": gate.BOLNA_INTEGRATION_APPROVED, "dispatch_in_progress": bool(s.get("dispatch_lock")),
            "blocking_call": {"id": str(blk["_id"]), "state": blk["state"], "candidate_name": blk.get("candidate_name")} if blk else None,
            "poll_seconds": POLL_SECONDS}


@dispatch_router.post("/test-calls/{call_id}/check")
async def check_now(call_id: str, request: Request):
    await _auth(request)
    _csrf(request)
    doc = await _call_or_404(call_id)
    if doc.get("state") in POLLED or (doc.get("state") == "finished" and doc.get("execution_id")):
        await reconcile_call(doc)
    return public_call(await _call_or_404(call_id))


@dispatch_router.post("/test-calls/{call_id}/resolve-review")
async def resolve_review(call_id: str, request: Request, body: dict = Body(...)):  # noqa: B008
    user = await _auth(request)
    _csrf(request)
    if body.get("confirmation") != "REVIEWED":
        raise HTTPException(400, "Type REVIEWED to confirm you checked this call in the Bolna dashboard")
    res = await db().ai_calls.update_one({"_id": (await _call_or_404(call_id))["_id"], "state": "needs_review"},
                                         {"$set": {"state": "reviewed", "reviewed_by": user, "reviewed_at": now_iso(),
                                                   "review_note": str(body.get("note") or "")[:500]}})
    if not res.modified_count:
        raise HTTPException(409, "Only calls in Needs Review can be marked reviewed")
    await _audit("review_resolved", user, call_id)
    return public_call(await _call_or_404(call_id))


@dispatch_router.get("/calls/{call_id}/recording")
async def recording(call_id: str, request: Request):
    await _auth(request)
    doc = await _call_or_404(call_id)
    url = doc.get("recording_url") or ""
    host = urlparse(url)
    if host.scheme != "https" or not host.hostname:
        raise HTTPException(404, "No recording for this call")
    headers = {"Range": request.headers["range"]} if request.headers.get("range") else {}
    if host.hostname == "api.bolna.ai":
        headers["Authorization"] = f"Bearer {decrypt_api_key(await _doc())}"
    client = httpx.AsyncClient(timeout=30, follow_redirects=True)
    try:
        r = await client.send(client.build_request("GET", url, headers=headers), stream=True)
    except httpx.HTTPError:
        await client.aclose()
        raise HTTPException(502, "Recording could not be retrieved from the provider") from None
    if r.status_code not in (200, 206):
        await r.aclose()
        await client.aclose()
        raise HTTPException(502, f"Recording unavailable from provider (HTTP {r.status_code})")
    out = {k: r.headers[k] for k in ("content-length", "content-range", "accept-ranges") if k in r.headers}
    out.update({"Cache-Control": "no-store, private", "X-Content-Type-Options": "nosniff"})

    async def stream():
        try:
            async for chunk in r.aiter_bytes():
                yield chunk
        finally:
            await r.aclose()
            await client.aclose()
    return StreamingResponse(stream(), status_code=r.status_code, headers=out,
                             media_type=r.headers.get("content-type", "audio/mpeg"))


TERMINAL_STATUSES = TERMINAL
