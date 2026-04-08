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
    """Upload Naukri Applies data - can be uploaded independently"""
    try:
        content = await file.read()
        if len(content) > 10 * 1024 * 1024:
            raise HTTPException(status_code=400, detail="File size exceeds 10MB limit")
        
        df = parse_file(content, file.filename)
        df.columns = df.columns.str.strip()
        
        # Detect email and phone columns
        email_col = None
        phone_col = None
        for col in df.columns:
            col_lower = col.lower()
            if 'email' in col_lower and 'type' not in col_lower:
                email_col = col
            if 'phone' in col_lower or 'mobile' in col_lower:
                phone_col = col
        
        if not email_col and not phone_col:
            raise HTTPException(status_code=400, detail="Could not detect Email or Phone column")
        
        # Detect other columns
        name_col = next((c for c in df.columns if c.lower() == 'name' or 'name' in c.lower()), None)
        job_col = next((c for c in df.columns if 'job' in c.lower() and ('title' in c.lower() or 'role' in c.lower())), None)
        date_col = next((c for c in df.columns if 'date' in c.lower() and 'application' in c.lower()), None)
        if not date_col:
            date_col = next((c for c in df.columns if 'submitted' in c.lower() or 'applied' in c.lower()), None)
        gender_col = next((c for c in df.columns if 'gender' in c.lower()), None)
        dob_col = next((c for c in df.columns if 'birth' in c.lower() or 'dob' in c.lower()), None)
        
        total = len(df)
        inserted = 0
        updated = 0
        errors = []
        
        for idx, row in df.iterrows():
            try:
                email = normalize_email(row.get(email_col)) if email_col else ""
                phone = normalize_phone(row.get(phone_col)) if phone_col else ""
                
                if not email and not phone:
                    errors.append(f"Row {idx + 2}: Missing email and phone")
                    continue
                
                # Build document
                doc = {
                    "name": clean_value(row.get(name_col)) if name_col else None,
                    "email": email,
                    "phone": phone,
                    "job_title": clean_value(row.get(job_col)) if job_col else None,
                    "date_of_application": clean_value(row.get(date_col)) if date_col else None,
                    "gender": clean_value(row.get(gender_col)) if gender_col else None,
                    "date_of_birth": clean_value(row.get(dob_col)) if dob_col else None,
                    "updated_at": datetime.now(timezone.utc)
                }
                
                # Store all original columns too
                for col in df.columns:
                    if col not in [email_col, phone_col, name_col, job_col, date_col, gender_col, dob_col]:
                        doc[f"_raw_{col}"] = clean_value(row.get(col))
                
                # UPSERT based on email OR phone composite uniqueness
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
        
        # Trigger reprocessing
        await reprocess_matching()
        
        return {
            "success": True,
            "message": f"Naukri data uploaded. Inserted: {inserted}, Updated: {updated}",
            "total": total,
            "inserted": inserted,
            "updated": updated,
            "errors": errors[:10]
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@api_router.post("/upload/pipeline")
async def upload_pipeline(file: UploadFile = File(...), user: str = Depends(get_current_user)):
    """Upload Pipeline data - can be uploaded independently"""
    try:
        content = await file.read()
        if len(content) > 10 * 1024 * 1024:
            raise HTTPException(status_code=400, detail="File size exceeds 10MB limit")
        
        df = parse_file(content, file.filename)
        df.columns = df.columns.str.strip()
        
        # Handle duplicate column names by taking unique ones
        cols = df.columns.tolist()
        seen = {}
        new_cols = []
        for col in cols:
            if col in seen:
                seen[col] += 1
                new_cols.append(f"{col}_{seen[col]}")
            else:
                seen[col] = 0
                new_cols.append(col)
        df.columns = new_cols
        
        # Detect key columns
        email_col = next((c for c in df.columns if 'email' in c.lower() and 'type' not in c.lower() and '_' not in c), None)
        phone_col = next((c for c in df.columns if ('phone' in c.lower() or 'mobile' in c.lower()) and '_' not in c), None)
        
        if not email_col and not phone_col:
            raise HTTPException(status_code=400, detail="Could not detect Email or Phone column")
        
        total = len(df)
        inserted = 0
        updated = 0
        errors = []
        
        for idx, row in df.iterrows():
            try:
                email = normalize_email(row.get(email_col)) if email_col else ""
                phone = normalize_phone(row.get(phone_col)) if phone_col else ""
                
                if not email and not phone:
                    errors.append(f"Row {idx + 2}: Missing email and phone")
                    continue
                
                # Map known fields
                doc = {
                    "email": email,
                    "phone": phone,
                    "name": clean_value(row.get('name')) if 'name' in df.columns else None,
                    "job_title": clean_value(row.get('job_role')) if 'job_role' in df.columns else None,
                    "gender": clean_value(row.get('gender')) if 'gender' in df.columns else None,
                    "age": clean_value(row.get('age')) if 'age' in df.columns else None,
                    "location": clean_value(row.get('location')) if 'location' in df.columns else clean_value(row.get('current_location')) if 'current_location' in df.columns else None,
                    "loca_change": clean_value(row.get('loca_change')) if 'loca_change' in df.columns else None,
                    "attend_inperson": clean_value(row.get('attend_inperson')) if 'attend_inperson' in df.columns else None,
                    "email_type": clean_value(row.get('email_type')) if 'email_type' in df.columns else None,
                    "confirm": clean_value(row.get('confirm_box')) if 'confirm_box' in df.columns else None,
                    "schedule_date": clean_value(row.get('schedule_date')) if 'schedule_date' in df.columns else None,
                    "schedule_time": clean_value(row.get('schedule_time')) if 'schedule_time' in df.columns else None,
                    "reschedule_count": clean_value(row.get('reschedule_count')) if 'reschedule_count' in df.columns else None,
                    "otp_verified": clean_value(row.get('otp_verified')) if 'otp_verified' in df.columns else None,
                    "otp_expired": clean_value(row.get('otp_expired')) if 'otp_expired' in df.columns else None,
                    "result_mail": clean_value(row.get('result_mail')) if 'result_mail' in df.columns else None,
                    "result_update": clean_value(row.get('result_update')) if 'result_update' in df.columns else None,
                    "result_status": clean_value(row.get('result_status')) if 'result_status' in df.columns else None,
                    "date_of_application": clean_value(row.get('submitted_at')) if 'submitted_at' in df.columns else None,
                    "updated_at": datetime.now(timezone.utc)
                }
                
                # UPSERT based on email OR phone
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
        
        # Trigger reprocessing
        await reprocess_matching()
        
        return {
            "success": True,
            "message": f"Pipeline data uploaded. Inserted: {inserted}, Updated: {updated}",
            "total": total,
            "inserted": inserted,
            "updated": updated,
            "errors": errors[:10]
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
    """Rebuild registered_candidates collection via INNER JOIN of naukri_applies and pipeline_data"""
    naukri_list = await db.naukri_applies.find({}).to_list(None)
    pipeline_list = await db.pipeline_data.find({}).to_list(None)

    pipeline_by_email = {p['email']: p for p in pipeline_list if p.get('email')}
    pipeline_by_phone = {p['phone']: p for p in pipeline_list if p.get('phone')}

    await db.registered_candidates.drop()

    registered_docs = []

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
            doc = {
                "name": naukri.get("name") or pipeline_match.get("name"),
                "email": email or pipeline_match.get("email", ""),
                "phone": phone or pipeline_match.get("phone", ""),
                "job_title": naukri.get("job_title") or pipeline_match.get("job_title"),
                "date_of_application": naukri.get("date_of_application") or pipeline_match.get("date_of_application"),
                "gender": naukri.get("gender") or pipeline_match.get("gender"),
                "date_of_birth": naukri.get("date_of_birth"),
                "age": pipeline_match.get("age"),
                "location": pipeline_match.get("location"),
                "loca_change": pipeline_match.get("loca_change"),
                "attend_inperson": pipeline_match.get("attend_inperson"),
                "email_type": pipeline_match.get("email_type"),
                "confirm": pipeline_match.get("confirm"),
                "schedule_date": pipeline_match.get("schedule_date"),
                "schedule_time": pipeline_match.get("schedule_time"),
                "reschedule_count": pipeline_match.get("reschedule_count"),
                "otp_verified": pipeline_match.get("otp_verified"),
                "otp_expired": pipeline_match.get("otp_expired"),
                "result_mail": pipeline_match.get("result_mail"),
                "result_update": pipeline_match.get("result_update"),
                "result_status": pipeline_match.get("result_status"),
            }
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
        "email_type": {"$regex": "shortlist", "$options": "i"}
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
    """Rejected: registered_candidates WHERE result_status IN (Reject, Rejected)"""
    skip = (page - 1) * limit
    query = {"result_status": {"$regex": "^reject", "$options": "i"}}
    total = await db.registered_candidates.count_documents(query)
    cursor = db.registered_candidates.find(query, {
        "_id": 0, "name": 1, "email": 1, "phone": 1, "job_title": 1,
        "date_of_application": 1, "gender": 1, "date_of_birth": 1,
        "location": 1, "loca_change": 1, "attend_inperson": 1,
        "email_type": 1, "confirm": 1
    }).skip(skip).limit(limit)
    data = await cursor.to_list(None)
    return {
        "data": data, "total": total, "page": page, "limit": limit,
        "columns": ["name", "email", "phone", "job_title", "date_of_application", "gender", "date_of_birth", "location", "loca_change", "attend_inperson", "email_type", "confirm"]
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
        "email_type": 1, "confirm": 1
    }).skip(skip).limit(limit)
    data = await cursor.to_list(None)
    return {
        "data": data, "total": total, "page": page, "limit": limit,
        "columns": ["name", "email", "phone", "job_title", "date_of_application", "gender", "date_of_birth", "location", "loca_change", "attend_inperson", "email_type", "confirm"]
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
