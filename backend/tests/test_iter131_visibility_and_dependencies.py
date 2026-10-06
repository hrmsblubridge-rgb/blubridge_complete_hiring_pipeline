"""iter131 — Visibility filters + dependency enforcement on the
Activate/Deactivate lifecycle.

Issue 1 of the user spec:
  * Inactive Job Roles must disappear from every dropdown / filter /
    picker (admin pages still see all rows for management).
  * Inactive Job Openings must disappear from every dropdown / picker.
  * Activating a Job Opening whose Role is inactive → 409 with the
    spec-mandated copy.
  * Activating a Hiring Form whose Role OR Opening is inactive → 409
    with the precise reason (4 cases in the spec).

Issue 2 of the user spec:
  * When `show_instruction_page=True` AND `instruction_content` is
    empty, the public flow must fall back to the default Instruction
    Page (the AI/ML "What You Need to Know" template) regardless of
    role — previously gated to AI/ML roles only.
"""

import asyncio
import inspect
import os
import sys
import uuid

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"))

from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorClient
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi import HTTPException, Request


@pytest.fixture
def db():
    import bb_modules
    client = AsyncIOMotorClient(os.environ["MONGO_URL"])
    fresh = client[os.environ["DB_NAME"]]
    bb_modules._db = fresh
    return fresh


@pytest.fixture
def mock_req():
    return MagicMock(spec=Request)


# ─────────────────────── Visibility (active_only) ─────────────────────────


@pytest.mark.asyncio
async def test_job_roles_active_only_excludes_inactive(db, mock_req):
    """`active_only=true` filters out inactive rows from the list."""
    import bb_modules
    marker = f"_iter131_v_{uuid.uuid4().hex[:8]}"
    active_name = f"Iter131 ActiveRole {uuid.uuid4().hex[:6]}"
    inactive_name = f"Iter131 InactiveRole {uuid.uuid4().hex[:6]}"
    await db.bb_job_roles.insert_many([
        {"name": active_name, "status": "active", "_iter131_test": marker},
        {"name": inactive_name, "status": "inactive", "_iter131_test": marker},
    ])
    try:
        with patch("bb_modules._require_auth", new=AsyncMock(return_value=None)):
            res_all = await bb_modules.list_job_roles(mock_req, active_only=False)
            res_active = await bb_modules.list_job_roles(mock_req, active_only=True)
        names_all = {r["name"] for r in res_all["roles"]}
        names_active = {r["name"] for r in res_active["roles"]}
        assert active_name in names_all and inactive_name in names_all
        assert active_name in names_active
        assert inactive_name not in names_active, (
            f"Inactive role leaked into active_only=true result: {inactive_name}"
        )
    finally:
        await db.bb_job_roles.delete_many({"_iter131_test": marker})


@pytest.mark.asyncio
async def test_job_openings_active_only_excludes_inactive(db, mock_req):
    import bb_modules
    marker = f"_iter131_o_{uuid.uuid4().hex[:8]}"
    a_id = (await db.bb_job_openings.insert_one(
        {"title": "Iter131 ActiveOp", "slug": f"i131-ao-{uuid.uuid4().hex[:6]}",
         "status": "active", "_iter131_test": marker}
    )).inserted_id
    b_id = (await db.bb_job_openings.insert_one(
        {"title": "Iter131 InactiveOp", "slug": f"i131-io-{uuid.uuid4().hex[:6]}",
         "status": "inactive", "_iter131_test": marker}
    )).inserted_id
    try:
        with patch("bb_modules._require_auth", new=AsyncMock(return_value=None)):
            res = await bb_modules.list_job_openings(mock_req, active_only=True)
        ids = {o["id"] for o in res["openings"]}
        assert str(a_id) in ids
        assert str(b_id) not in ids
    finally:
        await db.bb_job_openings.delete_many({"_iter131_test": marker})


@pytest.mark.asyncio
async def test_hiring_forms_active_only_excludes_inactive(db, mock_req):
    import bb_modules
    marker = f"_iter131_f_{uuid.uuid4().hex[:8]}"
    a_id = (await db.bb_hiring_forms.insert_one(
        {"name": "Iter131 ActiveForm", "slug": f"i131-af-{uuid.uuid4().hex[:6]}",
         "status": "active", "_iter131_test": marker}
    )).inserted_id
    b_id = (await db.bb_hiring_forms.insert_one(
        {"name": "Iter131 InactiveForm", "slug": f"i131-if-{uuid.uuid4().hex[:6]}",
         "status": "inactive", "_iter131_test": marker}
    )).inserted_id
    try:
        with patch("bb_modules._require_auth", new=AsyncMock(return_value=None)):
            res = await bb_modules.list_hiring_forms(mock_req, active_only=True)
        ids = {f["id"] for f in res["forms"]}
        assert str(a_id) in ids
        assert str(b_id) not in ids
    finally:
        await db.bb_hiring_forms.delete_many({"_iter131_test": marker})


# ─────────────────────── Dependency enforcement ───────────────────────────


@pytest.mark.asyncio
async def test_cannot_activate_opening_when_role_inactive(db, mock_req):
    """Spec dependency #1: opening blocked when role inactive."""
    import bb_modules
    marker = f"_iter131_d_{uuid.uuid4().hex[:8]}"
    role_name = f"Iter131 RoleDep {uuid.uuid4().hex[:6]}"
    await db.bb_job_roles.insert_one(
        {"name": role_name, "status": "inactive", "_iter131_test": marker}
    )
    op_id = (await db.bb_job_openings.insert_one(
        {"title": "Op", "job_role": role_name,
         "status": "inactive", "_iter131_test": marker}
    )).inserted_id

    try:
        with patch("bb_modules._require_auth", new=AsyncMock(return_value=None)):
            with pytest.raises(HTTPException) as exc:
                await bb_modules.activate_job_opening(str(op_id), mock_req)
        assert exc.value.status_code == 409
        assert "Job Role is currently inactive" in exc.value.detail
        # Opening must still be inactive.
        assert (await db.bb_job_openings.find_one({"_id": op_id}))["status"] == "inactive"

    finally:
        await db.bb_job_roles.delete_many({"_iter131_test": marker})
        await db.bb_job_openings.delete_many({"_iter131_test": marker})


@pytest.mark.asyncio
async def test_cannot_activate_form_when_role_inactive(db, mock_req):
    """Spec Case 1: form blocked when only the role is inactive."""
    import bb_modules
    marker = f"_iter131_dr_{uuid.uuid4().hex[:8]}"
    role_name = f"Iter131 RoleC1 {uuid.uuid4().hex[:6]}"
    await db.bb_job_roles.insert_one(
        {"name": role_name, "status": "inactive", "_iter131_test": marker}
    )
    op_id = (await db.bb_job_openings.insert_one(
        {"title": "Op", "job_role": role_name,
         "status": "active", "_iter131_test": marker}
    )).inserted_id
    form_id = (await db.bb_hiring_forms.insert_one(
        {"name": "Form", "job_role": role_name,
         "job_opening_id": str(op_id),
         "status": "inactive", "_iter131_test": marker}
    )).inserted_id
    try:
        with patch("bb_modules._require_auth", new=AsyncMock(return_value=None)):
            with pytest.raises(HTTPException) as exc:
                await bb_modules.activate_hiring_form(str(form_id), mock_req)
        assert exc.value.status_code == 409
        assert "Job Role is currently inactive" in exc.value.detail
    finally:
        await db.bb_job_roles.delete_many({"_iter131_test": marker})
        await db.bb_job_openings.delete_many({"_iter131_test": marker})
        await db.bb_hiring_forms.delete_many({"_iter131_test": marker})


@pytest.mark.asyncio
async def test_cannot_activate_form_when_opening_inactive(db, mock_req):
    """Spec Case 2: form blocked when only the opening is inactive."""
    import bb_modules
    marker = f"_iter131_do_{uuid.uuid4().hex[:8]}"
    role_name = f"Iter131 RoleC2 {uuid.uuid4().hex[:6]}"
    await db.bb_job_roles.insert_one(
        {"name": role_name, "status": "active", "_iter131_test": marker}
    )
    op_id = (await db.bb_job_openings.insert_one(
        {"title": "Op", "job_role": role_name,
         "status": "inactive", "_iter131_test": marker}
    )).inserted_id
    form_id = (await db.bb_hiring_forms.insert_one(
        {"name": "Form", "job_role": role_name,
         "job_opening_id": str(op_id),
         "status": "inactive", "_iter131_test": marker}
    )).inserted_id
    try:
        with patch("bb_modules._require_auth", new=AsyncMock(return_value=None)):
            with pytest.raises(HTTPException) as exc:
                await bb_modules.activate_hiring_form(str(form_id), mock_req)
        assert exc.value.status_code == 409
        assert "Job Opening is currently inactive" in exc.value.detail
        assert "Job Role is currently inactive" not in exc.value.detail
    finally:
        await db.bb_job_roles.delete_many({"_iter131_test": marker})
        await db.bb_job_openings.delete_many({"_iter131_test": marker})
        await db.bb_hiring_forms.delete_many({"_iter131_test": marker})


@pytest.mark.asyncio
async def test_cannot_activate_form_when_both_inactive(db, mock_req):
    """Spec Case 3: form blocked when BOTH are inactive — message
    enumerates both."""
    import bb_modules
    marker = f"_iter131_db_{uuid.uuid4().hex[:8]}"
    role_name = f"Iter131 RoleC3 {uuid.uuid4().hex[:6]}"
    await db.bb_job_roles.insert_one(
        {"name": role_name, "status": "inactive", "_iter131_test": marker}
    )
    op_id = (await db.bb_job_openings.insert_one(
        {"title": "Op", "job_role": role_name,
         "status": "inactive", "_iter131_test": marker}
    )).inserted_id
    form_id = (await db.bb_hiring_forms.insert_one(
        {"name": "Form", "job_role": role_name,
         "job_opening_id": str(op_id),
         "status": "inactive", "_iter131_test": marker}
    )).inserted_id
    try:
        with patch("bb_modules._require_auth", new=AsyncMock(return_value=None)):
            with pytest.raises(HTTPException) as exc:
                await bb_modules.activate_hiring_form(str(form_id), mock_req)
        assert exc.value.status_code == 409
        assert "Job Role and Job Opening" in exc.value.detail
    finally:
        await db.bb_job_roles.delete_many({"_iter131_test": marker})
        await db.bb_job_openings.delete_many({"_iter131_test": marker})
        await db.bb_hiring_forms.delete_many({"_iter131_test": marker})


@pytest.mark.asyncio
async def test_can_activate_form_when_both_active(db, mock_req):
    """Spec Case 4: both deps active → activation succeeds."""
    import bb_modules
    marker = f"_iter131_dok_{uuid.uuid4().hex[:8]}"
    role_name = f"Iter131 RoleC4 {uuid.uuid4().hex[:6]}"
    await db.bb_job_roles.insert_one(
        {"name": role_name, "status": "active", "_iter131_test": marker}
    )
    op_id = (await db.bb_job_openings.insert_one(
        {"title": "Op", "job_role": role_name,
         "status": "active", "_iter131_test": marker}
    )).inserted_id
    form_id = (await db.bb_hiring_forms.insert_one(
        {"name": "Form", "job_role": role_name,
         "job_opening_id": str(op_id),
         "status": "inactive", "_iter131_test": marker}
    )).inserted_id
    try:
        with patch("bb_modules._require_auth", new=AsyncMock(return_value=None)):
            res = await bb_modules.activate_hiring_form(str(form_id), mock_req)
        assert res["status"] == "active"
        assert (await db.bb_hiring_forms.find_one({"_id": form_id}))["status"] == "active"
    finally:
        await db.bb_job_roles.delete_many({"_iter131_test": marker})
        await db.bb_job_openings.delete_many({"_iter131_test": marker})
        await db.bb_hiring_forms.delete_many({"_iter131_test": marker})


# ─────────────────────── Issue 2 — Default Instruction Page ──────────────


def test_frontend_default_instruction_fallback_removed_role_gate():
    """`PublicRegistration.js` post-register branching must NOT gate the
    empty-content fallback on AI/ML role match — the AI/ML interstitial
    is the DEFAULT template and must show for any role when admin sets
    Show Information Page=Yes with empty content."""
    import pathlib
    src = pathlib.Path("/app/frontend/src/pages/PublicRegistration.js").read_text()
    # The post-register branching code must say "isShortlisted" without
    # also requiring "isAimlRole" in the SAME conditional.
    assert "isAimlRole" not in src.split("// AI & ML Info Page")[0], (
        "Empty-content fallback is still gated to AI/ML role only — "
        "non-AI/ML forms with empty instruction_content will silently "
        "skip the default Information Page."
    )


# ─────────────────────── Frontend dropdown audit ──────────────────────────


def test_frontend_dropdowns_use_active_only():
    """Every selection picker / filter that fetches job-roles or
    job-openings must include `active_only=true` so inactive entries
    disappear from the UI per spec."""
    import pathlib

    # Map: file → list of expected substrings that MUST be in the file.
    expected = {
        "/app/frontend/src/pages/JobOpenings.js": [
            "/api/bb/job-roles?active_only=true",
        ],
        "/app/frontend/src/pages/HiringForms.js": [
            "/api/bb/job-roles?active_only=true",
            "/api/bb/job-openings?active_only=true",
        ],
        "/app/frontend/src/pages/AttendedRoles.js": [
            "/api/bb/job-roles?active_only=true",
        ],
        "/app/frontend/src/pages/InterviewReports.js": [
            "/api/bb/job-roles?active_only=true",
        ],
        "/app/frontend/src/pages/Roles.js": [
            "/api/bb/job-roles?active_only=true",
        ],
        "/app/frontend/src/pages/MissingApplicants.js": [
            "/api/bb/job-roles?active_only=true",
        ],
    }
    for path, needles in expected.items():
        text = pathlib.Path(path).read_text()
        for n in needles:
            assert n in text, f"{path} missing active_only fetch for {n}"
