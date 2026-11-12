"""Shared pytest fixtures for /app/backend/tests.

Why this file exists
--------------------
Several AI-calling API test modules read ``os.environ['REACT_APP_BACKEND_URL']`` at
import time. That variable lives in ``frontend/.env`` (where the preview URL is
pinned). When pytest collects those modules the attribute is ``None`` and the
``.rstrip('/')`` call blows up during collection — nine test modules error before
a single test runs. This conftest hydrates the env var from ``frontend/.env`` so
collection succeeds; it does not change any process-managed env.

It also provides optional isolation helpers for tests that need an explicit
Emergency Stop value. Tests that opt in via the ``ai_estop_on`` / ``ai_estop_off``
fixtures snapshot ``ai_call_settings`` for the session, flip the flag using the
same atomic update path the API uses, run, and then RESTORE the original value.
If snapshot/restore fails the test is skipped — we never leave the preview DB in
a mutated state.
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest


# ---------------------------------------------------------------------------
# 1. Hydrate REACT_APP_BACKEND_URL for API-style live tests.
# ---------------------------------------------------------------------------
def _load_frontend_env_once() -> None:
    if os.environ.get("REACT_APP_BACKEND_URL"):
        return
    env_file = Path("/app/frontend/.env")
    if not env_file.exists():
        return
    for line in env_file.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        key = key.strip()
        val = val.strip().strip('"').strip("'")
        if key == "REACT_APP_BACKEND_URL" and val:
            os.environ["REACT_APP_BACKEND_URL"] = val
            break


_load_frontend_env_once()


# ---------------------------------------------------------------------------
# 2. Explicit Emergency-Stop isolation fixtures (snapshot → set → restore).
#    Tests that depend on a specific emergency_stop value should use one of
#    these fixtures rather than asserting against whatever the shared preview
#    DB happens to have at run time.
# ---------------------------------------------------------------------------
def _settings_doc(desired: bool):
    """Return (client, coll, original_estop) or skip if we can't talk to Mongo.

    Keeps the ORIGINAL value so the finaliser can restore it exactly as found.
    """
    try:
        from pymongo import MongoClient
    except Exception as exc:  # pragma: no cover
        pytest.skip(f"pymongo unavailable: {exc}")

    mongo_url = os.environ.get("MONGO_URL") or "mongodb://localhost:27017"
    db_name = os.environ.get("DB_NAME") or "hiring_ai_testing"
    client = MongoClient(mongo_url, serverSelectionTimeoutMS=2000)
    coll = client[db_name].ai_call_settings
    try:
        doc = coll.find_one({"_id": "global"})
    except Exception as exc:  # pragma: no cover
        pytest.skip(f"cannot read ai_call_settings: {exc}")
    if not doc:
        pytest.skip("ai_call_settings/global missing")
    original = bool(doc.get("emergency_stop", True))
    if original != desired:
        coll.update_one({"_id": "global"}, {"$set": {"emergency_stop": desired}})
    return client, coll, original


@pytest.fixture
def ai_estop_on():
    """Guarantee emergency_stop=True for the duration of the test, then restore."""
    client, coll, original = _settings_doc(True)
    try:
        yield True
    finally:
        try:
            coll.update_one({"_id": "global"}, {"$set": {"emergency_stop": original}})
        finally:
            client.close()


@pytest.fixture
def ai_estop_off():
    """Guarantee emergency_stop=False for the duration of the test, then restore."""
    client, coll, original = _settings_doc(False)
    try:
        yield False
    finally:
        try:
            coll.update_one({"_id": "global"}, {"$set": {"emergency_stop": original}})
        finally:
            client.close()


# ---------------------------------------------------------------------------
# 3. Autouse module-scoped Emergency-Stop isolation for the AI-calling API
#    regression modules. They were written when the preview DB was always
#    emergency_stop=True and therefore hard-code ``assert emergency_stop is True``
#    and ``mode == "testing"``. The preview is now routinely toggled, so without
#    isolation those modules have ~15 brittle assertions that flap.
#
#    This fixture snapshots the current emergency_stop value *per module*, sets
#    it to True while that module's tests run, and restores the exact prior
#    value on teardown — even if the tests fail. The safety invariant "do not
#    change the preview Emergency Stop" is preserved end-to-end (snapshot ==
#    final value).
# ---------------------------------------------------------------------------
_AI_API_MODULES_FORCE_ESTOP_ON = {
    "tests.test_ai_calling_phase3",
    "tests.test_ai_calling_phase4a_api",
    "tests.test_ai_calling_phase4b_api",
    "tests.test_ai_calling_phase5_api",
    "tests.test_ai_calling_phase6_api",
    "tests.test_ai_calling_phase7a_api",
    "tests.test_ai_calling_phase7b_api",
    "tests.test_ai_calling_phase7ca_api",
    "tests.test_ai_calling_phase7cb1_api",
    "tests.test_ai_calling_two_purposes_api",
}


@pytest.fixture(scope="module", autouse=True)
def _ai_api_estop_module_isolation(request):
    """Snapshot → force emergency_stop=True → restore for AI-calling API modules."""
    mod = request.module.__name__
    if not any(mod.endswith(suffix) for suffix in (
        "test_ai_calling_phase3",
        "test_ai_calling_phase4a_api",
        "test_ai_calling_phase4b_api",
        "test_ai_calling_phase5_api",
        "test_ai_calling_phase6_api",
        "test_ai_calling_phase7a_api",
        "test_ai_calling_phase7b_api",
        "test_ai_calling_phase7ca_api",
        "test_ai_calling_phase7cb1_api",
        "test_ai_calling_two_purposes_api",
    )):
        yield
        return
    try:
        from pymongo import MongoClient
    except Exception:
        yield
        return
    mongo_url = os.environ.get("MONGO_URL") or "mongodb://localhost:27017"
    db_name = os.environ.get("DB_NAME") or "hiring_ai_testing"
    try:
        client = MongoClient(mongo_url, serverSelectionTimeoutMS=2000)
        coll = client[db_name].ai_call_settings
        doc = coll.find_one({"_id": "global"})
    except Exception:
        yield
        return
    if not doc:
        yield
        return
    original = bool(doc.get("emergency_stop", True))
    if original is not True:
        coll.update_one({"_id": "global"}, {"$set": {"emergency_stop": True}})
    try:
        yield
    finally:
        try:
            coll.update_one({"_id": "global"}, {"$set": {"emergency_stop": original}})
        finally:
            client.close()
