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
- **Summary Statistics**: Role-wise funnel breakdown split by NIRF/Non-NIRF
- **View Applicants (Roles.js)**: Global registered table with filters + pagination
- **View Attended (AttendedRoles.js)**: Attended applicants with score columns, round filter, pagination

### Phase 3: Enhancements (Completed)
- Bulk upload system with sequential background queue (FIFO)
- College Rank List upload + NIRF classification
- Date filter fix on schedule_date
- Pagination with configurable page size (10-500)

### Phase 4: Job Role Normalization (Completed - Apr 17, 2026)
- `job_keyword_mapping` collection with CRUD endpoints
- Applied to all query endpoints (summary, applicants, attended, job-roles)
- Jobs & Keywords UI page at `/jobs-keywords`
- Table headers always visible (empty state fix)

### Phase 5: Dynamic Multi-Criteria College Matching (Completed - Apr 17, 2026)
- Structured multi-criteria matching: base name + city/state
- Confidence levels: HIGH (base+location), MEDIUM (single base), LOW (ambiguous)
- No hardcoded college names

### Phase 6: Data-Driven Keyword Mapping (Completed - Apr 17, 2026)
- **job_titles_master collection**: Auto-populated from Naukri uploads with distinct job titles
- **_sync_job_titles_master()**: Extracts and deduplicates titles on each Naukri upload
- **GET /api/job-titles/unmatched**: Returns unmapped job titles (is_mapped=false)
- **Checkbox-based UI**: Replaced manual keyword typing with checkbox selection from actual data
- **is_mapped tracking**: Keywords marked as mapped when assigned to a canonical role
- **Release on delete**: Keywords return to unmatched pool when mapping is deleted
- **Exact match normalization**: Changed from substring to exact match on normalized job titles
- **Duplicate prevention**: A keyword maps to only ONE canonical role

## DB Schema
- `users`: {email, password, role}
- `naukri_applies`: {email, phone, job_title, date_of_application, name, ug_university, pg_university, ...}
- `pipeline_data`: {email, phone, job_role, email_type, schedule_date, schedule_time, otp_verified, result_status, ...}
- `registered_candidates`: Merged naukri + pipeline data (rebuilt on each upload)
- `score_sheet`: {email, phone, score, round_name}
- `college_rank_list`: {rank, college_name, short_name, city, state}
- `job_keyword_mapping`: {job_role, keywords[], created_at}
- `job_titles_master`: {raw_job_title, normalized_job_title, is_mapped}

## Key API Endpoints
- `POST /api/login` / `POST /api/logout` / `GET /api/auth/check`
- `POST /api/upload/naukri` / `POST /api/upload/pipeline` / `POST /api/upload/scoresheet` / `POST /api/upload/college-rank`
- `POST /api/bulk-upload/{type}` / `GET /api/bulk-upload/status`
- `GET /api/summary` / `GET /api/job-roles` / `GET /api/applicants` / `GET /api/attended`
- `GET/POST/PUT/DELETE /api/job-keyword-mappings`
- `GET /api/job-titles/unmatched`

## Prioritized Backlog
### P1
- CSV export/download from summary and applicant tables
- Session persistence across page refreshes

### P2
- Upload History view
- Advanced chart visualizations on dashboard
- Role-based access control (Admin vs Recruiter)
