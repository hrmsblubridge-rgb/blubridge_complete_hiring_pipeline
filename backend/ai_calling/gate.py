"""Centralised permission gate. EVERY outbound AI call must pass evaluate() first.

The destination number is never taken from a request body: it is read from the
consented ai_test_candidates record and cross-checked against the job.
"""
import os
from datetime import datetime, timedelta
from bson import ObjectId

from .store import db, get_settings, IST

# Batch/automatic Bolna calling has NOT been approved. Flip only with explicit owner approval.
BOLNA_INTEGRATION_APPROVED = False
# Phase 5: server-side calling lock — Call Now disabled until the owner explicitly re-approves.
SINGLE_TEST_CALL_APPROVED = False
# Phase 2: Live Mode activation is locked in code.
LIVE_MODE_LOCKED = True

ACTIVE_JOB_STATUSES = ["claimed", "initiated", "ringing", "in-progress", "pending_reconciliation", "needs_review"]
COUNTED_JOB_STATUSES = ACTIVE_JOB_STATUSES + ["completed", "no_answer", "failed", "call-disconnected",
                                              "rejected", "finished", "reviewed"]


def server_calling_enabled() -> bool:
    return os.environ.get("AI_CALLING_ENABLED", "false").strip().lower() == "true"


async def evaluate(*, mode: str, test_candidate_id: str, batch_id: str, phone_e164: str, mode_version: int,
                   single_call: bool = False) -> dict:
    s = await get_settings()
    checks = []

    def add(key, label, ok, detail=""):
        checks.append({"key": key, "label": label, "ok": bool(ok), "detail": detail})

    add("ai_test_on", "AI Test Mode is ON", mode == "testing" and s["ai_test_enabled"])
    add("not_live", "Job is a test-list job (live dispatch uses its own gate)", mode != "live")
    add("server_enabled", "Server-side calling is enabled", server_calling_enabled(), "AI_CALLING_ENABLED env flag")
    if single_call:
        add("bolna_approved", "Single test call approved (Phase 4B)", SINGLE_TEST_CALL_APPROVED)
    else:
        add("bolna_approved", "Bolna API integration approved", BOLNA_INTEGRATION_APPROVED, "batch calling locked")
    from .provider import provider_ready
    prov = await db().ai_provider_settings.find_one({"_id": "bolna"}) or {}
    add("provider_validated", "Bolna configuration saved and validated", provider_ready(prov),
        f"status: {prov.get('status', 'not_configured')}")
    add("no_emergency_stop", "Emergency stop is not active", not s["emergency_stop"])
    add("mode_version", "Job belongs to current operating-mode version", mode_version == s["mode_version"],
        f"job v{mode_version} / current v{s['mode_version']}")

    cand = None
    if ObjectId.is_valid(test_candidate_id or ""):
        cand = await db().ai_test_candidates.find_one({"_id": ObjectId(test_candidate_id), "mode": "testing"})
    add("candidate_exists", "Recipient is a stored test candidate", cand is not None)
    cand = cand or {}
    if single_call:
        now = datetime.now(IST)
        add("interview_upcoming", "Interview date has not passed", (cand.get("interview_date") or "") >= now.date().isoformat())
        add("call_window", "Within the allowed calling window (IST)",
            s["call_window_start"] <= now.strftime("%H:%M") < s["call_window_end"],
            f"{s['call_window_start']}–{s['call_window_end']} IST")
    else:
        batch = None
        if ObjectId.is_valid(batch_id or ""):
            batch = await db().ai_test_batches.find_one({"_id": ObjectId(batch_id)})
        add("in_batch", "Recipient belongs to the selected test batch",
            bool(batch) and test_candidate_id in batch.get("candidate_ids", []) and batch.get("status") != "stopped")
    add("phone_matches", "Phone number is the saved number the consent was given for",
        bool(phone_e164) and phone_e164 == cand.get("phone_e164") == cand.get("consent_phone"))
    add("consent", "Recipient agreed to receive test calls", cand.get("consent_status") == "granted")
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
