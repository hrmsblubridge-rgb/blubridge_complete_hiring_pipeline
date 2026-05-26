"""iter121 — OTP per-channel retry regression.

Bug (production-reported): WhatsApp OTP was delivered but the OTP email never
arrived. Root cause: iter107 documented "per-channel retry" but the OTP
worker's cursor filter used `otp_sent != True` and was set TRUE the moment
ANY channel succeeded. So a partial WA-success + Email-fail tick committed
`otp_sent=True`, excluding the row from every subsequent tick — the email
was never retried.

Fix (iter121):
1. Cursor filter is now `$or: [{otp_wa_sent != True}, {otp_email_sent != True}]`
   — row remains eligible until BOTH channels are confirmed sent.
2. Before dispatch the worker examines `otp_wa_sent` / `otp_email_sent` and
   only attempts the channel(s) still unsent.
3. `notify_otp` now accepts `send_wa` / `send_email_channel` boolean flags so
   the worker can skip the already-succeeded channel and not re-spam the
   candidate.
4. `otp_sent=True` umbrella flag is only set when BOTH channels succeed.

Tests use ONLY tester credentials.
"""

import asyncio
import importlib
import os
import sys

import pytest
from dotenv import load_dotenv

load_dotenv("/app/backend/.env")
sys.path.insert(0, "/app/backend")


def test_notify_otp_signature_exposes_per_channel_flags():
    import inspect
    import messaging
    importlib.reload(messaging)
    sig = inspect.signature(messaging.notify_otp)
    params = sig.parameters
    assert "send_wa" in params, "send_wa flag missing from notify_otp"
    assert "send_email_channel" in params, "send_email_channel flag missing"
    # Defaults preserve existing callers (full send when omitted).
    assert params["send_wa"].default is True
    assert params["send_email_channel"].default is True


def test_notify_otp_skips_wa_when_flag_false(monkeypatch):
    """send_wa=False MUST NOT invoke send_whatsapp (no re-spam to candidate)."""
    import messaging
    importlib.reload(messaging)
    calls = {"wa": 0, "email": 0}

    async def _fake_wa(*a, **kw):
        calls["wa"] += 1
        return True

    async def _fake_email(*a, **kw):
        calls["email"] += 1
        return True

    monkeypatch.setattr(messaging, "send_whatsapp", _fake_wa)
    monkeypatch.setattr(messaging, "send_email", _fake_email)

    wa_ok, em_ok = asyncio.run(messaging.notify_otp(
        "Tester", "9443109903", "rishi.nayak@blubridge.com",
        "AI & ML Engineer", "123456", "2026-05-25", "10:00:00",
        is_test=True, send_wa=False, send_email_channel=True,
    ))
    assert calls["wa"] == 0, f"WhatsApp must NOT fire when send_wa=False; calls={calls}"
    assert calls["email"] == 1
    assert wa_ok is False
    assert em_ok is True


def test_notify_otp_skips_email_when_flag_false(monkeypatch):
    """send_email_channel=False MUST NOT invoke send_email."""
    import messaging
    importlib.reload(messaging)
    calls = {"wa": 0, "email": 0}

    async def _fake_wa(*a, **kw):
        calls["wa"] += 1
        return True

    async def _fake_email(*a, **kw):
        calls["email"] += 1
        return True

    monkeypatch.setattr(messaging, "send_whatsapp", _fake_wa)
    monkeypatch.setattr(messaging, "send_email", _fake_email)

    wa_ok, em_ok = asyncio.run(messaging.notify_otp(
        "Tester", "9443109903", "rishi.nayak@blubridge.com",
        "AI & ML Engineer", "123456", "2026-05-25", "10:00:00",
        is_test=True, send_wa=True, send_email_channel=False,
    ))
    assert calls["email"] == 0, f"Email must NOT fire when send_email_channel=False; calls={calls}"
    assert calls["wa"] == 1
    assert wa_ok is True
    assert em_ok is False


def test_notify_otp_sends_both_by_default(monkeypatch):
    """Backward compatibility: existing callers (no flags) must trigger both."""
    import messaging
    importlib.reload(messaging)
    calls = {"wa": 0, "email": 0}

    async def _fake_wa(*a, **kw):
        calls["wa"] += 1
        return True

    async def _fake_email(*a, **kw):
        calls["email"] += 1
        return True

    monkeypatch.setattr(messaging, "send_whatsapp", _fake_wa)
    monkeypatch.setattr(messaging, "send_email", _fake_email)

    wa_ok, em_ok = asyncio.run(messaging.notify_otp(
        "Tester", "9443109903", "rishi.nayak@blubridge.com",
        "AI & ML Engineer", "123456", "2026-05-25", "10:00:00",
        is_test=True,  # no flags = both channels
    ))
    assert calls["wa"] == 1 and calls["email"] == 1
    assert wa_ok is True and em_ok is True


def test_worker_cursor_filter_uses_per_channel_flags():
    """Grep guard: the worker file must use the iter121 cursor filter that
    keys off per-channel flags, not the legacy `otp_sent` umbrella flag."""
    with open("/app/backend/bg_workers.py", "r") as f:
        src = f.read()
    # Per-channel cursor filter present:
    assert "otp_wa_sent" in src
    assert "otp_email_sent" in src
    # Find the OTP worker cursor block — must contain $or pattern.
    otp_section = src.split("async def _worker_otp_generator")[1].split("async def _worker_schedule_link_sender")[0]
    assert '"$or"' in otp_section, "OTP cursor must use $or to retry per channel"
    assert "send_email_channel=not em_already_sent" in otp_section
    assert "send_wa=not wa_already_sent" in otp_section


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
