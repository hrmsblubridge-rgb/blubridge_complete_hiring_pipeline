"""Iteration 39 backend tests:
1. Bulk Upload (naukri/pipeline/score) end-to-end with sequential queue worker
2. Hiring Form 'Show Instruction Page?' field (show_instruction_page + instruction_content)
3. Messaging workers (OTP IST-based generator, continuous Rejection mailer)
4. pipeline_data updated after OTP verification
"""
import os
import time
import asyncio
from datetime import datetime, timezone, timedelta, date
from pathlib import Path

import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://recruit-pipeline-fix-1.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"

# IST tz — used for OTP worker assertions
IST = timezone(timedelta(hours=5, minutes=30))
MESSAGING_CUTOFF_TS = os.environ.get("MESSAGING_CUTOFF_TS", "2026-05-04T18:07:51.691447+00:00")


# -------- fixtures --------

@pytest.fixture(scope="session")
def session():
    s = requests.Session()
    r = s.post(f"{API}/login", json={"username": "Admin User", "password": "Admin User"}, timeout=30)
    assert r.status_code == 200, f"Login failed: {r.status_code} {r.text}"
    return s


@pytest.fixture(scope="session")
def mongo_db():
    """Direct DB access for OTP/Rejection worker assertions and seed cleanup."""
    try:
        from pymongo import MongoClient  # type: ignore
    except Exception:
        pytest.skip("pymongo not installed")
    mongo_url = os.environ.get("MONGO_URL")
    db_name = os.environ.get("DB_NAME", "hr_analytics")
    if not mongo_url:
        # try reading backend/.env directly
        env_path = Path("/app/backend/.env")
        if env_path.exists():
            for line in env_path.read_text().splitlines():
                if line.startswith("MONGO_URL"):
                    mongo_url = line.split("=", 1)[1].strip().strip('"')
                if line.startswith("DB_NAME"):
                    db_name = line.split("=", 1)[1].strip().strip('"')
    if not mongo_url:
        pytest.skip("MONGO_URL not configured")
    client = MongoClient(mongo_url)
    yield client[db_name]
    client.close()


# ============ TASK 1: BULK UPLOAD ============

def _wait_until(predicate, timeout_s=20, poll=1.0):
    end = time.time() + timeout_s
    while time.time() < end:
        if predicate():
            return True
        time.sleep(poll)
    return False


def _upload(session, upload_type, filename, content_bytes):
    files = {"files": (filename, content_bytes, "text/csv")}
    return session.post(f"{API}/bulk-upload/{upload_type}", files=files, timeout=60)


def _get_status(session, upload_type):
    r = session.get(f"{API}/bulk-upload/status", timeout=30)
    assert r.status_code == 200, f"status failed: {r.status_code} {r.text[:200]}"
    return r.json().get(upload_type, {})


# ---- naukri ----

def test_bulk_upload_naukri_completes(session):
    csv = (
        "Name,Email ID,Phone Number,Job Title\n"
        "TEST_Naukri_A,test_naukri_a@example.com,9000000001,QA Engineer\n"
        "TEST_Naukri_B,test_naukri_b@example.com,9000000002,Backend Dev\n"
    ).encode()
    fname = f"TEST_naukri_{int(time.time())}.csv"
    r = _upload(session, "naukri", fname, csv)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["success"] is True
    # `saved` returns server-side safe_name which embeds the original filename
    assert any(fname in s for s in body["saved"]), body

    # Wait for worker to complete
    def done():
        st = _get_status(session, "naukri")
        return any(p.get("name") == fname for p in st.get("processed", []))

    assert _wait_until(done, timeout_s=25, poll=1.5), \
        f"naukri file not processed within 25s. status={_get_status(session, 'naukri')}"

    st = _get_status(session, "naukri")
    proc = next(p for p in st["processed"] if p["name"] == fname)
    assert proc["result"]["success"] is True

    # File should be moved to processed_files
    proc_dir = Path("/app/processed_files/naukri")
    assert any(fname in p.name for p in proc_dir.iterdir()), \
        f"file not moved to {proc_dir}"


# ---- pipeline ----

def test_bulk_upload_pipeline_completes(session):
    csv = (
        "name,email,phone,job_role\n"
        "TEST_Pipe_A,test_pipe_a@example.com,9000000003,QA\n"
        "TEST_Pipe_B,test_pipe_b@example.com,9000000004,Dev\n"
    ).encode()
    fname = f"TEST_pipeline_{int(time.time())}.csv"
    r = _upload(session, "pipeline", fname, csv)
    assert r.status_code == 200, r.text
    assert any(fname in s for s in r.json()["saved"])

    def done():
        st = _get_status(session, "pipeline")
        return any(p.get("name") == fname for p in st.get("processed", []))

    assert _wait_until(done, timeout_s=30, poll=1.5), \
        f"pipeline file not processed within 30s — possibly stuck on reprocess_matching. status={_get_status(session, 'pipeline')}"


# ---- score ----

def test_bulk_upload_score_completes(session):
    csv = (
        "name,email,phone,score,round_name\n"
        "TEST_Score_A,test_score_a@example.com,9000000005,8.5,Round 1\n"
    ).encode()
    fname = f"TEST_score_{int(time.time())}.csv"
    r = _upload(session, "score", fname, csv)
    assert r.status_code == 200, r.text

    def done():
        st = _get_status(session, "score")
        return any(p.get("name") == fname for p in st.get("processed", []))

    assert _wait_until(done, timeout_s=20, poll=1.0), \
        f"score file not processed. status={_get_status(session, 'score')}"


# ---- invalid type ----

def test_bulk_upload_invalid_type_returns_400(session):
    csv = b"a,b\n1,2\n"
    files = {"files": ("x.csv", csv, "text/csv")}
    r = session.post(f"{API}/bulk-upload/invalidtype", files=files, timeout=20)
    assert r.status_code == 400
    assert "Invalid type" in r.text


# ---- status shape ----

def test_bulk_upload_status_shape(session):
    r = session.get(f"{API}/bulk-upload/status", timeout=30)
    assert r.status_code == 200
    body = r.json()
    for key in ("naukri", "pipeline", "score"):
        assert key in body
        assert "pending" in body[key]
        assert "processed" in body[key]
        assert "failed" in body[key]
        for f in body[key]["failed"]:
            # error key must always be set (reading new error_message OR legacy error)
            assert "error" in f


# ---- clear-failed endpoint ----

def test_clear_failed_endpoint(session, mongo_db):
    # Seed a failed doc for naukri
    doc = {
        "file_name": "TEST_failed_seed.csv",
        "file_path": "/tmp/TEST_failed_seed.csv",
        "file_type": "naukri",
        "status": "failed",
        "error_message": "seeded failure",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    inserted = mongo_db.bulk_upload_queue.insert_one(doc)

    try:
        r = session.post(f"{API}/bulk-upload/naukri/clear-failed", timeout=30)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["success"] is True
        assert body["archived"] >= 1, body
        # The seeded doc should now be archived
        after = mongo_db.bulk_upload_queue.find_one({"_id": inserted.inserted_id})
        assert after["status"] == "archived"
    finally:
        mongo_db.bulk_upload_queue.delete_one({"_id": inserted.inserted_id})


# ---- queue sequential drain (multi-file) ----

def test_bulk_upload_sequential_queue(session):
    """Upload 2 small naukri files at once — both should complete sequentially."""
    # Clear any pre-existing failed naukri rows so they don't pollute the assertion
    session.post(f"{API}/bulk-upload/naukri/clear-failed", timeout=20)

    fnames = []
    for i in range(2):
        csv = f"Name,Email ID,Phone Number\nTEST_Seq_{i},test_seq_{i}@x.com,90000100{i:02d}\n".encode()
        fname = f"TEST_seqQ_{int(time.time())}_{i}.csv"
        r = _upload(session, "naukri", fname, csv)
        assert r.status_code == 200
        fnames.append(fname)

    def all_done():
        st = _get_status(session, "naukri")
        names = {p["name"] for p in st.get("processed", [])}
        return all(f in names for f in fnames)

    assert _wait_until(all_done, timeout_s=60, poll=2.0), \
        f"sequential queue did not drain. status={_get_status(session, 'naukri')}"


# ============ TASK 2: HIRING FORM show_instruction_page ============

@pytest.fixture
def created_form_id(session):
    # Fetch or create a form type
    rt = session.get(f"{API}/bb/form-types", timeout=20)
    assert rt.status_code == 200, rt.text
    types = rt.json().get("form_types", [])
    if types:
        form_type_id = str(types[0].get("id") or types[0].get("_id"))
        form_type_name = types[0].get("name", "TestType")
    else:
        rc = session.post(f"{API}/bb/form-types", json={"name": "TEST_FormType_Iter39"}, timeout=20)
        assert rc.status_code in (200, 201), rc.text
        rb = rc.json()
        form_type_id = str(rb.get("id") or rb.get("_id"))
        form_type_name = "TEST_FormType_Iter39"

    payload = {
        "name": f"TEST_InstructionForm_{int(time.time())}",
        "job_role": "Test Role",
        "form_type_id": form_type_id,
        "form_type_name": form_type_name,
        "conditions": {},
        "job_description_attached": False,
        "show_instruction_page": True,
        "instruction_content": "<p>Hello, please read these instructions before continuing.</p>",
    }
    r = session.post(f"{API}/bb/hiring-forms", json=payload, timeout=30)
    assert r.status_code in (200, 201), r.text
    body = r.json()
    form = body.get("form") or body
    fid = form.get("id") or form.get("_id") or body.get("form_id")
    assert fid, f"no id in create response: {body}"
    yield fid, form
    # teardown
    try:
        session.delete(f"{API}/bb/hiring-forms/{fid}", timeout=10)
    except Exception:
        pass


def test_create_hiring_form_with_instruction_fields(session, created_form_id):
    fid, form = created_form_id
    # Verify GET (admin) reflects fields — fetch form list & find it
    r = session.get(f"{API}/bb/hiring-forms", timeout=30)
    assert r.status_code == 200
    listing = r.json()
    forms = listing.get("forms", listing) if isinstance(listing, dict) else listing
    matched = next((f for f in forms if str(f.get("id") or f.get("_id")) == str(fid)), None)
    assert matched, f"created form {fid} not in list"
    assert matched.get("show_instruction_page") is True
    assert "Hello" in (matched.get("instruction_content") or "")


def test_public_form_returns_instruction_fields(session, created_form_id):
    fid, form = created_form_id
    slug = form.get("slug") or fid
    r = requests.get(f"{API}/pub/form/{slug}", timeout=30)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data.get("show_instruction_page") is True, data
    assert "Hello" in (data.get("instruction_content") or ""), data


def test_update_hiring_form_show_instruction_false(session, created_form_id):
    fid, form = created_form_id
    r = session.put(f"{API}/bb/hiring-forms/{fid}",
                    json={"show_instruction_page": False, "instruction_content": ""},
                    timeout=30)
    assert r.status_code == 200, r.text
    # Verify via public form (read after write)
    slug = form.get("slug") or fid
    r2 = requests.get(f"{API}/pub/form/{slug}", timeout=30)
    assert r2.status_code == 200
    assert r2.json().get("show_instruction_page") is False


# ============ TASK 3: MESSAGING WORKERS ============

def test_bg_workers_uses_ist():
    """Code-level verification: bg_workers._local_now() returns IST time."""
    import sys
    sys.path.insert(0, "/app/backend")
    import importlib
    bg = importlib.import_module("bg_workers")
    now = bg._local_now()
    assert now.tzinfo is not None, "_local_now() must be tz-aware"
    offset = now.utcoffset()
    assert offset == timedelta(hours=5, minutes=30), \
        f"_local_now() expected IST (+5:30) but got {offset}"


def test_otp_worker_processes_seeded_record(mongo_db):
    """Insert a bb_registrations doc whose schedule_time is ~30 minutes ahead in IST and
    verify the OTP worker (30s tick) sets otp_sent=True with otpGeneratedAt/otpExpiry."""
    # Build IST 'now' and an interview 30 minutes ahead
    now_ist = datetime.now(IST)
    interview_ist = now_ist + timedelta(minutes=30)
    today_str = now_ist.strftime("%Y-%m-%d")
    hhmm = interview_ist.strftime("%H:%M:%S")

    seed = {
        "full_name": "TEST_OTPGen User",
        "email": "test_otp_seed@example.com",
        "phone": "9000099001",
        "schedule_date": today_str,
        "schedule_time": hhmm,
        "is_shortlisted": True,
        "isTest": True,
        "registered_at": (datetime.now(timezone.utc)).isoformat(),
        "form_id": "TEST",
        "job_role": "TEST_Role",
    }
    inserted = mongo_db.bb_registrations.insert_one(seed)
    try:
        # Worker polls every 30s. Wait up to 70s.
        deadline = time.time() + 70
        sent = False
        doc = None
        while time.time() < deadline:
            doc = mongo_db.bb_registrations.find_one({"_id": inserted.inserted_id})
            if doc and doc.get("otp_sent") is True:
                sent = True
                break
            time.sleep(5)
        assert sent, f"OTP not sent within 70s. doc={doc}"
        assert doc.get("otp"), "otp value missing"
        assert doc.get("otpGeneratedAt"), "otpGeneratedAt missing"
        assert doc.get("otpExpiry"), "otpExpiry missing"
    finally:
        mongo_db.bb_registrations.delete_one({"_id": inserted.inserted_id})


def test_rejection_mailer_continuous_worker(mongo_db):
    """Insert bb_applicant_updates with status=Rejected, isTest=True, updated_at=now.
    Worker polls every 60s — wait up to 90s for rejection_notified=True."""
    now_iso = datetime.now(timezone.utc).isoformat()
    seed = {
        "name": "TEST_Reject User",
        "email": "test_reject_seed@example.com",
        "phone": "9000099002",
        "status": "Rejected",
        "updated_at": now_iso,
        "isTest": True,
    }
    inserted = mongo_db.bb_applicant_updates.insert_one(seed)
    try:
        deadline = time.time() + 100
        notified = False
        doc = None
        while time.time() < deadline:
            doc = mongo_db.bb_applicant_updates.find_one({"_id": inserted.inserted_id})
            if doc and doc.get("rejection_notified") is True:
                notified = True
                break
            time.sleep(5)
        assert notified, f"rejection_notified not set within 100s. doc={doc}"
        assert "rejection_notified_at" in doc
    finally:
        mongo_db.bb_applicant_updates.delete_one({"_id": inserted.inserted_id})


# ============ TASK 3d: pipeline_data update on OTP verify ============

def test_verify_otp_updates_pipeline_data(session, mongo_db):
    """Seed a bb_registrations + pipeline_data record, call /api/bb/verify-otp,
    verify pipeline_data status=Attended and otp_verified=1."""
    phone = "9000099003"
    email = "test_verify_otp@example.com"
    otp_code = "654321"

    reg = {
        "full_name": "TEST_VerifyOTP User",
        "email": email,
        "phone": phone,
        "otp": otp_code,
        "otp_sent": True,
        "is_shortlisted": True,
        "isTest": True,
        "registered_at": datetime.now(timezone.utc).isoformat(),
    }
    pipe = {
        "name": "TEST_VerifyOTP User",
        "email": email,
        "phone": phone,
        "status": "Shortlisted",
        "otp_verified": "0",
    }
    reg_id = mongo_db.bb_registrations.insert_one(reg).inserted_id
    pipe_id = mongo_db.pipeline_data.insert_one(pipe).inserted_id

    try:
        r = session.post(f"{API}/bb/verify-otp", json={"phone": phone, "otp": otp_code}, timeout=30)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body.get("success") is True, body

        # Check pipeline_data updated
        pdoc = mongo_db.pipeline_data.find_one({"_id": pipe_id})
        assert pdoc.get("otp_verified") == "1", f"pipeline_data.otp_verified not updated: {pdoc}"
        assert pdoc.get("status") == "Attended", f"pipeline_data.status not Attended: {pdoc}"

        # bb_registrations updated too
        rdoc = mongo_db.bb_registrations.find_one({"_id": reg_id})
        assert rdoc.get("otp_verified") is True
        assert rdoc.get("status") == "Attended"
    finally:
        mongo_db.bb_registrations.delete_one({"_id": reg_id})
        mongo_db.pipeline_data.delete_one({"_id": pipe_id})
