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
    """Mongo filter fragment — restricts to NEW records only (post-cutoff)
    AND excludes superseded rows. iter92 — every worker that scans
    `bb_registrations` uses this so stale rows from a tester's earlier
    re-registration session can NEVER receive a fresh OTP or template send.
    Re-registration (bb_modules.py:register_applicant) flips `superseded=True`
    on all prior rows for the same email/phone before inserting the new row.
    """
    return {
        "registered_at": {"$gte": MESSAGING_CUTOFF_TS},
        "superseded": {"$ne": True},
    }


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
    _heartbeat = 0
    while True:
        try:
            now = _local_now()
            today_str = now.strftime("%Y-%m-%d")

            # iter121 — Per-channel retry. The cursor now picks up rows where
            # ANY channel hasn't sent yet (`otp_wa_sent` OR `otp_email_sent`),
            # not just where the legacy `otp_sent` umbrella flag is unset.
            # This fixes the production symptom where WhatsApp went out but
            # Email failed once and was never retried because the worker
            # mistakenly set `otp_sent=True` after the first partial success
            # (see iter107 comment thread above — the cursor filter never
            # matched the documented per-channel retry intent).
            cursor = _db.bb_registrations.find({
                **_cutoff_filter(),
                "schedule_date": today_str,
                "is_shortlisted": True,
                "$or": [
                    {"otp_wa_sent": {"$ne": True}},
                    {"otp_email_sent": {"$ne": True}},
                ],
                "schedule_time": {"$nin": [None, ""], "$exists": True},
            })
            docs = await cursor.to_list(None)

            # iter107 — Visible heartbeat every ~5 min (10 ticks * 30s) proves
            # the worker is alive even when no candidates are in the window.
            if _heartbeat % 10 == 0:
                _logger.info(
                    f"[OTP:HEARTBEAT] alive ist={now.strftime('%H:%M:%S')} "
                    f"today={today_str} pending_today={len(docs)}"
                )
            _heartbeat += 1

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
                    # Detailed per-candidate trace so admins can see why OTP
                    # hasn't fired yet (e.g. interview at 18:00, currently 12:00).
                    _logger.info(
                        f"[OTP:SKIP_WINDOW] email={doc.get('email')} "
                        f"interview={interview_dt.strftime('%H:%M')} "
                        f"window={window_start.strftime('%H:%M')}-{window_end.strftime('%H:%M')} "
                        f"now={now.strftime('%H:%M')}"
                    )
                    continue

                # iter107 — Atomic CAS guard. Mirror the schedule_link_sender
                # pattern: claim the row by flipping `otp_dispatch_in_progress`
                # FIRST so concurrent ticks / process restarts can't double-fire.
                # The actual `otp_sent=True` flag is set ONLY after notify_otp
                # completes successfully, so a transient failure now leaves the
                # row eligible for retry on the next tick.
                otp = doc.get("otp") or str(random.randint(100000, 999999))
                otp_expiry_iso = interview_dt.isoformat()
                now_iso = now.isoformat()
                # iter121 — Per-channel retry. Examine each channel's current
                # flag and only attempt the ones still unsent. Skip the row
                # entirely if BOTH are already done.
                wa_already_sent = bool(doc.get("otp_wa_sent"))
                em_already_sent = bool(doc.get("otp_email_sent"))
                if wa_already_sent and em_already_sent:
                    continue
                channels_to_send = []
                if not wa_already_sent:
                    channels_to_send.append("wa")
                if not em_already_sent:
                    channels_to_send.append("email")

                cas = await _db.bb_registrations.update_one(
                    {"_id": doc["_id"],
                     "otp_dispatch_in_progress": {"$ne": True}},
                    {"$set": {
                        "otp": otp,
                        "otp_dispatch_in_progress": True,
                        "otp_dispatch_started_at": now_iso,
                        "otpGeneratedAt": now_iso,
                        "otpExpiry": otp_expiry_iso,
                    }},
                )
                if cas.modified_count == 0:
                    # Another tick / process already claimed this row.
                    _logger.info(f"[OTP:SKIP_CLAIMED] email={doc.get('email')} already in progress")
                    continue

                # Mirror OTP onto the secondary collection (does NOT gate sending).
                await _db.registered_candidates.update_many(
                    {"$or": [{"email": doc.get("email", "")}, {"phone": doc.get("phone", "")}]},
                    {"$set": {
                        "otp": otp,
                        "otp_send": "1",
                        "otpGeneratedAt": now_iso,
                        "otpExpiry": otp_expiry_iso,
                    }}
                )

                _logger.info(
                    f"[OTP:DISPATCH_START] email={doc.get('email')} phone={doc.get('phone')} "
                    f"otp={otp} interview={interview_dt.strftime('%Y-%m-%d %H:%M')} IST "
                    f"channels_to_send={channels_to_send}"
                )

                wa_ok, em_ok = wa_already_sent, em_already_sent
                send_err = None
                try:
                    from messaging import notify_otp
                    result = await notify_otp(
                        doc.get("full_name", ""),
                        doc.get("phone", ""),
                        doc.get("email", ""),
                        doc.get("job_role", ""),
                        otp,
                        today_str,
                        schedule_time_str,
                        is_test=bool(doc.get("isTest")),
                        # iter121 — Only attempt the channels still unsent.
                        # A previously-successful channel must NOT be re-dispatched
                        # (avoids duplicate WhatsApp/email to the candidate).
                        send_wa=not wa_already_sent,
                        send_email_channel=not em_already_sent,
                    )
                    res_wa, res_em = result if isinstance(result, tuple) else (bool(result), False)
                    # Merge: keep already-true flags, OR in new results.
                    wa_ok = wa_already_sent or res_wa
                    em_ok = em_already_sent or res_em
                except Exception as ne:
                    send_err = ne
                    _logger.exception(f"[OTP:NOTIFY_EXC] email={doc.get('email')} err={ne!r}")

                # iter121 — Persist per-channel flags + ALSO the umbrella
                # `otp_sent` flag (set True ONLY when BOTH channels are done).
                # If only one channel succeeded this tick, leave `otp_sent`
                # alone so the cursor's `$or` filter picks the row up next
                # tick for the still-failed channel.
                any_ok = bool(wa_ok or em_ok)
                both_ok = bool(wa_ok and em_ok)
                if any_ok:
                    set_fields = {
                        "otp_wa_sent": bool(wa_ok),
                        "otp_email_sent": bool(em_ok),
                        "otp_dispatch_in_progress": False,
                    }
                    if wa_ok:
                        set_fields["otp_wa_sent_at"] = now_iso
                    if em_ok:
                        set_fields["otp_email_sent_at"] = now_iso
                    if both_ok:
                        set_fields["otp_sent"] = True
                        set_fields["otp_sent_at"] = now_iso
                    await _db.bb_registrations.update_one(
                        {"_id": doc["_id"]}, {"$set": set_fields},
                    )
                    _logger.info(
                        f"[OTP:DISPATCH_DONE] email={doc.get('email')} "
                        f"wa_ok={wa_ok} em_ok={em_ok} otp={otp}"
                    )
                else:
                    # Both channels failed — release the claim so next tick retries.
                    await _db.bb_registrations.update_one(
                        {"_id": doc["_id"]},
                        {"$set": {
                            "otp_dispatch_in_progress": False,
                            "otp_dispatch_last_error_at": now_iso,
                            "otp_dispatch_last_error": (repr(send_err)[:200] if send_err else "both_channels_returned_false"),
                        }},
                    )
                    _logger.error(
                        f"[OTP:DISPATCH_FAIL] email={doc.get('email')} "
                        f"wa_ok={wa_ok} em_ok={em_ok} err={send_err!r} — will retry next tick"
                    )

        except Exception as e:
            _logger.exception(f"[OTP Worker] Error: {e}")

        await asyncio.sleep(30)


# ============ WORKER B: Schedule Link Sender (every 60s) ============

async def _worker_schedule_link_sender():
    """Retry safety-net for shortlisted applicants whose inline schedule-link
    send failed (network blip / AiSensy hiccup). Iter80 — the 5-minute delay
    is REMOVED; the inline send in `register_applicant._instant_notify()` runs
    immediately on shortlisting and marks `schedule_link_sent=True`. This worker
    only re-tries rows that are still missing the flag.

    Behaviour:
      - Skips if `schedule_link_sent=True` (idempotent — inline send already done).
      - Skips if `schedule_initiated=True` (candidate has clicked the CTA).
      - Cutoff-guarded so legacy registrations are never contacted.
    """
    _logger.info("Schedule Link Sender worker started (retry safety-net, no delay)")
    while True:
        try:
            now = datetime.now(timezone.utc)
            # Iter80 — No `five_min_ago` filter. Pick up missing rows immediately,
            # bounded by a 24h upper bound so post-restart we never re-send to old rows.
            twenty_four_h_ago = (now - timedelta(hours=24)).isoformat()

            cursor = _db.bb_registrations.find({
                **_cutoff_filter(),
                "is_shortlisted": True,
                "schedule_link_sent": {"$ne": True},
                "schedule_initiated": {"$ne": True},
                "registered_at": {"$gte": max(twenty_four_h_ago, MESSAGING_CUTOFF_TS)},
            })
            docs = await cursor.to_list(None)

            for doc in docs:
                token = doc.get("schedule_token")
                if not token:
                    continue

                # iter90 — Atomic CAS guard. Mirror the inline _instant_notify
                # pattern: claim the row by flipping schedule_link_sent FIRST.
                # If modified_count==0, the inline task already won; skip silently.
                cas = await _db.bb_registrations.update_one(
                    {"_id": doc["_id"], "schedule_link_sent": {"$ne": True}},
                    {"$set": {
                        "schedule_link_sent": True,
                        "schedule_link_sent_at": now.isoformat(),
                    }},
                )
                if cas.modified_count == 0:
                    # Another runner (inline _instant_notify) already grabbed it.
                    continue

                from messaging import notify_shortlisted
                ok = await notify_shortlisted(
                    doc.get("full_name", ""),
                    doc.get("phone", ""),
                    doc.get("email", ""),
                    token,
                    is_test=bool(doc.get("isTest")),
                )
                wa_ok, em_ok = ok if isinstance(ok, tuple) else (bool(ok), False)
                await _db.bb_registrations.update_one(
                    {"_id": doc["_id"]},
                    {"$set": {
                        "shortlist_wa_sent": wa_ok,
                        "shortlist_wa_sent_at": now.isoformat() if wa_ok else None,
                        "shortlist_email_sent": em_ok,
                        "shortlist_email_sent_at": now.isoformat() if em_ok else None,
                        "shortlist_mail_sent": bool(em_ok),
                        "shortlist_mail_sent_time": now.isoformat(),
                    }}
                )
                _logger.info(f"[ScheduleLink:Retry] Sent to {doc.get('email')} ok=(wa={wa_ok}, em={em_ok})")

            # iter88 — Rejection sends are NO LONGER fired from this worker.
            # Form-condition rejections are now flagged with `rejection_pending=True`
            # by `_instant_notify` (bb_modules.py) and dispatched ONLY by
            # `_worker_import_rejection_mailer` at REJECTION_DISPATCH_HOUR IST
            # (default 19:00). The previous code here fired the AiSensy "Reject"
            # campaign within 60s of every non-shortlisted registration, which
            # broke the deferral contract and caused rejection WhatsApp to leak
            # into the shortlist flow window. DO NOT re-introduce immediate
            # rejection sends in this worker.

            # Send deferred interview mails (NEW only): shortlist sent but interview mail not yet sent
            # iter125c — Honour the inline `interview_mail_sent_in_progress`
            # CAS lock so a concurrent submit_schedule HTTP handler isn't
            # duplicated by this worker. The lock is released by the
            # inline path after notify_schedule_confirmation completes.
            deferred_cursor = _db.bb_registrations.find({
                **_cutoff_filter(),
                "shortlist_mail_sent": True,
                "interview_mail_sent": {"$ne": True},
                "interview_mail_sent_in_progress": {"$ne": True},
                "schedule_date": {"$nin": [None, ""], "$exists": True},
                "schedule_time": {"$nin": [None, ""], "$exists": True},
            })
            deferred_docs = await deferred_cursor.to_list(None)

            for doc in deferred_docs:
                # iter125c — Atomic CAS claim: only one runner may send for
                # this row, even across worker restarts / concurrent ticks.
                cas = await _db.bb_registrations.update_one(
                    {"_id": doc["_id"],
                     "interview_mail_sent": {"$ne": True},
                     "interview_mail_sent_in_progress": {"$ne": True}},
                    {"$set": {
                        "interview_mail_sent_in_progress": True,
                        "interview_mail_sent_in_progress_at": now.isoformat(),
                    }},
                )
                if cas.modified_count == 0:
                    _logger.info(
                        f"[InterviewMail] SKIP duplicate — CAS lost for {doc.get('email')}"
                    )
                    continue
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
                    {"$set": {"interview_mail_sent": True, "interview_mail_sent_at": now.isoformat()},
                     "$unset": {
                        "interview_mail_sent_in_progress": "",
                        "interview_mail_sent_in_progress_at": "",
                     }}
                )
                _logger.info(f"[InterviewMail] Deferred send to {doc.get('email')}")

        except Exception as e:
            _logger.error(f"[ScheduleLink Worker] Error: {e}")

        await asyncio.sleep(60)


# ============ WORKER C: 24h Reminder (every 5 min) ============

async def _worker_24h_reminder():
    """Remind shortlisted applicants who haven't scheduled after 24h.

    iter91 — Added a 7-day UPPER bound on `schedule_link_sent_at` to prevent
    stale tester re-registration rows (from days/weeks earlier test sessions)
    from being re-messaged with phantom data. Anything older than 7 days is
    considered abandoned and is no longer eligible for the reminder.
    """
    _logger.info("24h Reminder worker started")
    while True:
        try:
            now = datetime.now(timezone.utc)
            twenty_four_h_ago = (now - timedelta(hours=24)).isoformat()
            seven_days_ago = (now - timedelta(days=7)).isoformat()

            # Find applicants (NEW only): link sent between 24h and 7d ago,
            # not scheduled, no reminder sent, with REQUIRED template fields.
            cursor = _db.bb_registrations.find({
                **_cutoff_filter(),
                "is_shortlisted": True,
                "schedule_link_sent": True,
                "schedule_date": {"$in": [None, ""]},
                "reminder_24h_sent": {"$ne": True},
                "schedule_link_sent_at": {"$lte": twenty_four_h_ago, "$gte": seven_days_ago},
            })
            docs = await cursor.to_list(None)

            for doc in docs:
                token = doc.get("schedule_token")
                name = (doc.get("full_name") or "").strip()
                phone = (doc.get("phone") or "").strip()
                email = (doc.get("email") or "").strip()
                # iter91 FIX 2G — abort if any required template field is missing.
                # Never send a reminder with a placeholder/dummy name.
                if not token or not name or (not email and not phone):
                    _logger.warning(
                        f"[24hReminder] SKIP — missing required field "
                        f"(name={bool(name)} email={bool(email)} phone={bool(phone)} "
                        f"token={bool(token)}) doc_id={doc.get('_id')}"
                    )
                    # Flag as sent so the worker doesn't keep retrying this broken row.
                    await _db.bb_registrations.update_one(
                        {"_id": doc["_id"]},
                        {"$set": {"reminder_24h_sent": True,
                                   "reminder_24h_skipped_at": now.isoformat(),
                                   "reminder_24h_skip_reason": "missing_required_field"}}
                    )
                    continue

                from messaging import notify_schedule_reminder
                await notify_schedule_reminder(name, phone, email, token, is_test=bool(doc.get("isTest")))

                await _db.bb_registrations.update_one(
                    {"_id": doc["_id"]},
                    {"$set": {"reminder_24h_sent": True, "reminder_24h_sent_at": now.isoformat()}}
                )
                _logger.info(f"[24hReminder] Sent to {email}")

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
    _logger.info("Missed Interview worker started (IST-aware)")
    _heartbeat = 0
    while True:
        try:
            # iter114 — Use IST-local `now` so the "interview time + 1h"
            # trigger window matches `schedule_date` + `schedule_time` which
            # are stored as IST-local. The earlier UTC implementation made
            # the worker think every interview was ~5.5h in the future and
            # silently skipped EVERY candidate.
            now = _local_now()
            today_str = now.strftime("%Y-%m-%d")
            seven_days_ago_str = (now - timedelta(days=7)).strftime("%Y-%m-%d")

            # Find scheduled interviews (NEW only) for today/past that weren't attended
            cursor = _db.bb_registrations.find({
                **_cutoff_filter(),
                "status": "Interview Scheduled",
                "otp_verified": {"$ne": True},
                "missed_marked": {"$ne": True},
                "schedule_date": {"$lte": today_str, "$gte": seven_days_ago_str},
                "schedule_time": {"$nin": [None, ""], "$exists": True},
            })
            docs = await cursor.to_list(None)

            # iter114 — Visible heartbeat every ~5 min (10 ticks * 30s) so
            # admins can observe the worker even when no candidates are eligible.
            if _heartbeat % 10 == 0:
                _logger.info(
                    f"[Missed:HEARTBEAT] alive ist={now.strftime('%H:%M:%S')} "
                    f"today={today_str} scanned={len(docs)}"
                )
            _heartbeat += 1

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

                # Build interview datetime IN IST (same tz as `now`).
                try:
                    y, m, d = map(int, schedule_date.split("-"))
                    interview_dt = datetime(y, m, d, hour, minute, 0, tzinfo=now.tzinfo)
                except (ValueError, IndexError):
                    continue

                # iter114 — Detailed eligibility trace so admins can see why
                # any specific candidate hasn't been sent the reminder yet.
                trigger_dt = interview_dt + timedelta(hours=1)
                if now < trigger_dt:
                    _logger.info(
                        f"[Missed:SKIP_WINDOW] email={doc.get('email')} "
                        f"interview={interview_dt.strftime('%Y-%m-%d %H:%M IST')} "
                        f"trigger_at={trigger_dt.strftime('%H:%M')} now={now.strftime('%H:%M')}"
                    )
                    continue
                _logger.info(
                    f"[Missed:ELIGIBLE] email={doc.get('email')} "
                    f"interview={interview_dt.strftime('%Y-%m-%d %H:%M IST')} "
                    f"now={now.strftime('%H:%M')} (>={trigger_dt.strftime('%H:%M')})"
                )

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
                # iter113 — Lazily generate a `schedule_token` when missing so
                # the reschedule link still works for legacy rows that never
                # had one persisted (else the entire missed-reminder was
                # silently skipped — observed in production).
                if not token:
                    try:
                        import secrets
                        token = secrets.token_urlsafe(32)
                        await _db.bb_registrations.update_one(
                            {"_id": doc["_id"]},
                            {"$set": {"schedule_token": token, "schedule_token_generated_at": now.isoformat()}},
                        )
                    except Exception as _te:
                        _logger.warning(f"[Missed] token generation failed for {doc.get('email')}: {_te!r}")
                        token = None
                name = (doc.get("full_name") or "").strip()
                phone = (doc.get("phone") or "").strip()
                email = (doc.get("email") or "").strip()
                # iter122 — Per-channel idempotency scoped to `schedule_token`.
                # When a candidate reschedules, the schedule submission clears
                # `missed_marked` (and may clear `missed_reminder_sent`) so the
                # worker re-fires both channels on the SAME schedule_token if
                # the new interview is also past. AiSensy dedupes WhatsApp
                # within a window but Resend does NOT, so users observed 2
                # follow-up emails (real production complaint).
                #
                # Fix: store per-channel flags + the token they were dispatched
                # for. On the next tick, skip the channel if the stored
                # token still matches AND the channel is True. If the token
                # changed (genuine new schedule), treat as fresh dispatch.
                stored_token = doc.get("missed_reminder_token") or ""
                token_matches = bool(token) and stored_token == token
                wa_already = token_matches and bool(doc.get("missed_reminder_wa_sent"))
                em_already = token_matches and bool(doc.get("missed_reminder_email_sent"))
                if wa_already and em_already:
                    _logger.info(
                        f"[Missed:SKIP_ALREADY_SENT] email={email} token={token[:10] if token else None}… "
                        f"both channels already delivered for this schedule"
                    )
                    continue
                # iter113 — abort if any required template field is missing.
                if token and name and (email or phone):
                    _logger.info(
                        f"[Missed:DISPATCH] email={email} phone={phone} "
                        f"role={doc.get('job_role','')!r} interview={schedule_date} {schedule_time_str} "
                        f"channels_to_send={['wa']*(not wa_already) + ['email']*(not em_already)}"
                    )
                    wa_ok, em_ok = wa_already, em_already
                    try:
                        from messaging import notify_missed_reminder
                        result = await notify_missed_reminder(
                            name, phone, email,
                            doc.get("job_role", ""),
                            schedule_date,
                            schedule_time_str,
                            token,
                            is_test=bool(doc.get("isTest")),
                            send_wa=not wa_already,
                            send_email_channel=not em_already,
                        )
                        res_wa, res_em = result if isinstance(result, tuple) else (bool(result), False)
                        # Merge: keep already-True flags, OR in new results.
                        wa_ok = wa_already or res_wa
                        em_ok = em_already or res_em
                    except Exception as _me:
                        _logger.exception(f"[Missed:DISPATCH] FAILED email={email}: {_me!r}")
                    _logger.info(f"[Missed:DISPATCH_DONE] email={email} wa_ok={wa_ok} em_ok={em_ok}")
                    # iter122 — Persist per-channel state scoped to schedule_token.
                    if wa_ok or em_ok:
                        await _db.bb_registrations.update_one(
                            {"_id": doc["_id"]},
                            {"$set": {
                                "missed_reminder_wa_sent": bool(wa_ok),
                                "missed_reminder_email_sent": bool(em_ok),
                                "missed_reminder_token": token,
                                "missed_reminder_sent_at": now.isoformat(),
                            }},
                        )
                elif token:
                    _logger.warning(
                        f"[Missed] SKIP missed-reminder send — missing required field "
                        f"(name={bool(name)} email={bool(email)} phone={bool(phone)}) "
                        f"doc_id={doc.get('_id')}"
                    )

                _logger.info(f"[Missed] Marked {doc.get('email')} as Missed")

        except Exception as e:
            _logger.error(f"[Missed Interview Worker] Error: {e}")

        await asyncio.sleep(120)  # 2 minutes


async def _worker_import_rejection_mailer():
    """iter88 — Evening rejection dispatcher (default 19:00 IST).

    Runs every 5 minutes. ONLY performs sends when the LOCAL (IST) hour matches
    `REJECTION_DISPATCH_HOUR` env var (default 19). Override the env var
    temporarily for testing, then revert to 19.

    Two sources are processed in a single tick:
      A) `bb_applicant_updates` with status='Rejected' — post-interview rejections
         set by recruiters via Update Scores / bulk import.
      B) `bb_registrations` with rejection_pending=True — form-condition rejections
         deferred from `_instant_notify` during /api/pub/register.

    Idempotency: each source row sets `rejection_sent=True` + `rejection_sent_at`
    after a successful send. Records already flagged (including all historical
    rows updated by the one-shot backfill migration) are skipped forever.

    Cutoff guard: source A still respects `MESSAGING_CUTOFF_TS`. Source B is
    naturally post-cutoff since it's only written by new registrations.
    """
    try:
        _dispatch_hour = int(os.environ.get("REJECTION_DISPATCH_HOUR", "19"))
        if not (0 <= _dispatch_hour <= 23):
            raise ValueError("must be 0-23")
    except (ValueError, TypeError) as _e:
        _logger.warning(f"[RejectScheduler:INIT] invalid REJECTION_DISPATCH_HOUR ({_e!r}), defaulting to 19")
        _dispatch_hour = 19
    _logger.info(f"[RejectScheduler:INIT] dispatch_hour={_dispatch_hour:02d}:00 IST cutoff={MESSAGING_CUTOFF_TS} poll_every=300s")
    _logger.info("[RejectScheduler:STARTED] worker loop entering")
    # iter101 — Visible heartbeat. Without this, admins inspecting logs
    # before 19:00 IST see no scheduler activity and assume the worker died.
    # We log the "before-window" branch at INFO every ~30 min so the loop
    # presence is always observable. The 5-min poll cadence is unchanged.
    _heartbeat_counter = 0
    while _running:
        try:
            now_local = _local_now()  # IST
            if now_local.hour < _dispatch_hour:
                # Emit HEARTBEAT every ~30 min (1 in 6 ticks) so log volume
                # stays low while still proving the loop is alive.
                if _heartbeat_counter % 6 == 0:
                    _logger.info(
                        f"[RejectScheduler:HEARTBEAT] alive ist={now_local.isoformat()} "
                        f"hour={now_local.hour} target>={_dispatch_hour} status=sleeping_until_window"
                    )
                _heartbeat_counter += 1
                await asyncio.sleep(300)
                continue
            _heartbeat_counter = 0  # reset once we enter the window

            _logger.info(f"[RejectScheduler:TICK] window=OPEN ist={now_local.isoformat()} target_hour={_dispatch_hour} cutoff={MESSAGING_CUTOFF_TS}")
            _logger.info(f"[RejectScheduler:TIME_CHECK] ok hour={now_local.hour}>={_dispatch_hour}")
            sent = 0
            skipped_no_name = 0
            skipped_send_failed = 0
            skipped_tester = 0

            # iter126 — Tester-credential exclusion. Score Imports repeatedly
            # mark the tester row (rishi.nayak@blubridge.com / 9443109903 etc.)
            # as status='Rejected'; with `rejection_sent` cleared on every
            # re-registration reset, this fired a phantom "Final Reject"
            # WhatsApp + Email DAILY at REJECTION_DISPATCH_HOUR. Testers must
            # opt-in via Manual Applicant Alerts; auto-dispatch is suppressed.
            import re as _re
            tester_emails: set = set()
            tester_phones: set = set()
            try:
                async for _tc in _db.bb_test_credentials.find({}, {"_id": 0, "email": 1, "phone": 1}):
                    _em = (_tc.get("email") or "").strip().lower()
                    _ph_raw = _re.sub(r"\D", "", str(_tc.get("phone") or ""))
                    if _em:
                        tester_emails.add(_em)
                    if _ph_raw:
                        tester_phones.add(_ph_raw[-10:])
            except Exception as _tc_err:
                _logger.warning(f"[RejectScheduler:TESTER_LOAD_FAIL] {_tc_err!r}")
            _logger.info(
                f"[RejectScheduler:TESTERS] emails={sorted(tester_emails)} phones={sorted(tester_phones)} "
                "(these recipients are EXCLUDED from auto-rejection)"
            )

            # ---- Source A: post-interview rejections (bb_applicant_updates) ----
            filter_a = {
                "status": "Rejected",
                "rejection_sent": {"$ne": True},
                "rejection_notified": {"$ne": True},
                "import_rejection_notified": {"$ne": True},
                "updated_at": {"$gte": MESSAGING_CUTOFF_TS},
            }
            count_a = await _db.bb_applicant_updates.count_documents(filter_a)
            _logger.info(f"[RejectFetch] sourceA=bb_applicant_updates pending_rejections={count_a} filter={filter_a}")
            cursor_a = _db.bb_applicant_updates.find(filter_a)
            async for doc in cursor_a:
                email = (doc.get("email") or "").strip()
                phone = (doc.get("phone") or "").strip()
                # iter126 — Tester exclusion (see TESTERS log line above).
                _em_norm = email.lower()
                _ph_norm = _re.sub(r"\D", "", phone)[-10:] if phone else ""
                if _em_norm in tester_emails or (_ph_norm and _ph_norm in tester_phones):
                    skipped_tester += 1
                    # Mark the row so it stops matching the filter on subsequent
                    # ticks — testers must opt-in via Manual Alerts, this is a
                    # terminal skip not a transient one.
                    await _db.bb_applicant_updates.update_one(
                        {"_id": doc["_id"]},
                        {"$set": {
                            "rejection_sent": False,
                            "rejection_auto_skipped_tester": True,
                            "rejection_auto_skipped_at": now_local.isoformat(),
                            "rejection_notified": True,
                            "rejection_notified_at": now_local.isoformat(),
                        }},
                    )
                    _logger.info(
                        f"[RejectSkip:A:TESTER] email={email!r} phone={phone!r} "
                        f"reason=bb_test_credentials_match doc_id={doc.get('_id')}"
                    )
                    continue
                # iter115 — Canonical-latest lookup for Source A (mirrors the
                # Source B fix from iter113). `bb_applicant_updates.name` /
                # `.job_role` are written once at score-update time and are
                # NEVER refreshed on tester re-registration (only `scores`,
                # `status`, rejection flags get reset). Result: a tester who
                # re-registers as "May 21 Rishi" still received rejections
                # addressed to the stale "Final_Test_Rishi" because Source A
                # trusted the stale local row. Fix: read the latest
                # `pipeline_data` row (sort registered_at DESC) and PREFER
                # its name / job_role over the local row's values.
                pd_doc_a = None
                if email or phone:
                    pd_query = {"$or": []}
                    if email:
                        pd_query["$or"].append({"email": email})
                    if phone:
                        pd_query["$or"].append({"phone": phone})
                    pd_doc_a = await _db.pipeline_data.find_one(
                        pd_query,
                        {"_id": 0, "name": 1, "job_role": 1, "job_title": 1, "_normalized_job_role": 1, "registered_at": 1},
                        sort=[("registered_at", -1)],
                    )
                stale_name = (doc.get("name") or "").strip()
                stale_role = (doc.get("job_role") or doc.get("job_title") or "").strip()
                fresh_name = ((pd_doc_a or {}).get("name") or "").strip()
                fresh_role = (
                    (pd_doc_a or {}).get("job_role")
                    or (pd_doc_a or {}).get("job_title")
                    or ""
                ).strip()
                name = fresh_name or stale_name
                job_role = fresh_role or stale_role
                if pd_doc_a and (fresh_name != stale_name or fresh_role != stale_role):
                    _logger.info(
                        f"[RejectSend:A:CANONICAL] email={email!r} phone={phone!r} "
                        f"local_name={stale_name!r} → canonical_name={fresh_name!r} "
                        f"local_role={stale_role!r} → canonical_role={fresh_role!r} "
                        f"pd_registered_at={(pd_doc_a or {}).get('registered_at')!r}"
                    )
                # iter88 — ABORT if any required template field is missing.
                # Never send a rejection with a placeholder/dummy name.
                if not name or (not email and not phone):
                    skipped_no_name += 1
                    _logger.warning(
                        f"[RejectSkip:A] reason=missing_field name={bool(name)} "
                        f"email={bool(email)} phone={bool(phone)} doc_id={doc.get('_id')}"
                    )
                    continue
                _logger.info(
                    f"[RejectSend:A] attempt email={email!r} phone={phone!r} "
                    f"name={name!r} is_test={bool(doc.get('isTest'))} "
                    f"job_role={job_role!r}"
                )
                try:
                    from messaging import notify_rejected
                    # iter98 — emit WA + Email attempt markers BEFORE the call so
                    # we always see the attempt in logs even if SMTP/AiSensy crashes.
                    _logger.info(f"[RejectSend:WA]    starting email={email!r} phone={phone!r}")
                    _logger.info(f"[RejectSend:Email] starting email={email!r}")
                    ok = await notify_rejected(
                        name, phone, email,
                        job_role=job_role,
                        is_test=bool(doc.get("isTest")),
                    )
                    await _db.bb_applicant_updates.update_one(
                        {"_id": doc["_id"]},
                        {"$set": {
                            "rejection_sent": True,
                            "rejection_sent_at": now_local.isoformat(),
                            "rejection_notified": True,
                            "rejection_notified_at": now_local.isoformat(),
                            "rejection_send_ok": bool(ok),
                        }},
                    )
                    sent += 1
                    _logger.info(f"[RejectSend:A] DONE email={email!r} ok={ok}")
                except Exception as send_err:
                    skipped_send_failed += 1
                    _logger.error(f"[RejectSend:A] FAILED email={email!r}: {send_err!r}")

            # ---- Source B: form-condition rejections (bb_registrations) ----
            filter_b = {
                **_cutoff_filter(),
                "rejection_pending": True,
                "rejection_sent": {"$ne": True},
            }
            count_b = await _db.bb_registrations.count_documents(filter_b)
            _logger.info(f"[RejectFetch] sourceB=bb_registrations pending_rejections={count_b}")
            cursor_b = _db.bb_registrations.find(filter_b)
            async for doc in cursor_b:
                email = (doc.get("email") or "").strip()
                phone = (doc.get("phone") or "").strip()
                # iter126 — Tester exclusion (see TESTERS log line above).
                _em_norm = email.lower()
                _ph_norm = _re.sub(r"\D", "", phone)[-10:] if phone else ""
                if _em_norm in tester_emails or (_ph_norm and _ph_norm in tester_phones):
                    skipped_tester += 1
                    await _db.bb_registrations.update_one(
                        {"_id": doc["_id"]},
                        {"$set": {
                            "rejection_sent": False,
                            "rejection_pending": False,
                            "rejection_auto_skipped_tester": True,
                            "rejection_auto_skipped_at": now_local.isoformat(),
                        }},
                    )
                    _logger.info(
                        f"[RejectSkip:B:TESTER] email={email!r} phone={phone!r} "
                        f"reason=bb_test_credentials_match doc_id={doc.get('_id')}"
                    )
                    continue
                # iter113 — Same canonical lookup as Source A: prefer the
                # latest `pipeline_data` name/job_role over the local row's
                # values to eliminate stale-payload bugs.
                pd_doc = None
                if email or phone:
                    pd_query = {"$or": []}
                    if email:
                        pd_query["$or"].append({"email": email})
                    if phone:
                        pd_query["$or"].append({"phone": phone})
                    pd_doc = await _db.pipeline_data.find_one(
                        pd_query,
                        {"_id": 0, "name": 1, "job_role": 1, "job_title": 1, "_normalized_job_role": 1},
                        sort=[("registered_at", -1)],
                    )
                name = (
                    (pd_doc or {}).get("name")
                    or doc.get("full_name")
                    or doc.get("name")
                    or ""
                ).strip()
                # iter88 — ABORT if any required template field is missing.
                if not name or (not email and not phone):
                    skipped_no_name += 1
                    _logger.warning(
                        f"[RejectSkip:B] reason=missing_field name={bool(name)} "
                        f"email={bool(email)} phone={bool(phone)} doc_id={doc.get('_id')}"
                    )
                    continue
                _logger.info(
                    f"[RejectSend:B] attempt email={email!r} phone={phone!r} "
                    f"name={name!r} reason_code={doc.get('rejection_reason_code')!r} "
                    f"is_test={bool(doc.get('isTest'))}"
                )
                try:
                    from messaging import notify_rejected_with_reason
                    _logger.info(f"[RejectSend:WA]    starting email={email!r} phone={phone!r} reason=form-condition")
                    _logger.info(f"[RejectSend:Email] starting email={email!r} reason=form-condition")
                    ok = await notify_rejected_with_reason(
                        name, phone, email,
                        doc.get("rejection_reason_code") or "",
                        grad_min=doc.get("rejection_reason_grad_min"),
                        grad_max=doc.get("rejection_reason_grad_max"),
                        is_test=bool(doc.get("isTest")),
                    )
                    await _db.bb_registrations.update_one(
                        {"_id": doc["_id"]},
                        {"$set": {
                            "rejection_sent": True,
                            "rejection_sent_at": now_local.isoformat(),
                            "rejection_pending": False,
                            "reject_notified": bool(ok),
                            "reject_notified_at": now_local.isoformat() if ok else None,
                        }},
                    )
                    sent += 1
                    _logger.info(f"[RejectSend:B] DONE email={email!r} ok={ok}")
                except Exception as send_err:
                    skipped_send_failed += 1
                    _logger.error(f"[RejectSend:B] FAILED email={email!r}: {send_err!r}")

            _logger.info(
                f"[RejectScheduler] BATCH_DONE sent={sent} "
                f"skipped_missing_field={skipped_no_name} send_failed={skipped_send_failed} "
                f"skipped_tester={skipped_tester}"
            )

        except Exception as e:
            _logger.info(
                f"[RejectScheduler] BATCH_DONE sent={sent} "
                f"skipped_missing_field={skipped_no_name} send_failed={skipped_send_failed} "
                f"skipped_tester={skipped_tester}"
            )

        except Exception as e:
            _logger.error(f"[RejectScheduler] FATAL {e!r}")

        # Poll every 5 minutes. The hour-gate guarantees at most ~12 send-passes
        # per day inside the 19:00 window; each pass is idempotent.
        await asyncio.sleep(300)
