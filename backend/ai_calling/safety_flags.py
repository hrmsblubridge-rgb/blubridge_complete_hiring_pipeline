"""Safety-flag helpers extracted so every caller computes permissions identically (B4).

Design invariants (never relaxed):
  - Each gate is independent. Flipping one gate must NOT unlock another.
  - `test_calling_permitted` enables Test-Mode real outbound only. It has zero effect on Live.
  - Emergency Stop and server flag (AI_CALLING_ENABLED) ALWAYS override.
"""
from typing import Dict, List

TEST_CALLING_PERMITTED_FIELD = "test_calling_permitted"


def effective_test_permission(settings: dict, *, server_enabled: bool, provider_ready: bool) -> Dict:
    blockers: List[dict] = []
    if settings.get("emergency_stop", True):
        blockers.append({"key": "emergency_stop", "reason": "Emergency Stop is ON"})
    if not server_enabled:
        blockers.append({"key": "server_disabled", "reason": "Server outbound calling is disabled"})
    if not settings.get("ai_test_enabled", False):
        blockers.append({"key": "ai_test_off", "reason": "AI Test Mode is OFF"})
    if not settings.get(TEST_CALLING_PERMITTED_FIELD, False):
        blockers.append({"key": "test_calling_permitted_off",
                         "reason": "Test-only real calling is not permitted (server-enforced flag, defaults OFF)"})
    if not provider_ready:
        blockers.append({"key": "provider_unverified", "reason": "Bolna provider is not verified"})
    return {"permitted": not blockers, "blockers": blockers}


def effective_live_permission(settings: dict, *, server_enabled: bool, provider_ready: bool) -> Dict:
    from .modes import LIVE_DISPATCH_IMPLEMENTED
    blockers: List[dict] = []
    if settings.get("emergency_stop", True):
        blockers.append({"key": "emergency_stop", "reason": "Emergency Stop is ON"})
    if not server_enabled:
        blockers.append({"key": "server_disabled", "reason": "Server outbound calling is disabled"})
    if not settings.get("ai_live_enabled", False):
        blockers.append({"key": "ai_live_off", "reason": "AI Live Mode is OFF"})
    if not settings.get("live_dispatch_authorized", False):
        blockers.append({"key": "live_dispatch_unauth", "reason": "Live Dispatch Authorization is OFF"})
    if not provider_ready:
        blockers.append({"key": "provider_unverified", "reason": "Bolna provider is not verified"})
    if not LIVE_DISPATCH_IMPLEMENTED:
        blockers.append({"key": "code_locked", "reason": "Live dispatch not yet implemented in code"})
    return {"permitted": not blockers, "blockers": blockers}
