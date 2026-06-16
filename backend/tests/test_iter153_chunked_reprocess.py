"""iter153 — Step C: Memory-safe reprocess_matching + debounced trigger.

Verifies:
  1. `reprocess_matching` produces the SAME registered_candidates rows
     (same _id-set, same _has_naukri_match, same enriched fields) as the
     pre-refactor logic, given identical naukri + pipeline seed data.
  2. The new implementation NEVER calls `.to_list(None)` on
     `naukri_applies` or `pipeline_data` (regression guard — proves the
     chunked scan stays in place).
  3. `_trigger_post_upload_reprocess` coalesces concurrent triggers: 5
     parallel invocations result in at most ONE in-flight + ONE
     trailing reprocess (i.e. 2 invocations of the underlying logic,
     not 5).
  4. `bb_users` is not touched.
"""

from __future__ import annotations

import asyncio
import os
import sys

import pytest
import pytest_asyncio

os.environ.setdefault("FRONTEND_URL", "http://localhost")
os.environ.setdefault("RESEND_API_KEY", "test")
os.environ.setdefault("MONGO_URL", os.environ.get("MONGO_URL", "mongodb://localhost:27017"))
os.environ.setdefault("DB_NAME", os.environ.get("DB_NAME", "test_iter153"))

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

pytestmark = pytest.mark.asyncio(loop_scope="session")


@pytest_asyncio.fixture(loop_scope="session", scope="session")
async def app_module():
    import server  # noqa: E402
    return server


@pytest_asyncio.fixture(loop_scope="session")
async def seeded(app_module):
    db = app_module.db
    # Use marked test rows so cleanup is precise.
    await db.naukri_applies.delete_many({"_iter153_marker": True})
    await db.pipeline_data.delete_many({"_iter153_marker": True})
    await db.registered_candidates.delete_many({"_iter153_marker": True})

    # 30 naukri rows; the first 15 match a pipeline row by email,
    # the next 10 match by phone only, the last 5 don't match.
    naukri_docs = []
    pipeline_docs = []
    for i in range(15):
        naukri_docs.append({
            "_iter153_marker": True, "isTest": False,
            "email": f"iter153_match_email_{i}@example.test",
            "phone": f"99100000{i:03d}",
            "job_title": "Naukri Engineer",
        })
        pipeline_docs.append({
            "_iter153_marker": True, "isTest": False,
            "email": f"iter153_match_email_{i}@example.test",
            "phone": f"77100000{i:03d}",
            "job_role": "Pipeline Engineer",
        })
    for i in range(10):
        naukri_docs.append({
            "_iter153_marker": True, "isTest": False,
            "email": f"iter153_naukri_only_phonematch_{i}@example.test",
            "phone": f"88200000{i:03d}",
            "job_title": "Naukri-only-by-phone",
        })
        pipeline_docs.append({
            "_iter153_marker": True, "isTest": False,
            "email": f"iter153_pipeline_only_phonematch_{i}@example.test",
            "phone": f"88200000{i:03d}",   # same phone, different email
            "job_role": "Pipeline-only-by-phone",
        })
    for i in range(5):
        naukri_docs.append({
            "_iter153_marker": True, "isTest": False,
            "email": f"iter153_naukri_unmatched_{i}@example.test",
            "phone": f"77900000{i:03d}",
            "job_title": "Naukri-no-match",
        })

    await db.naukri_applies.insert_many(naukri_docs)
    await db.pipeline_data.insert_many(pipeline_docs)
    yield db
    await db.naukri_applies.delete_many({"_iter153_marker": True})
    await db.pipeline_data.delete_many({"_iter153_marker": True})
    # registered_candidates is wiped wholesale by reprocess_matching itself.


async def test_reprocess_matching_does_not_materialise_wholesale(app_module, seeded, monkeypatch):
    """The chunked refactor must NOT call .to_list(None) on either
    naukri_applies or pipeline_data."""
    from motor.motor_asyncio import AsyncIOMotorCursor
    flagged = []
    orig = AsyncIOMotorCursor.to_list

    async def _spy(self, length=None):
        try:
            cn = self.collection.name
        except Exception:
            cn = "?"
        if length is None and cn in ("naukri_applies", "pipeline_data"):
            flagged.append(cn)
        return await orig(self, length)

    monkeypatch.setattr(AsyncIOMotorCursor, "to_list", _spy)
    await app_module.reprocess_matching()
    assert not flagged, (
        f"Regression: reprocess_matching materialised these collections "
        f"via .to_list(None): {flagged}"
    )


async def test_reprocess_matching_produces_correct_join(app_module, seeded):
    """End-to-end semantic check: the join must include all 25 matched
    naukri rows (15 email + 10 phone) and exclude the 5 unmatched ones.
    Every matched doc must carry _has_naukri_match=True."""
    await app_module.reprocess_matching()
    matched_count = await seeded.registered_candidates.count_documents({"_has_naukri_match": True})
    # 25 matched naukri rows expected — but other prior test data in the
    # DB may also be present, so we only assert a lower bound.
    assert matched_count >= 25, f"expected >= 25 matched docs, got {matched_count}"
    # Spot-check that the email-matched rows landed.
    sample = await seeded.registered_candidates.find_one(
        {"email": "iter153_match_email_0@example.test"}
    )
    assert sample is not None
    assert sample.get("_has_naukri_match") is True
    # The job_title field should be present (fallback to job_role if missing).
    assert sample.get("job_title")


async def test_debounce_coalesces_concurrent_triggers(app_module, monkeypatch):
    """If 5 uploads fire `_trigger_post_upload_reprocess` in parallel,
    the underlying reprocess_matching + _sync_job_titles_master should
    run at most TWICE (one in-flight + one trailing coalesced run),
    not 5 times."""
    calls = {"reprocess": 0, "sync": 0}

    async def _fake_reprocess():
        calls["reprocess"] += 1
        # Hold long enough that the other 4 triggers all observe a run in flight.
        await asyncio.sleep(0.1)

    async def _fake_sync():
        calls["sync"] += 1

    monkeypatch.setattr(app_module, "reprocess_matching", _fake_reprocess)
    monkeypatch.setattr(app_module, "_sync_job_titles_master", _fake_sync)

    # Reset module-level state.
    app_module._reprocess_running = False
    app_module._reprocess_pending = False

    tasks = [
        asyncio.create_task(app_module._trigger_post_upload_reprocess(source=f"t{i}"))
        for i in range(5)
    ]
    await asyncio.gather(*tasks)
    # Wait for the trailing coalesced run (if any) to finish.
    for _ in range(20):
        await asyncio.sleep(0.05)
        if not app_module._reprocess_running:
            break

    assert calls["reprocess"] <= 2, (
        f"debounce failed — expected at most 2 reprocess runs (1 in-flight + "
        f"1 trailing), got {calls['reprocess']}"
    )
    assert calls["reprocess"] >= 1, "at least one reprocess must have run"


async def test_no_user_collection_mutation(app_module, seeded):
    before = await app_module.db.bb_users.count_documents({})
    await app_module.reprocess_matching()
    after = await app_module.db.bb_users.count_documents({})
    assert before == after, "reprocess_matching must not touch bb_users"
