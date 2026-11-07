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
    assert set(ud) == {"candidate_name", "company_name", "job_role", "interview_date", "interview_time", "office_address"}


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
