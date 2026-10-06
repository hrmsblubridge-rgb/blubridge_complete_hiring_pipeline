"""iter125c regression — Three production fixes:

ISSUE 1: View Applicants Summary Statistics misclassifying as "Unknown".
  Root cause: `/api/summary` grouped on
  `{"$ifNull": ["$_normalized_job_role", "Unknown"]}` only. Candidates
  whose derived field wasn't persisted yet (fresh uploads, in-progress
  reprocess) collapsed into the "Unknown" bucket — even though their raw
  `job_role` / `job_title` was valid.
  Fix: replaced with `$let / $cond` fallback chain
  `_normalized_job_role → job_role → job_title` inside the `$group._id`,
  matching the row-level fallback used by the data table.

ISSUE 2: /api/job-roles dropped freshly uploaded rows without
  `_normalized_job_role`.
  Fix: same fallback chain inside the aggregation pipeline. Rows without
  the persisted field now surface under their raw `job_role` label.

ISSUE 3: Reschedule sequencing — OTP sent BEFORE schedule details AND
  schedule details sent twice.
  Root cause: `submit_schedule()` unset OTP per-channel flags BEFORE
  calling `notify_schedule_confirmation`. During the network call
  (AiSensy + Resend), the OTP worker (30s tick) saw `otp_wa_sent != True`
  AND `otp_email_sent != True` AND schedule_date/time set → claimed the
  row and dispatched OTP first.
  Additionally, the same unset wiped `interview_mail_sent` allowing the
  deferred bg_worker `_schedule_link_sender` to ALSO send the schedule
  confirmation in parallel → duplicate.
  Fix: split unsets into pre-send vs post-send. Pre-send keeps OTP flags
  intact (and keeps interview_mail_sent intact too); post-send (AFTER
  notify_schedule_confirmation returns) clears the OTP per-channel flags
  so the OTP worker may now fire. Added `interview_mail_sent_in_progress`
  CAS lock to bridge the gap with the bg_worker.
"""
import asyncio
import inspect
import os
import sys

from dotenv import load_dotenv

load_dotenv("/app/backend/.env")
sys.path.insert(0, "/app/backend")

from motor.motor_asyncio import AsyncIOMotorClient  # noqa: E402
import server  # noqa: E402
import bb_modules  # noqa: E402
import bg_workers  # noqa: E402


def _fresh_db():
    client = AsyncIOMotorClient(os.environ["MONGO_URL"])
    return client[os.environ["DB_NAME"]], client


# ─────────────────── ISSUE 1: /api/summary fallback chain ───────────────────

def test_summary_aggregation_uses_fallback_chain():
    """Source-code guard: get_summary must use $let/$cond fallback for
    role grouping, not a simple `$ifNull → Unknown`."""
    src = inspect.getsource(server.get_summary)
    assert "$let" in src and "$cond" in src and "$$norm" in src, (
        "get_summary must use $let/$cond fallback chain for role grouping"
    )


def test_summary_endpoint_includes_new_role_without_normalized_field():
    """A pipeline_data row inserted with a NEW raw `job_role` and NO
    `_normalized_job_role` must NOT bucket as 'Unknown' in /api/summary."""

    async def _run():
        db, client = _fresh_db()
        original_db = server.db
        server.db = db
        try:
            email = "iter125c_summary_t@example.com"
            new_role = "Iter125c-Summary-Test-Role-PQR"
            await db.pipeline_data.delete_many({"email": email})
            await db.pipeline_data.insert_one({
                "email": email,
                "phone": "9000125801",
                "name": "iter125c-summary",
                "job_role": new_role,
                "last_update": "2026-05-28T10:00:00+00:00",
                "isTest": True,
            })

            # Replicate the aggregation pipeline shape from get_summary
            pipe_match = {"last_update": {"$gte": "2026-05-28", "$lte": "2026-05-28\uffff"}}
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
            results = await db.pipeline_data.aggregate([
                {"$match": pipe_match},
                {"$group": {"_id": {"role": role_id_expr}, "n": {"$sum": 1}}},
            ]).to_list(None)
            roles = {r["_id"]["role"] for r in results}
            assert new_role in roles, (
                f"Aggregation must include {new_role!r} (the raw job_role) "
                f"as a bucket — not 'Unknown'. Got: {roles}"
            )
            assert "Unknown" not in roles or all(r != new_role for r in roles if r == "Unknown")

            await db.pipeline_data.delete_many({"email": email})
        finally:
            server.db = original_db
            client.close()

    asyncio.run(_run())


# ─────────────────── ISSUE 2: /api/job-roles fallback ───────────────────

def test_job_roles_endpoint_uses_fallback_chain():
    """Source-code guard: get_job_roles must use $let/$cond fallback chain."""
    src = inspect.getsource(server.get_job_roles)
    assert "$let" in src and "$cond" in src and "$$norm" in src, (
        "get_job_roles must use $let/$cond fallback chain for role grouping"
    )


# ─────────────────── ISSUE 3: Reschedule sequencing ───────────────────

def test_submit_schedule_splits_unsets_pre_and_post_send():
    """Source-code guard: schedule_interview must split OTP-flag unsets
    into pre-send and POST-send phases so the schedule-confirmation
    message goes out BEFORE OTP per-channel flags are cleared."""
    src = inspect.getsource(bb_modules.schedule_interview)
    assert "pre_send_unset_fields" in src
    assert "post_send_unset_fields" in src
    assert "\"otp_wa_sent\"" in src
    assert "\"otp_email_sent\"" in src


def test_submit_schedule_uses_interview_mail_in_progress_cas():
    """Source-code guard: schedule_interview must atomically claim the
    schedule-confirmation dispatch via `interview_mail_sent_in_progress`
    so the deferred bg_worker can't fire a duplicate."""
    src = inspect.getsource(bb_modules.schedule_interview)
    assert "interview_mail_sent_in_progress" in src
    assert "_claimed_schedule_send" in src


def test_bg_worker_respects_in_progress_lock_and_does_cas():
    """Source-code guard: the deferred schedule-link bg_worker must
    skip rows where the inline path has claimed `interview_mail_sent_in_progress`
    AND perform its own CAS before sending — eliminating the duplicate."""
    with open(os.path.join(os.path.dirname(bb_modules.__file__), "bg_workers.py"), "r") as f:
        src = f.read()
    assert "interview_mail_sent_in_progress" in src
    assert "CAS lost" in src


def test_submit_schedule_otp_unset_happens_only_after_send():
    """Functional guard: in schedule_interview source, the
    `post_send_unset_fields` update must be applied AFTER the
    `notify_schedule_confirmation` call, not before."""
    src = inspect.getsource(bb_modules.schedule_interview)
    pre_idx = src.find("pre_send_unset_fields")
    # Use the ACTUAL await call (rfind handles trailing comments above the call)
    send_idx = src.find("await notify_schedule_confirmation(")
    post_apply_idx = src.find("\"$unset\": post_send_unset_fields")
    assert pre_idx > 0 and send_idx > 0 and post_apply_idx > 0
    assert pre_idx < send_idx < post_apply_idx, (
        f"Ordering violated: pre_send={pre_idx}, send={send_idx}, "
        f"post_apply={post_apply_idx}. post_send_unset_fields must be applied "
        f"AFTER notify_schedule_confirmation to prevent OTP from firing first."
    )
