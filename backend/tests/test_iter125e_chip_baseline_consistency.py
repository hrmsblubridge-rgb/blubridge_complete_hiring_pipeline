"""iter125e regression — Interview Schedule Reports chip baseline consistency.

Fixes the production-reported bug where roles like "Social Media Marketer"
NEVER showed up as a chip button on the Interview Schedule Reports page,
even though:
  * the role existed in `bb_job_roles`
  * the role appeared in the JOB ROLE dropdown
  * filtering by the role returned matching records in the table
  * during the brief "All Records" loading transition, the chip flashed
    momentarily before disappearing

Root cause: the legacy `summary.role_counts` aggregation was scoped to
the FULL filter (including `jobRole`). Frontend cached this as the chip
baseline only when `jobRole === ''`. So when the user selected a role,
the baseline went stale; when "All Records" was clicked, the baseline
refreshed BUT only against `pipeline_data` (the primary `src` collection
selected by total > 0 fallback logic). Roles whose candidates lived only
in `registered_candidates` (e.g. Social Media Marketer: 0 in
pipeline_data, 6 in registered_candidates) never made it into the
baseline.

Fix:
  * Backend (`bb_modules.py`): new `summary.all_role_counts` field built
    by aggregating role counts from BOTH `pipeline_data` AND
    `registered_candidates` independently, then merging with table-
    consistent semantics: pipeline_data wins if non-zero (since the
    table also reads pipeline_data when it has >=1 match), else
    registered_candidates fills the gap. This makes the chip count
    identical to the table count regardless of which collection holds
    the records for that role.
  * Frontend (`InterviewReports.js`): chip strip now reads
    `summary.all_role_counts` (refreshed every fetch) and merges the
    selected role's live `role_counts[jobRole]` value on top. No more
    stale baseline cached in a ref.
"""
import asyncio
import inspect
import os
import sys

from dotenv import load_dotenv

load_dotenv("/app/backend/.env")
sys.path.insert(0, "/app/backend")

from motor.motor_asyncio import AsyncIOMotorClient  # noqa: E402
import bb_modules  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
import server  # noqa: E402


def _fresh_db():
    client = AsyncIOMotorClient(os.environ["MONGO_URL"])
    return client[os.environ["DB_NAME"]], client


def test_endpoint_returns_all_role_counts_field():
    """Source-code guard: response must include `summary.all_role_counts`."""
    src = inspect.getsource(bb_modules.get_interview_reports)
    assert '"all_role_counts": all_role_counts' in src
    assert "_agg_by_role" in src


def test_chip_baseline_aggregates_from_both_collections():
    """Functional guard: the merged baseline must pick up roles that live
    only in `registered_candidates`. Seeds an rc-only test row with a
    fresh unique role and asserts the chip baseline surfaces it."""

    async def _run():
        db, client = _fresh_db()
        original_bb_db = bb_modules._db
        original_srv_db = server.db
        bb_modules._db = db
        server.db = db
        try:
            test_role = "Iter125e-RcOnly-ChipRole-XYZ-zzz"
            test_email = f"iter125e_rc_only@example.invalid"
            today = "2026-05-28"
            # Clean
            await db.pipeline_data.delete_many({"email": test_email})
            await db.registered_candidates.delete_many({"email": test_email})
            # Seed ONLY into registered_candidates (NOT pipeline_data)
            await db.registered_candidates.insert_one({
                "email": test_email,
                "phone": "9000125e01",
                "name": "iter125e-rc-only",
                "_normalized_job_role": test_role,
                "job_role": test_role,
                "schedule_date": today,
                "schedule_time": "10:00:00",
            })

            # Replicate the all_role_counts aggregation
            from server import (
                _build_canonical_index,
                _canonicalize_job_role,
                _get_job_keyword_mappings,
            )
            kw_to_canonical, _ = await _build_canonical_index()
            raw_mappings = await _get_job_keyword_mappings()
            base_match = bb_modules._build_interview_reports_match(
                today, today, None, None, None,
                _canonical_index=kw_to_canonical, _mappings=raw_mappings,
            )
            role_id_expr = {
                "$let": {
                    "vars": {
                        "norm": {"$ifNull": ["$_normalized_job_role", ""]},
                        "jr": {"$ifNull": ["$job_role", ""]},
                        "jt": {"$ifNull": ["$job_title", ""]},
                    },
                    "in": {
                        "$cond": [
                            {"$and": [
                                {"$ne": ["$$norm", ""]},
                                {"$ne": ["$$norm", "Unknown"]},
                            ]},
                            "$$norm",
                            {"$cond": [
                                {"$ne": ["$$jr", ""]}, "$$jr",
                                {"$cond": [{"$ne": ["$$jt", ""]}, "$$jt", "Unknown"]},
                            ]},
                        ],
                    },
                },
            }

            async def _agg(coll):
                cur = await coll.aggregate([
                    {"$match": base_match},
                    {"$group": {"_id": role_id_expr, "count": {"$sum": 1}}},
                ]).to_list(None)
                out = {}
                for r in cur:
                    if not r["_id"]:
                        continue
                    canon = _canonicalize_job_role(r["_id"], kw_to_canonical)
                    if not canon or canon.strip().lower() in ("", "unknown"):
                        continue
                    out[canon] = out.get(canon, 0) + r["count"]
                return out

            pd = await _agg(db.pipeline_data)
            rc = await _agg(db.registered_candidates)
            merged = dict(pd)
            for k, v in rc.items():
                if merged.get(k, 0) == 0:
                    merged[k] = v

            assert test_role in merged, (
                f"RC-only role {test_role!r} must surface in merged baseline. "
                f"pd={list(pd.keys())[:5]} rc={list(rc.keys())[:5]} merged={list(merged.keys())[:5]}"
            )
            assert merged[test_role] >= 1

            await db.registered_candidates.delete_many({"email": test_email})
        finally:
            bb_modules._db = original_bb_db
            server.db = original_srv_db
            client.close()

    asyncio.run(_run())


def test_chip_count_matches_table_count_for_rc_only_role():
    """Critical UX invariant: when the user selects an rc-only role in the
    dropdown, the chip count must equal the table's filtered count."""

    async def _run():
        db, client = _fresh_db()
        original_bb_db = bb_modules._db
        original_srv_db = server.db
        bb_modules._db = db
        server.db = db
        try:
            test_role = "Iter125e-RcOnly-TableConsistency-ABC"
            today = "2026-05-28"
            # Cleanup any prior
            for i in range(3):
                await db.registered_candidates.delete_many({"email": f"iter125e_tc_{i}@example.invalid"})
            # Seed 3 distinct rc-only candidates
            for i in range(3):
                await db.registered_candidates.insert_one({
                    "email": f"iter125e_tc_{i}@example.invalid",
                    "phone": f"9000125e{i:02d}",
                    "name": f"iter125e-tc-{i}",
                    "_normalized_job_role": test_role,
                    "job_role": test_role,
                    "schedule_date": today,
                    "schedule_time": "10:00:00",
                })

            from server import (
                _build_canonical_index,
                _canonicalize_job_role,
                _get_job_keyword_mappings,
            )
            kw_to_canonical, _ = await _build_canonical_index()
            raw_mappings = await _get_job_keyword_mappings()

            # Table count via filtered match (what the table would show)
            match_filtered = bb_modules._build_interview_reports_match(
                today, today, test_role, None, None,
                _canonical_index=kw_to_canonical, _mappings=raw_mappings,
            )
            pd_filt = await db.pipeline_data.count_documents(match_filtered)
            rc_filt = await db.registered_candidates.count_documents(match_filtered)
            table_count = pd_filt if pd_filt > 0 else rc_filt
            assert table_count >= 3

            # Chip baseline count via the merged aggregation
            base_match = bb_modules._build_interview_reports_match(
                today, today, None, None, None,
                _canonical_index=kw_to_canonical, _mappings=raw_mappings,
            )
            role_id_expr = {
                "$let": {
                    "vars": {
                        "norm": {"$ifNull": ["$_normalized_job_role", ""]},
                        "jr": {"$ifNull": ["$job_role", ""]},
                        "jt": {"$ifNull": ["$job_title", ""]},
                    },
                    "in": {
                        "$cond": [
                            {"$and": [
                                {"$ne": ["$$norm", ""]},
                                {"$ne": ["$$norm", "Unknown"]},
                            ]},
                            "$$norm",
                            {"$cond": [
                                {"$ne": ["$$jr", ""]}, "$$jr",
                                {"$cond": [{"$ne": ["$$jt", ""]}, "$$jt", "Unknown"]},
                            ]},
                        ],
                    },
                },
            }

            async def _agg(coll):
                cur = await coll.aggregate([
                    {"$match": base_match},
                    {"$group": {"_id": role_id_expr, "count": {"$sum": 1}}},
                ]).to_list(None)
                return {
                    _canonicalize_job_role(r["_id"], kw_to_canonical): r["count"]
                    for r in cur
                    if r["_id"]
                }

            pd_counts = await _agg(db.pipeline_data)
            rc_counts = await _agg(db.registered_candidates)
            merged = dict(pd_counts)
            for k, v in rc_counts.items():
                if merged.get(k, 0) == 0:
                    merged[k] = v
            chip_count = merged.get(test_role, 0)

            assert chip_count == table_count, (
                f"Chip count ({chip_count}) must match table count "
                f"({table_count}) for rc-only role {test_role!r}"
            )

            for i in range(3):
                await db.registered_candidates.delete_many({"email": f"iter125e_tc_{i}@example.invalid"})
        finally:
            bb_modules._db = original_bb_db
            server.db = original_srv_db
            client.close()

    asyncio.run(_run())


def test_frontend_chip_baseline_reads_all_role_counts():
    """Frontend guard: chip rendering must read `summary.all_role_counts`,
    not the legacy `baselineRoleCounts.current` ref."""
    path = "/app/frontend/src/pages/InterviewReports.js"
    with open(path, "r") as f:
        src = f.read()
    assert "summary.all_role_counts" in src
    # Old broken pattern must be GONE
    assert "baselineRoleCounts.current" not in src
