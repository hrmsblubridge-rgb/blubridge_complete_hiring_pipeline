"""iter135 — Team Score fixes:

1. Import — round column headers are NOT parsed; full header text
   becomes the round name verbatim. No bracket / total-score extraction.
2. Auto-creation — every non-base column auto-creates a ts_rounds row
   when missing (with NULL total_score).
3. Joining-date — accept dd-mm-yyyy + yyyy-mm-dd on import; store
   canonical yyyy-mm-dd; display/export as dd-mm-yyyy.
4. Frontend filter source-code guards (Name/Email/Role become dropdowns
   driven by /filters endpoint).
5. Isolation contract preserved.
"""

import asyncio
import io
import os
import re as _re
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


# ───── 1+2. Round headers are taken verbatim + auto-created ─────────────

@pytest.mark.asyncio
async def test_import_round_headers_are_verbatim_and_auto_created(db, mock_req):
    """User's exact examples — BP(20), C++(15), Mensa, Mensa.org — must
    all be stored as round names exactly as they appear, no parsing."""
    import team_score
    suffix = uuid.uuid4().hex[:6]
    headers = [
        f"BP(20)_{suffix}",
        f"C++(15)_{suffix}",
        f"Mensa_{suffix}",
        f"Mensa.org_{suffix}",
        f"Round-A_{suffix}",
        f"Round_B_{suffix}",
    ]
    header_line = "Name,Email,Role,Passing Year," + ",".join(headers)
    csv = (
        header_line + "\n"
        + f"User1,u1_{suffix}@x.io,Eng,2024,10,20,30,40,50,60\n"
    )
    fake = _FakeUpload("test.csv", csv.encode("utf-8"))

    try:
        res = await team_score.import_team_scores(mock_req, file=fake)
        assert res["success"] is True
        # Every column header was auto-created verbatim.
        for h in headers:
            assert h in res["rounds_created"], f"round {h!r} not auto-created"
            doc = await db.ts_rounds.find_one({"round_name": h})
            assert doc is not None, f"ts_rounds row missing for {h!r}"
            # CRITICAL: no parsing — total_score must be NULL.
            assert doc.get("total_score") in (None, 0, 0.0), (
                f"round {h!r} got total_score={doc.get('total_score')!r} — "
                f"brackets MUST NOT be parsed"
            )
        # Round scores stored under the verbatim keys.
        emp = await db.ts_employees.find_one({"email": f"u1_{suffix}@x.io"})
        assert emp is not None
        for h, expected in zip(headers, [10.0, 20.0, 30.0, 40.0, 50.0, 60.0]):
            assert emp["round_scores"].get(h) == expected
    finally:
        await db.ts_employees.delete_many({"email": {"$regex": f"_{suffix}@x.io$"}})
        await db.ts_rounds.delete_many({"round_name": {"$in": headers}})


@pytest.mark.asyncio
async def test_import_does_not_parse_bracket_pattern_as_total(db, mock_req):
    """Even the canonical BP(20) header — which the OLD code would have
    parsed as ('BP', 20) — must now be stored as the literal name 'BP(20)'
    with NULL total_score."""
    import team_score
    suffix = uuid.uuid4().hex[:6]
    rn = f"BP(20)_{suffix}"
    csv = (
        f"Name,Email,{rn}\n"
        f"User1,u_{suffix}@x.io,12\n"
    )
    fake = _FakeUpload("t.csv", csv.encode("utf-8"))
    try:
        res = await team_score.import_team_scores(mock_req, file=fake)
        # The literal "BP(20)_xxx" must be the round name.
        assert rn in res["rounds_created"]
        # The OLD-parsed name "BP" must NOT appear.
        assert "BP" not in res["rounds_created"]
        doc = await db.ts_rounds.find_one({"round_name": rn})
        assert doc and doc.get("total_score") in (None, 0, 0.0)
        # Source-code guard: the deprecated _parse_round_header /
        # _ROUND_COL_RE must be gone.
        import inspect
        src = inspect.getsource(team_score)
        assert "_parse_round_header" not in src
        assert "_ROUND_COL_RE" not in src
    finally:
        await db.ts_employees.delete_many({"email": f"u_{suffix}@x.io"})
        await db.ts_rounds.delete_many({"round_name": rn})


# ───── 3. Joining-date normalisation + display ──────────────────────────

def test_normalize_joining_date_helpers():
    """Helper functions must convert dd-mm-yyyy ↔ yyyy-mm-dd correctly."""
    import team_score
    # dd-mm-yyyy → yyyy-mm-dd (canonical store form)
    assert team_score._normalize_joining_date("01-06-2026") == "2026-06-01"
    assert team_score._normalize_joining_date("15-12-2025") == "2025-12-15"
    # yyyy-mm-dd passes through.
    assert team_score._normalize_joining_date("2026-06-01") == "2026-06-01"
    # ISO timestamps get stripped of the time component.
    assert team_score._normalize_joining_date("2026-06-01T00:00:00") == "2026-06-01"
    # Display: yyyy-mm-dd → dd-mm-yyyy.
    assert team_score._format_joining_date_display("2026-06-01") == "01-06-2026"
    assert team_score._format_joining_date_display("2025-12-15") == "15-12-2025"
    # Empty stays empty.
    assert team_score._normalize_joining_date("") == ""
    assert team_score._format_joining_date_display("") == ""


@pytest.mark.asyncio
async def test_import_normalizes_both_date_formats(db, mock_req):
    """An import with BOTH dd-mm-yyyy and yyyy-mm-dd in the same column
    must end up canonical yyyy-mm-dd in the DB."""
    import team_score
    suffix = uuid.uuid4().hex[:6]
    csv = (
        "Name,Email,Joining Date\n"
        f"A_{suffix},a_{suffix}@x.io,01-06-2026\n"
        f"B_{suffix},b_{suffix}@x.io,2026-06-01\n"
        f"C_{suffix},c_{suffix}@x.io,15-12-2025\n"
    )
    fake = _FakeUpload("t.csv", csv.encode("utf-8"))
    try:
        await team_score.import_team_scores(mock_req, file=fake)
        a = await db.ts_employees.find_one({"email": f"a_{suffix}@x.io"})
        b = await db.ts_employees.find_one({"email": f"b_{suffix}@x.io"})
        c = await db.ts_employees.find_one({"email": f"c_{suffix}@x.io"})
        assert a["joining_date"] == "2026-06-01"
        assert b["joining_date"] == "2026-06-01"
        assert c["joining_date"] == "2025-12-15"
    finally:
        await db.ts_employees.delete_many(
            {"email": {"$regex": f"_{suffix}@x.io$"}}
        )


@pytest.mark.asyncio
async def test_export_renders_joining_date_as_dd_mm_yyyy(db, mock_req):
    """Stored yyyy-mm-dd must be rendered as dd-mm-yyyy in exports."""
    import team_score
    suffix = uuid.uuid4().hex[:6]
    emp = await team_score.create_employee(
        team_score.EmployeeIn(
            name=f"DateTester_{suffix}", email=f"d_{suffix}@x.io",
            joining_date="2026-06-01",
        ),
        mock_req,
    )
    try:
        headers, rows = await team_score._collect_export_rows(
            {"email": f"d_{suffix}@x.io"}
        )
        # Column index of "Joining Date"
        jd_idx = headers.index("Joining Date")
        assert rows[0][jd_idx] == "01-06-2026", (
            f"Export joining_date got {rows[0][jd_idx]!r}, expected '01-06-2026'"
        )
        # No time component anywhere.
        for cell in rows[0]:
            assert "T00:00" not in str(cell)
            assert ":00:00" not in str(cell)
    finally:
        await db.ts_employees.delete_one({"_id": team_score._oid(emp["id"])})


@pytest.mark.asyncio
async def test_create_employee_normalizes_dd_mm_yyyy(db, mock_req):
    """API consumers can POST dd-mm-yyyy and we store yyyy-mm-dd."""
    import team_score
    suffix = uuid.uuid4().hex[:6]
    emp = await team_score.create_employee(
        team_score.EmployeeIn(
            name=f"DMY_{suffix}", email=f"dmy_{suffix}@x.io",
            joining_date="15-12-2025",
        ),
        mock_req,
    )
    try:
        doc = await db.ts_employees.find_one({"_id": team_score._oid(emp["id"])})
        assert doc["joining_date"] == "2025-12-15"
    finally:
        await db.ts_employees.delete_one({"_id": team_score._oid(emp["id"])})


# ───── 4. Frontend filter source-code guard ─────────────────────────────

def test_frontend_filters_use_select_dropdowns():
    """Name/Email/Role filters must be <select> dropdowns populated from
    `filterOpts` rather than free-text inputs."""
    path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "..", "frontend", "src", "pages", "TeamScore.js",
    )
    src = open(path, encoding="utf-8").read()
    # Each filter must be wrapped in <select ...>...</select>.
    for testid in ("ts-filter-name", "ts-filter-email", "ts-filter-role"):
        # Find the line with this data-testid.
        m = _re.search(rf'data-testid="{testid}"', src)
        assert m is not None, f"{testid} missing"
        # Walk backwards a bit and confirm it sits inside a <select.
        window = src[max(0, m.start() - 300): m.end() + 300]
        assert "<select" in window, (
            f"{testid} is not rendered as a <select> dropdown"
        )
        # And the dropdown maps from filterOpts.{field}.
        field = testid.split("-")[-1]
        assert f"filterOpts.{field}" in window, (
            f"{testid} dropdown should source options from filterOpts.{field}"
        )
    # Date helper present.
    assert "fmtJoiningDate" in src
    assert "joining_date" in src


# ───── 5. Isolation contract still holds ───────────────────────────────

def test_isolation_contract_still_holds():
    """No hiring-collection references after iter135 changes."""
    import inspect
    import team_score
    src = inspect.getsource(team_score)
    src_clean = _re.sub(r'""".*?"""', '', src, flags=_re.DOTALL)
    src_clean = _re.sub(r"'''.*?'''", '', src_clean, flags=_re.DOTALL)
    src_clean = _re.sub(r"#.*$", '', src_clean, flags=_re.MULTILINE)
    for f in (
        "pipeline_data", "naukri_applies", "bb_applicant_updates",
        "bb_rounds", "bb_job_roles", "job_titles_master",
        "registered_candidates", "bb_job_openings", "bb_hiring_forms",
    ):
        assert f not in src_clean, f"forbidden hiring collection {f!r} found"
