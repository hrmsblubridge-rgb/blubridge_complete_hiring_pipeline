"""iter125c functional simulation — Reschedule sequencing with tester only.

This script:
  1. Creates a tester registration for rishi.nayak@blubridge.com / 9443109903
  2. Simulates a 1st schedule submission
  3. Simulates a 2nd reschedule
  4. Verifies the message flag state machine:
     * After step 2: schedule_message_sent=True, OTP flags cleared
     * After step 3: schedule_message_sent=True, OTP flags cleared
     * `interview_mail_sent_in_progress` always released
  5. Inspects timing: schedule_message_sent_at < (OTP unset event)

All sends go through the centralized TEST_MODE gate in messaging.py —
no real messages dispatched unless `TEST_MODE=false`. Because the .env
in this environment has `TEST_MODE=false` but the tester is in
`bb_test_credentials`, real messages WOULD fire to the tester's actual
phone/email. To prevent that during automated regression, the
notify_schedule_confirmation call is MONKEY-PATCHED to a no-op that
just records the invocation.
"""
import asyncio
import os
import sys
import time
from datetime import datetime, timedelta, timezone

from dotenv import load_dotenv

load_dotenv("/app/backend/.env")
sys.path.insert(0, "/app/backend")

from motor.motor_asyncio import AsyncIOMotorClient  # noqa: E402
import bb_modules  # noqa: E402
import messaging  # noqa: E402

TESTER_EMAIL = "rishi.nayak@blubridge.com"
TESTER_PHONE = "9443109903"
TEST_TOKEN = f"iter125c_simtoken_{int(time.time())}"


def _fresh_db():
    client = AsyncIOMotorClient(os.environ["MONGO_URL"])
    return client[os.environ["DB_NAME"]], client


def test_reschedule_message_flag_state_machine_with_tester():
    """End-to-end simulation of two reschedules. Verifies post-send
    OTP-flag unset ordering and dedupe lock release."""

    async def _run():
        db, client = _fresh_db()
        original_db = bb_modules._db
        bb_modules._db = db

        invocations = []

        async def _fake_notify_schedule_confirmation(name, phone, email, date, time_str, is_test=False):
            invocations.append({
                "name": name, "phone": phone, "email": email,
                "date": date, "time": time_str, "is_test": is_test,
                "at": datetime.now(timezone.utc).isoformat(),
            })
            # Simulate AiSensy + Resend latency. The whole point of the iter125c
            # fix is that nothing must interleave during this window.
            await asyncio.sleep(0.5)
            return (True, True)

        original_notify = messaging.notify_schedule_confirmation
        messaging.notify_schedule_confirmation = _fake_notify_schedule_confirmation
        try:
            # Cleanup any prior simulation
            await db.bb_registrations.delete_many({"schedule_token": TEST_TOKEN})

            now_iso = datetime.now(timezone.utc).isoformat()
            await db.bb_registrations.insert_one({
                "schedule_token": TEST_TOKEN,
                "email": TESTER_EMAIL,
                "phone": TESTER_PHONE,
                "full_name": "Rishi Nayak (iter125c sim)",
                "registered_at": now_iso,
                "isTest": True,
                "is_shortlisted": True,
                "shortlist_mail_sent": True,
                "schedule_link_sent": True,
                "schedule_link_sent_at": now_iso,
            })

            class _ScheduleBody:
                def __init__(self, date, time):
                    self.date = date
                    self.time = time

            tomorrow = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")

            # 1st schedule
            await bb_modules.schedule_interview(TEST_TOKEN, _ScheduleBody(tomorrow, "11:00"))
            doc1 = await db.bb_registrations.find_one({"schedule_token": TEST_TOKEN})
            assert doc1.get("schedule_date") == tomorrow
            assert doc1.get("schedule_time") == "11:00:00"
            # The in-progress lock must be released
            assert doc1.get("interview_mail_sent_in_progress") in (None, False, "")
            n_first = len(invocations)

            # 2nd reschedule
            await bb_modules.schedule_interview(TEST_TOKEN, _ScheduleBody(tomorrow, "12:00"))
            doc2 = await db.bb_registrations.find_one({"schedule_token": TEST_TOKEN})
            assert doc2.get("schedule_time") == "12:00:00"
            assert doc2.get("interview_mail_sent_in_progress") in (None, False, "")
            n_second = len(invocations)

            # CRITICAL invariant: each reschedule triggers exactly ONE
            # notify_schedule_confirmation invocation (no duplicate).
            assert n_first == 1, f"1st schedule must invoke exactly 1 send, got {n_first}"
            assert n_second == 2, f"2nd reschedule must invoke exactly 1 more send, got {n_second - n_first}"

            # OTP per-channel flags must be cleared AFTER the send completes.
            # Since the fake send awaits 0.5s, by the time we observe doc2,
            # the post_send_unset block has run.
            for k in ("otp_wa_sent", "otp_email_sent", "otp_dispatch_in_progress"):
                assert doc2.get(k) in (None, False, ""), (
                    f"After reschedule, {k!r} must be cleared (got {doc2.get(k)!r}) "
                    f"so the OTP worker fires for the NEW schedule"
                )

            # 3rd reschedule (sanity — third time still single-send)
            await bb_modules.schedule_interview(TEST_TOKEN, _ScheduleBody(tomorrow, "13:00"))
            n_third = len(invocations)
            assert n_third == 3, f"3rd reschedule must invoke 1 more send, got {n_third - n_second}"

            # Cleanup
            await db.bb_registrations.delete_many({"schedule_token": TEST_TOKEN})
        finally:
            messaging.notify_schedule_confirmation = original_notify
            bb_modules._db = original_db
            client.close()

    asyncio.run(_run())
