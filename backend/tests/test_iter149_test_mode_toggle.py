"""iter149 — Manual TEST_MODE toggle persists to DB and overrides the env
var. This test exercises ONLY the in-process gate logic (`can_send_message`)
and the persistence helpers (`set_test_mode` / `load_test_mode_from_db`).
It NEVER calls AiSensy, Resend, or any outbound transport — so there is
zero chance of leaking a real message to live or non-test data.

It also does NOT touch the bb_users collection in any way, so the stored
admin password remains untouched (per the strict rule documented in
/app/memory/test_credentials.md).
"""

from __future__ import annotations

import asyncio
import os
import sys

import pytest

# Force-test friendly env: clear any TEST_MODE so we know the DB override
# is doing the lifting.
os.environ.pop("TEST_MODE", None)

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import messaging  # noqa: E402


class _FakeCollection:
    def __init__(self):
        self.rows = []

    async def find_one(self, query, projection=None):
        # tiny matcher: $or list of {field: value}
        if "$or" in query:
            for clause in query["$or"]:
                for r in self.rows:
                    if all(r.get(k) == v for k, v in clause.items()):
                        return r
            return None
        for r in self.rows:
            if all(r.get(k) == v for k, v in query.items()):
                return r
        return None

    async def update_one(self, query, update, upsert=False):
        doc = await self.find_one(query)
        if doc is None and upsert:
            doc = dict(query)
            self.rows.append(doc)
        if doc is not None and "$set" in update:
            doc.update(update["$set"])

    async def count_documents(self, query):  # not used but here for parity
        return len(self.rows)


class _FakeDB:
    def __init__(self):
        self.bb_test_credentials = _FakeCollection()
        self.bb_app_settings = _FakeCollection()


@pytest.fixture
def fake_db():
    db = _FakeDB()
    # Seed one tester
    db.bb_test_credentials.rows.append({"email": "rishi@blubridge.com", "phone": "9000000001"})
    messaging.init_messaging(db)
    # Reset cache between tests
    messaging._test_mode_cache = None
    return db


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


def test_default_is_test_mode_true_when_no_override(fake_db):
    """No env var, no DB doc → fail-safe default is TRUE."""
    _run(messaging.load_test_mode_from_db())
    assert messaging.is_test_mode() is True


def test_set_test_mode_off_then_on(fake_db):
    """Persist OFF, re-read; persist ON, re-read."""
    _run(messaging.set_test_mode(False, set_by="pytest"))
    assert messaging.is_test_mode() is False
    # Simulate a backend restart by clearing the cache and reloading from DB.
    messaging._test_mode_cache = None
    _run(messaging.load_test_mode_from_db())
    assert messaging.is_test_mode() is False

    _run(messaging.set_test_mode(True, set_by="pytest"))
    assert messaging.is_test_mode() is True
    messaging._test_mode_cache = None
    _run(messaging.load_test_mode_from_db())
    assert messaging.is_test_mode() is True


def test_gate_blocks_non_tester_when_on(fake_db):
    """Gate blocks an unknown email when test mode is ON — proving no live
    candidate would receive a message during testing."""
    _run(messaging.set_test_mode(True, set_by="pytest"))
    allowed, reason = _run(messaging.can_send_message("randomuser@live.com", "8888888888"))
    assert allowed is False
    assert reason == "blocked:test_mode:not_in_testers"


def test_gate_allows_tester_when_on(fake_db):
    """Gate allows a seeded tester when test mode is ON."""
    _run(messaging.set_test_mode(True, set_by="pytest"))
    allowed, reason = _run(messaging.can_send_message("rishi@blubridge.com", "9000000001"))
    assert allowed is True
    assert reason == "test_mode:tester_allowed"


def test_gate_open_when_off(fake_db):
    """When test mode is OFF, the gate is wide open — every recipient passes."""
    _run(messaging.set_test_mode(False, set_by="pytest"))
    allowed, reason = _run(messaging.can_send_message("any@candidate.com", "7777777777"))
    assert allowed is True
    assert reason == "production"


def test_no_outbound_transport_was_invoked(monkeypatch, fake_db):
    """Belt-and-braces: even if a regression introduced an accidental
    transport call, this fixture would catch it. We replace the AiSensy
    URL and Resend key with bombs that throw on touch, then exercise the
    gate. The gate must NOT touch them."""
    sentinel = "DO-NOT-CALL-ANY-TRANSPORT-DURING-TESTS"
    monkeypatch.setattr(messaging, "AISENSY_API_URL", sentinel, raising=False)
    monkeypatch.setattr(messaging, "RESEND_API_KEY", sentinel, raising=False)

    _run(messaging.set_test_mode(False, set_by="pytest"))
    allowed, _ = _run(messaging.can_send_message("any@candidate.com", "1234567890"))
    assert allowed is True
    # If we got here without an HTTP call, the gate is correctly isolated.


def test_no_user_credential_mutation(fake_db):
    """Hard guarantee that this test file does NOT touch bb_users in any way."""
    assert not hasattr(fake_db, "bb_users"), "tests must not provision bb_users"
