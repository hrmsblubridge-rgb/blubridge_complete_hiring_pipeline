"""Bolna AI client interface (Phase 2: NO network calls).

To be verified against official Bolna docs before Phase 3 (do not assume):
  - outbound call endpoint/path and auth header format
  - request fields: agent_id, recipient_phone_number, from_phone_number, user_data keys
  - execution id field name in the response
  - execution status values incl. no-answer / busy representation
  - webhook authentication (signature/IP allowlist) and payload fields
    (transcript, recording reference, extracted_data format)
"""
import os

CONFIG_KEYS = ["BOLNA_API_KEY", "BOLNA_AGENT_ID", "BOLNA_FROM_NUMBER", "BOLNA_WEBHOOK_TOKEN"]


class BolnaCallingDisabled(RuntimeError):
    pass


def config_status() -> dict:
    """Which keys are present (booleans only; values never leave the server)."""
    return {k: bool(os.environ.get(k)) for k in CONFIG_KEYS}


async def place_call(*, gate_result: dict, phone_e164: str, user_data: dict) -> dict:
    if not gate_result or not gate_result.get("allowed"):
        raise PermissionError("Permission gate denied this call")
    raise BolnaCallingDisabled("Outbound Bolna calls are not implemented in Phase 2")
