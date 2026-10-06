"""iter122 — Two production fixes covered:

ISSUE 1: Candidate follow-up email sent TWICE (WhatsApp sent ONCE).
  Root cause: when candidate clicked the reschedule link, the schedule
  submission cleared `missed_marked` and `missed_reminder_sent`. The
  worker re-fired both channels on the SAME schedule_token. AiSensy
  deduped WhatsApp within a 24h window but Resend did NOT, so the
  candidate received 2 emails.

  Fix: per-channel idempotency flags scoped to `schedule_token`:
    * `missed_reminder_wa_sent` (bool)
    * `missed_reminder_email_sent` (bool)
    * `missed_reminder_token` (the schedule_token at time of dispatch)
  Worker compares stored token to current token; if they match AND a
  channel is True, that channel is SKIPPED on retry. When the candidate
  reschedules with a new token, the comparison fails and a fresh
  dispatch happens — preserving the legitimate "new schedule → new
  reminder" flow.
  `notify_missed_reminder` extended with `send_wa` / `send_email_channel`
  flags (default True/True for backward compatibility).

ISSUE 2: New roles from datasets classified as "Unknown" (~8500 prod rows).
  Root cause: iter108 backfill condition was
    `if new_val and new_val != "Unknown" and new_val != raw`
  Rows whose `_resolve_normalized_job_role` returned the raw title
  verbatim (no exact mapping match) were skipped by `new_val != raw`,
  leaving them stuck at `_normalized_job_role='Unknown'`.

  Fix: dropped the `!= raw` clause. Backfill now updates whenever
  resolution produced ANY non-empty non-"Unknown" value AND the existing
  stored value is in the stuck set.

Tests use ONLY tester credentials + synthetic tagged rows.
"""

import asyncio
import os
import sys

import pytest
from dotenv import load_dotenv

load_dotenv("/app/backend/.env")
sys.path.insert(0, "/app/backend")

from motor.motor_asyncio import AsyncIOMotorClient

TEST_EMAIL = "rishi.nayak@blubridge.com"
TEST_PHONE = "9443109903"
TAG = "_iter122_missed_reminder_test"


# ─────────────────────── Issue 1 — missed-reminder per-channel ───────────────────────

def test_notify_missed_reminder_signature_exposes_per_channel_flags():
    import inspect
    import messaging
    sig = inspect.signature(messaging.notify_missed_reminder)
    params = sig.parameters
    assert "send_wa" in params, "send_wa flag missing from notify_missed_reminder"
    assert "send_email_channel" in params, "send_email_channel flag missing"
    assert params["send_wa"].default is True
    assert params["send_email_channel"].default is True


def test_notify_missed_reminder_skips_wa_when_flag_false(monkeypatch):
    import messaging
    calls = {"wa": 0, "email": 0}

    async def _fake_wa(*a, **kw):
        calls["wa"] += 1
        return True

    async def _fake_email(*a, **kw):
        calls["email"] += 1
        return True

    monkeypatch.setattr(messaging, "send_whatsapp", _fake_wa)
    monkeypatch.setattr(messaging, "send_email", _fake_email)

    asyncio.run(messaging.notify_missed_reminder(
        "Tester", TEST_PHONE, TEST_EMAIL,
        "AI & ML Engineer", "2026-05-26", "17:00:00",
        "abc123token", is_test=True,
        send_wa=False, send_email_channel=True,
    ))
    assert calls["wa"] == 0, f"WA must NOT fire when send_wa=False; calls={calls}"
    assert calls["email"] == 1


def test_notify_missed_reminder_skips_email_when_flag_false(monkeypatch):
    import messaging
    calls = {"wa": 0, "email": 0}

    async def _fake_wa(*a, **kw):
        calls["wa"] += 1
        return True

    async def _fake_email(*a, **kw):
        calls["email"] += 1
        return True

    monkeypatch.setattr(messaging, "send_whatsapp", _fake_wa)
    monkeypatch.setattr(messaging, "send_email", _fake_email)

    asyncio.run(messaging.notify_missed_reminder(
        "Tester", TEST_PHONE, TEST_EMAIL,
        "AI & ML Engineer", "2026-05-26", "17:00:00",
        "abc123token", is_test=True,
        send_wa=True, send_email_channel=False,
    ))
    assert calls["email"] == 0, f"Email must NOT fire when send_email_channel=False; calls={calls}"
    assert calls["wa"] == 1


def test_worker_persists_per_channel_flags_scoped_to_schedule_token():
    """Source-grep guard for the worker's iter122 persistence logic."""
    with open("/app/backend/bg_workers.py", "r") as f:
        src = f.read()
    # The four critical new persistence fields
    assert "missed_reminder_wa_sent" in src
    assert "missed_reminder_email_sent" in src
    assert "missed_reminder_token" in src
    assert "missed_reminder_sent_at" in src
    # The skip-if-token-matches guard
    assert "stored_token == token" in src
    assert "wa_already and em_already" in src
    # The per-channel kwargs at call site
    assert "send_wa=not wa_already" in src
    assert "send_email_channel=not em_already" in src


# ─────────────────────── Issue 2 — Unknown backfill ───────────────────────

async def _setup_stuck_unknown_row(db, raw_job_title: str):
    """Insert a synthetic naukri-style row that mimics the production stuck
    pattern: non-empty job_title, _normalized_job_role='Unknown'."""
    await db.naukri_applies.delete_many({TAG: True})
    await db.naukri_applies.insert_one({
        TAG: True,
        "email": "iter122_synthetic@example.test",
        "phone": "0000000000",
        "name": "Iter122 Synthetic",
        "job_title": raw_job_title,
        "_normalized_job_role": "Unknown",
        "date_of_application": "2026-05-26",
    })


async def _cleanup(db):
    await db.naukri_applies.delete_many({TAG: True})


def test_resolve_returns_raw_when_no_mapping():
    """The fundamental contract: resolution falls through to the raw title
    when no keyword matches. iter108 backfill must respect this."""
    from server import _resolve_normalized_job_role
    out = _resolve_normalized_job_role("Definitely Brand New Role 9999", mappings=[])
    assert out == "Definitely Brand New Role 9999"
    out2 = _resolve_normalized_job_role("", mappings=[])
    assert out2 == "Unknown"


def test_iter108_backfill_condition_no_longer_requires_different_raw():
    """Source-grep guard: the broken `new_val != raw` clause must be gone
    from EXECUTABLE code (not from explanatory comments)."""
    with open("/app/backend/server.py", "r") as f:
        lines = f.readlines()
    # Only inspect non-comment lines. The fix replaced the executable
    # `if new_val and new_val != "Unknown" and new_val != raw:` with
    # `if new_val and new_val != "Unknown":`.
    code_lines = [ln for ln in lines if not ln.lstrip().startswith("#")]
    code_text = "".join(code_lines)
    assert "new_val != raw" not in code_text, (
        "iter108 backfill still contains the broken `new_val != raw` clause "
        "in executable code (comments are allowed to mention the historical bug)."
    )
    # Positive assertion: the corrected condition is present.
    assert 'if new_val and new_val != "Unknown":' in code_text


def test_no_production_rows_remain_stuck_at_unknown_with_job_title():
    """End-to-end verification on the live DB: every row with a non-empty
    job_title should now have a real `_normalized_job_role` (not Unknown)."""
    async def _check():
        client = AsyncIOMotorClient(os.environ["MONGO_URL"])
        db = client[os.environ["DB_NAME"]]
        n = await db.naukri_applies.count_documents({
            "job_title": {"$nin": [None, ""]},
            "_normalized_job_role": "Unknown",
        })
        return n
    stuck = asyncio.run(_check())
    assert stuck == 0, (
        f"{stuck} naukri rows still stuck at _normalized_job_role='Unknown' "
        f"despite having a non-empty job_title."
    )


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
