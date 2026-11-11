# AI Calling Phase 2 (Testing Mode foundation) regression tests
import io
import os
from datetime import datetime, timedelta

import pytest
import requests
from openpyxl import Workbook, load_workbook
from pymongo import MongoClient
from bson import ObjectId


def _base():
    v = os.environ.get("REACT_APP_BACKEND_URL")
    if not v:
        for line in open("/app/frontend/.env"):
            if line.startswith("REACT_APP_BACKEND_URL="):
                v = line.split("=", 1)[1].strip().strip('"')
    return v.rstrip("/")


BASE_URL = _base()
API = f"{BASE_URL}/api/ai-calling"
COLS = ["candidate_name", "phone_number", "job_role", "interview_date", "interview_time",
        "language", "company_name", "office_address", "approved_for_test_call"]
FUT = (datetime.now() + timedelta(days=40)).strftime("%Y-%m-%d")
PAST = (datetime.now() - timedelta(days=5)).strftime("%Y-%m-%d")


def _mongo():
    env = dict(l.strip().split("=", 1) for l in open("/app/backend/.env") if "=" in l and not l.startswith("#"))
    return MongoClient(env["MONGO_URL"].strip('"'))[env["DB_NAME"].strip('"')]


@pytest.fixture(scope="module")
def s():
    sess = requests.Session()
    r = sess.post(f"{BASE_URL}/api/login", json={"username": "Admin User", "password": "QAZwsx##123"})
    if r.status_code != 200:
        pytest.skip("login failed")
    return sess


@pytest.fixture(scope="module")
def created():
    return {"cands": [], "batches": []}


@pytest.fixture(scope="module", autouse=True)
def cleanup(s, created):
    orig = s.get(f"{API}/settings").json()
    yield
    for cid in created["cands"]:
        s.delete(f"{API}/test-candidates/{cid}")
    if created["batches"]:
        _mongo().ai_test_batches.delete_many({"_id": {"$in": [ObjectId(b) for b in created["batches"]]}})
    # restore mode / estop / settings
    if orig["mode"] != s.get(f"{API}/settings").json()["mode"]:
        s.post(f"{API}/mode", json={"mode": orig["mode"]})
    s.post(f"{API}/emergency-stop", json={"active": orig["emergency_stop"]})
    s.put(f"{API}/settings", json={k: orig[k] for k in ("daily_call_limit", "max_concurrent_calls", "call_window_start", "call_window_end", "default_company_name", "default_office_address")})


def _cand(name, phone, **kw):
    d = {"candidate_name": name, "phone_number": phone, "job_role": "Data Analyst", "interview_date": FUT,
         "interview_time": "10:30", "language": "English", "company_name": "BluBridge", "office_address": "TEST Office, Chennai"}
    d.update(kw)
    return d


def _xlsx(rows, cols=COLS):
    wb = Workbook(); ws = wb.active; ws.append(cols)
    for r in rows:
        ws.append(r)
    b = io.BytesIO(); wb.save(b); return b.getvalue()


# ---- auth ----
class TestAuth:
    @pytest.mark.parametrize("method,path", [
        ("get", "/summary"), ("get", "/settings"), ("put", "/settings"), ("post", "/mode"), ("post", "/emergency-stop"),
        ("get", "/template"), ("get", "/test-candidates"), ("post", "/test-candidates"), ("post", "/test-candidates/upload"),
        ("put", "/test-candidates/x"), ("delete", "/test-candidates/x"), ("post", "/test-candidates/x/opt-out"), ("get", "/test-batches"),
        ("post", "/test-batches"), ("post", "/test-batches/x/preflight"), ("post", "/test-batches/x/start"),
        ("post", "/test-batches/x/stop"), ("get", "/calls"), ("get", "/calls/x"), ("get", "/live/status")])
    def test_401(self, method, path):
        # send a schema-valid body so we test auth, not body validation
        bodies = {"/mode": {"mode": "off"}, "/emergency-stop": {"active": False}, "/test-batches": {"candidate_ids": []},
                  "/test-candidates/x/approve": {"consent_confirmed": True, "phone_last4": "0000"},
                  "/test-candidates/x/opt-out": {"opted_out": True}}
        kw = {}
        if method in ("post", "put"):
            kw["json"] = bodies.get(path, {})
        if path.endswith("/upload"):
            kw = {"files": {"file": ("t.csv", b"a,b\n")}}
        r = getattr(requests, method)(f"{API}{path}", **kw)
        assert r.status_code == 401, f"{method} {path} -> {r.status_code}"


# ---- template ----
@pytest.mark.skip(reason="Approval workflow removed in Phase 7A; consent flow covered by test_ai_calling_phase7a.py")
class TestTemplate:
    def test_xlsx(self, s):
        r = s.get(f"{API}/template?format=xlsx")
        assert r.status_code == 200
        wb = load_workbook(io.BytesIO(r.content))
        assert wb.sheetnames == ["Test Candidates", "Instructions"]
        hdr = [c.value for c in wb["Test Candidates"][1]]
        assert hdr == COLS
        assert wb["Test Candidates"].max_row >= 3

    def test_csv(self, s):
        r = s.get(f"{API}/template?format=csv")
        assert r.status_code == 200
        assert r.text.splitlines()[0].strip() == ",".join(COLS)


# ---- upload ----
@pytest.mark.skip(reason="Phase 2 upload API superseded by Phase 3; covered in test_ai_calling_phase3.py")
class TestUpload:
    def test_wrong_columns_400(self, s):
        f = _xlsx([["a", "9000000051"]], cols=["name", "phone"])
        r = s.post(f"{API}/test-candidates/upload?commit=false", files={"file": ("t.xlsx", f)})
        assert r.status_code == 400 and "Column mismatch" in r.json()["detail"]

    def test_bad_ext_400(self, s):
        r = s.post(f"{API}/test-candidates/upload", files={"file": ("t.txt", b"x")})
        assert r.status_code == 400

    def test_preview_validation_and_commit(self, s, created):
        rows = [
            ["TEST_Up Good", "9000000051", "Data Analyst", FUT, "10:30", "English", "BluBridge", "TEST Office", "yes"],
            ["TEST_Bad Phone", "12345", "Data Analyst", FUT, "10:30", "English", "BluBridge", "TEST Office", "yes"],
            ["TEST_Past", "9000000052", "Data Analyst", PAST, "10:30", "English", "BluBridge", "TEST Office", "no"],
            ["TEST_BadTime", "9000000053", "Data Analyst", FUT, "25:99", "English", "BluBridge", "TEST Office", "no"],
            ["TEST_BadLang", "9000000054", "Data Analyst", FUT, "10:30", "Hindi", "BluBridge", "TEST Office", "no"],
            ["TEST_NoAddr", "9000000055", "Data Analyst", FUT, "10:30", "Tamil", "BluBridge", None, "no"],
            ["TEST_Dup", "9000000051", "Data Analyst", FUT, "2:00 PM", "Tamil", "BluBridge", "TEST Office", "yes"],
            ["TEST_Existing", "9000000011", "Data Analyst", FUT, "10:30", "English", "BluBridge", "TEST Office", "yes"],
        ]
        f = _xlsx(rows)
        r = s.post(f"{API}/test-candidates/upload?commit=false", files={"file": ("t.xlsx", f)})
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["total"] == 8 and d["valid"] == 1 and d["imported"] == 0 and d["committed"] is False
        errs = {x["candidate_name"]: " ".join(x["errors"]) for x in d["rows"]}
        assert "phone_number" in errs["TEST_Bad Phone"]
        assert "past" in errs["TEST_Past"]
        assert "interview_time" in errs["TEST_BadTime"]
        assert "language" in errs["TEST_BadLang"]
        assert "office_address" in errs["TEST_NoAddr"]
        assert "duplicate" in errs["TEST_Dup"]
        assert "already exists" in errs["TEST_Existing"]
        assert all("phone_e164" not in x for x in d["rows"])
        # preview must not persist
        items = s.get(f"{API}/test-candidates").json()["items"]
        assert not any(i["candidate_name"] == "TEST_Up Good" for i in items)
        # commit
        r = s.post(f"{API}/test-candidates/upload?commit=true", files={"file": ("t.xlsx", f)})
        assert r.status_code == 200 and r.json()["imported"] == 1
        items = s.get(f"{API}/test-candidates").json()["items"]
        got = [i for i in items if i["candidate_name"] == "TEST_Up Good"]
        assert len(got) == 1
        created["cands"].append(got[0]["id"])
        assert got[0]["approved"] is False and got[0]["sheet_approved_flag"] is True
        assert got[0]["source"] == "upload" and "approved_phone" not in got[0]

    def test_csv_full_validation_and_commit(self, s, created):
        lines = [",".join(COLS),
                 f"TEST_CsvGood,9000000057,Data Analyst,{FUT},10:30,English,BluBridge,TEST Office,yes",
                 f"TEST_CsvBadPhone,12345,Data Analyst,{FUT},10:30,English,BluBridge,TEST Office,yes",
                 f"TEST_CsvPast,9000000058,Data Analyst,{PAST},10:30,English,BluBridge,TEST Office,no",
                 f"TEST_CsvBadTime,9000000059,Data Analyst,{FUT},25:99,English,BluBridge,TEST Office,no",
                 f"TEST_CsvBadLang,9000000065,Data Analyst,{FUT},10:30,Hindi,BluBridge,TEST Office,no",
                 f"TEST_CsvNoAddr,9000000066,Data Analyst,{FUT},10:30,Tamil,BluBridge,,no",
                 f"TEST_CsvDup,9000000057,Data Analyst,{FUT},2:00 PM,Tamil,BluBridge,TEST Office,yes"]
        f = ("\n".join(lines) + "\n").encode()
        d = s.post(f"{API}/test-candidates/upload?commit=false", files={"file": ("t.csv", f)}).json()
        assert d["total"] == 7 and d["valid"] == 1 and d["imported"] == 0
        errs = {x["candidate_name"]: " ".join(x["errors"]) for x in d["rows"]}
        assert "phone_number" in errs["TEST_CsvBadPhone"] and "past" in errs["TEST_CsvPast"]
        assert "interview_time" in errs["TEST_CsvBadTime"] and "language" in errs["TEST_CsvBadLang"]
        assert "office_address" in errs["TEST_CsvNoAddr"] and "duplicate" in errs["TEST_CsvDup"]
        bad_cols = s.post(f"{API}/test-candidates/upload", files={"file": ("t.csv", b"name,phone\na,9000000051\n")})
        assert bad_cols.status_code == 400 and "Column mismatch" in bad_cols.json()["detail"]
        r = s.post(f"{API}/test-candidates/upload?commit=true", files={"file": ("t.csv", f)})
        assert r.json()["imported"] == 1
        got = [i for i in s.get(f"{API}/test-candidates").json()["items"] if i["candidate_name"] == "TEST_CsvGood"]
        assert len(got) == 1
        created["cands"].append(got[0]["id"])
        assert got[0]["approved"] is False and got[0]["sheet_approved_flag"] is True

    def test_csv_upload_preview(self, s):
        csv = ",".join(COLS) + f"\nTEST_Csv,9000000056,Analyst,{FUT},14:00,tamil,BluBridge,TEST Office,yes\n"
        r = s.post(f"{API}/test-candidates/upload?commit=false", files={"file": ("t.csv", csv.encode())})
        assert r.status_code == 200 and r.json()["valid"] == 1
        assert r.json()["rows"][0]["language"] == "Tamil"


# ---- manual / approval / edit / opt-out / revoke ----
@pytest.mark.skip(reason="Approval workflow removed in Phase 7A; consent flow covered by test_ai_calling_phase7a.py")
class TestCandidateLifecycle:
    def test_manual_validation(self, s, created):
        r = s.post(f"{API}/test-candidates", json=_cand("TEST_Bad", "abc", language="French"))
        assert r.status_code == 400
        for name in ("TEST_DupBase", "TEST_Dup"):
            r = s.post(f"{API}/test-candidates", json=_cand(name, "9000000011"))
            if r.status_code == 200:
                created["cands"].append(r.json()["id"])
        assert r.status_code == 409

    @pytest.mark.skip(reason="Phase 2 lifecycle superseded by Phase 3 API; covered in test_ai_calling_phase3.py")
    def test_full_lifecycle(self, s, created):
        r = s.post(f"{API}/test-candidates", json=_cand("TEST_Manual", "9000000061"))
        assert r.status_code == 200, r.text
        c = r.json(); cid = c["id"]; created["cands"].append(cid)
        assert c["approved"] is False and c["phone_e164"] == "+919000000061" and c["phone_masked"] == "+91*****0061"
        # approval guards
        assert s.post(f"{API}/test-candidates/{cid}/approve", json={"consent_confirmed": False, "phone_last4": "0061"}).status_code == 400
        assert s.post(f"{API}/test-candidates/{cid}/approve", json={"consent_confirmed": True, "phone_last4": "1111"}).status_code == 400
        r = s.post(f"{API}/test-candidates/{cid}/approve", json={"consent_confirmed": True, "phone_last4": "0061"})
        assert r.status_code == 200 and r.json()["approved"] is True and r.json()["consent_confirmed"] is True
        # edit non-phone keeps approval
        r = s.put(f"{API}/test-candidates/{cid}", json=_cand("TEST_Manual2", "9000000061"))
        assert r.status_code == 200 and r.json()["approved"] is True and r.json()["candidate_name"] == "TEST_Manual2"
        # edit phone resets
        r = s.put(f"{API}/test-candidates/{cid}", json=_cand("TEST_Manual2", "9000000062"))
        assert r.status_code == 200 and r.json()["approved"] is False and r.json()["consent_confirmed"] is False
        # edit to existing phone -> 409
        assert s.put(f"{API}/test-candidates/{cid}", json=_cand("TEST_Manual2", "9000000011")).status_code == 409
        # re-approve then revoke
        assert s.post(f"{API}/test-candidates/{cid}/approve", json={"consent_confirmed": True, "phone_last4": "0062"}).json()["approved"] is True
        r = s.post(f"{API}/test-candidates/{cid}/revoke")
        assert r.status_code == 200 and r.json()["approved"] is False
        # approve then opt-out revokes
        s.post(f"{API}/test-candidates/{cid}/approve", json={"consent_confirmed": True, "phone_last4": "0062"})
        r = s.post(f"{API}/test-candidates/{cid}/opt-out", json={"opted_out": True})
        assert r.json()["opted_out"] is True and r.json()["approved"] is False
        assert s.post(f"{API}/test-candidates/{cid}/approve", json={"consent_confirmed": True, "phone_last4": "0062"}).status_code == 400
        r = s.post(f"{API}/test-candidates/{cid}/opt-out", json={"opted_out": False})
        assert r.json()["opted_out"] is False and r.json()["approved"] is False

    def test_not_found(self, s):
        assert s.post(f"{API}/test-candidates/bad/approve", json={"consent_confirmed": True, "phone_last4": "0000"}).status_code == 404
        assert s.put(f"{API}/test-candidates/{ObjectId()}", json=_cand("X", "9000000069")).status_code == 404


# ---- batches + gate ----
@pytest.mark.skip(reason="Approval workflow removed in Phase 7A; consent flow covered by test_ai_calling_phase7a.py")
class TestBatches:
    def test_batch_flow(self, s, created):
        a = s.post(f"{API}/test-candidates", json=_cand("TEST_BatchA", "9000000063")).json(); created["cands"].append(a["id"])
        b = s.post(f"{API}/test-candidates", json=_cand("TEST_BatchB", "9000000064")).json(); created["cands"].append(b["id"])
        # unapproved rejected
        assert s.post(f"{API}/test-batches", json={"name": "TEST_x", "candidate_ids": [a["id"]]}).status_code == 400
        assert s.post(f"{API}/test-batches", json={"name": "TEST_x", "candidate_ids": []}).status_code == 400
        s.post(f"{API}/test-candidates/{a['id']}/approve", json={"consent_confirmed": True, "phone_last4": "0063"})
        # mix approved + unapproved rejected
        assert s.post(f"{API}/test-batches", json={"name": "TEST_x", "candidate_ids": [a["id"], b["id"]]}).status_code == 400
        r = s.post(f"{API}/test-batches", json={"name": "TEST_Batch", "candidate_ids": [a["id"]]})
        assert r.status_code == 200, r.text
        bt = r.json(); created["batches"].append(bt["id"])
        assert bt["status"] == "draft" and bt["candidate_ids"] == [a["id"]]
        assert any(x["id"] == bt["id"] for x in s.get(f"{API}/test-batches").json()["items"])
        # preflight
        pf = s.post(f"{API}/test-batches/{bt['id']}/preflight").json()
        res = pf["results"][0]
        assert res["allowed"] is False
        ck = {c["key"]: c["ok"] for c in res["checks"]}
        assert ck["bolna_approved"] is False
        assert ck["admin_approved"] and ck["phone_matches"] and ck["consent"] and ck["in_batch"]
        # start 423
        r = s.post(f"{API}/test-batches/{bt['id']}/start")
        assert r.status_code == 423
        # stop
        r = s.post(f"{API}/test-batches/{bt['id']}/stop")
        assert r.status_code == 200 and r.json()["stopped"] is True
        st = [x for x in s.get(f"{API}/test-batches").json()["items"] if x["id"] == bt["id"]][0]
        assert st["status"] == "stopped"
        assert s.post(f"{API}/test-batches/{ObjectId()}/start").status_code == 404


# ---- mode / settings / estop ----
class TestModeSettings:
    def test_live_forbidden(self, s):
        r = s.post(f"{API}/mode", json={"mode": "live"})
        assert r.status_code == 403
        assert s.get(f"{API}/settings").json()["mode"] != "live"
        assert s.post(f"{API}/mode", json={"mode": "bogus"}).status_code == 400

    def test_toggle_bumps_version(self, s):
        v0 = s.get(f"{API}/settings").json()["mode_version"]
        r = s.post(f"{API}/mode", json={"mode": "off"}).json()
        assert r["mode"] == "off"
        r = s.post(f"{API}/mode", json={"mode": "testing"}).json()
        assert r["mode"] == "testing" and r["mode_version"] >= v0 + 1
        assert isinstance(r["mode"], str)  # single field

    def test_settings_validation(self, s):
        assert s.put(f"{API}/settings", json={"daily_call_limit": 500}).status_code == 400
        assert s.put(f"{API}/settings", json={"max_concurrent_calls": 9}).status_code == 400
        r = s.put(f"{API}/settings", json={"daily_call_limit": 15})
        assert r.status_code == 200 and r.json()["daily_call_limit"] == 15
        assert s.get(f"{API}/settings").json()["daily_call_limit"] == 15

    def test_emergency_stop(self, s):
        r = s.post(f"{API}/emergency-stop", json={"active": True})
        assert r.status_code == 200 and r.json()["emergency_stop"] is True
        assert s.get(f"{API}/summary").json()["emergency_stop"] is True
        r = s.post(f"{API}/emergency-stop", json={"active": False})
        assert r.json()["emergency_stop"] is False

    def test_live_status_and_calls(self, s):
        d = s.get(f"{API}/live/status").json()
        assert d["locked"] is True and d["active"] is False
        items = s.get(f"{API}/calls").json()["items"]
        assert all(c["mode"] == "testing" for c in items)  # Phase 4B's one real test call may exist; never live
        assert s.get(f"{API}/calls/{ObjectId()}").status_code == 404


# ---- safety invariants ----
class TestInvariants:
    def test_no_jobs_or_calls(self):
        m = _mongo()
        unresolved = {"state": {"$in": ["dispatching", "accepted", "pending_reconciliation", "needs_review"]}}
        assert m.ai_calls.count_documents({"mode": "live"}) == 0 and m.ai_call_jobs.count_documents({"mode": "live"}) == 0
        assert m.ai_calls.count_documents(unresolved) == 0

    def test_summary_flags(self, s):
        d = s.get(f"{API}/summary").json()
        assert d["bolna_integration_approved"] is False and d["live_mode_locked"] is True
