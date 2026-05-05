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

FRONTEND_URL = os.environ.get("FRONTEND_URL", "https://applicant-details.preview.emergentagent.com")


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
    """Send missed interview reminder with reschedule link."""
    schedule_link = f"{FRONTEND_URL}/schedule-interview/{schedule_token}"
    await send_whatsapp("Candidate FollowUp", phone, email, [name, role, date, time], is_test=is_test)
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
