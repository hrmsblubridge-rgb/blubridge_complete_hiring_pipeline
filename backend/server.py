from dotenv import load_dotenv
from pathlib import Path

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

from fastapi import FastAPI, APIRouter, HTTPException, Request, Response, UploadFile, File, Depends, Query
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
import os
import logging
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
from datetime import datetime, timezone, timedelta
import jwt
import pandas as pd
import io
import re

# MongoDB connection
mongo_url = os.environ['MONGO_URL']
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ['DB_NAME']]

# JWT Configuration
JWT_SECRET = os.environ.get("JWT_SECRET", "recruitment-analytics-secret-key")
JWT_ALGORITHM = "HS256"

# Create the main app
app = FastAPI()
api_router = APIRouter(prefix="/api")

# ============ AUTH HELPERS ============

def create_token(username: str) -> str:
    payload = {
        "sub": username,
        "exp": datetime.now(timezone.utc) + timedelta(hours=24),
        "type": "access"
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)

async def get_current_user(request: Request) -> str:
    token = request.cookies.get("access_token")
    if not token:
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header[7:]
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        return payload["sub"]
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")

# ============ DATA HELPERS ============

def normalize_phone(phone) -> str:
    if pd.isna(phone) or phone is None:
        return ""
    phone_str = str(phone).strip()
    phone_str = re.sub(r'[^\d]', '', phone_str)
    if phone_str.startswith('91') and len(phone_str) > 10:
        phone_str = phone_str[2:]
    return phone_str

def normalize_email(email) -> str:
    if pd.isna(email) or email is None:
        return ""
    return str(email).strip().lower()

def clean_value(val):
    if pd.isna(val) or val is None:
        return None
    if isinstance(val, (pd.Timestamp, datetime)):
        return val.isoformat()
    return val

def parse_file(file_content: bytes, filename: str) -> pd.DataFrame:
    if filename.lower().endswith('.csv'):
        for encoding in ['utf-8', 'latin-1', 'cp1252']:
            try:
                return pd.read_csv(io.BytesIO(file_content), encoding=encoding)
            except UnicodeDecodeError:
                continue
        raise ValueError("Unable to decode CSV file")
    elif filename.lower().endswith(('.xlsx', '.xls')):
        return pd.read_excel(io.BytesIO(file_content))
    else:
        raise ValueError("Unsupported file format. Use .csv or .xlsx")

# ============ SCHEMA MAPPING LAYER ============

# Naukri Applies: display column name → normalized DB field name
NAUKRI_COLUMN_MAP = {
    "Job Title": "job_title",
    "Date of application": "date_of_application",
    "Name": "name",
    "Email ID": "email",
    "Phone Number": "phone",
    "Current Location": "current_location",
    "Preferred Locations": "preferred_locations",
    "Total Experience": "total_experience",
    "Curr. Company name": "curr_company_name",
    "Curr. Company Designation": "curr_company_designation",
    "Department": "department",
    "Role": "role",
    "Industry": "industry",
    "Key Skills": "key_skills",
    "Annual Salary": "annual_salary",
    "Notice period/ Availability to join": "notice_period",
    "Resume Headline": "resume_headline",
    "Summary": "summary",
    "Under Graduation degree": "ug_degree",
    "UG Specialization": "ug_specialization",
    "UG University/institute Name": "ug_university",
    "UG Graduation year": "ug_graduation_year",
    "Post graduation degree": "pg_degree",
    "PG specialization": "pg_specialization",
    "PG university/institute name": "pg_university",
    "PG graduation year": "pg_graduation_year",
    "Doctorate degree": "doctorate_degree",
    "Doctorate specialization": "doctorate_specialization",
    "Doctorate university/institute name": "doctorate_university",
    "Doctorate graduation year": "doctorate_graduation_year",
    "Gender": "gender",
    "Marital Status": "marital_status",
    "Home Town/City": "home_town",
    "Pin Code": "pin_code",
    "Work permit for USA": "work_permit_usa",
    "Date of Birth": "date_of_birth",
    "Permanent Address": "permanent_address",
    "Last Workflow activity": "last_workflow_activity",
    "Last Workflow activity by": "last_workflow_activity_by",
    "Time of Last Workflow activity Update": "time_last_workflow_update",
    "Latest Pipeline Stage": "latest_pipeline_stage",
    "Pipeline Status Updated By": "pipeline_status_updated_by",
    "Time when Stage updated": "time_stage_updated",
    "Download": "download",
    "Downloaded By": "downloaded_by",
    "Time Of Download": "time_of_download",
    "Viewed": "viewed",
    "Viewed By": "viewed_by",
    "Time Of View": "time_of_view",
    "Emailed": "emailed",
    "Emailed By": "emailed_by",
    "Time Of Email": "time_of_email",
    "Calling Status": "calling_status",
    "Calling Status updated by": "calling_status_updated_by",
    "Time of Calling activity update": "time_calling_update",
    "Comment 1": "comment_1",
    "Comment 1 BY": "comment_1_by",
    "Time Comment 1 posted": "time_comment_1",
    "Comment 2": "comment_2",
    "Comment 2 BY": "comment_2_by",
    "Time Comment 2 posted": "time_comment_2",
    "Comment 3": "comment_3",
    "Comment 3 BY": "comment_3_by",
    "Time Comment 3 posted": "time_comment_3",
    "Comment 4": "comment_4",
    "Comment 4 BY": "comment_4_by",
    "Time Comment 4 posted": "time_comment_4",
    "Comment 5": "comment_5",
    "Comment 5 BY": "comment_5_by",
    "Time Comment 5 posted": "time_comment_5",
    "Source": "source",
    "Candidate profile": "candidate_profile",
}

# Case-insensitive reverse lookup for Naukri column matching
_NAUKRI_CI_LOOKUP = {k.strip().lower(): v for k, v in NAUKRI_COLUMN_MAP.items()}

# HR Internal Pipeline: canonical column set (already snake_case)
PIPELINE_EXPECTED_COLUMNS = {
    "id", "name", "email", "phone", "age", "gender", "hr_team",
    "year_of_graduation", "college", "college_type", "degree", "course",
    "submitted_at", "last_update", "email_send", "current_location",
    "location", "state", "loca_change", "attend_inperson", "job_role",
    "email_type", "confirm_box", "resend", "whatsapp_reminder_sent",
    "schedule_date", "schedule_time", "reschedule_count", "otp",
    "otp_verified", "otp_expired", "otp_send", "message_id",
    "result_mail", "result_update", "result_status", "reschedule",
    "reschedule_mail", "rescheduled", "reschedule_date",
}

# Case-insensitive lookup for pipeline columns
_PIPELINE_CI_LOOKUP = {c.lower(): c for c in PIPELINE_EXPECTED_COLUMNS}

# ============ AUTH ENDPOINTS ============

class LoginRequest(BaseModel):
    username: str
    password: str

@api_router.post("/login")
async def login(response: Response, data: LoginRequest):
    # Hardcoded credentials as per requirements
    if data.username == "admin" and data.password == "admin":
        token = create_token(data.username)
        response.set_cookie(
            key="access_token", 
            value=token, 
            httponly=True, 
            secure=False, 
            samesite="lax", 
            max_age=86400, 
            path="/"
        )
        return {"success": True, "message": "Login successful", "username": data.username}
    else:
        raise HTTPException(status_code=401, detail="Invalid credentials")

@api_router.post("/logout")
async def logout(response: Response):
    response.delete_cookie(key="access_token", path="/")
    return {"success": True, "message": "Logged out"}

@api_router.get("/auth/check")
async def check_auth(user: str = Depends(get_current_user)):
    return {"authenticated": True, "username": user}

# ============ UPLOAD ENDPOINTS ============

@api_router.post("/upload/naukri")
async def upload_naukri(file: UploadFile = File(...), user: str = Depends(get_current_user)):
    """Upload Naukri Applies data — mapping-driven schema alignment"""
    try:
        content = await file.read()
        if len(content) > 10 * 1024 * 1024:
            raise HTTPException(status_code=400, detail="File size exceeds 10MB limit")

        df = parse_file(content, file.filename)
        df.columns = df.columns.str.strip()

        # Map CSV columns → DB field names using the mapping dictionary
        col_map = {}  # csv_column_name → db_field_name
        for csv_col in df.columns:
            if csv_col in NAUKRI_COLUMN_MAP:
                col_map[csv_col] = NAUKRI_COLUMN_MAP[csv_col]
            elif csv_col.strip().lower() in _NAUKRI_CI_LOOKUP:
                col_map[csv_col] = _NAUKRI_CI_LOOKUP[csv_col.strip().lower()]

        mapped_fields = set(col_map.values())
        if "email" not in mapped_fields and "phone" not in mapped_fields:
            raise HTTPException(status_code=400, detail="Could not detect 'Email ID' or 'Phone Number' column")

        total = len(df)
        inserted = 0
        updated = 0
        errors = []

        for idx, row in df.iterrows():
            try:
                doc = {}
                # Store mapped columns
                for csv_col, db_field in col_map.items():
                    doc[db_field] = clean_value(row.get(csv_col))

                # Store unmapped columns (data loss prevention)
                for csv_col in df.columns:
                    if csv_col not in col_map:
                        safe = re.sub(r'[^\w]', '_', csv_col.strip().lower()).strip('_')
                        doc[f"_extra_{safe}"] = clean_value(row.get(csv_col))

                # Normalize identifiers
                email = normalize_email(doc.get("email"))
                phone = normalize_phone(doc.get("phone"))
                doc["email"] = email
                doc["phone"] = phone
                doc["updated_at"] = datetime.now(timezone.utc)

                if not email and not phone:
                    errors.append(f"Row {idx + 2}: Missing Email ID and Phone Number")
                    continue

                # UPSERT on email OR phone
                query = {"$or": []}
                if email:
                    query["$or"].append({"email": email})
                if phone:
                    query["$or"].append({"phone": phone})

                existing = await db.naukri_applies.find_one(query)
                if existing:
                    await db.naukri_applies.update_one({"_id": existing["_id"]}, {"$set": doc})
                    updated += 1
                else:
                    doc["created_at"] = datetime.now(timezone.utc)
                    await db.naukri_applies.insert_one(doc)
                    inserted += 1

            except Exception as e:
                errors.append(f"Row {idx + 2}: {str(e)}")

        await reprocess_matching()

        return {
            "success": True,
            "message": f"Naukri data uploaded. Inserted: {inserted}, Updated: {updated}",
            "total": total,
            "inserted": inserted,
            "updated": updated,
            "errors": errors[:10],
            "mapped_columns": len(col_map),
            "unmapped_columns": len(df.columns) - len(col_map)
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@api_router.post("/upload/pipeline")
async def upload_pipeline(file: UploadFile = File(...), user: str = Depends(get_current_user)):
    """Upload HR Internal Pipeline data — handles duplicate columns, strict schema"""
    try:
        content = await file.read()
        if len(content) > 10 * 1024 * 1024:
            raise HTTPException(status_code=400, detail="File size exceeds 10MB limit")

        df = parse_file(content, file.filename)
        df.columns = df.columns.str.strip()

        # Deduplicate columns: keep first occurrence only
        cols = df.columns.tolist()
        seen_bases = set()
        keep_indices = []
        for i, col in enumerate(cols):
            base = re.sub(r'\.\d+$', '', col.strip()).lower()
            if base not in seen_bases:
                seen_bases.add(base)
                keep_indices.append(i)
        df = df.iloc[:, keep_indices]
        df.columns = [re.sub(r'\.\d+$', '', c.strip()) for c in df.columns]

        # Map CSV columns → DB field names
        col_map = {}
        for csv_col in df.columns:
            normalized = csv_col.strip().lower()
            if normalized in _PIPELINE_CI_LOOKUP:
                db_field = _PIPELINE_CI_LOOKUP[normalized]
                col_map[csv_col] = "pipeline_id" if db_field == "id" else db_field

        mapped_fields = set(col_map.values())
        if "email" not in mapped_fields and "phone" not in mapped_fields:
            raise HTTPException(status_code=400, detail="Could not detect 'email' or 'phone' column")

        total = len(df)
        inserted = 0
        updated = 0
        errors = []

        for idx, row in df.iterrows():
            try:
                doc = {}
                for csv_col, db_field in col_map.items():
                    doc[db_field] = clean_value(row.get(csv_col))

                # Store unmapped columns (data loss prevention)
                for csv_col in df.columns:
                    if csv_col not in col_map:
                        safe = re.sub(r'[^\w]', '_', csv_col.strip().lower()).strip('_')
                        doc[f"_extra_{safe}"] = clean_value(row.get(csv_col))

                email = normalize_email(doc.get("email"))
                phone = normalize_phone(doc.get("phone"))
                doc["email"] = email
                doc["phone"] = phone
                doc["updated_at"] = datetime.now(timezone.utc)

                if not email and not phone:
                    errors.append(f"Row {idx + 2}: Missing email and phone")
                    continue

                # UPSERT on email OR phone
                query = {"$or": []}
                if email:
                    query["$or"].append({"email": email})
                if phone:
                    query["$or"].append({"phone": phone})

                existing = await db.pipeline_data.find_one(query)
                if existing:
                    await db.pipeline_data.update_one({"_id": existing["_id"]}, {"$set": doc})
                    updated += 1
                else:
                    doc["created_at"] = datetime.now(timezone.utc)
                    await db.pipeline_data.insert_one(doc)
                    inserted += 1

            except Exception as e:
                errors.append(f"Row {idx + 2}: {str(e)}")

        await reprocess_matching()

        return {
            "success": True,
            "message": f"Pipeline data uploaded. Inserted: {inserted}, Updated: {updated}",
            "total": total,
            "inserted": inserted,
            "updated": updated,
            "errors": errors[:10],
            "mapped_columns": len(col_map),
            "unmapped_columns": len(df.columns) - len(col_map)
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ============ MATCHING & PROCESSING ============

def is_null_or_empty(val):
    """Check if a value is None, empty string, or missing"""
    return val is None or val == ""

async def reprocess_matching():
    """Rebuild registered_candidates via INNER JOIN — merges ALL fields from both collections"""
    naukri_list = await db.naukri_applies.find({}).to_list(None)
    pipeline_list = await db.pipeline_data.find({}).to_list(None)

    pipeline_by_email = {p['email']: p for p in pipeline_list if p.get('email')}
    pipeline_by_phone = {p['phone']: p for p in pipeline_list if p.get('phone')}

    await db.registered_candidates.drop()

    registered_docs = []
    _skip_keys = {"_id", "_is_registered", "created_at", "updated_at"}

    for naukri in naukri_list:
        email = naukri.get('email', '')
        phone = naukri.get('phone', '')

        pipeline_match = None
        if email and email in pipeline_by_email:
            pipeline_match = pipeline_by_email[email]
        elif phone and phone in pipeline_by_phone:
            pipeline_match = pipeline_by_phone[phone]

        is_registered = pipeline_match is not None

        await db.naukri_applies.update_one(
            {"_id": naukri["_id"]},
            {"$set": {"_is_registered": is_registered}}
        )

        if is_registered:
            # Start with ALL pipeline fields as the base
            doc = {}
            for k, v in pipeline_match.items():
                if k not in _skip_keys:
                    doc[k] = v

            # Overlay ALL naukri fields (naukri takes precedence for non-null shared fields)
            for k, v in naukri.items():
                if k not in _skip_keys:
                    if v is not None and v != "":
                        doc[k] = v
                    elif k not in doc:
                        doc[k] = v

            registered_docs.append(doc)

    if registered_docs:
        await db.registered_candidates.insert_many(registered_docs)

    await db.registered_candidates.create_index([("email", 1), ("phone", 1)])
    await db.registered_candidates.create_index("email_type")
    await db.registered_candidates.create_index("result_status")
    await db.registered_candidates.create_index("schedule_date")
    await db.registered_candidates.create_index("otp_verified")

# ============ DASHBOARD COUNTS ENDPOINT ============

# Helpers for NULL-safe MongoDB queries
_null_filter = {"$in": [None, ""]}
_not_null_filter = {"$nin": [None, ""], "$exists": True}

@api_router.get("/dashboard-counts")
async def get_dashboard_counts(user: str = Depends(get_current_user)):
    """All counts computed from DB. Sub-categories use registered_candidates ONLY."""

    total_applies = await db.naukri_applies.count_documents({})
    registered = await db.registered_candidates.count_documents({})
    unregistered = total_applies - registered

    # ALL sub-categories from registered_candidates (strict subsets of Registered)
    shortlisted = await db.registered_candidates.count_documents({
        "result_status": {"$regex": "shortlist", "$options": "i"}
    })
    rejected = await db.registered_candidates.count_documents({
        "result_status": {"$regex": "^reject", "$options": "i"}
    })
    scheduled = await db.registered_candidates.count_documents({
        "schedule_date": _not_null_filter,
        "schedule_time": _not_null_filter
    })
    not_scheduled = await db.registered_candidates.count_documents({
        "$and": [
            {"$or": [{"schedule_date": None}, {"schedule_date": ""}, {"schedule_date": {"$exists": False}}]},
            {"$or": [{"schedule_time": None}, {"schedule_time": ""}, {"schedule_time": {"$exists": False}}]}
        ]
    })
    attended = await db.registered_candidates.count_documents({
        "otp_verified": _not_null_filter
    })
    not_attended = await db.registered_candidates.count_documents({
        "$or": [
            {"otp_verified": None},
            {"otp_verified": ""},
            {"otp_verified": {"$exists": False}}
        ]
    })

    return {
        "total_applies": total_applies,
        "registered": registered,
        "unregistered": unregistered,
        "shortlisted": shortlisted,
        "rejected": rejected,
        "scheduled": scheduled,
        "not_scheduled": not_scheduled,
        "attended": attended,
        "not_attended": not_attended
    }

# ============ DRILL-DOWN DATA ENDPOINTS ============

@api_router.get("/data/unregistered")
async def get_unregistered(
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=500),
    user: str = Depends(get_current_user)
):
    """Unregistered: in naukri_applies but NOT in pipeline_data"""
    skip = (page - 1) * limit
    query = {"_is_registered": {"$ne": True}}
    total = await db.naukri_applies.count_documents(query)
    cursor = db.naukri_applies.find(query, {
        "_id": 0, "name": 1, "email": 1, "phone": 1,
        "job_title": 1, "date_of_application": 1, "gender": 1, "date_of_birth": 1
    }).skip(skip).limit(limit)
    data = await cursor.to_list(None)
    return {
        "data": data, "total": total, "page": page, "limit": limit,
        "columns": ["name", "email", "phone", "job_title", "date_of_application", "gender", "date_of_birth"]
    }

@api_router.get("/data/registered")
async def get_registered(
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=500),
    user: str = Depends(get_current_user)
):
    """Registered: JOIN of naukri_applies and pipeline_data"""
    skip = (page - 1) * limit
    total = await db.registered_candidates.count_documents({})
    cursor = db.registered_candidates.find({}, {
        "_id": 0, "name": 1, "email": 1, "phone": 1,
        "job_title": 1, "date_of_application": 1, "gender": 1, "date_of_birth": 1
    }).skip(skip).limit(limit)
    data = await cursor.to_list(None)
    return {
        "data": data, "total": total, "page": page, "limit": limit,
        "columns": ["name", "email", "phone", "job_title", "date_of_application", "gender", "date_of_birth"]
    }

@api_router.get("/data/shortlisted")
async def get_shortlisted(
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=500),
    user: str = Depends(get_current_user)
):
    """Shortlisted: registered_candidates WHERE result_status matches shortlist"""
    skip = (page - 1) * limit
    query = {"result_status": {"$regex": "shortlist", "$options": "i"}}
    total = await db.registered_candidates.count_documents(query)
    cursor = db.registered_candidates.find(query, {
        "_id": 0, "name": 1, "email": 1, "phone": 1, "job_title": 1,
        "date_of_application": 1, "gender": 1, "location": 1, "result_status": 1
    }).skip(skip).limit(limit)
    data = await cursor.to_list(None)
    return {
        "data": data, "total": total, "page": page, "limit": limit,
        "columns": ["name", "email", "phone", "job_title", "date_of_application", "gender", "location", "result_status"]
    }

@api_router.get("/data/rejected")
async def get_rejected(
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=500),
    user: str = Depends(get_current_user)
):
    """Rejected: registered_candidates WHERE result_status IN (Reject, Rejected)"""
    skip = (page - 1) * limit
    query = {"result_status": {"$regex": "^reject", "$options": "i"}}
    total = await db.registered_candidates.count_documents(query)
    cursor = db.registered_candidates.find(query, {
        "_id": 0, "name": 1, "email": 1, "phone": 1, "job_title": 1,
        "date_of_application": 1, "gender": 1, "date_of_birth": 1,
        "location": 1, "loca_change": 1, "attend_inperson": 1,
        "email_type": 1, "confirm_box": 1
    }).skip(skip).limit(limit)
    data = await cursor.to_list(None)
    return {
        "data": data, "total": total, "page": page, "limit": limit,
        "columns": ["name", "email", "phone", "job_title", "date_of_application", "gender", "date_of_birth", "location", "loca_change", "attend_inperson", "email_type", "confirm_box"]
    }

@api_router.get("/data/scheduled")
async def get_scheduled(
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=500),
    user: str = Depends(get_current_user)
):
    """Scheduled: registered_candidates WHERE schedule_date IS NOT NULL AND schedule_time IS NOT NULL"""
    skip = (page - 1) * limit
    query = {
        "schedule_date": _not_null_filter,
        "schedule_time": _not_null_filter
    }
    total = await db.registered_candidates.count_documents(query)
    cursor = db.registered_candidates.find(query, {
        "_id": 0, "name": 1, "email": 1, "phone": 1, "job_title": 1,
        "date_of_application": 1, "gender": 1,
        "schedule_date": 1, "schedule_time": 1, "reschedule_count": 1
    }).skip(skip).limit(limit)
    data = await cursor.to_list(None)
    return {
        "data": data, "total": total, "page": page, "limit": limit,
        "columns": ["name", "email", "phone", "job_title", "date_of_application", "gender", "schedule_date", "schedule_time", "reschedule_count"]
    }

@api_router.get("/data/not-scheduled")
async def get_not_scheduled(
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=500),
    user: str = Depends(get_current_user)
):
    """Not Scheduled: registered_candidates WHERE schedule_date IS NULL AND schedule_time IS NULL"""
    skip = (page - 1) * limit
    query = {
        "$and": [
            {"$or": [{"schedule_date": None}, {"schedule_date": ""}, {"schedule_date": {"$exists": False}}]},
            {"$or": [{"schedule_time": None}, {"schedule_time": ""}, {"schedule_time": {"$exists": False}}]}
        ]
    }
    total = await db.registered_candidates.count_documents(query)
    cursor = db.registered_candidates.find(query, {
        "_id": 0, "name": 1, "email": 1, "phone": 1, "job_title": 1,
        "date_of_application": 1, "gender": 1, "date_of_birth": 1,
        "location": 1, "loca_change": 1, "attend_inperson": 1,
        "email_type": 1, "confirm_box": 1
    }).skip(skip).limit(limit)
    data = await cursor.to_list(None)
    return {
        "data": data, "total": total, "page": page, "limit": limit,
        "columns": ["name", "email", "phone", "job_title", "date_of_application", "gender", "date_of_birth", "location", "loca_change", "attend_inperson", "email_type", "confirm_box"]
    }

@api_router.get("/data/attended")
async def get_attended(
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=500),
    user: str = Depends(get_current_user)
):
    """Attended: registered_candidates WHERE otp_verified IS NOT NULL"""
    skip = (page - 1) * limit
    query = {"otp_verified": _not_null_filter}
    total = await db.registered_candidates.count_documents(query)
    cursor = db.registered_candidates.find(query, {
        "_id": 0, "name": 1, "email": 1, "phone": 1, "job_title": 1,
        "date_of_application": 1, "gender": 1, "date_of_birth": 1,
        "schedule_date": 1, "schedule_time": 1, "reschedule_count": 1,
        "otp_verified": 1, "result_mail": 1, "result_update": 1, "result_status": 1
    }).skip(skip).limit(limit)
    data = await cursor.to_list(None)
    return {
        "data": data, "total": total, "page": page, "limit": limit,
        "columns": ["name", "email", "phone", "job_title", "date_of_application", "gender", "date_of_birth", "schedule_date", "schedule_time", "reschedule_count", "otp_verified", "result_mail", "result_update", "result_status"]
    }

@api_router.get("/data/not-attended")
async def get_not_attended(
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=500),
    user: str = Depends(get_current_user)
):
    """Not Attended: registered_candidates WHERE otp_verified IS NULL"""
    skip = (page - 1) * limit
    query = {
        "$or": [
            {"otp_verified": None},
            {"otp_verified": ""},
            {"otp_verified": {"$exists": False}}
        ]
    }
    total = await db.registered_candidates.count_documents(query)
    cursor = db.registered_candidates.find(query, {
        "_id": 0, "name": 1, "email": 1, "phone": 1, "job_title": 1,
        "date_of_application": 1, "gender": 1, "date_of_birth": 1,
        "schedule_date": 1, "schedule_time": 1, "reschedule_count": 1,
        "otp_verified": 1, "otp_expired": 1
    }).skip(skip).limit(limit)
    data = await cursor.to_list(None)
    return {
        "data": data, "total": total, "page": page, "limit": limit,
        "columns": ["name", "email", "phone", "job_title", "date_of_application", "gender", "date_of_birth", "schedule_date", "schedule_time", "reschedule_count", "otp_verified", "otp_expired"]
    }

# ============ SUMMARY & ROLE ANALYTICS ENDPOINTS ============

async def _aggregate_funnel_stats(match_filter: dict) -> list:
    """Aggregate funnel statistics grouped by job_title from registered_candidates"""
    pipeline = [
        {"$match": match_filter},
        {"$group": {
            "_id": "$job_title",
            "total_applicants": {"$sum": 1},
            "shortlisted": {"$sum": {"$cond": [
                {"$regexMatch": {"input": {"$ifNull": ["$result_status", ""]}, "regex": "shortlist", "options": "i"}},
                1, 0
            ]}},
            "rejected": {"$sum": {"$cond": [
                {"$regexMatch": {"input": {"$ifNull": ["$result_status", ""]}, "regex": "^reject", "options": "i"}},
                1, 0
            ]}},
            "scheduled": {"$sum": {"$cond": [
                {"$and": [
                    {"$ne": [{"$ifNull": ["$schedule_date", ""]}, ""]},
                    {"$ne": [{"$ifNull": ["$schedule_date", None]}, None]},
                    {"$ne": [{"$ifNull": ["$schedule_time", ""]}, ""]},
                    {"$ne": [{"$ifNull": ["$schedule_time", None]}, None]}
                ]},
                1, 0
            ]}},
            "not_scheduled": {"$sum": {"$cond": [
                {"$and": [
                    {"$or": [
                        {"$eq": [{"$ifNull": ["$schedule_date", None]}, None]},
                        {"$eq": ["$schedule_date", ""]}
                    ]},
                    {"$or": [
                        {"$eq": [{"$ifNull": ["$schedule_time", None]}, None]},
                        {"$eq": ["$schedule_time", ""]}
                    ]}
                ]},
                1, 0
            ]}},
            "attended": {"$sum": {"$cond": [
                {"$and": [
                    {"$ne": [{"$ifNull": ["$otp_verified", ""]}, ""]},
                    {"$ne": [{"$ifNull": ["$otp_verified", None]}, None]}
                ]},
                1, 0
            ]}},
            "not_attended": {"$sum": {"$cond": [
                {"$or": [
                    {"$eq": [{"$ifNull": ["$otp_verified", None]}, None]},
                    {"$eq": ["$otp_verified", ""]}
                ]},
                1, 0
            ]}}
        }},
        {"$sort": {"_id": 1}},
        {"$project": {
            "_id": 0,
            "job_role": "$_id",
            "total_applicants": 1,
            "shortlisted": 1,
            "rejected": 1,
            "scheduled": 1,
            "not_scheduled": 1,
            "attended": 1,
            "not_attended": 1
        }}
    ]
    return await db.registered_candidates.aggregate(pipeline).to_list(None)


@api_router.get("/summary")
async def get_summary(
    startDate: str = Query(None),
    endDate: str = Query(None),
    search: str = Query(None),
    user: str = Depends(get_current_user)
):
    """Job role-wise funnel statistics with date & search filters"""
    match = {}
    if startDate or endDate:
        date_filter = {}
        if startDate:
            date_filter["$gte"] = startDate
        if endDate:
            date_filter["$lte"] = endDate
        match["date_of_application"] = date_filter
    if search:
        match["job_title"] = {"$regex": re.escape(search), "$options": "i"}
    results = await _aggregate_funnel_stats(match)
    total_registered = sum(r["total_applicants"] for r in results)
    return {"data": results, "total_registered": total_registered}


@api_router.get("/job-roles")
async def get_job_roles(user: str = Depends(get_current_user)):
    """Unique job roles with registered applicant counts"""
    pipeline = [
        {"$match": {"job_title": {"$nin": [None, ""]}}},
        {"$group": {"_id": "$job_title", "count": {"$sum": 1}}},
        {"$sort": {"count": -1}},
        {"$project": {"_id": 0, "job_role": "$_id", "count": 1}}
    ]
    results = await db.registered_candidates.aggregate(pipeline).to_list(None)
    return {"job_roles": results}


def derive_status(doc: dict) -> str:
    """Derive candidate status from pipeline fields, most advanced stage first."""
    result_status = str(doc.get("result_status") or "").strip()
    otp_verified = str(doc.get("otp_verified") or "").strip()
    schedule_date = str(doc.get("schedule_date") or "").strip()
    schedule_time = str(doc.get("schedule_time") or "").strip()

    if re.match(r"^reject", result_status, re.IGNORECASE):
        return "Rejected"
    if otp_verified:
        return "Attended"
    if schedule_date and schedule_time:
        return "Interview Scheduled"
    if re.search(r"shortlist", result_status, re.IGNORECASE):
        return "Shortlisted"
    return "Registered"


@api_router.get("/role")
async def get_role_applicants(
    jobRole: str = Query(..., description="Job role to analyze"),
    startDate: str = Query(None),
    endDate: str = Query(None),
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=500),
    user: str = Depends(get_current_user)
):
    """Detailed applicant table for a single job role — returns individual candidate rows with derived status"""
    role = jobRole.strip()
    match = {"job_title": {"$regex": f"^{re.escape(role)}$", "$options": "i"}}
    if startDate or endDate:
        date_filter = {}
        if startDate:
            date_filter["$gte"] = startDate
        if endDate:
            date_filter["$lte"] = endDate
        match["date_of_application"] = date_filter

    total = await db.registered_candidates.count_documents(match)
    skip = (page - 1) * limit
    cursor = db.registered_candidates.find(match, {
        "_id": 0, "name": 1, "email": 1, "phone": 1, "gender": 1,
        "date_of_birth": 1, "date_of_application": 1,
        "email_type": 1, "result_status": 1, "otp_verified": 1,
        "schedule_date": 1, "schedule_time": 1
    }).skip(skip).limit(limit)
    docs = await cursor.to_list(None)

    applicants = []
    for doc in docs:
        applicants.append({
            "name": doc.get("name") or "-",
            "email": doc.get("email") or "-",
            "phone": doc.get("phone") or "-",
            "gender": doc.get("gender") or "-",
            "date_of_birth": doc.get("date_of_birth") or "-",
            "date_of_application": doc.get("date_of_application") or "-",
            "status": derive_status(doc)
        })

    return {
        "data": applicants,
        "total": total,
        "page": page,
        "limit": limit,
        "columns": ["name", "email", "phone", "gender", "date_of_birth", "date_of_application", "status"]
    }


# Status endpoint — DB-driven state
@api_router.get("/status")
async def get_status(user: str = Depends(get_current_user)):
    """Returns current data availability from database"""
    naukri_count = await db.naukri_applies.count_documents({})
    pipeline_count = await db.pipeline_data.count_documents({})
    registered_count = await db.registered_candidates.count_documents({})
    return {
        "naukri_count": naukri_count,
        "pipeline_count": pipeline_count,
        "registered_count": registered_count,
    }


# Health check
@api_router.get("/")
async def root():
    return {"message": "Recruitment Analytics API", "status": "healthy", "version": "4.0"}

# Include the router in the main app
app.include_router(api_router)

# CORS Configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=[os.environ.get('FRONTEND_URL', 'http://localhost:3000')],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Startup event
@app.on_event("startup")
async def startup_event():
    # Create indexes
    await db.naukri_applies.create_index([("email", 1), ("phone", 1)])
    await db.pipeline_data.create_index([("email", 1), ("phone", 1)])
    await db.registered_candidates.create_index([("email", 1), ("phone", 1)])
    await db.registered_candidates.create_index("email_type")
    await db.registered_candidates.create_index("result_status")
    await db.registered_candidates.create_index("schedule_date")
    await db.registered_candidates.create_index("otp_verified")
    
    # Write test credentials
    try:
        os.makedirs("/app/memory", exist_ok=True)
        with open("/app/memory/test_credentials.md", "w") as f:
            f.write("# Test Credentials\n\n")
            f.write("## Admin Account\n")
            f.write("- Username: admin\n")
            f.write("- Password: admin\n")
    except Exception as e:
        logger.error(f"Failed to write test credentials: {e}")

@app.on_event("shutdown")
async def shutdown_db_client():
    client.close()
