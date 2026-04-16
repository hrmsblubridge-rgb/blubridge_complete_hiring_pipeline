from dotenv import load_dotenv
from pathlib import Path

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

from fastapi import FastAPI, APIRouter, HTTPException, Request, Response, UploadFile, File, Depends, Query
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
import os
import logging
import shutil
import glob as glob_module
import asyncio
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
    # Handle numeric types — pandas reads phone columns as float when NaN present
    if isinstance(phone, (int, float)):
        try:
            phone_str = str(int(phone))
        except (ValueError, OverflowError):
            return ""
    else:
        phone_str = str(phone).strip()
    # Remove all spaces
    phone_str = phone_str.replace(" ", "")
    # Handle comma-separated: take first number
    if "," in phone_str:
        phone_str = phone_str.split(",")[0].strip()
    # Strip non-digit characters (+, -, etc.)
    phone_str = re.sub(r'[^\d]', '', phone_str)
    # Normalize to 10 digits based on length
    if len(phone_str) == 10:
        return phone_str
    if len(phone_str) > 10:
        return phone_str[-10:]
    return phone_str

def normalize_email(email) -> str:
    if pd.isna(email) or email is None:
        return ""
    return str(email).strip().lower()

import time as _time_module

MONTH_MAP = {
    "jan": "01", "feb": "02", "mar": "03", "apr": "04",
    "may": "05", "jun": "06", "jul": "07", "aug": "08",
    "sep": "09", "oct": "10", "nov": "11", "dec": "12"
}


def normalize_date(val) -> str:
    """Convert any date value/string to canonical YYYY-MM-DD format.
    Handles: pd.Timestamp, datetime, DD-MMM-YYYY, DD-MM-YYYY, YYYY-MM-DD, etc."""
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return None
    if isinstance(val, (pd.Timestamp, datetime)):
        return val.strftime("%Y-%m-%d")
    s = str(val).strip()
    if not s:
        return None
    # Already ISO? (YYYY-MM-DD)
    if re.match(r'^\d{4}-\d{2}-\d{2}', s):
        return s[:10]
    parts = re.split(r'[-/]', s)
    if len(parts) == 3:
        # DD-MMM-YYYY (24-Mar-2026)
        if parts[1].lower() in MONTH_MAP:
            mm = MONTH_MAP[parts[1].lower()]
            return f"{parts[2]}-{mm}-{parts[0].zfill(2)}"
        # DD-MM-YYYY (24-03-2026) — day first if parts[0] <= 31
        if len(parts[0]) <= 2 and len(parts[2]) == 4:
            return f"{parts[2]}-{parts[1].zfill(2)}-{parts[0].zfill(2)}"
        # MM-DD-YYYY fallback
        if len(parts[2]) == 4:
            return f"{parts[2]}-{parts[0].zfill(2)}-{parts[1].zfill(2)}"
    return s


def clean_value(val):
    if pd.isna(val) or val is None:
        return None
    if isinstance(val, (pd.Timestamp, datetime)):
        # Date-only timestamps → ISO YYYY-MM-DD
        if hasattr(val, 'hour') and val.hour == 0 and val.minute == 0 and val.second == 0:
            return val.strftime("%Y-%m-%d")
        return val.isoformat()
    if isinstance(val, _time_module.struct_time):
        return str(val)
    # Handle datetime.time objects (from Excel time columns like schedule_time)
    if hasattr(val, 'hour') and hasattr(val, 'minute') and not isinstance(val, datetime):
        return val.strftime("%I:%M %p") if hasattr(val, 'strftime') else str(val)
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

                # Normalize date fields to ISO YYYY-MM-DD
                for date_field in ("date_of_application", "date_of_birth"):
                    if doc.get(date_field):
                        doc[date_field] = normalize_date(doc[date_field])

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

async def renormalize_collection(collection_name: str):
    """Re-normalize email, phone, and date fields in an existing collection."""
    coll = db[collection_name]
    cursor = coll.find({})
    fixed = 0
    async for doc in cursor:
        updates = {}
        old_email = doc.get("email", "")
        old_phone = doc.get("phone", "")
        new_email = normalize_email(old_email)
        new_phone = normalize_phone(old_phone)
        if new_email != old_email:
            updates["email"] = new_email
        if new_phone != old_phone:
            updates["phone"] = new_phone
        # Normalize date fields
        for df_field in ("date_of_application", "date_of_birth"):
            old_val = doc.get(df_field)
            if old_val:
                new_val = normalize_date(old_val)
                if new_val and new_val != str(old_val):
                    updates[df_field] = new_val
        if updates:
            await coll.update_one({"_id": doc["_id"]}, {"$set": updates})
            fixed += 1
    return fixed


async def reprocess_matching():
    """Rebuild registered_candidates via INNER JOIN — merges ALL fields from both collections.
    Re-normalizes identifiers before matching to catch format mismatches."""

    # Step 1: Re-normalize existing data in place
    await renormalize_collection("naukri_applies")
    await renormalize_collection("pipeline_data")

    # Step 2: Load fresh data
    naukri_list = await db.naukri_applies.find({}).to_list(None)
    pipeline_list = await db.pipeline_data.find({}).to_list(None)

    # Step 3: Build lookup dicts with normalized keys
    pipeline_by_email = {}
    pipeline_by_phone = {}
    for p in pipeline_list:
        em = normalize_email(p.get('email'))
        ph = normalize_phone(p.get('phone'))
        if em:
            pipeline_by_email[em] = p
        if ph:
            pipeline_by_phone[ph] = p

    await db.registered_candidates.drop()

    registered_docs = []
    _skip_keys = {"_id", "_is_registered", "created_at", "updated_at"}

    for naukri in naukri_list:
        # Re-normalize naukri identifiers for matching
        email = normalize_email(naukri.get('email'))
        phone = normalize_phone(naukri.get('phone'))

        # Match on email OR phone (either is sufficient)
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
    """Shortlisted: registered_candidates WHERE email_type matches shortlist"""
    skip = (page - 1) * limit
    query = {"email_type": {"$regex": "shortlist", "$options": "i"}}
    total = await db.registered_candidates.count_documents(query)
    cursor = db.registered_candidates.find(query, {
        "_id": 0, "name": 1, "email": 1, "phone": 1, "job_title": 1,
        "date_of_application": 1, "gender": 1, "location": 1, "email_type": 1
    }).skip(skip).limit(limit)
    data = await cursor.to_list(None)
    return {
        "data": data, "total": total, "page": page, "limit": limit,
        "columns": ["name", "email", "phone", "job_title", "date_of_application", "gender", "location", "email_type"]
    }

@api_router.get("/data/rejected")
async def get_rejected(
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=500),
    user: str = Depends(get_current_user)
):
    """Rejected: registered_candidates WHERE email_type IN (reject, rejected)"""
    skip = (page - 1) * limit
    query = {"email_type": {"$regex": "^reject", "$options": "i"}}
    total = await db.registered_candidates.count_documents(query)
    cursor = db.registered_candidates.find(query, {
        "_id": 0, "name": 1, "email": 1, "phone": 1, "job_title": 1,
        "date_of_application": 1, "gender": 1, "date_of_birth": 1,
        "location": 1, "email_type": 1
    }).skip(skip).limit(limit)
    data = await cursor.to_list(None)
    return {
        "data": data, "total": total, "page": page, "limit": limit,
        "columns": ["name", "email", "phone", "job_title", "date_of_application", "gender", "date_of_birth", "location", "email_type"]
    }

@api_router.get("/data/scheduled")
async def get_scheduled(
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=500),
    user: str = Depends(get_current_user)
):
    """Scheduled: Shortlisted AND schedule_date/time NOT NULL (strict hierarchy)"""
    skip = (page - 1) * limit
    query = {
        "email_type": {"$regex": "shortlist", "$options": "i"},
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
    """Not Scheduled: Shortlisted AND schedule_date/time IS NULL (strict hierarchy)"""
    skip = (page - 1) * limit
    query = {
        "email_type": {"$regex": "shortlist", "$options": "i"},
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
    """Attended: Shortlisted AND Scheduled AND otp_verified NOT NULL (strict hierarchy)"""
    skip = (page - 1) * limit
    query = {
        "email_type": {"$regex": "shortlist", "$options": "i"},
        "schedule_date": _not_null_filter,
        "schedule_time": _not_null_filter,
        "otp_verified": _not_null_filter
    }
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
    """Not Attended: Shortlisted AND Scheduled AND otp_verified IS NULL (strict hierarchy)"""
    skip = (page - 1) * limit
    query = {
        "email_type": {"$regex": "shortlist", "$options": "i"},
        "schedule_date": _not_null_filter,
        "schedule_time": _not_null_filter,
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
    """Aggregate funnel statistics grouped by job_title from registered_candidates.
    Uses STRICT HIERARCHY: Shortlisted/Rejected from email_type,
    Scheduled = subset of Shortlisted, Attended = subset of Scheduled."""

    # Helper expressions for reuse
    _is_shortlisted = {"$regexMatch": {"input": {"$ifNull": ["$email_type", ""]}, "regex": "shortlist", "options": "i"}}
    _has_schedule = {"$and": [
        {"$ne": [{"$ifNull": ["$schedule_date", ""]}, ""]},
        {"$ne": [{"$ifNull": ["$schedule_date", None]}, None]},
        {"$ne": [{"$ifNull": ["$schedule_time", ""]}, ""]},
        {"$ne": [{"$ifNull": ["$schedule_time", None]}, None]}
    ]}
    _no_schedule = {"$and": [
        {"$or": [{"$eq": [{"$ifNull": ["$schedule_date", None]}, None]}, {"$eq": ["$schedule_date", ""]}]},
        {"$or": [{"$eq": [{"$ifNull": ["$schedule_time", None]}, None]}, {"$eq": ["$schedule_time", ""]}]}
    ]}
    _has_otp = {"$and": [
        {"$ne": [{"$ifNull": ["$otp_verified", ""]}, ""]},
        {"$ne": [{"$ifNull": ["$otp_verified", None]}, None]}
    ]}
    _no_otp = {"$or": [
        {"$eq": [{"$ifNull": ["$otp_verified", None]}, None]},
        {"$eq": ["$otp_verified", ""]}
    ]}

    pipeline = [
        {"$match": match_filter},
        {"$group": {
            "_id": "$job_title",
            "total_applicants": {"$sum": 1},
            # Shortlisted: email_type matches shortlist
            "shortlisted": {"$sum": {"$cond": [_is_shortlisted, 1, 0]}},
            # Rejected: email_type matches reject
            "rejected": {"$sum": {"$cond": [
                {"$regexMatch": {"input": {"$ifNull": ["$email_type", ""]}, "regex": "^reject", "options": "i"}},
                1, 0
            ]}},
            # Scheduled = Shortlisted AND has schedule
            "scheduled": {"$sum": {"$cond": [
                {"$and": [_is_shortlisted, _has_schedule]},
                1, 0
            ]}},
            # Not Scheduled = Shortlisted AND no schedule
            "not_scheduled": {"$sum": {"$cond": [
                {"$and": [_is_shortlisted, _no_schedule]},
                1, 0
            ]}},
            # Attended = Shortlisted AND scheduled AND otp_verified
            "attended": {"$sum": {"$cond": [
                {"$and": [_is_shortlisted, _has_schedule, _has_otp]},
                1, 0
            ]}},
            # Not Attended = Shortlisted AND scheduled AND no otp_verified
            "not_attended": {"$sum": {"$cond": [
                {"$and": [_is_shortlisted, _has_schedule, _no_otp]},
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
    """Job role-wise funnel statistics with date & search filters.
    Includes total_naukri (unique applicants from naukri_applies per role) and unregistered counts."""
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

    # Get unique naukri applicant counts per job role
    naukri_match = {}
    if startDate or endDate:
        naukri_match["date_of_application"] = match.get("date_of_application", {})
    if search:
        naukri_match["job_title"] = match.get("job_title", {})

    naukri_pipeline = [
        {"$match": naukri_match} if naukri_match else {"$match": {}},
        {"$group": {
            "_id": {"job_title": "$job_title", "email": "$email", "phone": "$phone"},
        }},
        {"$group": {
            "_id": "$_id.job_title",
            "total_naukri": {"$sum": 1}
        }},
        {"$project": {"_id": 0, "job_role": "$_id", "total_naukri": 1}}
    ]
    naukri_counts = await db.naukri_applies.aggregate(naukri_pipeline).to_list(None)
    naukri_map = {r["job_role"]: r["total_naukri"] for r in naukri_counts}

    # Merge naukri counts into results and compute unregistered
    for r in results:
        role = r["job_role"]
        r["total_naukri"] = naukri_map.get(role, 0)
        r["total_registered"] = r["total_applicants"]
        r["total_unregistered"] = max(r["total_naukri"] - r["total_registered"], 0)

    # Add roles that have naukri applicants but NO registered (all unregistered)
    existing_roles = {r["job_role"] for r in results}
    for role, count in naukri_map.items():
        if role not in existing_roles:
            results.append({
                "job_role": role,
                "total_naukri": count,
                "total_applicants": 0,
                "total_registered": 0,
                "total_unregistered": count,
                "shortlisted": 0, "rejected": 0,
                "scheduled": 0, "not_scheduled": 0,
                "attended": 0, "not_attended": 0
            })

    total_registered = sum(r.get("total_registered", r.get("total_applicants", 0)) for r in results)
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
    """Derive candidate status using STRICT HIERARCHY based on email_type field.
    Hierarchy: Registered → Shortlisted → Interview Scheduled → Attended/Not Attended
               Registered → Rejected
    """
    email_type = str(doc.get("email_type") or "").strip()
    otp_verified = str(doc.get("otp_verified") or "").strip()
    schedule_date = str(doc.get("schedule_date") or "").strip()
    schedule_time = str(doc.get("schedule_time") or "").strip()

    # Rejected: email_type IN ('reject', 'rejected')
    if re.match(r"^reject", email_type, re.IGNORECASE):
        return "Rejected"

    # Shortlisted hierarchy: email_type IN ('shortlist', 'shortlisted')
    if re.search(r"shortlist", email_type, re.IGNORECASE):
        # Interview Scheduled = Shortlisted AND has schedule
        if schedule_date and schedule_time:
            # Attended = Interview Scheduled AND otp_verified
            if otp_verified:
                return "Attended"
            # Not Attended = Interview Scheduled AND no otp_verified
            return "Not Attended"
        # Shortlisted but not yet scheduled
        return "Shortlisted"

    return "Registered"


@api_router.get("/role")
async def get_role_applicants(
    jobRole: str = Query(..., description="Job role to analyze"),
    startDate: str = Query(None),
    endDate: str = Query(None),
    search: str = Query(None),
    page: int = Query(1, ge=1),
    limit: int = Query(100, ge=1, le=500),
    user: str = Depends(get_current_user)
):
    """Lightweight applicant table — no score fetching. Supports search by name/email/phone."""
    role = jobRole.strip()
    match = {"job_title": {"$regex": f"^{re.escape(role)}$", "$options": "i"}}
    if startDate or endDate:
        date_filter = {}
        if startDate:
            date_filter["$gte"] = startDate
        if endDate:
            date_filter["$lte"] = endDate
        match["date_of_application"] = date_filter
    if search:
        search_re = {"$regex": re.escape(search), "$options": "i"}
        match["$or"] = [{"name": search_re}, {"email": search_re}, {"phone": search_re}]

    total = await db.registered_candidates.count_documents(match)
    skip = (page - 1) * limit
    cursor = db.registered_candidates.find(match, {
        "_id": 0, "name": 1, "email": 1, "phone": 1, "gender": 1,
        "date_of_birth": 1, "date_of_application": 1,
        "email_type": 1, "otp_verified": 1,
        "schedule_date": 1, "schedule_time": 1
    }).skip(skip).limit(limit)
    docs = await cursor.to_list(None)

    applicants = [{
        "name": doc.get("name") or "-",
        "email": doc.get("email") or "-",
        "phone": doc.get("phone") or "-",
        "gender": doc.get("gender") or "-",
        "date_of_birth": doc.get("date_of_birth") or "-",
        "date_of_application": doc.get("date_of_application") or "-",
        "status": derive_status(doc),
    } for doc in docs]

    return {
        "data": applicants,
        "total": total,
        "page": page,
        "limit": limit,
        "columns": ["name", "email", "phone", "gender", "date_of_birth", "date_of_application", "status"]
    }


# ============ GLOBAL APPLICANTS TABLE ============

@api_router.get("/applicants")
async def get_global_applicants(
    jobRole: str = Query(None),
    dateType: str = Query("Registered"),
    startDate: str = Query(None),
    endDate: str = Query(None),
    search: str = Query(None),
    page: int = Query(1, ge=1),
    limit: int = Query(100, ge=1, le=500),
    user: str = Depends(get_current_user)
):
    """Global registered applicants table with job role, date type, and search filters."""
    match = {}

    # Job role filter
    if jobRole and jobRole.strip() and jobRole.strip().lower() != "all jobs":
        match["job_title"] = {"$regex": f"^{re.escape(jobRole.strip())}$", "$options": "i"}

    # Date filter based on dateType
    if startDate and endDate:
        date_field = "last_update" if dateType == "Registered" else "schedule_date"
        match[date_field] = {"$gte": startDate, "$lte": endDate}

    # Search filter
    if search:
        search_re = {"$regex": re.escape(search), "$options": "i"}
        match["$or"] = [
            {"name": search_re}, {"email": search_re},
            {"phone": search_re}, {"job_title": search_re}
        ]

    total = await db.registered_candidates.count_documents(match)
    skip = (page - 1) * limit
    cursor = db.registered_candidates.find(match, {"_id": 0}).sort("name", 1).skip(skip).limit(limit)
    docs = await cursor.to_list(None)

    applicants = []
    for doc in docs:
        email_type = str(doc.get("email_type") or "").strip().lower()
        otp_verified = str(doc.get("otp_verified") or "").strip()
        schedule_date = str(doc.get("schedule_date") or "").strip()
        schedule_time = str(doc.get("schedule_time") or "").strip()
        result_status_raw = str(doc.get("result_status") or "").strip()

        # Derive registered_status using strict priority hierarchy
        if (email_type in ("shortlist", "shortlisted") and schedule_date and schedule_time
                and otp_verified and otp_verified != "0"):
            reg_status = "Attended"
        elif (email_type in ("shortlist", "shortlisted") and schedule_date and schedule_time
                and (not otp_verified or otp_verified == "0")):
            reg_status = "Not Attended"
        elif email_type in ("shortlist", "shortlisted") and schedule_date and schedule_time:
            reg_status = "Interview Scheduled"
        elif email_type in ("shortlist", "shortlisted") and (not schedule_date) and (not schedule_time):
            reg_status = "Interview Not Scheduled"
        elif email_type in ("reject", "rejected"):
            reg_status = "Rejected"
        elif email_type in ("shortlist", "shortlisted"):
            reg_status = "Shortlisted"
        else:
            reg_status = "Registered"

        # Result status only for Attended
        if reg_status == "Attended":
            res_status = result_status_raw if result_status_raw and result_status_raw not in ("-", "") else "NA"
        else:
            res_status = "NA"

        applicants.append({
            "name": doc.get("name") or "-",
            "email": doc.get("email") or "-",
            "phone": doc.get("phone") or "-",
            "college": doc.get("college") or "-",
            "degree": doc.get("degree") or "-",
            "job_role": doc.get("job_role") or doc.get("job_title") or "-",
            "registered_status": reg_status,
            "registered_date": doc.get("last_update") or "-",
            "schedule_date": doc.get("schedule_date") or "-",
            "schedule_time": doc.get("schedule_time") or "-",
            "attended_or_not": "Attended" if reg_status == "Attended" else "Not Attended",
            "result_status": res_status,
        })

    return {
        "data": applicants,
        "total": total,
        "page": page,
        "limit": limit,
    }


# ============ ATTENDED APPLICANTS MODULE ============

@api_router.get("/attended-roles")
async def get_attended_roles(user: str = Depends(get_current_user)):
    """Job role boxes with attended applicant counts."""
    pipeline = [
        {"$match": {
            "email_type": {"$regex": "shortlist", "$options": "i"},
            "schedule_date": _not_null_filter,
            "schedule_time": _not_null_filter,
            "otp_verified": _not_null_filter,
        }},
        {"$group": {"_id": "$job_title", "count": {"$sum": 1}}},
        {"$sort": {"_id": 1}},
        {"$project": {"_id": 0, "job_role": "$_id", "count": 1}}
    ]
    roles = await db.registered_candidates.aggregate(pipeline).to_list(None)
    return {"job_roles": roles}


@api_router.get("/attended")
async def get_attended_applicants(
    jobRole: str = Query(None),
    startDate: str = Query(None),
    endDate: str = Query(None),
    search: str = Query(None),
    round: str = Query(None),
    page: int = Query(1, ge=1),
    limit: int = Query(100, ge=1, le=500),
    user: str = Depends(get_current_user)
):
    """Global attended applicants table with scores."""

    # Base match: registered candidates who attended (otp_verified NOT NULL)
    match = {
        "otp_verified": _not_null_filter,
    }

    # Optional job role filter
    if jobRole and jobRole.strip() and jobRole.strip().lower() != "all jobs":
        role = jobRole.strip()
        match["job_title"] = {"$regex": f"^{re.escape(role)}$", "$options": "i"}

    # Date filter on schedule_date, only when BOTH dates provided
    if startDate and endDate:
        match["schedule_date"] = {**_not_null_filter, "$gte": startDate, "$lte": endDate}
    if search:
        search_re = {"$regex": re.escape(search), "$options": "i"}
        match["$or"] = [{"name": search_re}, {"email": search_re}, {"phone": search_re}, {"job_title": search_re}]

    # Pre-fetch all score records and build lookups (batch — avoids N+1)
    score_records = await db.score_sheet.find({}, {"_id": 0}).to_list(None)
    score_by_email = {}
    score_by_phone = {}
    for sr in score_records:
        se = normalize_email(sr.get("email"))
        sp = normalize_phone(sr.get("phone"))
        if se:
            score_by_email.setdefault(se, []).append(sr)
        if sp:
            score_by_phone.setdefault(sp, []).append(sr)

    # Fetch all matching attended candidates (pre-filter, then apply round filter in-memory)
    cursor = db.registered_candidates.find(match, {"_id": 0}).sort("name", 1)
    all_docs = await cursor.to_list(None)

    # Build applicant rows with scores
    applicants = []
    for doc in all_docs:
        doc_email = normalize_email(doc.get("email"))
        doc_phone = normalize_phone(doc.get("phone"))

        # Fetch matched scores
        matched_scores = []
        if doc_email and doc_email in score_by_email:
            matched_scores.extend(score_by_email[doc_email])
        if doc_phone and doc_phone in score_by_phone:
            for s in score_by_phone[doc_phone]:
                if s not in matched_scores:
                    matched_scores.append(s)

        # Map round_name → column
        round_scores = {}
        for sr in matched_scores:
            rn = sr.get("round_name", "").strip().lower()
            canonical = ROUND_NAME_MAP.get(rn)
            if canonical:
                round_scores[canonical] = sr.get("score", 0)

        # Apply round filter: only include rows that have a score for the selected round
        if round:
            canonical_round = ROUND_NAME_MAP.get(round.strip().lower())
            if canonical_round and canonical_round not in round_scores:
                continue

        row = {
            "name": doc.get("name") or "-",
            "email": doc.get("email") or "-",
            "phone": doc.get("phone") or "-",
            "college": doc.get("college") or "-",
            "degree": doc.get("degree") or "-",
            "course": doc.get("course") or "-",
            "year_of_graduation": doc.get("year_of_graduation") or "-",
            "job_role": doc.get("job_role") or doc.get("job_title") or "-",
            "schedule_date": doc.get("schedule_date") or "-",
            "result_status": doc.get("result_status") or "-",
        }
        for col in SCORE_ROUND_COLUMNS:
            row[col] = round_scores.get(col, "-")

        applicants.append(row)

    total = len(applicants)
    # Server-side pagination AFTER all filters
    start = (page - 1) * limit
    end = start + limit
    paginated = applicants[start:end]

    columns = ["name", "email", "phone", "college", "degree", "course",
               "year_of_graduation", "job_role", "schedule_date", "result_status"] + SCORE_ROUND_COLUMNS

    return {
        "data": paginated,
        "total": total,
        "page": page,
        "limit": limit,
        "columns": columns
    }


# ============ SCORE SHEET UPLOAD ============

SCORE_ROUND_COLUMNS = ["ZA", "C++", "Java", "BA", "LA", "Mensa Org", "Accounts2", "Accounts1", "BE", "Mensa", "BP"]
# Lowercase lookup map for case-insensitive matching
ROUND_NAME_MAP = {r.strip().lower(): r for r in SCORE_ROUND_COLUMNS}


@api_router.post("/upload/scoresheet")
async def upload_score_sheet(
    file: UploadFile = File(...),
    user: str = Depends(get_current_user)
):
    """Upload score sheet (CSV/XLSX). Fields: name, email, phone, score, round_name.
    Multiple rows per applicant (different rounds) are allowed — no overwrite."""
    content = await file.read()
    df = parse_file(content, file.filename)
    df.columns = df.columns.str.strip().str.lower()

    required = {"name", "email", "phone", "score", "round_name"}
    if not required.issubset(set(df.columns)):
        missing = required - set(df.columns)
        raise HTTPException(status_code=400, detail=f"Missing columns: {missing}")

    inserted = 0
    errors = []

    for idx, row in df.iterrows():
        try:
            email = normalize_email(row.get("email"))
            phone = normalize_phone(row.get("phone"))
            name = str(row.get("name") or "").strip()
            round_name = str(row.get("round_name") or "").strip()
            score_val = row.get("score")

            if not email and not phone:
                errors.append(f"Row {idx + 2}: Missing email and phone")
                continue
            if not round_name:
                errors.append(f"Row {idx + 2}: Missing round_name")
                continue

            # Parse score as float
            try:
                score = float(score_val) if not pd.isna(score_val) else 0.0
            except (ValueError, TypeError):
                score = 0.0

            doc = {
                "name": name,
                "email": email,
                "phone": phone,
                "score": score,
                "round_name": round_name,
                "created_at": datetime.now(timezone.utc).isoformat()
            }

            await db.score_sheet.insert_one(doc)
            inserted += 1

        except Exception as e:
            errors.append(f"Row {idx + 2}: {str(e)}")

    return {
        "success": True,
        "message": f"Score sheet uploaded. Inserted: {inserted}",
        "inserted": inserted,
        "errors": errors[:20]
    }


# ============ BULK UPLOAD SYSTEM ============

UPLOAD_BASE = Path("/app/uploads")
BULK_TYPES = {
    "naukri": {"pending": UPLOAD_BASE / "naukri" / "pending", "processed": UPLOAD_BASE / "naukri" / "processed"},
    "pipeline": {"pending": UPLOAD_BASE / "pipeline" / "pending", "processed": UPLOAD_BASE / "pipeline" / "processed"},
    "score": {"pending": UPLOAD_BASE / "score" / "pending", "processed": UPLOAD_BASE / "score" / "processed"},
}

# Create directories on module load
for t in BULK_TYPES.values():
    t["pending"].mkdir(parents=True, exist_ok=True)
    t["processed"].mkdir(parents=True, exist_ok=True)


async def _process_naukri_file(content: bytes, filename: str) -> dict:
    """Core naukri processing — extracted from upload_naukri for reuse."""
    df = parse_file(content, filename)
    df.columns = df.columns.str.strip()
    col_map = {}
    for csv_col in df.columns:
        if csv_col in NAUKRI_COLUMN_MAP:
            col_map[csv_col] = NAUKRI_COLUMN_MAP[csv_col]
        elif csv_col.strip().lower() in _NAUKRI_CI_LOOKUP:
            col_map[csv_col] = _NAUKRI_CI_LOOKUP[csv_col.strip().lower()]
    mapped_fields = set(col_map.values())
    if "email" not in mapped_fields and "phone" not in mapped_fields:
        return {"success": False, "error": "No email/phone column found"}
    inserted = 0
    updated = 0
    for idx, row in df.iterrows():
        try:
            doc = {}
            for csv_col, db_field in col_map.items():
                doc[db_field] = clean_value(row.get(csv_col))
            for csv_col in df.columns:
                if csv_col not in col_map:
                    safe = re.sub(r'[^\w]', '_', csv_col.strip().lower()).strip('_')
                    doc[f"_extra_{safe}"] = clean_value(row.get(csv_col))
            email = normalize_email(doc.get("email"))
            phone = normalize_phone(doc.get("phone"))
            doc["email"] = email
            doc["phone"] = phone
            for date_field in ("date_of_application", "date_of_birth"):
                if doc.get(date_field):
                    doc[date_field] = normalize_date(doc[date_field])
            doc["updated_at"] = datetime.now(timezone.utc)
            if not email and not phone:
                continue
            query = {"$or": []}
            if email: query["$or"].append({"email": email})
            if phone: query["$or"].append({"phone": phone})
            existing = await db.naukri_applies.find_one(query)
            if existing:
                await db.naukri_applies.update_one({"_id": existing["_id"]}, {"$set": doc})
                updated += 1
            else:
                doc["created_at"] = datetime.now(timezone.utc)
                await db.naukri_applies.insert_one(doc)
                inserted += 1
        except Exception:
            pass
    await reprocess_matching()
    return {"success": True, "inserted": inserted, "updated": updated}


async def _process_pipeline_file(content: bytes, filename: str) -> dict:
    """Core pipeline processing — extracted from upload_pipeline for reuse."""
    df = parse_file(content, filename)
    df.columns = df.columns.str.strip()
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
    col_map = {}
    for csv_col in df.columns:
        normalized = csv_col.strip().lower()
        if normalized in _PIPELINE_CI_LOOKUP:
            db_field = _PIPELINE_CI_LOOKUP[normalized]
            col_map[csv_col] = "pipeline_id" if db_field == "id" else db_field
    mapped_fields = set(col_map.values())
    if "email" not in mapped_fields and "phone" not in mapped_fields:
        return {"success": False, "error": "No email/phone column found"}
    inserted = 0
    updated = 0
    for idx, row in df.iterrows():
        try:
            doc = {}
            for csv_col, db_field in col_map.items():
                doc[db_field] = clean_value(row.get(csv_col))
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
                continue
            query = {"$or": []}
            if email: query["$or"].append({"email": email})
            if phone: query["$or"].append({"phone": phone})
            existing = await db.pipeline_data.find_one(query)
            if existing:
                await db.pipeline_data.update_one({"_id": existing["_id"]}, {"$set": doc})
                updated += 1
            else:
                doc["created_at"] = datetime.now(timezone.utc)
                await db.pipeline_data.insert_one(doc)
                inserted += 1
        except Exception:
            pass
    await reprocess_matching()
    return {"success": True, "inserted": inserted, "updated": updated}


async def _process_score_file(content: bytes, filename: str) -> dict:
    """Core score sheet processing — extracted from upload_scoresheet for reuse."""
    df = parse_file(content, filename)
    df.columns = df.columns.str.strip().str.lower()
    required = {"name", "email", "phone", "score", "round_name"}
    if not required.issubset(set(df.columns)):
        return {"success": False, "error": f"Missing columns: {required - set(df.columns)}"}
    inserted = 0
    for idx, row in df.iterrows():
        try:
            email = normalize_email(row.get("email"))
            phone = normalize_phone(row.get("phone"))
            name = str(row.get("name") or "").strip()
            round_name = str(row.get("round_name") or "").strip()
            score_val = row.get("score")
            if not email and not phone:
                continue
            if not round_name:
                continue
            try:
                score = float(score_val) if not pd.isna(score_val) else 0.0
            except (ValueError, TypeError):
                score = 0.0
            doc = {"name": name, "email": email, "phone": phone, "score": score,
                   "round_name": round_name, "created_at": datetime.now(timezone.utc).isoformat()}
            await db.score_sheet.insert_one(doc)
            inserted += 1
        except Exception:
            pass
    return {"success": True, "inserted": inserted}


_PROCESS_FN = {
    "naukri": _process_naukri_file,
    "pipeline": _process_pipeline_file,
    "score": _process_score_file,
}

# Track processing status per file
_bulk_file_status = {}  # key: "type/filename" -> {"status": "pending"|"processing"|"processed"|"failed", "result": {...}}


@api_router.post("/bulk-upload/process-now")
async def trigger_bulk_process(user: str = Depends(get_current_user)):
    """Manually trigger immediate processing of all pending files."""
    results = {}
    for utype, dirs in BULK_TYPES.items():
        process_fn = _PROCESS_FN[utype]
        pending_dir = dirs["pending"]
        processed_dir = dirs["processed"]
        type_results = []
        for filepath in sorted(pending_dir.iterdir()):
            if not filepath.is_file():
                continue
            key = f"{utype}/{filepath.name}"
            _bulk_file_status[key] = {"status": "processing", "result": None}
            try:
                content = filepath.read_bytes()
                result = await process_fn(content, filepath.name)
                if result.get("success"):
                    shutil.move(str(filepath), str(processed_dir / filepath.name))
                    _bulk_file_status[key] = {"status": "processed", "result": result}
                else:
                    _bulk_file_status[key] = {"status": "failed", "result": result}
                type_results.append({"file": filepath.name, **result})
            except Exception as e:
                _bulk_file_status[key] = {"status": "failed", "result": {"error": str(e)}}
                type_results.append({"file": filepath.name, "success": False, "error": str(e)})
        results[utype] = type_results
    return {"success": True, "results": results}


@api_router.post("/bulk-upload/{upload_type}")
async def bulk_upload_files(
    upload_type: str,
    files: List[UploadFile] = File(...),
    user: str = Depends(get_current_user)
):
    """Save multiple files to pending directory for background processing."""
    if upload_type not in BULK_TYPES:
        raise HTTPException(status_code=400, detail=f"Invalid type: {upload_type}. Must be naukri, pipeline, or score")
    pending_dir = BULK_TYPES[upload_type]["pending"]
    saved = []
    for f in files:
        if not f.filename.lower().endswith(('.csv', '.xlsx')):
            continue
        content = await f.read()
        # Avoid name collisions with timestamp prefix
        safe_name = f"{int(datetime.now(timezone.utc).timestamp())}_{f.filename}"
        dest = pending_dir / safe_name
        dest.write_bytes(content)
        _bulk_file_status[f"{upload_type}/{safe_name}"] = {"status": "pending", "result": None}
        saved.append(safe_name)
    return {"success": True, "saved": saved, "count": len(saved)}


@api_router.delete("/bulk-upload/{upload_type}/{filename}")
async def delete_bulk_file(upload_type: str, filename: str, user: str = Depends(get_current_user)):
    """Delete a file from the pending directory."""
    if upload_type not in BULK_TYPES:
        raise HTTPException(status_code=400, detail="Invalid type")
    filepath = BULK_TYPES[upload_type]["pending"] / filename
    if not filepath.exists():
        raise HTTPException(status_code=404, detail="File not found in pending")
    filepath.unlink()
    _bulk_file_status.pop(f"{upload_type}/{filename}", None)
    return {"success": True, "deleted": filename}


@api_router.get("/bulk-upload/status")
async def bulk_upload_status(user: str = Depends(get_current_user)):
    """Return pending and processed file lists for all types."""
    result = {}
    for utype, dirs in BULK_TYPES.items():
        pending = []
        for f in sorted(dirs["pending"].iterdir()):
            if f.is_file():
                key = f"{utype}/{f.name}"
                status_info = _bulk_file_status.get(key, {"status": "pending", "result": None})
                pending.append({"name": f.name, "size": f.stat().st_size, "status": status_info["status"],
                                "result": status_info.get("result")})
        processed = [{"name": f.name, "size": f.stat().st_size} for f in sorted(dirs["processed"].iterdir()) if f.is_file()]
        result[utype] = {"pending": pending, "processed": processed}
    return result


async def _run_bulk_processor():
    """Background worker: process all pending files every 30 seconds."""
    while True:
        await asyncio.sleep(30)
        for utype, dirs in BULK_TYPES.items():
            process_fn = _PROCESS_FN[utype]
            pending_dir = dirs["pending"]
            processed_dir = dirs["processed"]
            for filepath in sorted(pending_dir.iterdir()):
                if not filepath.is_file():
                    continue
                key = f"{utype}/{filepath.name}"
                if _bulk_file_status.get(key, {}).get("status") == "processing":
                    continue
                _bulk_file_status[key] = {"status": "processing", "result": None}
                try:
                    content = filepath.read_bytes()
                    result = await process_fn(content, filepath.name)
                    if result.get("success"):
                        shutil.move(str(filepath), str(processed_dir / filepath.name))
                        _bulk_file_status[key] = {"status": "processed", "result": result}
                    else:
                        _bulk_file_status[key] = {"status": "failed", "result": result}
                except Exception as e:
                    logger.error(f"Bulk process error ({key}): {e}")
                    _bulk_file_status[key] = {"status": "failed", "result": {"error": str(e)}}


@api_router.post("/reprocess")
async def trigger_reprocess(user: str = Depends(get_current_user)):
    """Re-normalize all data and rebuild registered_candidates from scratch."""
    naukri_before = await db.naukri_applies.count_documents({})
    pipeline_before = await db.pipeline_data.count_documents({})
    registered_before = await db.registered_candidates.count_documents({})

    await reprocess_matching()

    registered_after = await db.registered_candidates.count_documents({})
    return {
        "success": True,
        "message": "Reprocessing complete — data re-normalized and matching rebuilt",
        "naukri_count": naukri_before,
        "pipeline_count": pipeline_before,
        "registered_before": registered_before,
        "registered_after": registered_after,
        "change": registered_after - registered_before,
    }


@api_router.get("/debug/matching")
async def debug_matching(user: str = Depends(get_current_user)):
    """Debug endpoint: shows every naukri record, its normalized identifiers,
    and whether a pipeline match was found (and why/why not)."""
    naukri_list = await db.naukri_applies.find({}, {"_id": 0}).to_list(None)
    pipeline_list = await db.pipeline_data.find({}, {"_id": 0}).to_list(None)

    # Build normalized pipeline lookups
    pipeline_by_email = {}
    pipeline_by_phone = {}
    for p in pipeline_list:
        em = normalize_email(p.get('email'))
        ph = normalize_phone(p.get('phone'))
        if em:
            pipeline_by_email[em] = {"name": p.get("name"), "email": em, "phone": ph, "job_role": p.get("job_role")}
        if ph:
            pipeline_by_phone[ph] = {"name": p.get("name"), "email": em, "phone": ph, "job_role": p.get("job_role")}

    results = []
    matched_count = 0
    unmatched_count = 0

    for naukri in naukri_list:
        n_email = normalize_email(naukri.get('email'))
        n_phone = normalize_phone(naukri.get('phone'))

        match_type = None
        pipeline_info = None

        if n_email and n_email in pipeline_by_email:
            match_type = "email"
            pipeline_info = pipeline_by_email[n_email]
        elif n_phone and n_phone in pipeline_by_phone:
            match_type = "phone"
            pipeline_info = pipeline_by_phone[n_phone]

        is_matched = match_type is not None
        if is_matched:
            matched_count += 1
        else:
            unmatched_count += 1

        results.append({
            "naukri_name": naukri.get("name"),
            "naukri_email": n_email,
            "naukri_phone": n_phone,
            "naukri_job_title": naukri.get("job_title"),
            "matched": is_matched,
            "match_type": match_type,
            "pipeline_match": pipeline_info,
        })

    return {
        "total_naukri": len(naukri_list),
        "total_pipeline": len(pipeline_list),
        "matched": matched_count,
        "unmatched": unmatched_count,
        "details": results,
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

    # Start bulk upload background processor
    asyncio.create_task(_run_bulk_processor())
    logger.info("Bulk upload background processor started (30s interval)")

@app.on_event("shutdown")
async def shutdown_db_client():
    client.close()
