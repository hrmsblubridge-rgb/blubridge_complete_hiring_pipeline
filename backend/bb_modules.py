"""BluBridge Modules — New features for the Hiring Pipeline.
Separate router to avoid modifying existing server.py logic."""

from fastapi import APIRouter, HTTPException, Request, Query
from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime, timezone
from bson import ObjectId
import hashlib, secrets, re, logging

bb_router = APIRouter(prefix="/api/bb")
# Public router — no auth prefix
pub_router = APIRouter(prefix="/api/pub")

_logger = logging.getLogger("bb_modules")


# ============ MESSAGING STUBS (Present but NOT triggered/tested per instructions) ============

AISENSY_API_URL = "https://backend.aisensy.com/campaign/t1/api/v2"
AISENSY_API_KEY = "eyJhbGciOiJIUzI1NilsInR5cCI6IkpXVCJ9.eyJpZCI6IjY5NDI0MTYwNzA4MDcwNjE5YzAyZWFhNilsIm5hbWUiOiJCbHVicmlkZ2V0ZWNobm9sb2dpZXMiLCJhcHBOYW1IIjoiQWITZW5zeSIsImNsaWVudElkljoiNjg5NDRIOThiMjQ3NDQwYzBkYzljNzI3IiwiYWN0aXZIUGxhbil6IkZSRUVfRk9SRVZFUiIsImlhdCI6MTc2NTk0OTc5Mn0.16lJKhbj6JfK_1zzzUgLMwxy5laqBwu3IjV08xBLRBs"

SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = 465
SMTP_USER = "hr@blubridge.com"
SMTP_PASSWORD = "tmiu rkqp fxcw nwxf"
FROM_EMAIL = "hr@blubridge.com"

OFFICE_LOCATION = "30, Norton Road, Mandavelipakkam, Raja Annamalai Puram, Chennai, Tamil Nadu - 600028."


async def _send_aisensy_whatsapp(campaign_name: str, mobile: str, template_params: list, user_name: str = "Blubridge Technologies"):
    """AiSensy WhatsApp messaging — STUB. Logic present but NOT executed."""
    _logger.info(f"[STUB] WhatsApp: campaign={campaign_name}, mobile={mobile}, params={template_params}")
    # Implementation ready but not triggered per instructions
    return None


async def _send_email(to_email: str, subject: str, html_body: str):
    """SMTP email — STUB. Logic present but NOT executed."""
    _logger.info(f"[STUB] Email: to={to_email}, subject={subject}")
    # Implementation ready but not triggered per instructions
    return None


async def _notify_shortlisted(name: str, phone: str, email: str, schedule_link: str):
    """Send shortlist notification — STUB."""
    _logger.info(f"[STUB] Shortlist notification: {name}, {email}")


async def _notify_rejected(phone: str, email: str):
    """Send rejection notification — STUB."""
    _logger.info(f"[STUB] Reject notification: {email}")


async def _notify_schedule_confirmation(name: str, phone: str, email: str, date: str, time: str):
    """Send schedule confirmation — STUB."""
    _logger.info(f"[STUB] Schedule confirmation: {name}, {date} {time}")


async def _send_otp_notification(name: str, phone: str, email: str, job_role: str, otp: str, date: str, time: str):
    """Send OTP notification — STUB."""
    _logger.info(f"[STUB] OTP notification: {name}, otp={otp}")


async def _send_missed_reminder(name: str, phone: str, email: str, role: str, date: str, time: str, reschedule_link: str):
    """Send missed interview reminder — STUB."""
    _logger.info(f"[STUB] Missed reminder: {name}, {date} {time}")

# Shared dependencies — injected from server.py
_db = None
_auth_fn = None
_build_college_rank_lookup_fn = None
_classify_college_fn = None


def init_bb(database, auth_fn, college_lookup_fn, classify_fn):
    global _db, _auth_fn, _build_college_rank_lookup_fn, _classify_college_fn
    _db = database
    _auth_fn = auth_fn
    _build_college_rank_lookup_fn = college_lookup_fn
    _classify_college_fn = classify_fn


async def _require_auth(request: Request):
    return await _auth_fn(request)


def _oid(id_str: str) -> ObjectId:
    try:
        return ObjectId(id_str)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid ID format")


# ============ JOB ROLES ============

class JobRoleBody(BaseModel):
    name: str

@bb_router.get("/job-roles")
async def list_job_roles(request: Request):
    await _require_auth(request)
    roles = await _db.bb_job_roles.find({}).sort("name", 1).to_list(None)
    for r in roles:
        r["id"] = str(r.pop("_id"))
    return {"roles": roles}

@bb_router.post("/job-roles")
async def create_job_role(data: JobRoleBody, request: Request):
    await _require_auth(request)
    name = data.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Name required")
    doc = {"name": name, "created_at": datetime.now(timezone.utc).isoformat()}
    result = await _db.bb_job_roles.insert_one(doc)
    return {"success": True, "id": str(result.inserted_id), "name": name}

@bb_router.put("/job-roles/{role_id}")
async def update_job_role(role_id: str, data: JobRoleBody, request: Request):
    await _require_auth(request)
    result = await _db.bb_job_roles.update_one({"_id": _oid(role_id)}, {"$set": {"name": data.name.strip()}})
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Not found")
    return {"success": True}

@bb_router.delete("/job-roles/{role_id}")
async def delete_job_role(role_id: str, request: Request):
    await _require_auth(request)
    result = await _db.bb_job_roles.delete_one({"_id": _oid(role_id)})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Not found")
    return {"success": True}


# ============ FORM TYPES ============

class FormTypeBody(BaseModel):
    name: str

@bb_router.get("/form-types")
async def list_form_types(request: Request):
    await _require_auth(request)
    types = await _db.bb_form_types.find({}).sort("name", 1).to_list(None)
    for t in types:
        t["id"] = str(t.pop("_id"))
    return {"form_types": types}

@bb_router.post("/form-types")
async def create_form_type(data: FormTypeBody, request: Request):
    await _require_auth(request)
    name = data.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Name required")
    doc = {"name": name, "created_at": datetime.now(timezone.utc).isoformat()}
    result = await _db.bb_form_types.insert_one(doc)
    return {"success": True, "id": str(result.inserted_id), "name": name}

@bb_router.put("/form-types/{type_id}")
async def update_form_type(type_id: str, data: FormTypeBody, request: Request):
    await _require_auth(request)
    result = await _db.bb_form_types.update_one({"_id": _oid(type_id)}, {"$set": {"name": data.name.strip()}})
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Not found")
    return {"success": True}

@bb_router.delete("/form-types/{type_id}")
async def delete_form_type(type_id: str, request: Request):
    await _require_auth(request)
    result = await _db.bb_form_types.delete_one({"_id": _oid(type_id)})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Not found")
    return {"success": True}


# ============ HIRING FORMS ============

class ConditionsBody(BaseModel):
    age_min: Optional[int] = None
    age_max: Optional[int] = None
    grad_year_min: Optional[int] = None
    grad_year_max: Optional[int] = None
    locations: Optional[List[str]] = None
    location_change: Optional[str] = "NA"
    attend_in_person: Optional[str] = "NA"
    college_limit: Optional[str] = "Both"

class HiringFormCreate(BaseModel):
    name: str
    form_type_id: str
    job_role: str
    conditions: Optional[ConditionsBody] = None
    job_description_attached: Optional[bool] = False
    job_opening_id: Optional[str] = None

class HiringFormUpdate(BaseModel):
    name: Optional[str] = None
    form_type_id: Optional[str] = None
    job_role: Optional[str] = None
    conditions: Optional[ConditionsBody] = None
    job_description_attached: Optional[bool] = None
    job_opening_id: Optional[str] = None

@bb_router.get("/hiring-forms")
async def list_hiring_forms(request: Request):
    await _require_auth(request)
    forms = await _db.bb_hiring_forms.find({}).sort("created_at", -1).to_list(None)
    for f in forms:
        f["id"] = str(f.pop("_id"))
    return {"forms": forms}

@bb_router.post("/hiring-forms")
async def create_hiring_form(data: HiringFormCreate, request: Request):
    await _require_auth(request)
    ft = await _db.bb_form_types.find_one({"_id": _oid(data.form_type_id)})
    if not ft:
        raise HTTPException(status_code=400, detail="Form type not found")
    cond = data.conditions.dict() if data.conditions else {}
    if cond.get("locations"):
        cond["locations"] = [l.strip() for l in cond["locations"] if l.strip()]
    doc = {
        "name": data.name.strip(), "form_type_id": data.form_type_id,
        "form_type_name": ft["name"], "job_role": data.job_role.strip(),
        "conditions": cond,
        "job_description_attached": data.job_description_attached or False,
        "job_opening_id": data.job_opening_id or None,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    result = await _db.bb_hiring_forms.insert_one(doc)
    doc["id"] = str(result.inserted_id)
    doc.pop("_id", None)
    return {"success": True, "form": doc}

@bb_router.put("/hiring-forms/{form_id}")
async def update_hiring_form(form_id: str, data: HiringFormUpdate, request: Request):
    await _require_auth(request)
    oid = _oid(form_id)
    updates = {"updated_at": datetime.now(timezone.utc).isoformat()}
    if data.name is not None:
        updates["name"] = data.name.strip()
    if data.job_role is not None:
        updates["job_role"] = data.job_role.strip()
    if data.form_type_id is not None:
        ft = await _db.bb_form_types.find_one({"_id": _oid(data.form_type_id)})
        if not ft:
            raise HTTPException(status_code=400, detail="Form type not found")
        updates["form_type_id"] = data.form_type_id
        updates["form_type_name"] = ft["name"]
    if data.conditions is not None:
        cond = data.conditions.dict()
        if cond.get("locations"):
            cond["locations"] = [l.strip() for l in cond["locations"] if l.strip()]
        updates["conditions"] = cond
    if data.job_description_attached is not None:
        updates["job_description_attached"] = data.job_description_attached
    if data.job_opening_id is not None:
        updates["job_opening_id"] = data.job_opening_id
    result = await _db.bb_hiring_forms.update_one({"_id": oid}, {"$set": updates})
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Not found")
    return {"success": True}

@bb_router.delete("/hiring-forms/{form_id}")
async def delete_hiring_form(form_id: str, request: Request):
    await _require_auth(request)
    result = await _db.bb_hiring_forms.delete_one({"_id": _oid(form_id)})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Not found")
    return {"success": True}


# ============ ROUNDS ============

class RoundBody(BaseModel):
    name: str

@bb_router.get("/rounds")
async def list_rounds(request: Request):
    await _require_auth(request)
    rounds = await _db.bb_rounds.find({}).sort("name", 1).to_list(None)
    for r in rounds:
        r["id"] = str(r.pop("_id"))
    return {"rounds": rounds}

@bb_router.post("/rounds")
async def create_round(data: RoundBody, request: Request):
    await _require_auth(request)
    name = data.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Name required")
    doc = {"name": name, "created_at": datetime.now(timezone.utc).isoformat()}
    result = await _db.bb_rounds.insert_one(doc)
    return {"success": True, "id": str(result.inserted_id), "name": name}

@bb_router.put("/rounds/{round_id}")
async def update_round(round_id: str, data: RoundBody, request: Request):
    await _require_auth(request)
    result = await _db.bb_rounds.update_one({"_id": _oid(round_id)}, {"$set": {"name": data.name.strip()}})
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Not found")
    return {"success": True}

@bb_router.delete("/rounds/{round_id}")
async def delete_round(round_id: str, request: Request):
    await _require_auth(request)
    result = await _db.bb_rounds.delete_one({"_id": _oid(round_id)})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Not found")
    return {"success": True}


# ============ JOB OPENINGS ============

class JobOpeningCreate(BaseModel):
    title: str
    job_role: Optional[str] = ""
    vacancies: Optional[int] = None
    years_of_graduation: Optional[List[str]] = None
    education: Optional[List[str]] = None
    salary_range: Optional[str] = ""
    key_responsibilities: Optional[str] = ""
    added_advantages: Optional[str] = ""
    what_we_offer: Optional[str] = ""

class JobOpeningUpdate(BaseModel):
    title: Optional[str] = None
    job_role: Optional[str] = None
    vacancies: Optional[int] = None
    years_of_graduation: Optional[List[str]] = None
    education: Optional[List[str]] = None
    salary_range: Optional[str] = None
    key_responsibilities: Optional[str] = None
    added_advantages: Optional[str] = None
    what_we_offer: Optional[str] = None

@bb_router.get("/job-openings")
async def list_job_openings(request: Request):
    await _require_auth(request)
    openings = await _db.bb_job_openings.find({}).sort("created_at", -1).to_list(None)
    for o in openings:
        o["id"] = str(o.pop("_id"))
    return {"openings": openings}

@bb_router.post("/job-openings")
async def create_job_opening(data: JobOpeningCreate, request: Request):
    await _require_auth(request)
    doc = {"title": data.title.strip(), "job_role": (data.job_role or "").strip(),
           "vacancies": data.vacancies, "years_of_graduation": data.years_of_graduation or [],
           "education": data.education or [], "salary_range": (data.salary_range or "").strip(),
           "key_responsibilities": (data.key_responsibilities or "").strip(),
           "added_advantages": (data.added_advantages or "").strip(),
           "what_we_offer": (data.what_we_offer or "").strip(),
           "created_at": datetime.now(timezone.utc).isoformat(), "updated_at": datetime.now(timezone.utc).isoformat()}
    result = await _db.bb_job_openings.insert_one(doc)
    return {"success": True, "id": str(result.inserted_id)}

@bb_router.put("/job-openings/{opening_id}")
async def update_job_opening(opening_id: str, data: JobOpeningUpdate, request: Request):
    await _require_auth(request)
    updates = {"updated_at": datetime.now(timezone.utc).isoformat()}
    for field in ["title", "job_role", "salary_range", "key_responsibilities", "added_advantages", "what_we_offer"]:
        val = getattr(data, field, None)
        if val is not None:
            updates[field] = val.strip()
    if data.vacancies is not None:
        updates["vacancies"] = data.vacancies
    if data.years_of_graduation is not None:
        updates["years_of_graduation"] = data.years_of_graduation
    if data.education is not None:
        updates["education"] = data.education
    result = await _db.bb_job_openings.update_one({"_id": _oid(opening_id)}, {"$set": updates})
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Not found")
    return {"success": True}

@bb_router.delete("/job-openings/{opening_id}")
async def delete_job_opening(opening_id: str, request: Request):
    await _require_auth(request)
    result = await _db.bb_job_openings.delete_one({"_id": _oid(opening_id)})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Not found")
    return {"success": True}


# ============ INTERVIEW SCHEDULE REPORTS ============

@bb_router.get("/interview-reports")
async def get_interview_reports(
    request: Request,
    startDate: str = Query(None), endDate: str = Query(None),
    jobRole: str = Query(None), attendance: str = Query(None),
    collegeType: str = Query(None),
    page: int = Query(1, ge=1), limit: int = Query(100, ge=1, le=500),
):
    await _require_auth(request)
    match = {"schedule_date": {"$nin": [None, ""], "$exists": True},
             "schedule_time": {"$nin": [None, ""], "$exists": True}}
    if startDate:
        match["schedule_date"] = {**match["schedule_date"], "$gte": startDate}
    if endDate:
        match["schedule_date"] = {**match["schedule_date"], "$lte": endDate}

    all_docs = await _db.registered_candidates.find(match, {"_id": 0}).sort("schedule_date", -1).to_list(None)
    rank_lookup = await _build_college_rank_lookup_fn()

    rows = []
    role_counts = {}
    attended_count = 0
    not_attended_count = 0
    premium_count = 0
    non_premium_count = 0

    for doc in all_docs:
        cc = _classify_college_fn(doc, rank_lookup)
        is_nirf = cc["college_status"].startswith("NIRF")
        college_type = "Premium College" if is_nirf else "Non Premium College"
        otp = str(doc.get("otp_verified") or "").strip()
        att_status = "Attended" if otp else "Not Attended"
        role = doc.get("job_role") or doc.get("job_title") or "-"

        if jobRole and jobRole.strip().lower() not in ("", "all"):
            if role.lower() != jobRole.strip().lower():
                continue
        if attendance and attendance.strip().lower() not in ("", "all"):
            target = attendance.strip().lower().replace(" ", "")
            if att_status.lower().replace(" ", "") != target:
                continue
        if collegeType and collegeType.strip().lower() not in ("", "all"):
            if "premium" in collegeType.strip().lower() and "non" not in collegeType.strip().lower() and not is_nirf:
                continue
            if "non" in collegeType.strip().lower() and is_nirf:
                continue

        role_counts[role] = role_counts.get(role, 0) + 1
        if att_status == "Attended":
            attended_count += 1
        else:
            not_attended_count += 1
        if is_nirf:
            premium_count += 1
        else:
            non_premium_count += 1

        rows.append({"name": doc.get("name") or "-", "email": doc.get("email") or "-",
                      "date": doc.get("schedule_date") or "-", "time": doc.get("schedule_time") or "-",
                      "job_role": role, "college_type": college_type, "attendance": att_status})

    total = len(rows)
    start_idx = (page - 1) * limit
    return {
        "data": rows[start_idx:start_idx + limit], "total": total, "page": page, "limit": limit,
        "summary": {"role_counts": role_counts, "attended": attended_count, "not_attended": not_attended_count,
                     "premium_colleges": premium_count, "non_premium_colleges": non_premium_count}
    }


# ============ UPDATE APPLICANT SCORES ============

class ScoreEntry(BaseModel):
    round_name: str
    score: float

class ApplicantScoreUpdate(BaseModel):
    status: str
    scores: Optional[List[ScoreEntry]] = None

@bb_router.get("/attended-for-scores")
async def get_attended_for_scores(request: Request, startDate: str = Query(None), endDate: str = Query(None)):
    await _require_auth(request)
    match = {"otp_verified": {"$nin": [None, ""], "$exists": True},
             "schedule_date": {"$nin": [None, ""], "$exists": True}}
    if startDate:
        match["schedule_date"] = {**match.get("schedule_date", {}), "$gte": startDate}
    if endDate:
        match["schedule_date"] = {**match.get("schedule_date", {}), "$lte": endDate}

    docs = await _db.registered_candidates.find(match, {"_id": 0, "email": 1, "phone": 1, "name": 1,
        "schedule_date": 1, "job_role": 1, "job_title": 1, "result_status": 1}).sort("schedule_date", -1).to_list(None)

    updates = await _db.bb_applicant_updates.find({}, {"_id": 0}).to_list(None)
    update_map = {u["email"]: u for u in updates if u.get("email")}

    result = []
    for doc in docs:
        email = doc.get("email") or ""
        upd = update_map.get(email, {})
        result.append({"name": doc.get("name") or "-", "email": email, "phone": doc.get("phone") or "-",
                        "date_of_interview": doc.get("schedule_date") or "-",
                        "job_role": doc.get("job_role") or doc.get("job_title") or "-",
                        "status": upd.get("status") or doc.get("result_status") or "On hold",
                        "scores": upd.get("scores", [])})
    return {"data": result}

@bb_router.put("/applicant-score/{email:path}")
async def update_applicant_score(email: str, data: ApplicantScoreUpdate, request: Request):
    await _require_auth(request)
    if not email:
        raise HTTPException(status_code=400, detail="Email required")
    update_doc = {"email": email, "status": data.status, "updated_at": datetime.now(timezone.utc).isoformat()}
    if data.scores:
        update_doc["scores"] = [{"round_name": s.round_name, "score": s.score} for s in data.scores]
    await _db.bb_applicant_updates.update_one({"email": email}, {"$set": update_doc}, upsert=True)
    await _db.registered_candidates.update_many({"email": email}, {"$set": {"result_status": data.status}})
    return {"success": True}


@bb_router.post("/import-scores")
async def import_scores(request: Request):
    """Import applicant scores from uploaded CSV file."""
    await _require_auth(request)
    from fastapi import UploadFile, File
    form = await request.form()
    file = form.get("file")
    if not file:
        raise HTTPException(status_code=400, detail="No file uploaded")
    content = await file.read()
    import io, csv
    text = content.decode("utf-8", errors="ignore")
    reader = csv.DictReader(io.StringIO(text))
    imported = 0
    for row in reader:
        email = (row.get("email") or row.get("EMAIL") or "").strip().lower()
        status = row.get("status") or row.get("STATUS") or "On hold"
        if email:
            await _db.bb_applicant_updates.update_one(
                {"email": email},
                {"$set": {"email": email, "status": status, "updated_at": datetime.now(timezone.utc).isoformat()}},
                upsert=True
            )
            imported += 1
    return {"success": True, "imported": imported}


# ============ HOLIDAYS ============

class HolidayBody(BaseModel):
    name: str
    date: str

@bb_router.get("/holidays")
async def list_holidays(request: Request):
    await _require_auth(request)
    docs = await _db.bb_holidays.find({}).sort("date", 1).to_list(None)
    for d in docs:
        d["id"] = str(d.pop("_id"))
    return {"holidays": docs}

@bb_router.post("/holidays")
async def create_holiday(data: HolidayBody, request: Request):
    await _require_auth(request)
    doc = {"name": data.name.strip(), "date": data.date.strip(), "created_at": datetime.now(timezone.utc).isoformat()}
    result = await _db.bb_holidays.insert_one(doc)
    return {"success": True, "id": str(result.inserted_id)}

@bb_router.put("/holidays/{holiday_id}")
async def update_holiday(holiday_id: str, data: HolidayBody, request: Request):
    await _require_auth(request)
    result = await _db.bb_holidays.update_one({"_id": _oid(holiday_id)}, {"$set": {"name": data.name.strip(), "date": data.date.strip()}})
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Not found")
    return {"success": True}

@bb_router.delete("/holidays/{holiday_id}")
async def delete_holiday(holiday_id: str, request: Request):
    await _require_auth(request)
    result = await _db.bb_holidays.delete_one({"_id": _oid(holiday_id)})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Not found")
    return {"success": True}


# ============ VERIFY APPLICANT OTP ============

class OTPVerifyBody(BaseModel):
    phone: str
    otp: str

@bb_router.post("/verify-otp")
async def verify_applicant_otp(data: OTPVerifyBody, request: Request):
    await _require_auth(request)
    phone = re.sub(r'[^\d]', '', data.phone.strip())
    if len(phone) > 10:
        phone = phone[-10:]
    otp_val = data.otp.strip()
    if not phone or not otp_val:
        raise HTTPException(status_code=400, detail="Phone and OTP required")
    # Find applicant in bb_registrations by phone + otp
    applicant = await _db.bb_registrations.find_one({"phone": phone, "otp": otp_val, "otp_expired": {"$in": [None, ""]}})
    if not applicant:
        return {"success": False, "message": "Invalid OTP !"}
    # Mark as verified
    await _db.bb_registrations.update_one({"_id": applicant["_id"]}, {"$set": {"otp_verified": True, "status": "Attended"}})
    # Also update registered_candidates if matched
    await _db.registered_candidates.update_many(
        {"$or": [{"phone": phone}, {"email": applicant.get("email", "")}]},
        {"$set": {"otp_verified": "1"}}
    )
    return {"success": True, "message": "Applicant Successfully Verified !"}


# ============ PUBLIC ENDPOINTS (NO AUTH) ============

def _generate_token(email: str) -> str:
    """Generate a unique token for interview scheduling link."""
    return hashlib.sha256(f"{email}:{secrets.token_hex(8)}".encode()).hexdigest()[:24]

def _generate_otp() -> str:
    """Generate a 6-digit OTP."""
    import random
    return str(random.randint(100000, 999999))

class RegistrationBody(BaseModel):
    form_id: str
    full_name: str
    email: str
    phone: str
    age: Optional[int] = None
    current_location_state: Optional[str] = ""
    preferred_location_city: Optional[str] = ""
    year_of_graduation: Optional[int] = None
    degree: Optional[str] = ""
    course: Optional[str] = ""
    college: Optional[str] = ""
    location_change: Optional[str] = None
    attend_in_person: Optional[str] = None

@pub_router.get("/form/{form_id}")
async def get_public_form(form_id: str):
    """Get form details for public registration (no auth)."""
    form = await _db.bb_hiring_forms.find_one({"_id": _oid(form_id)})
    if not form:
        raise HTTPException(status_code=404, detail="Form not found")
    result = {
        "id": str(form["_id"]),
        "name": form.get("name", ""),
        "job_role": form.get("job_role", ""),
        "form_type_name": form.get("form_type_name", ""),
        "conditions": form.get("conditions", {}),
        "job_description_attached": form.get("job_description_attached", False),
        "job_opening_id": form.get("job_opening_id"),
    }
    # If job description attached, fetch the job opening
    if result["job_description_attached"] and result.get("job_opening_id"):
        opening = await _db.bb_job_openings.find_one({"_id": _oid(result["job_opening_id"])})
        if opening:
            result["job_opening"] = {
                "title": opening.get("title", ""),
                "job_role": opening.get("job_role", ""),
                "vacancies": opening.get("vacancies"),
                "years_of_graduation": opening.get("years_of_graduation", []),
                "education": opening.get("education", []),
                "salary_range": opening.get("salary_range", ""),
                "key_responsibilities": opening.get("key_responsibilities", ""),
                "added_advantages": opening.get("added_advantages", ""),
                "what_we_offer": opening.get("what_we_offer", ""),
            }
    return result

@pub_router.post("/register")
async def register_applicant(data: RegistrationBody):
    """Public registration — no auth. Checks shortlist conditions and stores applicant."""
    form = await _db.bb_hiring_forms.find_one({"_id": _oid(data.form_id)})
    if not form:
        raise HTTPException(status_code=404, detail="Form not found")

    cond = form.get("conditions", {})
    job_role = form.get("job_role", "")

    # Auto-shortlisting check
    rejected_reasons = []

    # Age limit
    if cond.get("age_min") is not None and data.age is not None:
        if data.age < cond["age_min"]:
            rejected_reasons.append("Age below minimum")
    if cond.get("age_max") is not None and data.age is not None:
        if data.age > cond["age_max"]:
            rejected_reasons.append("Age above maximum")

    # Graduation year limit
    if cond.get("grad_year_min") is not None and data.year_of_graduation is not None:
        if data.year_of_graduation < cond["grad_year_min"]:
            rejected_reasons.append("Graduation year below minimum")
    if cond.get("grad_year_max") is not None and data.year_of_graduation is not None:
        if data.year_of_graduation > cond["grad_year_max"]:
            rejected_reasons.append("Graduation year above maximum")

    # Location limit
    location_mismatch = False
    allowed_locations = [l.strip().lower() for l in (cond.get("locations") or []) if l.strip()]
    preferred_city = (data.preferred_location_city or "").strip().lower()
    if allowed_locations and preferred_city:
        if preferred_city not in allowed_locations:
            location_mismatch = True
            # Check location_change and attend_in_person only when location doesn't match
            valid_loc_change = cond.get("location_change", "NA")
            if valid_loc_change != "NA":
                user_choice = (data.location_change or "").strip()
                if user_choice != valid_loc_change:
                    rejected_reasons.append(f"Location change: required {valid_loc_change}, got {user_choice}")

            valid_attend = cond.get("attend_in_person", "NA")
            if valid_attend != "NA":
                user_choice = (data.attend_in_person or "").strip()
                if user_choice != valid_attend:
                    rejected_reasons.append(f"Attend in person: required {valid_attend}, got {user_choice}")

    # College limit (NIRF check)
    college_limit = cond.get("college_limit", "Both")
    if college_limit != "Both" and data.college:
        rank_lookup = await _build_college_rank_lookup_fn()
        from bb_modules import _classify_college_fn
        cc = _classify_college_fn({"ug_university": data.college, "pg_university": ""}, rank_lookup)
        is_nirf = cc["college_status"].startswith("NIRF")
        if college_limit == "NIRF" and not is_nirf:
            rejected_reasons.append("College not NIRF ranked")
        elif college_limit == "Non NIRF" and is_nirf:
            rejected_reasons.append("College is NIRF (Non NIRF required)")

    is_shortlisted = len(rejected_reasons) == 0
    status = "Interview Not Scheduled" if is_shortlisted else "Rejected"

    # Generate schedule token for shortlisted
    schedule_token = _generate_token(data.email) if is_shortlisted else None

    # Store registration
    phone_normalized = re.sub(r'[^\d]', '', data.phone.strip())
    if len(phone_normalized) > 10:
        phone_normalized = phone_normalized[-10:]

    reg_doc = {
        "form_id": data.form_id,
        "form_name": form.get("name", ""),
        "job_role": job_role,
        "full_name": data.full_name.strip(),
        "email": data.email.strip().lower(),
        "phone": phone_normalized,
        "age": data.age,
        "current_location_state": (data.current_location_state or "").strip(),
        "preferred_location_city": (data.preferred_location_city or "").strip(),
        "year_of_graduation": data.year_of_graduation,
        "degree": (data.degree or "").strip(),
        "course": (data.course or "").strip(),
        "college": (data.college or "").strip(),
        "location_change": data.location_change,
        "attend_in_person": data.attend_in_person,
        "status": status,
        "is_shortlisted": is_shortlisted,
        "rejected_reasons": rejected_reasons,
        "schedule_token": schedule_token,
        "otp": None,
        "otp_verified": False,
        "otp_expired": None,
        "schedule_date": None,
        "schedule_time": None,
        "reschedule_count": 0,
        "registered_at": datetime.now(timezone.utc).isoformat(),
    }
    await _db.bb_registrations.insert_one(reg_doc)

    # Also insert into registered_candidates for Analytics Dashboard integration
    rc_doc = {
        "name": data.full_name.strip(),
        "email": data.email.strip().lower(),
        "phone": phone_normalized,
        "job_title": job_role,
        "job_role": job_role,
        "email_type": "shortlist" if is_shortlisted else "reject",
        "degree": (data.degree or "").strip(),
        "course": (data.course or "").strip(),
        "ug_university": (data.college or "").strip(),
        "pg_university": "",
        "year_of_graduation": str(data.year_of_graduation) if data.year_of_graduation else "",
        "date_of_application": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "last_update": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "schedule_date": "",
        "schedule_time": "",
        "otp_verified": "",
        "result_status": "",
        "source": "registration_form",
    }
    await _db.registered_candidates.insert_one(rc_doc)

    # Email/WhatsApp STUBBED — status updates happen, no messages sent
    return {
        "success": True,
        "status": status,
        "is_shortlisted": is_shortlisted,
        "schedule_token": schedule_token,
        "rejected_reasons": rejected_reasons,
    }


@pub_router.get("/schedule/{token}")
async def get_schedule_info(token: str):
    """Get applicant info for interview scheduling (public, via unique token)."""
    reg = await _db.bb_registrations.find_one({"schedule_token": token})
    if not reg:
        raise HTTPException(status_code=404, detail="Invalid or expired link")
    # Get holidays
    holidays = await _db.bb_holidays.find({}, {"_id": 0, "date": 1}).to_list(None)
    holiday_dates = [h["date"] for h in holidays]

    return {
        "name": reg.get("full_name", ""),
        "email": reg.get("email", ""),
        "phone": reg.get("phone", ""),
        "already_scheduled": bool(reg.get("schedule_date")),
        "schedule_date": reg.get("schedule_date"),
        "schedule_time": reg.get("schedule_time"),
        "reschedule_count": reg.get("reschedule_count", 0),
        "holidays": holiday_dates,
    }


class ScheduleBody(BaseModel):
    date: str
    time: str

@pub_router.post("/schedule/{token}")
async def schedule_interview(token: str, data: ScheduleBody):
    """Schedule or reschedule interview (public, via unique token)."""
    reg = await _db.bb_registrations.find_one({"schedule_token": token})
    if not reg:
        raise HTTPException(status_code=404, detail="Invalid or expired link")

    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    is_reschedule = bool(reg.get("schedule_date"))

    updates = {
        "schedule_date": data.date.strip(),
        "schedule_time": data.time.strip(),
        "status": "Interview Scheduled",
        "last_update": now_str,
    }
    if is_reschedule:
        updates["reschedule_count"] = reg.get("reschedule_count", 0) + 1

    # Generate OTP for the applicant
    otp = _generate_otp()
    updates["otp"] = otp

    await _db.bb_registrations.update_one({"_id": reg["_id"]}, {"$set": updates})

    # Update registered_candidates for Analytics Dashboard integration
    email = reg.get("email", "")
    phone = reg.get("phone", "")
    # Convert time to 24h format for storage
    time_24 = data.time.strip()
    await _db.registered_candidates.update_many(
        {"$or": [{"email": email}, {"phone": phone}]},
        {"$set": {
            "schedule_date": data.date.strip(),
            "schedule_time": time_24,
            "last_update": now_str,
            "email_type": "shortlist",
        }}
    )

    # Email/WhatsApp STUBBED — no messages sent
    return {"success": True, "is_reschedule": is_reschedule, "otp": otp}
