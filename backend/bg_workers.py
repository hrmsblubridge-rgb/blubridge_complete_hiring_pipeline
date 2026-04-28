"""Background workers for automated messaging tasks.
All workers are idempotent — safe to run repeatedly without duplicate sends."""

import asyncio
import logging
import random
from datetime import datetime, timezone, timedelta

_logger = logging.getLogger("bg_workers")

_db = None
_running = False


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
    asyncio.create_task(_worker_otp_generator())
    asyncio.create_task(_worker_schedule_link_sender())
    asyncio.create_task(_worker_24h_reminder())


# ============ WORKER A: OTP Generator (every 60s) ============

async def _worker_otp_generator():
    """Check for interviews scheduled today where OTP not sent. Send OTP 3h before interview."""
    _logger.info("OTP Generator worker started")
    while True:
        try:
            now = datetime.now(timezone.utc)
            today_str = now.strftime("%Y-%m-%d")

            # Find registrations with interview today, OTP not sent
            cursor = _db.bb_registrations.find({
                "schedule_date": today_str,
                "status": "Interview Scheduled",
                "otp_sent": {"$ne": True},
            })
            docs = await cursor.to_list(None)

            for doc in docs:
                schedule_time_str = doc.get("schedule_time", "")
                if not schedule_time_str:
                    continue

                # Parse schedule time (format: HH:MM:SS)
                try:
                    hour, minute = int(schedule_time_str.split(":")[0]), int(schedule_time_str.split(":")[1])
                    interview_dt = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
                    trigger_time = interview_dt - timedelta(hours=3)

                    if now >= trigger_time:
                        # Generate OTP if not already set for today
                        otp = doc.get("otp")
                        if not otp:
                            otp = str(random.randint(100000, 999999))

                        await _db.bb_registrations.update_one(
                            {"_id": doc["_id"]},
                            {"$set": {"otp": otp, "otp_sent": True, "otp_sent_at": now.isoformat()}}
                        )

                        # Update registered_candidates too
                        await _db.registered_candidates.update_many(
                            {"$or": [{"email": doc.get("email", "")}, {"phone": doc.get("phone", "")}]},
                            {"$set": {"otp": otp, "otp_send": "1"}}
                        )

                        # Send notifications
                        from messaging import notify_otp
                        await notify_otp(
                            doc.get("full_name", ""),
                            doc.get("phone", ""),
                            doc.get("email", ""),
                            doc.get("job_role", ""),
                            otp,
                            today_str,
                            schedule_time_str,
                        )
                        _logger.info(f"[OTP] Sent to {doc.get('email')}, otp={otp}")
                except (ValueError, IndexError):
                    _logger.warning(f"[OTP] Could not parse schedule_time: {schedule_time_str}")

        except Exception as e:
            _logger.error(f"[OTP Worker] Error: {e}")

        await asyncio.sleep(60)


# ============ WORKER B: Schedule Link Sender (every 60s) ============

async def _worker_schedule_link_sender():
    """Send schedule link 5-30 min after registration for shortlisted applicants."""
    _logger.info("Schedule Link Sender worker started")
    while True:
        try:
            now = datetime.now(timezone.utc)
            five_min_ago = (now - timedelta(minutes=30)).isoformat()
            thirty_min_future = (now - timedelta(minutes=5)).isoformat()

            # Find shortlisted registrations submitted 5-30 min ago, link not sent
            cursor = _db.bb_registrations.find({
                "is_shortlisted": True,
                "schedule_link_sent": {"$ne": True},
                "registered_at": {"$lte": thirty_min_future, "$gte": five_min_ago},
            })
            docs = await cursor.to_list(None)

            for doc in docs:
                token = doc.get("schedule_token")
                if not token:
                    continue

                from messaging import notify_shortlisted
                await notify_shortlisted(
                    doc.get("full_name", ""),
                    doc.get("phone", ""),
                    doc.get("email", ""),
                    token,
                )

                await _db.bb_registrations.update_one(
                    {"_id": doc["_id"]},
                    {"$set": {"schedule_link_sent": True, "schedule_link_sent_at": now.isoformat()}}
                )
                _logger.info(f"[ScheduleLink] Sent to {doc.get('email')}")

            # Also send rejection notifications for rejected applicants not yet notified
            rejected_cursor = _db.bb_registrations.find({
                "is_shortlisted": False,
                "reject_notified": {"$ne": True},
                "registered_at": {"$lte": thirty_min_future, "$gte": five_min_ago},
            })
            rejected_docs = await rejected_cursor.to_list(None)

            for doc in rejected_docs:
                from messaging import notify_rejected
                await notify_rejected(
                    doc.get("full_name", ""),
                    doc.get("phone", ""),
                    doc.get("email", ""),
                )
                await _db.bb_registrations.update_one(
                    {"_id": doc["_id"]},
                    {"$set": {"reject_notified": True, "reject_notified_at": now.isoformat()}}
                )
                _logger.info(f"[Reject] Notified {doc.get('email')}")

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

            # Find applicants: link sent > 24h ago, not scheduled, no reminder sent
            cursor = _db.bb_registrations.find({
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
                )

                await _db.bb_registrations.update_one(
                    {"_id": doc["_id"]},
                    {"$set": {"reminder_24h_sent": True, "reminder_24h_sent_at": now.isoformat()}}
                )
                _logger.info(f"[24hReminder] Sent to {doc.get('email')}")

        except Exception as e:
            _logger.error(f"[24hReminder Worker] Error: {e}")

        await asyncio.sleep(300)  # 5 minutes
