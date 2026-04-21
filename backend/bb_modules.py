"""BluBridge Modules — New features for the Hiring Pipeline.
Separate router to avoid modifying existing server.py logic."""

from fastapi import APIRouter, HTTPException, Request, Query
from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime, timezone
from bson import ObjectId

bb_router = APIRouter(prefix="/api/bb")

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

class HiringFormUpdate(BaseModel):
    name: Optional[str] = None
    form_type_id: Optional[str] = None
    job_role: Optional[str] = None
    conditions: Optional[ConditionsBody] = None

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
    description: Optional[str] = ""

class JobOpeningUpdate(BaseModel):
    title: Optional[str] = None
    job_role: Optional[str] = None
    description: Optional[str] = None

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
           "description": (data.description or "").strip(),
           "created_at": datetime.now(timezone.utc).isoformat(), "updated_at": datetime.now(timezone.utc).isoformat()}
    result = await _db.bb_job_openings.insert_one(doc)
    return {"success": True, "id": str(result.inserted_id)}

@bb_router.put("/job-openings/{opening_id}")
async def update_job_opening(opening_id: str, data: JobOpeningUpdate, request: Request):
    await _require_auth(request)
    updates = {"updated_at": datetime.now(timezone.utc).isoformat()}
    if data.title is not None: updates["title"] = data.title.strip()
    if data.job_role is not None: updates["job_role"] = data.job_role.strip()
    if data.description is not None: updates["description"] = data.description.strip()
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
