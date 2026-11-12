"""Phase 4A unit tests: pure helpers with sanitized fixtures (no network, no DB)."""
from ai_calling.bolna_client import build_call_request
from ai_calling.execution import (
    extraction_config_check, normalize_execution, normalize_extraction, rank, spoken_date, spoken_time, user_data_for,
)

CAND = {"candidate_name": "Test Person", "company_name": "BluBridge", "job_role": "Data Analyst",
        "interview_date": "2026-12-15", "interview_time": "10:30", "office_address": "Chennai Office"}

FIXTURE_DOCS = {  # sanitized from docs/post-call/execution-payload
    "id": "b7140255-0000-0000-0000-000000000000", "agent_id": "5bc97541-0000-0000-0000-000000000000",
    "status": "completed", "transcript": "assistant: Hello\nuser: yes I will come\n",
    "telephony_data": {"recording_url": "https://api.bolna.ai/recordings/call/x", "duration": 28,
                       "hangup_reason": "inactivity_timeout", "to_number": "+919000000001", "from_number": "+918000000000"},
    "extracted_data": {}, "conversation_duration": 28, "created_at": "2026-09-04T08:52:07+00:00",
    "error_message": None, "user_number": "+919000000001",
}


def test_spoken_formats():
    assert spoken_date("2026-12-15") == "Tuesday, 15 December 2026"
    assert spoken_time("10:30") == "10:30 AM IST"
    assert spoken_time("14:00") == "2 PM IST"


def test_user_data_has_exact_variables():
    ud = user_data_for(CAND)
    assert set(ud) == {"candidate_name", "company_name", "job_role", "interview_date", "interview_time", "office_address", "call_purpose"}
    assert ud["call_purpose"] == "interview_confirmation"
    assert user_data_for(CAND, "missed_interview_followup")["call_purpose"] == "missed_interview_followup"


def test_build_request_documented_fields_only():
    body = build_call_request(agent_id="a", recipient="+919000000001", from_number="+918000000000", user_data={})
    assert set(body) == {"agent_id", "recipient_phone_number", "from_phone_number", "user_data"}


def test_empty_extraction_is_unknown():
    n = normalize_execution(FIXTURE_DOCS)
    assert n["terminal"] and n["duration_seconds"] == 28 and n["recording_url"]
    assert n["response"]["extraction_empty"] is True
    assert n["response"]["attendance_status"] == "UNKNOWN"


def test_extraction_values():
    r = normalize_extraction({"attendance_status": "Confirmed", "wants_reschedule": "no", "requested_virtual": False,
                              "rejection_reason": "", "candidate_questions": "Is parking available?\nDress code?",
                              "call_summary": "Will attend"})
    assert r["attendance_status"] == "CONFIRMED" and r["wants_reschedule"] is False
    assert r["candidate_questions"] == ["Is parking available?", "Dress code?"] and not r["fields_missing"]
    assert normalize_extraction({"attendance_status": "maybe"})["attendance_status"] == "UNKNOWN"
    assert normalize_extraction('{"attendance_status":"declined"}')["attendance_status"] == "DECLINED"


def test_status_order():
    assert rank("queued") < rank("ringing") < rank("call-disconnected") < rank("completed")
    assert rank("no-answer") == rank("completed")


def test_extraction_config_check():
    chk = extraction_config_check({"agent_config": {"agent_prompts": {"task_1": {"system_prompt": "Hi {candidate_name}"}}}})
    assert chk["fields_missing"] and "candidate_name" in chk["variables_found"]


# ---- Nested "Interview Call Results" (sanitized from observed Bolna output) ----
from ai_calling.execution import extraction_from_dispositions  # noqa: E402


def _r(obj=None, subj=None, status="completed"):
    return {"subjective": subj, "objective": obj, "confidence": 0.9, "confidence_label": "High",
            "reasoning_subjective": None, "reasoning_objective": "x", "validation": None, "status": status, "status_reason": None}


NESTED = {"Interview Call Results": {
    "attendance_status": _r(obj="CONFIRMED"), "wants_reschedule": _r(obj="No"), "requested_virtual": _r(obj="Unknown"),
    "rejection_reason": _r(subj="None"), "candidate_questions": _r(subj="Is parking available?\nWhat should I bring?"),
    "call_summary": _r(subj="Candidate confirmed attendance."),
}, "General": {"Call Completion": _r(obj="complete")}}


def test_nested_category_parsed():
    r = normalize_extraction(NESTED)
    assert r["category"] == "Interview Call Results" and not r["fields_missing"]
    assert r["attendance_status"] == "CONFIRMED" and r["wants_reschedule"] is False and r["requested_virtual"] is None
    assert r["rejection_reason"] is None and r["call_summary"] == "Candidate confirmed attendance."
    assert r["candidate_questions"] == ["Is parking available?", "What should I bring?"]
    assert r["field_meta"]["attendance_status"]["confidence_label"] == "High"


def test_nested_unknown_and_incomplete_stay_unknown():
    d = {"Interview Call Results": {"attendance_status": _r(obj="UNKNOWN"), "wants_reschedule": _r(obj="Yes")}}
    r = normalize_extraction(d)
    assert r["attendance_status"] == "UNKNOWN" and r["wants_reschedule"] is True
    d2 = {"Interview Call Results": {"attendance_status": _r(obj="CONFIRMED", status="failed")}}
    assert normalize_extraction(d2)["attendance_status"] == "UNKNOWN"
    assert normalize_extraction({"Interview Call Results": {"attendance_status": _r(obj="WRONG_NUMBER")}})["attendance_status"] == "WRONG_NUMBER"
    assert normalize_extraction({})["attendance_status"] == "UNKNOWN"


def _disp(name, cat, obj=True, opts=("Yes", "No", "Unknown")):
    return {"name": name, "category": cat, "is_objective": obj, "is_subjective": not obj,
            "objective_options": [{"value": o} for o in opts] if obj else []}


def test_dispositions_validator():
    defs = [_disp("attendance_status", "Interview Call Results", opts=("CONFIRMED", "DECLINED", "UNKNOWN")),
            _disp("wants_reschedule", "Interview Call Results"), _disp("requested_virtual", "Interview Call Results"),
            _disp("rejection_reason", "Interview Call Results", obj=False), _disp("candidate_questions", "Interview Call Results", obj=False),
            _disp("call_summary", "Interview Call Results", obj=False), _disp("Call Success", "General")]
    r = extraction_from_dispositions(defs)
    assert r["verified_from_api"] and not r["fields_missing"] and not r["outside_category"]
    assert r["fields"]["attendance_status"]["type"] == "objective" and r["fields"]["call_summary"]["type"] == "subjective"
    r2 = extraction_from_dispositions(defs[:2], errors=1)
    assert "call_summary" in r2["fields_missing"] and r2["dispositions_unreadable"] == 1
