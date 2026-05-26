"""Centralized messaging service — WhatsApp (AiSensy) + Email (Resend HTTPS API).

Single source of truth for the outbound gate (TEST_MODE). NEVER call AiSensy
or Resend directly from anywhere else — always go through `send_whatsapp` /
`send_email` so the test-mode rules are enforced uniformly.
"""

import os
import logging
import httpx

from _fmt import fmt_date, fmt_time

_logger = logging.getLogger("messaging")

# ============ CONFIG (from environment) ============

AISENSY_API_URL = "https://backend.aisensy.com/campaign/t1/api/v2"
AISENSY_API_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpZCI6IjY5NDI0MTYwNzA4MDcwNjE5YzAyZWFhNiIsIm5hbWUiOiJCbHVicmlkZ2V0ZWNobm9sb2dpZXMiLCJhcHBOYW1lIjoiQWlTZW5zeSIsImNsaWVudElkIjoiNjg5NDRlOThiMjQ3NDQwYzBkYzljNzI3IiwiYWN0aXZlUGxhbiI6IkZSRUVfRk9SRVZFUiIsImlhdCI6MTc2NTk0OTc5Mn0.16lJKhbj6JfK_1zzzUgLMwxy5IaqBwu3ljV08xBLRBs"

# iter106 — Resend HTTPS API is the SOLE email transport. SMTP has been
# fully removed (Render free-tier blocks outbound SMTP, and the Gmail
# relay produced intermittent timeouts). All three env vars are read
# fresh from Render; only the from-email/from-name carry safe defaults
# so deploys without overrides keep working out-of-box.
RESEND_API_KEY = os.environ.get("RESEND_API_KEY", "").strip()
RESEND_FROM_EMAIL = os.environ.get("RESEND_FROM_EMAIL", "information.team@blubrg.com").strip()
RESEND_FROM_NAME = os.environ.get("RESEND_FROM_NAME", "BluBridge Hiring").strip()
# iter119 — Reply-To routing. Applicant clicks Reply in their mail client →
# the reply automatically targets the recruitment inbox below, NOT the sender
# transactional address. Override via `MAIL_REPLY_TO` env on Render.
MAIL_REPLY_TO = os.environ.get("MAIL_REPLY_TO", "hiring@blubridge.com").strip()

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
    # iter92 — exclude superseded rows so OTP lookups never return a stale
    # OTP from a previous tester re-registration session.
    if schedule_date:
        doc = await _db.bb_registrations.find_one(
            {"$or": clauses, "schedule_date": schedule_date,
             "otp": {"$exists": True, "$nin": [None, ""]},
             "superseded": {"$ne": True}},
            {"_id": 0, "otp": 1},
            sort=[("otp_sent_at", -1)],
        )
        if doc and doc.get("otp"):
            return str(doc["otp"])

    # Fallback: latest OTP regardless of schedule_date (handles the
    # historical case where schedule_date wasn't recorded on the OTP doc).
    doc = await _db.bb_registrations.find_one(
        {"$or": clauses, "otp": {"$exists": True, "$nin": [None, ""]},
         "superseded": {"$ne": True}},
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

    # Tester-only debug — surfaces exact template params reaching the provider
    # so we can confirm the right name/role/date arrived from the new submission.
    if is_test_mode():
        _logger.info(
            f"[MSG DEBUG] channel=wa campaign={campaign_name} "
            f"template_email={email} template_phone={phone} "
            f"template_params={template_params}"
        )

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


# ============ EMAIL (Resend HTTPS API) ============

# iter73 — Branded email shell aligned VERBATIM with the BluBridge PDF
# reference (white body, blue #2071b9 accents, BLUBRIDGE wordmark in
# footer only). No top header bar — the salutation opens the email.
# iter117 — Footer wordmark replaced with the official BluBridge PNG logo
# hosted on Emergent's customer-assets CDN (stable HTTPS, no CORS/auth
# issues). Override via `BLUBRIDGE_LOGO_URL` env var if the asset URL ever
# changes — code falls back to the hosted default if unset.
_BRAND_BLUE = "#2071b9"
_BRAND_BLUE_DARK = "#1a5a96"
_BLUBRIDGE_LOGO_URL = os.environ.get(
    "BLUBRIDGE_LOGO_URL",
    "https://customer-assets.emergentagent.com/job_695f5e57-e07f-4640-8643-86f62b12ce9d/artifacts/mr5kvgxn_image.png",
)


def _email_shell(body_html: str, with_logo_footer: bool = True) -> str:
    """Wrap notification body HTML in a clean white email envelope that
    mirrors the PDF reference exactly. Inline styles only.

    iter117 — Footer now ALWAYS renders the official BluBridge image logo
    (the `with_logo_footer` parameter is preserved for API compatibility but
    no longer suppresses the logo — every recruitment email must carry the
    standardized brand mark). The `<img>` uses an absolute HTTPS URL with
    explicit width/height for Outlook + Gmail mobile parity, plus a text
    `alt` so screen readers and image-blocked previews still surface the
    brand name.
    """
    # `with_logo_footer` kept for backward compatibility — intentionally
    # unused; every email gets the standardized footer logo (iter117).
    _ = with_logo_footer
    footer_logo = f"""
        <tr><td style="padding:36px 32px 32px 32px;text-align:left;">
          <img src="{_BLUBRIDGE_LOGO_URL}" alt="Blubridge"
               width="200" height="auto"
               style="display:block;width:200px;max-width:60%;height:auto;border:0;outline:none;text-decoration:none;-ms-interpolation-mode:bicubic;" />
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
    """Send email via Resend HTTPS API. Returns True on success.
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

    # Tester-only debug — confirms recipient + subject reaching the API layer.
    if is_test_mode():
        _logger.info(
            f"[MSG DEBUG] channel=email template_email={to_email} "
            f"template_phone={phone} subject={subject!r}"
        )

    try:
        if not RESEND_API_KEY:
            _logger.error(
                f"[Email:FAIL] stage=config RESEND_API_KEY missing — set it on Render. "
                f"to={to_email} subject={subject}"
            )
            return False

        # Build the HTTP payload exactly per Resend's API:
        #   POST https://api.resend.com/emails
        #   Authorization: Bearer <api_key>
        #   { from, to, subject, html }
        from_field = (
            f"{RESEND_FROM_NAME} <{RESEND_FROM_EMAIL}>"
            if RESEND_FROM_NAME else RESEND_FROM_EMAIL
        )
        payload = {
            "from": from_field,
            "to": [to_email],
            "subject": subject,
            "html": html_body,
        }
        # iter120 — Reply-To dual-belt approach. Previous iter119 passed
        # `reply_to=["hiring@blubridge.com"]` (list form per Resend docs)
        # but candidates' Gmail/Outlook Reply still pointed at the From
        # address (information.team@blubrg.com). Two fixes layered:
        #   1. `reply_to` as a PLAIN STRING (Resend accepts both, string
        #      form is the canonical pre-array contract).
        #   2. Custom `headers["Reply-To"]` so the raw RFC-5322 Reply-To
        #      header is injected into the MIME envelope directly. Even
        #      if Resend's JSON-to-header mapping ever drops `reply_to`,
        #      the custom header guarantees mail clients honour it.
        # Setting both is safe — Resend deduplicates headers.
        if MAIL_REPLY_TO:
            payload["reply_to"] = MAIL_REPLY_TO
            payload["headers"] = {"Reply-To": MAIL_REPLY_TO}

        if is_test_mode():
            _logger.info(
                f"[Email DEBUG] provider=resend api=https port=443 "
                f"from={from_field!r} reply_to={MAIL_REPLY_TO!r} to={to_email}"
            )

        _logger.info(
            f"[Email:REQ] provider=resend from={from_field!r} "
            f"reply_to={MAIL_REPLY_TO!r} to={to_email} subject={subject!r}"
        )
        try:
            async with httpx.AsyncClient(timeout=20.0) as client:
                resp = await client.post(
                    "https://api.resend.com/emails",
                    headers={
                        "Authorization": f"Bearer {RESEND_API_KEY}",
                        "Content-Type": "application/json",
                    },
                    json=payload,
                )
        except (httpx.TimeoutException, httpx.NetworkError) as _ne:
            _logger.error(
                f"[Email:FAIL] stage=transport provider=resend to={to_email} err={_ne!r}"
            )
            return False

        if resp.status_code in (200, 201):
            try:
                msg_id = (resp.json() or {}).get("id")
            except Exception:
                msg_id = None
            _logger.info(
                f"[Email] SENT via=resend to={to_email} subject={subject} id={msg_id}"
            )
            return True

        _logger.error(
            f"[Email:FAIL] stage=api provider=resend status={resp.status_code} "
            f"to={to_email} body={resp.text[:300]!r}"
        )
        return False
    except Exception as e:
        # Catch-all so an unexpected runtime error never propagates up to a
        # worker / FastAPI handler. Always log and return False.
        _logger.error(
            f"[Email:FAIL] stage=unexpected to={to_email} subject={subject} err={e!r}"
        )
        return False


# ============ HIGH-LEVEL NOTIFICATION FUNCTIONS ============

# Hard-required env: omit the silent default so misconfiguration fails fast at
# startup (raises KeyError instead of silently mailing a wrong staging URL).
FRONTEND_URL = os.environ["FRONTEND_URL"]


def build_public_url(path: str) -> str:
    """iter91 — Single source of truth for every public-facing URL we put
    inside WhatsApp / email templates and API response payloads.

    Reads PUBLIC_BASE_URL (preferred) and falls back to FRONTEND_URL for
    backward compatibility. Read FRESH per call so a value change on the
    hosting dashboard (Render / Emergent) takes effect on the NEXT request
    without forcing a full backend restart.

    Strips trailing slash on base and leading slash on path so concatenation
    is deterministic regardless of how either side was provided.

    Tester-only [LINK DEBUG] log surfaces the resolved base + final URL in
    TEST_MODE so we can confirm uniformity across modules in production logs.
    """
    base = (os.environ.get("PUBLIC_BASE_URL") or os.environ.get("FRONTEND_URL") or FRONTEND_URL or "").rstrip("/")
    leaf = (path or "").lstrip("/")
    url = f"{base}/{leaf}" if base else f"/{leaf}"
    if is_test_mode():
        _src = "PUBLIC_BASE_URL" if os.environ.get("PUBLIC_BASE_URL") else "FRONTEND_URL"
        _logger.info(f"[LINK DEBUG] base_url_source={_src} generated_url={url}")
    return url


async def notify_shortlisted(name: str, phone: str, email: str, schedule_token: str, is_test: bool = False):
    """Send shortlist notification with schedule link via WhatsApp + Email.
    Returns (wa_ok, em_ok). iter73 — content verbatim from BluBridge PDF."""
    schedule_link = build_public_url(f"/schedule-interview/{schedule_token}")

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
    # iter94 — Post-interview rejection uses NEW "Final Reject" AiSensy template
    # (params: [candidate_name, job_role]). Form-condition rejection continues
    # to use existing "Reject" template via notify_rejected_with_reason — they
    # are now strictly isolated campaigns.
    wa_ok = await send_whatsapp(
        "Final Reject", phone, email,
        [name or "Candidate", job_role or "—"],
        is_test=is_test,
    )

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
    em_ok = await send_email(email, phone, tmpl["subject"], _email_shell(html), is_test=is_test)
    _logger.info(f"[Reject:{reason}] email={email} wa_ok={wa_ok} em_ok={em_ok} text={wa_text!r}")
    return bool(wa_ok or em_ok)


async def notify_schedule_confirmation(name: str, phone: str, email: str, date: str, time: str, is_test: bool = False):
    """Send schedule confirmation via WhatsApp + Email.
    iter73 — Content verbatim from BluBridge PDF reference.
    iter79 — Date/time displayed as `dd-mm-yyyy` + `hh:mm AM/PM`."""
    date = fmt_date(date)
    time = fmt_time(time)
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


async def notify_otp(name: str, phone: str, email: str, job_role: str, otp: str, date: str, time: str, is_test: bool = False, send_wa: bool = True, send_email_channel: bool = True):
    """Send OTP notification via WhatsApp + Email.
    iter73 — Content + design verbatim from BluBridge PDF reference (OTP in
    blue inside a light-grey rectangular box).
    iter79 — Date/time displayed as `dd-mm-yyyy` + `hh:mm AM/PM`.
    iter107 — Returns (wa_ok, em_ok). Independent channel failures so the
    OTP worker can persist per-channel state and retry only the failed one.
    iter121 — `send_wa` / `send_email_channel` flags so the worker can
    attempt ONLY the channel that hasn't sent yet on retry ticks. Default
    True/True preserves existing callers' behavior. Note the email-channel
    flag is NOT named `send_email` to avoid shadowing the imported
    `send_email` function below."""
    date = fmt_date(date)
    time = fmt_time(time)
    _logger.info(
        f"[OTP:NOTIFY_START] email={email} phone={phone} role={job_role!r} "
        f"date={date} time={time} otp_len={len(str(otp))} "
        f"send_wa={send_wa} send_email_channel={send_email_channel}"
    )
    wa_ok = False
    if send_wa:
        try:
            wa_ok = await send_whatsapp("OTP With Job", phone, email, [name, job_role, otp, phone, date, time, OFFICE_LOCATION], is_test=is_test)
        except Exception as _we:
            _logger.exception(f"[OTP:NOTIFY_WA_EXC] email={email} err={_we!r}")
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
    em_ok = False
    if send_email_channel:
        try:
            em_ok = await send_email(email, phone, "Your Interview OTP - Blubridge Technologies", _email_shell(body), is_test=is_test)
        except Exception as _ee:
            _logger.exception(f"[OTP:NOTIFY_EMAIL_EXC] email={email} err={_ee!r}")
    _logger.info(
        f"[OTP:NOTIFY_DONE] email={email} wa_ok={wa_ok} em_ok={em_ok} "
        f"attempted_wa={send_wa} attempted_email={send_email_channel}"
    )
    return wa_ok, em_ok


async def notify_missed_reminder(name: str, phone: str, email: str, role: str, date: str, time: str, schedule_token: str, is_test: bool = False, send_wa: bool = True, send_email_channel: bool = True):
    """Send missed-interview / candidate follow-up via WhatsApp + Email.
    Returns (wa_ok, em_ok). iter73 — Email content verbatim from BluBridge
    PDF reference (no BLUBRIDGE footer logo per PDF; Reschedule button in
    brand blue).
    iter79 — Date/time displayed as `dd-mm-yyyy` + `hh:mm AM/PM`.

    AiSensy "Candidate Followups1" template now expects exactly 5 params:
    [name, role, date, time, schedule_link]. Aligned with PHP reference.
    iter122 — `send_wa` / `send_email_channel` flags so the worker can attempt
    ONLY the channel that hasn't already succeeded for this schedule_token
    (mirrors the iter121 OTP fix). Default True/True preserves all existing
    callers. The email-channel flag is named `send_email_channel` (not
    `send_email`) to avoid shadowing the imported `send_email` function."""
    date = fmt_date(date)
    time = fmt_time(time)
    schedule_link = build_public_url(f"/schedule-interview/{schedule_token}") if schedule_token else build_public_url("/")
    # iter113 — Independent try/except per channel so a WA exception cannot
    # stop the email send (mirrors the iter107 OTP fix).
    _logger.info(
        f"[MissedReminder:NOTIFY_START] email={email} phone={phone} role={role!r} "
        f"date={date} time={time} send_wa={send_wa} send_email_channel={send_email_channel}"
    )
    wa_ok = False
    if send_wa:
        try:
            wa_ok = await send_whatsapp(
                "Candidate Followups1", phone, email,
                [name, role, date, time, schedule_link],
                is_test=is_test,
            )
        except Exception as _we:
            _logger.exception(f"[MissedReminder:NOTIFY_WA_EXC] email={email} err={_we!r}")
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
    em_ok = False
    if send_email_channel:
        try:
            em_ok = await send_email(email, phone, "Missed Interview - Reschedule Opportunity - Blubridge", _email_shell(body, with_logo_footer=False), is_test=is_test)
        except Exception as _ee:
            _logger.exception(f"[MissedReminder:NOTIFY_EMAIL_EXC] email={email} err={_ee!r}")
    _logger.info(
        f"[MissedReminder:NOTIFY_DONE] email={email} wa_ok={wa_ok} em_ok={em_ok} "
        f"attempted_wa={send_wa} attempted_email={send_email_channel}"
    )
    return wa_ok, em_ok


async def notify_schedule_reminder(name: str, phone: str, email: str, schedule_token: str, is_test: bool = False):
    """Send 24h reminder to schedule interview. iter73 — uses the same
    PDF-aligned design as the shortlist email."""
    schedule_link = build_public_url(f"/schedule-interview/{schedule_token}")
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
