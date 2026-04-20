# Recruitment Analytics - Product Requirements Document

## Original Problem Statement
Build a comprehensive Recruitment Analytics platform that handles bulk file uploads (Naukri Applies, HR Pipeline, Score Sheet, College Rank List), normalizes phone numbers, computes derived statuses hierarchically, classifies colleges into NIRF/Non-NIRF categories, and provides analytics dashboards with filtering and pagination.

## Core Architecture
- **Frontend**: React + Tailwind CSS + Shadcn UI + Phosphor Icons
- **Backend**: FastAPI + Motor (async MongoDB driver)
- **Database**: MongoDB
- **Auth**: Hardcoded admin/admin with JWT cookie-based auth

## Implemented Features

### Phase 1: Core Platform (Completed)
- Login/logout with JWT cookie auth
- Upload endpoints for Naukri, Pipeline, Score Sheet, College Rank datasets
- Email/phone normalization (10-digit phone extraction)
- Data matching: Naukri + Pipeline → registered_candidates (inner join on email/phone)
- Derived status hierarchy: Registered → Shortlisted → Scheduled → Attended
- Dashboard with upload buttons and navigation

### Phase 2: Analytics Views (Completed)
- Summary Statistics, View Applicants, View Attended — with filters + pagination

### Phase 3: Enhancements (Completed)
- Date filter fix, pagination with configurable page size

### Phase 4: Job Role Normalization (Completed - Apr 17, 2026)
- Data-driven keyword mapping from Naukri uploads
- Checkbox-based UI at /jobs-keywords
- Exact match normalization on all query endpoints

### Phase 5: Dynamic Multi-Criteria College Matching (Completed - Apr 17, 2026)
- Base name + city/state matching with confidence levels (HIGH/MEDIUM/LOW)
- No hardcoded college names

### Phase 6: DB-Driven Bulk Upload Queue (Completed - Apr 20, 2026)
- **Replaced** in-memory queue with persistent `bulk_upload_queue` MongoDB collection
- **Background worker**: `_bg_queue_worker()` runs as asyncio task, polls every 3s, processes ONE file at a time
- **Fault-tolerant**: On startup, stuck "processing" records reset to "pending"
- **Independent of UI**: Processing continues even if browser/app is closed
- **File storage**: `/app/uploads/{type}/` → `/app/processed_files/{type}/` on success
- **Status API**: Returns pending, processed (with results), and failed (with errors) per type
- **Frontend**: Refresh button (no polling), clickable processed_files folder, failed files section

## DB Schema
- `naukri_applies`, `pipeline_data`, `registered_candidates`, `score_sheet`, `college_rank_list`
- `job_keyword_mapping`: {job_role, keywords[], created_at}
- `job_titles_master`: {raw_job_title, normalized_job_title, is_mapped}
- `bulk_upload_queue`: {file_name, file_path, file_type, status, created_at, updated_at, error_message, result}

## Key API Endpoints
- Auth: POST /api/login, POST /api/logout, GET /api/auth/check
- Upload: POST /api/upload/{naukri,pipeline,scoresheet,college-rank}
- Bulk: POST /api/bulk-upload/{type}, GET /api/bulk-upload/status, DELETE /api/bulk-upload/{type}/{id}
- Analytics: GET /api/summary, /api/job-roles, /api/applicants, /api/attended
- Keywords: GET/POST/PUT/DELETE /api/job-keyword-mappings, GET /api/job-titles/unmatched

## Prioritized Backlog
### P1
- CSV export/download from summary and applicant tables
- Session persistence across page refreshes

### P2
- Upload History view
- Advanced chart visualizations on dashboard
- Role-based access control (Admin vs Recruiter)
