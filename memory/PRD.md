# Recruitment Analytics System - PRD

## Project Overview
Full-stack web application for recruitment analytics with a **sequential, state-driven workflow** that ingests Naukri Applies and Pipeline Data, processes them together, and displays combined analytics.

## Workflow Flow (CRITICAL)
```
Login → Step 1: Upload Naukri → Step 2: Upload Pipeline → Auto-Process → Dashboard
```
- Dashboard only accessible after BOTH uploads complete and processing finishes
- Route guards enforce sequential access
- State persisted in database (survives page refresh)

## User Personas
1. **Recruiters** - Upload candidate data and view analytics
2. **HR Managers** - Monitor recruitment funnel and track conversion rates
3. **Admin** - Manage system access

## Core Requirements (Static)
- JWT-based authentication (60 min sessions)
- Sequential workflow (Naukri → Pipeline → Process → Dashboard)
- Dynamic schema detection from uploaded files
- File upload (CSV/XLSX) with 10MB limit
- Data validation and normalization
- Candidate matching (email primary, phone fallback)
- Funnel visualization with dynamic status breakdown
- Detailed data tables with all fields
- CSV export

## What's Been Implemented (April 7, 2026)

### Sequential Workflow System (NEW)
- [x] Workflow state persisted in MongoDB per user
- [x] `/upload/naukri` - Entry point (always accessible)
- [x] `/upload/pipeline` - Requires Naukri upload complete
- [x] `/dashboard` - Requires processing complete
- [x] Route guards enforce access sequence
- [x] Progress indicators in UI (Step 1 → Step 2 → Step 3)
- [x] Green checkmarks show completed steps
- [x] "Continue to Step 2" button after Naukri upload
- [x] Auto-processing after Pipeline upload
- [x] "New Analysis" button to reset and start fresh

### Dynamic Schema System
- [x] Auto-detect email, phone, status, job role columns
- [x] Store ALL fields from uploaded files
- [x] Extract status values from actual data

### Authentication System
- [x] JWT auth with httpOnly cookies
- [x] Login/Register pages
- [x] Protected routes
- [x] Admin seeding on startup

### Data Upload
- [x] Step 1: Upload Naukri with schema detection
- [x] Step 2: Upload Pipeline with schema detection
- [x] Shows detected schema after upload
- [x] Data normalization
- [x] Duplicate detection
- [x] Error reporting

### Data Processing
- [x] `POST /api/process-combined` - Only after BOTH uploads
- [x] Candidate matching (email/phone)
- [x] Dynamic status classification

### Analytics Dashboard
- [x] "Analysis Complete" banner
- [x] Summary Funnel tab with counts
- [x] Detailed Data tab with tables
- [x] Registration filter
- [x] Status filter (dynamically populated)
- [x] Job role filter (if detected)
- [x] Search, pagination, CSV download

## API Endpoints
### Auth
- POST `/api/auth/register`
- POST `/api/auth/login`
- POST `/api/auth/logout`
- GET `/api/auth/me`
- POST `/api/auth/refresh`

### Workflow
- GET `/api/workflow/state` - Get current workflow state
- POST `/api/workflow/reset` - Reset and start fresh

### Upload
- POST `/api/upload/naukri` - Step 1 (updates workflow state)
- POST `/api/upload/pipeline` - Step 2 (requires Step 1 complete)

### Processing
- POST `/api/process-combined` - Requires both uploads

### Analytics
- GET `/api/analytics?job_role=`
- GET `/api/data?source=&job_role=&status=&registration=&search=&page=&limit=`
- GET `/api/analytics/download?source=&job_role=&status=`

## Database Collections
- `users` - User accounts
- `workflow_state` - Per-user workflow progress
- `schema_metadata` - Detected schemas
- `naukri_applies_raw` - Raw Naukri data (all fields)
- `pipeline_data_raw` - Raw Pipeline data (all fields)
- `processed_candidates` - Matched/processed candidates
- `upload_history` - Upload logs

## Workflow State Schema
```json
{
  "user_id": "...",
  "naukri_uploaded": true/false,
  "pipeline_uploaded": true/false,
  "processing_complete": true/false,
  "current_step": "naukri|pipeline|processing|dashboard"
}
```

## Prioritized Backlog

### P0 - Critical (Completed)
- [x] Sequential workflow enforcement
- [x] Route guards
- [x] Dynamic schema detection
- [x] Authentication
- [x] File uploads
- [x] Combined processing
- [x] Analytics dashboard

### P1 - Important (Future)
- [ ] Bulk data re-upload without full reset
- [ ] Upload history view
- [ ] Progress bar during processing

### P2 - Nice to Have
- [ ] Role-based access (Admin/Recruiter)
- [ ] Advanced charts
- [ ] Email notifications when processing complete

## Next Tasks
1. Add processing progress indicator
2. Add upload history tracking
3. Add more chart types to dashboard
