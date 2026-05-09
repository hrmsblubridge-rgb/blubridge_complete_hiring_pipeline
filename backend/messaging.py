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
            body_text = resp.text or ""
            # iter74 — Stricter success check: HTTP 200 alone is not enough.
            # AiSensy occasionally returns 200 with an embedded error body
            # (e.g. `{"message":"Template params does not match…"}` and no
            # `success`/`submitted_message_id` keys). Parse the JSON body
            # and require `success == true` (or a `submitted_message_id`).
            ok = False
            try:
                j = resp.json() if body_text else {}
                if resp.status_code == 200:
                    success_flag = str(j.get("success", "")).lower() == "true"
                    submitted = bool(j.get("submitted_message_id"))
                    ok = success_flag or submitted
            except Exception:
                # Non-JSON 200 response → conservative success on raw 200.
                ok = resp.status_code == 200
            _logger.info(
                f"[WhatsApp:RESP] campaign={campaign_name} phone={safe_phone} "
                f"status={resp.status_code} ok={ok} body={body_text[:400]}"
            )
            return ok
    except Exception as e:
        _logger.error(f"[WhatsApp:EXC] campaign={campaign_name} phone={safe_phone}: {e}")
        return False


async def send_whatsapp_with_diagnostics(campaign_name: str, phone: str, email: str, template_params: list):
    """iter74 — Diagnostic variant that returns the full AiSensy probe data
    (request payload + response body + parsed flags). Used by the
    `/api/bb/diagnostics/whatsapp-probe` endpoint to produce a consolidated
    side-by-side report of all 5 campaigns. ONLY used by Admin diagnostics
    — production sends still go through `send_whatsapp`."""
    allowed, reason = await can_send_message(email, phone)
    if not allowed:
        return {
            "campaign": campaign_name, "phone": phone, "params": template_params,
            "blocked": True, "reason": reason, "ok": False,
            "status_code": None, "response_body": None, "submitted_message_id": None,
        }
    safe_phone = _norm_phone(phone)
    if len(safe_phone) == 10:
        safe_phone = "91" + safe_phone

    payload = {
        "apiKey": AISENSY_API_KEY,
        "campaignName": campaign_name,
        "destination": safe_phone,
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

    out = {
        "campaign": campaign_name,
        "phone": safe_phone,
        "param_count": len(template_params),
        "params": template_params,
        "userName": "Blubridgetechnologies",
        "blocked": False,
        "reason": reason,
        "status_code": None,
        "response_body": None,
        "response_json": None,
        "submitted_message_id": None,
        "success_flag": None,
        "error_message": None,
        "ok": False,
    }
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(AISENSY_API_URL, json=payload)
            out["status_code"] = resp.status_code
            out["response_body"] = (resp.text or "")[:1000]
            try:
                j = resp.json()
                out["response_json"] = j
                out["submitted_message_id"] = j.get("submitted_message_id")
                out["success_flag"] = j.get("success")
                out["error_message"] = j.get("message") or j.get("error")
                if resp.status_code == 200:
                    out["ok"] = (
                        str(j.get("success", "")).lower() == "true"
                        or bool(j.get("submitted_message_id"))
                    )
            except Exception:
                out["ok"] = resp.status_code == 200
    except Exception as e:
        out["error_message"] = f"Exception: {e}"
    return out


# ============ EMAIL (SMTP) ============

# iter73 — Branded email shell aligned VERBATIM with the BluBridge PDF
# reference (white body, blue #2071b9 accents, BLUBRIDGE wordmark in
# footer only). No top header bar — the salutation opens the email.
_BRAND_BLUE = "#2071b9"
_BRAND_BLUE_DARK = "#1a5a96"


def _email_shell(body_html: str, with_logo_footer: bool = True) -> str:
    """Wrap notification body HTML in a clean white email envelope that
    mirrors the PDF reference exactly. Inline styles only."""
    footer_logo = ""
    if with_logo_footer:
        footer_logo = f"""
        <tr><td style="padding:36px 32px 32px 32px;text-align:left;">
          <p style="margin:0;font-family:Georgia,'Times New Roman',serif;font-weight:800;letter-spacing:0.22em;color:{_BRAND_BLUE};font-size:22px;">BLUBRIDGE</p>
        </td></tr>
        """
    return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head>
<body style="margin:0;padding:0;background:#ffffff;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif;color:#1f2937;">
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="background:#ffffff;padding:24px 16px;">
    <tr><td align="center">
      <table role="presentation" width="640" cellpadding="0" cellspacing="0" border="0" style="max-width:640px;background:#ffffff;">
        <tr><td style="padding:24px 32px 0 32px;font-size:15px;line-height:1.7;color:#1f2937;">
          {body_html}
        </td></tr>
        {footer_logo}
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
    Returns (wa_ok, em_ok). iter73 — content verbatim from BluBridge PDF."""
    schedule_link = f"{FRONTEND_URL}/schedule-interview/{schedule_token}"

    # WhatsApp: ShortList campaign
    wa_ok = await send_whatsapp("ShortList", phone, email, [name, schedule_link], is_test=is_test)

    # Email — verbatim PDF wording, with a blue CTA button.
    body = f"""
    <p style="margin:0 0 16px 0;">Dear {name},</p>
    <p style="margin:0 0 16px 0;">Congratulations! After reviewing your responses, we are pleased to inform you that your profile aligns with our requirements.</p>
    <p style="margin:0 0 16px 0;">Please schedule a convenient time for your offline(in-person) interview using the link below:</p>
    <p style="text-align:center;margin:28px 0;">
      <a href="{schedule_link}" style="display:inline-block;background:{_BRAND_BLUE};color:#ffffff;text-decoration:none;padding:12px 28px;border-radius:6px;font-weight:600;font-size:14px;">Schedule My Interview</a>
    </p>
    <p style="margin:0 0 16px 0;font-size:12px;color:#6b7280;word-break:break-all;">Or paste this link in your browser: <a href="{schedule_link}" style="color:{_BRAND_BLUE};">{schedule_link}</a></p>
    <p style="margin:0 0 16px 0;">We look forward to our discussion and exploring how you can contribute to our team's research efforts.</p>
    <p style="margin:24px 0 4px 0;">Best regards,</p>
    <p style="margin:0;">Blubridge Technologies</p>
    """
    em_ok = await send_email(email, phone, "You're Shortlisted! Schedule Your Interview - Blubridge", _email_shell(body), is_test=is_test)
    return wa_ok, em_ok


async def notify_rejected(name: str, phone: str, email: str, job_role: str = "", is_test: bool = False):
    """Send rejection (post-attended) via WhatsApp + Email.
    iter73 — Email content + design verbatim from BluBridge PDF reference,
    including the blue 'Job Role' highlight section. `job_role` is optional;
    omitted from the highlight section when not supplied (registration-stage
    rejection)."""
    wa_ok = await send_whatsapp("Reject", phone, email, [], is_test=is_test)

    # Blue 'Job Role' highlight (table-style) — only if job_role supplied.
    job_role_block = ""
    if job_role:
        job_role_block = f"""
    <table role="presentation" cellpadding="0" cellspacing="0" border="0" style="margin:18px 0 24px 0;">
      <tr>
        <td style="background:{_BRAND_BLUE};color:#ffffff;padding:10px 18px;font-weight:600;font-size:14px;border-radius:4px 0 0 4px;">Job Role</td>
        <td style="background:#f1f5f9;color:#1f2937;padding:10px 18px;font-size:14px;border-radius:0 4px 4px 0;">{job_role}</td>
      </tr>
    </table>
        """

    body = f"""
    <p style="margin:0 0 16px 0;">Dear {name},</p>
    <p style="margin:0 0 16px 0;">Thank you for your interest in the opportunity with Blubridge and for investing your time in our hiring process.</p>
    <p style="margin:0 0 16px 0;">After careful evaluation, we regret to inform you that we will not be moving forward with your application at this time, as your scores did not meet our minimum qualifying standard of 80%.</p>
    <p style="margin:0 0 8px 0;">Below is a summary of your performance for your reference:</p>
    {job_role_block}
    <p style="margin:0 0 16px 0;">We genuinely appreciate your effort and encourage you to stay connected with Blubridge for future opportunities that may better align with your profile and skills.</p>
    <p style="margin:0 0 16px 0;">We wish you all the best in your future career endeavors. Stay motivated and keep striving for excellence!</p>
    <p style="margin:24px 0 4px 0;">Warm regards,</p>
    <p style="margin:0;">Blubridge Recruitment Team</p>
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
    """Send schedule confirmation via WhatsApp + Email.
    iter73 — Content verbatim from BluBridge PDF reference."""
    wa_ok = await send_whatsapp("Schedule Detail", phone, email, [name, date, time, OFFICE_LOCATION], is_test=is_test)
    body = f"""
    <p style="margin:0 0 16px 0;">Hi {name},</p>
    <p style="margin:0 0 16px 0;">Thank you for scheduling your interview with Blubridge Technologies. Your interview details are confirmed as follows:</p>
    <table role="presentation" cellpadding="0" cellspacing="0" border="0" style="margin:18px 0 22px 0;background:#f8fafc;border-left:4px solid {_BRAND_BLUE};padding:0;width:100%;">
      <tr><td style="padding:14px 18px;">
        <p style="margin:0 0 6px 0;color:#374151;"><strong>Date:</strong> {date}</p>
        <p style="margin:0 0 6px 0;color:#374151;"><strong>Time:</strong> {time}</p>
        <p style="margin:0;color:#374151;"><strong>Location:</strong> {OFFICE_LOCATION}</p>
      </td></tr>
    </table>
    <p style="margin:0 0 8px 0;">Your interview will consist of the following rounds:</p>
    <p style="margin:0 0 6px 0;"><strong>Round 1:</strong> Logical Reasoning &amp; Aptitude (100 minutes)</p>
    <p style="margin:0 0 6px 0;"><strong>Round 2:</strong> Advanced Logical Reasoning (30 minutes)</p>
    <p style="margin:0 0 16px 0;font-style:italic;color:#6b7280;">If shortlisted, a further round will be conducted.</p>
    <p style="margin:0 0 16px 0;">We look forward to meeting you.</p>
    <p style="margin:24px 0 4px 0;">Best regards,</p>
    <p style="margin:0;">Blubridge Technologies</p>
    """
    em_ok = await send_email(email, phone, "Interview Scheduled - Blubridge Technologies", _email_shell(body), is_test=is_test)
    return wa_ok, em_ok


async def notify_otp(name: str, phone: str, email: str, job_role: str, otp: str, date: str, time: str, is_test: bool = False):
    """Send OTP notification via WhatsApp + Email.
    iter73 — Content + design verbatim from BluBridge PDF reference (OTP in
    blue inside a light-grey rectangular box)."""
    wa_ok = await send_whatsapp("OTP With Job", phone, email, [name, job_role, otp, phone, date, time, OFFICE_LOCATION], is_test=is_test)
    body = f"""
    <p style="margin:0 0 16px 0;">Hi {name},</p>
    <p style="margin:0 0 16px 0;">Your One-Time Password (OTP) to confirm your interview attendance at Blubridge Technologies is:</p>
    <div style="background:#f1f5f9;border:1px solid #e2e8f0;border-radius:6px;padding:22px;text-align:center;margin:18px 0 22px 0;">
      <span style="color:{_BRAND_BLUE};font-size:38px;font-weight:700;letter-spacing:0.18em;font-family:'Courier New',Courier,monospace;">{otp}</span>
    </div>
    <p style="margin:0 0 16px 0;">Please provide this OTP along with your personal details at the office reception on the day of your interview.</p>
    <p style="margin:0 0 6px 0;font-weight:600;color:#1f2937;">Interview Details:</p>
    <table role="presentation" cellpadding="0" cellspacing="0" border="0" style="margin:6px 0 22px 0;">
      <tr><td style="padding:3px 18px 3px 0;color:#6b7280;width:80px;">Role:</td><td style="padding:3px 0;color:#1f2937;">{job_role}</td></tr>
      <tr><td style="padding:3px 18px 3px 0;color:#6b7280;">Phone:</td><td style="padding:3px 0;color:#1f2937;">{phone}</td></tr>
      <tr><td style="padding:3px 18px 3px 0;color:#6b7280;">Date:</td><td style="padding:3px 0;color:#1f2937;">{date}</td></tr>
      <tr><td style="padding:3px 18px 3px 0;color:#6b7280;">Time:</td><td style="padding:3px 0;color:#1f2937;">{time}</td></tr>
      <tr><td style="padding:3px 18px 3px 0;color:#6b7280;vertical-align:top;">Location:</td><td style="padding:3px 0;color:#1f2937;">{OFFICE_LOCATION}</td></tr>
    </table>
    <p style="margin:0 0 16px 0;">This OTP is valid only for eight hours from your scheduled interview slot.</p>
    <p style="margin:0 0 16px 0;">Looking forward to seeing you soon!</p>
    <p style="margin:24px 0 4px 0;">Best regards,</p>
    <p style="margin:0;">Blubridge Recruitment Team</p>
    """
    em_ok = await send_email(email, phone, "Your Interview OTP - Blubridge Technologies", _email_shell(body), is_test=is_test)
    return wa_ok, em_ok


async def notify_missed_reminder(name: str, phone: str, email: str, role: str, date: str, time: str, schedule_token: str, is_test: bool = False):
    """Send missed-interview / candidate follow-up via WhatsApp + Email.
    Returns (wa_ok, em_ok). iter73 — Email content verbatim from BluBridge
    PDF reference (no BLUBRIDGE footer logo per PDF; Reschedule button in
    brand blue).

    AiSensy "Candidate Followups1" template now expects exactly 5 params:
    [name, role, date, time, schedule_link]. Aligned with PHP reference."""
    schedule_link = f"{FRONTEND_URL}/schedule-interview/{schedule_token}" if schedule_token else FRONTEND_URL
    wa_ok = await send_whatsapp(
        "Candidate Followups1", phone, email,
        [name, role, date, time, schedule_link],
        is_test=is_test,
    )
    body = f"""
    <p style="margin:0 0 16px 0;">Hi {name},</p>
    <p style="margin:0 0 16px 0;">We noticed you missed your scheduled interview at Blubridge. We understand unexpected situations may occur, so we'd like to offer you one final opportunity to reschedule.</p>
    <p style="margin:0 0 16px 0;">If you miss the interview again, you won't be able to apply for any positions at Blubridge for the next 3 months.</p>
    <p style="margin:0 0 16px 0;">If you're still interested, please use the link below to reschedule your interview at your earliest convenience:</p>
    <p style="text-align:center;margin:28px 0;">
      <a href="{schedule_link}" style="display:inline-block;background:{_BRAND_BLUE};color:#ffffff;text-decoration:none;padding:12px 28px;border-radius:6px;font-weight:600;font-size:14px;">Reschedule Your Interview</a>
    </p>
    <p style="margin:0 0 16px 0;">Rescheduling is subject to available slots.</p>
    <p style="margin:24px 0 4px 0;">Warm regards,</p>
    <p style="margin:0;">Blubridge Recruitment Team</p>
    """
    em_ok = await send_email(email, phone, "Missed Interview - Reschedule Opportunity - Blubridge", _email_shell(body, with_logo_footer=False), is_test=is_test)
    return wa_ok, em_ok


async def notify_schedule_reminder(name: str, phone: str, email: str, schedule_token: str, is_test: bool = False):
    """Send 24h reminder to schedule interview. iter73 — uses the same
    PDF-aligned design as the shortlist email."""
    schedule_link = f"{FRONTEND_URL}/schedule-interview/{schedule_token}"
    await send_whatsapp("ShortList", phone, email, [name, schedule_link], is_test=is_test)
    body = f"""
    <p style="margin:0 0 16px 0;">Dear {name},</p>
    <p style="margin:0 0 16px 0;">This is a reminder that you have been shortlisted for an interview at Blubridge Technologies, but you haven't scheduled your interview yet.</p>
    <p style="margin:0 0 16px 0;">Please schedule your interview at the earliest using the link below:</p>
    <p style="text-align:center;margin:28px 0;">
      <a href="{schedule_link}" style="display:inline-block;background:{_BRAND_BLUE};color:#ffffff;text-decoration:none;padding:12px 28px;border-radius:6px;font-weight:600;font-size:14px;">Schedule My Interview</a>
    </p>
    <p style="margin:0 0 16px 0;font-size:12px;color:#6b7280;word-break:break-all;">Or paste this link: <a href="{schedule_link}" style="color:{_BRAND_BLUE};">{schedule_link}</a></p>
    <p style="margin:24px 0 4px 0;">Best regards,</p>
    <p style="margin:0;">Blubridge Technologies</p>
    """
    await send_email(email, phone, "Reminder: Schedule Your Interview - Blubridge", _email_shell(body), is_test=is_test)
