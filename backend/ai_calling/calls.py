"""Phase 4A: dry-run call preparation + webhook receiver. NEVER sends POST /call."""
import hashlib
import hmac
import json
import logging
import re

from bson import ObjectId
from fastapi import APIRouter, HTTPException, Request
from pymongo.errors import DuplicateKeyError

from . import bolna_client as bc
from . import gate
from .execution import TERMINAL, normalize_execution, rank, user_data_for
from .provider import _auth, _csrf, _doc, decrypt_api_key, provider_ready
from .store import db, get_settings, mask_phone, now_iso

_logger = logging.getLogger("ai_calling.calls")
calls_router = APIRouter()
BOLNA_IPS = {"13.203.39.153", "13.126.9.249", "13.202.133.53"}
_TOKEN_PATH = re.compile(r"(/webhook/bolna/)[^\s/?\"]+")


class _RedactWebhookToken(logging.Filter):
    """Keep the secret webhook route token out of uvicorn access logs."""
    def filter(self, record):
        if isinstance(record.args, tuple):
            record.args = tuple(_TOKEN_PATH.sub(r"\1[redacted]", a) if isinstance(a, str) else a for a in record.args)
        return True


logging.getLogger("uvicorn.access").addFilter(_RedactWebhookToken())


@calls_router.post("/test-candidates/{cid}/dry-run")
async def dry_run(cid: str, request: Request):
    user = await _auth(request)
    _csrf(request)
    cand = await db().ai_test_candidates.find_one({"_id": ObjectId(cid), "mode": "testing"}) if ObjectId.is_valid(cid) else None
    if not cand:
        raise HTTPException(404, "Test candidate not found")
    s = await get_settings()
    prov = await _doc()
    checks = [
        {"key": "testing_mode", "ok": s["mode"] == "testing", "label": "Testing Mode is active"},
        {"key": "approved", "ok": cand.get("approved") is True and cand.get("approved_phone") == cand.get("phone_e164"), "label": "Recipient approved for this exact number"},
        {"key": "consent", "ok": cand.get("consent_confirmed") is True, "label": "Recipient consent confirmed"},
        {"key": "not_opted_out", "ok": not cand.get("opted_out"), "label": "Recipient has not opted out"},
        {"key": "provider_validated", "ok": provider_ready(prov), "label": "Bolna configuration verified (Test Connection)"},
        {"key": "emergency_stop", "ok": not s["emergency_stop"], "label": "Emergency stop inactive", "informational": True},
        {"key": "server_enabled", "ok": gate.server_calling_enabled(), "label": "Server-side calling enabled", "informational": True},
        {"key": "bolna_approved", "ok": gate.BOLNA_INTEGRATION_APPROVED, "label": "Real calls approved (Phase 4B)", "informational": True},
    ]
    blocking = [c for c in checks if not c["ok"] and not c.get("informational")]
    if blocking:
        return {"prepared": False, "would_send": False, "checks": checks}
    body = bc.build_call_request(agent_id=prov["agent_id"], recipient=cand["phone_e164"],
                                 from_number=prov["caller_number"], user_data=user_data_for(cand))
    preview = {**body, "recipient_phone_number": mask_phone(body["recipient_phone_number"]),
               "from_phone_number": mask_phone(body.get("from_phone_number", ""))}
    await db().ai_dry_runs.insert_one({"test_candidate_id": cid, "by": user, "at": now_iso(),
                                       "agent_id": prov["agent_id"], "user_data": body["user_data"]})
    _logger.info(f"[DryRun] prepared for candidate={cid} by={user} (not sent)")
    return {"prepared": True, "would_send": False, "method": "POST", "url": f"{bc.BASE_URL}/call",
            "headers": {"Authorization": "Bearer ••••••••", "Content-Type": "application/json"},
            "body": preview, "checks": checks}


# ---------------- webhook ----------------

async def _record_event(execution_id: str, status: str, payload: dict, ip: str, matched: bool):
    """Return event _id if new, None if this exact event was already processed."""
    h = hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()
    try:
        res = await db().ai_webhook_events.insert_one({"execution_id": execution_id, "status": status, "payload_hash": h,
                                                       "source_ip": ip, "ip_allowlisted": ip in BOLNA_IPS,
                                                       "matched": matched, "received_at": now_iso()})
        return res.inserted_id
    except DuplicateKeyError:
        return None


async def apply_execution(call: dict, ex: dict, source: str):
    """Persist an AUTHORITATIVE execution (re-fetched from Bolna). Ignores out-of-order regressions."""
    n = normalize_execution(ex)
    cur = call.get("status", "")
    if rank(n["status"]) < rank(cur) or (cur in TERMINAL and n["status"] != cur):
        return {"ignored": "out_of_order"}
    upd = {"status": n["status"], "updated_at": now_iso(), "last_source": source}
    if n["terminal"]:
        upd.update({k: n[k] for k in ("duration_seconds", "hangup_reason", "recording_url", "transcript",
                                       "extracted_data_raw", "error_message")})
        upd["response"] = n["response"]
        upd["completed_at"] = now_iso()
    await db().ai_calls.update_one({"_id": call["_id"]}, {"$set": upd})
    return {"applied": n["status"]}


@calls_router.post("/webhook/bolna/{token}")
async def bolna_webhook(token: str, request: Request):
    prov = await _doc()
    expected = prov.get("webhook_token_hash") or ""
    if not expected or not hmac.compare_digest(hashlib.sha256(token.encode()).hexdigest(), expected):
        raise HTTPException(404, "Not found")
    ip = (request.headers.get("x-forwarded-for") or (request.client.host if request.client else "")).split(",")[0].strip()
    try:
        payload = await request.json()
    except ValueError:
        raise HTTPException(400, "Invalid JSON") from None
    if not isinstance(payload, dict):
        raise HTTPException(400, "Invalid JSON")
    ex_id = str(payload.get("id") or payload.get("execution_id") or "")
    status = str(payload.get("status") or "")
    call = await db().ai_calls.find_one({"execution_id": ex_id}) if ex_id else None
    fresh = await _record_event(ex_id, status, payload, ip, bool(call))
    if not call:
        _logger.warning(f"[Webhook] unmatched execution ignored status={status}")
        return {"received": True, "matched": False}
    if not fresh:
        return {"received": True, "duplicate": True}
    # Never trust the webhook body: re-fetch the execution from Bolna before applying.
    try:
        api_key = decrypt_api_key(prov)
        ex = await bc.get_execution(api_key, ex_id)
    except Exception:  # noqa: BLE001 — any re-fetch failure: release the event so Bolna's retry is processed
        await db().ai_webhook_events.delete_one({"_id": fresh})
        await db().ai_calls.update_one({"_id": call["_id"]}, {"$set": {"needs_refetch": True}})
        return {"received": True, "matched": True, "refetch": "failed"}
    if str(ex.get("id") or "") != ex_id or ex.get("agent_id") != call.get("agent_id"):
        await db().ai_calls.update_one({"_id": call["_id"]}, {"$set": {"execution_mismatch": True, "mismatch_at": now_iso()}})
        return {"received": True, "matched": True, "rejected": "execution mismatch"}
    await db().ai_calls.update_one({"_id": call["_id"]}, {"$set": {"needs_refetch": False}})
    return {"received": True, "matched": True, **(await apply_execution(call, ex, "refetch"))}
