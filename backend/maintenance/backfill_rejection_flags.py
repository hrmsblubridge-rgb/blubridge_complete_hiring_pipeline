"""
Backfill historical rejection flags.

Runs ONCE at startup, gated by a marker document in `bb_migrations`.
Sets `rejection_sent=True` + `rejection_pending=False` on EVERY existing
record that already represents a rejected applicant. After this runs,
the new evening-rejection worker will treat all of them as "already sent"
and will never message any of them.

Strict safety: this script only WRITES FLAGS. It never reads message
templates, never calls any send helper, never touches the AiSensy or SMTP
network. There is no way for it to deliver a message to anyone.

Triggered from server.py `@app.on_event("startup")`.
"""
import logging
from datetime import datetime, timezone

_logger = logging.getLogger(__name__)

MIGRATION_ID = "rejection_flag_backfill_v1"

# All four observed spellings in the live `pipeline_data` table:
#   Rejected (2626), Reject (1093), reject (266), rejected (70)
REJECTION_STATUS_VARIANTS = ["Rejected", "Reject", "reject", "rejected"]


async def run_backfill(db) -> dict:
    """Idempotent. Returns a stats dict. Safe to call repeatedly — after the
    first successful run, the marker doc short-circuits all subsequent calls.
    """
    # Marker check — never run twice.
    marker = await db.bb_migrations.find_one({"_id": MIGRATION_ID})
    if marker and marker.get("status") == "completed":
        _logger.info(f"[Backfill:{MIGRATION_ID}] already completed at {marker.get('completed_at')}, skipping")
        return {"skipped": True, "reason": "already_completed"}

    started_at = datetime.now(timezone.utc).isoformat()
    _logger.info(f"[Backfill:{MIGRATION_ID}] starting at {started_at}")

    now_iso = started_at
    set_payload = {
        "rejection_sent": True,
        "rejection_pending": False,
        "rejection_backfilled_at": now_iso,
    }
    stats = {"pipeline_data": 0, "bb_applicant_updates": 0, "bb_registrations": 0}

    # 1) pipeline_data — match ANY of the 4 spellings of result_status.
    try:
        r1 = await db.pipeline_data.update_many(
            {"result_status": {"$in": REJECTION_STATUS_VARIANTS},
             "rejection_sent": {"$ne": True}},
            {"$set": set_payload},
        )
        stats["pipeline_data"] = r1.modified_count
    except Exception as e:
        _logger.warning(f"[Backfill] pipeline_data step failed: {e}")

    # 2) bb_applicant_updates — covers the admin "Update Scores" + bulk import path.
    try:
        r2 = await db.bb_applicant_updates.update_many(
            {"$or": [
                {"status": {"$in": REJECTION_STATUS_VARIANTS}},
                {"rejection_notified": True},          # legacy flag set by old worker
                {"import_rejection_notified": True},   # legacy flag set by bulk import
            ],
             "rejection_sent": {"$ne": True}},
            {"$set": set_payload},
        )
        stats["bb_applicant_updates"] = r2.modified_count
    except Exception as e:
        _logger.warning(f"[Backfill] bb_applicant_updates step failed: {e}")

    # 3) bb_registrations — form-condition rejections during /api/pub/register.
    try:
        r3 = await db.bb_registrations.update_many(
            {"$or": [
                {"is_shortlisted": False},
                {"reject_notified": True},
            ],
             "rejection_sent": {"$ne": True}},
            {"$set": set_payload},
        )
        stats["bb_registrations"] = r3.modified_count
    except Exception as e:
        _logger.warning(f"[Backfill] bb_registrations step failed: {e}")

    # Marker doc — record completion so we never re-run.
    completed_at = datetime.now(timezone.utc).isoformat()
    try:
        await db.bb_migrations.update_one(
            {"_id": MIGRATION_ID},
            {"$set": {
                "status": "completed",
                "started_at": started_at,
                "completed_at": completed_at,
                "stats": stats,
                "note": "All historical rejected records flagged rejection_sent=True. "
                        "Future evening worker will skip them.",
            }},
            upsert=True,
        )
    except Exception as e:
        _logger.error(f"[Backfill] marker write failed (will retry on next boot): {e}")
        return {"completed": False, "error": str(e), "stats": stats}

    _logger.info(f"[Backfill:{MIGRATION_ID}] completed — stats={stats}")
    return {"completed": True, "stats": stats}
