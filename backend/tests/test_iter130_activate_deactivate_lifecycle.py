"""iter130 — Activate / Deactivate Lifecycle for Job Roles, Job
Openings, and Hiring Forms.

Validates all 6 user-spec scenarios end-to-end via direct calls to the
endpoint functions (no HTTP round-trip needed — auth is mocked).

Critical applicant-protection assertion: deactivation MUST NOT modify
any internal applicant-processing collection (pipeline_data,
bb_applicant_updates, registered_candidates, etc.). The flag is
consulted only at the public-facing entry points.
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
from fastapi import Request


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


# ─────────────────────── Migration ────────────────────────────────────────


@pytest.mark.asyncio
async def test_migration_backfills_default_active(db):
    """Existing rows with no `status` field must be backfilled to
    `active`. Idempotent — running it twice yields zero further
    modifications."""
    import bb_modules
    # Seed a row without status.
    marker = f"_iter130_mig_{uuid.uuid4().hex[:8]}"
    await db.bb_job_roles.insert_one({"name": marker, "_iter130_test": marker})
    try:
        await bb_modules._ensure_status_indexes_and_backfill()
        doc = await db.bb_job_roles.find_one({"_iter130_test": marker})
        assert doc.get("status") == "active"
    finally:
        await db.bb_job_roles.delete_many({"_iter130_test": marker})


# ─────────────────────── Scenario 1 — Job Role cascade ────────────────────


@pytest.mark.asyncio
async def test_scenario1_deactivate_job_role_cascades(db, mock_req):
    """Spec Scenario 1: deactivating a Job Role cascade-deactivates
    every linked Job Opening AND every linked Hiring Form."""
    import bb_modules
    marker = f"_iter130_s1_{uuid.uuid4().hex[:8]}"
    role_name = f"Iter130 Role {uuid.uuid4().hex[:6]}"

    role_id = (await db.bb_job_roles.insert_one(
        {"name": role_name, "status": "active", "_iter130_test": marker}
    )).inserted_id
    op_id = (await db.bb_job_openings.insert_one(
        {"title": "Iter130 Op", "job_role": role_name,
         "status": "active", "_iter130_test": marker}
    )).inserted_id
    form_id = (await db.bb_hiring_forms.insert_one(
        {"name": "Iter130 Form", "job_role": role_name,
         "job_opening_id": str(op_id),
         "status": "active", "_iter130_test": marker}
    )).inserted_id

    try:
        with patch("bb_modules._require_auth", new=AsyncMock(return_value=None)):
            res = await bb_modules.deactivate_job_role(str(role_id), mock_req)
        assert res["success"] is True
        assert res["status"] == "inactive"
        assert res["cascade"]["openings_affected"] == 1
        assert res["cascade"]["forms_affected"] == 1

        # All three rows must be inactive now.
        assert (await db.bb_job_roles.find_one({"_id": role_id}))["status"] == "inactive"
        op_doc = await db.bb_job_openings.find_one({"_id": op_id})
        assert op_doc["status"] == "inactive"
        assert op_doc["deactivated_by"] == "job_role"
        form_doc = await db.bb_hiring_forms.find_one({"_id": form_id})
        assert form_doc["status"] == "inactive"
        assert form_doc["deactivated_by"] == "job_role"

    finally:
        await db.bb_job_roles.delete_many({"_iter130_test": marker})
        await db.bb_job_openings.delete_many({"_iter130_test": marker})
        await db.bb_hiring_forms.delete_many({"_iter130_test": marker})


# ─────────────────────── Scenario 2 — Reactivate role no cascade ──────────


@pytest.mark.asyncio
async def test_scenario2_reactivate_job_role_does_not_cascade(db, mock_req):
    """Spec Scenario 2: re-activating a Job Role flips ONLY the role.
    Openings and forms remain inactive until manually activated."""
    import bb_modules
    marker = f"_iter130_s2_{uuid.uuid4().hex[:8]}"
    role_name = f"Iter130 Role S2 {uuid.uuid4().hex[:6]}"

    role_id = (await db.bb_job_roles.insert_one(
        {"name": role_name, "status": "inactive",
         "deactivated_by": "manual", "_iter130_test": marker}
    )).inserted_id
    op_id = (await db.bb_job_openings.insert_one(
        {"title": "Op S2", "job_role": role_name, "status": "inactive",
         "deactivated_by": "job_role", "_iter130_test": marker}
    )).inserted_id
    form_id = (await db.bb_hiring_forms.insert_one(
        {"name": "Form S2", "job_role": role_name, "status": "inactive",
         "deactivated_by": "job_role", "_iter130_test": marker}
    )).inserted_id

    try:
        with patch("bb_modules._require_auth", new=AsyncMock(return_value=None)):
            res = await bb_modules.activate_job_role(str(role_id), mock_req)
        assert res["status"] == "active"
        # Role flipped to active.
        assert (await db.bb_job_roles.find_one({"_id": role_id}))["status"] == "active"
        # Openings + forms MUST stay inactive.
        assert (await db.bb_job_openings.find_one({"_id": op_id}))["status"] == "inactive"
        assert (await db.bb_hiring_forms.find_one({"_id": form_id}))["status"] == "inactive"

    finally:
        await db.bb_job_roles.delete_many({"_iter130_test": marker})
        await db.bb_job_openings.delete_many({"_iter130_test": marker})
        await db.bb_hiring_forms.delete_many({"_iter130_test": marker})


# ─────────────────────── Scenario 3 — Job Opening cascade ─────────────────


@pytest.mark.asyncio
async def test_scenario3_deactivate_opening_cascades_only_forms(db, mock_req):
    """Spec Scenario 3: deactivating a Job Opening cascade-deactivates
    every linked Hiring Form but leaves the Job Role untouched."""
    import bb_modules
    marker = f"_iter130_s3_{uuid.uuid4().hex[:8]}"
    role_name = f"Iter130 Role S3 {uuid.uuid4().hex[:6]}"

    role_id = (await db.bb_job_roles.insert_one(
        {"name": role_name, "status": "active", "_iter130_test": marker}
    )).inserted_id
    op_id = (await db.bb_job_openings.insert_one(
        {"title": "Op S3", "job_role": role_name, "status": "active",
         "_iter130_test": marker}
    )).inserted_id
    form_id = (await db.bb_hiring_forms.insert_one(
        {"name": "Form S3", "job_role": role_name,
         "job_opening_id": str(op_id),
         "status": "active", "_iter130_test": marker}
    )).inserted_id

    try:
        with patch("bb_modules._require_auth", new=AsyncMock(return_value=None)):
            res = await bb_modules.deactivate_job_opening(str(op_id), mock_req)
        assert res["cascade"]["forms_affected"] == 1
        assert (await db.bb_job_openings.find_one({"_id": op_id}))["status"] == "inactive"
        form_doc = await db.bb_hiring_forms.find_one({"_id": form_id})
        assert form_doc["status"] == "inactive"
        assert form_doc["deactivated_by"] == "job_opening"
        # Role MUST stay active.
        assert (await db.bb_job_roles.find_one({"_id": role_id}))["status"] == "active"

    finally:
        await db.bb_job_roles.delete_many({"_iter130_test": marker})
        await db.bb_job_openings.delete_many({"_iter130_test": marker})
        await db.bb_hiring_forms.delete_many({"_iter130_test": marker})


# ─────────────────────── Scenario 4 — Reactivate opening no cascade ───────


@pytest.mark.asyncio
async def test_scenario4_reactivate_opening_does_not_cascade(db, mock_req):
    import bb_modules
    marker = f"_iter130_s4_{uuid.uuid4().hex[:8]}"

    op_id = (await db.bb_job_openings.insert_one(
        {"title": "Op S4", "status": "inactive",
         "deactivated_by": "manual", "_iter130_test": marker}
    )).inserted_id
    form_id = (await db.bb_hiring_forms.insert_one(
        {"name": "Form S4", "job_opening_id": str(op_id),
         "status": "inactive", "deactivated_by": "job_opening",
         "_iter130_test": marker}
    )).inserted_id

    try:
        with patch("bb_modules._require_auth", new=AsyncMock(return_value=None)):
            await bb_modules.activate_job_opening(str(op_id), mock_req)
        assert (await db.bb_job_openings.find_one({"_id": op_id}))["status"] == "active"
        assert (await db.bb_hiring_forms.find_one({"_id": form_id}))["status"] == "inactive"

    finally:
        await db.bb_job_openings.delete_many({"_iter130_test": marker})
        await db.bb_hiring_forms.delete_many({"_iter130_test": marker})


# ─────────────────────── Scenario 5 — Form standalone ─────────────────────


@pytest.mark.asyncio
async def test_scenario5_form_lifecycle_is_standalone(db, mock_req):
    import bb_modules
    marker = f"_iter130_s5_{uuid.uuid4().hex[:8]}"
    role_name = f"Iter130 Role S5 {uuid.uuid4().hex[:6]}"

    role_id = (await db.bb_job_roles.insert_one(
        {"name": role_name, "status": "active", "_iter130_test": marker}
    )).inserted_id
    op_id = (await db.bb_job_openings.insert_one(
        {"title": "Op S5", "job_role": role_name, "status": "active",
         "_iter130_test": marker}
    )).inserted_id
    form_id = (await db.bb_hiring_forms.insert_one(
        {"name": "Form S5", "job_role": role_name,
         "job_opening_id": str(op_id),
         "status": "active", "_iter130_test": marker}
    )).inserted_id

    try:
        with patch("bb_modules._require_auth", new=AsyncMock(return_value=None)):
            res = await bb_modules.deactivate_hiring_form(str(form_id), mock_req)
        assert res["cascade"]["openings_affected"] == 0
        assert res["cascade"]["forms_affected"] == 0
        assert (await db.bb_hiring_forms.find_one({"_id": form_id}))["status"] == "inactive"
        # Neither role nor opening must move.
        assert (await db.bb_job_openings.find_one({"_id": op_id}))["status"] == "active"
        assert (await db.bb_job_roles.find_one({"_id": role_id}))["status"] == "active"

    finally:
        await db.bb_job_roles.delete_many({"_iter130_test": marker})
        await db.bb_job_openings.delete_many({"_iter130_test": marker})
        await db.bb_hiring_forms.delete_many({"_iter130_test": marker})


# ─────────────────────── Scenario 6 — Applicant protection ────────────────


@pytest.mark.asyncio
async def test_scenario6_existing_applicant_unaffected_by_role_deactivation(db, mock_req):
    """Spec Scenario 6 (CRITICAL): an already-registered applicant for
    a Job Role MUST be totally untouched when that role is deactivated.
    The lifecycle endpoints must not write to pipeline_data,
    bb_applicant_updates, or registered_candidates."""
    import bb_modules
    marker = f"_iter130_s6_{uuid.uuid4().hex[:8]}"
    role_name = f"Iter130 Role S6 {uuid.uuid4().hex[:6]}"

    role_id = (await db.bb_job_roles.insert_one(
        {"name": role_name, "status": "active", "_iter130_test": marker}
    )).inserted_id
    applicant_email = f"iter130s6-{uuid.uuid4().hex[:8]}@example.invalid"
    await db.pipeline_data.insert_one({
        "email": applicant_email, "phone": "9000130006",
        "job_role": role_name, "name": "S6 Applicant",
        "schedule_date": "2026-06-15", "otp_verified": "1",
        "_iter130_test": marker,
    })
    await db.bb_applicant_updates.insert_one({
        "email": applicant_email, "phone": "9000130006",
        "status": "Shortlisted",
        "scores": [{"round_name": "Round 1", "score": 8.0}],
        "_iter130_test": marker,
    })

    try:
        snap_pd = await db.pipeline_data.find_one({"email": applicant_email})
        snap_upd = await db.bb_applicant_updates.find_one({"email": applicant_email})

        with patch("bb_modules._require_auth", new=AsyncMock(return_value=None)):
            await bb_modules.deactivate_job_role(str(role_id), mock_req)

        # Snapshot equality on every field except _id.
        after_pd = await db.pipeline_data.find_one({"email": applicant_email})
        after_upd = await db.bb_applicant_updates.find_one({"email": applicant_email})
        snap_pd.pop("_id", None); after_pd.pop("_id", None)
        snap_upd.pop("_id", None); after_upd.pop("_id", None)
        assert snap_pd == after_pd, "pipeline_data was modified by role deactivation"
        assert snap_upd == after_upd, "bb_applicant_updates was modified"

    finally:
        await db.bb_job_roles.delete_many({"_iter130_test": marker})
        await db.pipeline_data.delete_many({"_iter130_test": marker})
        await db.bb_applicant_updates.delete_many({"_iter130_test": marker})


# ─────────────────────── Public endpoint short-circuits ───────────────────


@pytest.mark.asyncio
async def test_public_job_opening_returns_inactive_payload(db):
    """Public endpoint must return `inactive=True` + the spec-mandated
    title/message strings when the opening is deactivated."""
    import bb_modules
    marker = f"_iter130_pub_op_{uuid.uuid4().hex[:8]}"

    op_id = (await db.bb_job_openings.insert_one(
        {"title": "Inactive Op", "slug": f"inactive-op-{uuid.uuid4().hex[:6]}",
         "status": "inactive", "_iter130_test": marker}
    )).inserted_id
    try:
        res = await bb_modules.get_public_job_opening(str(op_id))
        assert res.get("inactive") is True
        assert res["title"] == "Job Opening Unavailable"
        assert "no longer accepting applications" in res["message"]

    finally:
        await db.bb_job_openings.delete_many({"_iter130_test": marker})


@pytest.mark.asyncio
async def test_public_hiring_form_returns_inactive_payload(db):
    import bb_modules
    marker = f"_iter130_pub_form_{uuid.uuid4().hex[:8]}"

    form_id = (await db.bb_hiring_forms.insert_one(
        {"name": "Inactive Form", "slug": f"inactive-form-{uuid.uuid4().hex[:6]}",
         "status": "inactive", "_iter130_test": marker}
    )).inserted_id

    try:
        res = await bb_modules.get_public_form(str(form_id))
        assert res.get("inactive") is True
        assert res["title"] == "Applications Currently Closed"
        assert "no longer being accepted" in res["message"]
        assert "careers page" in res["message"]

    finally:
        await db.bb_hiring_forms.delete_many({"_iter130_test": marker})


# ─────────────────────── Cascade preview counts ──────────────────────────


@pytest.mark.asyncio
async def test_cascade_preview_counts_for_role(db, mock_req):
    """`/job-roles/{id}/cascade-preview` returns the count of active
    openings + forms that WOULD be deactivated."""
    import bb_modules
    marker = f"_iter130_prev_{uuid.uuid4().hex[:8]}"
    role_name = f"Iter130 Preview {uuid.uuid4().hex[:6]}"

    role_id = (await db.bb_job_roles.insert_one(
        {"name": role_name, "status": "active", "_iter130_test": marker}
    )).inserted_id
    await db.bb_job_openings.insert_many([
        {"title": f"PrevOp{i}", "job_role": role_name,
         "status": "active", "_iter130_test": marker}
        for i in range(3)
    ])
    await db.bb_hiring_forms.insert_many([
        {"name": f"PrevForm{i}", "job_role": role_name,
         "status": "active", "_iter130_test": marker}
        for i in range(2)
    ])
    # One already-inactive row that should NOT be counted.
    await db.bb_job_openings.insert_one(
        {"title": "PrevOpDead", "job_role": role_name,
         "status": "inactive", "_iter130_test": marker}
    )

    try:
        with patch("bb_modules._require_auth", new=AsyncMock(return_value=None)):
            res = await bb_modules.cascade_preview_job_role(str(role_id), mock_req)
        assert res["openings"] == 3
        assert res["forms"] == 2
        assert res["status"] == "active"

    finally:
        await db.bb_job_roles.delete_many({"_iter130_test": marker})
        await db.bb_job_openings.delete_many({"_iter130_test": marker})
        await db.bb_hiring_forms.delete_many({"_iter130_test": marker})
