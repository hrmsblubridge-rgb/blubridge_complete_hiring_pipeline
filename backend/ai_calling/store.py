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
    "language", "company_name", "office_address", "consent_for_test_call",
]
LANGUAGES = {"english": "English", "tamil": "Tamil"}

SETTINGS_DEFAULTS = {
    "mode": "off",
    "mode_version": 1,
    "emergency_stop": True,
    "ai_test_enabled": True,
    "ai_live_enabled": False,
    "live_dispatch_authorized": False,
    "live_daily_call_limit": 20,
    "live_max_concurrent_calls": 1,
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
    "default_company_name", "default_office_address", "live_daily_call_limit", "live_max_concurrent_calls",
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
    out = {**SETTINGS_DEFAULTS, **{k: v for k, v in doc.items() if k != "_id"}}
    out["mode"] = "testing" if out["ai_test_enabled"] else "off"  # legacy display field, derived from AI Test Mode
    return out


def mask_phone(p: str) -> str:
    return (p[:3] + "*****" + p[-4:]) if p and len(p) >= 8 else (p or "")



# ---------- row normalisation (Phase 3 rules) ----------
TIMEZONE = "Asia/Kolkata"
EXAMPLE_PREFIX = "EXAMPLE"
MANDATORY = ["candidate_name", "phone_number", "job_role", "interview_date",
             "interview_time", "language", "company_name", "office_address"]
ERROR_CATEGORIES = ["missing_field", "invalid_phone", "invalid_date", "invalid_time",
                    "invalid_language", "invalid_value", "example_row",
                    "duplicate_in_file", "duplicate_existing"]


def _clean(v) -> str:
    if v is None:
        return ""
    s = str(v).strip()
    return "" if s.lower() in ("nan", "none", "nat") else s


def normalize_phone(raw) -> str:
    s = _clean(raw)
    if re.fullmatch(r"\+?\d+\.0", s):
        s = s[:-2]
    d = re.sub(r"\D", "", s)
    if len(d) == 12 and d.startswith("91"):
        d = d[2:]
    elif len(d) == 11 and d.startswith("0"):
        d = d[1:]
    if len(d) != 10 or d[0] not in "6789":
        raise ValueError("phone_number must be an Indian mobile in +91XXXXXXXXXX format")
    return "+91" + d


def parse_date(raw) -> str:
    s = _clean(raw)[:10]
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", s):
        raise ValueError("interview_date must be YYYY-MM-DD")
    return date.fromisoformat(s).isoformat()


def parse_time(raw) -> str:
    s = _clean(raw)
    m = re.fullmatch(r"(\d{1,2})(?:\.0)?", s) or re.fullmatch(r"(\d{1,2}):([0-5]\d)(?::[0-5]\d)?", s)
    if m and 0 <= int(m.group(1)) <= 23:
        mins = int(m.group(2)) if m.re.groups > 1 and m.group(2) else 0
        return f"{int(m.group(1)):02d}:{mins:02d}"
    raise ValueError("interview_time must be HH in 24-hour IST (e.g. 10 or 14), optionally HH:MM")


def parse_yes_no(raw):
    s = _clean(raw).upper()
    return True if s in ("YES", "Y") else False if s in ("NO", "N") else None


def _err(field, category, message):
    return {"field": field, "category": category, "message": message}


def error_text(errors: list) -> str:
    return "; ".join(e["message"] for e in errors)


def validate_row(row: dict, require_flag: bool = False) -> tuple:
    """Return (clean_fields, errors[]). Never authorises anything."""
    errors, out = [], {}
    for f in MANDATORY:
        if not _clean(row.get(f)):
            errors.append(_err(f, "missing_field", f"{f} is required"))
    missing = {e["field"] for e in errors}
    out["candidate_name"] = _clean(row.get("candidate_name"))
    if out["candidate_name"].upper().startswith(EXAMPLE_PREFIX):
        errors.append(_err("candidate_name", "example_row", "Example row — replace with a real test recipient or delete it"))
    out["phone_e164"] = _clean(row.get("phone_number"))
    if "phone_number" not in missing:
        try:
            out["phone_e164"] = normalize_phone(row.get("phone_number"))
        except ValueError as e:
            errors.append(_err("phone_number", "invalid_phone", str(e)))
    out["job_role"] = _clean(row.get("job_role"))
    out["interview_date"] = _clean(row.get("interview_date"))
    if "interview_date" not in missing:
        try:
            out["interview_date"] = parse_date(row.get("interview_date"))
            if date.fromisoformat(out["interview_date"]) < datetime.now(IST).date():
                errors.append(_err("interview_date", "invalid_date", "interview_date is in the past"))
        except ValueError as e:
            errors.append(_err("interview_date", "invalid_date", str(e)))
    out["interview_time"] = _clean(row.get("interview_time"))
    if "interview_time" not in missing:
        try:
            out["interview_time"] = parse_time(row.get("interview_time"))
        except ValueError as e:
            errors.append(_err("interview_time", "invalid_time", str(e)))
    lang = _clean(row.get("language"))
    out["language"] = LANGUAGES.get(lang.lower(), lang)
    if lang and lang.lower() not in LANGUAGES:
        errors.append(_err("language", "invalid_language", "language must be English or Tamil"))
    out["company_name"] = _clean(row.get("company_name"))
    out["office_address"] = _clean(row.get("office_address"))
    out["interview_timezone"] = TIMEZONE
    raw = row.get("consent_for_test_call", row.get("approved_for_test_call"))
    flag = parse_yes_no(raw)
    if require_flag and flag is None:
        errors.append(_err("consent_for_test_call", "invalid_value", "consent_for_test_call must be YES or NO"))
    out["sheet_consent"] = bool(flag)
    return out, errors

