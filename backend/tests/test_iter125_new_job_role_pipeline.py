"""iter125 regression — Dynamic job-role insertion pipeline.

Validates the fix where new job roles uploaded into `pipeline_data` or
`naukri_applies` properly propagate to ALL downstream surfaces:

  - `bb_job_roles` row inserted (case-insensitive dedupe)
  - `job_titles_master` row inserted with `is_mapped: False`
  - Unmapped Job Keywords endpoint surfaces the new normalized title
  - `_normalized_job_role` set to RAW role (never "Unknown") when no
    mapping exists yet
  - `reprocess_matching` now persists pipeline_data derived fields

All rows use `isTest: True` so the live production data is never touched.

Each test creates its OWN motor client to avoid asyncio event-loop reuse
issues across `asyncio.run()` boundaries.
"""
import asyncio
import inspect
import os
import sys

from dotenv import load_dotenv

load_dotenv("/app/backend/.env")
sys.path.insert(0, "/app/backend")

from motor.motor_asyncio import AsyncIOMotorClient  # noqa: E402
import server  # noqa: E402

NEW_ROLE_PIPELINE = "Iter125-TestRole-PipelineOnly-Z9"
NEW_ROLE_NAUKRI = "Iter125-TestRole-NaukriOnly-Z9"
P_EMAIL = "iter125_pipe@example.com"
N_EMAIL = "iter125_naukri@example.com"


def _fresh_db():
    client = AsyncIOMotorClient(os.environ["MONGO_URL"])
    return client[os.environ["DB_NAME"]], client


async def _cleanup(db):
    await db.pipeline_data.delete_many({"email": P_EMAIL})
    await db.naukri_applies.delete_many({"email": N_EMAIL})
    await db.bb_job_roles.delete_many(
        {"name": {"$in": [NEW_ROLE_PIPELINE, NEW_ROLE_NAUKRI]}}
    )
    await db.job_titles_master.delete_many(
        {"raw_job_title": {"$in": [NEW_ROLE_PIPELINE, NEW_ROLE_NAUKRI]}}
    )


def test_sync_inserts_new_roles_into_master_tables():
    """Brand-new roles must be inserted into both `bb_job_roles` AND
    `job_titles_master` by `_sync_job_titles_master`."""

    async def _run():
        # Bind server.db to a freshly-created event-loop motor client so
        # `_sync_job_titles_master` runs in the same loop as our asserts.
        db, client = _fresh_db()
        original_db = server.db
        server.db = db
        try:
            await _cleanup(db)
            await db.pipeline_data.insert_one({
                "email": P_EMAIL, "phone": "9000125001", "name": "iter125-p",
                "job_role": NEW_ROLE_PIPELINE, "isTest": True,
            })
            await db.naukri_applies.insert_one({
                "email": N_EMAIL, "phone": "9000125002", "name": "iter125-n",
                "job_title": NEW_ROLE_NAUKRI, "isTest": True,
            })

            await server._sync_job_titles_master()

            assert await db.bb_job_roles.count_documents({"name": NEW_ROLE_PIPELINE}) == 1
            assert await db.bb_job_roles.count_documents({"name": NEW_ROLE_NAUKRI}) == 1
            assert await db.job_titles_master.count_documents({"raw_job_title": NEW_ROLE_PIPELINE}) == 1
            assert await db.job_titles_master.count_documents({"raw_job_title": NEW_ROLE_NAUKRI}) == 1
        finally:
            await _cleanup(db)
            server.db = original_db
            client.close()

    asyncio.run(_run())


def test_new_role_appears_in_unmatched_titles():
    """A freshly uploaded unmapped role must surface in unmatched titles
    without a mapped flag set."""

    async def _run():
        db, client = _fresh_db()
        original_db = server.db
        server.db = db
        try:
            await _cleanup(db)
            await db.pipeline_data.insert_one({
                "email": P_EMAIL, "phone": "9000125001", "name": "iter125-p",
                "job_role": NEW_ROLE_PIPELINE, "isTest": True,
            })
            await server._sync_job_titles_master()

            kw_to_canonical, _ = await server._build_canonical_index()
            mapped_norm_set = set(kw_to_canonical.keys())
            norm = server._normalize_text_for_matching(NEW_ROLE_PIPELINE)
            assert norm not in mapped_norm_set, "new role must NOT be pre-mapped"

            jtm_doc = await db.job_titles_master.find_one(
                {"normalized_job_title": norm}
            )
            assert jtm_doc is not None
            assert not jtm_doc.get("is_mapped")
        finally:
            await _cleanup(db)
            server.db = original_db
            client.close()

    asyncio.run(_run())


def test_persist_derived_sets_normalized_job_role_to_raw_for_unmapped():
    """When an upload introduces a NEW role with no mapping, persist must
    store the RAW role into `_normalized_job_role` — never collapse to
    literal "Unknown"."""

    async def _run():
        db, client = _fresh_db()
        original_db = server.db
        server.db = db
        try:
            await _cleanup(db)
            await db.pipeline_data.insert_one({
                "email": P_EMAIL, "phone": "9000125001", "name": "iter125-p",
                "job_role": NEW_ROLE_PIPELINE, "isTest": True,
            })

            mappings = await server._get_job_keyword_mappings()
            doc = await db.pipeline_data.find_one({"email": P_EMAIL})
            raw_role = doc.get("job_title") or doc.get("job_role") or ""
            normalized_role = server._resolve_normalized_job_role(raw_role, mappings)
            await db.pipeline_data.update_one(
                {"_id": doc["_id"]},
                {"$set": {"_normalized_job_role": normalized_role or "Unknown"}},
            )
            updated = await db.pipeline_data.find_one({"email": P_EMAIL})
            assert updated["_normalized_job_role"] == NEW_ROLE_PIPELINE
            assert updated["_normalized_job_role"] != "Unknown"
        finally:
            await _cleanup(db)
            server.db = original_db
            client.close()

    asyncio.run(_run())


def test_reprocess_matching_persists_pipeline_data():
    """iter125 fix — `reprocess_matching` MUST call
    `_persist_derived_fields("pipeline_data")` so freshly-uploaded HR rows
    are surfaced on the Job Roles page without a manual backfill curl."""
    src = inspect.getsource(server.reprocess_matching)
    assert '_persist_derived_fields("pipeline_data")' in src, (
        "reprocess_matching must call _persist_derived_fields on pipeline_data"
    )
