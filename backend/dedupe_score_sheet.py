"""
One-time dedupe + canonicalisation for the legacy `score_sheet` collection.

Why: the historical upload path (pre-iter45) inserted raw rows on every upload,
so candidates like `gourangakalita17@gmail.com` ended up with duplicate
(round, score) pairs. The new resolver picks the most-recent record per
canonical round, but cleaning the source removes ambiguity for analytics + UI.

Behaviour:
    * Dry-run by default. Pass --apply to commit.
    * Groups by (email or phone, canonical round_name).
    * Keeps the most-recent record. Marks the rest with `_dup_of=<keeper_id>`
      and (when --apply) DELETES them.
    * Adds `round_canonical` to the keeper for fast querying.
    * Adds `updated_at` if missing.

Usage:
    cd /app/backend
    python3 dedupe_score_sheet.py             # dry-run
    python3 dedupe_score_sheet.py --apply     # commit
"""
import argparse
import asyncio
import logging
import os
import sys
import re
from datetime import datetime, timezone

from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

load_dotenv("/app/backend/.env")
sys.path.insert(0, "/app/backend")

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("dedupe")


ROUND_NAME_ALIASES = {
    "technical 1": "Round 1", "technical1": "Round 1", "tech 1": "Round 1",
    "round 1": "Round 1", "round1": "Round 1",
    "technical 2": "Round 2", "technical2": "Round 2", "tech 2": "Round 2",
    "round 2": "Round 2", "round2": "Round 2",
    "hr interview": "HR Round", "hr round": "HR Round", "hr": "HR Round",
    "final discussion": "Final Round", "final round": "Final Round", "final": "Final Round",
    "accounts1": "Accounts 1", "accounts2": "Accounts 2",
    "mensa org": "Mensa Org", "mensaorg": "Mensa Org",
}


def _norm_round(name):
    if not name:
        return ""
    s = re.sub(r"\s+", " ", str(name).strip())
    return ROUND_NAME_ALIASES.get(s.lower(), s)


def _norm_email(e):
    return (str(e or "").strip().lower())


def _norm_phone(p):
    digits = re.sub(r"[^\d]", "", str(p or ""))
    return digits[-10:] if len(digits) >= 10 else digits


def _ts(rec):
    return str(rec.get("updated_at") or rec.get("created_at") or "")


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()

    cli = AsyncIOMotorClient(os.environ["MONGO_URL"])
    db = cli[os.environ["DB_NAME"]]

    total = await db.score_sheet.count_documents({})
    log.info(f"score_sheet total records: {total}")

    # Group key: (email_or_phone, canonical_round)
    groups = {}  # key → list[doc]
    cursor = db.score_sheet.find({}, {"_id": 1, "email": 1, "phone": 1,
                                        "round_name": 1, "score": 1,
                                        "created_at": 1, "updated_at": 1})
    if args.limit:
        cursor = cursor.limit(args.limit)
    async for d in cursor:
        em = _norm_email(d.get("email"))
        ph = _norm_phone(d.get("phone"))
        canon = _norm_round(d.get("round_name"))
        if not canon:
            continue
        key = (em or ph, canon)
        groups.setdefault(key, []).append(d)

    deleted = 0
    keepers_updated = 0
    singletons = 0
    for key, docs in groups.items():
        if len(docs) <= 1:
            singletons += 1
            keeper = docs[0]
            if args.apply and not keeper.get("round_canonical"):
                await db.score_sheet.update_one(
                    {"_id": keeper["_id"]},
                    {"$set": {"round_canonical": _norm_round(keeper.get("round_name"))}},
                )
                keepers_updated += 1
            continue
        # Sort newest first; keeper is most-recent
        docs_sorted = sorted(docs, key=_ts, reverse=True)
        keeper = docs_sorted[0]
        dups = docs_sorted[1:]
        log.info(f"DUP {key[0]} | {key[1]} → {len(dups)} dups (keep {keeper['_id']} ts={_ts(keeper)})")
        if args.apply:
            ids = [d["_id"] for d in dups]
            await db.score_sheet.delete_many({"_id": {"$in": ids}})
            deleted += len(ids)
            await db.score_sheet.update_one(
                {"_id": keeper["_id"]},
                {"$set": {"round_canonical": key[1],
                           "updated_at": datetime.now(timezone.utc).isoformat()}},
            )
            keepers_updated += 1

    log.info("=" * 60)
    log.info(f"Mode               : {'APPLY' if args.apply else 'DRY-RUN'}")
    log.info(f"Distinct groups     : {len(groups)}")
    log.info(f"Single-record groups: {singletons}")
    log.info(f"Duplicates deleted : {deleted}")
    log.info(f"Keepers updated    : {keepers_updated}")
    log.info("=" * 60)
    if not args.apply:
        log.info("Dry-run only. Re-run with --apply to commit.")
    cli.close()


if __name__ == "__main__":
    asyncio.run(main())
