"""Centralized messaging service — WhatsApp (AiSensy) + Email (SMTP).

Single source of truth for the outbound gate (TEST_MODE). NEVER call AiSensy
or SMTP directly from anywhere else — always go through `send_whatsapp` /
`send_email` so the test-mode rules are enforced uniformly.
"""

import os
import logging
import smtplib
import ssl
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import httpx

_logger = logging.getLogger("messaging")

# ============ CONFIG (from environment) ============

AISENSY_API_URL = "https://backend.aisensy.com/campaign/t1/api/v2"
AISENSY_API_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpZCI6IjY5NDI0MTYwNzA4MDcwNjE5YzAyZWFhNiIsIm5hbWUiOiJCbHVicmlkZ2V0ZWNobm9sb2dpZXMiLCJhcHBOYW1lIjoiQWlTZW5zeSIsImNsaWVudElkIjoiNjg5NDRlOThiMjQ3NDQwYzBkYzljNzI3IiwiYWN0aXZlUGxhbiI6IkZSRUVfRk9SRVZFUiIsImlhdCI6MTc2NTk0OTc5Mn0.16lJKhbj6JfK_1zzzUgLMwxy5IaqBwu3ljV08xBLRBs"

SMTP_HOST = os.environ.get("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.environ.get("SMTP_PORT", "465"))
SMTP_USER = os.environ.get("SMTP_USER", "hiring@blubridge.com")
SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD", "zfdb buxc ehyq gctr")
FROM_EMAIL = os.environ.get("FROM_EMAIL", "hiring@blubridge.com")

OFFICE_LOCATION = "30, Norton Road, Mandavelipakkam, Raja Annamalai Puram, Chennai, Tamil Nadu - 600028."


def _is_enabled(flag: str) -> bool:
    return os.environ.get(flag, "false").lower() == "true"


# ============ TEST MODE GATE (single source of truth) ============
# When TEST_MODE=true (default — fail-safe), the only recipients that may
# receive WhatsApp/Email are those whose email OR phone exists in the
# `bb_test_credentials` collection (managed via the Tester Credentials admin
# UI). The actual recipient is used as-is; we NEVER auto-substitute another
# tester's contact info.
#
# When TEST_MODE=false (production), the gate is open — every send goes to
# the real recipient.
#
# Disabling TEST_MODE is a manual ops decision: edit /app/backend/.env and
# restart the backend. There is NO code path that turns it off automatically.

_db = None  # injected by server.py via init_messaging(db) at startup


def init_messaging(db):
    """Wire the Mongo handle so `can_send_message` can read tester credentials."""
    global _db
    _db = db


def is_test_mode() -> bool:
    """Default TRUE — fail-safe. Only `TEST_MODE=false` (case-insensitive)
    in /app/backend/.env disables test mode."""
    return os.environ.get("TEST_MODE", "true").strip().lower() == "true"


def _norm_email(v: str) -> str:
    return (v or "").strip().lower()


def _norm_phone(v: str) -> str:
    digits = "".join(ch for ch in (v or "") if ch.isdigit())
    if len(digits) > 10:
        digits = digits[-10:]
    return digits


async def can_send_message(email: str, phone: str) -> tuple:
    """Central messaging gate. Returns `(allowed: bool, reason: str)`.

    TEST_MODE=true  → allowed only if (email OR phone) exists in bb_test_credentials.
    TEST_MODE=false → always allowed (production).

    Reason codes:
      - "production"                       : test mode off
      - "test_mode:tester_allowed"         : recipient matched a tester row
      - "blocked:test_mode:not_in_testers" : recipient not in tester list
      - "blocked:test_mode:empty_recipient": both email and phone blank
      - "blocked:test_mode:db_not_initialized" : startup race (unexpected)
    """
    if not is_test_mode():
        return True, "production"
    e = _norm_email(email)
    p = _norm_phone(phone)
    if not (e or p):
        return False, "blocked:test_mode:empty_recipient"
    if _db is None:
        return False, "blocked:test_mode:db_not_initialized"
    clauses = []
    if e:
        clauses.append({"email": e})
    if p:
        clauses.append({"phone": p})
    doc = await _db.bb_test_credentials.find_one({"$or": clauses}, {"_id": 1})
    if doc:
        return True, "test_mode:tester_allowed"
    return False, "blocked:test_mode:not_in_testers"


# Deprecated — retained only because two legacy callers (bb_resend, bb_modules)
# imported the symbol. Both now use `can_send_message` instead.
def is_allowed_recipient(email: str, phone: str) -> bool:
    """DEPRECATED. Always returns False. Use `can_send_message` (async) instead."""
    _logger.warning("is_allowed_recipient() is deprecated — use can_send_message()")
    return False


# ============ OTP RESOLUTION (iter71) ============
# Single source of truth for the OTP value tied to an applicant + interview
# date. Rule: ONE OTP per (applicant, schedule_date). Reused everywhere
# (Manual OTP Verify, Manual Alerts OTP, Bulk Comm OTP, OTP worker, OTP
# email/WhatsApp). Reset on reschedule or re-registration only.

async def get_otp_for_schedule(email: str, phone: str, schedule_date: str = "") -> str:
    """Read-only lookup. Returns the OTP currently stored on the latest
    matching `bb_registrations` doc for this applicant. If `schedule_date`
    is supplied, prefers a doc with that exact `schedule_date`. Falls back
    to most-recent doc otherwise. Empty string when no OTP exists yet.

    NEVER generates a new OTP — use `get_or_create_otp_for_schedule` for
    that (currently invoked only by the OTP worker / registration flow)."""
    if _db is None:
        return ""
    e = _norm_email(email)
    p = _norm_phone(phone)
    if not (e or p):
        return ""
    import re as _re
    clauses = []
    if e:
        clauses.append({"email": e})
    if p:
        clauses.append({"phone": {"$regex": f"{_re.escape(p)}$"}})

    # Prefer exact schedule_date match (one OTP per interview date).
    if schedule_date:
        doc = await _db.bb_registrations.find_one(
            {"$or": clauses, "schedule_date": schedule_date,
             "otp": {"$exists": True, "$nin": [None, ""]}},
            {"_id": 0, "otp": 1},
            sort=[("otp_sent_at", -1)],
        )
        if doc and doc.get("otp"):
            return str(doc["otp"])

    # Fallback: latest OTP regardless of schedule_date (handles the
    # historical case where schedule_date wasn't recorded on the OTP doc).
    doc = await _db.bb_registrations.find_one(
        {"$or": clauses, "otp": {"$exists": True, "$nin": [None, ""]}},
        {"_id": 0, "otp": 1, "schedule_date": 1},
        sort=[("otp_sent_at", -1)],
    )
    return str(doc["otp"]) if doc and doc.get("otp") else ""


async def get_or_create_otp_for_schedule(email: str, phone: str, schedule_date: str, name: str = "") -> str:
    """Worker/registration-only path: returns existing OTP or generates a
    new one and persists it on `bb_registrations`. Other callers MUST use
    `get_otp_for_schedule` (read-only) to avoid duplicate OTP creation."""
    existing = await get_otp_for_schedule(email, phone, schedule_date)
    if existing:
        return existing
    if _db is None:
        return ""
    import random
    from datetime import datetime as _dt, timezone as _tz
    new_otp = str(random.randint(100000, 999999))
    e = _norm_email(email)
    p = _norm_phone(phone)
    now_iso = _dt.now(_tz.utc).isoformat()
    # Try update existing doc for the same (email/phone, schedule_date)
    res = await _db.bb_registrations.update_one(
        {"$or": [{"email": e}, {"phone": p}], "schedule_date": schedule_date},
        {"$set": {"otp": new_otp, "otp_sent_at": now_iso, "otp_sent": True}},
    )
    if res.matched_count == 0:
        # Insert minimal doc so subsequent lookups find it.
        await _db.bb_registrations.insert_one({
            "name": name, "email": e, "phone": p,
            "schedule_date": schedule_date,
            "otp": new_otp, "otp_sent": True, "otp_sent_at": now_iso,
            "created_via": "otp_resolver", "created_at": now_iso,
        })
    return new_otp


async def reset_otp_on_reschedule(email: str, phone: str) -> int:
    """Invalidate ALL stored OTPs for this applicant. Called when the
    interview is rescheduled — old OTP must be wiped so the OTP worker
    generates a fresh one for the new slot. Returns count of docs modified."""
    if _db is None:
        return 0
    import re as _re
    e = _norm_email(email)
    p = _norm_phone(phone)
    clauses = []
    if e:
        clauses.append({"email": e})
    if p:
        clauses.append({"phone": {"$regex": f"{_re.escape(p)}$"}})
    if not clauses:
        return 0
    res = await _db.bb_registrations.update_many(
        {"$or": clauses},
        {"$unset": {"otp": "", "otp_sent": "", "otp_sent_at": "",
                    "otpGeneratedAt": "", "otpExpiry": ""}},
    )
    _logger.info(f"[OTP:reset_on_reschedule] email={e} phone={p} cleared={res.modified_count}")
    return res.modified_count


# ============ WHATSAPP (AiSensy) ============

async def send_whatsapp(campaign_name: str, phone: str, email: str, template_params: list, is_test: bool = False):
    """Send WhatsApp via AiSensy API. Returns True on success.
    `is_test` is accepted for backward compatibility but is ignored — gating
    is centralised in `can_send_message`."""
    allowed, reason = await can_send_message(email, phone)
    _logger.info(
        f"[Gate:WA] campaign={campaign_name} email={email} phone={phone} "
        f"test_mode={is_test_mode()} allowed={allowed} reason={reason}"
    )
    if not allowed:
        return False

    if not _is_enabled("ENABLE_WHATSAPP"):
        _logger.info(f"[SKIP] WhatsApp disabled: campaign={campaign_name}")
        return False

    safe_phone = _norm_phone(phone)
    if len(safe_phone) == 10:
        safe_phone = "91" + safe_phone

    payload = {
        "apiKey": AISENSY_API_KEY,
        "campaignName": campaign_name,
        "destination": safe_phone,
        # iter70 — Match PHP integration exactly: AiSensy account holder name
        # is "Blubridgetechnologies" (single word, no spaces). Verified from
        # the JWT's `name` claim in AISENSY_API_KEY.
        "userName": "Blubridgetechnologies",
        "templateParams": template_params,
        "source": "python-api",
        "media": [],
        "buttons": [],
        "carouselCards": [],
        "location": [],
        "attributes": [],
        "paramsFallbackValue": {"FirstName": "user"},
    }

    # iter70 — Detailed pre-send log so silent AiSensy drops can be traced.
    _logger.info(
        f"[WhatsApp:REQ] campaign={campaign_name} phone={safe_phone} "
        f"params={template_params} userName=Blubridgetechnologies"
    )

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(AISENSY_API_URL, json=payload)
            ok = resp.status_code == 200
            _logger.info(
                f"[WhatsApp:RESP] campaign={campaign_name} phone={safe_phone} "
                f"status={resp.status_code} ok={ok} body={resp.text[:300]}"
            )
            return ok
    except Exception as e:
        _logger.error(f"[WhatsApp:EXC] campaign={campaign_name} phone={safe_phone}: {e}")
        return False


# ============ EMAIL (SMTP) ============

# iter72 — Branded email shell aligned with the PDF reference design. All
# notify_* helpers wrap their body HTML with `_email_shell()` so every
# outbound email shares the same header (BLUBRIDGE wordmark) and footer.
def _email_shell(body_html: str) -> str:
    """Wrap notification body HTML in a branded email envelope.

    Preserves the body exactly as written; only adds the outer container,
    header logo, and footer signature. Inline styles only — many email
    clients strip <style> blocks."""
    return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head>
<body style="margin:0;padding:0;background:#f5f4ec;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif;color:#1a2332;">
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="background:#f5f4ec;padding:32px 16px;">
    <tr><td align="center">
      <table role="presentation" width="600" cellpadding="0" cellspacing="0" border="0" style="max-width:600px;background:#ffffff;border-radius:12px;overflow:hidden;box-shadow:0 1px 3px rgba(0,0,0,0.08);">
        <tr>
          <td style="background:#1a2332;padding:20px 28px;">
            <div style="font-family:Georgia,'Times New Roman',serif;font-weight:700;letter-spacing:0.18em;color:#ffffff;font-size:18px;">
              BLU<span style="color:#22d3ee;">BRIDGE</span>
            </div>
            <div style="color:#cbd5e1;font-size:11px;letter-spacing:0.14em;margin-top:2px;">RECRUITMENT &nbsp;·&nbsp; HIRING PIPELINE</div>
          </td>
        </tr>
        <tr><td style="padding:32px 32px 16px 32px;font-size:15px;line-height:1.65;color:#1f2937;">
          {body_html}
        </td></tr>
        <tr><td style="padding:0 32px 28px 32px;border-top:1px solid #e5e3d8;margin-top:24px;">
          <p style="margin:24px 0 6px 0;font-size:13px;color:#6b7280;">— Blubridge Recruitment Team</p>
          <p style="margin:0;font-family:Georgia,'Times New Roman',serif;font-weight:700;letter-spacing:0.18em;color:#1a2332;font-size:14px;">
            BLU<span style="color:#0891b2;">BRIDGE</span>
          </p>
          <p style="margin:8px 0 0 0;font-size:11px;color:#9ca3af;">
            30, Norton Road, Mandavelipakkam, Raja Annamalai Puram, Chennai - 600028.
          </p>
        </td></tr>
      </table>
    </td></tr>
  </table>
</body></html>"""


async def send_email(to_email: str, phone: str, subject: str, html_body: str, is_test: bool = False):
    """Send email via SMTP SSL. Returns True on success.
    `is_test` is accepted for backward compatibility but is ignored — gating
    is centralised in `can_send_message`."""
    allowed, reason = await can_send_message(to_email, phone)
    _logger.info(
        f"[Gate:Email] subject={subject!r} email={to_email} phone={phone} "
        f"test_mode={is_test_mode()} allowed={allowed} reason={reason}"
    )
    if not allowed:
        return False

    if not _is_enabled("ENABLE_EMAIL"):
        _logger.info(f"[SKIP] Email disabled: to={to_email}, subject={subject}")
        return False

    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = FROM_EMAIL
        msg["To"] = to_email
        msg.attach(MIMEText(html_body, "html"))

        context = ssl.create_default_context()
        with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, context=context, timeout=15) as server:
            server.login(SMTP_USER, SMTP_PASSWORD)
            server.sendmail(FROM_EMAIL, to_email, msg.as_string())
        _logger.info(f"[Email] SENT to={to_email} subject={subject}")
        return True
    except Exception as e:
        _logger.error(f"[Email] FAILED to={to_email} subject={subject}: {e}")
        return False


# ============ HIGH-LEVEL NOTIFICATION FUNCTIONS ============

# Hard-required env: omit the silent default so misconfiguration fails fast at
# startup (raises KeyError instead of silently mailing a wrong staging URL).
FRONTEND_URL = os.environ["FRONTEND_URL"]


async def notify_shortlisted(name: str, phone: str, email: str, schedule_token: str, is_test: bool = False):
    """Send shortlist notification with schedule link via WhatsApp + Email.
    Returns (wa_ok, em_ok)."""
    schedule_link = f"{FRONTEND_URL}/schedule-interview/{schedule_token}"

    # WhatsApp: ShortList campaign
    wa_ok = await send_whatsapp("ShortList", phone, email, [name, schedule_link], is_test=is_test)

    # Email — body wrapped by _email_shell() (branded header + footer).
    body = f"""
    <p style="margin:0 0 12px 0;">Dear {name},</p>
    <p>Congratulations! After reviewing your responses, we are pleased to inform you that your profile aligns with our requirements.</p>
    <p>Please schedule a convenient time for your <strong>offline (in-person) interview</strong> using the link below:</p>
    <p style="text-align:center;margin:24px 0;">
      <a href="{schedule_link}" style="display:inline-block;background:#1a2332;color:#ffffff;text-decoration:none;padding:12px 28px;border-radius:8px;font-weight:600;font-size:14px;">Schedule My Interview</a>
    </p>
    <p style="font-size:12px;color:#6b7280;word-break:break-all;">Or paste this link in your browser: {schedule_link}</p>
    <p>We look forward to our discussion and exploring how you can contribute to our team's research efforts.</p>
    """
    em_ok = await send_email(email, phone, "You're Shortlisted! Schedule Your Interview - Blubridge", _email_shell(body), is_test=is_test)
    return wa_ok, em_ok


async def notify_rejected(name: str, phone: str, email: str, is_test: bool = False):
    """Send rejection notification via WhatsApp + Email. Returns True if at least one channel succeeded."""
    wa_ok = await send_whatsapp("Reject", phone, email, [], is_test=is_test)
    body = f"""
    <p style="margin:0 0 12px 0;">Dear {name},</p>
    <p>Thank you for your time and effort in completing our registration form.</p>
    <p>While your background and experience are impressive, we have decided to move forward with candidates whose profiles more closely align with our current requirements.</p>
    <p>We encourage you to apply for future opportunities at Blubridge Technologies.</p>
    <p style="margin:20px 0 0 0;">Wishing you the best in your future endeavours!</p>
    """
    em_ok = await send_email(email, phone, "Application Update - Blubridge Technologies", _email_shell(body), is_test=is_test)
    return bool(wa_ok or em_ok)


# Reason-specific rejection templates ------------------------------------------------
# Reason codes: AGE | GRADUATION_YEAR | LOCATION | GENERAL
REJECTION_TEMPLATES = {
    "AGE": {
        "subject": "Application Update - Blubridge Technologies",
        "email_body": "Thank you for your interest. Unfortunately, your profile does not currently meet our eligibility criteria for this role. We will reach out if a more suitable opportunity opens up.",
        "wa_body": "Hi {name}, thank you for applying. We will reach out if suitable opportunities arise.",
    },
    "GRADUATION_YEAR": {
        "subject": "Application Update - Blubridge Technologies",
        "email_body": "Thank you for applying. We are currently hiring candidates from the {grad_min}–{grad_max} batch only. We'll reach out if future openings match your batch.",
        "wa_body": "Hi {name}, we are currently hiring only {grad_min}–{grad_max} batch candidates.",
    },
    "LOCATION": {
        "subject": "Application Update - Blubridge Technologies",
        "email_body": "Thank you for your interest. We are currently proceeding only with candidates willing to attend in-person interviews in Chennai. We'll get in touch if remote opportunities open up.",
        "wa_body": "Hi {name}, we are proceeding only with candidates available for in-person interviews in Chennai.",
    },
    "GENERAL": {
        "subject": "Application Update - Blubridge Technologies",
        "email_body": "Thank you for applying. We will get back to you if your profile matches future requirements.",
        "wa_body": "Hi {name}, thank you for applying. We will reach out if suitable opportunities arise.",
    },
}


async def notify_rejected_with_reason(
    name: str, phone: str, email: str, reason: str,
    grad_min=None, grad_max=None, is_test: bool = False,
):
    """Send a reason-specific rejection (Email + WhatsApp). Returns True if any channel succeeded."""
    tmpl = REJECTION_TEMPLATES.get(reason) or REJECTION_TEMPLATES["GENERAL"]
    fmt_args = {"name": name, "grad_min": grad_min or "", "grad_max": grad_max or ""}
    wa_text = tmpl["wa_body"].format(**fmt_args)
    em_text = tmpl["email_body"].format(**fmt_args)
    # WhatsApp: AiSensy "Reject" campaign template is pre-approved with 0 params.
    # Reason-specific copy is delivered via Email only; WA remains the generic
    # template until the recruiter configures dedicated reason-based campaigns.
    wa_ok = await send_whatsapp("Reject", phone, email, [], is_test=is_test)
    html = f"""
    <p>Dear {name},</p>
    <p>{em_text}</p>
    <p>Wishing you the best in your future endeavours!</p>
    <p>Warm regards,<br>Blubridge Technologies</p>
    """
    em_ok = await send_email(email, phone, tmpl["subject"], html, is_test=is_test)
    _logger.info(f"[Reject:{reason}] email={email} wa_ok={wa_ok} em_ok={em_ok} text={wa_text!r}")
    return bool(wa_ok or em_ok)


async def notify_schedule_confirmation(name: str, phone: str, email: str, date: str, time: str, is_test: bool = False):
    """Send schedule confirmation via WhatsApp + Email. Returns (wa_ok, em_ok)."""
    wa_ok = await send_whatsapp("Schedule Detail", phone, email, [name, date, time, OFFICE_LOCATION], is_test=is_test)
    body = f"""
    <p style="margin:0 0 12px 0;">Hi {name},</p>
    <p>Thank you for scheduling your interview with Blubridge Technologies. Your interview details are confirmed as follows:</p>
    <table role="presentation" cellpadding="0" cellspacing="0" border="0" style="margin:18px 0;background:#f5f4ec;border-radius:8px;padding:16px;width:100%;">
      <tr><td style="padding:6px 14px;font-size:13px;color:#6b7280;width:100px;">Date</td><td style="padding:6px 14px;font-weight:600;color:#1a2332;">{date}</td></tr>
      <tr><td style="padding:6px 14px;font-size:13px;color:#6b7280;">Time</td><td style="padding:6px 14px;font-weight:600;color:#1a2332;">{time}</td></tr>
      <tr><td style="padding:6px 14px;font-size:13px;color:#6b7280;vertical-align:top;">Location</td><td style="padding:6px 14px;color:#1a2332;">{OFFICE_LOCATION}</td></tr>
    </table>
    <p><strong>Your interview will consist of the following rounds:</strong></p>
    <ul style="padding-left:20px;margin:8px 0 16px 0;">
      <li><strong>Round 1:</strong> Logical Reasoning &amp; Aptitude (100 minutes)</li>
      <li><strong>Round 2:</strong> Advanced Logical Reasoning (30 minutes)</li>
    </ul>
    <p style="font-size:13px;color:#6b7280;font-style:italic;">If shortlisted, a further round will be conducted.</p>
    <p style="margin:18px 0 0 0;">We look forward to meeting you.</p>
    """
    em_ok = await send_email(email, phone, "Interview Scheduled - Blubridge Technologies", _email_shell(body), is_test=is_test)
    return wa_ok, em_ok


async def notify_otp(name: str, phone: str, email: str, job_role: str, otp: str, date: str, time: str, is_test: bool = False):
    """Send OTP notification via WhatsApp + Email. Returns (wa_ok, em_ok)."""
    wa_ok = await send_whatsapp("OTP With Job", phone, email, [name, job_role, otp, phone, date, time, OFFICE_LOCATION], is_test=is_test)
    body = f"""
    <p style="margin:0 0 12px 0;">Hi {name},</p>
    <p>Your One-Time Password (OTP) to confirm your interview attendance at Blubridge Technologies is:</p>
    <div style="text-align:center;margin:24px 0;">
      <div style="display:inline-block;background:#1a2332;color:#22d3ee;font-family:'Courier New',Courier,monospace;font-weight:700;font-size:34px;letter-spacing:0.34em;padding:18px 32px;border-radius:10px;">{otp}</div>
    </div>
    <p>Please provide this OTP along with your personal details at the office reception on the day of your interview.</p>
    <p style="margin:20px 0 8px 0;font-weight:600;color:#1a2332;">Interview Details</p>
    <table role="presentation" cellpadding="0" cellspacing="0" border="0" style="margin:8px 0 16px 0;background:#f5f4ec;border-radius:8px;padding:14px;width:100%;">
      <tr><td style="padding:5px 14px;font-size:13px;color:#6b7280;width:100px;">Role</td><td style="padding:5px 14px;font-weight:600;color:#1a2332;">{job_role}</td></tr>
      <tr><td style="padding:5px 14px;font-size:13px;color:#6b7280;">Phone</td><td style="padding:5px 14px;color:#1a2332;">{phone}</td></tr>
      <tr><td style="padding:5px 14px;font-size:13px;color:#6b7280;">Date</td><td style="padding:5px 14px;color:#1a2332;">{date}</td></tr>
      <tr><td style="padding:5px 14px;font-size:13px;color:#6b7280;">Time</td><td style="padding:5px 14px;color:#1a2332;">{time}</td></tr>
      <tr><td style="padding:5px 14px;font-size:13px;color:#6b7280;vertical-align:top;">Location</td><td style="padding:5px 14px;color:#1a2332;">{OFFICE_LOCATION}</td></tr>
    </table>
    <p style="font-size:13px;color:#6b7280;">This OTP is valid only for <strong>eight hours</strong> from your scheduled interview slot.</p>
    <p style="margin:16px 0 0 0;">Looking forward to seeing you soon!</p>
    """
    em_ok = await send_email(email, phone, "Your Interview OTP - Blubridge Technologies", _email_shell(body), is_test=is_test)
    return wa_ok, em_ok


async def notify_missed_reminder(name: str, phone: str, email: str, role: str, date: str, time: str, schedule_token: str, is_test: bool = False):
    """Send missed-interview / candidate follow-up via WhatsApp + Email.
    Returns (wa_ok, em_ok).

    iter70 — Aligned with PHP reference (user spec):
        $campaign_name = "Candidate Followups1";
        sendAiSensyMessage($campaign_name, $phone,
            [$name, $role, $formattedDate, $time, $schedule_link],
            "Blubridgetechnologies");
    AiSensy "Candidate Followups1" template now expects exactly 5 params:
    [name, role, date, time, schedule_link]. The reschedule CTA URL is
    delivered as the 5th template variable (NOT the button URL).
    """
    schedule_link = f"{FRONTEND_URL}/schedule-interview/{schedule_token}" if schedule_token else FRONTEND_URL
    wa_ok = await send_whatsapp(
        "Candidate Followups1", phone, email,
        [name, role, date, time, schedule_link],
        is_test=is_test,
    )
    body = f"""
    <p style="margin:0 0 12px 0;">Hi {name},</p>
    <p>We noticed you missed your scheduled interview at Blubridge for the role of <strong>{role}</strong>. We understand unexpected situations may occur, so we'd like to offer you one final opportunity to reschedule.</p>
    <p style="background:#fef3c7;border-left:4px solid #d97706;padding:12px 16px;margin:18px 0;color:#92400e;font-size:14px;">
      <strong>Note:</strong> If you miss the interview again, you won't be able to apply for any positions at Blubridge for the next <strong>3 months</strong>.
    </p>
    <p>If you're still interested, please use the link below to reschedule your interview at your earliest convenience:</p>
    <p style="text-align:center;margin:24px 0;">
      <a href="{schedule_link}" style="display:inline-block;background:#1a2332;color:#ffffff;text-decoration:none;padding:12px 28px;border-radius:8px;font-weight:600;font-size:14px;">Reschedule Your Interview</a>
    </p>
    <p style="font-size:12px;color:#6b7280;">Rescheduling is subject to available slots.</p>
    """
    em_ok = await send_email(email, phone, "Missed Interview - Reschedule Opportunity - Blubridge", _email_shell(body), is_test=is_test)
    return wa_ok, em_ok


async def notify_schedule_reminder(name: str, phone: str, email: str, schedule_token: str, is_test: bool = False):
    """Send 24h reminder to schedule interview."""
    schedule_link = f"{FRONTEND_URL}/schedule-interview/{schedule_token}"
    await send_whatsapp("ShortList", phone, email, [name, schedule_link], is_test=is_test)
    body = f"""
    <p style="margin:0 0 12px 0;">Dear {name},</p>
    <p>This is a reminder that you have been shortlisted for an interview at Blubridge Technologies, but you haven't scheduled your interview yet.</p>
    <p>Please schedule your interview at the earliest using the link below:</p>
    <p style="text-align:center;margin:24px 0;">
      <a href="{schedule_link}" style="display:inline-block;background:#1a2332;color:#ffffff;text-decoration:none;padding:12px 28px;border-radius:8px;font-weight:600;font-size:14px;">Schedule My Interview</a>
    </p>
    <p style="font-size:12px;color:#6b7280;word-break:break-all;">Or paste this link: {schedule_link}</p>
    """
    await send_email(email, phone, "Reminder: Schedule Your Interview - Blubridge", _email_shell(body), is_test=is_test)
