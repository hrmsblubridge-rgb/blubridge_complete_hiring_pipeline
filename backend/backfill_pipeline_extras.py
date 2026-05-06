"""
Backfill `college_type`, `source`, and `college` on legacy `pipeline_data`
records by smart-matching against `bb_registrations` and `naukri_applies`.

Master matching rule:
    Email (primary) + Phone (secondary). If both exist on a candidate, they
    must point to the same person. Conflicts are skipped + logged.

Behaviour:
    * Dry-run by default (no DB writes). Pass --apply to commit.
    * Only fills MISSING fields (None / "" / "NULL" / "N/A"). Existing values
      are never overwritten.
    * Adds `updated_at` on every update.
    * Uses _classify_college_fn (NIRF rank lookup) for college_type derivation.

Usage:
    cd /app/backend
    python backfill_pipeline_extras.py            # dry run
    python backfill_pipeline_extras.py --apply    # commit changes
    python backfill_pipeline_extras.py --apply --limit 1000
"""
import argparse
import asyncio
import logging
import os
import sys
from datetime import datetime, timezone

from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

load_dotenv("/app/backend/.env")
sys.path.insert(0, "/app/backend")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger("backfill")


# Reuse the existing NIRF classifier + rank-lookup helpers from server.py.
# We need them to derive college_type from a college name.
async def _build_rank_lookup_for_db(db):
    docs = await db.college_rank_list.find({}, {"_id": 0}).to_list(None)
    out = {}
    for d in docs:
        name = (d.get("college_name") or d.get("name") or "").strip().lower()
        rank = d.get("rank") or d.get("nirf_rank")
        if name and rank:
            out[name] = rank
    return out


def _classify(college_name: str, rank_lookup: dict) -> str:
    """Lightweight NIRF classification: returns 'NIRF - #N' or 'Non NIRF' or ''."""
    if not college_name:
        return ""
    key = college_name.strip().lower()
    rank = rank_lookup.get(key)
    if rank:
        return f"NIRF - #{rank}"
    # Try partial-word match (very loose, mirrors existing fuzzy logic)
    for nm, rk in rank_lookup.items():
        if nm and nm in key:
            return f"NIRF - #{rk}"
    return "Non NIRF"


def _is_blank(v) -> bool:
    if v is None:
        return True
    s = str(v).strip()
    return s == "" or s.upper() in ("NULL", "N/A", "NONE")


def _norm_email(e):
    return (str(e or "").strip().lower())


def _norm_phone(p):
    import re
    digits = re.sub(r"[^\d]", "", str(p or ""))
    return digits[-10:] if len(digits) >= 10 else digits


async def _resolve(db, email, phone, rank_lookup):
    """Resolve missing college_type/source/college from external sources."""
    out = {}
    em = _norm_email(email)
    ph = _norm_phone(phone)
    if not em and not ph:
        return out
    or_clauses = []
    if em:
        or_clauses.append({"email": em})
    if ph:
        or_clauses.append({"phone": ph})
    match = {"$or": or_clauses}

    # bb_registrations (latest)
    reg_list = await db.bb_registrations.find(match, {"_id": 0}).sort("registered_at", -1).limit(1).to_list(1)
    reg = reg_list[0] if reg_list else None
    if reg:
        if not _is_blank(reg.get("college")):
            out["college"] = reg["college"]
            ct = _classify(reg["college"], rank_lookup)
            if ct:
                out["college_type"] = ct
        form_name = (reg.get("form_name") or "").lower()
        out["source"] = "college_form" if "college" in form_name else "registration_form"

    # naukri_applies
    if "college_type" not in out or "source" not in out or "college" not in out:
        nk = await db.naukri_applies.find_one(match, {"_id": 0})
        if nk:
            if "college" not in out:
                col = (nk.get("pg_university") or nk.get("ug_university") or "").strip()
                if col:
                    out["college"] = col
            if "college_type" not in out:
                col = out.get("college") or (nk.get("pg_university") or nk.get("ug_university") or "")
                ct = _classify(col, rank_lookup)
                if ct:
                    out["college_type"] = ct
            if "source" not in out:
                raw_src = (nk.get("source") or "").strip()
                out["source"] = f"naukri:{raw_src}" if raw_src else "naukri"

    return out


async def _detect_conflict(db, email, phone):
    em = _norm_email(email)
    ph = _norm_phone(phone)
    if not em or not ph:
        return None
    for col in ("pipeline_data", "bb_registrations", "naukri_applies"):
        doc = await db[col].find_one({"phone": ph}, {"_id": 0, "email": 1})
        if doc:
            other = _norm_email(doc.get("email"))
            if not other or other == em:
                continue
            # Some legacy rows have comma-joined duplicates like
            # "x@y.com, x@y.com" — split + dedupe before declaring a conflict.
            parts = {p.strip() for p in other.split(",") if p.strip()}
            if em in parts or len(parts) == 1 and next(iter(parts)) == em:
                continue
            return f"phone {ph} ↔ different email '{other}' in {col}"
    return None


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true",
                        help="Apply updates (default is dry-run)")
    parser.add_argument("--limit", type=int, default=0,
                        help="Limit number of records scanned (0 = all)")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    if args.verbose:
        log.setLevel(logging.DEBUG)

    mongo_url = os.environ["MONGO_URL"]
    db_name = os.environ["DB_NAME"]
    cli = AsyncIOMotorClient(mongo_url)
    db = cli[db_name]

    log.info("Loading NIRF rank lookup...")
    rank_lookup = await _build_rank_lookup_for_db(db)
    log.info(f"  → {len(rank_lookup)} colleges in NIRF lookup")

    # Find pipeline_data rows missing college_type OR source
    missing_q = {"$or": [
        {"college_type": {"$in": [None, "", "NULL", "N/A"]}},
        {"college_type": {"$exists": False}},
        {"source": {"$in": [None, "", "NULL", "N/A"]}},
        {"source": {"$exists": False}},
    ]}
    total = await db.pipeline_data.count_documents(missing_q)
    log.info(f"Records needing backfill: {total}")
    if args.limit and args.limit < total:
        log.info(f"  → limiting scan to {args.limit}")

    cursor = db.pipeline_data.find(missing_q, {"_id": 1, "email": 1, "phone": 1,
                                                "college": 1, "college_type": 1,
                                                "source": 1})
    if args.limit:
        cursor = cursor.limit(args.limit)

    stats = {"scanned": 0, "filled": 0, "skipped_conflict": 0,
             "no_match": 0, "already_complete": 0,
             "filled_college_type": 0, "filled_source": 0, "filled_college": 0}

    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

    async for doc in cursor:
        stats["scanned"] += 1
        email = doc.get("email")
        phone = doc.get("phone")

        # Use the doc's own college (if any) before reaching external sources
        own_college = doc.get("college")
        own_ct = _classify(own_college, rank_lookup) if not _is_blank(own_college) else ""

        extras = await _resolve(db, email, phone, rank_lookup)

        # Build set patch — only fill what's actually missing
        set_patch = {}
        if _is_blank(doc.get("college_type")):
            ct = own_ct or extras.get("college_type")
            if ct:
                set_patch["college_type"] = ct
                stats["filled_college_type"] += 1
        if _is_blank(doc.get("source")):
            src = extras.get("source")
            if src:
                set_patch["source"] = src
                stats["filled_source"] += 1
        if _is_blank(doc.get("college")) and extras.get("college"):
            set_patch["college"] = extras["college"]
            stats["filled_college"] += 1

        if not set_patch:
            stats["no_match"] += 1
            log.debug(f"  no resolvable data for {email or phone}")
            continue

        # Conflict check before commit
        conflict = await _detect_conflict(db, email, phone)
        if conflict:
            stats["skipped_conflict"] += 1
            log.warning(f"SKIP conflict ({email or phone}): {conflict}")
            continue

        set_patch["updated_at"] = now_iso

        if args.apply:
            await db.pipeline_data.update_one({"_id": doc["_id"]}, {"$set": set_patch})
            stats["filled"] += 1
        else:
            stats["filled"] += 1
            log.debug(f"DRY {email or phone}: {set_patch}")

        if stats["scanned"] % 1000 == 0:
            log.info(f"  progress: scanned={stats['scanned']} filled={stats['filled']} "
                     f"skipped_conflict={stats['skipped_conflict']}")

    log.info("=" * 60)
    log.info(f"  Mode             : {'APPLY' if args.apply else 'DRY-RUN'}")
    log.info(f"  Scanned          : {stats['scanned']}")
    log.info(f"  Filled (records) : {stats['filled']}")
    log.info(f"     college_type  : {stats['filled_college_type']}")
    log.info(f"     source        : {stats['filled_source']}")
    log.info(f"     college        : {stats['filled_college']}")
    log.info(f"  No match         : {stats['no_match']}")
    log.info(f"  Skipped conflict : {stats['skipped_conflict']}")
    log.info("=" * 60)
    if not args.apply:
        log.info("This was a dry-run. Re-run with --apply to commit changes.")

    cli.close()


if __name__ == "__main__":
    asyncio.run(main())
