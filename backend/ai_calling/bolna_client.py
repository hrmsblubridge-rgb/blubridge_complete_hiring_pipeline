"""Bolna AI HTTP client. Phase 4B: place_call sends ONE POST /call only after the single-call gate passes.

Verified against official docs (Nov 2026):
  base https://api.bolna.ai, header "Authorization: Bearer <api_key>"
  GET  /v2/agent/{agent_id}          docs/api-reference/agent/v2/get
  GET  /phone-numbers/all            docs/api-reference/phone-numbers/get_all
  GET  /executions/{execution_id}    docs/api-reference/executions/get_execution
  POST /call {agent_id, recipient_phone_number, from_phone_number?, user_data?}
                                     docs/api-reference/calls/make  (NOT sent in 4A)
The key/headers are never logged or returned.
"""
import re
from urllib.parse import urlencode

import httpx

BASE_URL = "https://api.bolna.ai"
TIMEOUT = 15.0
CALL_TIMEOUT = 25.0


class BolnaCallingDisabled(RuntimeError):
    pass


class BolnaError(Exception):
    def __init__(self, kind: str, status: int = 0):
        super().__init__(kind)
        self.kind, self.status = kind, status


async def _get(api_key: str, path: str):
    try:
        async with httpx.AsyncClient(base_url=BASE_URL, timeout=TIMEOUT) as c:
            r = await c.get(path, headers={"Authorization": f"Bearer {api_key}", "Accept": "application/json"})
    except httpx.HTTPError:
        raise BolnaError("network_error") from None
    if r.status_code in (401, 403):
        raise BolnaError("invalid_credentials", r.status_code)
    if r.status_code == 404:
        raise BolnaError("not_found", 404)
    if r.status_code == 429:
        raise BolnaError("rate_limited", 429)
    if r.status_code >= 400:
        raise BolnaError("provider_error", r.status_code)
    try:
        return r.json()
    except ValueError:
        raise BolnaError("invalid_response", r.status_code) from None


async def get_agent(api_key: str, agent_id: str) -> dict:
    return await _get(api_key, f"/v2/agent/{agent_id}")


async def list_phone_numbers(api_key: str) -> list:
    data = await _get(api_key, "/phone-numbers/all")
    return data if isinstance(data, list) else data.get("data", []) if isinstance(data, dict) else []


async def get_execution(api_key: str, execution_id: str) -> dict:
    return await _get(api_key, f"/executions/{execution_id}")


async def get_disposition(api_key: str, disposition_id: str, agent_id: str) -> dict:
    """GET /dispositions/{id}?agent_id= (docs/api-reference/dispositions/get). Extraction field definition."""
    return await _get(api_key, f"/dispositions/{disposition_id}?agent_id={agent_id}")


def build_call_request(*, agent_id: str, recipient: str, from_number: str, user_data: dict) -> dict:
    """Documented POST /call body. Only documented fields are used."""
    body = {"agent_id": agent_id, "recipient_phone_number": recipient, "user_data": user_data}
    if from_number:
        body["from_phone_number"] = from_number
    return body


class BolnaRejected(Exception):
    """Provider definitively refused the request (4xx): the call was not placed."""
    def __init__(self, kind: str, status: int, message: str = ""):
        super().__init__(kind)
        self.kind, self.status, self.message = kind, status, message


class DispatchUncertain(Exception):
    """Timeout / 5xx / unclear response: the call MAY have been placed. Reconcile, never retry."""
    def __init__(self, kind: str, status: int = 0):
        super().__init__(kind)
        self.kind, self.status = kind, status


def sanitize(text) -> str:
    """Mask phone-like digit runs and cap length before storing provider messages."""
    s = re.sub(r"\+?\d{6,}", lambda m: "•••" + m.group(0)[-4:], str(text or ""))
    return s[:300]


async def list_agent_executions(api_key: str, agent_id: str, frm: str, to: str) -> list:
    """GET /v2/agent/{agent_id}/executions (docs/api-reference/executions/get_executions). Read-only."""
    q = urlencode({"from": frm, "to": to, "page_number": 1, "page_size": 50, "call_type": "outbound"})
    data = await _get(api_key, f"/v2/agent/{agent_id}/executions?{q}")
    return data if isinstance(data, list) else (data.get("data") or []) if isinstance(data, dict) else []


async def place_call(*, gate_result: dict, api_key: str, body: dict) -> dict:
    """Documented POST /call. Sends exactly ONE request; never retries."""
    if not gate_result or not gate_result.get("allowed"):
        raise PermissionError("Permission gate denied this call")
    try:
        async with httpx.AsyncClient(base_url=BASE_URL, timeout=CALL_TIMEOUT) as c:
            r = await c.post("/call", json=body, headers={"Authorization": f"Bearer {api_key}", "Accept": "application/json"})
    except httpx.HTTPError:
        raise DispatchUncertain("network_or_timeout") from None
    if r.status_code >= 500 or r.status_code == 408:
        raise DispatchUncertain("provider_unavailable", r.status_code)
    try:
        data = r.json()
    except ValueError:
        data = None
    if r.status_code >= 400:
        msg = (data.get("message") or data.get("detail") or data.get("error")) if isinstance(data, dict) else r.text
        kind = {401: "invalid_credentials", 403: "forbidden", 404: "not_found", 429: "rate_limited"}.get(r.status_code, "rejected")
        raise BolnaRejected(kind, r.status_code, sanitize(msg))
    ex_id = data.get("execution_id") if isinstance(data, dict) else None
    if not ex_id:
        raise DispatchUncertain("no_execution_id", r.status_code)
    return {"execution_id": str(ex_id), "status": str(data.get("status") or "queued")}
