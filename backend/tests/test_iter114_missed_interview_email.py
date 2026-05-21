"""iter114 — Missed Interview email dispatch regression.

Root cause: `RESEND_API_KEY` was missing in `/app/backend/.env` (and Render),
which made every `send_email` call fail with `[Email:FAIL] stage=config
RESEND_API_KEY missing` while WhatsApp dispatch continued to work. The
`_worker_missed_interview` worker therefore correctly heart-beat, identified
eligible candidates, marked them as Missed, and dispatched the WA reminder —
but the email half silently dropped, surfacing to the user as "no follow-up
mail received after the 1-hour grace window".

Fix: Set `RESEND_API_KEY` env var. These tests guard against the regression by
exercising the centralized `send_email` and `notify_missed_reminder` paths.
ONLY tester credentials are used (`rishi.nayak@blubridge.com` / `9443109903`).
"""

import asyncio
import os
import secrets
import sys

import pytest
from dotenv import load_dotenv

load_dotenv("/app/backend/.env")
sys.path.insert(0, "/app/backend")

TEST_EMAIL = "rishi.nayak@blubridge.com"
TEST_PHONE = "9443109903"


def test_resend_api_key_present():
    """Guard: the key must be set, else every email-flow drops silently."""
    assert os.environ.get("RESEND_API_KEY"), (
        "RESEND_API_KEY is empty — every email flow (OTP, missed-reminder, "
        "rejection, shortlist) will silently drop. Set it in .env and on Render."
    )


def test_send_email_via_resend():
    from messaging import send_email

    ok = asyncio.run(
        send_email(
            TEST_EMAIL,
            TEST_PHONE,
            "iter114 — Resend transport regression",
            "<p>Automated regression test. Confirms Resend transport works.</p>",
            is_test=True,
        )
    )
    assert ok is True


def test_notify_missed_reminder_dispatches_both_channels():
    from messaging import notify_missed_reminder

    token = secrets.token_urlsafe(32)
    wa_ok, em_ok = asyncio.run(
        notify_missed_reminder(
            name="Rishi Nayak",
            phone=TEST_PHONE,
            email=TEST_EMAIL,
            role="AI & ML Engineer",
            date="2026-05-21",
            time="15:30:00",
            schedule_token=token,
            is_test=True,
        )
    )
    # Email MUST go through — that is the regression we are guarding.
    assert em_ok is True, "Missed-interview EMAIL failed — check RESEND_API_KEY."
    # WhatsApp may or may not succeed depending on AiSensy template state; log only.
    assert isinstance(wa_ok, bool)


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
