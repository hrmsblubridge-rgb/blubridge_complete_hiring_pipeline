"""Centralized messaging service — WhatsApp (AiSensy) + Email (SMTP).
All recipient overrides for TEST_MODE happen HERE and only here."""

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


# ============ STRICT ALLOWLIST ============
# Hard gate applied to every WhatsApp + Email send. Blocks messages to any
# recipient whose (email, phone) pair does not match one of the allowed pairs.
# The caller's email AND phone must BOTH match a single pair. No fallback,
# no auto-replacement. Blocked attempts are logged at INFO level.
_ALLOWED_PAIRS = (
    ("rishi.nayak@blubridge.com", "9443109903"),
    ("rajlearn@gmail.com", "8883847098"),
)


def _norm_email(v: str) -> str:
    return (v or "").strip().lower()


def _norm_phone(v: str) -> str:
    digits = "".join(ch for ch in (v or "") if ch.isdigit())
    # Normalise to last 10 digits (strip "91" / "+91" country code)
    if len(digits) > 10:
        digits = digits[-10:]
    return digits


def is_allowed_recipient(email: str, phone: str) -> bool:
    """True iff (email, phone) exactly matches one allowlisted pair."""
    e = _norm_email(email)
    p = _norm_phone(phone)
    for a_email, a_phone in _ALLOWED_PAIRS:
        if e == _norm_email(a_email) and p == _norm_phone(a_phone):
            return True
    return False


def _resolve_recipient(phone: str, email: str, is_test: bool = False) -> tuple:
    """Resolve real vs test recipient.

    Test override triggers ONLY when:
      - the record/caller passes `is_test=True`, OR
      - env FORCE_TEST_MODE=true (emergency kill-switch).

    Previously TEST_MODE=true re-routed ALL messages — causing real applicants
    to never receive their own communications. That behaviour is now opt-in
    per-record only.
    """
    if is_test or _is_enabled("FORCE_TEST_MODE"):
        test_phone = os.environ.get("TEST_PHONE", "9443109903")
        test_email = os.environ.get("TEST_EMAIL", "rishi.nayak@blubridge.com")
        _logger.info(f"[TEST_ROUTE] Overriding: phone={phone}->{test_phone}, email={email}->{test_email}")
        return test_phone, test_email
    return phone, email


# ============ WHATSAPP (AiSensy) ============

async def send_whatsapp(campaign_name: str, phone: str, email: str, template_params: list, is_test: bool = False):
    """Send WhatsApp via AiSensy API. Returns True on success.
    `is_test=True` re-routes the message to TEST_PHONE (dev/test records only)."""
    # ── STRICT ALLOWLIST GATE ──
    if not is_allowed_recipient(email, phone):
        _logger.info(f"[ALLOWLIST:BLOCK] WhatsApp campaign={campaign_name} phone={phone} email={email} — recipient not on allowlist")
        return False

    if not _is_enabled("ENABLE_WHATSAPP"):
        _logger.info(f"[SKIP] WhatsApp disabled: campaign={campaign_name}")
        return False

    safe_phone, _ = _resolve_recipient(phone, email, is_test=is_test)
    # Ensure 91 prefix for Indian numbers
    if len(safe_phone) == 10:
        safe_phone = "91" + safe_phone

    payload = {
        "apiKey": AISENSY_API_KEY,
        "campaignName": campaign_name,
        "destination": safe_phone,
        "userName": "Blubridge Technologies",
        "templateParams": template_params,
        "source": "python-api",
        "media": [],
        "buttons": [],
        "carouselCards": [],
        "location": [],
        "attributes": [],
        "paramsFallbackValue": {"FirstName": "user"},
    }

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(AISENSY_API_URL, json=payload)
            _logger.info(f"[WhatsApp] campaign={campaign_name} phone={safe_phone} status={resp.status_code} body={resp.text[:200]}")
            return resp.status_code == 200
    except Exception as e:
        _logger.error(f"[WhatsApp] FAILED campaign={campaign_name} phone={safe_phone}: {e}")
        return False


# ============ EMAIL (SMTP) ============

async def send_email(to_email: str, phone: str, subject: str, html_body: str, is_test: bool = False):
    """Send email via SMTP SSL. Returns True on success.
    `is_test=True` re-routes the message to TEST_EMAIL (dev/test records only)."""
    # ── STRICT ALLOWLIST GATE ──
    if not is_allowed_recipient(to_email, phone):
        _logger.info(f"[ALLOWLIST:BLOCK] Email subject={subject!r} phone={phone} email={to_email} — recipient not on allowlist")
        return False

    if not _is_enabled("ENABLE_EMAIL"):
        _logger.info(f"[SKIP] Email disabled: to={to_email}, subject={subject}")
        return False

    _, safe_email = _resolve_recipient(phone, to_email, is_test=is_test)

    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = FROM_EMAIL
        msg["To"] = safe_email
        msg.attach(MIMEText(html_body, "html"))

        context = ssl.create_default_context()
        with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, context=context, timeout=15) as server:
            server.login(SMTP_USER, SMTP_PASSWORD)
            server.sendmail(FROM_EMAIL, safe_email, msg.as_string())
        _logger.info(f"[Email] SENT to={safe_email} subject={subject}")
        return True
    except Exception as e:
        _logger.error(f"[Email] FAILED to={safe_email} subject={subject}: {e}")
        return False


# ============ HIGH-LEVEL NOTIFICATION FUNCTIONS ============

# Hard-required env: omit the silent default so misconfiguration fails fast at
# startup (raises KeyError instead of silently mailing a wrong staging URL).
FRONTEND_URL = os.environ["FRONTEND_URL"]


async def notify_shortlisted(name: str, phone: str, email: str, schedule_token: str, is_test: bool = False):
    """Send shortlist notification with schedule link via WhatsApp + Email."""
    schedule_link = f"{FRONTEND_URL}/schedule-interview/{schedule_token}"

    # WhatsApp: ShortList campaign
    await send_whatsapp("ShortList", phone, email, [name, schedule_link], is_test=is_test)

    # Email
    html = f"""
    <p>Dear {name},</p>
    <p>Congratulations! After reviewing your responses, we are pleased to inform you that your profile aligns with our requirements.</p>
    <p>Please schedule a convenient time for your offline (in-person) interview using the link below:</p>
    <p><a href="{schedule_link}">{schedule_link}</a></p>
    <p>We look forward to our discussion and exploring how you can contribute to our team's research efforts.</p>
    <p>Best regards,<br>Blubridge Technologies</p>
    """
    await send_email(email, phone, "You're Shortlisted! Schedule Your Interview - Blubridge", html, is_test=is_test)


async def notify_rejected(name: str, phone: str, email: str, is_test: bool = False):
    """Send rejection notification via WhatsApp + Email. Returns True if at least one channel succeeded."""
    wa_ok = await send_whatsapp("Reject", phone, email, [], is_test=is_test)
    html = f"""
    <p>Dear {name},</p>
    <p>Thank you for your time and effort in completing our registration form.</p>
    <p>While your background and experience are impressive, we have decided to move forward with candidates whose profiles more closely align with our current requirements.</p>
    <p>We encourage you to apply for future opportunities at Blubridge Technologies.</p>
    <p>Wishing you the best in your future endeavours!</p>
    <p>Warm regards,<br>Blubridge Technologies</p>
    """
    em_ok = await send_email(email, phone, "Application Update - Blubridge Technologies", html, is_test=is_test)
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
    """Send schedule confirmation via WhatsApp + Email."""
    await send_whatsapp("Schedule Detail", phone, email, [name, date, time, OFFICE_LOCATION], is_test=is_test)
    html = f"""
    <p>Hi {name},</p>
    <p>Thank you for scheduling your interview with Blubridge Technologies. Your interview details are confirmed as follows:</p>
    <p><strong>Date:</strong> {date}<br><strong>Time:</strong> {time}<br><strong>Location:</strong> {OFFICE_LOCATION}</p>
    <p>We look forward to meeting you.</p>
    <p>Best regards,<br>Blubridge Technologies</p>
    """
    await send_email(email, phone, "Interview Scheduled - Blubridge Technologies", html, is_test=is_test)


async def notify_otp(name: str, phone: str, email: str, job_role: str, otp: str, date: str, time: str, is_test: bool = False):
    """Send OTP notification via WhatsApp + Email."""
    await send_whatsapp("OTP With Job", phone, email, [name, job_role, otp, phone, date, time, OFFICE_LOCATION], is_test=is_test)
    html = f"""
    <p>Hi {name},</p>
    <p>Your One-Time Password (OTP) to confirm your interview attendance at Blubridge Technologies is:</p>
    <h2>{otp}</h2>
    <p>Please provide this OTP along with your personal details at the office reception on the day of your interview.</p>
    <p><strong>Interview Details:</strong></p>
    <p><strong>Role:</strong> {job_role}<br><strong>Phone:</strong> {phone}<br><strong>Date:</strong> {date}<br><strong>Time:</strong> {time}<br><strong>Location:</strong> {OFFICE_LOCATION}</p>
    <p>This OTP is valid only for eight hours from your scheduled interview slot.</p>
    <p>Looking forward to seeing you soon!</p>
    <p>Best regards,<br>Blubridge Recruitment Team</p>
    """
    await send_email(email, phone, f"Your Interview OTP - Blubridge Technologies", html, is_test=is_test)


async def notify_missed_reminder(name: str, phone: str, email: str, role: str, date: str, time: str, schedule_token: str, is_test: bool = False):
    """Send missed interview reminder with reschedule link.

    Iter47 — WhatsApp template "Candidate FollowUp" now accepts 5 params
    ([name, role, formattedDate, time, schedule_link]) so the message carries
    the reschedule CTA directly, matching the updated PHP template.
    """
    schedule_link = f"{FRONTEND_URL}/schedule-interview/{schedule_token}"
    await send_whatsapp(
        "Candidate FollowUp", phone, email,
        [name, role, date, time, schedule_link],
        is_test=is_test,
    )
    html = f"""
    <p>Hi {name},</p>
    <p>We noticed you missed your scheduled interview at Blubridge. We understand unexpected situations may occur, so we'd like to offer you one final opportunity to reschedule.</p>
    <p>If you miss the interview again, you won't be able to apply for any positions at Blubridge for the next 3 months.</p>
    <p>If you're still interested, please use the link below to reschedule your interview at your earliest convenience:</p>
    <p><a href="{schedule_link}">Reschedule Your Interview</a></p>
    <p>Rescheduling is subject to available slots.</p>
    <p>Warm regards,<br>Blubridge Recruitment Team</p>
    """
    await send_email(email, phone, "Missed Interview - Reschedule Opportunity - Blubridge", html, is_test=is_test)


async def notify_schedule_reminder(name: str, phone: str, email: str, schedule_token: str, is_test: bool = False):
    """Send 24h reminder to schedule interview."""
    schedule_link = f"{FRONTEND_URL}/schedule-interview/{schedule_token}"
    await send_whatsapp("ShortList", phone, email, [name, schedule_link], is_test=is_test)
    html = f"""
    <p>Dear {name},</p>
    <p>This is a reminder that you have been shortlisted for an interview at Blubridge Technologies, but you haven't scheduled your interview yet.</p>
    <p>Please schedule your interview at the earliest using the link below:</p>
    <p><a href="{schedule_link}">{schedule_link}</a></p>
    <p>Best regards,<br>Blubridge Technologies</p>
    """
    await send_email(email, phone, "Reminder: Schedule Your Interview - Blubridge", html, is_test=is_test)
