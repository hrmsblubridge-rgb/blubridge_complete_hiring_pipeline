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
from bson import ObjectId

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
    if data.username == "Admin User" and data.password == "Admin User":
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
        await _sync_job_titles_master()

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


async def _persist_derived_fields(collection_name: str):
    """Compute & persist `_college_status`, `_nirf_category`, `_college_resolved`,
    `_match_confidence`, `_normalized_job_role` for every document in `collection_name`.
    Used after `reprocess_matching` and bulk uploads to keep endpoints fast."""
    from pymongo import UpdateOne
    coll = db[collection_name]
    rank_lookup = await _build_college_rank_lookup()
    mappings = await _get_job_keyword_mappings()

    ops = []
    cursor = coll.find({}, {"_id": 1, "ug_university": 1, "pg_university": 1, "job_title": 1})
    async for doc in cursor:
        cc = _classify_college(doc, rank_lookup)
        cs = cc["college_status"]
        cat = "NIRF" if cs.startswith("NIRF - #") else "Non NIRF"
        normalized_role = _resolve_normalized_job_role(doc.get("job_title") or "", mappings)
        ops.append(UpdateOne(
            {"_id": doc["_id"]},
            {"$set": {
                "_college_status": cs,
                "_nirf_category": cat,
                "_college_resolved": cc.get("college") or "-",
                "_match_confidence": cc.get("match_confidence") or None,
                "_normalized_job_role": normalized_role or "Unknown",
            }}
        ))
        if len(ops) >= 1000:
            await coll.bulk_write(ops, ordered=False)
            ops = []
    if ops:
        await coll.bulk_write(ops, ordered=False)

    await coll.create_index("_college_status")
    await coll.create_index("_nirf_category")
    await coll.create_index("_normalized_job_role")


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

    # Persist derived fields so endpoints can filter/aggregate at DB level.
    await _persist_derived_fields("registered_candidates")
    await _persist_derived_fields("naukri_applies")

# ============ JOB ROLE NORMALIZATION ============

def _normalize_text_for_matching(text: str) -> str:
    """Normalize text for keyword matching: lowercase, trim, remove punctuation."""
    if not text:
        return ""
    return re.sub(r'[^\w\s]', '', text.lower().strip())


async def _sync_job_titles_master():
    """Extract distinct job titles from naukri_applies and upsert into job_titles_master."""
    pipeline = [
        {"$match": {"job_title": {"$nin": [None, ""]}}},
        {"$group": {"_id": "$job_title"}},
    ]
    results = await db.naukri_applies.aggregate(pipeline).to_list(None)
    for r in results:
        raw = str(r["_id"]).strip()
        if not raw:
            continue
        normalized = _normalize_text_for_matching(raw)
        if not normalized:
            continue
        existing = await db.job_titles_master.find_one({"normalized_job_title": normalized})
        if not existing:
            await db.job_titles_master.insert_one({
                "raw_job_title": raw,
                "normalized_job_title": normalized,
                "is_mapped": False,
            })


async def _get_job_keyword_mappings() -> list:
    """Fetch all job keyword mappings from DB."""
    return await db.job_keyword_mapping.find({}, {"_id": 0}).to_list(None)


def _resolve_normalized_job_role(job_title: str, mappings: list) -> str:
    """Given a raw job_title and keyword mappings, return the canonical job role.
    Matches by exact normalized comparison (keywords are full job titles).
    Returns first match or falls back to raw job_title."""
    if not job_title:
        return job_title or "Unknown"
    normalized_title = _normalize_text_for_matching(job_title)
    for mapping in mappings:
        for keyword in mapping.get("keywords", []):
            kw_normalized = _normalize_text_for_matching(keyword)
            if kw_normalized and kw_normalized == normalized_title:
                return mapping["job_role"]
    return job_title


class JobKeywordMappingCreate(BaseModel):
    job_role: str
    keywords: List[str]


class JobKeywordMappingUpdate(BaseModel):
    job_role: Optional[str] = None
    keywords: Optional[List[str]] = None


@api_router.get("/job-titles/unmatched")
async def get_unmatched_job_titles(user: str = Depends(get_current_user)):
    """Return all job titles from job_titles_master that are not yet mapped."""
    titles = await db.job_titles_master.find(
        {"is_mapped": {"$ne": True}}, {"_id": 0, "raw_job_title": 1, "normalized_job_title": 1}
    ).to_list(None)
    return {"titles": [t.get("raw_job_title", t.get("normalized_job_title", "")) for t in titles if t.get("raw_job_title") or t.get("normalized_job_title")]}


@api_router.get("/job-keyword-mappings")
async def list_job_keyword_mappings(user: str = Depends(get_current_user)):
    """List all job keyword mappings."""
    mappings = await db.job_keyword_mapping.find({}).to_list(None)
    for m in mappings:
        m["id"] = str(m.pop("_id"))
    return {"mappings": mappings}


@api_router.post("/job-keyword-mappings")
async def create_job_keyword_mapping(data: JobKeywordMappingCreate, user: str = Depends(get_current_user)):
    """Create a new job keyword mapping and mark keywords as mapped."""
    keywords = [k.strip() for k in data.keywords if k.strip()]
    if not keywords:
        raise HTTPException(status_code=400, detail="At least one keyword is required")
    doc = {
        "job_role": data.job_role.strip(),
        "keywords": keywords,
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    result = await db.job_keyword_mapping.insert_one(doc)
    # Mark keywords as mapped in job_titles_master
    for kw in keywords:
        norm = _normalize_text_for_matching(kw)
        if norm:
            await db.job_titles_master.update_many(
                {"normalized_job_title": norm},
                {"$set": {"is_mapped": True}}
            )
    return {"success": True, "id": str(result.inserted_id), "job_role": doc["job_role"], "keywords": doc["keywords"]}


@api_router.put("/job-keyword-mappings/{mapping_id}")
async def update_job_keyword_mapping(mapping_id: str, data: JobKeywordMappingUpdate, user: str = Depends(get_current_user)):
    """Update an existing job keyword mapping. Handles keyword add/remove and is_mapped flags."""
    try:
        oid = ObjectId(mapping_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid mapping ID")

    old_mapping = await db.job_keyword_mapping.find_one({"_id": oid})
    if not old_mapping:
        raise HTTPException(status_code=404, detail="Mapping not found")

    updates = {}
    if data.job_role is not None:
        updates["job_role"] = data.job_role.strip()

    new_keywords = None
    if data.keywords is not None:
        new_keywords = [k.strip() for k in data.keywords if k.strip()]
        updates["keywords"] = new_keywords

    if not updates:
        raise HTTPException(status_code=400, detail="No updates provided")

    await db.job_keyword_mapping.update_one({"_id": oid}, {"$set": updates})

    # Handle is_mapped flag changes for keywords
    if new_keywords is not None:
        old_keywords = set(old_mapping.get("keywords", []))
        new_keywords_set = set(new_keywords)
        removed = old_keywords - new_keywords_set
        added = new_keywords_set - old_keywords

        # Unmap removed keywords (only if not used by another mapping)
        for kw in removed:
            norm = _normalize_text_for_matching(kw)
            if norm:
                other = await db.job_keyword_mapping.find_one(
                    {"keywords": kw, "_id": {"$ne": oid}}
                )
                if not other:
                    await db.job_titles_master.update_many(
                        {"normalized_job_title": norm},
                        {"$set": {"is_mapped": False}}
                    )

        # Map newly added keywords
        for kw in added:
            norm = _normalize_text_for_matching(kw)
            if norm:
                await db.job_titles_master.update_many(
                    {"normalized_job_title": norm},
                    {"$set": {"is_mapped": True}}
                )

    return {"success": True}


@api_router.delete("/job-keyword-mappings/{mapping_id}")
async def delete_job_keyword_mapping(mapping_id: str, user: str = Depends(get_current_user)):
    """Delete a job keyword mapping and release its keywords."""
    try:
        oid = ObjectId(mapping_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid mapping ID")

    mapping = await db.job_keyword_mapping.find_one({"_id": oid})
    if not mapping:
        raise HTTPException(status_code=404, detail="Mapping not found")

    await db.job_keyword_mapping.delete_one({"_id": oid})

    # Unmap keywords (only if not used by another mapping)
    for kw in mapping.get("keywords", []):
        norm = _normalize_text_for_matching(kw)
        if norm:
            other = await db.job_keyword_mapping.find_one({"keywords": kw})
            if not other:
                await db.job_titles_master.update_many(
                    {"normalized_job_title": norm},
                    {"$set": {"is_mapped": False}}
                )

    return {"success": True}


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
    """Job role-wise funnel statistics split by NIRF / Non-NIRF.

    OPTIMIZED: Uses MongoDB aggregation pipelines on persisted derived fields
    (`_normalized_job_role`, `_nirf_category`) so all grouping happens inside
    the DB. No 20K-doc in-memory scans.
    """
    match = {}
    if startDate or endDate:
        date_filter = {}
        if startDate:
            date_filter["$gte"] = startDate
        if endDate:
            date_filter["$lte"] = endDate
        match["date_of_application"] = date_filter
    if search:
        match["_normalized_job_role"] = {"$regex": re.escape(search), "$options": "i"}

    # Helper expressions
    is_shortlisted = {"$regexMatch": {"input": {"$ifNull": ["$email_type", ""]}, "regex": "shortlist", "options": "i"}}
    is_rejected = {"$regexMatch": {"input": {"$ifNull": ["$email_type", ""]}, "regex": "^reject", "options": "i"}}
    has_schedule = {"$and": [
        {"$ne": [{"$ifNull": ["$schedule_date", ""]}, ""]},
        {"$ne": [{"$ifNull": ["$schedule_time", ""]}, ""]},
    ]}
    has_otp = {"$ne": [{"$ifNull": ["$otp_verified", ""]}, ""]}

    reg_pipeline = [
        {"$match": match},
        {"$group": {
            "_id": {
                "role": {"$ifNull": ["$_normalized_job_role", "Unknown"]},
                "cat": {"$ifNull": ["$_nirf_category", "Non NIRF"]},
            },
            "total": {"$sum": 1},
            "shortlisted": {"$sum": {"$cond": [is_shortlisted, 1, 0]}},
            "rejected": {"$sum": {"$cond": [is_rejected, 1, 0]}},
            "scheduled": {"$sum": {"$cond": [{"$and": [is_shortlisted, has_schedule]}, 1, 0]}},
            "not_scheduled": {"$sum": {"$cond": [{"$and": [is_shortlisted, {"$not": has_schedule}]}, 1, 0]}},
            "attended": {"$sum": {"$cond": [{"$and": [is_shortlisted, has_schedule, has_otp]}, 1, 0]}},
            "not_attended": {"$sum": {"$cond": [{"$and": [is_shortlisted, has_schedule, {"$not": has_otp}]}, 1, 0]}},
        }},
    ]
    reg_results = await db.registered_candidates.aggregate(reg_pipeline, allowDiskUse=False).to_list(None)
    buckets = {(r["_id"]["role"], r["_id"]["cat"]): r for r in reg_results}

    # Naukri counts per (role, cat) — distinct on email/phone
    naukri_match = {}
    if startDate or endDate:
        naukri_match["date_of_application"] = match["date_of_application"]
    if search:
        naukri_match["_normalized_job_role"] = match["_normalized_job_role"]

    naukri_pipeline = [
        {"$match": naukri_match} if naukri_match else {"$match": {}},
        {"$group": {
            "_id": {
                "role": {"$ifNull": ["$_normalized_job_role", "Unknown"]},
                "cat": {"$ifNull": ["$_nirf_category", "Non NIRF"]},
                "email": {"$ifNull": ["$email", ""]},
                "phone": {"$ifNull": ["$phone", ""]},
            },
        }},
        {"$group": {
            "_id": {"role": "$_id.role", "cat": "$_id.cat"},
            "naukri_count": {"$sum": 1},
        }},
    ]
    naukri_results = await db.naukri_applies.aggregate(naukri_pipeline, allowDiskUse=False).to_list(None)
    naukri_buckets = {(r["_id"]["role"], r["_id"]["cat"]): r["naukri_count"] for r in naukri_results}

    # Combine
    results = []
    all_keys = set(buckets.keys()) | set(naukri_buckets.keys())
    for (role, cat) in sorted(all_keys):
        b = buckets.get((role, cat), {})
        naukri_count = naukri_buckets.get((role, cat), 0)
        total = b.get("total", 0)
        results.append({
            "job_role": f"{role} - {cat}",
            "total_naukri": naukri_count,
            "total_registered": total,
            "total_unregistered": max(naukri_count - total, 0),
            "shortlisted": b.get("shortlisted", 0),
            "rejected": b.get("rejected", 0),
            "scheduled": b.get("scheduled", 0),
            "not_scheduled": b.get("not_scheduled", 0),
            "attended": b.get("attended", 0),
            "not_attended": b.get("not_attended", 0),
        })

    total_registered = sum(r["total_registered"] for r in results)
    return {"data": results, "total_registered": total_registered}


@api_router.get("/job-roles")
async def get_job_roles(user: str = Depends(get_current_user)):
    """Unique normalized job roles with registered applicant counts.
    OPTIMIZED: aggregation on persisted `_normalized_job_role`."""
    pipeline = [
        {"$match": {"_normalized_job_role": {"$nin": [None, "", "Unknown"]}}},
        {"$group": {"_id": "$_normalized_job_role", "count": {"$sum": 1}}},
        {"$sort": {"count": -1}},
        {"$project": {"_id": 0, "job_role": "$_id", "count": 1}},
    ]
    results = await db.registered_candidates.aggregate(pipeline, allowDiskUse=False).to_list(None)
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
    collegeStatus: str = Query(None),
    page: int = Query(1, ge=1),
    limit: int = Query(100, ge=1, le=500),
    user: str = Depends(get_current_user)
):
    """Global registered applicants table.

    OPTIMIZED: All filters (job role, college status, date, search) are pushed
    into a single MongoDB `.find()` using persisted `_normalized_job_role` and
    `_nirf_category` fields. Pagination via DB-level skip/limit. No 20K-doc
    in-memory scans.
    """
    match = {}

    # Date filter
    if startDate and endDate:
        date_field = "last_update" if dateType == "Registered" else "schedule_date"
        match[date_field] = {"$gte": startDate, "$lte": endDate}

    # College status filter (uses persisted _nirf_category / _college_status)
    if collegeStatus and collegeStatus.strip() and collegeStatus.strip().lower() != "all":
        fval = collegeStatus.strip()
        if fval == "NIRF":
            match["_nirf_category"] = "NIRF"
        elif fval == "Non NIRF":
            match["_nirf_category"] = "Non NIRF"
        else:
            match["_college_status"] = fval

    # Job role filter (uses persisted _normalized_job_role)
    if jobRole and jobRole.strip() and jobRole.strip().lower() != "all jobs":
        match["_normalized_job_role"] = {"$regex": f"^{re.escape(jobRole.strip())}$", "$options": "i"}

    # Search filter
    if search:
        search_re = {"$regex": re.escape(search), "$options": "i"}
        match["$or"] = [
            {"name": search_re}, {"email": search_re},
            {"phone": search_re}, {"_normalized_job_role": search_re},
        ]

    # DB-level count + paginated fetch with stable sort on `name`
    total = await db.registered_candidates.count_documents(match)
    skip = (page - 1) * limit

    projection = {
        "_id": 0, "name": 1, "email": 1, "phone": 1,
        "_college_status": 1, "_college_resolved": 1, "_match_confidence": 1,
        "_normalized_job_role": 1,
        "degree": 1, "email_type": 1, "otp_verified": 1,
        "schedule_date": 1, "schedule_time": 1, "result_status": 1,
        "last_update": 1,
    }

    # Use aggregation for sorted pagination (Atlas-friendly: $sort with $limit
    # uses bounded memory after $match narrows result set, but we add an index
    # on `name` to avoid 32MB sort cap for large unfiltered result sets).
    pipeline = [
        {"$match": match},
        {"$sort": {"name": 1}},
        {"$skip": skip},
        {"$limit": limit},
        {"$project": projection},
    ]
    docs = await db.registered_candidates.aggregate(pipeline, allowDiskUse=False).to_list(None)

    applicants = []
    for doc in docs:
        cs = doc.get("_college_status") or "Non NIRF"
        normalized_role = doc.get("_normalized_job_role") or doc.get("job_title") or "Unknown"

        email_type = str(doc.get("email_type") or "").strip().lower()
        otp_verified = str(doc.get("otp_verified") or "").strip()
        schedule_date = str(doc.get("schedule_date") or "").strip()
        schedule_time = str(doc.get("schedule_time") or "").strip()
        result_status_raw = str(doc.get("result_status") or "").strip()

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

        if reg_status == "Attended":
            res_status = result_status_raw if result_status_raw and result_status_raw not in ("-", "") else "NA"
        else:
            res_status = "NA"

        applicants.append({
            "name": doc.get("name") or "-",
            "email": doc.get("email") or "-",
            "phone": doc.get("phone") or "-",
            "college_status": cs,
            "college": doc.get("_college_resolved") or "-",
            "match_confidence": doc.get("_match_confidence") or "-",
            "degree": doc.get("degree") or "-",
            "job_role": normalized_role or "-",
            "registered_status": reg_status,
            "registered_date": doc.get("last_update") or "-",
            "schedule_date": doc.get("schedule_date") or "-",
            "schedule_time": doc.get("schedule_time") or "-",
            "attended_or_not": "Attended" if reg_status == "Attended" else "Not Attended",
            "result_status": res_status,
        })

    return {"data": applicants, "total": total, "page": page, "limit": limit}


# ============ ATTENDED APPLICANTS MODULE ============

@api_router.get("/attended-roles")
async def get_attended_roles(user: str = Depends(get_current_user)):
    """Job role boxes with attended applicant counts.
    OPTIMIZED: aggregation on persisted `_normalized_job_role`."""
    pipeline = [
        {"$match": {
            "email_type": {"$regex": "shortlist", "$options": "i"},
            "schedule_date": _not_null_filter,
            "schedule_time": _not_null_filter,
            "otp_verified": _not_null_filter,
        }},
        {"$group": {
            "_id": {"$ifNull": ["$_normalized_job_role", "Unknown"]},
            "count": {"$sum": 1},
        }},
        {"$sort": {"_id": 1}},
        {"$project": {"_id": 0, "job_role": "$_id", "count": 1}},
    ]
    roles = await db.registered_candidates.aggregate(pipeline, allowDiskUse=False).to_list(None)
    return {"job_roles": roles}


@api_router.get("/attended")
async def get_attended_applicants(
    jobRole: str = Query(None),
    startDate: str = Query(None),
    endDate: str = Query(None),
    search: str = Query(None),
    round: str = Query(None),
    collegeStatus: str = Query(None),
    page: int = Query(1, ge=1),
    limit: int = Query(100, ge=1, le=500),
    user: str = Depends(get_current_user)
):
    """Global attended applicants table with scores.
    OPTIMIZED: filters pushed to DB; pagination at DB level; scores fetched
    for the current page only."""

    match = {"otp_verified": _not_null_filter}

    if startDate and endDate:
        match["schedule_date"] = {**_not_null_filter, "$gte": startDate, "$lte": endDate}

    # College status filter via persisted _nirf_category / _college_status
    if collegeStatus and collegeStatus.strip() and collegeStatus.strip().lower() != "all":
        fval = collegeStatus.strip()
        if fval == "NIRF":
            match["_nirf_category"] = "NIRF"
        elif fval == "Non NIRF":
            match["_nirf_category"] = "Non NIRF"
        else:
            match["_college_status"] = fval

    # Job role filter via persisted _normalized_job_role
    if jobRole and jobRole.strip() and jobRole.strip().lower() != "all jobs":
        match["_normalized_job_role"] = {"$regex": f"^{re.escape(jobRole.strip())}$", "$options": "i"}

    if search:
        search_re = {"$regex": re.escape(search), "$options": "i"}
        match["$or"] = [
            {"name": search_re}, {"email": search_re},
            {"phone": search_re}, {"_normalized_job_role": search_re},
        ]

    # Round filter requires score data; if specified, intersect with score_sheet identifiers
    if round:
        canonical_round = ROUND_NAME_MAP.get(round.strip().lower())
        if canonical_round:
            score_emails = set()
            score_phones = set()
            async for sr in db.score_sheet.find(
                {"round_name": {"$regex": f"^{re.escape(canonical_round)}$", "$options": "i"}},
                {"_id": 0, "email": 1, "phone": 1}
            ):
                se = normalize_email(sr.get("email"))
                sp = normalize_phone(sr.get("phone"))
                if se: score_emails.add(se)
                if sp: score_phones.add(sp)
            id_filter = []
            if score_emails:
                id_filter.append({"email": {"$in": list(score_emails)}})
            if score_phones:
                id_filter.append({"phone": {"$in": list(score_phones)}})
            if id_filter:
                # combine with existing match (preserve existing $or if any)
                round_or = {"$or": id_filter} if len(id_filter) > 1 else id_filter[0]
                match = {"$and": [match, round_or]}
            else:
                # No scores for this round — empty result
                return {"data": [], "total": 0, "page": page, "limit": limit,
                        "columns": ["name", "email", "phone", "college_status", "college",
                                    "degree", "course", "year_of_graduation", "job_role",
                                    "schedule_date", "result_status"] + SCORE_ROUND_COLUMNS}

    total = await db.registered_candidates.count_documents(match)
    skip = (page - 1) * limit

    pipeline = [
        {"$match": match},
        {"$sort": {"name": 1}},
        {"$skip": skip},
        {"$limit": limit},
    ]
    docs = await db.registered_candidates.aggregate(pipeline, allowDiskUse=False).to_list(None)

    # Fetch scores ONLY for this page's emails/phones
    page_emails = list({normalize_email(d.get("email")) for d in docs if d.get("email")})
    page_phones = list({normalize_phone(d.get("phone")) for d in docs if d.get("phone")})
    score_query = []
    if page_emails: score_query.append({"email": {"$in": page_emails}})
    if page_phones: score_query.append({"phone": {"$in": page_phones}})
    score_records = []
    if score_query:
        score_records = await db.score_sheet.find(
            {"$or": score_query} if len(score_query) > 1 else score_query[0],
            {"_id": 0}
        ).to_list(None)

    score_by_email = {}
    score_by_phone = {}
    for sr in score_records:
        se = normalize_email(sr.get("email"))
        sp = normalize_phone(sr.get("phone"))
        if se: score_by_email.setdefault(se, []).append(sr)
        if sp: score_by_phone.setdefault(sp, []).append(sr)

    applicants = []
    for doc in docs:
        cs = doc.get("_college_status") or "Non NIRF"
        normalized_role = doc.get("_normalized_job_role") or doc.get("job_title") or "Unknown"

        doc_email = normalize_email(doc.get("email"))
        doc_phone = normalize_phone(doc.get("phone"))

        matched_scores = []
        if doc_email and doc_email in score_by_email:
            matched_scores.extend(score_by_email[doc_email])
        if doc_phone and doc_phone in score_by_phone:
            for s in score_by_phone[doc_phone]:
                if s not in matched_scores:
                    matched_scores.append(s)

        round_scores = {}
        for sr in matched_scores:
            rn = sr.get("round_name", "").strip().lower()
            canonical = ROUND_NAME_MAP.get(rn)
            if canonical:
                round_scores[canonical] = sr.get("score", 0)

        row = {
            "name": doc.get("name") or "-",
            "email": doc.get("email") or "-",
            "phone": doc.get("phone") or "-",
            "college_status": cs,
            "college": doc.get("_college_resolved") or "-",
            "match_confidence": doc.get("_match_confidence") or "-",
            "degree": doc.get("degree") or "-",
            "course": doc.get("course") or "-",
            "year_of_graduation": doc.get("year_of_graduation") or "-",
            "job_role": normalized_role or "-",
            "schedule_date": doc.get("schedule_date") or "-",
            "result_status": doc.get("result_status") or "-",
        }
        for col in SCORE_ROUND_COLUMNS:
            row[col] = round_scores.get(col, "-")
        applicants.append(row)

    columns = ["name", "email", "phone", "college_status", "college", "degree", "course",
               "year_of_graduation", "job_role", "schedule_date", "result_status"] + SCORE_ROUND_COLUMNS

    return {
        "data": applicants,
        "total": total,
        "page": page,
        "limit": limit,
        "columns": columns,
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


# ============ COLLEGE RANK UPLOAD ============

COLLEGE_RANK_COLUMNS = {"rank", "college_name", "short_name", "city", "state"}

@api_router.post("/upload/college-rank")
async def upload_college_rank(
    file: UploadFile = File(...),
    user: str = Depends(get_current_user)
):
    """Upload college rank list (CSV/XLSX). Columns: Rank, College Name, Short Name, City, State."""
    content = await file.read()
    df = parse_file(content, file.filename)
    df.columns = df.columns.str.strip()
    # Map column names to snake_case
    col_map = {}
    for c in df.columns:
        cl = c.strip().lower().replace(" ", "_")
        if cl in COLLEGE_RANK_COLUMNS:
            col_map[c] = cl
    mapped = set(col_map.values())
    if "college_name" not in mapped:
        raise HTTPException(status_code=400, detail=f"Missing 'College Name' column. Found: {list(df.columns)}")

    # Clear existing and re-insert
    await db.college_rank_list.delete_many({})
    inserted = 0
    for _, row in df.iterrows():
        try:
            doc = {}
            for csv_col, db_field in col_map.items():
                val = row.get(csv_col)
                if pd.isna(val):
                    doc[db_field] = None
                elif db_field == "rank":
                    try:
                        doc[db_field] = int(float(val))
                    except (ValueError, TypeError):
                        doc[db_field] = None
                else:
                    doc[db_field] = str(val).strip()
            if not doc.get("college_name"):
                continue
            await db.college_rank_list.insert_one(doc)
            inserted += 1
        except Exception:
            pass
    return {"success": True, "inserted": inserted}


async def _build_college_rank_lookup() -> dict:
    """Build structured lookup for multi-criteria college matching.
    Groups rank entries by base_name for efficient lookup.
    Returns: {entries_by_base: {base: [entries]}, cities: set, states: set}"""
    docs = await db.college_rank_list.find({}, {"_id": 0}).to_list(None)

    # First pass: collect all known cities and states (normalized)
    city_set = set()
    state_set = set()
    for doc in docs:
        city = _normalize_college_text(doc.get("city") or "")
        state = _normalize_college_text(doc.get("state") or "")
        if city:
            city_set.add(city)
        if state:
            state_set.add(state)

    # Second pass: build lookup keyed by base_name
    entries_by_base = {}

    for doc in docs:
        rank = doc.get("rank")
        college_name = (doc.get("college_name") or "").strip()
        short_name = (doc.get("short_name") or "").strip()
        city = _normalize_college_text(doc.get("city") or "")
        state = _normalize_college_text(doc.get("state") or "")

        if not college_name:
            continue

        normalized = _normalize_college_text(college_name)

        # For rank entries, remove generic words + own location tokens to get base
        own_locations = set()
        for token in normalized.split():
            if token in city_set or token in state_set:
                own_locations.add(token)
        # Also check multi-word city/state phrases
        if city:
            for t in city.split():
                if t in normalized:
                    own_locations.add(t)
        if state:
            for t in state.split():
                if t in normalized:
                    own_locations.add(t)

        base = _extract_college_base(normalized, own_locations)

        entry = {
            "college_name": college_name,
            "short_name": short_name,
            "normalized": normalized,
            "base": base,
            "city": city,
            "state": state,
            "rank": rank,
        }

        if base:
            entries_by_base.setdefault(base, []).append(entry)

        # Also index by short_name base
        if short_name:
            short_norm = _normalize_college_text(short_name)
            short_base = _extract_college_base(short_norm, own_locations)
            if short_base and short_base != base:
                entries_by_base.setdefault(short_base, []).append(entry)

    return {"entries_by_base": entries_by_base, "cities": city_set, "states": state_set}


_GENERIC_COLLEGE_WORDS = frozenset({
    "university", "institute", "college", "of", "the", "and", "for",
})


def _normalize_college_text(text: str) -> str:
    """Normalize: lowercase, trim, remove punctuation, single spaces."""
    if not text:
        return ""
    text = text.lower().strip()
    text = re.sub(r'[,.\-&()\[\]/]', ' ', text)
    text = re.sub(r'\s+', ' ', text).strip()
    return text


def _extract_college_base(normalized_text: str, location_tokens: set = None) -> str:
    """Extract base name by removing generic words and location tokens."""
    tokens = normalized_text.split()
    remove = _GENERIC_COLLEGE_WORDS
    if location_tokens:
        remove = remove | location_tokens
    base_tokens = [t for t in tokens if t not in remove]
    return " ".join(base_tokens).strip()


def _match_college_entry(university_text: str, rank_lookup: dict) -> dict:
    """Match a university text against the rank lookup using multi-criteria matching.
    Returns: {rank, college_name, confidence: HIGH|MEDIUM|LOW|None}"""
    if not university_text or not university_text.strip():
        return {"rank": None, "college_name": "", "confidence": None}

    normalized = _normalize_college_text(university_text)
    cities = rank_lookup["cities"]
    states = rank_lookup["states"]
    entries_by_base = rank_lookup["entries_by_base"]

    # Extract location tokens from the university text
    location_tokens = set()
    extracted_city = None
    extracted_state = None

    # Single-word token matching
    for token in normalized.split():
        if token in cities:
            location_tokens.add(token)
            if not extracted_city:
                extracted_city = token
        if token in states:
            location_tokens.add(token)
            if not extracted_state:
                extracted_state = token

    # Multi-word city/state phrase matching
    for city in cities:
        if ' ' in city and city in normalized:
            extracted_city = city
            for t in city.split():
                location_tokens.add(t)
    for state in states:
        if ' ' in state and state in normalized:
            extracted_state = state
            for t in state.split():
                location_tokens.add(t)

    # Extract base name (remove generic words + location tokens)
    base = _extract_college_base(normalized, location_tokens)

    if not base:
        return {"rank": None, "college_name": university_text, "confidence": None}

    # Step 1: Exact base match
    candidates = list(entries_by_base.get(base, []))

    # Step 1a: Token-subset fallback if no exact match
    if not candidates:
        base_tokens = set(base.split())
        for key, entries in entries_by_base.items():
            key_tokens = set(key.split())
            if base_tokens and key_tokens:
                if base_tokens.issubset(key_tokens) or key_tokens.issubset(base_tokens):
                    candidates.extend(entries)
        # Deduplicate
        seen = set()
        deduped = []
        for c in candidates:
            uid = (c["college_name"], c.get("rank"))
            if uid not in seen:
                seen.add(uid)
                deduped.append(c)
        candidates = deduped

    if not candidates:
        return {"rank": None, "college_name": university_text, "confidence": None}

    # Step 2: Strong match (base + location)
    if extracted_city or extracted_state:
        for entry in candidates:
            city_match = (extracted_city and entry["city"]
                          and (extracted_city in entry["city"] or entry["city"] in extracted_city))
            state_match = (extracted_state and entry["state"]
                           and (extracted_state in entry["state"] or entry["state"] in extracted_state))
            if city_match or state_match:
                return {"rank": entry["rank"], "college_name": entry["college_name"], "confidence": "HIGH"}

    # Step 3: Base-only — single match
    if len(candidates) == 1:
        return {"rank": candidates[0]["rank"], "college_name": candidates[0]["college_name"], "confidence": "MEDIUM"}

    # Step 4: Multiple matches — disambiguate via NIRF
    nirf_candidates = [e for e in candidates if e["rank"] is not None and e["rank"] <= 100]
    if len(nirf_candidates) == 1:
        return {"rank": nirf_candidates[0]["rank"], "college_name": nirf_candidates[0]["college_name"], "confidence": "MEDIUM"}

    # Ambiguous — multiple NIRF or none
    return {"rank": None, "college_name": university_text, "confidence": "LOW"}


def _classify_college(doc: dict, rank_lookup: dict) -> dict:
    """Classify a candidate's college using structured multi-criteria matching.
    Returns: {college_status, college, match_confidence}"""
    ug_text = (doc.get("ug_university") or "").strip()
    pg_text = (doc.get("pg_university") or "").strip()

    ug_match = _match_college_entry(ug_text, rank_lookup)
    pg_match = _match_college_entry(pg_text, rank_lookup)

    ug_nirf = ug_match["rank"] is not None and ug_match["rank"] <= 100
    pg_nirf = pg_match["rank"] is not None and pg_match["rank"] <= 100

    # UG/PG priority: Both NIRF→PG, else whichever is NIRF
    if ug_nirf and pg_nirf:
        return {"college_status": f"NIRF - #{pg_match['rank']}", "college": pg_text or "-",
                "match_confidence": pg_match["confidence"]}
    if pg_nirf:
        return {"college_status": f"NIRF - #{pg_match['rank']}", "college": pg_text or "-",
                "match_confidence": pg_match["confidence"]}
    if ug_nirf:
        return {"college_status": f"NIRF - #{ug_match['rank']}", "college": ug_text or "-",
                "match_confidence": ug_match["confidence"]}
    # Neither NIRF: prefer UG if exists, else PG
    return {"college_status": "Non NIRF", "college": ug_text or pg_text or "-",
            "match_confidence": ug_match.get("confidence") or pg_match.get("confidence")}

UPLOAD_BASE = Path("/app/uploads")
PROCESSED_BASE = Path("/app/processed_files")
BULK_TYPES_LIST = ["naukri", "pipeline", "score"]

# Create directories on module load
for _bt in BULK_TYPES_LIST:
    (UPLOAD_BASE / _bt).mkdir(parents=True, exist_ok=True)
    (PROCESSED_BASE / _bt).mkdir(parents=True, exist_ok=True)



# ============ DB-DRIVEN BACKGROUND QUEUE WORKER ============

_worker_running = False


async def _bg_queue_worker():
    """Persistent background worker: continuously polls bulk_upload_queue for pending jobs.
    Processes ONE file at a time, sequentially. Runs independent of UI/browser."""
    global _worker_running
    if _worker_running:
        return
    _worker_running = True
    logger.info("Background queue worker started")
    try:
        while True:
            # Fetch next pending job (FIFO)
            job = await db.bulk_upload_queue.find_one(
                {"status": "pending"},
                sort=[("created_at", 1)]
            )
            if not job:
                await asyncio.sleep(3)
                continue

            job_id = job["_id"]
            file_type = job["file_type"]
            file_path = job["file_path"]
            file_name = job["file_name"]

            # Mark as processing
            await db.bulk_upload_queue.update_one(
                {"_id": job_id},
                {"$set": {"status": "processing", "updated_at": datetime.now(timezone.utc).isoformat()}}
            )
            logger.info(f"Queue: processing {file_type}/{file_name}")

            try:
                path = Path(file_path)
                if not path.exists():
                    raise FileNotFoundError(f"File not found: {file_path}")

                content = path.read_bytes()
                process_fn = _PROCESS_FN.get(file_type)
                if not process_fn:
                    raise ValueError(f"Unknown file type: {file_type}")

                result = await process_fn(content, file_name)

                if result.get("success"):
                    # Move file to processed_files directory
                    dest = PROCESSED_BASE / file_type / path.name
                    shutil.move(str(path), str(dest))
                    await db.bulk_upload_queue.update_one(
                        {"_id": job_id},
                        {"$set": {
                            "status": "completed",
                            "result": result,
                            "updated_at": datetime.now(timezone.utc).isoformat()
                        }}
                    )
                    logger.info(f"Queue: completed {file_type}/{file_name}")
                else:
                    await db.bulk_upload_queue.update_one(
                        {"_id": job_id},
                        {"$set": {
                            "status": "failed",
                            "error_message": result.get("error", "Processing returned failure"),
                            "updated_at": datetime.now(timezone.utc).isoformat()
                        }}
                    )
                    logger.warning(f"Queue: failed {file_type}/{file_name} — {result}")

            except Exception as e:
                logger.error(f"Queue: error {file_type}/{file_name} — {e}")
                await db.bulk_upload_queue.update_one(
                    {"_id": job_id},
                    {"$set": {
                        "status": "failed",
                        "error_message": str(e),
                        "updated_at": datetime.now(timezone.utc).isoformat()
                    }}
                )

            # Small delay between jobs
            await asyncio.sleep(0.5)

    except asyncio.CancelledError:
        logger.info("Background queue worker stopped")
    finally:
        _worker_running = False


# ============ BULK UPLOAD ENDPOINTS ============

@api_router.get("/bulk-upload/status")
async def bulk_upload_status(user: str = Depends(get_current_user)):
    """Return queue status for all types: pending, processing, completed, failed."""
    result = {}
    for utype in BULK_TYPES_LIST:
        # Pending + Processing from DB
        active = await db.bulk_upload_queue.find(
            {"file_type": utype, "status": {"$in": ["pending", "processing"]}},
            {"_id": 1, "file_name": 1, "file_path": 1, "status": 1, "created_at": 1, "error_message": 1}
        ).sort("created_at", 1).to_list(None)
        pending = []
        for j in active:
            size = 0
            try:
                p = Path(j["file_path"])
                if p.exists():
                    size = p.stat().st_size
            except Exception:
                pass
            pending.append({
                "id": str(j["_id"]),
                "name": j["file_name"],
                "status": j["status"],
                "size": size,
            })

        # Completed from DB
        completed = await db.bulk_upload_queue.find(
            {"file_type": utype, "status": "completed"},
            {"_id": 1, "file_name": 1, "file_path": 1, "result": 1, "updated_at": 1}
        ).sort("updated_at", -1).to_list(None)
        processed = []
        for j in completed:
            size = 0
            try:
                p = PROCESSED_BASE / utype
                for fp in p.iterdir():
                    if fp.name.endswith(j["file_name"]) or j["file_name"] in fp.name:
                        size = fp.stat().st_size
                        break
            except Exception:
                pass
            processed.append({
                "id": str(j["_id"]),
                "name": j["file_name"],
                "size": size,
                "result": j.get("result"),
            })

        # Failed from DB
        failed_docs = await db.bulk_upload_queue.find(
            {"file_type": utype, "status": "failed"},
            {"_id": 1, "file_name": 1, "error_message": 1, "updated_at": 1}
        ).sort("updated_at", -1).to_list(None)
        failed = [{"id": str(j["_id"]), "name": j["file_name"],
                    "error": j.get("error_message", "Unknown error")} for j in failed_docs]

        result[utype] = {"pending": pending, "processed": processed, "failed": failed}
    return result


@api_router.post("/bulk-upload/process-now")
async def trigger_bulk_process(user: str = Depends(get_current_user)):
    """Manual trigger — worker is always running, this confirms status."""
    pending_count = await db.bulk_upload_queue.count_documents({"status": "pending"})
    processing_count = await db.bulk_upload_queue.count_documents({"status": "processing"})
    return {"success": True, "message": "Worker is running", "pending": pending_count, "processing": processing_count}


@api_router.post("/bulk-upload/{upload_type}")
async def bulk_upload_files(
    upload_type: str,
    files: List[UploadFile] = File(...),
    user: str = Depends(get_current_user)
):
    """Save files to disk and enqueue DB records. Worker processes them in background."""
    if upload_type not in BULK_TYPES_LIST:
        raise HTTPException(status_code=400, detail=f"Invalid type: {upload_type}. Must be naukri, pipeline, or score")
    upload_dir = UPLOAD_BASE / upload_type
    saved = []
    for f in files:
        if not f.filename.lower().endswith(('.csv', '.xlsx')):
            continue
        content = await f.read()
        safe_name = f"{int(datetime.now(timezone.utc).timestamp())}_{f.filename}"
        dest = upload_dir / safe_name
        dest.write_bytes(content)
        # Insert into DB queue
        await db.bulk_upload_queue.insert_one({
            "file_name": f.filename,
            "file_path": str(dest),
            "file_type": upload_type,
            "status": "pending",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "error_message": None,
            "result": None,
        })
        saved.append(safe_name)
    return {"success": True, "saved": saved, "count": len(saved)}


@api_router.delete("/bulk-upload/{upload_type}/{queue_id}")
async def delete_bulk_file(upload_type: str, queue_id: str, user: str = Depends(get_current_user)):
    """Delete a pending file from queue and disk."""
    try:
        oid = ObjectId(queue_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid queue ID")
    job = await db.bulk_upload_queue.find_one({"_id": oid})
    if not job:
        raise HTTPException(status_code=404, detail="Queue entry not found")
    if job["status"] == "processing":
        raise HTTPException(status_code=409, detail="Cannot delete file while processing")
    # Remove file from disk
    try:
        path = Path(job["file_path"])
        if path.exists():
            path.unlink()
    except Exception:
        pass
    await db.bulk_upload_queue.delete_one({"_id": oid})
    return {"success": True, "deleted": job["file_name"]}


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
    await _sync_job_titles_master()
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

# Include BluBridge modules router
from bb_modules import bb_router, pub_router, init_bb
init_bb(db, get_current_user, _build_college_rank_lookup, _classify_college)
app.include_router(bb_router)
app.include_router(pub_router)

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
    await db.registered_candidates.create_index("_normalized_job_role")
    await db.registered_candidates.create_index("_nirf_category")
    await db.registered_candidates.create_index("_college_status")
    await db.registered_candidates.create_index("name")
    await db.naukri_applies.create_index("_normalized_job_role")
    await db.naukri_applies.create_index("_nirf_category")
    await db.job_titles_master.create_index("normalized_job_title", unique=True)
    await db.job_titles_master.create_index("is_mapped")
    await db.bulk_upload_queue.create_index([("status", 1), ("created_at", 1)])
    
    # Resume: reset any stuck "processing" records to "pending"
    stuck = await db.bulk_upload_queue.update_many(
        {"status": "processing"},
        {"$set": {"status": "pending", "updated_at": datetime.now(timezone.utc).isoformat()}}
    )
    if stuck.modified_count > 0:
        logger.info(f"Reset {stuck.modified_count} stuck processing jobs to pending")

    # Write test credentials
    try:
        os.makedirs("/app/memory", exist_ok=True)
        with open("/app/memory/test_credentials.md", "w") as f:
            f.write("# Test Credentials\n\n")
            f.write("## Admin Account (RecruitIQ)\n")
            f.write("- Username: `Admin User`\n")
            f.write("- Password: `Admin User`\n")
    except Exception as e:
        logger.error(f"Failed to write test credentials: {e}")

    # Start persistent background queue worker
    asyncio.create_task(_bg_queue_worker())
    logger.info("DB-driven background queue worker launched")

    # Start messaging background workers
    from bg_workers import init_workers, start_all_workers
    init_workers(db)
    await start_all_workers()
    logger.info("Messaging background workers launched")

@app.on_event("shutdown")
async def shutdown_db_client():
    client.close()
