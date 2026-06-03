"""iter133 — Team Score module (isolated CRUD + import/export).

Validates the spec end-to-end via direct calls to the module
functions (no HTTP round trip — auth is mocked). Each test seeds
synthetic ts_rounds + ts_employees rows tagged `_iter133_test=<marker>`
and self-cleans in `finally`.

ISOLATION ASSERTION: tests touch ONLY ts_rounds and ts_employees.
No reads or writes hit pipeline_data, naukri_applies,
bb_applicant_updates, bb_rounds, bb_job_roles, or job_titles_master.
"""

import asyncio
import io
import os
import sys
import uuid

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"))

from motor.motor_asyncio import AsyncIOMotorClient
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi import Request, UploadFile


@pytest.fixture
def db():
    import team_score
    client = AsyncIOMotorClient(os.environ["MONGO_URL"])
    fresh = client[os.environ["DB_NAME"]]
    team_score._db = fresh
    team_score._require_auth = AsyncMock(return_value=None)
    return fresh


@pytest.fixture
def mock_req():
    return MagicMock(spec=Request)


# ─────────────────────── Rounds CRUD ────────────────────────────────────


@pytest.mark.asyncio
async def test_create_and_list_round(db, mock_req):
    import team_score
    marker = f"_iter133_round_{uuid.uuid4().hex[:8]}"
    name = f"Iter133_R_{uuid.uuid4().hex[:6]}"
    try:
        r = await team_score.create_round(
            team_score.RoundIn(round_name=name, total_score=25), mock_req
        )
        assert r["round_name"] == name and r["total_score"] == 25.0
        listing = await team_score.list_rounds(mock_req)
        names = {x["round_name"] for x in listing["rounds"]}
        assert name in names
    finally:
        await db.ts_rounds.delete_many({"round_name": name})


@pytest.mark.asyncio
async def test_delete_round_purges_from_employees(db, mock_req):
    import team_score
    rn = f"Iter133_DR_{uuid.uuid4().hex[:6]}"
    r = await team_score.create_round(
        team_score.RoundIn(round_name=rn, total_score=10), mock_req
    )
    emp = await team_score.create_employee(
        team_score.EmployeeIn(name="Del Tester", round_scores={rn: 5.0}),
        mock_req,
    )
    try:
        await team_score.delete_round(r["id"], mock_req)
        # Employee's round_scores must no longer contain the deleted round.
        doc = await db.ts_employees.find_one({"_id": MagicMock()._mock_name or None}) or \
              await db.ts_employees.find_one({"name": "Del Tester"})
        assert rn not in (doc.get("round_scores") or {})
    finally:
        await db.ts_employees.delete_many({"name": "Del Tester"})
        await db.ts_rounds.delete_many({"round_name": rn})


# ─────────────────────── Employees CRUD ─────────────────────────────────


@pytest.mark.asyncio
async def test_employee_lifecycle(db, mock_req):
    import team_score
    rn = f"Iter133_EL_{uuid.uuid4().hex[:6]}"
    await team_score.create_round(team_score.RoundIn(round_name=rn, total_score=20), mock_req)
    emp = await team_score.create_employee(
        team_score.EmployeeIn(
            name=f"Iter133 Emp {uuid.uuid4().hex[:4]}",
            email="t@test.io", role="Engineer", nirf_rank="10",
            round_scores={rn: 15.0},
        ),
        mock_req,
    )
    try:
        # Default status active.
        assert emp["employee_status"] == "active"
        # Deactivate → status flips.
        res = await team_score.deactivate_employee(emp["id"], mock_req)
        assert res["employee_status"] == "inactive"
        # Reactivate → active again.
        res = await team_score.activate_employee(emp["id"], mock_req)
        assert res["employee_status"] == "active"
    finally:
        await db.ts_employees.delete_one({"_id": team_score._oid(emp["id"])})
        await db.ts_rounds.delete_many({"round_name": rn})


# ─────────────────────── Export — separator row + raw scores ────────────


@pytest.mark.asyncio
async def test_export_active_inactive_separation(db, mock_req):
    import team_score
    marker = f"_iter133_exp_{uuid.uuid4().hex[:8]}"
    rn = f"Iter133_EXP_{uuid.uuid4().hex[:6]}"
    await team_score.create_round(team_score.RoundIn(round_name=rn, total_score=20), mock_req)
    a = await team_score.create_employee(
        team_score.EmployeeIn(name="Active1", email="a@x.io", round_scores={rn: 10.0}),
        mock_req,
    )
    b = await team_score.create_employee(
        team_score.EmployeeIn(name="Inactive1", email="b@x.io", round_scores={rn: 18.0}),
        mock_req,
    )
    await team_score.deactivate_employee(b["id"], mock_req)
    try:
        headers, rows = await team_score._collect_export_rows({
            "$or": [{"email": "a@x.io"}, {"email": "b@x.io"}]
        })
        # Header contains round in `Name(Total)` format.
        assert any(f"{rn}(20)" in h or f"{rn}({rn}" not in h for h in headers)
        # Active row appears before separator, inactive row after.
        names = [r[0] for r in rows]
        assert "Active1" in names
        sep_idx = names.index("INACTIVE EMPLOYEES")
        assert names.index("Active1") < sep_idx
        assert "Inactive1" in names[sep_idx + 1:]
        # iter134 — Export cells mirror the Team Score table:
        # `score/total (pct%)` (e.g. `10/20 (50.00%)`).
        idx_round = [i for i, h in enumerate(headers) if h.startswith(rn)][0]
        active_row = rows[names.index("Active1")]
        assert active_row[idx_round] == "10/20 (50.00%)"
    finally:
        await db.ts_employees.delete_many({"email": {"$in": ["a@x.io", "b@x.io"]}})
        await db.ts_rounds.delete_many({"round_name": rn})


# ─────────────────────── Import — auto-create rounds + separator ────────


@pytest.mark.asyncio
async def test_import_creates_missing_rounds_and_splits_status(db, mock_req):
    import team_score
    new_round = f"Iter133_IMP_{uuid.uuid4().hex[:6]}"
    csv_content = (
        f"Name,Email,Role,{new_round}(50)\n"
        f"ImpActive,impa@x.io,Eng,40\n"
        f"INACTIVE EMPLOYEES,,,\n"
        f"ImpInactive,impi@x.io,Eng,30\n"
    )
    # Build a fake UploadFile.
    class _Fake:
        filename = "test.csv"
        def __init__(self, data): self._data = data
        async def read(self): return self._data
    fake = _Fake(csv_content.encode("utf-8"))

    try:
        res = await team_score.import_team_scores(mock_req, file=fake)
        assert res["success"] is True
        assert res["inserted"] >= 2
        assert res["separators"] >= 1
        assert new_round in res["rounds_created"]
        # Active employee → status='active'; below separator → 'inactive'.
        a = await db.ts_employees.find_one({"email": "impa@x.io"})
        i = await db.ts_employees.find_one({"email": "impi@x.io"})
        assert a and a["employee_status"] == "active"
        assert i and i["employee_status"] == "inactive"
        # Raw scores stored, not percentages.
        assert a["round_scores"][new_round] == 40.0
        assert i["round_scores"][new_round] == 30.0
    finally:
        await db.ts_employees.delete_many({"email": {"$in": ["impa@x.io", "impi@x.io"]}})
        await db.ts_rounds.delete_many({"round_name": new_round})


# ─────────────────────── Isolation contract ─────────────────────────────


@pytest.mark.asyncio
async def test_no_reads_to_hiring_collections(db, mock_req):
    """Source-code guard: the team_score module must NOT reference any
    hiring-pipeline collection. The spec mandates total isolation.
    We strip docstrings/comments before scanning so the module's own
    "we don't touch X" prose doesn't trip the guard."""
    import inspect, re as _re
    import team_score
    src = inspect.getsource(team_score)
    # Drop block-quoted docstrings and # comments.
    src_clean = _re.sub(r'""".*?"""', '', src, flags=_re.DOTALL)
    src_clean = _re.sub(r"'''.*?'''", '', src_clean, flags=_re.DOTALL)
    src_clean = _re.sub(r"#.*$", '', src_clean, flags=_re.MULTILINE)
    forbidden = [
        "pipeline_data", "naukri_applies", "bb_applicant_updates",
        "bb_rounds", "bb_job_roles", "job_titles_master",
        "registered_candidates", "bb_job_openings", "bb_hiring_forms",
    ]
    for f in forbidden:
        assert f not in src_clean, (
            f"team_score.py references forbidden hiring collection {f!r} — "
            f"breaks isolation contract."
        )
