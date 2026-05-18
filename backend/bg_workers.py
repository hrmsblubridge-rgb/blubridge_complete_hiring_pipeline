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

            # Query ONLY today's interviews where OTP not yet sent (NEW records only)
            cursor = _db.bb_registrations.find({
                **_cutoff_filter(),
                "schedule_date": today_str,
                "is_shortlisted": True,
                "otp_sent": {"$ne": True},
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

                cas = await _db.bb_registrations.update_one(
                    {"_id": doc["_id"],
                     "otp_sent": {"$ne": True},
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
                    f"otp={otp} interview={interview_dt.strftime('%Y-%m-%d %H:%M')} IST"
                )

                wa_ok, em_ok = False, False
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
                    )
                    wa_ok, em_ok = result if isinstance(result, tuple) else (bool(result), False)
                except Exception as ne:
                    send_err = ne
                    _logger.exception(f"[OTP:NOTIFY_EXC] email={doc.get('email')} err={ne!r}")

                # iter107 — Persist per-channel results AFTER the send. We mark
                # `otp_sent=True` only if AT LEAST ONE channel succeeded; if
                # BOTH failed we clear `otp_dispatch_in_progress` so the next
                # tick retries. This is the inverse of the old behaviour where
                # `otp_sent=True` was committed before the send and any failure
                # permanently lost the OTP email.
                any_ok = bool(wa_ok or em_ok)
                if any_ok:
                    await _db.bb_registrations.update_one(
                        {"_id": doc["_id"]},
                        {"$set": {
                            "otp_sent": True,
                            "otp_sent_at": now_iso,
                            "otp_wa_sent": bool(wa_ok),
                            "otp_wa_sent_at": now_iso if wa_ok else None,
                            "otp_email_sent": bool(em_ok),
                            "otp_email_sent_at": now_iso if em_ok else None,
                            "otp_dispatch_in_progress": False,
                        }},
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
    _logger.info("Missed Interview worker started")
    while True:
        try:
            now = datetime.now(timezone.utc)
            today_str = now.strftime("%Y-%m-%d")
            # iter91 — Stop scanning interviews older than 7 days. Stale tester
            # re-registration rows from days/weeks ago would otherwise trigger
            # phantom missed-reminder sends.
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
                name = (doc.get("full_name") or "").strip()
                phone = (doc.get("phone") or "").strip()
                email = (doc.get("email") or "").strip()
                # iter91 FIX 2G — abort if any required template field is missing.
                if token and name and (email or phone):
                    from messaging import notify_missed_reminder
                    await notify_missed_reminder(
                        name, phone, email,
                        doc.get("job_role", ""),
                        schedule_date,
                        schedule_time_str,
                        token,
                        is_test=bool(doc.get("isTest")),
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
                name = (doc.get("name") or "").strip()
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
                    f"job_role={(doc.get('job_role') or doc.get('job_title') or '')!r}"
                )
                try:
                    from messaging import notify_rejected
                    # iter98 — emit WA + Email attempt markers BEFORE the call so
                    # we always see the attempt in logs even if SMTP/AiSensy crashes.
                    _logger.info(f"[RejectSend:WA]    starting email={email!r} phone={phone!r}")
                    _logger.info(f"[RejectSend:Email] starting email={email!r}")
                    ok = await notify_rejected(
                        name, phone, email,
                        job_role=doc.get("job_role") or doc.get("job_title") or "",
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
                name = (doc.get("full_name") or doc.get("name") or "").strip()
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
                f"skipped_missing_field={skipped_no_name} send_failed={skipped_send_failed}"
            )

        except Exception as e:
            _logger.error(f"[RejectScheduler] FATAL {e!r}")

        # Poll every 5 minutes. The hour-gate guarantees at most ~12 send-passes
        # per day inside the 19:00 window; each pass is idempotent.
        await asyncio.sleep(300)
