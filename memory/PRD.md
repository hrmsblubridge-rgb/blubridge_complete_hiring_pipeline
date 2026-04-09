# Recruitment Analytics System - PRD

## Project Overview
Full-stack recruitment analytics system. Ingests Naukri Applies and HR Pipeline datasets independently, matches records via email/phone JOIN, provides role-wise funnel analytics and individual applicant drill-downs.

## Architecture
- **Frontend**: React + Tailwind CSS + Phosphor Icons
- **Backend**: FastAPI + Motor (async MongoDB)
- **Database**: MongoDB (naukri_applies, pipeline_data, registered_candidates)
- **Auth**: JWT cookie-based (admin/admin)

## Data Flow
```
Upload File → Parse CSV → Apply Column Mapping → Normalize email/phone → UPSERT into DB → Run JOIN matching → Rebuild registered_candidates → API serves from DB → UI renders
```

## Key Design Decisions
1. **Role API uses query param** (`/api/role?jobRole=`) — no 404s from special chars
2. **Uploads are independent** — each works alone; matching runs with available data
3. **DB-driven state** — `/api/status` returns live counts
4. **Registered = INNER JOIN** of naukri + pipeline on email OR phone (either sufficient)
5. **Schema mapping** — NAUKRI_COLUMN_MAP (72 fields), PIPELINE_EXPECTED_COLUMNS (40 fields)
6. **Robust normalization** — Email: lowercase+trim. Phone: float→int, strip +91/91/leading zeros, digits only
7. **Re-normalization on every match cycle** — Both collections re-normalized before JOIN

## STRICT STATUS HIERARCHY (email_type field)
```
Registered (exists in both datasets via email OR phone match)
├── Shortlisted (email_type IN 'shortlist', 'shortlisted')
│   ├── Interview Scheduled (has schedule_date AND schedule_time)
│   │   ├── Attended (otp_verified IS NOT NULL)
│   │   └── Not Attended (otp_verified IS NULL)
│   └── Interview Not Scheduled (no schedule_date/time)
├── Rejected (email_type IN 'reject', 'rejected')
└── (Other Registered — email_type is neither shortlist nor reject)
```

### Hierarchy Constraints
- ALL statuses are subsets of Registered
- Scheduled is a STRICT SUBSET of Shortlisted
- Attended is a STRICT SUBSET of Scheduled
- shortlisted = scheduled + not_scheduled
- scheduled = attended + not_attended

## Normalization Rules
### Email: `LOWERCASE + TRIM`
### Phone: `float→int, digits only, strip +91/91, strip leading zeros`

## Matching Logic
```
ON (LOWER(TRIM(NA.email)) = LOWER(TRIM(PD.email)) OR CLEAN_PHONE(NA.phone) = CLEAN_PHONE(PD.phone))
```

## API Endpoints
- POST /api/login, /api/logout, GET /api/auth/check
- POST /api/upload/naukri, /api/upload/pipeline
- GET /api/status
- GET /api/dashboard-counts (strict hierarchy counts)
- GET /api/summary?startDate=&endDate=&search= (role-wise funnel with hierarchy)
- GET /api/job-roles
- GET /api/role?jobRole=&page=&limit= (individual applicants with derived status)
- POST /api/reprocess (re-normalize + rebuild matching)
- GET /api/debug/matching (per-record match details)
- GET /api/data/{category} (unregistered, registered, shortlisted, rejected, scheduled, not-scheduled, attended, not-attended)

## Pages
- /dashboard — Upload buttons + DB status + navigation
- /summary — Role-wise funnel table with date/search filters
- /roles — Clickable job role grid with registered counts
- /roles/:jobRole — Detailed applicant table with status badges, date filters, pagination

## Completed Work
- [x] Stateful DB-Driven Dashboard Refactor
- [x] Relational Integrity (registered_candidates JOIN collection)
- [x] Schema Alignment (72 Naukri + 40 Pipeline column mappings)
- [x] Frontend Restructure: /summary, /roles, /roles/:jobRole pages
- [x] Role API 404 Fix (query params)
- [x] Independent Upload Flow
- [x] Role Drilldown: Applicant Table with derived status (Apr 9)
- [x] Phone normalization fix: float→int, leading zeros (Apr 9)
- [x] Re-normalization during matching (Apr 9)
- [x] Debug/Reprocess endpoints (Apr 9)
- [x] **STRICT HIERARCHY**: Shortlisted/Rejected via email_type, Scheduled⊂Shortlisted, Attended⊂Scheduled (Apr 9)

## Backlog
### P1
- [ ] CSV export from summary and role drill-down tables
- [ ] Session persistence across page refreshes

### P2
- [ ] Upload history view
- [ ] Advanced chart visualizations on dashboard
- [ ] Role-based access control (Admin vs Recruiter)
