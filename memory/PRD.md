# Recruitment Analytics System - PRD

## Project Overview
Full-stack web application for recruitment analytics that dynamically ingests any dataset format, processes them, matches records, and displays both aggregated funnel analytics and detailed row-level data.

## User Personas
1. **Recruiters** - Upload candidate data and view analytics
2. **HR Managers** - Monitor recruitment funnel and track conversion rates
3. **Admin** - Manage system access

## Core Requirements (Static)
- JWT-based authentication (60 min sessions)
- Dynamic schema detection from uploaded files
- File upload (CSV/XLSX) with 10MB limit
- Data validation and normalization
- Candidate matching (email primary, phone fallback)
- Funnel visualization with dynamic status breakdown
- Detailed data tables with all fields
- Job role filtering (auto-detected)
- CSV export

## What's Been Implemented (April 7, 2026)

### Dynamic Schema System (REFACTORED)
- [x] No hardcoded column names or status values
- [x] Auto-detect email column (Email, Email ID, etc.)
- [x] Auto-detect phone column (Phone, Phone Number, Mobile, etc.)
- [x] Auto-detect status column (email_type, status, pipeline_status, etc.)
- [x] Auto-detect job role column (job_role, Job Title, position, etc.)
- [x] Auto-detect name column
- [x] Store ALL fields from uploaded files dynamically
- [x] Extract status values from actual data

### Authentication System
- [x] JWT auth with httpOnly cookies (60 min sessions)
- [x] Login/Register pages
- [x] Protected routes
- [x] Admin seeding on startup

### Data Upload
- [x] `/upload/naukri` - Dynamic upload with schema detection
- [x] `/upload/pipeline` - Dynamic upload with schema detection
- [x] Shows detected schema after upload (columns, email, phone, status)
- [x] Data normalization (email lowercase, phone numeric)
- [x] Duplicate detection via email/phone
- [x] Error reporting

### Data Processing
- [x] `/api/process-data` - Match candidates between datasets
- [x] Email/phone matching priority
- [x] Dynamic status classification

### Analytics Dashboard
- [x] **Summary Funnel Tab**: Total applies, Registered/Not Registered, Dynamic status breakdown
- [x] **Detailed Data Tab**: Full table with all columns from files
- [x] Data source selector (Processed, Naukri, Pipeline)
- [x] Registration filter
- [x] Status filter (dynamically populated)
- [x] Job role filter (if detected)
- [x] Search by name/email/phone
- [x] Pagination
- [x] CSV download
- [x] Reset data functionality
- [x] Schema info display

### Design
- [x] Swiss brutalist theme (light)
- [x] Syne + DM Sans typography
- [x] Sharp edges, 1px borders
- [x] Phosphor icons
- [x] Responsive layout

## API Endpoints
- POST `/api/auth/register`
- POST `/api/auth/login`
- POST `/api/auth/logout`
- GET `/api/auth/me`
- POST `/api/auth/refresh`
- POST `/api/upload/naukri` - Returns schema_info
- POST `/api/upload/pipeline` - Returns schema_info
- POST `/api/process-data`
- GET `/api/analytics?job_role=`
- GET `/api/data?source=&job_role=&status=&registration=&search=&page=&limit=`
- GET `/api/analytics/download?source=&job_role=&status=`
- GET `/api/schema`
- DELETE `/api/reset-data?source=`

## Database Collections
- `users` - User accounts
- `schema_metadata` - Detected schemas for each dataset type
- `naukri_applies_raw` - Raw Naukri data with ALL fields
- `pipeline_data_raw` - Raw Pipeline data with ALL fields
- `processed_candidates` - Matched/processed candidates
- `upload_history` - Upload logs

## Supported Sample Files
- **Naukri Applies**: XLSX with columns like Email ID, Phone Number, Name, Job Title, Pipeline Status, etc. (70+ columns supported)
- **Pipeline Data**: CSV with columns like email, phone, name, job_role, email_type (status), etc. (45+ columns supported)

## Prioritized Backlog

### P0 - Critical (Completed)
- [x] Dynamic schema detection
- [x] Authentication
- [x] File uploads with schema extraction
- [x] Data processing
- [x] Analytics dashboard (Summary + Detailed)

### P1 - Important (Future)
- [ ] Column mapping UI for ambiguous files
- [ ] Bulk delete/reset data
- [ ] Upload history view

### P2 - Nice to Have
- [ ] Role-based access (Admin/Recruiter)
- [ ] Advanced charts (bar, pie)
- [ ] Date range filtering

## Next Tasks
1. Add column mapping UI for edge cases
2. Implement upload history tracking page
3. Add more chart types to dashboard
