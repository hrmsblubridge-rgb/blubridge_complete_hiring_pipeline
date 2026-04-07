from dotenv import load_dotenv
from pathlib import Path

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

from fastapi import FastAPI, APIRouter, HTTPException, Request, Response, UploadFile, File, Depends, Query
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
import os
import logging
from pydantic import BaseModel, Field, EmailStr
from typing import List, Optional
import uuid
from datetime import datetime, timezone, timedelta
import bcrypt
import jwt
from bson import ObjectId
import pandas as pd
import io
import re
import csv

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
        "exp": datetime.now(timezone.utc) + timedelta(minutes=15),
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

class UserResponse(BaseModel):
    id: str
    name: str
    email: str
    role: str

class UploadResponse(BaseModel):
    success: bool
    message: str
    total_records: int
    valid_records: int
    duplicate_records: int
    invalid_records: int
    errors: List[str]

class AnalyticsResponse(BaseModel):
    total_naukri_applies: int
    registered: int
    not_registered: int
    shortlisted: int
    rejected: int
    scheduled: int
    not_scheduled: int
    attended: int
    not_attended: int
    job_roles: List[str]

# Auth Endpoints
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

# Helper functions for data processing
def normalize_phone(phone):
    if pd.isna(phone) or phone is None:
        return ""
    phone_str = str(phone).strip()
    # Remove spaces, dashes, country codes
    phone_str = re.sub(r'[\s\-\(\)\+]', '', phone_str)
    # Remove country code if present (assuming +91 or 91 at start)
    if phone_str.startswith('91') and len(phone_str) > 10:
        phone_str = phone_str[2:]
    return phone_str

def normalize_email(email):
    if pd.isna(email) or email is None:
        return ""
    return str(email).strip().lower()

def parse_file(file_content: bytes, filename: str) -> pd.DataFrame:
    if filename.endswith('.csv'):
        return pd.read_csv(io.BytesIO(file_content))
    elif filename.endswith('.xlsx') or filename.endswith('.xls'):
        return pd.read_excel(io.BytesIO(file_content))
    else:
        raise ValueError("Unsupported file format. Use .csv or .xlsx")

# Upload Endpoints
@api_router.post("/upload/naukri", response_model=UploadResponse)
async def upload_naukri(file: UploadFile = File(...), user: dict = Depends(get_current_user)):
    try:
        content = await file.read()
        if len(content) > 10 * 1024 * 1024:  # 10MB limit
            raise HTTPException(status_code=400, detail="File size exceeds 10MB limit")
        
        df = parse_file(content, file.filename)
        
        # Validate required columns (case-insensitive)
        df.columns = df.columns.str.strip()
        column_map = {col.lower(): col for col in df.columns}
        required = ['name', 'email', 'phone number', 'job role']
        missing = [r for r in required if r not in column_map]
        
        if missing:
            raise HTTPException(status_code=400, detail=f"Missing columns: {', '.join(missing)}")
        
        # Rename columns to standard names
        df = df.rename(columns={
            column_map['name']: 'name',
            column_map['email']: 'email',
            column_map['phone number']: 'phone',
            column_map['job role']: 'job_role'
        })
        
        total_records = len(df)
        errors = []
        valid_records = 0
        duplicate_records = 0
        invalid_records = 0
        
        for idx, row in df.iterrows():
            try:
                email = normalize_email(row.get('email'))
                phone = normalize_phone(row.get('phone'))
                name = str(row.get('name', '')).strip() if not pd.isna(row.get('name')) else ''
                job_role = str(row.get('job_role', '')).strip() if not pd.isna(row.get('job_role')) else ''
                
                if not email and not phone:
                    errors.append(f"Row {idx + 2}: Missing both email and phone")
                    invalid_records += 1
                    continue
                
                if not name:
                    errors.append(f"Row {idx + 2}: Missing name")
                    invalid_records += 1
                    continue
                
                # Check for duplicates
                existing = await db.naukri_applies.find_one({
                    "$or": [
                        {"email": email} if email else {"_id": None},
                        {"phone": phone} if phone else {"_id": None}
                    ]
                })
                
                if existing:
                    duplicate_records += 1
                    continue
                
                doc = {
                    "name": name,
                    "email": email,
                    "phone": phone,
                    "job_role": job_role,
                    "created_at": datetime.now(timezone.utc),
                    "uploaded_by": user["_id"]
                }
                await db.naukri_applies.insert_one(doc)
                valid_records += 1
                
            except Exception as e:
                errors.append(f"Row {idx + 2}: {str(e)}")
                invalid_records += 1
        
        # Log upload history
        await db.upload_history.insert_one({
            "type": "naukri",
            "filename": file.filename,
            "total_records": total_records,
            "valid_records": valid_records,
            "duplicate_records": duplicate_records,
            "invalid_records": invalid_records,
            "uploaded_by": user["_id"],
            "uploaded_at": datetime.now(timezone.utc)
        })
        
        return UploadResponse(
            success=True,
            message="Naukri applies uploaded successfully",
            total_records=total_records,
            valid_records=valid_records,
            duplicate_records=duplicate_records,
            invalid_records=invalid_records,
            errors=errors[:10]  # Return first 10 errors
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@api_router.post("/upload/pipeline", response_model=UploadResponse)
async def upload_pipeline(file: UploadFile = File(...), user: dict = Depends(get_current_user)):
    try:
        content = await file.read()
        if len(content) > 10 * 1024 * 1024:  # 10MB limit
            raise HTTPException(status_code=400, detail="File size exceeds 10MB limit")
        
        df = parse_file(content, file.filename)
        
        # Validate required columns (case-insensitive)
        df.columns = df.columns.str.strip()
        column_map = {col.lower(): col for col in df.columns}
        required = ['name', 'email', 'phone number', 'job role', 'status']
        missing = [r for r in required if r not in column_map]
        
        if missing:
            raise HTTPException(status_code=400, detail=f"Missing columns: {', '.join(missing)}")
        
        # Rename columns to standard names
        df = df.rename(columns={
            column_map['name']: 'name',
            column_map['email']: 'email',
            column_map['phone number']: 'phone',
            column_map['job role']: 'job_role',
            column_map['status']: 'status'
        })
        
        valid_statuses = ['shortlisted', 'rejected', 'scheduled', 'attended', 'not attended', 'not scheduled']
        total_records = len(df)
        errors = []
        valid_records = 0
        duplicate_records = 0
        invalid_records = 0
        
        for idx, row in df.iterrows():
            try:
                email = normalize_email(row.get('email'))
                phone = normalize_phone(row.get('phone'))
                name = str(row.get('name', '')).strip() if not pd.isna(row.get('name')) else ''
                job_role = str(row.get('job_role', '')).strip() if not pd.isna(row.get('job_role')) else ''
                status = str(row.get('status', '')).strip().lower() if not pd.isna(row.get('status')) else ''
                
                if not email and not phone:
                    errors.append(f"Row {idx + 2}: Missing both email and phone")
                    invalid_records += 1
                    continue
                
                if not name:
                    errors.append(f"Row {idx + 2}: Missing name")
                    invalid_records += 1
                    continue
                
                if status not in valid_statuses:
                    errors.append(f"Row {idx + 2}: Invalid status '{status}'")
                    invalid_records += 1
                    continue
                
                # Check for duplicates
                existing = await db.pipeline_data.find_one({
                    "$or": [
                        {"email": email} if email else {"_id": None},
                        {"phone": phone} if phone else {"_id": None}
                    ]
                })
                
                if existing:
                    duplicate_records += 1
                    continue
                
                doc = {
                    "name": name,
                    "email": email,
                    "phone": phone,
                    "job_role": job_role,
                    "status": status,
                    "created_at": datetime.now(timezone.utc),
                    "uploaded_by": user["_id"]
                }
                await db.pipeline_data.insert_one(doc)
                valid_records += 1
                
            except Exception as e:
                errors.append(f"Row {idx + 2}: {str(e)}")
                invalid_records += 1
        
        # Log upload history
        await db.upload_history.insert_one({
            "type": "pipeline",
            "filename": file.filename,
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
            errors=errors[:10]
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# Processing Endpoint
@api_router.post("/process")
async def process_data(user: dict = Depends(get_current_user)):
    try:
        # Clear existing processed data
        await db.processed_candidates.delete_many({})
        
        # Get all naukri applies
        naukri_cursor = db.naukri_applies.find({}, {"_id": 0})
        naukri_list = await naukri_cursor.to_list(None)
        
        # Get all pipeline data
        pipeline_cursor = db.pipeline_data.find({}, {"_id": 0})
        pipeline_list = await pipeline_cursor.to_list(None)
        
        # Create lookup dict for pipeline data
        pipeline_by_email = {p['email']: p for p in pipeline_list if p.get('email')}
        pipeline_by_phone = {p['phone']: p for p in pipeline_list if p.get('phone')}
        
        processed_count = 0
        registered_count = 0
        not_registered_count = 0
        
        for naukri in naukri_list:
            email = naukri.get('email', '')
            phone = naukri.get('phone', '')
            
            # Try to match by email first, then phone
            pipeline_match = None
            if email and email in pipeline_by_email:
                pipeline_match = pipeline_by_email[email]
            elif phone and phone in pipeline_by_phone:
                pipeline_match = pipeline_by_phone[phone]
            
            if pipeline_match:
                # Registered
                status = pipeline_match.get('status', 'shortlisted')
                registered_count += 1
            else:
                # Not Registered
                status = 'not_registered'
                not_registered_count += 1
            
            doc = {
                "name": naukri.get('name'),
                "email": email,
                "phone": phone,
                "job_role": naukri.get('job_role'),
                "registration_status": "registered" if pipeline_match else "not_registered",
                "status": status,
                "processed_at": datetime.now(timezone.utc)
            }
            await db.processed_candidates.insert_one(doc)
            processed_count += 1
        
        return {
            "success": True,
            "message": "Data processed successfully",
            "total_processed": processed_count,
            "registered": registered_count,
            "not_registered": not_registered_count
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# Analytics Endpoint
@api_router.get("/analytics")
async def get_analytics(job_role: Optional[str] = Query(None), user: dict = Depends(get_current_user)):
    try:
        # Build filter
        match_filter = {}
        if job_role and job_role != "all":
            match_filter["job_role"] = job_role
        
        # Get total naukri applies
        total_naukri = await db.processed_candidates.count_documents(match_filter)
        
        # If no processed data, return zeros
        if total_naukri == 0:
            # Get job roles from raw naukri data
            job_roles = await db.naukri_applies.distinct("job_role")
            return {
                "total_naukri_applies": 0,
                "registered": 0,
                "not_registered": 0,
                "shortlisted": 0,
                "rejected": 0,
                "scheduled": 0,
                "not_scheduled": 0,
                "attended": 0,
                "not_attended": 0,
                "job_roles": [r for r in job_roles if r]
            }
        
        # Registered vs Not Registered
        registered_filter = {**match_filter, "registration_status": "registered"}
        not_registered_filter = {**match_filter, "registration_status": "not_registered"}
        
        registered = await db.processed_candidates.count_documents(registered_filter)
        not_registered = await db.processed_candidates.count_documents(not_registered_filter)
        
        # Status counts (from registered candidates only)
        shortlisted = await db.processed_candidates.count_documents({**registered_filter, "status": "shortlisted"})
        rejected = await db.processed_candidates.count_documents({**registered_filter, "status": "rejected"})
        scheduled = await db.processed_candidates.count_documents({**registered_filter, "status": "scheduled"})
        not_scheduled = await db.processed_candidates.count_documents({**registered_filter, "status": "not scheduled"})
        attended = await db.processed_candidates.count_documents({**registered_filter, "status": "attended"})
        not_attended = await db.processed_candidates.count_documents({**registered_filter, "status": "not attended"})
        
        # Get distinct job roles
        job_roles = await db.processed_candidates.distinct("job_role")
        
        return {
            "total_naukri_applies": total_naukri,
            "registered": registered,
            "not_registered": not_registered,
            "shortlisted": shortlisted,
            "rejected": rejected,
            "scheduled": scheduled,
            "not_scheduled": not_scheduled,
            "attended": attended,
            "not_attended": not_attended,
            "job_roles": [r for r in job_roles if r]
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# CSV Download Endpoint
@api_router.get("/analytics/download")
async def download_analytics(job_role: Optional[str] = Query(None), user: dict = Depends(get_current_user)):
    try:
        match_filter = {}
        if job_role and job_role != "all":
            match_filter["job_role"] = job_role
        
        cursor = db.processed_candidates.find(match_filter, {"_id": 0, "processed_at": 0})
        candidates = await cursor.to_list(None)
        
        if not candidates:
            raise HTTPException(status_code=404, detail="No data to download")
        
        # Create CSV
        output = io.StringIO()
        writer = csv.DictWriter(output, fieldnames=['name', 'email', 'phone', 'job_role', 'registration_status', 'status'])
        writer.writeheader()
        writer.writerows(candidates)
        
        csv_content = output.getvalue()
        
        return Response(
            content=csv_content,
            media_type="text/csv",
            headers={"Content-Disposition": "attachment; filename=analytics_report.csv"}
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# Health check
@api_router.get("/")
async def root():
    return {"message": "Recruitment Analytics API", "status": "healthy"}

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
    await db.naukri_applies.create_index([("email", 1), ("phone", 1)])
    await db.pipeline_data.create_index([("email", 1), ("phone", 1)])
    await db.processed_candidates.create_index("job_role")
    
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
            f.write("- Role: admin\n\n")
            f.write("## Auth Endpoints\n")
            f.write("- POST /api/auth/register\n")
            f.write("- POST /api/auth/login\n")
            f.write("- POST /api/auth/logout\n")
            f.write("- GET /api/auth/me\n")
            f.write("- POST /api/auth/refresh\n")
    except Exception as e:
        logger.error(f"Failed to write test credentials: {e}")

@app.on_event("shutdown")
async def shutdown_db_client():
    client.close()
