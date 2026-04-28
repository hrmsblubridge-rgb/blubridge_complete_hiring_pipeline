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

SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = 465
SMTP_USER = "hr@blubridge.com"
SMTP_PASSWORD = "tmiu rkqp fxcw nwxf"
FROM_EMAIL = "hr@blubridge.com"

OFFICE_LOCATION = "30, Norton Road, Mandavelipakkam, Raja Annamalai Puram, Chennai, Tamil Nadu - 600028."


def _is_enabled(flag: str) -> bool:
    return os.environ.get(flag, "false").lower() == "true"


def _resolve_recipient(phone: str, email: str) -> tuple:
    """Central TEST_MODE guard — overrides ALL recipients."""
    if _is_enabled("TEST_MODE"):
        test_phone = os.environ.get("TEST_PHONE", "9443109903")
        test_email = os.environ.get("TEST_EMAIL", "rishi.nayak@blubridge.com")
        _logger.info(f"[TEST_MODE] Overriding recipient: phone={phone}->{test_phone}, email={email}->{test_email}")
        return test_phone, test_email
    return phone, email


# ============ WHATSAPP (AiSensy) ============

async def send_whatsapp(campaign_name: str, phone: str, email: str, template_params: list):
    """Send WhatsApp via AiSensy API. Returns True on success."""
    if not _is_enabled("ENABLE_WHATSAPP"):
        _logger.info(f"[SKIP] WhatsApp disabled: campaign={campaign_name}")
        return False

    safe_phone, _ = _resolve_recipient(phone, email)
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

async def send_email(to_email: str, phone: str, subject: str, html_body: str):
    """Send email via SMTP SSL. Returns True on success."""
    if not _is_enabled("ENABLE_EMAIL"):
        _logger.info(f"[SKIP] Email disabled: to={to_email}, subject={subject}")
        return False

    _, safe_email = _resolve_recipient(phone, to_email)

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


async def notify_shortlisted(name: str, phone: str, email: str, schedule_token: str):
    """Send shortlist notification with schedule link via WhatsApp + Email."""
    schedule_link = f"{FRONTEND_URL}/schedule-interview/{schedule_token}"

    # WhatsApp: ShortList campaign
    await send_whatsapp("ShortList", phone, email, [name, schedule_link])

    # Email
    html = f"""
    <p>Dear {name},</p>
    <p>Congratulations! After reviewing your responses, we are pleased to inform you that your profile aligns with our requirements.</p>
    <p>Please schedule a convenient time for your offline (in-person) interview using the link below:</p>
    <p><a href="{schedule_link}">{schedule_link}</a></p>
    <p>We look forward to our discussion and exploring how you can contribute to our team's research efforts.</p>
    <p>Best regards,<br>Blubridge Technologies</p>
    """
    await send_email(email, phone, "You're Shortlisted! Schedule Your Interview - Blubridge", html)


async def notify_rejected(name: str, phone: str, email: str):
    """Send rejection notification via WhatsApp + Email."""
    # WhatsApp: Reject campaign
    await send_whatsapp("Reject", phone, email, [])

    # Email
    html = f"""
    <p>Dear {name},</p>
    <p>Thank you for your time and effort in completing our registration form.</p>
    <p>While your background and experience are impressive, we have decided to move forward with candidates whose profiles more closely align with our current requirements.</p>
    <p>We encourage you to apply for future opportunities at Blubridge Technologies.</p>
    <p>Wishing you the best in your future endeavours!</p>
    <p>Warm regards,<br>Blubridge Technologies</p>
    """
    await send_email(email, phone, "Application Update - Blubridge Technologies", html)


async def notify_schedule_confirmation(name: str, phone: str, email: str, date: str, time: str):
    """Send schedule confirmation via WhatsApp + Email."""
    # WhatsApp: Schedule Detail campaign
    await send_whatsapp("Schedule Detail", phone, email, [name, date, time, OFFICE_LOCATION])

    # Email
    html = f"""
    <p>Hi {name},</p>
    <p>Thank you for scheduling your interview with Blubridge Technologies. Your interview details are confirmed as follows:</p>
    <p><strong>Date:</strong> {date}<br><strong>Time:</strong> {time}<br><strong>Location:</strong> {OFFICE_LOCATION}</p>
    <p>We look forward to meeting you.</p>
    <p>Best regards,<br>Blubridge Technologies</p>
    """
    await send_email(email, phone, "Interview Scheduled - Blubridge Technologies", html)


async def notify_otp(name: str, phone: str, email: str, job_role: str, otp: str, date: str, time: str):
    """Send OTP notification via WhatsApp + Email."""
    # WhatsApp: OTP With Job campaign
    await send_whatsapp("OTP With Job", phone, email, [name, job_role, otp, phone, date, time, OFFICE_LOCATION])

    # Email
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
    await send_email(email, phone, f"Your Interview OTP - Blubridge Technologies", html)


async def notify_missed_reminder(name: str, phone: str, email: str, role: str, date: str, time: str, schedule_token: str):
    """Send missed interview reminder with reschedule link."""
    schedule_link = f"{FRONTEND_URL}/schedule-interview/{schedule_token}"

    # WhatsApp: Candidate FollowUp campaign
    await send_whatsapp("Candidate FollowUp", phone, email, [name, role, date, time])

    # Email
    html = f"""
    <p>Hi {name},</p>
    <p>We noticed you missed your scheduled interview at Blubridge. We understand unexpected situations may occur, so we'd like to offer you one final opportunity to reschedule.</p>
    <p>If you miss the interview again, you won't be able to apply for any positions at Blubridge for the next 3 months.</p>
    <p>If you're still interested, please use the link below to reschedule your interview at your earliest convenience:</p>
    <p><a href="{schedule_link}">Reschedule Your Interview</a></p>
    <p>Rescheduling is subject to available slots.</p>
    <p>Warm regards,<br>Blubridge Recruitment Team</p>
    """
    await send_email(email, phone, "Missed Interview - Reschedule Opportunity - Blubridge", html)


async def notify_schedule_reminder(name: str, phone: str, email: str, schedule_token: str):
    """Send 24h reminder to schedule interview."""
    schedule_link = f"{FRONTEND_URL}/schedule-interview/{schedule_token}"

    # WhatsApp: ShortList campaign (re-send schedule link)
    await send_whatsapp("ShortList", phone, email, [name, schedule_link])

    # Email
    html = f"""
    <p>Dear {name},</p>
    <p>This is a reminder that you have been shortlisted for an interview at Blubridge Technologies, but you haven't scheduled your interview yet.</p>
    <p>Please schedule your interview at the earliest using the link below:</p>
    <p><a href="{schedule_link}">{schedule_link}</a></p>
    <p>Best regards,<br>Blubridge Technologies</p>
    """
    await send_email(email, phone, "Reminder: Schedule Your Interview - Blubridge", html)
