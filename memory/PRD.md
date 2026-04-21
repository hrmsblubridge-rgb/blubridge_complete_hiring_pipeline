# Recruitment Analytics - Product Requirements Document

## Original Problem Statement
Build a comprehensive Recruitment Analytics platform (BluBridge Hiring Pipeline) that handles bulk file uploads, normalizes data, computes derived statuses, classifies colleges, and provides analytics dashboards.

## Core Architecture
- **Frontend**: React + Tailwind CSS + Shadcn UI + Phosphor Icons
- **Backend**: FastAPI + Motor (async MongoDB driver)
- **Database**: MongoDB
- **Auth**: Hardcoded admin/admin with JWT cookie-based auth

## Implemented Features

### Phase 1-3: Core Platform, Analytics, Enhancements (Completed)
- Login/logout, Upload endpoints (Naukri, Pipeline, Score Sheet, College Rank)
- Email/phone normalization, Data matching, Derived status hierarchy
- Summary Statistics, View Applicants, View Attended
- Pagination, Date filters, Bulk upload with DB-driven queue

### Phase 4: Job Role Normalization (Completed - Apr 17)
- Data-driven keyword mapping from Naukri uploads, checkbox UI at /jobs-keywords

### Phase 5: Dynamic Multi-Criteria College Matching (Completed - Apr 17)
- Base name + city/state matching with confidence levels (HIGH/MEDIUM/LOW)

### Phase 6: DB-Driven Bulk Upload Queue (Completed - Apr 20)
- Persistent background worker, fault-tolerant, independent of UI

### Phase 7: BluBridge Extension Modules (Completed - Apr 21)
Based on the BluBridge Hiring Pipeline PDF design plan:

- **Home Page** (`/home`): New landing hub with 6 navigation buttons to all modules. Login now redirects here.
- **Create Job Roles** (`/manage-job-roles`): CRUD for canonical job roles displayed as cards with Edit/Delete
- **Hiring Forms** (`/hiring-forms`):
  - Form Types: CRUD (card UI with Edit/Delete)
  - Hiring Forms: CRUD with Name, Type dropdown, Job Role, Conditions section
  - Conditions: Age limit, Graduation Year limit, Location limit (multi-add), Location Change (Yes/No/NA), Attend in Person (Yes/No/NA), College limit (NIRF/Non NIRF/Both)
- **Interview Schedule Reports** (`/interview-reports`): Date range, Job Role, Attendance, College filters. Job role tabs with counts. Attendance/Premium summaries. Table with NAME/EMAIL/DATE/TIME/JOB ROLE/COLLEGE TYPE/ATTENDANCE. CSV Export.
- **Update Applicants Scores** (`/update-scores`): Date range filter, attended applicants table with per-row Update button. Floating form with Status (On hold/Rejected/Selected) + Round scores (dynamic add). Rounds management CRUD.
- **Create Job Openings** (`/job-openings`): CRUD with title, job role, description

**Architecture**: All new code in separate `bb_modules.py` backend + separate frontend pages. Zero changes to existing server.py logic. Dependency injection via `init_bb()`.

## DB Collections
### Existing (UNTOUCHED)
- `naukri_applies`, `pipeline_data`, `registered_candidates`, `score_sheet`, `college_rank_list`
- `job_keyword_mapping`, `job_titles_master`, `bulk_upload_queue`

### New (bb_ prefix)
- `bb_job_roles`: {name, created_at}
- `bb_form_types`: {name, created_at}
- `bb_hiring_forms`: {name, form_type_id, form_type_name, job_role, conditions{...}, created_at}
- `bb_rounds`: {name, created_at}
- `bb_job_openings`: {title, job_role, description, created_at}
- `bb_applicant_updates`: {email, status, scores[{round_name, score}], updated_at}

## API Endpoints
### Existing (UNTOUCHED)
- /api/login, /api/logout, /api/auth/check
- /api/upload/*, /api/bulk-upload/*
- /api/summary, /api/job-roles, /api/applicants, /api/attended
- /api/job-keyword-mappings, /api/job-titles/unmatched

### New (bb prefix)
- CRUD: /api/bb/job-roles, /api/bb/form-types, /api/bb/hiring-forms, /api/bb/rounds, /api/bb/job-openings
- Reports: /api/bb/interview-reports (GET with filters)
- Scores: /api/bb/attended-for-scores (GET), /api/bb/applicant-score/{email} (PUT)

## Prioritized Backlog
### P1
- CSV export from existing summary/applicant tables
- Registration Form public submission (applicant-facing)
- Shortlisting engine (apply form conditions to applicants)

### P2
- Upload History view
- Advanced chart visualizations
- Role-based access control (Admin vs Recruiter)
