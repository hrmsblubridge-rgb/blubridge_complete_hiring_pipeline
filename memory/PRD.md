# Recruitment Analytics System - PRD

## Project Overview
Full-stack recruitment analytics system. Ingests Naukri Applies and HR Pipeline datasets independently, matches records via email/phone JOIN, provides role-wise funnel analytics and individual applicant drill-downs.

## Architecture
- **Frontend**: React + Tailwind CSS + Phosphor Icons
- **Backend**: FastAPI + Motor (async MongoDB)
- **Database**: MongoDB (naukri_applies, pipeline_data, registered_candidates)
- **Auth**: JWT cookie-based (admin/admin)

## Data Flow (Verified E2E)
```
Upload File → Parse → Normalize Fields → UPSERT into DB → Verify DB → Run JOIN → API Response → Render in UI
```

## Key Design Decisions
1. **Role API uses query param** (`/api/role?jobRole=`) — no 404s from special chars
2. **Uploads are independent** — each works alone; matching runs with available data
3. **DB-driven state** — `/api/status` returns live counts; no frontend state dependency
4. **Registered = INNER JOIN** of naukri + pipeline on email OR phone
5. **Schema mapping** — NAUKRI_COLUMN_MAP (72 fields), PIPELINE_EXPECTED_COLUMNS (40 fields)
6. **Shortlisted uses `result_status`** (not `email_type`) — per user's explicit data model

## Status Derivation Logic (Priority order)
1. **Rejected** — `result_status` matches "Reject" or "Rejected"
2. **Attended** — `otp_verified` is not NULL/empty
3. **Interview Scheduled** — `schedule_date` AND `schedule_time` not NULL/empty
4. **Shortlisted** — `result_status` matches "shortlist"
5. **Registered** — default (exists in registered_candidates)

## API Endpoints
- POST /api/login, /api/logout, GET /api/auth/check
- POST /api/upload/naukri, /api/upload/pipeline
- GET /api/status
- GET /api/dashboard-counts
- GET /api/summary?startDate=&endDate=&search=
- GET /api/job-roles
- GET /api/role?jobRole=&startDate=&endDate=&page=&limit= (returns individual applicants with derived status)
- GET /api/data/{category} (unregistered, registered, shortlisted, rejected, scheduled, not-scheduled, attended, not-attended)

## Pages
- /dashboard — Upload buttons + DB status + navigation
- /summary — Role-wise funnel table with date/search filters
- /roles — Clickable job role grid with applicant counts
- /roles/:jobRole — Detailed applicant table with status badges, date filters, pagination

## Completed Work
- [x] Stateful DB-Driven Dashboard Refactor
- [x] Relational Integrity Refactor using `registered_candidates` JOIN collection
- [x] Schema Alignment Refactor with precise Header Mapping Dictionaries
- [x] Frontend Restructure: /summary, /roles, /roles/:jobRole pages
- [x] Role API 404 Fix (query params)
- [x] Independent Upload Flow
- [x] Data Flow Stabilization & E2E Validation
- [x] Role Drilldown: Detailed Applicant Table with derived status (Apr 9, 2026)
- [x] Shortlisted field correction: result_status instead of email_type (Apr 9, 2026)

## Backlog
### P1
- [ ] CSV export from summary and role drill-down tables
- [ ] Session persistence across page refreshes

### P2
- [ ] Upload history view
- [ ] Advanced chart visualizations on dashboard
- [ ] Role-based access control (Admin vs Recruiter)
