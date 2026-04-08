# Recruitment Analytics System - PRD

## Project Overview
Full-stack web application for recruitment analytics that ingests Naukri Applies and Pipeline datasets, processes them, matches records using Email/Phone composite key, and displays a funnel-based analytics dashboard with hierarchical drill-down panels.

## Architecture
- **Frontend**: React + Tailwind CSS + Phosphor Icons + Framer Motion
- **Backend**: FastAPI + Motor (async MongoDB)
- **Database**: MongoDB
- **Auth**: JWT cookie-based (hardcoded admin/admin)

## Workflow
```
Login -> Dashboard (Upload Datasets via modal -> View Analytics -> Drill-down into categories)
```

## Core Data Architecture (Relational Integrity)

### Collections
- `naukri_applies` - Raw Naukri applicant data, with `_is_registered` flag
- `pipeline_data` - Raw HR pipeline data
- `registered_candidates` - **DERIVED** collection: INNER JOIN of naukri_applies + pipeline_data on (email OR phone)

### Matching Logic
After each upload, `reprocess_matching()` rebuilds `registered_candidates`:
1. For each naukri record, match against pipeline by email OR phone
2. Matched records are merged (naukri + pipeline fields) into `registered_candidates`
3. Unmatched naukri records are flagged `_is_registered: false`

### Category Definitions (ALL from registered_candidates)
- **Total Applies**: count(naukri_applies)
- **Registered**: count(registered_candidates) — the JOIN result
- **Unregistered**: total_applies - registered
- **Shortlisted**: registered_candidates WHERE email_type matches 'shortlist'
- **Rejected**: registered_candidates WHERE result_status matches 'reject'
- **Scheduled**: registered_candidates WHERE schedule_date IS NOT NULL AND schedule_time IS NOT NULL
- **Not Scheduled**: registered_candidates WHERE schedule_date IS NULL AND schedule_time IS NULL
- **Attended**: registered_candidates WHERE otp_verified IS NOT NULL
- **Not Attended**: registered_candidates WHERE otp_verified IS NULL

### Integrity Constraints
- registered + unregistered = total_applies
- scheduled + not_scheduled = registered (partition)
- attended + not_attended = registered (partition)
- All sub-categories <= registered (strict subsets)

## API Endpoints
- POST `/api/login` - Login
- POST `/api/logout` - Logout
- GET `/api/auth/check` - Check auth
- POST `/api/upload/naukri` - Upload Naukri CSV/XLSX
- POST `/api/upload/pipeline` - Upload Pipeline CSV/XLSX
- GET `/api/dashboard-counts` - Funnel counts (all from registered_candidates)
- GET `/api/data/unregistered` - From naukri_applies where not registered
- GET `/api/data/registered` - From registered_candidates
- GET `/api/data/shortlisted` - From registered_candidates
- GET `/api/data/rejected` - From registered_candidates
- GET `/api/data/scheduled` - From registered_candidates
- GET `/api/data/not-scheduled` - From registered_candidates
- GET `/api/data/attended` - From registered_candidates
- GET `/api/data/not-attended` - From registered_candidates

## Code Architecture
```
/app/
├── backend/
│   ├── .env
│   ├── requirements.txt
│   ├── server.py
│   └── tests/
│       ├── test_recruitment_api.py
│       └── test_relational_integrity.py
├── frontend/
│   └── src/
│       ├── App.js
│       ├── context/AuthContext.js
│       ├── components/ProtectedRoute.js
│       └── pages/
│           ├── Login.js
│           └── Dashboard.js
├── test_data/
│   ├── naukri_test.csv
│   └── pipeline_test.csv
```

## Testing Status (April 8, 2026)
- Backend: 34/34 tests passed (100%) — relational integrity validated
- Frontend: All features verified (100%)
- UPSERT: Verified (re-upload updates, no duplicates)
- Partition checks: scheduled+not_scheduled=registered, attended+not_attended=registered

## Prioritized Backlog

### P1 - Important
- [ ] CSV export/download from data table modals
- [ ] Session persistence across hard page refreshes
- [ ] Search within data table modals

### P2 - Nice to Have
- [ ] Upload history view
- [ ] Progress bar during processing
- [ ] Role-based access (Admin/Recruiter)
- [ ] Advanced charts/visualizations
