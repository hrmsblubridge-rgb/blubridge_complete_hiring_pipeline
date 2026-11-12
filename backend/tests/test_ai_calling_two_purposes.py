"""Two calling purposes (pre-interview confirmation + OTP-based missed-interview follow-up), queue capacity,
single-recipient calling. SCRATCH DB + mock provider only; Bolna place_call is patched to fail if touched."""
from datetime import datetime, timedelta

import pytest

from ai_calling import live_prep, purposes
from ai_calling.execution import normalize_extraction, user_data_for
from ai_calling.store import IST, SETTINGS_DEFAULTS
from tests.test_ai_calling_phase7ca import NOW, reg, run
from ai_calling import consent

S = {**SETTINGS_DEFAULTS, "mode_version": 1}
TODAY = NOW.date()


def at(days, hh, mm=0):
    return datetime.combine(TODAY + timedelta(days=days), datetime.min.time(), IST).replace(hour=hh, minute=mm)


def booking(iv: datetime, **kw):
    b = reg(schedule_date=iv.date().isoformat(), schedule_time=iv.strftime("%H:%M:00"), **kw)
    b.setdefault("ai_call_consent", {"status": "granted", "text_version": "2026-06-v4"})
    return b


@pytest.mark.parametrize("days", range(1, 8))
def test_confirmation_offset_days(days):
    iv = at(9, 12)
    p = purposes.plan_for(purposes.CONFIRM, booking(iv), NOW, {**S, "confirm_offset_days": days})
    assert p["status"] == "SCHEDULED" and datetime.fromisoformat(p["planned_at"]) == iv - timedelta(days=days)


def test_confirmation_short_notice_and_window():
    ok = purposes.plan_for(purposes.CONFIRM, booking(NOW + timedelta(hours=3)), NOW, S)
    assert ok["status"] == "SCHEDULED" and ok["short_notice"]
    assert purposes.plan_for(purposes.CONFIRM, booking(NOW + timedelta(minutes=90)), NOW, S)["status"] == "NEEDS_REVIEW"
    early = purposes.plan_for(purposes.CONFIRM, booking(at(3, 8, 30)), NOW, S)
    assert datetime.fromisoformat(early["planned_at"]) == at(2, 10)
    late = purposes.plan_for(purposes.CONFIRM, booking(at(3, 19, 30)), NOW, S)  # 19:30 the day before → next day 10:00
    assert datetime.fromisoformat(late["planned_at"]) == at(3, 10)


@pytest.mark.parametrize("minutes,expected", [(60, at(1, 13)), (240, at(1, 16)), (10080, at(8, 12))])
def test_missed_offsets(minutes, expected):
    p = purposes.plan_missed(booking(at(1, 12)), NOW, {**S, "missed_offset_minutes": minutes})
    assert p["status"] == "SCHEDULED" and datetime.fromisoformat(p["planned_at"]) == expected


def test_missed_window_until_1930_and_next_day():
    assert datetime.fromisoformat(purposes.plan_missed(booking(at(1, 18, 15)), NOW, S)["planned_at"]) == at(1, 19, 15)
    assert datetime.fromisoformat(purposes.plan_missed(booking(at(1, 18, 45)), NOW, S)["planned_at"]) == at(2, 10)
    assert datetime.fromisoformat(purposes.plan_missed(booking(at(1, 8)), NOW, S)["planned_at"]) == at(1, 10)


@pytest.mark.parametrize("otp,ok,reason", [("", True, None), (False, True, None), (True, False, "ATTENDED_OTP_VERIFIED"),
                                           ("1", False, "ATTENDED_OTP_VERIFIED"), (None, False, "ATTENDANCE_UNKNOWN"),
                                           (0, False, "ATTENDANCE_UNKNOWN"), ("abc", False, "ATTENDANCE_UNKNOWN")])
def test_otp_states(otp, ok, reason):
    r = purposes.missed_eligibility(booking(at(1, 12), otp_verified=otp))
    assert (not r) is ok and (reason is None or reason in r)


def test_otp_missing_and_no_missed_marked_dependency():
    b = booking(at(1, 12))
    b.pop("otp_verified")
    assert "OTP_FIELD_MISSING_DATA_ISSUE" in purposes.missed_eligibility(b)
    assert purposes.missed_eligibility(booking(at(1, 12), status="Missed", missed_marked=True)) == []
    assert purposes.missed_eligibility(booking(at(1, 12), missed_marked=False)) == []
    for bad in ("Rejected", "Cancelled", "Attended"):
        assert purposes.missed_eligibility(booking(at(1, 12), status=bad))


def test_consent_version_scope():
    v3 = booking(at(1, 12), ai_call_consent={"status": "granted", "text_version": "2026-06-v3"})
    assert "NO_FOLLOWUP_CONSENT" in purposes.missed_eligibility(v3)
    assert purposes.plan_for(purposes.CONFIRM, booking(at(4, 12), ai_call_consent=v3["ai_call_consent"]), NOW, S)["status"] == "SCHEDULED"


def test_eleven_fields_nested_and_incomplete_ignored():
    ex = {"Interview Call Results": {
        "attendance_status": {"objective": "UNKNOWN", "status": "completed", "confidence": 0.9},
        "wants_reschedule": {"objective": "yes", "status": "completed"}, "requested_virtual": "no",
        "rejection_reason": None, "candidate_questions": "Where is parking?; Dress code?", "call_summary": "Summary",
        "missed_interview_outcome": {"objective": "claims attended", "status": "completed"},
        "missed_interview_reason": {"subjective": "Was at reception", "status": "completed"},
        "expected_arrival_time": {"objective": "11:30", "status": "in_progress"},
        "attendance_dispute": "YES", "preferred_reschedule_datetime": "Friday 3 PM"}}
    n = normalize_extraction(ex)
    assert n["category"] == "Interview Call Results" and len(n["missed_fields_present"]) == 5
    assert n["missed_interview_outcome"] == "CLAIMS_ATTENDED" and n["attendance_dispute"] is True
    assert n["expected_arrival_time"] is None  # incomplete extraction ignored
    assert n["wants_reschedule"] is True and n["candidate_questions"] == ["Where is parking?", "Dress code?"]
    assert purposes.outcome_of(purposes.MISSED, {"attendance_status": "DECLINED", "missed_interview_outcome": "DO_NOT_CALL"}) == "DO_NOT_CALL"
    assert purposes.outcome_of(purposes.CONFIRM, {"attendance_status": "DO_NOT_CALL"}) == "DO_NOT_CALL"
    assert user_data_for({"candidate_name": "a", "company_name": "b", "job_role": "c", "interview_date": "2099-01-01",
                          "interview_time": "10:00", "office_address": "d"}, purposes.MISSED)["call_purpose"] == purposes.MISSED


async def _seed(d, iv, **kw):
    rid = str((await d.bb_registrations.insert_one(booking(iv, **kw))).inserted_id)
    await consent.record_consent(rid, "granted", "test", "t")
    return rid


def test_missed_flow_retry_then_otp_verified_cancels(monkeypatch):
    async def case(tc, d):
        rid = await _seed(d, at(0, 10))
        await live_prep.plan_live("t", now=NOW)
        j = await d.ai_live_mock_jobs.find_one({"purpose": purposes.MISSED})
        assert j and await d.ai_live_mock_jobs.count_documents({"purpose": purposes.CONFIRM, "status": "planned"}) == 0
        due = datetime.fromisoformat(j["planned_at"])
        r = await live_prep.mock_tick("w", now=due, outcome="no_answer")
        assert r["result"] == "no_answer" and r["retry_job"] and r["user_data"]["call_purpose"] == purposes.MISSED
        retry = await d.ai_live_mock_jobs.find_one({"attempt": 2})
        assert datetime.fromisoformat(retry["planned_at"]) == due + timedelta(minutes=30)
        await d.bb_registrations.update_one({}, {"$set": {"otp_verified": True}})  # employee verifies OTP
        r2 = await live_prep.mock_tick("w", now=due + timedelta(minutes=31))
        assert r2["result"] == "cancelled_otp_verified"
        assert (await d.bb_registrations.find_one({}))["otp_verified"] is True  # never written by AI calling
        assert rid
    run(monkeypatch, case, settings={"missed_enabled": True})


def test_otp_verified_while_pending_and_right_before_dispatch(monkeypatch):
    async def case(tc, d):
        await _seed(d, at(0, 10))
        await live_prep.plan_live("t", now=NOW)
        await d.bb_registrations.update_one({}, {"$set": {"otp_verified": "1"}})
        await live_prep.plan_live("t", now=NOW)
        assert (await d.ai_live_mock_jobs.find_one({"purpose": purposes.MISSED}))["status"] == "cancelled"
        await d.bb_registrations.update_one({}, {"$set": {"otp_verified": ""}})
        await d.ai_live_mock_jobs.update_one({}, {"$set": {"status": "planned"}})
        real_gate, placed = live_prep.gate_job, []

        async def gate_then_verify(job, now, overall=None, b=None):
            g = await real_gate(job, now, overall, b)
            await d.bb_registrations.update_one({}, {"$set": {"otp_verified": True}})
            return g

        class Spy(live_prep.MockProvider):
            async def place(self, *a):
                placed.append(a)
                return await super().place(*a)
        monkeypatch.setattr(live_prep, "gate_job", gate_then_verify)
        j = await d.ai_live_mock_jobs.find_one({})
        r = await live_prep.mock_tick("w", now=datetime.fromisoformat(j["planned_at"]), provider=Spy())
        assert r["result"] == "cancelled_otp_verified" and placed == []
    run(monkeypatch, case, settings={"missed_enabled": True})


def test_reschedule_request_suppresses_missed_then_new_booking(monkeypatch):
    async def case(tc, d):
        rid = await _seed(d, at(2, 12))
        await live_prep.plan_live("t", now=NOW)
        assert await d.ai_live_mock_jobs.count_documents({"status": "planned"}) == 2
        r = await live_prep.mock_tick("w", now=at(1, 12), outcome="RESCHEDULE_REQUESTED")
        assert r["outcome"] == "RESCHEDULE_REQUESTED"
        alert = await d.ai_call_alerts.find_one({"type": "RESCHEDULE_REQUEST_PENDING"})
        assert alert and alert["detail"]["preferred_reschedule_datetime"]
        assert (await d.ai_live_mock_jobs.find_one({"purpose": purposes.MISSED}))["status"] == "cancelled"
        assert (await d.bb_registrations.find_one({}))["schedule_date"] == at(2, 12).date().isoformat()  # slot unchanged
        await d.bb_registrations.update_one({}, {"$set": {"schedule_date": at(4, 12).date().isoformat()}, "$inc": {"reschedule_count": 1}})
        await live_prep.plan_live("t", now=at(1, 12, 5))
        assert await d.ai_live_mock_jobs.count_documents({"status": "planned", "purpose": purposes.MISSED}) == 1
        assert await d.bb_registrations.count_documents({}) == 1 and rid
    run(monkeypatch, case, settings={"missed_enabled": True})


@pytest.mark.parametrize("outcome,alert", [("RUNNING_LATE", "RUNNING_LATE"), ("CLAIMS_ATTENDED", "CLAIMS_ATTENDED")])
def test_missed_alerts(monkeypatch, outcome, alert):
    async def case(tc, d):
        await _seed(d, at(0, 10))
        await live_prep.plan_live("t", now=NOW)
        j = await d.ai_live_mock_jobs.find_one({"purpose": purposes.MISSED})
        r = await live_prep.mock_tick("w", now=datetime.fromisoformat(j["planned_at"]), outcome=outcome)
        a = await d.ai_call_alerts.find_one({"type": alert})
        assert r["outcome"] == outcome and a["needs_hr_review"] and r["retry_job"] is None
        assert (await d.bb_registrations.find_one({}))["otp_verified"] is False
        if outcome == "RUNNING_LATE":
            assert a["detail"]["expected_arrival_time"]
        await live_prep.plan_live("t", now=datetime.fromisoformat(j["planned_at"]) + timedelta(minutes=5))
        assert await d.ai_live_mock_jobs.count_documents({"status": "planned"}) == 0  # no further automatic follow-up
    run(monkeypatch, case, settings={"missed_enabled": True})


def test_do_not_call_blocks_both_purposes(monkeypatch):
    async def case(tc, d):
        rid = await _seed(d, at(0, 10))
        await live_prep.plan_live("t", now=NOW)
        j = await d.ai_live_mock_jobs.find_one({"purpose": purposes.MISSED})
        await live_prep.mock_tick("w", now=datetime.fromisoformat(j["planned_at"]), outcome="DO_NOT_CALL")
        c = await d.ai_candidate_consents.find_one({"registration_id": rid})
        assert c["do_not_call"] and "AI_CALL_OPT_OUT" in c["dnc_sources"]
        b = {**booking(at(4, 12)), "do_not_call": True}
        assert purposes.plan_for(purposes.CONFIRM, b, NOW, S)["status"] == "SKIPPED"
        assert "DO_NOT_CALL" in purposes.missed_eligibility(b)
    run(monkeypatch, case, settings={"missed_enabled": True})


def test_queue_500_capacity_and_priority(monkeypatch):
    async def case(tc, d):
        docs = [booking(at(2, 12, i % 25), phone=f"+9198{i:08d}", schedule_token=f"q{i:023d}") for i in range(500)]
        ids = (await d.bb_registrations.insert_many(docs)).inserted_ids
        await d.ai_candidate_consents.insert_many([{"registration_id": str(x), "consent_status": "granted", "consent_text_version": "2026-06-v4",
                                                   "do_not_call": False, "dnc_sources": []} for x in ids])
        res = await live_prep.plan_live("t", now=NOW)
        assert res["counts"]["planned"] == 500 and await d.ai_live_mock_jobs.count_documents({}) == 500
        await d.ai_call_settings.update_one({"_id": "global"}, {"$set": {"live_daily_call_limit": 40, "live_pilot_daily_cap": 40,
                                                                          "live_queue_capacity": 1000}})
        out = await live_prep.mock_run("w", now=at(1, 12, 25), capacity=1000)
        assert out["results"].get("completed") == 40 and out["results"].get("daily_limit") == 1
        assert await d.ai_live_mock_jobs.count_documents({}) == 500  # nothing deleted or truncated
        assert await d.ai_live_mock_jobs.count_documents({"status": "planned"}) == 460
        done = max(j["planned_at"] for j in await d.ai_live_mock_jobs.find({"status": "completed"}).to_list(100))
        waiting = min(j["planned_at"] for j in await d.ai_live_mock_jobs.find({"status": "planned"}).to_list(500))
        assert done <= waiting  # earliest due first
    run(monkeypatch, case)


def test_single_live_job_and_duplicate_request(monkeypatch):
    async def case(tc, d):
        await _seed(d, at(2, 12))
        await live_prep.plan_live("t", now=NOW)
        j = await d.ai_live_mock_jobs.find_one({})
        assert (await tc.post(f"/live-prep/mock-jobs/{j['_id']}/process", json={})).status_code == 409  # not due yet
        r = await live_prep.mock_tick("w", now=at(1, 12), job_id=str(j["_id"]))
        assert r["result"] == "completed" and r["provider_request_sent"] is False
        assert r["gate"]["allowed_live"] is False and "authorized" in r["gate"]["mock_bypassed"]
        assert (await live_prep.mock_tick("w", now=at(1, 12), job_id=str(j["_id"])))["claimed"] is None
        assert await d.ai_calls.count_documents({}) == 0
    run(monkeypatch, case)


def test_live_candidate_without_consent_not_queued(monkeypatch):
    async def case(tc, d):
        await d.bb_registrations.insert_one(booking(at(2, 12)))
        res = await live_prep.plan_live("t", now=NOW)
        assert res["counts"]["planned"] == 0 and await d.ai_live_mock_jobs.count_documents({}) == 0
    run(monkeypatch, case, settings={"missed_enabled": True})


def test_scheduling_settings_validate_audit_and_recalculate(monkeypatch):
    async def case(tc, d):
        await _seed(d, at(5, 12))
        await live_prep.plan_live("t", now=NOW)
        for bad in ({"confirm_offset_days": 8}, {"confirm_offset_days": 0}, {"missed_offset_minutes": 59},
                    {"missed_offset_minutes": 10081}, {"live_max_concurrent_calls": 0}, {"nope": 1}):
            assert (await tc.put("/scheduling", json=bad)).status_code == 400
        r = await tc.put("/scheduling", json={"confirm_offset_days": 3, "missed_enabled": False})
        assert r.status_code == 200 and r.json()["interview_confirmation"]["offset_days"] == 3
        j = await d.ai_live_mock_jobs.find_one({"purpose": purposes.CONFIRM})
        assert j["planned_at"].startswith(at(2, 12).date().isoformat())
        assert await d.ai_call_audit.count_documents({"action": "scheduling_updated"}) == 1
    run(monkeypatch, case)


def test_test_call_status_reasons_single_recipient(monkeypatch):
    async def case(tc, d):
        st = (await tc.get("/test-calls/status")).json()
        assert st["single_call_enabled"] is False and st["min_recipients"] == 1
        assert "Emergency Stop is ON" in st["block_reasons"] and any("AI_CALLING_ENABLED" in x for x in st["block_reasons"])
        from ai_calling import gate
        oid = (await d.ai_test_candidates.insert_one({"mode": "testing", "candidate_name": "Colleague", "phone_e164": "+919000000555",
                                                     "consent_status": "granted", "consent_phone": "+919000000555",
                                                     "opted_out": False, "interview_date": "2099-01-01"})).inserted_id
        v = await gate.evaluate(mode="testing", test_candidate_id=str(oid), batch_id="", phone_e164="+919000000555",
                                mode_version=1, single_call=True)
        keys = {c["key"]: c["ok"] for c in v["checks"]}
        assert "bolna_approved" not in keys and keys["consent"] and keys["no_emergency_stop"] is False and not v["allowed"]
        await d.ai_test_candidates.update_one({"_id": oid}, {"$set": {"consent_status": "not_given"}})
        v2 = await gate.evaluate(mode="testing", test_candidate_id=str(oid), batch_id="", phone_e164="+919000000555",
                                 mode_version=1, single_call=True)
        assert {c["key"]: c["ok"] for c in v2["checks"]}["consent"] is False
        r = await tc.post(f"/test-candidates/{oid}/call-now", json={"idempotency_key": "idem-key-single-000001", "confirm_name": "Colleague"},
                          headers={"X-CSRF-Intent": "ai-calling"})
        assert r.status_code == 409 and await d.ai_calls.count_documents({}) == 0  # Emergency Stop blocks the real call
    run(monkeypatch, case)
