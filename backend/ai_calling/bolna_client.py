"""Bolna AI HTTP client. Read-only calls only in Phase 4A; place_call stays disabled.

Verified against official docs (Nov 2026):
  base https://api.bolna.ai, header "Authorization: Bearer <api_key>"
  GET  /v2/agent/{agent_id}          docs/api-reference/agent/v2/get
  GET  /phone-numbers/all            docs/api-reference/phone-numbers/get_all
  GET  /executions/{execution_id}    docs/api-reference/executions/get_execution
  POST /call {agent_id, recipient_phone_number, from_phone_number?, user_data?}
                                     docs/api-reference/calls/make  (NOT sent in 4A)
The key/headers are never logged or returned.
"""
import httpx

BASE_URL = "https://api.bolna.ai"
TIMEOUT = 15.0


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


async def place_call(*, gate_result: dict, **_):
    if not gate_result or not gate_result.get("allowed"):
        raise PermissionError("Permission gate denied this call")
    raise BolnaCallingDisabled("Outbound Bolna calls are disabled until Phase 4B approval")
