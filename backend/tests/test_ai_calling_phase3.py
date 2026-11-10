# Phase 3 — AI Calling Testing Mode: Test Candidate Management regression tests
# Uses ONLY dummy phones +9190000002xx; deletes only the ids it created.
import io
import os
from datetime import date, timedelta

import openpyxl
import pytest
import requests

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL').rstrip('/')
API = f"{BASE_URL}/api/ai-calling"
COLUMNS = ["candidate_name", "phone_number", "job_role", "interview_date", "interview_time",
           "language", "company_name", "office_address", "approved_for_test_call"]
FUT = (date.today() + timedelta(days=20)).isoformat()
CREATED = []


def _row(name, phone, **kw):
    r = dict(candidate_name=name, phone_number=phone, job_role="QA", interview_date=FUT, interview_time="10",
             language="English", company_name="BluBridge", office_address="Chennai", approved_for_test_call="YES")
    r.update(kw)
    return r


def _manual(name, phone, **kw):
    r = _row(name, phone, **kw)
    r.pop("approved_for_test_call")
    return r


@pytest.fixture(scope="module")
def s():
    sess = requests.Session()
    r = sess.post(f"{BASE_URL}/api/login", json={"username": "Admin User", "password": "QAZwsx##123"})
    if r.status_code != 200:
        pytest.skip("login failed")
    yield sess
    for cid in CREATED:
        sess.delete(f"{API}/test-candidates/{cid}")


def _ids_by_phone(s, phones):
    items = s.get(f"{API}/test-candidates", params={"page_size": 100}).json()["items"]
    # list hides approved_phone but exposes phone_e164
    return {i["phone_e164"]: i["id"] for i in items if i["phone_e164"] in phones}


# --- auth / template ---
class TestTemplate:
    def test_unauth_rejected(self):
        assert requests.get(f"{API}/template").status_code in (401, 403)

    def test_xlsx_template(self, s):
        r = s.get(f"{API}/template")
        assert r.status_code == 200
        wb = openpyxl.load_workbook(io.BytesIO(r.content))
        assert wb.sheetnames == ["Test Candidates", "Instructions"]
        ws = wb["Test Candidates"]
        rows = list(ws.iter_rows(values_only=True))
        assert list(rows[0]) == COLUMNS
        data = [x for x in rows[1:] if any(x)]
        assert len(data) == 2
        assert all(str(x[0]).startswith("EXAMPLE") for x in data)
        assert data[0][1] == "+919000000001" and isinstance(data[0][1], str)
        assert ws["B2"].number_format == "@"
        date.fromisoformat(data[0][3])
        assert data[0][4] == "10" and data[1][4] == "14"
        assert {data[0][5], data[1][5]} == {"English", "Tamil"}
        assert {data[0][8], data[1][8]} == {"YES", "NO"}

    def test_csv_template(self, s):
        r = s.get(f"{API}/template", params={"format": "csv"})
        assert r.status_code == 200
        assert r.text.splitlines()[0] == ",".join(COLUMNS)


# --- upload preview / validate / import ---
class TestUpload:
    def test_sample_unchanged_both_example(self, s):
        x = s.get(f"{API}/template").content
        r = s.post(f"{API}/test-candidates/upload", files={"file": ("s.xlsx", x)})
        assert r.status_code == 200
        d = r.json()
        assert d["total"] == 2 and d["valid"] == 0 and d["by_category"]["example_row"] == 2

    def test_txt_rejected(self, s):
        r = s.post(f"{API}/test-candidates/upload", files={"file": ("a.txt", b"hello")})
        assert r.status_code == 400 and "Unsupported file type" in r.json()["detail"]

    def test_column_mismatch(self, s):
        r = s.post(f"{API}/test-candidates/upload", files={"file": ("a.csv", b"name,phone\nx,y\n")})
        assert r.status_code == 400 and "Column mismatch" in r.json()["detail"]

    def test_mixed_csv_categories(self, s):
        base = s.post(f"{API}/test-candidates", json=_manual("TEST_existing_base", "+919000000011"))
        if base.status_code == 200:
            CREATED.append(base.json()["id"])
        rows = [
            _row("TEST_ok", "+919000000201"),
            _row("TEST_dup", "+919000000201"),
            _row("TEST_badphone", "12345"),
            _row("TEST_baddate", "+919000000203", interview_date="20/12/2026"),
            _row("TEST_badtime", "+919000000204", interview_time="25"),
            _row("TEST_badlang", "+919000000205", language="Hindi"),
            _row("", "+919000000206"),
            _row("TEST_existing", "+919000000011"),
            _row("TEST_flag", "+919000000207", approved_for_test_call="maybe"),
            _row("TEST_past", "+919000000208", interview_date="2020-01-01"),
        ]
        csv = ",".join(COLUMNS) + "\n" + "\n".join(",".join(r[c] for c in COLUMNS) for r in rows)
        r = s.post(f"{API}/test-candidates/upload", files={"file": ("m.csv", csv.encode())})
        assert r.status_code == 200
        d = r.json()
        c = d["by_category"]
        assert d["total"] == 10 and d["valid"] == 1
        for k in ("duplicate_in_file", "invalid_phone", "invalid_time", "invalid_language",
                  "missing_field", "duplicate_existing", "invalid_value"):
            assert c[k] >= 1, k
        assert c["invalid_date"] == 2
        # nothing saved
        assert not _ids_by_phone(s, {"+919000000201"})

    def test_import_rejected_when_invalid(self, s):
        r = s.post(f"{API}/test-candidates/import", json={"rows": [
            {"row": 2, "values": _row("TEST_a", "+919000000209")},
            {"row": 3, "values": _row("TEST_b", "bad")}]})
        assert r.status_code == 400 and "still invalid" in r.json()["detail"]

    def test_validate_then_import(self, s):
        rows = [{"row": 2 + i, "values": _row(f"TEST_imp{i}", f"+9190000002{10 + i}", language="Tamil" if i % 2 else "english")}
                for i in range(22)]
        v = s.post(f"{API}/test-candidates/validate-rows", json={"rows": rows})
        assert v.status_code == 200 and v.json()["valid"] == 22
        r = s.post(f"{API}/test-candidates/import", json={"rows": rows, "filename": "t.csv"})
        assert r.status_code == 200
        d = r.json()
        assert d["imported"] == 22 and d["upload_batch_id"].startswith("UP-")
        ids = _ids_by_phone(s, {f"+9190000002{10 + i}" for i in range(22)})
        assert len(ids) == 22
        CREATED.extend(ids.values())
        items = s.get(f"{API}/test-candidates", params={"search": "TEST_imp0"}).json()["items"]
        it = items[0]
        assert it["source"] == "upload" and it["approved"] is False and it["interview_timezone"] == "Asia/Kolkata"
        assert it["upload_batch_id"] == d["upload_batch_id"] and it["test_candidate_id"].startswith("TC-")
        assert it["language"] == "English" and it["interview_time"] == "10:00"
        assert "*****" in it["phone_masked"]
        # re-import → duplicate_existing
        v2 = s.post(f"{API}/test-candidates/validate-rows", json={"rows": rows[:1]}).json()
        assert v2["by_category"]["duplicate_existing"] == 1


# --- list / filters / pagination ---
class TestList:
    def test_pagination(self, s):
        d = s.get(f"{API}/test-candidates", params={"search": "TEST_imp", "page_size": 20}).json()
        assert d["total"] == 22 and d["pages"] == 2 and len(d["items"]) == 20
        d2 = s.get(f"{API}/test-candidates", params={"search": "TEST_imp", "page": 2}).json()
        assert len(d2["items"]) == 2

    def test_filters(self, s):
        d = s.get(f"{API}/test-candidates", params={"search": "TEST_imp", "language": "Tamil"}).json()
        assert d["total"] == 11 and all(i["language"] == "Tamil" for i in d["items"])
        d = s.get(f"{API}/test-candidates", params={"search": "TEST_imp", "source": "manual"}).json()
        assert d["total"] == 0
        d = s.get(f"{API}/test-candidates", params={"search": "TEST_imp", "ready": "not_approved"}).json()
        assert d["total"] == 22
        d = s.get(f"{API}/test-candidates", params={"search": "9000000215"}).json()
        assert d["total"] == 1


# --- manual / approve / edit / bulk / delete ---
class TestCrud:
    def test_manual_validation(self, s):
        r = s.post(f"{API}/test-candidates", json=_manual("TEST_m", "+919000000240", company_name=""))
        assert r.status_code == 400 and "company_name" in r.json()["detail"]
        r = s.post(f"{API}/test-candidates", json=_manual("TEST_m", "5550001"))
        assert r.status_code == 400
        base = s.post(f"{API}/test-candidates", json=_manual("TEST_dupbase", "+919000000011"))
        if base.status_code == 200:
            CREATED.append(base.json()["id"])
        r = s.post(f"{API}/test-candidates", json=_manual("TEST_m", "+919000000011"))
        if r.status_code == 200:
            CREATED.append(r.json()["id"])
        assert r.status_code == 409

    def test_manual_approve_edit_flow(self, s):
        r = s.post(f"{API}/test-candidates", json=_manual("TEST_manual", "9000000240", interview_time="15:30"))
        assert r.status_code == 200
        c = r.json()
        CREATED.append(c["id"])
        assert c["phone_e164"] == "+919000000240" and c["source"] == "manual" and c["readiness"] == "not_approved"
        cid = c["id"]
        assert s.post(f"{API}/test-candidates/{cid}/approve", json={"consent_confirmed": True, "phone_last4": "1111"}).status_code == 400
        assert s.post(f"{API}/test-candidates/{cid}/approve", json={"consent_confirmed": False, "phone_last4": "0240"}).status_code == 400
        a = s.post(f"{API}/test-candidates/{cid}/approve", json={"consent_confirmed": True, "phone_last4": "0240"})
        assert a.status_code == 200 and a.json()["readiness"] == "ready_calling_disabled"
        assert a.json()["approval_audit"][-1]["action"] == "approved"
        e = s.put(f"{API}/test-candidates/{cid}", json=_manual("TEST_manual", "+919000000241"))
        assert e.status_code == 200
        ed = e.json()
        assert ed["approved"] is False and ed["readiness"] == "not_approved"
        assert ed["approval_audit"][-1]["action"] == "approval_invalidated"

    def test_bulk(self, s):
        ids = list(_ids_by_phone(s, {f"+9190000002{10 + i}" for i in range(3)}).values())
        assert s.post(f"{API}/test-candidates/bulk-approve", json={"ids": ids, "consent_confirmed": True, "confirmation": "approve"}).status_code == 400
        assert s.post(f"{API}/test-candidates/bulk-approve", json={"ids": ids, "consent_confirmed": False, "confirmation": "APPROVE"}).status_code == 400
        r = s.post(f"{API}/test-candidates/bulk-approve", json={"ids": ids, "consent_confirmed": True, "confirmation": "APPROVE"})
        assert r.status_code == 200 and r.json()["approved"] == 3
        r = s.post(f"{API}/test-candidates/bulk-revoke", json={"ids": ids})
        assert r.status_code == 200 and r.json()["revoked"] == 3
        d = s.get(f"{API}/test-candidates", params={"search": "TEST_imp", "approval": "approved"}).json()
        assert d["total"] == 0
        assert s.post(f"{API}/test-candidates/bulk-delete", json={"ids": ids[:2], "confirmation": "delete"}).status_code == 400
        r = s.post(f"{API}/test-candidates/bulk-delete", json={"ids": ids[:2], "confirmation": "DELETE"})
        assert r.status_code == 200 and r.json()["deleted"] == 2
        r = s.delete(f"{API}/test-candidates/{ids[2]}")
        assert r.status_code == 200
        assert s.delete(f"{API}/test-candidates/{ids[2]}").status_code == 404


# --- calling gates ---
class TestCallingGates:
    def test_initiate_423(self, s):
        r = s.post(f"{API}/calls/initiate", json={})
        assert r.status_code == 423
        assert r.json()["detail"] == "AI Calling will be enabled after Bolna API integration and testing are completed."

    def test_live_403(self, s):
        assert s.post(f"{API}/mode", json={"mode": "live"}).status_code == 403

    def test_stop_and_state(self, s):
        r = s.post(f"{API}/calls/stop")
        assert r.status_code == 200 and "cancelled_jobs" in r.json()
        sm = s.get(f"{API}/summary").json()
        assert sm["emergency_stop"] is True and sm["live_mode_locked"] is True
