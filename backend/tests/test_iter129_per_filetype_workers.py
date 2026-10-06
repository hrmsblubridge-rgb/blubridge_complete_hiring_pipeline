"""iter129 — Per-file-type concurrent queue workers.

User-reported: naukri bulk uploads sat at `queued_local` forever while
pipeline uploads processed fine. Root cause: single FIFO worker was
busy on pipeline files queued seconds before the naukri file. Worker
was healthy; queue was just FIFO single-threaded → naukri waited
behind every pipeline file in line.

Fix: launch one worker per file_type (naukri, pipeline, score) so each
queue drains in parallel. The user's naukri file would have started
processing immediately even with 4 pipeline files queued ahead.
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

from motor.motor_asyncio import AsyncIOMotorClient


@pytest.fixture
def db():
    client = AsyncIOMotorClient(os.environ["MONGO_URL"])
    return client[os.environ["DB_NAME"]]


# ─────────────────────── Source-code guards ──────────────────────────────


def test_worker_accepts_file_type_scope_parameter():
    """`_bg_queue_worker` must accept a `file_type_scope` kwarg so
    one worker can be launched per file_type."""
    import server
    sig = inspect.signature(server._bg_queue_worker)
    assert "file_type_scope" in sig.parameters
    p = sig.parameters["file_type_scope"]
    # Default must be None so legacy callers continue to work.
    assert p.default is None


def test_worker_registry_is_a_set():
    """The `_worker_running` registry must be a set (one entry per
    scope), not the legacy single boolean."""
    import server
    assert isinstance(server._worker_running, set)


def test_worker_claim_filter_honors_file_type_scope():
    """When `file_type_scope` is given, the claim filter must constrain
    to rows whose `file_type` OR legacy `upload_type` matches."""
    import server
    src = inspect.getsource(server._bg_queue_worker)
    assert 'claim_filter["$and"]' in src
    assert '"file_type": file_type_scope' in src
    assert '"upload_type": file_type_scope' in src


def test_startup_launches_one_worker_per_file_type():
    """`startup_event` must spawn one worker per known file_type."""
    import server
    src = inspect.getsource(server.startup_event)
    # Must iterate over the file_type tuple and call _bg_queue_worker
    # with each scope.
    assert '("naukri", "pipeline", "score")' in src
    assert "file_type_scope=_scope" in src


def test_worker_logs_include_scope():
    """Start + stop log lines must surface the scope so operators can
    distinguish each worker in production logs."""
    import server
    src = inspect.getsource(server._bg_queue_worker)
    assert 'scope={scope_key!r}' in src


# ─────────────────────── Functional behaviour ────────────────────────────


@pytest.mark.asyncio
async def test_typed_worker_filter_excludes_other_types(db):
    """A naukri-scoped claim filter must NOT match a pipeline row
    (proves the parallel-drain isolation)."""
    import server
    from bson import ObjectId

    test_marker = f"_iter129_{uuid.uuid4().hex[:8]}"
    # iter129 tests — use a SYNTHETIC host_id (not server.HOST_ID) so the
    # live backend's queue workers never race with the test seed rows.
    synthetic_host = f"test-host-{uuid.uuid4().hex[:8]}"
    pipeline_id = ObjectId()
    naukri_id = ObjectId()

    await db.bulk_upload_queue.insert_many([
        {
            "_id": pipeline_id,
            "file_type": "pipeline",
            "file_name": "test-pipeline.csv",
            "file_path": "/tmp/iter129-fake-pipeline.csv",
            "status": "queued_local",
            "host_id": synthetic_host,
            "owner": "e1_recruitment_app",
            "created_at": "2026-06-01T00:00:00+00:00",
            "_iter129_test": test_marker,
        },
        {
            "_id": naukri_id,
            "file_type": "naukri",
            "file_name": "test-naukri.csv",
            "file_path": "/tmp/iter129-fake-naukri.csv",
            "status": "queued_local",
            "host_id": synthetic_host,
            "owner": "e1_recruitment_app",
            "created_at": "2026-06-01T00:00:01+00:00",
            "_iter129_test": test_marker,
        },
    ])

    try:
        # Build the naukri-scoped claim filter exactly the way the
        # worker would, but bound to the synthetic host so the live
        # workers never see these rows.
        base_or = [
            {"status": "queued_local", "host_id": synthetic_host},
        ]
        naukri_filter = {
            "$or": base_or,
            "$and": [
                {"$or": [
                    {"file_type": "naukri"},
                    {"upload_type": "naukri"},
                ]},
            ],
            "_iter129_test": test_marker,
        }
        matches = await db.bulk_upload_queue.find(
            naukri_filter, {"_id": 1, "file_type": 1}
        ).to_list(None)

        ids = {str(m["_id"]) for m in matches}
        assert str(naukri_id) in ids, "Naukri row not matched by naukri-scoped filter"
        assert str(pipeline_id) not in ids, (
            "Pipeline row leaked into naukri-scoped filter — workers would race"
        )

    finally:
        await db.bulk_upload_queue.delete_many({"_iter129_test": test_marker})


@pytest.mark.asyncio
async def test_typed_filter_honors_legacy_upload_type_field(db):
    """A legacy row with `upload_type='naukri'` (and no `file_type`)
    must STILL be claimable by the naukri worker."""
    import server
    from bson import ObjectId

    test_marker = f"_iter129_legacy_{uuid.uuid4().hex[:8]}"
    synthetic_host = f"test-host-{uuid.uuid4().hex[:8]}"
    legacy_id = ObjectId()

    await db.bulk_upload_queue.insert_one({
        "_id": legacy_id,
        # NO file_type — legacy schema only has upload_type
        "upload_type": "naukri",
        "filename": "legacy-naukri.csv",
        "filepath": "/tmp/iter129-legacy-naukri.csv",
        "status": "queued_local",
        "host_id": synthetic_host,
        "owner": "e1_recruitment_app",
        "created_at": "2026-06-01T00:00:00+00:00",
        "_iter129_test": test_marker,
    })

    try:
        base_or = [
            {"status": "queued_local", "host_id": synthetic_host},
        ]
        naukri_filter = {
            "$or": base_or,
            "$and": [
                {"$or": [
                    {"file_type": "naukri"},
                    {"upload_type": "naukri"},
                ]},
            ],
            "_iter129_test": test_marker,
        }
        m = await db.bulk_upload_queue.find_one(naukri_filter)
        assert m is not None, (
            "Legacy upload_type='naukri' row not matched — typed filter "
            "would silently ignore it"
        )

    finally:
        await db.bulk_upload_queue.delete_many({"_iter129_test": test_marker})
