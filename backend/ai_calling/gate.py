"""Centralised permission gate. EVERY outbound AI call must pass evaluate() first.

The destination number is never taken from a request body: it is read from the
approved ai_test_candidates record and cross-checked against the job.
"""
import os
from datetime import datetime, timedelta
from bson import ObjectId

from .store import db, get_settings, IST

# Phase 2: Bolna calling has NOT been approved. Flip only with explicit owner approval.
BOLNA_INTEGRATION_APPROVED = False
# Phase 2: Live Mode activation is locked in code.
LIVE_MODE_LOCKED = True

ACTIVE_JOB_STATUSES = ["claimed", "initiated", "ringing", "in-progress"]
COUNTED_JOB_STATUSES = ACTIVE_JOB_STATUSES + ["completed", "no_answer", "failed", "call-disconnected"]


def server_calling_enabled() -> bool:
    return os.environ.get("AI_CALLING_ENABLED", "false").strip().lower() == "true"


async def evaluate(*, mode: str, test_candidate_id: str, batch_id: str, phone_e164: str, mode_version: int) -> dict:
    s = await get_settings()
    checks = []

    def add(key, label, ok, detail=""):
        checks.append({"key": key, "label": label, "ok": bool(ok), "detail": detail})

    add("testing_mode", "Testing Mode is active", mode == "testing" and s["mode"] == "testing", f"current mode: {s['mode']}")
    add("not_live", "Job is not a Live Mode job (Live Mode locked)", mode != "live" and LIVE_MODE_LOCKED)
    add("server_enabled", "Server-side calling is enabled", server_calling_enabled(), "AI_CALLING_ENABLED env flag")
    add("bolna_approved", "Bolna API integration approved", BOLNA_INTEGRATION_APPROVED, "locked until Phase 3 approval")
    add("no_emergency_stop", "Emergency stop is not active", not s["emergency_stop"])
    add("mode_version", "Job belongs to current operating-mode version", mode_version == s["mode_version"],
        f"job v{mode_version} / current v{s['mode_version']}")

    cand = None
    if ObjectId.is_valid(test_candidate_id or ""):
        cand = await db().ai_test_candidates.find_one({"_id": ObjectId(test_candidate_id), "mode": "testing"})
    add("candidate_exists", "Recipient is a stored test candidate", cand is not None)
    cand = cand or {}
    add("admin_approved", "Administrator explicitly approved the recipient", cand.get("approved") is True)
    batch = None
    if ObjectId.is_valid(batch_id or ""):
        batch = await db().ai_test_batches.find_one({"_id": ObjectId(batch_id)})
    add("in_batch", "Recipient belongs to the selected test batch",
        bool(batch) and test_candidate_id in batch.get("candidate_ids", []) and batch.get("status") != "stopped")
    add("phone_matches", "Phone number matches the approved record",
        bool(phone_e164) and phone_e164 == cand.get("phone_e164") == cand.get("approved_phone"))
    add("consent", "Recipient agreed to receive test calls", cand.get("consent_confirmed") is True)
    add("not_opted_out", "Recipient has not opted out", not cand.get("opted_out"))

    day_start = datetime.now(IST).replace(hour=0, minute=0, second=0, microsecond=0)
    today = await db().ai_call_jobs.count_documents({
        "mode": "testing", "status": {"$in": COUNTED_JOB_STATUSES},
        "created_at": {"$gte": day_start.isoformat(), "$lt": (day_start + timedelta(days=1)).isoformat()},
    })
    add("daily_limit", "Daily call limit not exceeded", today < int(s["daily_call_limit"]), f"{today}/{s['daily_call_limit']} today")
    active = await db().ai_call_jobs.count_documents({"status": {"$in": ACTIVE_JOB_STATUSES}})
    add("concurrency", "Concurrency limit not exceeded", active < int(s["max_concurrent_calls"]),
        f"{active}/{s['max_concurrent_calls']} active")

    return {"allowed": all(c["ok"] for c in checks), "checks": checks}
