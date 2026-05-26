"""iter119 — Production sender + Reply-To configuration regression.

Validates that every outbound email:
  * `from` header uses "BluBridge Hiring <information.team@blubrg.com>"
  * `reply_to` field routes replies to "hiring@blubridge.com"
  * No `onboarding@resend.dev` references survive in mail logic
  * Values are env-driven (overridable per environment without code change)

Tests intercept the Resend HTTP call so they do NOT require the `blubrg.com`
domain to be verified in Resend — they validate the payload our code SENDS,
not what Resend's API accepts. Once you verify the domain on resend.com,
no code change is required.
"""

import asyncio
import importlib
import os
import sys

import pytest
from dotenv import load_dotenv

load_dotenv("/app/backend/.env")
sys.path.insert(0, "/app/backend")


def test_env_defaults_match_user_spec():
    """The deployed `.env` must carry the production sender + reply-to."""
    import messaging
    importlib.reload(messaging)
    assert messaging.RESEND_FROM_NAME == "BluBridge Hiring"
    assert messaging.RESEND_FROM_EMAIL == "information.team@blubrg.com"
    assert messaging.MAIL_REPLY_TO == "hiring@blubridge.com"


def test_no_resend_sandbox_sender_remains():
    """Guard: confirm no `onboarding@resend.dev` references survive in
    production mail-sending code paths."""
    backend = "/app/backend"
    offenders = []
    for root, _dirs, files in os.walk(backend):
        if "/node_modules/" in root or "/.venv/" in root or "/tests" in root:
            continue
        for f in files:
            if not f.endswith((".py", ".env")):
                continue
            path = os.path.join(root, f)
            try:
                with open(path, "r", encoding="utf-8") as fh:
                    contents = fh.read()
            except Exception:
                continue
            if "onboarding@resend.dev" in contents:
                offenders.append(path)
    assert not offenders, f"Sandbox sender still present in: {offenders}"


def test_send_email_payload_includes_correct_from_and_reply_to(monkeypatch):
    """Intercept the Resend HTTP POST and assert the constructed payload."""
    import messaging
    importlib.reload(messaging)
    captured = {}

    class _FakeResponse:
        status_code = 200
        text = '{"id":"fake-iter119"}'
        def json(self):
            return {"id": "fake-iter119"}

    class _FakeClient:
        def __init__(self, *a, **kw):
            pass
        async def __aenter__(self):
            return self
        async def __aexit__(self, *a):
            return None
        async def post(self, url, headers=None, json=None):
            captured["url"] = url
            captured["payload"] = json
            captured["auth"] = headers.get("Authorization", "") if headers else ""
            return _FakeResponse()

    monkeypatch.setattr(messaging.httpx, "AsyncClient", _FakeClient)
    # Make sure RESEND_API_KEY is non-empty for the guard.
    monkeypatch.setattr(messaging, "RESEND_API_KEY", "test_key_iter119")

    asyncio.run(messaging.send_email(
        "rishi.nayak@blubridge.com", "9443109903",
        "iter119 unit",
        "<p>iter119 unit body</p>",
        is_test=True,
    ))

    assert captured["url"] == "https://api.resend.com/emails"
    p = captured["payload"]
    assert p["from"] == "BluBridge Hiring <information.team@blubrg.com>", p
    assert p["to"] == ["rishi.nayak@blubridge.com"]
    assert p["subject"] == "iter119 unit"
    assert "<p>iter119 unit body</p>" in p["html"]
    assert p.get("reply_to") == ["hiring@blubridge.com"], p
    # No sandbox sender in the actual outbound payload.
    assert "onboarding@resend.dev" not in str(p)


def test_env_overrides_work(monkeypatch):
    """Operators can swap sender / reply-to via env vars without code change."""
    monkeypatch.setenv("RESEND_FROM_EMAIL", "noreply@example.test")
    monkeypatch.setenv("RESEND_FROM_NAME", "Override Name")
    monkeypatch.setenv("MAIL_REPLY_TO", "support@example.test")
    import messaging
    importlib.reload(messaging)
    assert messaging.RESEND_FROM_EMAIL == "noreply@example.test"
    assert messaging.RESEND_FROM_NAME == "Override Name"
    assert messaging.MAIL_REPLY_TO == "support@example.test"
    # Reset to .env defaults so other tests in this module see the real values.
    monkeypatch.delenv("RESEND_FROM_EMAIL")
    monkeypatch.delenv("RESEND_FROM_NAME")
    monkeypatch.delenv("MAIL_REPLY_TO")
    importlib.reload(messaging)


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
