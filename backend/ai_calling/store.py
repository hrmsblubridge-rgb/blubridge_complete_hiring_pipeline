"""Shared state, settings and row validation for the AI Calling module.

Collections owned by this module (never touches existing hiring collections):
  ai_call_settings, ai_test_candidates, ai_test_batches, ai_call_jobs, ai_calls
"""
import re
from datetime import datetime, timezone, timedelta, date

IST = timezone(timedelta(hours=5, minutes=30))
SETTINGS_ID = "global"
MODES = ("off", "testing", "live")

COLUMNS = [
    "candidate_name", "phone_number", "job_role", "interview_date", "interview_time",
    "language", "company_name", "office_address", "approved_for_test_call",
]
LANGUAGES = {"english": "English", "tamil": "Tamil"}

SETTINGS_DEFAULTS = {
    "mode": "off",
    "mode_version": 1,
    "emergency_stop": False,
    "daily_call_limit": 20,
    "max_concurrent_calls": 1,
    "call_window_start": "10:00",
    "call_window_end": "19:00",
    "default_company_name": "BluBridge",
    "default_office_address": "",
    "live_retry_no_answer": 1,
    "live_call_hours_before": 24,
}
EDITABLE_SETTINGS = {
    "daily_call_limit", "max_concurrent_calls", "call_window_start", "call_window_end",
    "default_company_name", "default_office_address",
}

_state = {"db": None, "auth": None}


def db():
    return _state["db"]


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def serialize(doc: dict) -> dict:
    if not doc:
        return doc
    out = {k: v for k, v in doc.items() if k != "_id"}
    out["id"] = str(doc["_id"])
    return out


async def get_settings() -> dict:
    await db().ai_call_settings.update_one(
        {"_id": SETTINGS_ID}, {"$setOnInsert": {**SETTINGS_DEFAULTS, "created_at": now_iso()}}, upsert=True
    )
    doc = await db().ai_call_settings.find_one({"_id": SETTINGS_ID})
    return {**SETTINGS_DEFAULTS, **{k: v for k, v in doc.items() if k != "_id"}}


def mask_phone(p: str) -> str:
    return (p[:3] + "*****" + p[-4:]) if p and len(p) >= 8 else (p or "")


# ---------- row normalisation ----------

def _clean(v) -> str:
    if v is None:
        return ""
    s = str(v).strip()
    return "" if s.lower() in ("nan", "none", "nat") else s


def normalize_phone(raw) -> str:
    s = _clean(raw)
    if re.fullmatch(r"\d+\.0", s):
        s = s[:-2]
    d = re.sub(r"\D", "", s)
    if len(d) == 12 and d.startswith("91"):
        d = d[2:]
    elif len(d) == 11 and d.startswith("0"):
        d = d[1:]
    if len(d) != 10 or d[0] not in "6789":
        raise ValueError("phone_number must be a valid 10-digit Indian mobile number")
    return "+91" + d


def parse_date(raw) -> str:
    s = _clean(raw)[:10]
    for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y", "%Y/%m/%d"):
        try:
            return datetime.strptime(s, fmt).date().isoformat()
        except ValueError:
            continue
    raise ValueError("interview_date must be YYYY-MM-DD or DD-MM-YYYY")


def parse_time(raw) -> str:
    s = _clean(raw).upper().replace(".", "")
    for fmt in ("%H:%M", "%H:%M:%S", "%I:%M %p", "%I:%M%p", "%I %p", "%I%p"):
        try:
            return datetime.strptime(s, fmt).strftime("%H:%M")
        except ValueError:
            continue
    raise ValueError("interview_time must be HH:MM (24h) or h:mm AM/PM")


def parse_yes(raw) -> bool:
    return _clean(raw).lower() in ("yes", "y", "true", "1")


def validate_row(row: dict, settings: dict) -> tuple:
    """Return (clean_fields, errors). Never authorises anything."""
    errors, out = [], {}
    out["candidate_name"] = _clean(row.get("candidate_name"))
    if not out["candidate_name"]:
        errors.append("candidate_name is required")
    try:
        out["phone_e164"] = normalize_phone(row.get("phone_number"))
    except ValueError as e:
        out["phone_e164"] = _clean(row.get("phone_number"))
        errors.append(str(e))
    out["job_role"] = _clean(row.get("job_role"))
    if not out["job_role"]:
        errors.append("job_role is required")
    try:
        out["interview_date"] = parse_date(row.get("interview_date"))
        if date.fromisoformat(out["interview_date"]) < datetime.now(IST).date():
            errors.append("interview_date is in the past")
    except ValueError as e:
        out["interview_date"] = _clean(row.get("interview_date"))
        errors.append(str(e))
    try:
        out["interview_time"] = parse_time(row.get("interview_time"))
    except ValueError as e:
        out["interview_time"] = _clean(row.get("interview_time"))
        errors.append(str(e))
    lang = _clean(row.get("language")).lower()
    out["language"] = LANGUAGES.get(lang, _clean(row.get("language")))
    if lang not in LANGUAGES:
        errors.append("language must be English or Tamil")
    out["company_name"] = _clean(row.get("company_name")) or settings.get("default_company_name", "")
    if not out["company_name"]:
        errors.append("company_name is required")
    out["office_address"] = _clean(row.get("office_address")) or settings.get("default_office_address", "")
    if not out["office_address"]:
        errors.append("office_address is required")
    out["sheet_approved_flag"] = parse_yes(row.get("approved_for_test_call"))
    return out, errors
