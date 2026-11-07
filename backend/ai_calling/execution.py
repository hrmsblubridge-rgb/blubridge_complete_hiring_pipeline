"""Pure helpers for Phase 4A: spoken date/time, dynamic variables, execution + extraction normalisation."""
import json
import re
from datetime import date, datetime

REQUIRED_VARIABLES = ["candidate_name", "company_name", "job_role", "interview_date", "interview_time", "office_address"]
EXTRACTION_FIELDS = ["attendance_status", "wants_reschedule", "requested_virtual", "rejection_reason", "candidate_questions", "call_summary"]
STATUS_RANK = {"queued": 0, "initiated": 1, "ringing": 2, "in-progress": 3, "call-disconnected": 4}
TERMINAL = {"completed", "no-answer", "busy", "failed", "canceled", "stopped", "error", "balance-low"}
ATTENDANCE = {"confirmed": "CONFIRMED", "yes": "CONFIRMED", "attending": "CONFIRMED", "declined": "DECLINED",
              "no": "DECLINED", "not_attending": "DECLINED", "reschedule": "RESCHEDULE_REQUESTED",
              "virtual": "VIRTUAL_REQUESTED"}


def rank(status: str) -> int:
    return 5 if status in TERMINAL else STATUS_RANK.get(status, -1)


def spoken_date(iso: str) -> str:
    d = date.fromisoformat(iso)
    return f"{d.strftime('%A')}, {d.day} {d.strftime('%B %Y')}"


def spoken_time(hhmm: str) -> str:
    t = datetime.strptime(hhmm, "%H:%M")
    return t.strftime("%I:%M %p").lstrip("0").replace(":00 ", " ") + " IST"


def user_data_for(cand: dict) -> dict:
    """Values come only from the saved test candidate record."""
    return {
        "candidate_name": cand["candidate_name"], "company_name": cand["company_name"], "job_role": cand["job_role"],
        "interview_date": spoken_date(cand["interview_date"]), "interview_time": spoken_time(cand["interview_time"]),
        "office_address": cand["office_address"],
    }


def _bool(v):
    if isinstance(v, bool):
        return v
    s = str(v or "").strip().lower()
    return True if s in ("true", "yes", "1") else False if s in ("false", "no", "0") else None


def normalize_extraction(extracted) -> dict:
    """Empty/missing extraction ⇒ UNKNOWN. Never infers confirmation."""
    data = extracted
    if isinstance(data, str):
        try:
            data = json.loads(data)
        except ValueError:
            data = {}
    data = data if isinstance(data, dict) else {}
    present = [f for f in EXTRACTION_FIELDS if f in data]
    raw_att = str(data.get("attendance_status") or "").strip().lower().replace(" ", "_")
    qs = data.get("candidate_questions")
    if isinstance(qs, str):
        qs = [q.strip() for q in qs.split("\n") if q.strip()]
    return {
        "extraction_empty": not data, "fields_present": present,
        "fields_missing": [f for f in EXTRACTION_FIELDS if f not in data],
        "attendance_status": ATTENDANCE.get(raw_att, "UNKNOWN"),
        "wants_reschedule": _bool(data.get("wants_reschedule")),
        "requested_virtual": _bool(data.get("requested_virtual")),
        "rejection_reason": (str(data["rejection_reason"]).strip() or None) if data.get("rejection_reason") else None,
        "candidate_questions": qs if isinstance(qs, list) else [],
        "call_summary": (str(data["call_summary"]).strip() or None) if data.get("call_summary") else None,
    }


def normalize_execution(ex: dict) -> dict:
    tel = ex.get("telephony_data") or {}
    return {
        "execution_id": ex.get("id") or ex.get("execution_id"), "agent_id": ex.get("agent_id"),
        "status": ex.get("status"), "terminal": ex.get("status") in TERMINAL,
        "created_at": ex.get("created_at"), "duration_seconds": tel.get("duration") or ex.get("conversation_duration"),
        "hangup_reason": tel.get("hangup_reason"), "to_number": tel.get("to_number") or ex.get("user_number"),
        "recording_url": tel.get("recording_url"), "transcript": ex.get("transcript"),
        "extracted_data_raw": ex.get("extracted_data"), "error_message": ex.get("error_message"),
        "response": normalize_extraction(ex.get("extracted_data")),
    }


def extraction_config_check(agent: dict) -> dict:
    """Best-effort: look for the required field names (whole words) anywhere in the agent config text."""
    blob = json.dumps(agent or {})
    found = [f for f in EXTRACTION_FIELDS if re.search(rf"\b{f}\b", blob)]
    has_extract_key = "extract" in blob.lower()
    return {"verified_from_api": False, "extraction_section_detected": has_extract_key,
            "fields_found": found, "fields_missing": [f for f in EXTRACTION_FIELDS if f not in found],
            "variables_found": [v for v in REQUIRED_VARIABLES if re.search(rf"\b{v}\b", blob)]}
