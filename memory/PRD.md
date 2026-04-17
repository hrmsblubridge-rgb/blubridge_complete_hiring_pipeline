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
- **Summary Statistics**: Role-wise funnel breakdown (Naukri → Registered → Shortlisted → Scheduled → Attended) split by NIRF/Non-NIRF
- **View Applicants (Roles.js)**: Global registered table with Job Role, Date Type, Search, College Status filters + pagination
- **View Attended (AttendedRoles.js)**: Attended applicants with score columns, round filter, pagination

### Phase 3: Enhancements (Completed)
- Bulk upload system with sequential background queue (FIFO processing)
- College Rank List upload + NIRF classification (NIRF/Non-NIRF based on rank ≤ 100)
- College field derived from Naukri UG/PG aligned with NIRF logic
- Date filter fix on schedule_date
- Pagination with configurable page size (10-500)

### Phase 4: Job Role Normalization (Completed - Apr 17, 2026)
- **job_keyword_mapping collection**: Stores canonical job roles with associated keywords
- **CRUD API**: GET/POST/PUT/DELETE `/api/job-keyword-mappings`
- **Normalization logic**: Lowercase, trim, strip punctuation from job_title, then substring match against keywords. First match wins, fallback to raw title.
- **Applied everywhere**: `/api/job-roles`, `/api/summary`, `/api/applicants`, `/api/attended`, `/api/attended-roles` all use `_resolve_normalized_job_role()`
- **Jobs & Keywords UI**: New page at `/jobs-keywords` with Add/Edit/Delete modal for managing keyword-to-role mappings with keyword pills
- **Table headers always visible**: Empty state fix applied to Summary, Roles, and AttendedRoles pages - tables always show headers with "No records found" row when empty

## DB Schema
- `users`: {email, password, role}
- `naukri_applies`: {email, phone, job_title, date_of_application, name, ug_university, pg_university, ...}
- `pipeline_data`: {email, phone, job_role, email_type, schedule_date, schedule_time, otp_verified, result_status, ...}
- `registered_candidates`: Merged naukri + pipeline data (rebuilt on each upload)
- `score_sheet`: {email, phone, score, round_name}
- `college_rank_list`: {rank, college_name, short_name, city, state}
- `job_keyword_mapping`: {job_role, keywords[], created_at}

## Key API Endpoints
- `POST /api/login` / `POST /api/logout` / `GET /api/auth/check`
- `POST /api/upload/naukri` / `POST /api/upload/pipeline` / `POST /api/upload/scoresheet` / `POST /api/upload/college-rank`
- `POST /api/bulk-upload/{type}` / `GET /api/bulk-upload/status`
- `GET /api/summary` / `GET /api/job-roles` / `GET /api/applicants` / `GET /api/attended`
- `GET/POST/PUT/DELETE /api/job-keyword-mappings`

## Prioritized Backlog
### P1
- CSV export/download from summary and applicant tables
- Session persistence across page refreshes

### P2
- Upload History view
- Advanced chart visualizations on dashboard
- Role-based access control (Admin vs Recruiter)
