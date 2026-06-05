"""iter143 — Team Score import clamps out-of-range round scores.

If an imported cell value exceeds the round's `total_score`, replace
the value with the total. NULL/0 totals → no clamp (there's no ceiling
to enforce). Auto-created rounds from the same import default to NULL
total, so their cells are NOT clamped.

The endpoint reports `scores_clamped: <int>` so the UI can surface it.
"""

import os
import re
import sys
import uuid

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"))

from motor.motor_asyncio import AsyncIOMotorClient
from unittest.mock import AsyncMock, MagicMock
from fastapi import Request


@pytest.fixture
def db():
    import team_score
    client = AsyncIOMotorClient(os.environ["MONGO_URL"])
    fresh = client[os.environ["DB_NAME"]]
    team_score._db = fresh
    # iter143 — auth bypass via in-process mock; no password mutation.
    team_score._require_auth = AsyncMock(return_value=None)
    return fresh


@pytest.fixture
def mock_req():
    return MagicMock(spec=Request)


class _FakeUpload:
    def __init__(self, name, data):
        self.filename = name
        self._data = data

    async def read(self):
        return self._data


@pytest.mark.asyncio
async def test_import_clamps_scores_above_round_total(db, mock_req):
    """Cells > round.total_score get replaced with round.total_score.
    Cells <= total pass through untouched."""
    import team_score
    suffix = uuid.uuid4().hex[:8]
    round_name = f"Iter143_Capped_{suffix}"
    try:
        # Pre-create the round with a known total of 20.
        await team_score.create_round(
            team_score.RoundIn(round_name=round_name, total_score=20.0),
            mock_req,
        )
        csv = (
            f"Name,Email,{round_name}\n"
            f"Within_{suffix},within_{suffix}@x.io,15\n"     # within range
            f"Exactly_{suffix},exact_{suffix}@x.io,20\n"     # equal to total
            f"Over_{suffix},over_{suffix}@x.io,99\n"         # WAY over → 20
            f"Slightly_{suffix},slight_{suffix}@x.io,20.5\n" # just over → 20
        )
        res = await team_score.import_team_scores(
            mock_req, file=_FakeUpload("t.csv", csv.encode("utf-8"))
        )
        assert res["success"] is True
        assert res["scores_clamped"] == 2, (
            f"expected 2 cells clamped (99 and 20.5), got {res['scores_clamped']}"
        )
        # Verify the stored values:
        w = await db.ts_employees.find_one({"email": f"within_{suffix}@x.io"})
        e = await db.ts_employees.find_one({"email": f"exact_{suffix}@x.io"})
        o = await db.ts_employees.find_one({"email": f"over_{suffix}@x.io"})
        s = await db.ts_employees.find_one({"email": f"slight_{suffix}@x.io"})
        assert w["round_scores"][round_name] == 15.0
        assert e["round_scores"][round_name] == 20.0
        assert o["round_scores"][round_name] == 20.0, (
            f"99 should clamp to 20, got {o['round_scores'][round_name]}"
        )
        assert s["round_scores"][round_name] == 20.0, (
            f"20.5 should clamp to 20, got {s['round_scores'][round_name]}"
        )
    finally:
        await db.ts_employees.delete_many(
            {"email": {"$regex": f"_{suffix}@x.io$"}}
        )
        await db.ts_rounds.delete_many({"round_name": round_name})


@pytest.mark.asyncio
async def test_auto_created_round_has_no_ceiling_so_no_clamp(db, mock_req):
    """When the import itself auto-creates a round (its total ends up
    NULL), there is no ceiling to clamp against — even a "huge" value
    stays as the user wrote it."""
    import team_score
    suffix = uuid.uuid4().hex[:8]
    rn = f"Iter143_Auto_{suffix}"   # not pre-created
    try:
        csv = (
            f"Name,Email,{rn}\n"
            f"Big_{suffix},big_{suffix}@x.io,9999\n"
        )
        res = await team_score.import_team_scores(
            mock_req, file=_FakeUpload("t.csv", csv.encode("utf-8"))
        )
        assert res["scores_clamped"] == 0, (
            f"NULL-total auto-created round must NOT clamp; got "
            f"scores_clamped={res['scores_clamped']}"
        )
        e = await db.ts_employees.find_one({"email": f"big_{suffix}@x.io"})
        assert e["round_scores"][rn] == 9999.0
        r_doc = await db.ts_rounds.find_one({"round_name": rn})
        assert r_doc and r_doc.get("total_score") in (None, 0, 0.0)
    finally:
        await db.ts_employees.delete_many(
            {"email": f"big_{suffix}@x.io"}
        )
        await db.ts_rounds.delete_many({"round_name": rn})


@pytest.mark.asyncio
async def test_clamp_applies_to_inactive_rows_too(db, mock_req):
    """Rows below the 'INACTIVE EMPLOYEES' separator must also be
    clamped — the rule is per-cell, not per-status."""
    import team_score
    suffix = uuid.uuid4().hex[:8]
    rn = f"Iter143_Both_{suffix}"
    try:
        await team_score.create_round(
            team_score.RoundIn(round_name=rn, total_score=10.0),
            mock_req,
        )
        csv = (
            f"Name,Email,{rn}\n"
            f"Active_{suffix},active_{suffix}@x.io,50\n"
            f"INACTIVE EMPLOYEES,,\n"
            f"Inactive_{suffix},inactive_{suffix}@x.io,77\n"
        )
        res = await team_score.import_team_scores(
            mock_req, file=_FakeUpload("t.csv", csv.encode("utf-8"))
        )
        assert res["scores_clamped"] == 2
        a = await db.ts_employees.find_one({"email": f"active_{suffix}@x.io"})
        i = await db.ts_employees.find_one({"email": f"inactive_{suffix}@x.io"})
        assert a["round_scores"][rn] == 10.0
        assert i["round_scores"][rn] == 10.0
        assert a["employee_status"] == "active"
        assert i["employee_status"] == "inactive"
    finally:
        await db.ts_employees.delete_many(
            {"email": {"$regex": f"_{suffix}@x.io$"}}
        )
        await db.ts_rounds.delete_many({"round_name": rn})


def test_isolation_contract_still_holds():
    """iter143 must not introduce any reads/writes to hiring collections."""
    import inspect
    import team_score
    src = inspect.getsource(team_score)
    src = re.sub(r'""".*?"""', '', src, flags=re.DOTALL)
    src = re.sub(r"'''.*?'''", '', src, flags=re.DOTALL)
    src = re.sub(r"#.*$", '', src, flags=re.MULTILINE)
    for f in (
        "pipeline_data", "naukri_applies", "bb_applicant_updates",
        "bb_rounds", "bb_job_roles", "job_titles_master",
        "bb_users",            # iter143 — also forbid touching auth.
    ):
        assert f not in src, f"forbidden collection {f!r} found"


def test_no_password_mutation_in_module_or_tests():
    """iter143 — Hard guard: ensure NO module under /app/backend resets
    `bb_users.password_hash` UNCONDITIONALLY (i.e. without first
    verifying the old password). This guards against future agents
    re-seeding the admin password from a script or migration.

    The only legitimate mutation site is `server.py`'s `change_password`
    endpoint, which calls `_verify_pw(old_password, ...)` before any
    `$set: {password_hash: ...}`. That file is whitelisted explicitly.
    """
    backend_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    WHITELIST = {
        os.path.join(backend_root, "server.py"),  # /api/change-password
    }
    THIS_FILE = os.path.abspath(__file__)
    offenders = []
    for dirpath, _dirnames, filenames in os.walk(backend_root):
        if any(seg in dirpath for seg in (".venv", "__pycache__", "node_modules")):
            continue
        for fn in filenames:
            if not fn.endswith(".py"):
                continue
            path = os.path.join(dirpath, fn)
            if path == THIS_FILE or path in WHITELIST:
                continue
            with open(path, "r", encoding="utf-8", errors="ignore") as fh:
                text = fh.read()
            if "password_hash" not in text:
                continue
            if re.search(
                r'\$set["\']?\s*:\s*\{[^}]*password_hash',
                text, re.DOTALL,
            ):
                offenders.append(path)
    assert not offenders, (
        "Forbidden unconditional password mutation found in: "
        + ", ".join(offenders)
    )
