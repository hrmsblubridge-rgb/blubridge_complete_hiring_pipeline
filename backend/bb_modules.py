"""BluBridge Modules — New features for the Hiring Pipeline.
Separate router to avoid modifying existing server.py logic."""

from fastapi import APIRouter, HTTPException, Request, Query
from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime, timezone
from bson import ObjectId
import hashlib, secrets, re, logging, uuid

bb_router = APIRouter(prefix="/api/bb")
# Public router — no auth prefix
pub_router = APIRouter(prefix="/api/pub")

_logger = logging.getLogger("bb_modules")


# ============ MESSAGING — Delegated to messaging.py ============
# All recipient overrides (TEST_MODE) happen in messaging.py centrally.
# No direct messaging logic in this file.

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
    """Interview Schedule Reports — OPTIMIZED (May 2026).
    Filters and summary counts are computed at the DB level using the persisted
    derived fields `_nirf_category` and `_normalized_job_role`. Returns
    {data, total, page, limit, totalPages, summary}.
    """
    await _require_auth(request)

    # Base match: only candidates with a schedule
    match = {
        "schedule_date": {"$nin": [None, ""], "$exists": True},
        "schedule_time": {"$nin": [None, ""], "$exists": True},
    }
    if startDate or endDate:
        sd = {"$nin": [None, ""], "$exists": True}
        if startDate:
            sd["$gte"] = startDate
        if endDate:
            sd["$lte"] = endDate
        match["schedule_date"] = sd

    # Job role filter → persisted _normalized_job_role (case-insensitive exact)
    if jobRole and jobRole.strip().lower() not in ("", "all"):
        match["_normalized_job_role"] = {
            "$regex": f"^{re.escape(jobRole.strip())}$", "$options": "i"
        }

    # College type filter → persisted _nirf_category
    if collegeType and collegeType.strip().lower() not in ("", "all"):
        ct = collegeType.strip().lower()
        if "non" in ct:
            match["_nirf_category"] = "Non NIRF"
        elif "premium" in ct:
            match["_nirf_category"] = "NIRF"

    # Attendance filter → otp_verified presence
    if attendance and attendance.strip().lower() not in ("", "all"):
        att = attendance.strip().lower().replace(" ", "")
        if att == "attended":
            match["otp_verified"] = {"$nin": [None, ""], "$exists": True}
        elif att == "notattended":
            match["$or"] = [
                {"otp_verified": {"$in": [None, ""]}},
                {"otp_verified": {"$exists": False}},
            ]

    # Total + paginated page (DB-level)
    total = await _db.registered_candidates.count_documents(match)
    skip = (page - 1) * limit
    pipeline = [
        {"$match": match},
        {"$sort": {"schedule_date": -1, "schedule_time": -1}},
        {"$skip": skip},
        {"$limit": limit},
        {"$project": {
            "_id": 0, "name": 1, "email": 1,
            "schedule_date": 1, "schedule_time": 1,
            "job_title": 1, "job_role": 1, "_normalized_job_role": 1,
            "_nirf_category": 1, "otp_verified": 1,
        }},
    ]
    docs = await _db.registered_candidates.aggregate(pipeline, allowDiskUse=False).to_list(None)

    rows = []
    for d in docs:
        is_nirf = (d.get("_nirf_category") or "Non NIRF") == "NIRF"
        otp = str(d.get("otp_verified") or "").strip()
        rows.append({
            "name": d.get("name") or "-",
            "email": d.get("email") or "-",
            "date": d.get("schedule_date") or "-",
            "time": d.get("schedule_time") or "-",
            "job_role": d.get("_normalized_job_role") or d.get("job_role") or d.get("job_title") or "-",
            "college_type": "Premium College" if is_nirf else "Non Premium College",
            "attendance": "Attended" if otp else "Not Attended",
        })

    # Summary (aggregated over the filtered set — ALL rows, not just this page)
    summary_pipeline = [
        {"$match": match},
        {"$group": {
            "_id": None,
            "attended": {"$sum": {"$cond": [
                {"$and": [
                    {"$ne": [{"$ifNull": ["$otp_verified", ""]}, ""]},
                    {"$ne": [{"$ifNull": ["$otp_verified", None]}, None]},
                ]}, 1, 0
            ]}},
            "not_attended": {"$sum": {"$cond": [
                {"$or": [
                    {"$eq": [{"$ifNull": ["$otp_verified", ""]}, ""]},
                    {"$eq": [{"$ifNull": ["$otp_verified", None]}, None]},
                ]}, 1, 0
            ]}},
            "premium_colleges": {"$sum": {"$cond": [
                {"$eq": [{"$ifNull": ["$_nirf_category", "Non NIRF"]}, "NIRF"]}, 1, 0
            ]}},
            "non_premium_colleges": {"$sum": {"$cond": [
                {"$ne": [{"$ifNull": ["$_nirf_category", "Non NIRF"]}, "NIRF"]}, 1, 0
            ]}},
        }},
    ]
    sres = await _db.registered_candidates.aggregate(summary_pipeline, allowDiskUse=False).to_list(None)
    base = sres[0] if sres else {"attended": 0, "not_attended": 0, "premium_colleges": 0, "non_premium_colleges": 0}

    # Role counts per filter set
    role_pipeline = [
        {"$match": match},
        {"$group": {
            "_id": {"$ifNull": ["$_normalized_job_role", "Unknown"]},
            "count": {"$sum": 1},
        }},
        {"$sort": {"count": -1}},
        {"$limit": 100},
    ]
    role_results = await _db.registered_candidates.aggregate(role_pipeline, allowDiskUse=False).to_list(None)
    role_counts = {r["_id"]: r["count"] for r in role_results}

    total_pages = (total + limit - 1) // limit if total else 1
    return {
        "data": rows,
        "total": total,
        "page": page,
        "limit": limit,
        "totalPages": total_pages,
        "summary": {
            "role_counts": role_counts,
            "attended": base.get("attended", 0),
            "not_attended": base.get("not_attended", 0),
            "premium_colleges": base.get("premium_colleges", 0),
            "non_premium_colleges": base.get("non_premium_colleges", 0),
        },
    }


# ============ UPDATE APPLICANT SCORES ============

class ScoreEntry(BaseModel):
    round_name: str
    score: float

class ApplicantScoreUpdate(BaseModel):
    status: str
    scores: Optional[List[ScoreEntry]] = None

@bb_router.get("/attended-for-scores")
async def get_attended_for_scores(
    request: Request,
    startDate: str = Query(None),
    endDate: str = Query(None),
    page: int = Query(1, ge=1),
    limit: int = Query(100, ge=1, le=500),
):
    """Update Applicants Scores — with pagination (May 2026).
    Returns {data, total, page, limit, totalPages, available_rounds}.
    `available_rounds` always reflects the full score_sheet set (global filter).
    """
    await _require_auth(request)
    match = {"otp_verified": {"$nin": [None, ""], "$exists": True},
             "schedule_date": {"$nin": [None, ""], "$exists": True}}
    if startDate:
        match["schedule_date"] = {**match.get("schedule_date", {}), "$gte": startDate}
    if endDate:
        match["schedule_date"] = {**match.get("schedule_date", {}), "$lte": endDate}

    # Total + DB-level pagination
    total = await _db.registered_candidates.count_documents(match)
    skip = (page - 1) * limit
    pipeline = [
        {"$match": match},
        {"$sort": {"schedule_date": -1}},
        {"$skip": skip},
        {"$limit": limit},
        {"$project": {
            "_id": 0, "email": 1, "phone": 1, "name": 1,
            "schedule_date": 1, "job_role": 1, "job_title": 1,
            "result_status": 1,
        }},
    ]
    docs = await _db.registered_candidates.aggregate(pipeline, allowDiskUse=False).to_list(None)

    # Page-scoped status overrides
    page_emails = [(d.get("email") or "").strip().lower() for d in docs if d.get("email")]
    updates = await _db.bb_applicant_updates.find(
        {"email": {"$in": page_emails}} if page_emails else {"_id": None}, {"_id": 0}
    ).to_list(None) if page_emails else []
    update_map = {u["email"]: u for u in updates if u.get("email")}

    # Scores for the current page only
    page_phones = []
    for d in docs:
        p = re.sub(r'[^\d]', '', d.get("phone") or "")
        if len(p) > 10:
            p = p[-10:]
        if p:
            page_phones.append(p)
    score_q = []
    if page_emails:
        score_q.append({"email": {"$in": page_emails}})
    if page_phones:
        score_q.append({"phone": {"$in": page_phones}})
    score_records = []
    if score_q:
        score_records = await _db.score_sheet.find(
            {"$or": score_q} if len(score_q) > 1 else score_q[0], {"_id": 0}
        ).to_list(None)

    score_by_email = {}
    score_by_phone = {}
    for sr in score_records:
        se = (sr.get("email") or "").strip().lower()
        sp = re.sub(r'[^\d]', '', sr.get("phone") or "")
        if len(sp) > 10:
            sp = sp[-10:]
        if se:
            score_by_email.setdefault(se, []).append(sr)
        if sp:
            score_by_phone.setdefault(sp, []).append(sr)

    # Available rounds (GLOBAL — unchanged contract): distinct names from score_sheet
    available_rounds = await _db.score_sheet.distinct("round_name")
    available_rounds = sorted([r for r in available_rounds if r])

    result = []
    for doc in docs:
        email = (doc.get("email") or "").strip().lower()
        phone = re.sub(r'[^\d]', '', doc.get("phone") or "")
        if len(phone) > 10:
            phone = phone[-10:]
        upd = update_map.get(email, {})

        merged_scores = []
        if upd.get("scores"):
            merged_scores = upd["scores"]
        else:
            matched = []
            if email and email in score_by_email:
                matched.extend(score_by_email[email])
            if phone and phone in score_by_phone:
                for s in score_by_phone[phone]:
                    if s not in matched:
                        matched.append(s)
            for sr in matched:
                rn = (sr.get("round_name") or "").strip()
                sc = sr.get("score", 0)
                if rn:
                    merged_scores.append({"round_name": rn, "score": sc})

        result.append({"name": doc.get("name") or "-", "email": email, "phone": doc.get("phone") or "-",
                        "date_of_interview": doc.get("schedule_date") or "-",
                        "job_role": doc.get("job_role") or doc.get("job_title") or "-",
                        "status": upd.get("status") or doc.get("result_status") or "On hold",
                        "scores": merged_scores})

    total_pages = (total + limit - 1) // limit if total else 1
    return {
        "data": result,
        "total": total,
        "page": page,
        "limit": limit,
        "totalPages": total_pages,
        "available_rounds": available_rounds,
    }

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


@bb_router.post("/import-scores/preview")
async def import_scores_preview(request: Request):
    """STEP 1 of 2 — Parse uploaded CSV/XLSX and return rows for user preview.
    Does NOT write to DB. Use POST /import-scores/confirm to commit.
    Expected columns (in order):
      Name, Schedule Date, College, Degree, Course, Year of Graduation,
      Email, Phone, Job Role, Status, <round columns alphabetical...>
    """
    await _require_auth(request)
    form = await request.form()
    file = form.get("file")
    if not file:
        raise HTTPException(status_code=400, detail="No file uploaded")
    content = await file.read()
    filename = (getattr(file, "filename", "") or "").lower()

    rows, headers = _parse_score_file(content, filename)
    fixed = ["Name", "Schedule Date", "College", "Degree", "Course",
             "Year of Graduation", "Email", "Phone", "Job Role", "Status"]
    missing = [h for h in fixed if h not in headers]
    if missing:
        raise HTTPException(status_code=400, detail=f"Invalid file: missing columns {missing}")
    round_cols = [h for h in headers if h not in fixed]

    parsed = []
    errors = []
    for idx, row in enumerate(rows, start=2):  # start=2 because row 1 is header
        email = str(row.get("Email", "") or "").strip().lower()
        if not email:
            errors.append({"row": idx, "error": "Missing Email"})
            continue
        scores = []
        for r in round_cols:
            v = str(row.get(r, "") or "").strip()
            if v == "" or v == "-":
                continue
            try:
                scores.append({"round_name": r, "score": float(v)})
            except (TypeError, ValueError):
                errors.append({"row": idx, "error": f"Invalid score for {r}: '{v}'"})
        parsed.append({
            "name": str(row.get("Name", "") or "").strip(),
            "schedule_date": str(row.get("Schedule Date", "") or "").strip(),
            "college": str(row.get("College", "") or "").strip(),
            "degree": str(row.get("Degree", "") or "").strip(),
            "course": str(row.get("Course", "") or "").strip(),
            "year_of_graduation": str(row.get("Year of Graduation", "") or "").strip(),
            "email": email,
            "phone": str(row.get("Phone", "") or "").strip(),
            "job_role": str(row.get("Job Role", "") or "").strip(),
            "status": str(row.get("Status", "") or "On hold").strip() or "On hold",
            "scores": scores,
        })

    return {
        "rows": parsed,
        "round_columns": sorted(round_cols),
        "errors": errors,
        "total": len(parsed),
    }


@bb_router.post("/import-scores/confirm")
async def import_scores_confirm(data: dict, request: Request):
    """STEP 2 of 2 — Commit previewed rows. Tags every record with
    `isImported:true`, `import_batch_id`, `imported_at` so the 7 PM rejection
    mailer can target ONLY this batch (never legacy DB records)."""
    await _require_auth(request)
    rows = data.get("rows", [])
    if not isinstance(rows, list) or not rows:
        raise HTTPException(status_code=400, detail="No rows provided")

    batch_id = str(uuid.uuid4())
    now_iso = datetime.now(timezone.utc).isoformat()
    imported = 0
    for r in rows:
        email = str(r.get("email", "") or "").strip().lower()
        if not email:
            continue
        scores_in = r.get("scores", []) or []
        scores = [{"round_name": s.get("round_name"), "score": s.get("score")}
                  for s in scores_in if s.get("round_name")]
        await _db.bb_applicant_updates.update_one(
            {"email": email},
            {"$set": {
                "email": email,
                "status": r.get("status", "On hold"),
                "scores": scores,
                "name": r.get("name", ""),
                "phone": r.get("phone", ""),
                "job_role": r.get("job_role", ""),
                "schedule_date": r.get("schedule_date", ""),
                "isImported": True,
                "import_batch_id": batch_id,
                "imported_at": now_iso,
                "import_rejection_notified": False,
                "updated_at": now_iso,
            }},
            upsert=True,
        )
        imported += 1
    return {"success": True, "imported": imported, "batch_id": batch_id}


@bb_router.post("/import-scores")
async def import_scores_legacy(request: Request):
    """Legacy single-step import (kept for backward compat).
    For the new preview→confirm flow, use /import-scores/preview then /import-scores/confirm.
    """
    await _require_auth(request)
    form = await request.form()
    file = form.get("file")
    if not file:
        raise HTTPException(status_code=400, detail="No file uploaded")
    content = await file.read()
    filename = (getattr(file, "filename", "") or "").lower()
    try:
        rows, headers = _parse_score_file(content, filename)
    except HTTPException:
        # Try legacy CSV parse with simple email/status columns
        import io, csv
        rdr = csv.DictReader(io.StringIO(content.decode("utf-8", errors="ignore")))
        imported = 0
        for row in rdr:
            email = (row.get("email") or row.get("EMAIL") or "").strip().lower()
            status = row.get("status") or row.get("STATUS") or "On hold"
            if email:
                await _db.bb_applicant_updates.update_one(
                    {"email": email},
                    {"$set": {"email": email, "status": status,
                              "updated_at": datetime.now(timezone.utc).isoformat()}},
                    upsert=True,
                )
                imported += 1
        return {"success": True, "imported": imported}
    # Delegate to confirm path
    fixed = ["Name", "Schedule Date", "College", "Degree", "Course",
             "Year of Graduation", "Email", "Phone", "Job Role", "Status"]
    round_cols = [h for h in headers if h not in fixed]
    parsed_rows = []
    for row in rows:
        email = str(row.get("Email", "") or "").strip().lower()
        if not email:
            continue
        scores = []
        for r in round_cols:
            v = str(row.get(r, "") or "").strip()
            if v in ("", "-"):
                continue
            try:
                scores.append({"round_name": r, "score": float(v)})
            except (TypeError, ValueError):
                pass
        parsed_rows.append({
            "name": str(row.get("Name", "") or "").strip(),
            "schedule_date": str(row.get("Schedule Date", "") or "").strip(),
            "email": email,
            "phone": str(row.get("Phone", "") or "").strip(),
            "job_role": str(row.get("Job Role", "") or "").strip(),
            "status": str(row.get("Status", "") or "On hold").strip() or "On hold",
            "scores": scores,
        })
    return await import_scores_confirm({"rows": parsed_rows}, request)


@bb_router.get("/export-scores")
async def export_scores(
    request: Request,
    format: str = Query("xlsx", regex="^(xlsx|csv)$"),
    startDate: str = Query(None),
    endDate: str = Query(None),
):
    """Export Update Scores list as CSV/XLSX. Same column layout as Import.
    Columns: Name, Schedule Date, College, Degree, Course, Year of Graduation,
             Email, Phone, Job Role, Status, <round columns alphabetical>.
    """
    await _require_auth(request)

    # Same source as /attended-for-scores (HR pipeline_data)
    schedule_date_filter = {"$nin": [None, ""], "$exists": True}
    if startDate:
        schedule_date_filter["$gte"] = startDate
    if endDate:
        schedule_date_filter["$lte"] = endDate
    match = {"isTest": {"$ne": True},
             "otp_verified": {"$nin": [None, ""], "$exists": True},
             "schedule_date": schedule_date_filter}

    docs = await _db.pipeline_data.find(match, {
        "_id": 0, "email": 1, "phone": 1, "name": 1,
        "schedule_date": 1, "job_role": 1, "job_title": 1,
        "result_status": 1, "college": 1, "degree": 1, "course": 1,
        "year_of_graduation": 1,
    }).to_list(None)

    # Override with bb_applicant_updates (status + scores)
    update_emails = [(d.get("email") or "").strip().lower() for d in docs if d.get("email")]
    updates = await _db.bb_applicant_updates.find(
        {"email": {"$in": update_emails}}, {"_id": 0}
    ).to_list(None) if update_emails else []
    update_map = {u["email"]: u for u in updates if u.get("email")}

    # Page-scoped scores from score_sheet
    score_records = await _db.score_sheet.find(
        {"email": {"$in": update_emails}} if update_emails else {"_id": None}, {"_id": 0}
    ).to_list(None) if update_emails else []
    score_by_email = {}
    for sr in score_records:
        se = (sr.get("email") or "").strip().lower()
        if se:
            score_by_email.setdefault(se, []).append(sr)

    # Discover all round columns present in this dataset; sort alphabetical
    all_rounds = set()
    for u in updates:
        for s in (u.get("scores") or []):
            if s.get("round_name"):
                all_rounds.add(str(s["round_name"]).strip())
    for sr in score_records:
        rn = (sr.get("round_name") or "").strip()
        if rn:
            all_rounds.add(rn)
    round_cols = sorted(all_rounds)

    fixed = ["Name", "Schedule Date", "College", "Degree", "Course",
             "Year of Graduation", "Email", "Phone", "Job Role", "Status"]
    headers = fixed + round_cols

    rows_out = []
    for d in docs:
        email = (d.get("email") or "").strip().lower()
        upd = update_map.get(email, {})
        scores_map = {}
        # Priority: bb_applicant_updates.scores > score_sheet
        if upd.get("scores"):
            for s in upd["scores"]:
                if s.get("round_name"):
                    scores_map[str(s["round_name"]).strip()] = s.get("score")
        else:
            for sr in score_by_email.get(email, []):
                rn = (sr.get("round_name") or "").strip()
                if rn:
                    scores_map[rn] = sr.get("score")

        row = {
            "Name": d.get("name") or "",
            "Schedule Date": d.get("schedule_date") or "",
            "College": d.get("college") or "",
            "Degree": d.get("degree") or "",
            "Course": d.get("course") or "",
            "Year of Graduation": d.get("year_of_graduation") or "",
            "Email": email,
            "Phone": d.get("phone") or "",
            "Job Role": d.get("job_role") or d.get("job_title") or "",
            "Status": upd.get("status") or d.get("result_status") or "On hold",
        }
        for r in round_cols:
            v = scores_map.get(r)
            row[r] = "" if v is None else v
        rows_out.append(row)

    from fastapi.responses import StreamingResponse
    import io
    if format == "csv":
        import csv
        buf = io.StringIO()
        writer = csv.DictWriter(buf, fieldnames=headers)
        writer.writeheader()
        for r in rows_out:
            writer.writerow(r)
        data = buf.getvalue().encode("utf-8")
        return StreamingResponse(
            io.BytesIO(data),
            media_type="text/csv",
            headers={"Content-Disposition": 'attachment; filename="applicant_scores.csv"'},
        )
    else:  # xlsx
        from openpyxl import Workbook
        wb = Workbook()
        ws = wb.active
        ws.title = "Scores"
        ws.append(headers)
        for r in rows_out:
            ws.append([r.get(h, "") for h in headers])
        buf = io.BytesIO()
        wb.save(buf)
        buf.seek(0)
        return StreamingResponse(
            buf,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": 'attachment; filename="applicant_scores.xlsx"'},
        )


def _parse_score_file(content: bytes, filename: str) -> tuple:
    """Parse uploaded CSV/XLSX. Returns (rows[list[dict]], headers[list[str]]).
    Used by both /import-scores/preview and the legacy /import-scores."""
    import io
    if filename.endswith(".xlsx") or filename.endswith(".xls"):
        from openpyxl import load_workbook
        wb = load_workbook(io.BytesIO(content), read_only=True, data_only=True)
        ws = wb.active
        all_rows = list(ws.iter_rows(values_only=True))
        if not all_rows:
            raise HTTPException(status_code=400, detail="Empty file")
        headers = [str(h or "").strip() for h in all_rows[0]]
        rows = [dict(zip(headers, [
            "" if v is None else (v.strftime("%Y-%m-%d") if hasattr(v, "strftime") else str(v))
            for v in r
        ])) for r in all_rows[1:] if any(v is not None and str(v).strip() != "" for v in r)]
        return rows, headers
    # CSV / fallback
    import csv
    text = content.decode("utf-8", errors="ignore")
    reader = csv.DictReader(io.StringIO(text))
    headers = list(reader.fieldnames or [])
    rows = list(reader)
    if not headers:
        raise HTTPException(status_code=400, detail="Empty or invalid CSV")
    return rows, headers


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
    applicant = await _db.bb_registrations.find_one({"phone": phone, "otp": otp_val})
    if not applicant:
        return {"success": False, "message": "Invalid OTP !"}
    # Check if OTP is expired
    if applicant.get("otp_expired"):
        return {"success": False, "message": "OTP has expired. Please contact support."}
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

    # Messaging handled by background workers (schedule_link_sender)
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

    # Send schedule confirmation ONLY if shortlist mail was already sent (sequencing rule)
    # Cutoff guard (May 2026): never message records registered before MESSAGING_CUTOFF_TS.
    import os as _os
    _cutoff = _os.environ.get("MESSAGING_CUTOFF_TS", "9999-12-31T23:59:59+00:00")
    _is_new_record = (reg.get("registered_at") or "0000") >= _cutoff
    try:
        if reg.get("shortlist_mail_sent") and _is_new_record:
            from messaging import notify_schedule_confirmation
            await notify_schedule_confirmation(
                reg.get("full_name", ""), reg.get("phone", ""), reg.get("email", ""),
                data.date.strip(), time_24,
            )
            await _db.bb_registrations.update_one(
                {"_id": reg["_id"]},
                {"$set": {"interview_mail_sent": True, "interview_mail_sent_at": datetime.now(timezone.utc).isoformat()}}
            )
        elif not _is_new_record:
            _logger.info(f"[CutoffGuard] Skipped messaging for legacy record {reg.get('email')} (registered_at < cutoff)")
        else:
            # Shortlist mail not yet sent — interview mail will be sent by worker after shortlist mail
            _logger.info(f"[Sequencing] Interview mail deferred for {reg.get('email')} — awaiting shortlist mail first")
    except Exception as e:
        _logger.error(f"Schedule confirmation send failed: {e}")

    return {"success": True, "is_reschedule": is_reschedule, "otp": otp}
