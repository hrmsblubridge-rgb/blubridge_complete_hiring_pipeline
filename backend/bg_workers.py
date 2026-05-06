"""Background workers for automated messaging tasks.
All workers are idempotent — safe to run repeatedly without duplicate sends.

MESSAGING_CUTOFF_TS guard (May 2026):
  Every worker filters `registered_at >= MESSAGING_CUTOFF_TS` (set in .env).
  Records created BEFORE this timestamp (legacy / pre-deployment data) are NEVER
  contacted. Only NEW applicants registered after the cutoff trigger messages.
  See `_cutoff_filter()` below.

LOCAL TIME (IST):
  Schedule dates/times are entered by candidates in IST. Workers compare
  using IST consistently. `_local_now()` returns the current IST time.
"""

import asyncio
import logging
import os
import random
from datetime import datetime, timezone, timedelta

_logger = logging.getLogger("bg_workers")

_db = None
_running = False

# Indian Standard Time (UTC+5:30) — system "local time" for all schedule comparisons
IST = timezone(timedelta(hours=5, minutes=30))


def _local_now() -> datetime:
    """Current time in IST (system local time for scheduling)."""
    return datetime.now(IST)

# Cutoff: only contact applicants whose `registered_at` is >= this ISO timestamp.
# If env var missing, default to far-future so we send NOTHING by accident.
MESSAGING_CUTOFF_TS = os.environ.get("MESSAGING_CUTOFF_TS", "9999-12-31T23:59:59+00:00")


def _cutoff_filter() -> dict:
    """Mongo filter fragment — restricts to NEW records only (post-cutoff)."""
    return {"registered_at": {"$gte": MESSAGING_CUTOFF_TS}}


def init_workers(database):
    global _db
    _db = database


async def start_all_workers():
    """Launch all background workers as concurrent tasks."""
    global _running
    if _running:
        return
    _running = True
    _logger.info("Starting background messaging workers")
    _logger.info(f"[CutoffGuard] MESSAGING_CUTOFF_TS={MESSAGING_CUTOFF_TS} — only post-cutoff registrations will be messaged")
    asyncio.create_task(_worker_otp_generator())
    asyncio.create_task(_worker_schedule_link_sender())
    asyncio.create_task(_worker_24h_reminder())
    asyncio.create_task(_worker_otp_expiry())
    asyncio.create_task(_worker_missed_interview())
    asyncio.create_task(_worker_import_rejection_mailer())


# ============ WORKER A: OTP Generator (every 30s) ============

async def _worker_otp_generator():
    """Send OTP within [schedule_time - 3h, schedule_time - 1min] window only.

    Uses IST (system local) consistently for both `now` and the candidate's
    `schedule_time` (which is stored as HH:MM:SS local). Polls every 30s so
    short-notice scheduling (interview within the next 3 hours) gets an OTP
    promptly while still respecting the >=1 minute pre-interview boundary.
    """
    _logger.info("OTP Generator worker started (IST-aware)")
    while True:
        try:
            now = _local_now()
            today_str = now.strftime("%Y-%m-%d")

            # Query ONLY today's interviews where OTP not yet sent (NEW records only)
            cursor = _db.bb_registrations.find({
                **_cutoff_filter(),
                "schedule_date": today_str,
                "is_shortlisted": True,
                "otp_sent": {"$ne": True},
                "schedule_time": {"$nin": [None, ""], "$exists": True},
            })
            docs = await cursor.to_list(None)

            for doc in docs:
                schedule_time_str = (doc.get("schedule_time") or "").strip()
                if not schedule_time_str:
                    continue

                try:
                    parts = schedule_time_str.split(":")
                    hour, minute = int(parts[0]), int(parts[1])
                except (ValueError, IndexError):
                    continue

                # Build full interview datetime in IST (same tz as now)
                interview_dt = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
                window_start = interview_dt - timedelta(hours=3)
                window_end = interview_dt - timedelta(minutes=1)

                # Outside window? — skip. (Short-notice: if interview is within
                # 3h, window_start is in the past so we send immediately.)
                if now < window_start or now > window_end:
                    continue

                # Inside window — generate and send OTP (exactly once via otp_sent flag)
                otp = doc.get("otp") or str(random.randint(100000, 999999))
                otp_expiry_iso = interview_dt.isoformat()
                now_iso = now.isoformat()

                await _db.bb_registrations.update_one(
                    {"_id": doc["_id"]},
                    {"$set": {
                        "otp": otp,
                        "otp_sent": True,
                        "otp_sent_at": now_iso,
                        # camelCase aliases for external integrations
                        "otpGeneratedAt": now_iso,
                        "otpExpiry": otp_expiry_iso,
                    }}
                )

                await _db.registered_candidates.update_many(
                    {"$or": [{"email": doc.get("email", "")}, {"phone": doc.get("phone", "")}]},
                    {"$set": {
                        "otp": otp,
                        "otp_send": "1",
                        "otpGeneratedAt": now_iso,
                        "otpExpiry": otp_expiry_iso,
                    }}
                )

                from messaging import notify_otp
                await notify_otp(
                    doc.get("full_name", ""),
                    doc.get("phone", ""),
                    doc.get("email", ""),
                    doc.get("job_role", ""),
                    otp,
                    today_str,
                    schedule_time_str,
                    is_test=bool(doc.get("isTest")),
                )
                _logger.info(f"[OTP] Sent to {doc.get('email')}, otp={otp}, IST_now={now.strftime('%H:%M')}, window={window_start.strftime('%H:%M')}-{window_end.strftime('%H:%M')}, interview={interview_dt.strftime('%H:%M')}")

        except Exception as e:
            _logger.exception(f"[OTP Worker] Error: {e}")

        await asyncio.sleep(30)


# ============ WORKER B: Schedule Link Sender (every 60s) ============

async def _worker_schedule_link_sender():
    """Send schedule link 5+ minutes after registration for shortlisted applicants
    who have NOT already clicked 'Schedule Interview' on the result page.

    Behaviour:
      - Skips if `schedule_initiated=True` (candidate already navigated to the
        scheduling page within 5 min — no point spamming them).
      - Skips if `schedule_link_sent=True` (idempotent).
      - Cutoff-guarded so legacy registrations are never contacted.
    """
    _logger.info("Schedule Link Sender worker started (5-min delay, schedule_initiated-aware)")
    while True:
        try:
            now = datetime.now(timezone.utc)
            # Pick rows registered >= 5 min ago (the delay window). 24h upper
            # bound prevents re-sending after restart for very old rows.
            five_min_ago = (now - timedelta(minutes=5)).isoformat()
            twenty_four_h_ago = (now - timedelta(hours=24)).isoformat()

            cursor = _db.bb_registrations.find({
                **_cutoff_filter(),
                "is_shortlisted": True,
                "schedule_link_sent": {"$ne": True},
                "schedule_initiated": {"$ne": True},
                "registered_at": {"$lte": five_min_ago,
                                   "$gte": max(twenty_four_h_ago, MESSAGING_CUTOFF_TS)},
            })
            docs = await cursor.to_list(None)

            for doc in docs:
                token = doc.get("schedule_token")
                if not token:
                    continue

                from messaging import notify_shortlisted
                ok = await notify_shortlisted(
                    doc.get("full_name", ""),
                    doc.get("phone", ""),
                    doc.get("email", ""),
                    token,
                    is_test=bool(doc.get("isTest")),
                )

                await _db.bb_registrations.update_one(
                    {"_id": doc["_id"]},
                    {"$set": {
                        "schedule_link_sent": True,
                        "schedule_link_sent_at": now.isoformat(),
                        "shortlist_mail_sent": bool(ok),
                        "shortlist_mail_sent_time": now.isoformat(),
                    }}
                )
                _logger.info(f"[ScheduleLink] Sent to {doc.get('email')} (delay window passed, no schedule_initiated)")

            # Also send rejection notifications for rejected applicants not yet notified (NEW only)
            rejected_cursor = _db.bb_registrations.find({
                **_cutoff_filter(),
                "is_shortlisted": False,
                "reject_notified": {"$ne": True},
                "registered_at": {"$lte": five_min_ago, "$gte": max(twenty_four_h_ago, MESSAGING_CUTOFF_TS)},
            })
            rejected_docs = await rejected_cursor.to_list(None)

            for doc in rejected_docs:
                from messaging import notify_rejected
                await notify_rejected(
                    doc.get("full_name", ""),
                    doc.get("phone", ""),
                    doc.get("email", ""),
                    is_test=bool(doc.get("isTest")),
                )
                await _db.bb_registrations.update_one(
                    {"_id": doc["_id"]},
                    {"$set": {"reject_notified": True, "reject_notified_at": now.isoformat()}}
                )
                _logger.info(f"[Reject] Notified {doc.get('email')}")

            # Send deferred interview mails (NEW only): shortlist sent but interview mail not yet sent
            deferred_cursor = _db.bb_registrations.find({
                **_cutoff_filter(),
                "shortlist_mail_sent": True,
                "interview_mail_sent": {"$ne": True},
                "schedule_date": {"$nin": [None, ""], "$exists": True},
                "schedule_time": {"$nin": [None, ""], "$exists": True},
            })
            deferred_docs = await deferred_cursor.to_list(None)

            for doc in deferred_docs:
                from messaging import notify_schedule_confirmation
                await notify_schedule_confirmation(
                    doc.get("full_name", ""),
                    doc.get("phone", ""),
                    doc.get("email", ""),
                    doc.get("schedule_date", ""),
                    doc.get("schedule_time", ""),
                    is_test=bool(doc.get("isTest")),
                )
                await _db.bb_registrations.update_one(
                    {"_id": doc["_id"]},
                    {"$set": {"interview_mail_sent": True, "interview_mail_sent_at": now.isoformat()}}
                )
                _logger.info(f"[InterviewMail] Deferred send to {doc.get('email')}")

        except Exception as e:
            _logger.error(f"[ScheduleLink Worker] Error: {e}")

        await asyncio.sleep(60)


# ============ WORKER C: 24h Reminder (every 5 min) ============

async def _worker_24h_reminder():
    """Remind shortlisted applicants who haven't scheduled after 24h."""
    _logger.info("24h Reminder worker started")
    while True:
        try:
            now = datetime.now(timezone.utc)
            twenty_four_h_ago = (now - timedelta(hours=24)).isoformat()

            # Find applicants (NEW only): link sent > 24h ago, not scheduled, no reminder sent
            cursor = _db.bb_registrations.find({
                **_cutoff_filter(),
                "is_shortlisted": True,
                "schedule_link_sent": True,
                "schedule_date": {"$in": [None, ""]},
                "reminder_24h_sent": {"$ne": True},
                "schedule_link_sent_at": {"$lte": twenty_four_h_ago},
            })
            docs = await cursor.to_list(None)

            for doc in docs:
                token = doc.get("schedule_token")
                if not token:
                    continue

                from messaging import notify_schedule_reminder
                await notify_schedule_reminder(
                    doc.get("full_name", ""),
                    doc.get("phone", ""),
                    doc.get("email", ""),
                    token,
                    is_test=bool(doc.get("isTest")),
                )

                await _db.bb_registrations.update_one(
                    {"_id": doc["_id"]},
                    {"$set": {"reminder_24h_sent": True, "reminder_24h_sent_at": now.isoformat()}}
                )
                _logger.info(f"[24hReminder] Sent to {doc.get('email')}")

        except Exception as e:
            _logger.error(f"[24hReminder Worker] Error: {e}")

        await asyncio.sleep(300)  # 5 minutes


# ============ WORKER D: OTP Expiry (every 60s) ============

async def _worker_otp_expiry():
    """Expire OTPs that were sent more than 8 hours ago."""
    _logger.info("OTP Expiry worker started")
    while True:
        try:
            now = datetime.now(timezone.utc)
            eight_hours_ago = (now - timedelta(hours=8)).isoformat()

            # Find registrations (NEW only) with OTP sent > 8h ago and not yet expired
            cursor = _db.bb_registrations.find({
                **_cutoff_filter(),
                "otp_sent": True,
                "otp_expired": {"$ne": True},
                "otp_verified": {"$ne": True},
                "otp_sent_at": {"$lte": eight_hours_ago},
            })
            docs = await cursor.to_list(None)

            for doc in docs:
                await _db.bb_registrations.update_one(
                    {"_id": doc["_id"]},
                    {"$set": {"otp_expired": True, "otp_expired_at": now.isoformat()}}
                )
                _logger.info(f"[OTP Expiry] Expired OTP for {doc.get('email')}")

        except Exception as e:
            _logger.error(f"[OTP Expiry Worker] Error: {e}")

        await asyncio.sleep(60)


# ============ WORKER E: Missed Interview Auto-Status (every 2 min) ============

async def _worker_missed_interview():
    """Mark applicants as 'Missed' if interview time passed and OTP not verified. Send reminder."""
    _logger.info("Missed Interview worker started")
    while True:
        try:
            now = datetime.now(timezone.utc)
            today_str = now.strftime("%Y-%m-%d")

            # Find scheduled interviews (NEW only) for today/past that weren't attended
            cursor = _db.bb_registrations.find({
                **_cutoff_filter(),
                "status": "Interview Scheduled",
                "otp_verified": {"$ne": True},
                "missed_marked": {"$ne": True},
                "schedule_date": {"$lte": today_str},
                "schedule_time": {"$nin": [None, ""], "$exists": True},
            })
            docs = await cursor.to_list(None)

            for doc in docs:
                schedule_date = doc.get("schedule_date", "")
                schedule_time_str = (doc.get("schedule_time") or "").strip()
                if not schedule_time_str:
                    continue

                try:
                    parts = schedule_time_str.split(":")
                    hour, minute = int(parts[0]), int(parts[1])
                except (ValueError, IndexError):
                    continue

                # Build interview datetime
                try:
                    from datetime import date as date_type
                    y, m, d = map(int, schedule_date.split("-"))
                    interview_dt = datetime(y, m, d, hour, minute, 0, tzinfo=timezone.utc)
                except (ValueError, IndexError):
                    continue

                # Only mark missed if interview time + 2 hours has passed (grace period)
                if now < interview_dt + timedelta(hours=2):
                    continue

                # Mark as missed
                await _db.bb_registrations.update_one(
                    {"_id": doc["_id"]},
                    {"$set": {"status": "Missed", "missed_marked": True, "missed_at": now.isoformat()}}
                )

                # Update registered_candidates
                await _db.registered_candidates.update_many(
                    {"$or": [{"email": doc.get("email", "")}, {"phone": doc.get("phone", "")}]},
                    {"$set": {"result_status": "Missed"}}
                )

                # Send missed reminder with reschedule link
                token = doc.get("schedule_token")
                if token:
                    from messaging import notify_missed_reminder
                    await notify_missed_reminder(
                        doc.get("full_name", ""),
                        doc.get("phone", ""),
                        doc.get("email", ""),
                        doc.get("job_role", ""),
                        schedule_date,
                        schedule_time_str,
                        token,
                        is_test=bool(doc.get("isTest")),
                    )

                _logger.info(f"[Missed] Marked {doc.get('email')} as Missed")

        except Exception as e:
            _logger.error(f"[Missed Interview Worker] Error: {e}")

        await asyncio.sleep(120)  # 2 minutes


async def _worker_import_rejection_mailer():
    """Continuously mail (Email + WhatsApp) any applicant whose status was set
    to 'Rejected' AFTER `MESSAGING_CUTOFF_TS` and not yet notified.

    Scope:
      - Reads `bb_applicant_updates` (the canonical store updated by Update Scores
        / bulk imports / admin UI).
      - Cutoff-guarded: `updated_at >= MESSAGING_CUTOFF_TS` so historical data
        never receives a bulk send.
      - Idempotent: sets `rejection_notified=True` after a successful send.
      - Never re-sends if `rejection_notified=True` (or legacy
        `import_rejection_notified=True`).
      - Polls every 60s so admins see prompt delivery.
    """
    _logger.info("Rejection mailer worker started (continuous)")
    while _running:
        try:
            cursor = _db.bb_applicant_updates.find({
                "status": "Rejected",
                "rejection_notified": {"$ne": True},
                "import_rejection_notified": {"$ne": True},
                "updated_at": {"$gte": MESSAGING_CUTOFF_TS},
            })

            sent = 0
            async for doc in cursor:
                email = (doc.get("email") or "").strip()
                phone = (doc.get("phone") or "").strip()
                name = doc.get("name") or "Candidate"
                if not email and not phone:
                    continue

                try:
                    from messaging import notify_rejected
                    ok = await notify_rejected(name, phone, email, is_test=bool(doc.get("isTest")))
                    await _db.bb_applicant_updates.update_one(
                        {"_id": doc["_id"]},
                        {"$set": {
                            "rejection_notified": True,
                            "rejection_notified_at": _local_now().isoformat(),
                            "rejection_send_ok": bool(ok),
                        }},
                    )
                    sent += 1
                    _logger.info(f"[Reject:UI] Sent to {email} ok={ok}")
                except Exception as send_err:
                    _logger.error(f"[Reject:UI] Send failed for {email}: {send_err}")

            if sent:
                _logger.info(f"[Reject:UI] Batch complete — {sent} rejection notifications sent")

        except Exception as e:
            _logger.error(f"[Rejection Mailer Worker] Error: {e}")

        await asyncio.sleep(60)
