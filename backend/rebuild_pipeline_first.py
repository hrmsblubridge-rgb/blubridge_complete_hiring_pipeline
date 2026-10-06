"""Pipeline-first rebuild of `registered_candidates` — efficient version.

STRATEGY (optimized for Atlas free tier):
  1. Drop registered_candidates.
  2. Build naukri lookup (email/phone -> full doc) by streaming docs in small pages.
  3. Stream pipeline_data in chunks; for each doc, merge matched naukri data, bulk insert.
  4. Bulk-update `naukri_applies._is_registered` based on matched email/phone sets.

NEW CLASSIFICATION:
  - Registered   = every pipeline_data record (HR internal)
  - Unregistered = naukri_applies record with no pipeline match (_is_registered=False)

SAFETY: does NOT alter raw data; skips isTest=True rows.
"""
import asyncio, os, re, sys, time

with open('/app/backend/.env') as f:
    for line in f:
        line = line.strip()
        if line and not line.startswith('#') and '=' in line:
            k, v = line.split('=', 1)
            os.environ[k.strip()] = v.strip().strip('"')

sys.path.insert(0, '/app/backend')

from motor.motor_asyncio import AsyncIOMotorClient
from pymongo import UpdateOne

client = AsyncIOMotorClient(
    os.environ['MONGO_URL'],
    serverSelectionTimeoutMS=30000,
    connectTimeoutMS=30000,
    socketTimeoutMS=600000,
)
db = client[os.environ['DB_NAME']]

LOG = '/tmp/rebuild_pipeline_first.log'
def log(msg):
    line = f"[{time.strftime('%H:%M:%S')}] {msg}"
    with open(LOG, 'a') as f:
        f.write(line + '\n')
    print(line, flush=True)


def norm_email(e):
    if not e:
        return ''
    return str(e).strip().lower()


def norm_phone(p):
    if not p:
        return ''
    digits = re.sub(r'[^\d]', '', str(p))
    if len(digits) > 10:
        digits = digits[-10:]
    return digits if len(digits) == 10 else ''


SKIP_KEYS = {"_id", "_is_registered", "created_at", "updated_at"}


async def rebuild():
    with open(LOG, 'w') as f:
        f.write('')
    log("Starting pipeline-first rebuild (efficient)...")

    pipe_total = await db.pipeline_data.count_documents({"isTest": {"$ne": True}})
    naukri_total = await db.naukri_applies.count_documents({"isTest": {"$ne": True}})
    log(f"Baseline: pipeline_data={pipe_total}, naukri_applies={naukri_total}")

    # PHASE 1: Build naukri lookup — full docs indexed by email/phone.
    # Use batch_size for efficient cursor paging on Atlas.
    log("Phase 1: Loading naukri_applies into memory...")
    n_by_email = {}
    n_by_phone = {}
    naukri_total_loaded = 0

    cursor = db.naukri_applies.find({"isTest": {"$ne": True}}, batch_size=2000)
    async for n in cursor:
        em = norm_email(n.get('email'))
        ph = norm_phone(n.get('phone'))
        if em:
            n_by_email[em] = n
        if ph:
            n_by_phone[ph] = n
        naukri_total_loaded += 1
        if naukri_total_loaded % 5000 == 0:
            log(f"  naukri loaded: {naukri_total_loaded}")
    log(f"Phase 1 done: naukri loaded={naukri_total_loaded}, emails={len(n_by_email)}, phones={len(n_by_phone)}")

    # PHASE 2: Stream pipeline → merge → bulk insert
    log("Phase 2: Streaming pipeline_data and building registered_candidates...")
    await db.registered_candidates.drop()

    matched_naukri_ids = set()
    batch = []
    inserted = 0
    matched_count = 0

    pcur = db.pipeline_data.find({"isTest": {"$ne": True}}, batch_size=2000)
    async for p in pcur:
        em = norm_email(p.get('email'))
        ph = norm_phone(p.get('phone'))
        naukri_doc = None
        if em and em in n_by_email:
            naukri_doc = n_by_email[em]
        elif ph and ph in n_by_phone:
            naukri_doc = n_by_phone[ph]

        if naukri_doc:
            matched_naukri_ids.add(naukri_doc["_id"])
            matched_count += 1

        doc = {k: v for k, v in p.items() if k not in SKIP_KEYS}
        if naukri_doc:
            for k, v in naukri_doc.items():
                if k in SKIP_KEYS:
                    continue
                if v is not None and v != "":
                    doc[k] = v
                elif k not in doc:
                    doc[k] = v

        if not doc.get("job_title"):
            doc["job_title"] = doc.get("job_role") or ""
        doc["_has_naukri_match"] = bool(naukri_doc)

        batch.append(doc)
        if len(batch) >= 2000:
            await db.registered_candidates.insert_many(batch, ordered=False)
            inserted += len(batch)
            log(f"  inserted: {inserted}/{pipe_total} (enriched_so_far={matched_count})")
            batch = []

    if batch:
        await db.registered_candidates.insert_many(batch, ordered=False)
        inserted += len(batch)

    log(f"Phase 2 done: registered_candidates={inserted}, naukri-enriched={matched_count}")

    # PHASE 3: Flag naukri._is_registered — single update_many per group
    log("Phase 3: Updating naukri_applies._is_registered...")
    matched_list = list(matched_naukri_ids)
    if matched_list:
        # Chunk the $in to avoid oversized operators
        chunk = 5000
        for i in range(0, len(matched_list), chunk):
            await db.naukri_applies.update_many(
                {"_id": {"$in": matched_list[i:i + chunk]}, "isTest": {"$ne": True}},
                {"$set": {"_is_registered": True}}
            )
    # Mark all others as False (cannot use $nin with 19K items, so use invert per chunk)
    # Simpler: set all to False first, then set matched to True
    # But we just set matched to True above; now set the rest to False:
    await db.naukri_applies.update_many(
        {"_id": {"$nin": matched_list}, "isTest": {"$ne": True}},
        {"$set": {"_is_registered": False}}
    )
    set_true = await db.naukri_applies.count_documents({"_is_registered": True, "isTest": {"$ne": True}})
    set_false = await db.naukri_applies.count_documents({"_is_registered": False, "isTest": {"$ne": True}})
    log(f"Phase 3 done: _is_registered True={set_true}, False={set_false}")

    # PHASE 4: Indexes
    log("Phase 4: Creating indexes...")
    await db.registered_candidates.create_index([("email", 1), ("phone", 1)])
    await db.registered_candidates.create_index("email_type")
    await db.registered_candidates.create_index("result_status")
    await db.registered_candidates.create_index("schedule_date")
    await db.registered_candidates.create_index("otp_verified")
    await db.registered_candidates.create_index("_has_naukri_match")
    await db.naukri_applies.create_index("_is_registered")

    # PHASE 5: Persist derived fields
    log("Phase 5: Persisting derived fields (_normalized_job_role, _college_status, etc.)...")
    import server  # noqa
    await server._persist_derived_fields("registered_candidates")
    await server._persist_derived_fields("naukri_applies")

    rc = await db.registered_candidates.count_documents({})
    nu = await db.naukri_applies.count_documents({"_is_registered": {"$ne": True}})
    log(f"DONE. registered_candidates={rc}, unregistered_naukri={nu}")


if __name__ == "__main__":
    asyncio.run(rebuild())
