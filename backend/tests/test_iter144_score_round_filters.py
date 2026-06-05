"""iter144 — Score & Round per-field filters + combo-box dropdowns.

Backend:
- /api/bb/score-round/table accepts independent `name`, `email`, `phone`
  query params (case-insensitive substring; phone digits-only).
- /api/bb/score-round/filter-options returns distinct name/email/phone
  values from `pipeline_data`, restricted to an optional date range.

Frontend (source-code guard):
- Three new combo-box filters (`sr-filter-name`, `sr-filter-email`,
  `sr-filter-phone`) — each rendered as `<input list="…">` paired with
  the matching `<datalist>`.
- Reset clears all three; the load() call wires them into the request.
"""

import os
import re
import sys
import uuid

import pytest
import pytest_asyncio

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"))

from motor.motor_asyncio import AsyncIOMotorClient
from httpx import AsyncClient, ASGITransport


PAGE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "..", "frontend", "src", "pages", "ScoreRound.js",
)


def _src():
    return open(PAGE, encoding="utf-8").read()


TAG_KEY = "_iter144_score_round_test"


@pytest_asyncio.fixture
async def db():
    client = AsyncIOMotorClient(os.environ["MONGO_URL"])
    d = client[os.environ["DB_NAME"]]
    yield d


@pytest_asyncio.fixture
async def http_client():
    # iter144 — dependency override + bb_router auth bypass, NOT a
    # password reset. The user has explicitly forbidden any agent from
    # mutating bb_users.password_hash.
    from server import app, get_current_user
    import bb_modules
    app.dependency_overrides[get_current_user] = lambda: "iter144-test"
    original_auth = bb_modules._auth_fn
    async def _bypass(_req):
        return "iter144-test"
    bb_modules._auth_fn = _bypass
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client
    app.dependency_overrides.clear()
    bb_modules._auth_fn = original_auth


@pytest.mark.asyncio
async def test_per_field_filters_and_filter_options(db, http_client):
    suffix = uuid.uuid4().hex[:8]
    # Numeric phone suffix so the backend's digits-only normaliser keeps it intact.
    num_suffix = re.sub(r"\D", "", uuid.uuid4().hex)[:5] or "12345"
    name_a = f"Iter144 Alpha {suffix}"
    name_b = f"Iter144 Beta {suffix}"
    email_a = f"alpha_{suffix}@example.com"
    email_b = f"beta_{suffix}@example.com"
    phone_a = f"99001{num_suffix}"
    phone_b = f"88002{num_suffix}"
    docs = [
        {TAG_KEY: True, "name": name_a, "email": email_a, "phone": phone_a,
         "schedule_date": "2026-06-01", "result_status": "Shortlisted"},
        {TAG_KEY: True, "name": name_b, "email": email_b, "phone": phone_b,
         "schedule_date": "2026-06-01", "result_status": "Shortlisted"},
    ]
    try:
        await db.pipeline_data.delete_many({TAG_KEY: True})
        await db.pipeline_data.insert_many(docs)

        # ── 1. /filter-options returns the seeded distinct values
        r = await http_client.get(
            "/api/bb/score-round/filter-options",
            params={"startDate": "2026-06-01", "endDate": "2026-06-01"},
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert name_a in body["name"] and name_b in body["name"]
        assert email_a.lower() in body["email"] and email_b.lower() in body["email"]
        assert phone_a in body["phone"] and phone_b in body["phone"]

        # ── 2. name= filter narrows to row A only
        r = await http_client.get(
            "/api/bb/score-round/table",
            params={"name": "Alpha " + suffix, "status": "", "limit": 100},
        )
        rows = [x for x in r.json().get("data", []) if x.get("name", "").startswith("Iter144")]
        rows = [x for x in rows if suffix in (x.get("name") or "")]
        assert len(rows) == 1 and rows[0]["name"] == name_a, rows

        # ── 3. email= filter narrows to row B only
        r = await http_client.get(
            "/api/bb/score-round/table",
            params={"email": email_b, "status": "", "limit": 100},
        )
        rows = [x for x in r.json().get("data", []) if x.get("email") == email_b]
        assert len(rows) == 1 and rows[0]["name"] == name_b

        # ── 4. phone= filter (digits-only normalisation): supplying the
        # number with formatting still finds the row.
        formatted_phone = f"({phone_a[:3]}) {phone_a[3:]}"
        r = await http_client.get(
            "/api/bb/score-round/table",
            params={"phone": formatted_phone, "status": "", "limit": 100},
        )
        rows = [x for x in r.json().get("data", []) if x.get("phone") == phone_a]
        assert len(rows) == 1 and rows[0]["name"] == name_a

        # ── 5. Combining two field filters AND together
        r = await http_client.get(
            "/api/bb/score-round/table",
            params={"name": "Iter144", "email": email_a, "status": "", "limit": 100},
        )
        rows = [x for x in r.json().get("data", []) if x.get("email") == email_a]
        assert len(rows) == 1 and rows[0]["name"] == name_a
    finally:
        await db.pipeline_data.delete_many({TAG_KEY: True})


# ─────────── Frontend source-code guards ────────────────────────────────

def test_frontend_has_three_combo_box_filters():
    s = _src()
    for tid, lid, field in (
        ("sr-filter-name", "sr-filter-name-list", "name"),
        ("sr-filter-email", "sr-filter-email-list", "email"),
        ("sr-filter-phone", "sr-filter-phone-list", "phone"),
    ):
        idx = s.index(f'data-testid="{tid}"')
        tag_start = s.rfind("<input", 0, idx)
        tag_end = s.index(">", idx)
        tag = s[tag_start: tag_end + 1]
        assert f'list="{lid}"' in tag, f"{tid} not wired to datalist {lid}"
        # The datalist is rendered and bound to filterOpts.{field}.
        m = re.search(
            rf'<datalist id="{lid}">.*?filterOpts\.{field}',
            s, re.DOTALL,
        )
        assert m, f"datalist {lid} missing or not bound to filterOpts.{field}"


def test_frontend_reset_clears_new_filters():
    s = _src()
    reset_fn = s[s.index("const resetFilters ="):]
    reset_fn = reset_fn[: reset_fn.index("};") + 2]
    for setter in ("setNameInput('')", "setEmailInput('')", "setPhoneInput('')"):
        assert setter in reset_fn, f"resetFilters missing {setter}"


def test_frontend_load_sends_per_field_params():
    s = _src()
    # The load() callback must forward the new fields.
    load_fn = s[s.index("const load = useCallback"):]
    load_fn = load_fn[: load_fn.index("[page, limit")]
    assert "params.name = appliedFilters.name" in load_fn
    assert "params.email = appliedFilters.email" in load_fn
    assert "params.phone = appliedFilters.phone" in load_fn


# ─────────── Password-mutation guard (re-asserted for this iter) ────────

def test_no_password_mutation_in_backend():
    """iter143/iter144 — keep enforcing: no PRODUCTION module under
    /app/backend may UNCONDITIONALLY $set bb_users.password_hash. The
    only legitimate mutation site is server.py's change_password
    endpoint, which is gated by _verify_pw(old_password, ...) and is
    whitelisted explicitly.

    Test files under tests/ are excluded because (a) they are never
    deployed, and (b) some legitimately CONTAIN this guard's own regex
    string as a literal, which would otherwise be a false positive.
    """
    backend_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    WHITELIST = {os.path.join(backend_root, "server.py")}
    offenders = []
    for dirpath, _dirnames, filenames in os.walk(backend_root):
        if any(seg in dirpath for seg in (".venv", "__pycache__", "node_modules", "/tests")):
            continue
        if dirpath.endswith("/tests"):
            continue
        for fn in filenames:
            if not fn.endswith(".py"):
                continue
            path = os.path.join(dirpath, fn)
            if path in WHITELIST:
                continue
            text = open(path, encoding="utf-8", errors="ignore").read()
            if "password_hash" not in text:
                continue
            if re.search(
                r'\$set["\']?\s*:\s*\{[^}]*password_hash',
                text, re.DOTALL,
            ):
                offenders.append(path)
    assert not offenders, (
        "Forbidden password mutation found in: " + ", ".join(offenders)
    )
