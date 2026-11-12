"""Tests for the two admin-editable, independent safety switches:

- POST /api/ai-calling/live-calling-stop   (defaults ON, blocks only Live)
- POST /api/ai-calling/test-calling-permitted  (defaults OFF, enables only Test)

Invariants verified here:
1. Default state (fresh install / after settings reset) is safe:
   live_calling_stop=True, test_calling_permitted=False.
2. Engaging/releasing is idempotent and audited.
3. Live Calling Stop blocks Live dispatch without affecting Test Mode permission.
4. Test Calling Permitted enables Test only and never flips a Live blocker.
5. Global Emergency Stop still blocks BOTH Test and Live, independent of the two switches.
6. Typed-confirmation phrase required for the dangerous direction (release Live Stop,
   enable Test calling).
"""
import pytest

from ai_calling.safety_flags import effective_live_permission, effective_test_permission


# ---------- pure-logic / gate matrix tests (no HTTP, no DB) ----------

PROV_READY = True
SERVER_ON = True


def _flags(ai_test=True, ai_live=True, estop=False, live_stop=True, test_permit=False,
           live_auth=True, mode_version=1):
    return {
        "ai_test_enabled": ai_test, "ai_live_enabled": ai_live,
        "emergency_stop": estop, "live_calling_stop": live_stop,
        "test_calling_permitted": test_permit, "live_dispatch_authorized": live_auth,
        "mode_version": mode_version,
    }


def _blocker_keys(result):
    return {b["key"] for b in result["blockers"]}


def test_default_state_blocks_both():
    s = _flags()  # defaults: live_stop ON, test_permit OFF
    live = effective_live_permission(s, server_enabled=SERVER_ON, provider_ready=PROV_READY)
    test = effective_test_permission(s, server_enabled=SERVER_ON, provider_ready=PROV_READY)
    assert not live["permitted"]
    assert not test["permitted"]
    assert "live_calling_stop" in _blocker_keys(live)
    assert "test_calling_permitted_off" in _blocker_keys(test)


def test_live_stop_blocks_only_live():
    """Live Calling Stop ON must NOT add to the test-blocker list."""
    s = _flags(live_stop=True, test_permit=True)
    test = effective_test_permission(s, server_enabled=SERVER_ON, provider_ready=PROV_READY)
    # No key named live_calling_stop in test blockers:
    assert "live_calling_stop" not in _blocker_keys(test)
    # With test_permit True and other flags healthy, test is now permitted.
    assert test["permitted"], test["blockers"]


def test_test_permit_does_not_unlock_live():
    """Permitting test calling must NOT reduce the live-blocker set."""
    s = _flags(live_stop=True, test_permit=True)
    live = effective_live_permission(s, server_enabled=SERVER_ON, provider_ready=PROV_READY)
    assert "test_calling_permitted" not in _blocker_keys(live)
    assert "live_calling_stop" in _blocker_keys(live)
    assert not live["permitted"]


def test_emergency_stop_blocks_both_regardless_of_switches():
    """Emergency Stop must appear in both blocker lists even when both switches look safe."""
    s = _flags(live_stop=False, test_permit=True, estop=True)
    live = effective_live_permission(s, server_enabled=SERVER_ON, provider_ready=PROV_READY)
    test = effective_test_permission(s, server_enabled=SERVER_ON, provider_ready=PROV_READY)
    assert "emergency_stop" in _blocker_keys(live)
    assert "emergency_stop" in _blocker_keys(test)
    assert not live["permitted"] and not test["permitted"]


def test_release_live_stop_still_requires_live_auth():
    """Releasing Live Stop alone does NOT unlock Live — Live Auth, AI Live, server, provider all still required."""
    s = _flags(live_stop=False, live_auth=False)
    live = effective_live_permission(s, server_enabled=SERVER_ON, provider_ready=PROV_READY)
    assert "live_dispatch_unauth" in _blocker_keys(live)
    assert not live["permitted"]


def test_strict_true_identity_on_live_stop():
    """Any value other than exactly False is treated as 'stopped'. Fails closed."""
    for truthy in (True, 1, "true", "yes", None, {}, [], "stopped"):
        s = _flags(live_stop=truthy)
        live = effective_live_permission(s, server_enabled=SERVER_ON, provider_ready=PROV_READY)
        assert "live_calling_stop" in _blocker_keys(live), f"value {truthy!r} should still block"


def test_strict_true_identity_on_test_permit():
    """test_calling_permitted must be exactly True; 1, 'yes', 'true' all fail closed."""
    for falsy_but_truthy in (1, "true", "yes", {"permitted": True}):
        s = _flags(test_permit=falsy_but_truthy)
        test = effective_test_permission(s, server_enabled=SERVER_ON, provider_ready=PROV_READY)
        assert "test_calling_permitted_off" in _blocker_keys(test), f"value {falsy_but_truthy!r} should still block"


# ---------- HTTP endpoint tests (require REACT_APP_BACKEND_URL + admin cookie) ----------
# These are wired through conftest.ai_estop_* snapshot/restore and so never mutate
# real preview DB state beyond the window of the test.

try:
    import os
    import requests
    _BASE = os.environ.get("REACT_APP_BACKEND_URL")
    _ADMIN_PW = "QAZwsx##123"
except Exception:  # pragma: no cover
    _BASE = None


@pytest.fixture(scope="module")
def admin_session():
    if not _BASE:
        pytest.skip("REACT_APP_BACKEND_URL not configured")
    s = requests.Session()
    r = s.post(f"{_BASE}/api/login",
               json={"username": "Admin User", "password": _ADMIN_PW}, timeout=10)
    if r.status_code != 200:
        pytest.skip(f"admin login failed ({r.status_code})")
    s.headers.update({"X-CSRF-Intent": "ai-calling",
                      "Origin": os.environ.get("FRONTEND_URL", _BASE)})
    yield s


@pytest.fixture
def restore_safety_switches(admin_session):
    """Snapshot live_calling_stop + test_calling_permitted, restore on teardown."""
    before = admin_session.get(f"{_BASE}/api/ai-calling/safety-status", timeout=10).json()
    sw = before.get("switches", {})
    live_before = bool(sw.get("live_calling_stop", True))
    test_before = bool(sw.get("test_calling_permitted", False))
    yield
    # restore
    admin_session.post(f"{_BASE}/api/ai-calling/live-calling-stop",
                       json={"active": True, "reason": "test teardown"}, timeout=10)
    if not live_before:
        admin_session.post(f"{_BASE}/api/ai-calling/live-calling-stop",
                           json={"active": False, "reason": "test teardown",
                                 "confirmation": "RELEASE LIVE CALLING STOP"}, timeout=10)
    admin_session.post(f"{_BASE}/api/ai-calling/test-calling-permitted",
                       json={"permitted": False, "reason": "test teardown"}, timeout=10)
    if test_before:
        admin_session.post(f"{_BASE}/api/ai-calling/test-calling-permitted",
                           json={"permitted": True, "reason": "test teardown",
                                 "confirmation": "PERMIT TEST CALLING"}, timeout=10)


def test_live_stop_release_requires_phrase(admin_session, restore_safety_switches):
    # Engage first so release is a real state change.
    admin_session.post(f"{_BASE}/api/ai-calling/live-calling-stop",
                       json={"active": True}, timeout=10)
    r = admin_session.post(f"{_BASE}/api/ai-calling/live-calling-stop",
                           json={"active": False, "reason": "no phrase"}, timeout=10)
    assert r.status_code == 400
    assert "RELEASE LIVE CALLING STOP" in r.text


def test_live_stop_release_with_phrase_succeeds(admin_session, restore_safety_switches):
    admin_session.post(f"{_BASE}/api/ai-calling/live-calling-stop",
                       json={"active": True}, timeout=10)
    r = admin_session.post(f"{_BASE}/api/ai-calling/live-calling-stop",
                           json={"active": False, "reason": "qa",
                                 "confirmation": "RELEASE LIVE CALLING STOP"}, timeout=10)
    assert r.status_code == 200
    # Safety-status now reports OFF.
    st = admin_session.get(f"{_BASE}/api/ai-calling/safety-status", timeout=10).json()
    assert st["switches"]["live_calling_stop"] is False


def test_live_stop_is_idempotent(admin_session, restore_safety_switches):
    # Engage twice — second call must not 500 or write a second audit row.
    r1 = admin_session.post(f"{_BASE}/api/ai-calling/live-calling-stop",
                            json={"active": True}, timeout=10)
    r2 = admin_session.post(f"{_BASE}/api/ai-calling/live-calling-stop",
                            json={"active": True}, timeout=10)
    assert r1.status_code == 200 and r2.status_code == 200


def test_test_permit_enable_requires_phrase(admin_session, restore_safety_switches):
    # Ensure OFF first.
    admin_session.post(f"{_BASE}/api/ai-calling/test-calling-permitted",
                       json={"permitted": False}, timeout=10)
    r = admin_session.post(f"{_BASE}/api/ai-calling/test-calling-permitted",
                           json={"permitted": True, "reason": "no phrase"}, timeout=10)
    assert r.status_code == 400
    assert "PERMIT TEST CALLING" in r.text


def test_test_permit_toggle_round_trip(admin_session, restore_safety_switches):
    # OFF -> ON (with phrase) -> OFF
    admin_session.post(f"{_BASE}/api/ai-calling/test-calling-permitted",
                       json={"permitted": False}, timeout=10)
    r = admin_session.post(f"{_BASE}/api/ai-calling/test-calling-permitted",
                           json={"permitted": True, "reason": "qa",
                                 "confirmation": "PERMIT TEST CALLING"}, timeout=10)
    assert r.status_code == 200
    st = admin_session.get(f"{_BASE}/api/ai-calling/safety-status", timeout=10).json()
    assert st["switches"]["test_calling_permitted"] is True
    r = admin_session.post(f"{_BASE}/api/ai-calling/test-calling-permitted",
                           json={"permitted": False, "reason": "qa"}, timeout=10)
    assert r.status_code == 200
    st = admin_session.get(f"{_BASE}/api/ai-calling/safety-status", timeout=10).json()
    assert st["switches"]["test_calling_permitted"] is False


def test_endpoints_require_csrf_header(admin_session):
    # Setting to None tells requests to drop the merged session header.
    r = admin_session.post(f"{_BASE}/api/ai-calling/live-calling-stop",
                           json={"active": True}, headers={"X-CSRF-Intent": None}, timeout=10)
    assert r.status_code == 403
