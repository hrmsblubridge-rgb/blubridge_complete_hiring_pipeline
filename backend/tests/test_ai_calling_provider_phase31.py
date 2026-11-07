# Phase 3.1 — Bolna provider configuration (encrypted, write-only key, CSRF, audit) tests. DUMMY keys only.
import os

import pytest
import requests

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL').rstrip('/')
API = f"{BASE_URL}/api/ai-calling/provider"
H = {"X-CSRF-Intent": "ai-calling", "Origin": BASE_URL}
KEY = "dummyKey_NOT_REAL_PYTEST_ZZ9876"


@pytest.fixture(scope="module")
def s():
    sess = requests.Session()
    r = sess.post(f"{BASE_URL}/api/login", json={"username": "Admin User", "password": "QAZwsx##123"})
    if r.status_code != 200:
        pytest.skip("login failed")
    return sess


# --- auth ---
def test_unauthenticated_401():
    assert requests.get(API).status_code == 401
    assert requests.put(f"{API}/credentials", json={"api_key": KEY}, headers=H).status_code == 401


# --- CSRF ---
def test_put_without_csrf_403(s):
    r = s.put(f"{API}/credentials", json={"api_key": KEY})
    assert r.status_code == 403


def test_put_evil_origin_403(s):
    r = s.put(f"{API}/credentials", json={"api_key": KEY},
              headers={"X-CSRF-Intent": "ai-calling", "Origin": "https://evil.example"})
    assert r.status_code == 403


def test_short_key_400_no_echo(s):
    r = s.put(f"{API}/credentials", json={"api_key": "shortSECRETx"}, headers=H)
    assert r.status_code == 400
    assert "shortSECRETx" not in r.text


# --- save key + get masked ---
def test_save_key_and_get_masked(s):
    r = s.put(f"{API}/credentials", json={"api_key": KEY}, headers=H)
    assert r.status_code == 200, r.text
    assert KEY not in r.text and "gAAAA" not in r.text
    g = s.get(API)
    assert g.status_code == 200
    d = g.json()
    assert KEY not in g.text and "gAAAA" not in g.text
    assert d["has_api_key"] is True
    assert d["api_key_masked"].endswith("9876")
    assert d["test_connection_enabled"] is False


def test_settings_save_and_invalid_caller(s):
    bad = s.put(f"{API}/settings", json={"caller_number": "12ab"}, headers=H)
    assert bad.status_code == 400
    r = s.put(f"{API}/settings", json={"agent_id": "TEST_agent_pytest_01", "caller_number": "+918012340000"}, headers=H)
    assert r.status_code in (200, 400), r.text  # 400 if no changes
    d = s.get(API).json()
    assert d["agent_id"] == "TEST_agent_pytest_01"
    assert d["caller_number_masked"].endswith("0000")
    assert "+918012340000" not in s.get(API).text
    assert d["status"] == "configured_unverified"


def test_indian_caller_normalized(s):
    r = s.put(f"{API}/settings", json={"caller_number": "9876501234"}, headers=H)
    assert r.status_code == 200
    assert r.json()["caller_number_masked"].endswith("1234")


def test_test_connection_423(s):
    assert s.post(f"{API}/test-connection", headers=H).status_code == 423


def test_audit_no_secrets(s):
    r = s.get(f"{API}/audit")
    assert r.status_code == 200
    items = r.json()["items"]
    assert len(items) > 0
    assert KEY not in r.text and "gAAAA" not in r.text
    assert any(i["action"] == "api_key_replaced" for i in items)


def test_clear_requires_word_then_clears(s):
    assert s.post(f"{API}/clear", json={"confirmation": "clear"}, headers=H).status_code == 400
    assert s.post(f"{API}/clear", json={"confirmation": "CLEAR"}).status_code == 403
    r = s.post(f"{API}/clear", json={"confirmation": "CLEAR"}, headers=H)
    assert r.status_code == 200
    d = s.get(API).json()
    assert d["status"] == "not_configured"
    assert d["has_api_key"] is False and d["agent_id"] == ""
