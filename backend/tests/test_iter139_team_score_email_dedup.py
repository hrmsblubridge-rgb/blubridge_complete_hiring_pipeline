"""iter139 — Team Score email-based deduplication.

Email is the unique business key. On every manual add, manual edit, and
import, any existing rows sharing the same email (case-insensitive) are
fully REPLACED by the new incoming doc — no field merging, no score
accumulation. Pre-existing duplicates are consolidated in the same pass.
"""

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


# ───────── Manual Add — duplicate email replaces existing ──────────────

@pytest.mark.asyncio
async def test_manual_add_replaces_existing_by_email(db, mock_req):
    import team_score
    suffix = uuid.uuid4().hex[:8]
    email = f"john_{suffix}@company.com"
    try:
        # First add — old record.
        await team_score.create_employee(
            team_score.EmployeeIn(
                name="John", email=email, role="Developer", college="ABC",
                round_scores={"R1": 5.0},
                employee_status="active",
            ),
            mock_req,
        )
        # Second add — same email, completely different details.
        await team_score.create_employee(
            team_score.EmployeeIn(
                name="John Smith", email=email, role="Senior Developer",
                college="XYZ", round_scores={"R2": 9.0},
                employee_status="inactive",
            ),
            mock_req,
        )
        # Exactly ONE doc remains for this email; it's the new one.
        docs = await db.ts_employees.find(
            {"email": {"$regex": f"^{_re.escape(email)}$", "$options": "i"}}
        ).to_list(None)
        assert len(docs) == 1, f"expected 1 doc, got {len(docs)}"
        d = docs[0]
        # Full replacement — no merged fields.
        assert d["name"] == "John Smith"
        assert d["role"] == "Senior Developer"
        assert d["college"] == "XYZ"
        assert d["employee_status"] == "inactive"
        assert d["round_scores"] == {"R2": 9.0}
        assert "R1" not in (d.get("round_scores") or {})
    finally:
        await db.ts_employees.delete_many(
            {"email": {"$regex": f"^{_re.escape(email)}$", "$options": "i"}}
        )
        await db.ts_rounds.delete_many({"round_name": {"$in": ["R1", "R2"]}})


@pytest.mark.asyncio
async def test_manual_add_different_emails_both_kept(db, mock_req):
    """Sanity check: different emails should NOT collide."""
    import team_score
    suffix = uuid.uuid4().hex[:8]
    a = f"john_{suffix}@company.com"
    b = f"alice_{suffix}@company.com"
    try:
        await team_score.create_employee(
            team_score.EmployeeIn(name="John", email=a), mock_req)
        await team_score.create_employee(
            team_score.EmployeeIn(name="Alice", email=b), mock_req)
        docs = await db.ts_employees.find(
            {"email": {"$in": [a, b]}}
        ).to_list(None)
        assert len(docs) == 2
    finally:
        await db.ts_employees.delete_many({"email": {"$in": [a, b]}})


# ───────── Case-insensitive email matching ─────────────────────────────

@pytest.mark.asyncio
async def test_case_insensitive_email_dedup(db, mock_req):
    import team_score
    suffix = uuid.uuid4().hex[:8]
    lower = f"john_{suffix}@company.com"
    upper = f"JOHN_{suffix}@COMPANY.COM"
    mixed = f"John_{suffix}@Company.com"
    try:
        await team_score.create_employee(
            team_score.EmployeeIn(name="L", email=lower), mock_req)
        await team_score.create_employee(
            team_score.EmployeeIn(name="U", email=upper), mock_req)
        await team_score.create_employee(
            team_score.EmployeeIn(name="M", email=mixed), mock_req)
        # All three were treated as the SAME identity; only the last
        # one survives.
        docs = await db.ts_employees.find(
            {"email": {"$regex": f"^{_re.escape(lower)}$", "$options": "i"}}
        ).to_list(None)
        assert len(docs) == 1
        assert docs[0]["name"] == "M"
    finally:
        await db.ts_employees.delete_many(
            {"email": {"$regex": f"^{_re.escape(lower)}$", "$options": "i"}}
        )


# ───────── Import — duplicate email replaces existing ──────────────────

@pytest.mark.asyncio
async def test_import_replaces_existing_email(db, mock_req):
    import team_score
    suffix = uuid.uuid4().hex[:8]
    email = f"john_{suffix}@company.com"
    try:
        # Seed an old record manually.
        await team_score.create_employee(
            team_score.EmployeeIn(
                name="Old John", email=email, role="Developer",
                round_scores={f"R1_{suffix}": 5.0},
            ),
            mock_req,
        )
        # Import a CSV with the SAME email but different details.
        csv = (
            f"Name,Email,Role,R2_{suffix}\n"
            f"New John,{email},Senior Dev,9\n"
        )
        res = await team_score.import_team_scores(
            mock_req, file=_FakeUpload("x.csv", csv.encode("utf-8"))
        )
        assert res["success"] is True
        assert res["updated"] == 1
        assert res["inserted"] == 0
        # Exactly one survivor.
        docs = await db.ts_employees.find(
            {"email": {"$regex": f"^{_re.escape(email)}$", "$options": "i"}}
        ).to_list(None)
        assert len(docs) == 1
        d = docs[0]
        assert d["name"] == "New John"
        assert d["role"] == "Senior Dev"
        assert d["round_scores"] == {f"R2_{suffix}": 9.0}
    finally:
        await db.ts_employees.delete_many(
            {"email": {"$regex": f"^{_re.escape(email)}$", "$options": "i"}}
        )
        await db.ts_rounds.delete_many(
            {"round_name": {"$in": [f"R1_{suffix}", f"R2_{suffix}"]}}
        )


@pytest.mark.asyncio
async def test_import_case_insensitive_dedup(db, mock_req):
    """Importing JOHN@COMPANY.COM when john@company.com exists must
    REPLACE (not insert a second row)."""
    import team_score
    suffix = uuid.uuid4().hex[:8]
    email_lc = f"john_{suffix}@company.com"
    try:
        await team_score.create_employee(
            team_score.EmployeeIn(name="lower", email=email_lc), mock_req)
        csv = (
            "Name,Email\n"
            f"upper,{email_lc.upper()}\n"
        )
        await team_score.import_team_scores(
            mock_req, file=_FakeUpload("x.csv", csv.encode("utf-8"))
        )
        docs = await db.ts_employees.find(
            {"email": {"$regex": f"^{_re.escape(email_lc)}$", "$options": "i"}}
        ).to_list(None)
        assert len(docs) == 1
        assert docs[0]["name"] == "upper"
    finally:
        await db.ts_employees.delete_many(
            {"email": {"$regex": f"^{_re.escape(email_lc)}$", "$options": "i"}}
        )


# ───────── Pre-existing duplicates get consolidated on next write ──────

@pytest.mark.asyncio
async def test_preexisting_duplicates_consolidated_on_add(db, mock_req):
    """Legacy rows: 3 records share an email. Next create_employee for
    that email must wipe ALL three and leave only the new one."""
    import team_score
    suffix = uuid.uuid4().hex[:8]
    email = f"dup_{suffix}@company.com"
    try:
        # Seed 3 legacy duplicates with random round score noise.
        for i in range(3):
            await db.ts_employees.insert_one({
                "name": f"Legacy{i}", "email": email, "employee_status": "active",
                "round_scores": {f"L_{i}": float(i)},
            })
        assert await db.ts_employees.count_documents({"email": email}) == 3

        # New add → ALL legacy rows wiped; new is the only survivor.
        await team_score.create_employee(
            team_score.EmployeeIn(
                name="Fresh", email=email, role="Lead",
                round_scores={"FreshR": 7.0},
                employee_status="inactive",
            ),
            mock_req,
        )
        docs = await db.ts_employees.find(
            {"email": {"$regex": f"^{_re.escape(email)}$", "$options": "i"}}
        ).to_list(None)
        assert len(docs) == 1
        assert docs[0]["name"] == "Fresh"
        assert docs[0]["round_scores"] == {"FreshR": 7.0}
        assert docs[0]["employee_status"] == "inactive"
    finally:
        await db.ts_employees.delete_many({"email": email})
        await db.ts_rounds.delete_many({"round_name": "FreshR"})


# ───────── Manual edit consolidates other rows sharing the new email ───

@pytest.mark.asyncio
async def test_manual_edit_consolidates_other_rows_sharing_email(db, mock_req):
    """User edits row B and sets its email to match row A. After save
    only ONE row remains — the edited one."""
    import team_score
    suffix = uuid.uuid4().hex[:8]
    shared = f"shared_{suffix}@company.com"
    try:
        # Seed two distinct rows.
        a = await team_score.create_employee(
            team_score.EmployeeIn(name="A", email=shared), mock_req)
        b = await team_score.create_employee(
            team_score.EmployeeIn(name="B", email=f"other_{suffix}@x.io"), mock_req)
        # Edit B → set its email to the shared one.
        await team_score.update_employee(
            b["id"],
            team_score.EmployeeIn(name="B-edited", email=shared, role="X"),
            mock_req,
        )
        docs = await db.ts_employees.find(
            {"email": {"$regex": f"^{_re.escape(shared)}$", "$options": "i"}}
        ).to_list(None)
        assert len(docs) == 1
        # The edited row (B) is the survivor.
        assert docs[0]["name"] == "B-edited"
        # Old A row was consolidated away.
        a_doc = await db.ts_employees.find_one({"_id": team_score._oid(a["id"])})
        assert a_doc is None
    finally:
        await db.ts_employees.delete_many(
            {"email": {"$regex": f"^{_re.escape(shared)}$", "$options": "i"}}
        )
        await db.ts_employees.delete_many(
            {"email": f"other_{suffix}@x.io"}
        )


# ───────── Empty email rows are NOT dedup'd against each other ─────────

@pytest.mark.asyncio
async def test_empty_email_rows_not_collapsed(db, mock_req):
    """Two records with empty email must remain separate — there's no
    business key to dedup on."""
    import team_score
    suffix = uuid.uuid4().hex[:8]
    n1 = f"NoEmailA_{suffix}"
    n2 = f"NoEmailB_{suffix}"
    try:
        await team_score.create_employee(
            team_score.EmployeeIn(name=n1, email=""), mock_req)
        await team_score.create_employee(
            team_score.EmployeeIn(name=n2, email=""), mock_req)
        docs = await db.ts_employees.find(
            {"name": {"$in": [n1, n2]}}
        ).to_list(None)
        assert len(docs) == 2
    finally:
        await db.ts_employees.delete_many({"name": {"$in": [n1, n2]}})


# ───────── Isolation contract still holds ───────────────────────────────

def test_isolation_contract_still_holds():
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
        assert f not in src_clean, f"forbidden collection {f!r} found"
