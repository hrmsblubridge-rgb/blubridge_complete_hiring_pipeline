"""One-shot maintenance: reclaim Atlas storage from bulk_upload_queue.

The `bulk_upload_queue` collection caches the parsed contents of every uploaded
CSV/XLSX. Once a job finishes (status in {completed, archived, processed,
failed}) the row is no longer needed — it just consumes Atlas storage.

Run when you hit Atlas's 512 MB free-tier quota and writes start failing.

Usage:
    cd /app/backend && set -a && source .env && set +a && \
        python3 maintenance/reclaim_bulk_upload_queue.py [--dry-run]
"""
import asyncio
import os
import sys
from motor.motor_asyncio import AsyncIOMotorClient


async def main():
    dry_run = "--dry-run" in sys.argv
    c = AsyncIOMotorClient(os.environ["MONGO_URL"])
    db = c[os.environ["DB_NAME"]]
    before = await db.command("dbStats")
    print(
        f"BEFORE: data={before['dataSize']/1e6:.1f} MB  "
        f"index={before['indexSize']/1e6:.1f} MB  "
        f"total={(before['dataSize']+before['indexSize'])/1e6:.1f} MB"
    )
    terminal = {"status": {"$in": ["completed", "archived", "processed", "failed"]}}
    n = await db.bulk_upload_queue.count_documents(terminal)
    print(f"bulk_upload_queue terminal rows: {n}")
    if dry_run:
        print("(dry-run — no delete performed)")
        return
    res = await db.bulk_upload_queue.delete_many(terminal)
    print(f"Deleted {res.deleted_count} rows.")
    after = await db.command("dbStats")
    print(
        f"AFTER : data={after['dataSize']/1e6:.1f} MB  "
        f"index={after['indexSize']/1e6:.1f} MB  "
        f"total={(after['dataSize']+after['indexSize'])/1e6:.1f} MB"
    )


if __name__ == "__main__":
    asyncio.run(main())
