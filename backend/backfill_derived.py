"""One-time backfill: compute and persist derived fields on registered_candidates
and naukri_applies so endpoints can filter at the DB level (no in-memory scans).

Persisted fields (prefixed `_` to indicate computed/internal):
  _college_status   : "NIRF - #<rank>" | "Non NIRF"
  _nirf_category    : "NIRF" | "Non NIRF"
  _college_resolved : best matched college string
  _match_confidence : HIGH | MEDIUM | LOW | None
  _normalized_job_role : canonical job role from job_keyword_mapping (else raw job_title)

Run:
  python3 /app/backend/backfill_derived.py
"""
import asyncio, os, sys, time

# Load .env
with open('/app/backend/.env') as f:
    for line in f:
        line = line.strip()
        if line and not line.startswith('#') and '=' in line:
            k, v = line.split('=', 1)
            os.environ[k.strip()] = v.strip().strip('"')

sys.path.insert(0, '/app/backend')

from motor.motor_asyncio import AsyncIOMotorClient
from pymongo import UpdateOne

# Re-use server helpers (avoid duplicating logic)
import server  # noqa

LOG = '/tmp/backfill.log'
def log(msg):
    line = f"[{time.strftime('%H:%M:%S')}] {msg}"
    with open(LOG, 'a') as f:
        f.write(line + '\n')
    print(line, flush=True)


async def compute_and_persist(collection_name: str, batch_size: int = 1000):
    """Stream docs from `collection_name`, compute derived fields, bulk-update."""
    coll = server.db[collection_name]
    rank_lookup = await server._build_college_rank_lookup()
    mappings = await server._get_job_keyword_mappings()

    total = await coll.count_documents({})
    log(f"{collection_name}: {total} docs to backfill")

    cursor = coll.find({}, {
        "_id": 1, "ug_university": 1, "pg_university": 1,
        "college": 1, "job_title": 1, "job_role": 1,
    })

    ops = []
    processed = 0
    async for doc in cursor:
        cc = server._classify_college(doc, rank_lookup)
        cs = cc["college_status"]
        cat = "NIRF" if cs.startswith("NIRF - #") else "Non NIRF"
        raw_role = doc.get("job_title") or doc.get("job_role") or ""
        normalized_role = server._resolve_normalized_job_role(raw_role, mappings)
        ops.append(UpdateOne(
            {"_id": doc["_id"]},
            {"$set": {
                "_college_status": cs,
                "_nirf_category": cat,
                "_college_resolved": cc.get("college") or "-",
                "_match_confidence": cc.get("match_confidence") or None,
                "_normalized_job_role": normalized_role or "Unknown",
            }}
        ))
        if len(ops) >= batch_size:
            await coll.bulk_write(ops, ordered=False)
            processed += len(ops)
            log(f"  {collection_name}: {processed}/{total}")
            ops = []

    if ops:
        await coll.bulk_write(ops, ordered=False)
        processed += len(ops)
        log(f"  {collection_name}: {processed}/{total}")

    # Indexes for fast filtering
    await coll.create_index("_college_status")
    await coll.create_index("_nirf_category")
    await coll.create_index("_normalized_job_role")
    log(f"{collection_name}: indexes created")


async def main():
    with open(LOG, 'w') as f:
        f.write('')
    log("Starting backfill...")

    # Sync job titles master so dropdowns stay current (optional best-effort)
    try:
        await server._sync_job_titles_master()
    except Exception as e:
        log(f"job_titles_master sync skipped: {e}")

    await compute_and_persist("registered_candidates")
    await compute_and_persist("naukri_applies")
    await compute_and_persist("pipeline_data")

    # Sort indexes used by /api/applicants pagination
    await server.db.registered_candidates.create_index("name")
    await server.db.registered_candidates.create_index("last_update")
    await server.db.registered_candidates.create_index("schedule_date")
    log("DONE")


if __name__ == "__main__":
    asyncio.run(main())
