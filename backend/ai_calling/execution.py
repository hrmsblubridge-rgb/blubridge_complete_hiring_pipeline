"""Pure helpers for Phase 4A: spoken date/time, dynamic variables, execution + extraction normalisation."""
import json
import re
from datetime import date, datetime

REQUIRED_VARIABLES = ["candidate_name", "company_name", "job_role", "interview_date", "interview_time", "office_address"]
EXTRACTION_FIELDS = ["attendance_status", "wants_reschedule", "requested_virtual", "rejection_reason", "candidate_questions", "call_summary"]
EXTRACTION_CATEGORY = "Interview Call Results"
STATUS_RANK = {"queued": 0, "initiated": 1, "ringing": 2, "in-progress": 3, "call-disconnected": 4}
TERMINAL = {"completed", "no-answer", "busy", "failed", "canceled", "stopped", "error", "balance-low"}
ATTENDANCE_VALUES = {"CONFIRMED", "DECLINED", "RESCHEDULE_REQUESTED", "VIRTUAL_REQUESTED", "WRONG_NUMBER", "DO_NOT_CALL", "UNKNOWN"}
ATTENDANCE = {"confirmed": "CONFIRMED", "attending": "CONFIRMED", "declined": "DECLINED", "not_attending": "DECLINED",
              "reschedule": "RESCHEDULE_REQUESTED", "reschedule_requested": "RESCHEDULE_REQUESTED",
              "virtual": "VIRTUAL_REQUESTED", "virtual_requested": "VIRTUAL_REQUESTED"}
EMPTY_TEXT = {"", "unknown", "none", "null", "n/a", "na", "nil", "-"}


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
    return True if s in ("true", "yes", "y", "1") else False if s in ("false", "no", "n", "0") else None


def _text(v):
    s = str(v).strip() if v is not None else ""
    return None if s.lower() in EMPTY_TEXT else s


def _field_value(v):
    """Bolna disposition result {objective, subjective, status, ...} → plain value; flat values pass through."""
    if isinstance(v, dict) and ("objective" in v or "subjective" in v):
        if v.get("status") not in (None, "completed"):
            return None
        obj = v.get("objective")
        return obj if obj not in (None, "") else v.get("subjective")
    return v


def _flatten(data: dict) -> tuple:
    """Support extracted_data[category][field] (observed) and extracted_data[field] (flat)."""
    flat, meta, category = {}, {}, None
    for k, v in data.items():
        if isinstance(v, dict) and any(f in v for f in EXTRACTION_FIELDS):
            category = category or k
            for f in EXTRACTION_FIELDS:
                if f in v and f not in flat:
                    flat[f] = v[f]
    for f in EXTRACTION_FIELDS:
        if f in data and f not in flat:
            flat[f] = data[f]
    for f, v in flat.items():
        if isinstance(v, dict):
            meta[f] = {k: v.get(k) for k in ("confidence", "confidence_label", "status") if k in v}
    return flat, meta, category


def normalize_extraction(extracted) -> dict:
    """Empty/missing/unclear extraction ⇒ UNKNOWN / None. Never infers confirmation."""
    data = extracted
    if isinstance(data, str):
        try:
            data = json.loads(data)
        except ValueError:
            data = {}
    data = data if isinstance(data, dict) else {}
    flat, meta, category = _flatten(data)
    vals = {f: _field_value(flat[f]) for f in flat}
    raw_att = re.sub(r"[\s\-]+", "_", str(vals.get("attendance_status") or "").strip())
    att = raw_att.upper() if raw_att.upper() in ATTENDANCE_VALUES else ATTENDANCE.get(raw_att.lower().replace(" ", "_"), "UNKNOWN")
    qs = vals.get("candidate_questions")
    if isinstance(qs, str):
        qs = [q.strip(" -•\t") for q in re.split(r"[\n;]", qs) if _text(q.strip(" -•\t"))]
    qs = [q for q in qs if _text(q)] if isinstance(qs, list) else []
    return {
        "extraction_empty": not flat, "category": category, "fields_present": [f for f in EXTRACTION_FIELDS if f in flat],
        "fields_missing": [f for f in EXTRACTION_FIELDS if f not in flat],
        "attendance_status": att,
        "wants_reschedule": _bool(vals.get("wants_reschedule")),
        "requested_virtual": _bool(vals.get("requested_virtual")),
        "rejection_reason": _text(vals.get("rejection_reason")),
        "candidate_questions": qs,
        "call_summary": _text(vals.get("call_summary")),
        "field_meta": meta,
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


def extraction_from_dispositions(dispositions: list, errors: int = 0) -> dict:
    """Verify required fields from Bolna disposition definitions (GET /dispositions/{id})."""
    by_name = {}
    for d in dispositions:
        d = d.get("data") if isinstance(d.get("data"), dict) else d
        n = re.sub(r"\s+", "_", str(d.get("name") or "").strip().lower())
        if n:
            by_name[n] = {"category": d.get("category"),
                          "type": "objective" if d.get("is_objective") else "subjective" if d.get("is_subjective") else "none",
                          "options": [o.get("value") for o in (d.get("objective_options") or [])]}
    found = [f for f in EXTRACTION_FIELDS if f in by_name]
    return {"verified_from_api": True, "source": "dispositions", "dispositions_total": len(dispositions) + errors,
            "dispositions_unreadable": errors, "fields_found": found,
            "fields_missing": [f for f in EXTRACTION_FIELDS if f not in by_name],
            "outside_category": [f for f in found if by_name[f]["category"] != EXTRACTION_CATEGORY],
            "fields": {f: by_name[f] for f in found}}


def extraction_config_check(agent: dict) -> dict:
    """Fallback for agents without dispositions: look for field names in legacy extraction_details text."""
    blob = json.dumps(agent or {})
    found = [f for f in EXTRACTION_FIELDS if re.search(rf"\b{f}\b", blob)]
    has_extract_key = "extract" in blob.lower()
    return {"verified_from_api": False, "source": "agent_config", "extraction_section_detected": has_extract_key,
            "fields_found": found, "fields_missing": [f for f in EXTRACTION_FIELDS if f not in found],
            "variables_found": [v for v in REQUIRED_VARIABLES if re.search(rf"\b{v}\b", blob)]}
