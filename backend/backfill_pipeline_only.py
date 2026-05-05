"""Backfill ONLY pipeline_data with derived fields.
Re-uses server._persist_derived_fields helper (which now reads `college` + `job_role`
fallbacks). Streams in batches; safe for Atlas free tier disk.
"""
import asyncio, os, sys, time

with open('/app/backend/.env') as f:
    for line in f:
        line = line.strip()
        if line and not line.startswith('#') and '=' in line:
            k, v = line.split('=', 1)
            os.environ[k.strip()] = v.strip().strip('"')

sys.path.insert(0, '/app/backend')
import server  # noqa


async def main():
    t0 = time.time()
    print(f"[{time.strftime('%H:%M:%S')}] Starting pipeline_data backfill...")
    total = await server.db.pipeline_data.count_documents({})
    print(f"[{time.strftime('%H:%M:%S')}] pipeline_data count={total}")
    await server._persist_derived_fields("pipeline_data")
    has = await server.db.pipeline_data.count_documents({"_normalized_job_role": {"$exists": True}})
    print(f"[{time.strftime('%H:%M:%S')}] DONE in {int(time.time()-t0)}s. has _normalized_job_role={has}/{total}")

if __name__ == "__main__":
    asyncio.run(main())
