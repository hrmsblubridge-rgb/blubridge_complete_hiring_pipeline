from dotenv import load_dotenv
from pathlib import Path

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

from fastapi import FastAPI, APIRouter, HTTPException, Request, Response, UploadFile, File, Depends, Query
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
import os
import logging
from pydantic import BaseModel, EmailStr
from typing import List, Optional, Any, Dict
from datetime import datetime, timezone, timedelta
import bcrypt
import jwt
from bson import ObjectId
import pandas as pd
import io
import re
import csv
import json

# MongoDB connection
mongo_url = os.environ['MONGO_URL']
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ['DB_NAME']]

# JWT Configuration
JWT_ALGORITHM = "HS256"

def get_jwt_secret() -> str:
    return os.environ["JWT_SECRET"]

def hash_password(password: str) -> str:
    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(password.encode("utf-8"), salt)
    return hashed.decode("utf-8")

def verify_password(plain_password: str, hashed_password: str) -> bool:
    return bcrypt.checkpw(plain_password.encode("utf-8"), hashed_password.encode("utf-8"))

def create_access_token(user_id: str, email: str) -> str:
    payload = {
        "sub": user_id,
        "email": email,
        "exp": datetime.now(timezone.utc) + timedelta(minutes=60),
        "type": "access"
    }
    return jwt.encode(payload, get_jwt_secret(), algorithm=JWT_ALGORITHM)

def create_refresh_token(user_id: str) -> str:
    payload = {
        "sub": user_id,
        "exp": datetime.now(timezone.utc) + timedelta(days=7),
        "type": "refresh"
    }
    return jwt.encode(payload, get_jwt_secret(), algorithm=JWT_ALGORITHM)

async def get_current_user(request: Request) -> dict:
    token = request.cookies.get("access_token")
    if not token:
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header[7:]
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    try:
        payload = jwt.decode(token, get_jwt_secret(), algorithms=[JWT_ALGORITHM])
        if payload.get("type") != "access":
            raise HTTPException(status_code=401, detail="Invalid token type")
        user = await db.users.find_one({"_id": ObjectId(payload["sub"])})
        if not user:
            raise HTTPException(status_code=401, detail="User not found")
        user["_id"] = str(user["_id"])
        user.pop("password_hash", None)
        return user
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")

# Create the main app
app = FastAPI()

# Create a router with the /api prefix
api_router = APIRouter(prefix="/api")

# Pydantic Models
class UserRegister(BaseModel):
    name: str
    email: EmailStr
    password: str

class UserLogin(BaseModel):
    email: EmailStr
    password: str

class UploadResponse(BaseModel):
    success: bool
    message: str
    total_records: int
    valid_records: int
    duplicate_records: int
    invalid_records: int
    errors: List[str]
    schema_info: Dict[str, Any]

# ============ DYNAMIC SCHEMA UTILITIES ============

def normalize_phone(phone) -> str:
    """Normalize phone number to numeric format"""
    if pd.isna(phone) or phone is None:
        return ""
    phone_str = str(phone).strip()
    # Remove all non-numeric characters
    phone_str = re.sub(r'[^\d]', '', phone_str)
    # Remove country code if present (91 for India)
    if phone_str.startswith('91') and len(phone_str) > 10:
        phone_str = phone_str[2:]
    return phone_str

def normalize_email(email) -> str:
    """Normalize email to lowercase"""
    if pd.isna(email) or email is None:
        return ""
    return str(email).strip().lower()

def detect_identifier_columns(columns: List[str]) -> Dict[str, Optional[str]]:
    """Dynamically detect email and phone columns"""
    email_col = None
    phone_col = None
    
    # Exact matches first, then partial matches
    email_exact = ['email', 'email id', 'email_id', 'emailid', 'e-mail']
    email_partial = ['email', 'mail']
    phone_exact = ['phone', 'phone number', 'phone_number', 'phonenumber', 'mobile', 'mobile number', 'contact']
    phone_partial = ['phone', 'mobile', 'contact']
    
    columns_lower = {col.lower().strip(): col for col in columns}
    
    # Try exact matches first
    for pattern in email_exact:
        if pattern in columns_lower:
            email_col = columns_lower[pattern]
            break
    
    # Fall back to partial matches
    if not email_col:
        for pattern in email_partial:
            for col_lower, col_original in columns_lower.items():
                if pattern in col_lower and 'type' not in col_lower:  # Exclude email_type
                    email_col = col_original
                    break
            if email_col:
                break
    
    # Phone detection - exact first
    for pattern in phone_exact:
        if pattern in columns_lower:
            phone_col = columns_lower[pattern]
            break
    
    # Fall back to partial matches
    if not phone_col:
        for pattern in phone_partial:
            for col_lower, col_original in columns_lower.items():
                if pattern in col_lower:
                    phone_col = col_original
                    break
            if phone_col:
                break
    
    return {"email": email_col, "phone": phone_col}

def detect_status_column(df: pd.DataFrame) -> Optional[str]:
    """Auto-detect the status column by looking for common status values"""
    status_indicators = ['shortlist', 'shortlisted', 'rejected', 'scheduled', 'attended', 'selected', 
                        'hired', 'pending', 'in progress', 'not attended', 'not scheduled',
                        'interview', 'offer', 'joined', 'dropped', 'hold', 'waitlist', 'confirmed']
    
    # Priority columns to check first
    priority_patterns = ['status', 'pipeline_status', 'email_type', 'candidate_status', 'result_status']
    
    columns_lower = {col.lower().strip(): col for col in df.columns}
    
    # Check priority patterns first
    for pattern in priority_patterns:
        for col_lower, col_original in columns_lower.items():
            if pattern == col_lower or pattern in col_lower:
                # Verify it has status-like values
                try:
                    unique_values = df[col_original].dropna().astype(str).str.lower().unique()
                    if len(unique_values) > 0 and len(unique_values) < 20:  # Reasonable number of statuses
                        return col_original
                except Exception:
                    continue
    
    # Fallback: check all columns for status-like values
    for col in df.columns:
        try:
            unique_values = df[col].dropna().astype(str).str.lower().unique()
            matches = sum(1 for val in unique_values if any(ind in val for ind in status_indicators))
            if matches >= 1 and len(unique_values) < 15:  # At least 1 match
                return col
        except Exception:
            continue
    
    return None

def detect_job_role_column(df: pd.DataFrame) -> Optional[str]:
    """Auto-detect job role column"""
    # Exact matches first
    role_exact = ['job_role', 'job role', 'jobrole', 'job title', 'job_title', 'jobtitle', 'position', 'designation']
    role_partial = ['job', 'role', 'position', 'designation', 'title']
    
    columns_lower = {col.lower().strip(): col for col in df.columns}
    
    # Try exact matches first
    for pattern in role_exact:
        if pattern in columns_lower:
            return columns_lower[pattern]
    
    # Then try partial matches, prioritizing 'job' patterns
    for pattern in role_partial:
        for col_lower, col_original in columns_lower.items():
            if pattern in col_lower and 'id' not in col_lower:  # Exclude job_id type columns
                # Verify it has reasonable values (text, not just numbers)
                try:
                    unique_values = df[col_original].dropna().astype(str).unique()
                    if len(unique_values) > 1 and len(unique_values) < 100:
                        # Check if values look like job titles
                        sample = str(unique_values[0]).lower()
                        if any(kw in sample for kw in ['engineer', 'developer', 'analyst', 'manager', 'scientist', 'accountant', 'designer', 'ai', 'ml', 'data']):
                            return col_original
                except Exception:
                    continue
    
    return None

def detect_name_column(df: pd.DataFrame) -> Optional[str]:
    """Auto-detect name column"""
    name_patterns = ['name', 'candidate name', 'full name', 'applicant name', 'candidate']
    
    columns_lower = {col.lower().strip(): col for col in df.columns}
    
    for pattern in name_patterns:
        for col_lower, col_original in columns_lower.items():
            if pattern in col_lower or col_lower == pattern:
                return col_original
    
    return None

def parse_file(file_content: bytes, filename: str) -> pd.DataFrame:
    """Parse uploaded file to DataFrame"""
    if filename.lower().endswith('.csv'):
        # Try different encodings
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

def clean_value(val):
    """Clean a value for JSON storage"""
    if pd.isna(val):
        return None
    if isinstance(val, (pd.Timestamp, datetime)):
        return val.isoformat()
    return val

def dataframe_to_records(df: pd.DataFrame) -> List[Dict]:
    """Convert DataFrame to list of clean dictionaries"""
    records = []
    for _, row in df.iterrows():
        record = {col: clean_value(row[col]) for col in df.columns}
        records.append(record)
    return records

# ============ AUTH ENDPOINTS ============

@api_router.post("/auth/register")
async def register(response: Response, data: UserRegister):
    email = data.email.lower()
    existing = await db.users.find_one({"email": email})
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")
    
    hashed = hash_password(data.password)
    user_doc = {
        "name": data.name,
        "email": email,
        "password_hash": hashed,
        "role": "user",
        "created_at": datetime.now(timezone.utc)
    }
    result = await db.users.insert_one(user_doc)
    user_id = str(result.inserted_id)
    
    access_token = create_access_token(user_id, email)
    refresh_token = create_refresh_token(user_id)
    
    response.set_cookie(key="access_token", value=access_token, httponly=True, secure=False, samesite="lax", max_age=900, path="/")
    response.set_cookie(key="refresh_token", value=refresh_token, httponly=True, secure=False, samesite="lax", max_age=604800, path="/")
    
    return {"id": user_id, "name": data.name, "email": email, "role": "user"}

@api_router.post("/auth/login")
async def login(response: Response, data: UserLogin):
    email = data.email.lower()
    user = await db.users.find_one({"email": email})
    if not user:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    
    if not verify_password(data.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    
    user_id = str(user["_id"])
    access_token = create_access_token(user_id, email)
    refresh_token = create_refresh_token(user_id)
    
    response.set_cookie(key="access_token", value=access_token, httponly=True, secure=False, samesite="lax", max_age=900, path="/")
    response.set_cookie(key="refresh_token", value=refresh_token, httponly=True, secure=False, samesite="lax", max_age=604800, path="/")
    
    return {"id": user_id, "name": user["name"], "email": email, "role": user.get("role", "user")}

@api_router.post("/auth/logout")
async def logout(response: Response):
    response.delete_cookie(key="access_token", path="/")
    response.delete_cookie(key="refresh_token", path="/")
    return {"message": "Logged out"}

@api_router.get("/auth/me")
async def get_me(user: dict = Depends(get_current_user)):
    return user

@api_router.post("/auth/refresh")
async def refresh_token(request: Request, response: Response):
    token = request.cookies.get("refresh_token")
    if not token:
        raise HTTPException(status_code=401, detail="No refresh token")
    try:
        payload = jwt.decode(token, get_jwt_secret(), algorithms=[JWT_ALGORITHM])
        if payload.get("type") != "refresh":
            raise HTTPException(status_code=401, detail="Invalid token type")
        user = await db.users.find_one({"_id": ObjectId(payload["sub"])})
        if not user:
            raise HTTPException(status_code=401, detail="User not found")
        
        user_id = str(user["_id"])
        access_token = create_access_token(user_id, user["email"])
        response.set_cookie(key="access_token", value=access_token, httponly=True, secure=False, samesite="lax", max_age=900, path="/")
        return {"message": "Token refreshed"}
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Refresh token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")

# ============ DYNAMIC UPLOAD ENDPOINTS ============

@api_router.post("/upload/naukri", response_model=UploadResponse)
async def upload_naukri(file: UploadFile = File(...), user: dict = Depends(get_current_user)):
    try:
        content = await file.read()
        if len(content) > 10 * 1024 * 1024:
            raise HTTPException(status_code=400, detail="File size exceeds 10MB limit")
        
        df = parse_file(content, file.filename)
        df.columns = df.columns.str.strip()
        
        # Dynamically detect identifier columns
        identifiers = detect_identifier_columns(df.columns.tolist())
        email_col = identifiers["email"]
        phone_col = identifiers["phone"]
        
        if not email_col and not phone_col:
            raise HTTPException(status_code=400, detail="Could not detect Email or Phone column. Please ensure your file has an email or phone column.")
        
        # Detect other important columns
        name_col = detect_name_column(df)
        job_role_col = detect_job_role_column(df)
        
        # Store schema metadata
        schema_info = {
            "columns": df.columns.tolist(),
            "email_column": email_col,
            "phone_column": phone_col,
            "name_column": name_col,
            "job_role_column": job_role_col,
            "total_columns": len(df.columns)
        }
        
        # Update schema in database
        await db.schema_metadata.update_one(
            {"type": "naukri"},
            {"$set": {**schema_info, "updated_at": datetime.now(timezone.utc)}},
            upsert=True
        )
        
        total_records = len(df)
        errors = []
        valid_records = 0
        duplicate_records = 0
        invalid_records = 0
        
        for idx, row in df.iterrows():
            try:
                # Extract and normalize identifiers
                email = normalize_email(row.get(email_col)) if email_col else ""
                phone = normalize_phone(row.get(phone_col)) if phone_col else ""
                
                if not email and not phone:
                    errors.append(f"Row {idx + 2}: Missing both email and phone")
                    invalid_records += 1
                    continue
                
                # Check for duplicates
                query_conditions = []
                if email:
                    query_conditions.append({"_normalized_email": email})
                if phone:
                    query_conditions.append({"_normalized_phone": phone})
                
                existing = await db.naukri_applies_raw.find_one({"$or": query_conditions}) if query_conditions else None
                
                if existing:
                    duplicate_records += 1
                    continue
                
                # Store ALL fields dynamically
                doc = {col: clean_value(row[col]) for col in df.columns}
                
                # Add normalized fields and metadata
                doc["_normalized_email"] = email
                doc["_normalized_phone"] = phone
                doc["_source"] = "naukri"
                doc["_created_at"] = datetime.now(timezone.utc)
                doc["_uploaded_by"] = user["_id"]
                
                await db.naukri_applies_raw.insert_one(doc)
                valid_records += 1
                
            except Exception as e:
                errors.append(f"Row {idx + 2}: {str(e)}")
                invalid_records += 1
        
        # Log upload history
        await db.upload_history.insert_one({
            "type": "naukri",
            "filename": file.filename,
            "schema_info": schema_info,
            "total_records": total_records,
            "valid_records": valid_records,
            "duplicate_records": duplicate_records,
            "invalid_records": invalid_records,
            "uploaded_by": user["_id"],
            "uploaded_at": datetime.now(timezone.utc)
        })
        
        return UploadResponse(
            success=True,
            message="Naukri data uploaded successfully",
            total_records=total_records,
            valid_records=valid_records,
            duplicate_records=duplicate_records,
            invalid_records=invalid_records,
            errors=errors[:10],
            schema_info=schema_info
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@api_router.post("/upload/pipeline", response_model=UploadResponse)
async def upload_pipeline(file: UploadFile = File(...), user: dict = Depends(get_current_user)):
    try:
        content = await file.read()
        if len(content) > 10 * 1024 * 1024:
            raise HTTPException(status_code=400, detail="File size exceeds 10MB limit")
        
        df = parse_file(content, file.filename)
        df.columns = df.columns.str.strip()
        
        # Dynamically detect columns
        identifiers = detect_identifier_columns(df.columns.tolist())
        email_col = identifiers["email"]
        phone_col = identifiers["phone"]
        
        if not email_col and not phone_col:
            raise HTTPException(status_code=400, detail="Could not detect Email or Phone column. Please ensure your file has an email or phone column.")
        
        # Detect other columns
        name_col = detect_name_column(df)
        job_role_col = detect_job_role_column(df)
        status_col = detect_status_column(df)
        
        # Get unique status values if status column exists
        status_values = []
        if status_col:
            status_values = df[status_col].dropna().astype(str).str.strip().unique().tolist()
        
        # Store schema metadata
        schema_info = {
            "columns": df.columns.tolist(),
            "email_column": email_col,
            "phone_column": phone_col,
            "name_column": name_col,
            "job_role_column": job_role_col,
            "status_column": status_col,
            "status_values": status_values,
            "total_columns": len(df.columns)
        }
        
        # Update schema in database
        await db.schema_metadata.update_one(
            {"type": "pipeline"},
            {"$set": {**schema_info, "updated_at": datetime.now(timezone.utc)}},
            upsert=True
        )
        
        total_records = len(df)
        errors = []
        valid_records = 0
        duplicate_records = 0
        invalid_records = 0
        
        for idx, row in df.iterrows():
            try:
                email = normalize_email(row.get(email_col)) if email_col else ""
                phone = normalize_phone(row.get(phone_col)) if phone_col else ""
                
                if not email and not phone:
                    errors.append(f"Row {idx + 2}: Missing both email and phone")
                    invalid_records += 1
                    continue
                
                # Check for duplicates
                query_conditions = []
                if email:
                    query_conditions.append({"_normalized_email": email})
                if phone:
                    query_conditions.append({"_normalized_phone": phone})
                
                existing = await db.pipeline_data_raw.find_one({"$or": query_conditions}) if query_conditions else None
                
                if existing:
                    duplicate_records += 1
                    continue
                
                # Store ALL fields dynamically
                doc = {col: clean_value(row[col]) for col in df.columns}
                
                # Add normalized fields and metadata
                doc["_normalized_email"] = email
                doc["_normalized_phone"] = phone
                doc["_normalized_status"] = str(row.get(status_col, "")).strip().lower() if status_col else None
                doc["_source"] = "pipeline"
                doc["_created_at"] = datetime.now(timezone.utc)
                doc["_uploaded_by"] = user["_id"]
                
                await db.pipeline_data_raw.insert_one(doc)
                valid_records += 1
                
            except Exception as e:
                errors.append(f"Row {idx + 2}: {str(e)}")
                invalid_records += 1
        
        # Log upload history
        await db.upload_history.insert_one({
            "type": "pipeline",
            "filename": file.filename,
            "schema_info": schema_info,
            "total_records": total_records,
            "valid_records": valid_records,
            "duplicate_records": duplicate_records,
            "invalid_records": invalid_records,
            "uploaded_by": user["_id"],
            "uploaded_at": datetime.now(timezone.utc)
        })
        
        return UploadResponse(
            success=True,
            message="Pipeline data uploaded successfully",
            total_records=total_records,
            valid_records=valid_records,
            duplicate_records=duplicate_records,
            invalid_records=invalid_records,
            errors=errors[:10],
            schema_info=schema_info
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ============ PROCESSING ENDPOINT ============

@api_router.post("/process-data")
async def process_data(user: dict = Depends(get_current_user)):
    try:
        # Clear existing processed data
        await db.processed_candidates.delete_many({})
        
        # Get schema metadata
        naukri_schema = await db.schema_metadata.find_one({"type": "naukri"})
        pipeline_schema = await db.schema_metadata.find_one({"type": "pipeline"})
        
        # Get all naukri applies
        naukri_cursor = db.naukri_applies_raw.find({})
        naukri_list = await naukri_cursor.to_list(None)
        
        # Get all pipeline data
        pipeline_cursor = db.pipeline_data_raw.find({})
        pipeline_list = await pipeline_cursor.to_list(None)
        
        # Create lookup dicts for pipeline data
        pipeline_by_email = {}
        pipeline_by_phone = {}
        
        for p in pipeline_list:
            if p.get('_normalized_email'):
                pipeline_by_email[p['_normalized_email']] = p
            if p.get('_normalized_phone'):
                pipeline_by_phone[p['_normalized_phone']] = p
        
        processed_count = 0
        registered_count = 0
        not_registered_count = 0
        status_counts = {}
        
        for naukri in naukri_list:
            email = naukri.get('_normalized_email', '')
            phone = naukri.get('_normalized_phone', '')
            
            # Match by email first, then phone
            pipeline_match = None
            if email and email in pipeline_by_email:
                pipeline_match = pipeline_by_email[email]
            elif phone and phone in pipeline_by_phone:
                pipeline_match = pipeline_by_phone[phone]
            
            # Create processed document with all original fields
            doc = {k: v for k, v in naukri.items() if not k.startswith('_id')}
            doc["_naukri_id"] = str(naukri["_id"])
            
            if pipeline_match:
                # Merge pipeline data
                doc["_registration_status"] = "registered"
                doc["_pipeline_id"] = str(pipeline_match["_id"])
                doc["_pipeline_status"] = pipeline_match.get("_normalized_status", "unknown")
                
                # Copy all pipeline fields with prefix
                for k, v in pipeline_match.items():
                    if not k.startswith('_'):
                        doc[f"_pipeline_{k}"] = v
                
                registered_count += 1
                
                # Count status
                status = doc["_pipeline_status"]
                status_counts[status] = status_counts.get(status, 0) + 1
            else:
                doc["_registration_status"] = "not_registered"
                doc["_pipeline_status"] = None
                not_registered_count += 1
            
            doc["_processed_at"] = datetime.now(timezone.utc)
            await db.processed_candidates.insert_one(doc)
            processed_count += 1
        
        return {
            "success": True,
            "message": "Data processed successfully",
            "total_processed": processed_count,
            "registered": registered_count,
            "not_registered": not_registered_count,
            "status_breakdown": status_counts
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ============ ANALYTICS ENDPOINT ============

@api_router.get("/analytics")
async def get_analytics(job_role: Optional[str] = Query(None), user: dict = Depends(get_current_user)):
    try:
        # Get schema metadata
        naukri_schema = await db.schema_metadata.find_one({"type": "naukri"})
        pipeline_schema = await db.schema_metadata.find_one({"type": "pipeline"})
        
        job_role_col = None
        if naukri_schema:
            job_role_col = naukri_schema.get("job_role_column")
        
        # Build filter
        match_filter = {}
        if job_role and job_role != "all" and job_role_col:
            match_filter[job_role_col] = job_role
        
        # Get total counts
        total_naukri = await db.processed_candidates.count_documents(match_filter)
        
        if total_naukri == 0:
            # Get job roles from raw data
            job_roles = []
            if job_role_col:
                job_roles = await db.naukri_applies_raw.distinct(job_role_col)
                job_roles = [r for r in job_roles if r]
            
            # Clean schema objects by removing _id fields
            clean_naukri_schema = None
            clean_pipeline_schema = None
            if naukri_schema:
                clean_naukri_schema = {k: v for k, v in naukri_schema.items() if k != "_id"}
            if pipeline_schema:
                clean_pipeline_schema = {k: v for k, v in pipeline_schema.items() if k != "_id"}
            
            return {
                "total_naukri_applies": 0,
                "registered": 0,
                "not_registered": 0,
                "status_breakdown": {},
                "job_roles": job_roles,
                "job_role_column": job_role_col,
                "schema": {
                    "naukri": clean_naukri_schema,
                    "pipeline": clean_pipeline_schema
                }
            }
        
        # Registration counts
        registered_filter = {**match_filter, "_registration_status": "registered"}
        not_registered_filter = {**match_filter, "_registration_status": "not_registered"}
        
        registered = await db.processed_candidates.count_documents(registered_filter)
        not_registered = await db.processed_candidates.count_documents(not_registered_filter)
        
        # Dynamic status breakdown
        status_breakdown = {}
        if pipeline_schema and pipeline_schema.get("status_values"):
            for status in pipeline_schema["status_values"]:
                status_lower = status.lower().strip()
                count = await db.processed_candidates.count_documents({
                    **registered_filter,
                    "_pipeline_status": status_lower
                })
                status_breakdown[status] = count
        
        # Also get any statuses not in original schema
        pipeline = [
            {"$match": registered_filter},
            {"$group": {"_id": "$_pipeline_status", "count": {"$sum": 1}}}
        ]
        status_agg = await db.processed_candidates.aggregate(pipeline).to_list(None)
        for item in status_agg:
            if item["_id"] and item["_id"] not in [s.lower() for s in status_breakdown.keys()]:
                status_breakdown[item["_id"]] = item["count"]
        
        # Get distinct job roles
        job_roles = []
        if job_role_col:
            job_roles = await db.processed_candidates.distinct(job_role_col)
            job_roles = [r for r in job_roles if r]
        
        # Clean schema objects by removing _id fields
        clean_naukri_schema = None
        clean_pipeline_schema = None
        if naukri_schema:
            clean_naukri_schema = {k: v for k, v in naukri_schema.items() if k != "_id"}
        if pipeline_schema:
            clean_pipeline_schema = {k: v for k, v in pipeline_schema.items() if k != "_id"}
        
        return {
            "total_naukri_applies": total_naukri,
            "registered": registered,
            "not_registered": not_registered,
            "status_breakdown": status_breakdown,
            "job_roles": job_roles,
            "job_role_column": job_role_col,
            "schema": {
                "naukri": clean_naukri_schema,
                "pipeline": clean_pipeline_schema
            }
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ============ DATA ENDPOINTS ============

@api_router.get("/data")
async def get_data(
    source: str = Query("all", description="naukri, pipeline, processed, or all"),
    job_role: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    registration: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=500),
    user: dict = Depends(get_current_user)
):
    try:
        # Get schema metadata
        naukri_schema = await db.schema_metadata.find_one({"type": "naukri"})
        pipeline_schema = await db.schema_metadata.find_one({"type": "pipeline"})
        
        # Clean schema objects by removing _id
        clean_naukri_schema = {k: v for k, v in naukri_schema.items() if k != "_id"} if naukri_schema else None
        clean_pipeline_schema = {k: v for k, v in pipeline_schema.items() if k != "_id"} if pipeline_schema else None
        
        result = {
            "naukri": None,
            "pipeline": None,
            "processed": None,
            "schemas": {
                "naukri": clean_naukri_schema,
                "pipeline": clean_pipeline_schema
            }
        }
        
        skip = (page - 1) * limit
        
        # Build filters
        def build_search_filter(schema, search_term):
            if not search_term or not schema:
                return {}
            
            conditions = []
            email_col = schema.get("email_column")
            name_col = schema.get("name_column")
            phone_col = schema.get("phone_column")
            
            if email_col:
                conditions.append({email_col: {"$regex": search_term, "$options": "i"}})
            if name_col:
                conditions.append({name_col: {"$regex": search_term, "$options": "i"}})
            if phone_col:
                conditions.append({phone_col: {"$regex": search_term, "$options": "i"}})
            
            return {"$or": conditions} if conditions else {}
        
        if source in ["naukri", "all"]:
            naukri_filter = {}
            if job_role and job_role != "all" and naukri_schema:
                job_role_col = naukri_schema.get("job_role_column")
                if job_role_col:
                    naukri_filter[job_role_col] = job_role
            
            if search and naukri_schema:
                search_filter = build_search_filter(naukri_schema, search)
                naukri_filter.update(search_filter)
            
            total_naukri = await db.naukri_applies_raw.count_documents(naukri_filter)
            naukri_data = await db.naukri_applies_raw.find(
                naukri_filter, 
                {"_id": 0}
            ).skip(skip).limit(limit).to_list(None)
            
            # Clean datetime objects
            for record in naukri_data:
                for k, v in record.items():
                    if isinstance(v, datetime):
                        record[k] = v.isoformat()
            
            result["naukri"] = {
                "data": naukri_data,
                "total": total_naukri,
                "page": page,
                "limit": limit,
                "columns": naukri_schema.get("columns", []) if naukri_schema else []
            }
        
        if source in ["pipeline", "all"]:
            pipeline_filter = {}
            if status and status != "all" and pipeline_schema:
                pipeline_filter["_normalized_status"] = status.lower()
            
            if job_role and job_role != "all" and pipeline_schema:
                job_role_col = pipeline_schema.get("job_role_column")
                if job_role_col:
                    pipeline_filter[job_role_col] = job_role
            
            if search and pipeline_schema:
                search_filter = build_search_filter(pipeline_schema, search)
                pipeline_filter.update(search_filter)
            
            total_pipeline = await db.pipeline_data_raw.count_documents(pipeline_filter)
            pipeline_data = await db.pipeline_data_raw.find(
                pipeline_filter,
                {"_id": 0}
            ).skip(skip).limit(limit).to_list(None)
            
            for record in pipeline_data:
                for k, v in record.items():
                    if isinstance(v, datetime):
                        record[k] = v.isoformat()
            
            result["pipeline"] = {
                "data": pipeline_data,
                "total": total_pipeline,
                "page": page,
                "limit": limit,
                "columns": pipeline_schema.get("columns", []) if pipeline_schema else []
            }
        
        if source in ["processed", "all"]:
            processed_filter = {}
            if registration and registration != "all":
                processed_filter["_registration_status"] = registration
            
            if status and status != "all":
                processed_filter["_pipeline_status"] = status.lower()
            
            if job_role and job_role != "all" and naukri_schema:
                job_role_col = naukri_schema.get("job_role_column")
                if job_role_col:
                    processed_filter[job_role_col] = job_role
            
            if search:
                conditions = []
                if naukri_schema:
                    email_col = naukri_schema.get("email_column")
                    name_col = naukri_schema.get("name_column")
                    if email_col:
                        conditions.append({email_col: {"$regex": search, "$options": "i"}})
                    if name_col:
                        conditions.append({name_col: {"$regex": search, "$options": "i"}})
                if conditions:
                    processed_filter["$or"] = conditions
            
            total_processed = await db.processed_candidates.count_documents(processed_filter)
            processed_data = await db.processed_candidates.find(
                processed_filter,
                {"_id": 0}
            ).skip(skip).limit(limit).to_list(None)
            
            for record in processed_data:
                for k, v in record.items():
                    if isinstance(v, datetime):
                        record[k] = v.isoformat()
            
            # Get combined columns
            combined_columns = []
            if naukri_schema:
                combined_columns.extend(naukri_schema.get("columns", []))
            combined_columns.extend(["_registration_status", "_pipeline_status"])
            
            result["processed"] = {
                "data": processed_data,
                "total": total_processed,
                "page": page,
                "limit": limit,
                "columns": combined_columns
            }
        
        return result
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ============ SCHEMA ENDPOINT ============

@api_router.get("/schema")
async def get_schema(user: dict = Depends(get_current_user)):
    """Get current schema metadata for both datasets"""
    naukri_schema = await db.schema_metadata.find_one({"type": "naukri"}, {"_id": 0})
    pipeline_schema = await db.schema_metadata.find_one({"type": "pipeline"}, {"_id": 0})
    
    return {
        "naukri": naukri_schema,
        "pipeline": pipeline_schema
    }

# ============ CSV DOWNLOAD ENDPOINT ============

@api_router.get("/analytics/download")
async def download_analytics(
    source: str = Query("processed"),
    job_role: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    registration: Optional[str] = Query(None),
    user: dict = Depends(get_current_user)
):
    try:
        naukri_schema = await db.schema_metadata.find_one({"type": "naukri"})
        
        filter_query = {}
        
        if source == "processed":
            if registration and registration != "all":
                filter_query["_registration_status"] = registration
            if status and status != "all":
                filter_query["_pipeline_status"] = status.lower()
            if job_role and job_role != "all" and naukri_schema:
                job_role_col = naukri_schema.get("job_role_column")
                if job_role_col:
                    filter_query[job_role_col] = job_role
            
            cursor = db.processed_candidates.find(filter_query, {"_id": 0})
        elif source == "naukri":
            if job_role and job_role != "all" and naukri_schema:
                job_role_col = naukri_schema.get("job_role_column")
                if job_role_col:
                    filter_query[job_role_col] = job_role
            cursor = db.naukri_applies_raw.find(filter_query, {"_id": 0})
        elif source == "pipeline":
            pipeline_schema = await db.schema_metadata.find_one({"type": "pipeline"})
            if status and status != "all":
                filter_query["_normalized_status"] = status.lower()
            if job_role and job_role != "all" and pipeline_schema:
                job_role_col = pipeline_schema.get("job_role_column")
                if job_role_col:
                    filter_query[job_role_col] = job_role
            cursor = db.pipeline_data_raw.find(filter_query, {"_id": 0})
        else:
            raise HTTPException(status_code=400, detail="Invalid source")
        
        data = await cursor.to_list(None)
        
        if not data:
            raise HTTPException(status_code=404, detail="No data to download")
        
        # Get all columns from data
        all_columns = set()
        for record in data:
            all_columns.update(record.keys())
        
        # Filter out internal fields for cleaner export
        export_columns = [c for c in all_columns if not c.startswith('_') or c in ['_registration_status', '_pipeline_status']]
        export_columns.sort()
        
        # Create CSV
        output = io.StringIO()
        writer = csv.DictWriter(output, fieldnames=export_columns, extrasaction='ignore')
        writer.writeheader()
        
        for record in data:
            # Clean datetime values
            clean_record = {}
            for k, v in record.items():
                if isinstance(v, datetime):
                    clean_record[k] = v.isoformat()
                else:
                    clean_record[k] = v
            writer.writerow(clean_record)
        
        csv_content = output.getvalue()
        
        return Response(
            content=csv_content,
            media_type="text/csv",
            headers={"Content-Disposition": f"attachment; filename={source}_data.csv"}
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ============ RESET DATA ENDPOINT ============

@api_router.delete("/reset-data")
async def reset_data(source: str = Query("all"), user: dict = Depends(get_current_user)):
    """Reset data for fresh upload"""
    try:
        if source in ["naukri", "all"]:
            await db.naukri_applies_raw.delete_many({})
            await db.schema_metadata.delete_one({"type": "naukri"})
        
        if source in ["pipeline", "all"]:
            await db.pipeline_data_raw.delete_many({})
            await db.schema_metadata.delete_one({"type": "pipeline"})
        
        if source in ["processed", "all"]:
            await db.processed_candidates.delete_many({})
        
        return {"success": True, "message": f"Data reset successfully for: {source}"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# Health check
@api_router.get("/")
async def root():
    return {"message": "Recruitment Analytics API", "status": "healthy", "version": "2.0"}

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
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Admin seeding on startup
@app.on_event("startup")
async def startup_event():
    # Create indexes
    await db.users.create_index("email", unique=True)
    await db.naukri_applies_raw.create_index([("_normalized_email", 1), ("_normalized_phone", 1)])
    await db.pipeline_data_raw.create_index([("_normalized_email", 1), ("_normalized_phone", 1)])
    await db.processed_candidates.create_index("_registration_status")
    await db.processed_candidates.create_index("_pipeline_status")
    
    # Seed admin
    admin_email = os.environ.get("ADMIN_EMAIL", "admin@recruitment.com")
    admin_password = os.environ.get("ADMIN_PASSWORD", "Admin123!")
    
    existing = await db.users.find_one({"email": admin_email})
    if existing is None:
        hashed = hash_password(admin_password)
        await db.users.insert_one({
            "email": admin_email,
            "password_hash": hashed,
            "name": "Admin",
            "role": "admin",
            "created_at": datetime.now(timezone.utc)
        })
        logger.info(f"Admin user created: {admin_email}")
    elif not verify_password(admin_password, existing["password_hash"]):
        await db.users.update_one(
            {"email": admin_email},
            {"$set": {"password_hash": hash_password(admin_password)}}
        )
        logger.info(f"Admin password updated: {admin_email}")
    
    # Write test credentials
    try:
        os.makedirs("/app/memory", exist_ok=True)
        with open("/app/memory/test_credentials.md", "w") as f:
            f.write("# Test Credentials\n\n")
            f.write("## Admin Account\n")
            f.write(f"- Email: {admin_email}\n")
            f.write(f"- Password: {admin_password}\n")
            f.write("- Role: admin\n")
    except Exception as e:
        logger.error(f"Failed to write test credentials: {e}")

@app.on_event("shutdown")
async def shutdown_db_client():
    client.close()
