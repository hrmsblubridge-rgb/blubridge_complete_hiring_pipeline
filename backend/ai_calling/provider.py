"""Bolna provider configuration (Phase 3.1). Admin-only, encrypted credential storage.

- API key is encrypted with Fernet (AES-128-CBC + HMAC-SHA256) before it reaches MongoDB.
- Master key comes ONLY from the backend env secret AI_PROVIDER_ENCRYPTION_KEY
  (a Fernet key, or a random passphrase of >= 32 chars that is HKDF-derived).
- The decrypted key is never returned by any endpoint and never logged.
"""
import base64
import hashlib
import logging
import os
import re

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from fastapi import APIRouter, Body, HTTPException, Request

from .store import _state, db, now_iso

_logger = logging.getLogger("ai_calling.provider")
provider_router = APIRouter(prefix="/provider")
DOC_ID = "bolna"
ENC_ENV = "AI_PROVIDER_ENCRYPTION_KEY"
CSRF_HEADER = "X-CSRF-Intent"
CSRF_VALUE = "ai-calling"


# ---------------- crypto ----------------

def _fernet():
    raw = os.environ.get(ENC_ENV, "").strip()
    if not raw:
        return None
    try:
        return Fernet(raw.encode())
    except (ValueError, TypeError):
        if len(raw) < 32:
            return None
        derived = HKDF(algorithm=hashes.SHA256(), length=32, salt=b"blubridge-ai-provider-v1", info=b"fernet").derive(raw.encode())
        return Fernet(base64.urlsafe_b64encode(derived))


def _key_id() -> str:
    """Non-reversible fingerprint of the master key, to detect key rotation/mismatch."""
    raw = os.environ.get(ENC_ENV, "").strip()
    return hashlib.sha256(("kid:" + raw).encode()).hexdigest()[:12] if raw else ""


def encryption_status() -> dict:
    raw = os.environ.get(ENC_ENV, "").strip()
    if not raw:
        return {"ready": False, "reason": f"{ENC_ENV} is not configured in backend secrets"}
    if _fernet() is None:
        return {"ready": False, "reason": f"{ENC_ENV} must be a Fernet key or a random passphrase of at least 32 characters"}
    return {"ready": True, "reason": ""}


def decrypt_api_key(doc: dict) -> str:
    """Server-side use only (Phase 4 client). Never return this from an endpoint."""
    f = _fernet()
    if not f or not doc.get("api_key_encrypted"):
        raise RuntimeError("Provider API key unavailable")
    return f.decrypt(doc["api_key_encrypted"].encode()).decode()


# ---------------- helpers ----------------

async def _auth(request: Request) -> str:
    return await _state["auth"](request)


def _csrf(request: Request):
    """Mutations need the custom header (not settable cross-site without a CORS preflight,
    which only FRONTEND_URL passes) and, when present, a matching Origin."""
    if request.headers.get(CSRF_HEADER) != CSRF_VALUE:
        raise HTTPException(403, "Missing CSRF protection header")
    origin = (request.headers.get("origin") or "").rstrip("/")
    allowed = os.environ.get("FRONTEND_URL", "").rstrip("/")
    if origin and origin != allowed:
        raise HTTPException(403, "Cross-origin configuration change rejected")


def _mask(v: str, keep: int = 4) -> str:
    return ("•" * 8 + v[-keep:]) if v and len(v) > keep else ("•" * 4 if v else "")


def _norm_caller(raw: str) -> str:
    s = re.sub(r"[\s\-()]", "", raw or "")
    if re.fullmatch(r"0?[6-9]\d{9}", s):
        s = "+91" + s[-10:]
    elif re.fullmatch(r"91[6-9]\d{9}", s):
        s = "+" + s
    if not re.fullmatch(r"\+[1-9]\d{7,14}", s):
        raise HTTPException(400, "Calling number must be in international format, e.g. +918012345678")
    return s


def _norm_agent(raw: str) -> str:
    s = (raw or "").strip()
    if not re.fullmatch(r"[A-Za-z0-9_\-]{6,100}", s):
        raise HTTPException(400, "Agent ID must be 6–100 characters (letters, digits, - or _)")
    return s


async def _doc() -> dict:
    return await db().ai_provider_settings.find_one({"_id": DOC_ID}) or {}


async def _audit(request: Request, user: str, action: str, fields: list, version: int):
    await db().ai_provider_audit.insert_one({
        "provider": DOC_ID, "action": action, "fields_changed": fields, "config_version": version,
        "by": user, "at": now_iso(), "ip": request.client.host if request.client else "",
    })
    _logger.info(f"[ProviderConfig] {action} fields={fields} by={user} v{version}")


async def _apply(request: Request, user: str, action: str, fields: list, set_fields: dict, unset: dict = None):
    """Persist a config change, bump version, mark unverified, pause pending jobs."""
    op = {"$set": {**set_fields, "provider": DOC_ID, "status": "configured_unverified",
                   "updated_by": user, "updated_at": now_iso()},
          "$inc": {"config_version": 1}}
    if unset:
        op["$unset"] = unset
    await db().ai_provider_settings.update_one({"_id": DOC_ID}, op, upsert=True)
    paused = await db().ai_call_jobs.update_many(
        {"status": "pending"}, {"$set": {"status": "paused_config_changed", "paused_at": now_iso()}})
    doc = await _doc()
    await _audit(request, user, action, fields, doc.get("config_version", 0))
    return paused.modified_count


def provider_ready(doc: dict) -> bool:
    """Used by the permission gate: configured AND verified (verification arrives in Phase 4)."""
    return bool(doc.get("api_key_encrypted") and doc.get("agent_id") and doc.get("caller_number")
                and doc.get("status") == "verified" and doc.get("key_id") == _key_id())


# ---------------- endpoints ----------------

@provider_router.get("")
async def get_provider(request: Request):
    """Masked status only. Never returns the API key or its ciphertext."""
    await _auth(request)
    d = await _doc()
    enc = encryption_status()
    readable = None
    if d.get("api_key_encrypted") and enc["ready"]:
        try:
            decrypt_api_key(d)
            readable = True
        except (InvalidToken, RuntimeError):
            readable = False
    has_all = bool(d.get("api_key_encrypted") and d.get("agent_id") and d.get("caller_number"))
    has_any = bool(d.get("api_key_encrypted") or d.get("agent_id") or d.get("caller_number"))
    if not has_any:
        status = "not_configured"
    elif readable is False or (d.get("api_key_encrypted") and d.get("key_id") != _key_id()):
        status = "key_unreadable"
    elif not has_all:
        status = "incomplete"
    else:
        status = d.get("status", "configured_unverified")
    return {
        "provider": "bolna", "status": status, "encryption": enc,
        "has_api_key": bool(d.get("api_key_encrypted")), "api_key_masked": ("•" * 8 + d["api_key_last4"]) if d.get("api_key_last4") else "",
        "agent_id": d.get("agent_id", ""), "agent_id_masked": _mask(d.get("agent_id", ""), 6),
        "caller_number_masked": _mask(d.get("caller_number", ""), 4),
        "config_version": d.get("config_version", 0), "updated_by": d.get("updated_by"), "updated_at": d.get("updated_at"),
        "test_connection_enabled": False,
    }


@provider_router.put("/credentials")
async def save_credentials(request: Request, body: dict = Body(...)):  # noqa: B008 — dict avoids echoing the key in 422 errors
    user = await _auth(request)
    _csrf(request)
    enc = encryption_status()
    if not enc["ready"]:
        raise HTTPException(503, f"Cannot store credentials: {enc['reason']}")
    key = body.get("api_key")
    if not isinstance(key, str) or not re.fullmatch(r"\S{16,512}", key.strip()):
        raise HTTPException(400, "API key must be 16–512 characters without spaces")
    key = key.strip()
    token = _fernet().encrypt(key.encode()).decode()
    paused = await _apply(request, user, "api_key_replaced", ["api_key"],
                          {"api_key_encrypted": token, "api_key_last4": key[-4:], "key_id": _key_id(), "api_key_set_at": now_iso()})
    del key, token
    return {"saved": True, "paused_jobs": paused, **(await get_provider(request))}


@provider_router.put("/settings")
async def save_settings(request: Request, body: dict = Body(...)):  # noqa: B008
    user = await _auth(request)
    _csrf(request)
    cur = await _doc()
    upd, fields = {}, []
    if body.get("agent_id") not in (None, ""):
        upd["agent_id"] = _norm_agent(str(body["agent_id"]))
    if body.get("caller_number") not in (None, ""):
        upd["caller_number"] = _norm_caller(str(body["caller_number"]))
    fields = [k for k, v in upd.items() if cur.get(k) != v]
    if not fields:
        raise HTTPException(400, "No changes to save")
    paused = await _apply(request, user, "settings_updated", fields, {k: upd[k] for k in fields})
    return {"saved": True, "paused_jobs": paused, **(await get_provider(request))}


@provider_router.post("/clear")
async def clear_provider(request: Request, body: dict = Body(...)):  # noqa: B008
    user = await _auth(request)
    _csrf(request)
    if body.get("confirmation") != "CLEAR":
        raise HTTPException(400, "Type CLEAR to confirm")
    await _apply(request, user, "configuration_cleared", ["api_key", "agent_id", "caller_number"],
                 {"status": "not_configured"},
                 {"api_key_encrypted": "", "api_key_last4": "", "key_id": "", "agent_id": "", "caller_number": "", "api_key_set_at": ""})
    await db().ai_provider_settings.update_one({"_id": DOC_ID}, {"$set": {"status": "not_configured"}})
    return {"cleared": True, **(await get_provider(request))}


@provider_router.get("/audit")
async def provider_audit(request: Request):
    await _auth(request)
    docs = await db().ai_provider_audit.find({"provider": DOC_ID}, {"_id": 0}).sort("at", -1).to_list(100)
    return {"items": docs}


@provider_router.post("/test-connection")
async def test_connection(request: Request):
    await _auth(request)
    _csrf(request)
    raise HTTPException(423, "Test Connection will be enabled in Phase 4 (Bolna API integration)")
