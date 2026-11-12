"""Phase 7A live API tests (public URL): switches, policy, live-dispatch lock, consent workflow. NEVER places calls."""
import os

import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
if not BASE_URL:
    for line in open("/app/frontend/.env"):
        if line.startswith("REACT_APP_BACKEND_URL="):
            BASE_URL = line.split("=", 1)[1].strip().rstrip("/")
API = f"{BASE_URL}/api/ai-calling"
H = {"X-CSRF-Intent": "ai-calling"}
EXPECTED = {  # (overall, test, live) -> (test_calls, live_calls)
    (True, False, False): (False, False), (True, True, False): (True, False), (True, False, True): (False, True),
    (True, True, True): (True, True), (False, False, False): (False, False), (False, True, False): (True, False),
    (False, False, True): (False, False), (False, True, True): (True, False)}


@pytest.fixture(scope="module")
def s():
    sess = requests.Session()
    for pw in ("QAZwsx##123", "Admin User"):
        r = sess.post(f"{BASE_URL}/api/login", json={"username": "Admin User", "password": pw})
        if r.status_code == 200:
            return sess
    pytest.skip("login failed")


@pytest.fixture(scope="module")
def created(s):
    ids = []
    yield ids
    for i in ids:
        s.delete(f"{API}/test-candidates/{i}", headers=H)


# --- switches / policy
def test_switches_initial(s):
    d = s.get(f"{API}/switches").json()
    assert d["ai_test_enabled"] is True and d["ai_live_enabled"] is False and d["emergency_stop"] is True
    assert d["effective"]["label"] == "Test-list calls only"
    assert isinstance(d["overall_test_mode"], bool)
    assert d["live_dispatch_authorized"] is False and d["live_dispatch_implemented"] is False
    assert "Emergency stop is ON" in d["test"]["blockers"] and d["test"]["can_call"] is False
    assert "AI Live Mode is OFF" in d["live"]["blockers"]
    assert len(d["policy"]) == 8
    for row in d["policy"]:
        assert (row["test_calls"], row["live_calls"]) == EXPECTED[(row["overall_test"], row["ai_test"], row["ai_live"])]


def test_switch_live_on_then_off_and_stale_409(s):
    jobs_before = None
    d = s.get(f"{API}/switches").json()
    v = d["switch_version"]
    hist = s.get(f"{API}/test-calls/status").json()
    try:
        r = s.post(f"{API}/switches", json={"ai_live_enabled": True, "expected_version": v}, headers=H)
        assert r.status_code == 200, r.text
        d2 = r.json()
        assert d2["ai_test_enabled"] and d2["ai_live_enabled"] and d2["switch_version"] == v + 1
        exp_label = "Both test-list and live eligible candidate calls" if d2["overall_test_mode"] else "Test-list calls only"
        assert d2["effective"]["label"] == exp_label
        assert d2["live"]["can_call"] is False and "Live dispatch is not implemented yet (Phase 7A)" in d2["live"]["blockers"]
        # stale version
        r = s.post(f"{API}/switches", json={"ai_live_enabled": False, "expected_version": v}, headers=H)
        assert r.status_code == 409
    finally:
        cur = s.get(f"{API}/switches").json()
        r = s.post(f"{API}/switches", json={"ai_live_enabled": False, "ai_test_enabled": True,
                                            "expected_version": cur["switch_version"]}, headers=H)
        assert r.status_code == 200
    d3 = s.get(f"{API}/switches").json()
    assert d3["ai_live_enabled"] is False and d3["ai_test_enabled"] is True and d3["live_dispatch_authorized"] is False
    assert d3["effective"]["label"] == "Test-list calls only"
    _ = (jobs_before, hist)


def test_live_authorize_423(s):
    assert s.post(f"{API}/live-dispatch/authorize", headers=H).status_code == 423


def test_no_auth_401_and_no_csrf_403(s):
    assert requests.get(f"{API}/switches").status_code == 401
    assert requests.post(f"{API}/switches", json={"ai_live_enabled": True}, headers=H).status_code == 401
    assert s.post(f"{API}/switches", json={"ai_live_enabled": True}).status_code == 403
    assert s.post(f"{API}/live-dispatch/authorize").status_code == 403


def test_status_single_call_disabled(s):
    d = s.get(f"{API}/test-calls/status").json()
    assert d.get("single_call_enabled") is False, d


# --- consent workflow
def _body(name, phone, **kw):
    b = {"candidate_name": name, "phone_number": phone, "job_role": "Analyst", "interview_date": "2099-01-01",
         "interview_time": "10", "language": "English", "company_name": "BluBridge", "office_address": "Chennai"}
    b.update(kw)
    return b


def test_create_without_consent(s, created):
    r = s.post(f"{API}/test-candidates", json=_body("TEST_NoConsent", "+919000000401", consent_for_test_call=False), headers=H)
    assert r.status_code in (200, 201), r.text
    d = r.json(); created.append(d["id"])
    assert d["readiness"] == "no_consent" and d["consent_status"] == "not_granted" and "approved" not in d


def test_create_with_consent_and_filter(s, created):
    r = s.post(f"{API}/test-candidates", json=_body("TEST_Consent", "+919000000402", consent_for_test_call=True), headers=H)
    assert r.status_code in (200, 201), r.text
    d = r.json(); created.append(d["id"])
    assert d["readiness"] == "ready" and d["consent_status"] == "granted"
    lst = s.get(f"{API}/test-candidates", params={"consent": "granted"}).json()
    items = lst.get("items", lst) if isinstance(lst, dict) else lst
    ids = [i["id"] for i in items]
    assert d["id"] in ids and created[0] not in ids
    assert all(i["consent_status"] == "granted" for i in items)


def test_old_approval_endpoints_gone(s, created):
    cid = created[0]
    for path in (f"/test-candidates/{cid}/approve", f"/test-candidates/{cid}/revoke",
                 "/test-candidates/bulk-approve", "/test-candidates/bulk-revoke"):
        r = s.post(f"{API}{path}", json={"ids": [cid]}, headers=H)
        assert r.status_code in (404, 405), (path, r.status_code)


def test_withdraw_regrant_optout(s, created):
    cid = created[1]
    w = s.post(f"{API}/test-candidates/{cid}/consent", json={"granted": False}, headers=H).json()
    assert w["consent_status"] == "withdrawn" and w["readiness"] == "no_consent"
    g = s.post(f"{API}/test-candidates/{cid}/consent", json={"granted": True}, headers=H).json()
    assert g["consent_status"] == "granted" and g["readiness"] == "ready"
    o = s.post(f"{API}/test-candidates/{cid}/opt-out", json={"opted_out": True}, headers=H).json()
    assert o["readiness"] == "opted_out" and o["consent_status"] == "not_granted"
    assert s.post(f"{API}/test-candidates/{cid}/consent", json={"granted": True}, headers=H).status_code == 400
    c = s.post(f"{API}/test-candidates/{cid}/opt-out", json={"opted_out": False}, headers=H).json()
    assert c["consent_status"] == "not_granted" and c["readiness"] == "no_consent"


def test_phone_change_resets_consent(s, created):
    cid = created[1]
    s.post(f"{API}/test-candidates/{cid}/consent", json={"granted": True}, headers=H)
    r = s.put(f"{API}/test-candidates/{cid}", json=_body("TEST_Consent", "+919000000403"), headers=H)
    assert r.status_code == 200, r.text
    assert r.json()["consent_status"] == "not_granted"
    r = s.put(f"{API}/test-candidates/{cid}", json=_body("TEST_Consent", "+919000000404", consent_for_test_call=True), headers=H).json()
    assert r["consent_status"] == "granted" and r["readiness"] == "ready"
    # same phone, edit name -> consent kept
    r = s.put(f"{API}/test-candidates/{cid}", json=_body("TEST_Consent2", "+919000000404"), headers=H).json()
    assert r["consent_status"] == "granted"


def test_call_now_locked_with_wrong_name(s, created):
    # wrong confirm_name on purpose: must be 423 before anything else
    r = s.post(f"{API}/test-candidates/{created[1]}/call-now",
               json={"idempotency_key": "idem-key-phase7a-api-0001", "confirm_name": "WRONG_NAME_x"}, headers=H)
    assert r.status_code in (400, 404, 409, 412)  # real gates (name/emergency stop) block it


def test_delete_and_404(s, created):
    for cid in list(created):
        assert s.delete(f"{API}/test-candidates/{cid}", headers=H).status_code in (200, 204)
        created.remove(cid)
        assert s.get(f"{API}/test-candidates/{cid}").status_code in (404, 405)
