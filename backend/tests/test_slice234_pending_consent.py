"""Slice 2+3+4 regression tests. Isolated via mongomock_motor; no real DB / network."""
import asyncio
import os
import sys

import mongomock_motor
import pytest
from fastapi import HTTPException

sys.path.insert(0, '/app/backend')
from ai_calling import admin_auth as aa  # noqa: E402
from ai_calling import router as ai_router_mod, store  # noqa: E402

os.environ["AI_CALLING_ENABLED"] = "false"


class _Req:
    def __init__(self, headers=None):
        self.headers = {"X-CSRF-Intent": "ai-calling", **(headers or {})}


async def _fake_admin(_r): return "Admin User"
async def _fake_other(_r): return "Other Admin"


@pytest.fixture()
def db_():
    client = mongomock_motor.AsyncMongoMockClient()
    database = client["slice234_test"]
    store._state["db"] = database
    store._state["auth"] = _fake_admin
    ai_router_mod._state["db"] = database
    ai_router_mod._state["auth"] = _fake_admin
    yield database


def run(coro):
    return asyncio.run(coro)


# ---- Pending Authorization ----

def test_pending_excludes_past_and_opted_out(db_):
    async def go():
        from bson import ObjectId
        rids = []
        for name, idate, status, consent in [
            ("Future A", "2026-12-01", "booked", None),
            ("Past B", "2025-01-01", "booked", None),
            ("Future DNC", "2026-12-02", "booked", {"do_not_call": True}),
            ("Future Withdrawn", "2026-12-03", "booked", {"consent_status": "withdrawn"}),
            ("Future Cancelled", "2026-12-04", "cancelled", None),
        ]:
            oid = ObjectId()
            await db_.bb_registrations.insert_one({
                "_id": oid, "candidate_name": name, "job_role": "QA", "phone_e164": "+9199" + "00001" + str(len(rids)).zfill(3),
                "interview_date": idate, "interview_time": "15:00", "booking_status": status,
            })
            if consent:
                await db_.ai_candidate_consents.insert_one({"registration_id": str(oid), **consent})
            rids.append(str(oid))
        # Call the pure helper directly (endpoint signature uses FastAPI Query defaults).
        r = await aa._list_pending({"job_role": None, "date_from": None, "date_to": None}, 1, 50)
        names = [i["candidate_name"] for i in r["items"]]
        assert names == ["Future A"]  # only one eligible for review
    run(go())


def test_review_approve_requires_policy_and_evidence_never_writes_consent(db_):
    async def go():
        from bson import ObjectId
        oid = ObjectId()
        await db_.bb_registrations.insert_one({"_id": oid, "candidate_name": "X", "interview_date": "2026-12-01",
                                               "interview_time": "15:00", "booking_status": "booked"})
        body = aa.ReviewBody(registration_ids=[str(oid)], purposes=["interview_confirmation"],
                             decision="approve", reason="unit")
        with pytest.raises(HTTPException) as e:
            await aa.bulk_review(body, _Req())
        assert e.value.status_code == 400
        # provide policy + evidence → success
        body.policy_id = "P-001"; body.evidence_ref = "E-001"
        r = await aa.bulk_review(body, _Req())
        assert r["approved"] == [str(oid)]
        # ai_candidate_consents MUST NOT have been touched
        assert await db_.ai_candidate_consents.count_documents({"registration_id": str(oid)}) == 0
        # admin collections populated
        assert await db_.ai_admin_authorizations.count_documents({"registration_id": str(oid)}) == 1
        assert await db_.ai_admin_authorization_audit.count_documents({"registration_id": str(oid)}) == 1
    run(go())


def test_review_skips_dnc_and_past_bookings(db_):
    async def go():
        from bson import ObjectId
        past = ObjectId(); dnc = ObjectId()
        await db_.bb_registrations.insert_many([
            {"_id": past, "candidate_name": "Past", "interview_date": "2025-01-01",
             "interview_time": "10:00", "booking_status": "booked"},
            {"_id": dnc, "candidate_name": "DNC", "interview_date": "2026-12-01",
             "interview_time": "10:00", "booking_status": "booked"},
        ])
        await db_.ai_candidate_consents.insert_one({"registration_id": str(dnc), "do_not_call": True})
        body = aa.ReviewBody(registration_ids=[str(past), str(dnc)], purposes=["interview_confirmation"],
                             decision="approve", policy_id="P", evidence_ref="E")
        r = await aa.bulk_review(body, _Req())
        assert r["approved"] == []
        reasons = {s["id"]: s["reason"] for s in r["skipped"]}
        assert reasons[str(past)] == "booking_no_longer_valid"
        assert reasons[str(dnc)] == "candidate_opt_out_or_dnc"
        # Audit trail still records the attempt? No — we only audit decisions we acted on. Verify:
        assert await db_.ai_admin_authorization_audit.count_documents({"registration_id": str(past)}) == 0
    run(go())


# ---- Consent editor publish authorization (RBAC + top-level admin) ----

def test_consent_publish_only_top_level_admin(db_):
    async def go():
        # Save a valid draft first.
        await aa.save_draft(aa.ConsentDraftBody(title="T", text="x" * 100), _Req())
        # Correct admin succeeds with correct confirmation.
        r = await aa.publish_version(aa.ConsentPublishBody(confirmation="PUBLISH CONSENT VERSION"), _Req())
        assert r["published"] is True
        v1 = r["version_id"]
        # Wrong admin principal is denied.
        store._state["auth"] = _fake_other
        ai_router_mod._state["auth"] = _fake_other
        with pytest.raises(HTTPException) as e:
            await aa.publish_version(aa.ConsentPublishBody(confirmation="PUBLISH CONSENT VERSION"), _Req())
        assert e.value.status_code == 403
        # Correct admin + wrong confirmation also rejected.
        store._state["auth"] = _fake_admin
        ai_router_mod._state["auth"] = _fake_admin
        with pytest.raises(HTTPException) as e:
            await aa.publish_version(aa.ConsentPublishBody(confirmation="nope"), _Req())
        assert e.value.status_code == 400
        # Published versions are immutable — one more publish adds a new row, old row intact.
        await aa.save_draft(aa.ConsentDraftBody(title="T2", text="y" * 100), _Req())
        r2 = await aa.publish_version(aa.ConsentPublishBody(confirmation="PUBLISH CONSENT VERSION"), _Req())
        assert r2["version_id"] != v1
        assert await db_.ai_consent_versions.count_documents({}) == 2
    run(go())


def test_consent_draft_validation(db_):
    async def go():
        with pytest.raises(HTTPException) as e:
            await aa.save_draft(aa.ConsentDraftBody(title="", text="x" * 100), _Req())
        assert e.value.status_code == 400
        with pytest.raises(HTTPException) as e:
            await aa.save_draft(aa.ConsentDraftBody(title="T", text="short"), _Req())
        assert e.value.status_code == 400
        # Valid
        await aa.save_draft(aa.ConsentDraftBody(title="T", text="x" * 100), _Req())
    run(go())


# ---- Capacity summary + preview ----

def test_capacity_summary_shape(db_):
    async def go():
        await db_.ai_call_settings.update_one({"_id": "global"},
            {"$set": {**store.SETTINGS_DEFAULTS}}, upsert=True)
        r = await aa.capacity_summary(_Req())
        assert r["live"]["effective_daily_maximum"] == min(
            r["live"]["configured_daily_maximum"], r["live"]["pilot_daily_cap"])
        assert "pilot" in r["live"]["explanation"].lower()
    run(go())


def test_preview_scenarios_both_purposes(db_):
    async def go():
        r = await aa.preview_scenarios(_Req())
        assert len(r["interview_confirmation"]) >= 5
        missed = r["missed_interview_followup"]
        otp_states = {s["otp_interpretation"] for s in missed}
        # All four OTP interpretations present per spec
        assert {"unverified", "verified", "missing_blocked", "verified_just_now"}.issubset(otp_states)
        r2 = await aa.preview_scenarios(_Req(), purpose="missed_interview_followup")
        assert r2["purpose"] == "missed_interview_followup"
    run(go())
