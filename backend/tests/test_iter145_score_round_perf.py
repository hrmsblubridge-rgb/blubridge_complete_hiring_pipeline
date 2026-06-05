"""iter145 — Score & Round perf hardening regression.

The iter144 implementation of /score-round/filter-options pulled the
FULL pipeline_data collection (136k+ rows in production) into Python on
every call and shipped 100k+ <option> nodes to the browser. That caused
serious page lag and occasional browser blackouts when the recruiter
navigated to /score-round or applied a filter.

This regression test locks down three independent guarantees:
  1. Backend response is capped — never more than `limit` (default 500)
     entries per field, regardless of dataset size.
  2. Backend uses sort+limit BEFORE the $addToSet group so the query
     does NOT scan the full collection.
  3. Frontend fetches the dropdown options LAZILY on input focus, not
     on page mount, so navigating to /score-round is instant.
"""

import os
import re
import sys
import time
import uuid

import pytest
import pytest_asyncio

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"))

from motor.motor_asyncio import AsyncIOMotorClient
from httpx import AsyncClient, ASGITransport


PAGE_SR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "..", "frontend", "src", "pages", "ScoreRound.js",
)
PAGE_US = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "..", "frontend", "src", "pages", "UpdateScores.js",
)


@pytest_asyncio.fixture
async def http_client():
    from server import app, get_current_user
    import bb_modules
    app.dependency_overrides[get_current_user] = lambda: "iter145-test"
    original = bb_modules._auth_fn
    async def _bypass(_req):
        return "iter145-test"
    bb_modules._auth_fn = _bypass
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test", timeout=30.0) as c:
        yield c
    app.dependency_overrides.clear()
    bb_modules._auth_fn = original


# ── Backend perf guarantees ──────────────────────────────────────────────

@pytest.mark.asyncio
async def test_filter_options_caps_and_perf(http_client):
    """Three perf guarantees combined into one test to avoid the
    motor + pytest-asyncio "event loop is closed" issue that fires when
    multiple async tests share a module-cached motor client:

      1. With `limit=50`, no field returns more than 50 entries.
      2. The default (no `limit`) cap is ≤ 500 — beyond that a
         <datalist> stops being usable in Chrome/Firefox.
      3. End-to-end wall-clock for the endpoint stays well under 5s —
         intentionally generous; catches regressions like the original
         "scan all 136k rows + ship 5MB JSON" implementation.
    """
    # 1) Explicit limit
    r = await http_client.get(
        "/api/bb/score-round/filter-options",
        params={"limit": 50},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert len(body["name"]) <= 50
    assert len(body["email"]) <= 50
    assert len(body["phone"]) <= 50

    # 2) Default cap ≤ 500 + 3) wall-clock < 5s
    t = time.time()
    r = await http_client.get("/api/bb/score-round/filter-options")
    dt = time.time() - t
    assert r.status_code == 200
    body = r.json()
    for f in ("name", "email", "phone"):
        assert len(body[f]) <= 500, (
            f"{f} returned {len(body[f])} entries — must be ≤ 500"
        )
    assert dt < 5.0, f"endpoint took {dt:.2f}s — must be < 5s"


# ── Source-code guards (cheap + lock the architecture in) ────────────────

def test_backend_filter_options_uses_sort_limit_before_group():
    """The aggregation pipeline must $sort + $limit BEFORE the $group
    stage so the heavy $addToSet operates on a tiny window, not the
    full collection."""
    bb = open(
        os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "bb_modules.py",
        ),
        encoding="utf-8",
    ).read()
    fn_idx = bb.index("async def score_round_filter_options")
    fn_end = bb.index("\n\n@bb_router", fn_idx)
    fn = bb[fn_idx:fn_end]
    # The pipeline used in this endpoint must include sort + limit
    # BEFORE the group, and the group must use $addToSet.
    assert '"$sort"' in fn, "missing $sort stage"
    assert '"$limit"' in fn, "missing $limit stage"
    assert "$addToSet" in fn, "missing $addToSet stage"
    # Sort must appear before group lexically.
    assert fn.index('"$sort"') < fn.index("$group" if "$group" in fn else "$addToSet"), (
        "$sort must appear BEFORE $group"
    )
    # asyncio.gather is used to parallelise the per-field aggregations.
    assert "asyncio.gather" in fn


def test_score_round_frontend_lazy_fetches_on_focus():
    """The Score & Round combo-box filters must NOT fetch options on
    mount; instead each input fires `onFocus={fetchFilterOpts}`."""
    s = open(PAGE_SR, encoding="utf-8").read()
    # No `useEffect(() => { fetchFilterOpts(); }, [fetchFilterOpts])` —
    # that's the eager-fetch pattern we just removed.
    assert "useEffect(() => { fetchFilterOpts(); }, [fetchFilterOpts])" not in s, (
        "fetchFilterOpts must NOT run on mount — it must be lazy on focus"
    )
    # The 3 inputs must wire onFocus to the lazy fetcher.
    for tid in ("sr-filter-name", "sr-filter-email", "sr-filter-phone"):
        idx = s.index(f'data-testid="{tid}"')
        tag_start = s.rfind("<input", 0, idx)
        tag_end = s.index(">", idx)
        tag = s[tag_start: tag_end + 1]
        assert "onFocus={fetchFilterOpts}" in tag, (
            f"{tid} input missing onFocus={{fetchFilterOpts}}"
        )
    # The lazy-load idempotency guard must be present.
    assert "optsLoadedRef" in s


def test_update_scores_frontend_lazy_fetches_on_focus():
    """Same pattern applied to /update-scores so the same perf
    regression can't reappear there."""
    s = open(PAGE_US, encoding="utf-8").read()
    assert "useEffect(() => { fetchFilterOpts(); }, [fetchFilterOpts])" not in s
    for tid in ("us-filter-name", "us-filter-email", "us-filter-phone"):
        idx = s.index(f'data-testid="{tid}"')
        tag_start = s.rfind("<input", 0, idx)
        tag_end = s.index(">", idx)
        tag = s[tag_start: tag_end + 1]
        assert "onFocus={fetchFilterOpts}" in tag, (
            f"{tid} input missing onFocus={{fetchFilterOpts}}"
        )
    assert "optsLoadedRef" in s
