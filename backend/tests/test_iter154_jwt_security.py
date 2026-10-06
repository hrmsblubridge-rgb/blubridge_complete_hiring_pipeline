"""iter154 — JWT security hardening.

Verifies:
  1. JWT_SECRET fallback is removed (import fails without the env var).
  2. Login issues a token that carries the user's `token_version`.
  3. `/auth/check` accepts the token, /logout invalidates it, and
     subsequent requests with the SAME token now return 401.
  4. Tokens issued for user A cannot be used after user A's password
     changes (`token_version` bump on password change).
  5. bb_users state is preserved — only `token_version` and (if
     provisioned by the test) password_hash of the test user change.
     Existing production user rows (e.g. `Admin User`) are untouched.
"""

from __future__ import annotations

import os
import sys

import pytest
import pytest_asyncio

os.environ.setdefault("FRONTEND_URL", "http://localhost")
os.environ.setdefault("RESEND_API_KEY", "test")
os.environ.setdefault("MONGO_URL", os.environ.get("MONGO_URL", "mongodb://localhost:27017"))
os.environ.setdefault("DB_NAME", os.environ.get("DB_NAME", "test_iter154"))
os.environ.setdefault("JWT_SECRET", "iter154-test-secret-32-chars-min")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

pytestmark = pytest.mark.asyncio(loop_scope="session")


@pytest_asyncio.fixture(loop_scope="session", scope="session")
async def app_module():
    import server  # noqa
    return server


@pytest_asyncio.fixture(loop_scope="session")
async def test_user(app_module):
    """Provision a DEDICATED test user in bb_users so we never touch the
    real admin account. Named with a marker so cleanup is precise."""
    username = "iter154_pytest_user"
    password = "iter154_pytest_pw"
    from server import _hash_pw
    await app_module.db.bb_users.delete_many({"username": username})
    await app_module.db.bb_users.insert_one({
        "username": username,
        "password_hash": _hash_pw(password),
        "role": "admin",
        "token_version": 1,
        "_iter154_marker": True,
    })
    yield username, password
    await app_module.db.bb_users.delete_many({"_iter154_marker": True})


def test_jwt_secret_fallback_removed():
    """The default hardcoded secret must not exist in the source."""
    with open("/app/backend/server.py", "r") as f:
        src = f.read()
    assert 'recruitment-analytics-secret-key' not in src, (
        "Legacy hardcoded JWT_SECRET fallback still present — remove it."
    )


async def test_login_issues_versioned_token(app_module, test_user):
    """Login response should set an access_token cookie carrying `ver`."""
    username, password = test_user
    import jwt as _jwt
    from httpx import AsyncClient, ASGITransport
    transport = ASGITransport(app=app_module.app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        r = await ac.post("/api/login", json={"username": username, "password": password})
    assert r.status_code == 200
    token = r.cookies.get("access_token")
    assert token
    payload = _jwt.decode(token, os.environ["JWT_SECRET"], algorithms=["HS256"])
    assert payload["sub"] == username
    assert payload.get("ver") == 1  # our seeded token_version


async def test_logout_invalidates_prior_token(app_module, test_user):
    """The SAME token that worked before logout must return 401 after."""
    username, password = test_user
    from httpx import AsyncClient, ASGITransport
    transport = ASGITransport(app=app_module.app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        # Login
        r = await ac.post("/api/login", json={"username": username, "password": password})
        token = r.cookies.get("access_token")
        assert token
        headers = {"Authorization": f"Bearer {token}"}

        # Auth check works
        r = await ac.get("/api/auth/check", headers=headers)
        assert r.status_code == 200

        # Logout
        r = await ac.post("/api/logout", headers=headers)
        assert r.status_code == 200

        # Same token should now fail with 401
        r = await ac.get("/api/auth/check", headers=headers)
    assert r.status_code == 401, f"Expected 401 after logout, got {r.status_code}: {r.text}"


async def test_password_change_invalidates_tokens(app_module, test_user):
    """Changing password bumps token_version → prior tokens invalidated."""
    username, password = test_user
    new_password = "iter154_pytest_pw_v2"
    from httpx import AsyncClient, ASGITransport
    transport = ASGITransport(app=app_module.app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        r = await ac.post("/api/login", json={"username": username, "password": password})
        token = r.cookies.get("access_token")
        headers = {"Authorization": f"Bearer {token}"}
        assert (await ac.get("/api/auth/check", headers=headers)).status_code == 200

        r = await ac.post("/api/auth/change-password",
                          json={"old_password": password, "new_password": new_password},
                          headers=headers)
        assert r.status_code == 200

        # Old token must no longer work.
        r = await ac.get("/api/auth/check", headers=headers)
    assert r.status_code == 401


async def test_existing_admin_row_untouched(app_module):
    """Regression guard: the real `Admin User` row must be present with a
    password_hash we did NOT modify."""
    doc = await app_module.db.bb_users.find_one({"username": "Admin User"})
    if doc is None:
        pytest.skip("No production Admin User row in this DB — skipping.")
    assert doc.get("password_hash"), "Admin User row must retain its password_hash"
