# Recruitment Analytics System - PRD

## Project Overview
Full-stack recruitment analytics system that ingests Naukri Applies and HR Internal Pipeline datasets, processes them with strict schema mapping, matches records using Email/Phone, and displays a funnel-based analytics dashboard with hierarchical drill-down panels.

## Architecture
- **Frontend**: React + Tailwind CSS + Phosphor Icons + Framer Motion
- **Backend**: FastAPI + Motor (async MongoDB)
- **Database**: MongoDB (3 collections: naukri_applies, pipeline_data, registered_candidates)
- **Auth**: JWT cookie-based (hardcoded admin/admin)

## Schema Mapping Layer

### Naukri Applies (NAUKRI_COLUMN_MAP)
Maps CSV display column names → normalized snake_case DB fields:
- "Email ID" → email
- "Phone Number" → phone
- "Job Title" → job_title
- "Date of application" → date_of_application
- "Name" → name
- "Gender" → gender
- "Date of Birth" → date_of_birth
- "Current Location" → current_location
- ... (65+ fields mapped)

### HR Internal Pipeline (PIPELINE_EXPECTED_COLUMNS)
Canonical column set (already snake_case):
- id → pipeline_id (to avoid MongoDB _id conflict)
- name, email, phone, age, gender, hr_team, job_role
- email_type, confirm_box, schedule_date, schedule_time
- otp_verified, otp_expired, result_status, result_mail
- ... (40 fields total)
- Handles duplicate columns in CSV (keeps first occurrence)

### Key Schema Corrections
- Pipeline field is `confirm_box` (NOT `confirm`)
- Pipeline field is `job_role` (NOT `job_title`)
- Pipeline `id` stored as `pipeline_id`
- Unmapped CSV columns stored with `_extra_` prefix (no data loss)

## Data Architecture (Relational Integrity)

### registered_candidates (DERIVED)
- INNER JOIN of naukri_applies + pipeline_data on (email OR phone)
- Contains ALL fields from BOTH datasets (merged)
- Naukri fields take precedence for shared field names (name, email, phone, gender)
- Rebuilt on every upload via `reprocess_matching()`

### Category Definitions (ALL from registered_candidates)
- **Registered**: count(registered_candidates)
- **Unregistered**: total_applies - registered (from naukri_applies where not matched)
- **Shortlisted**: registered WHERE email_type matches 'shortlist'
- **Rejected**: registered WHERE result_status matches 'reject'
- **Scheduled**: registered WHERE schedule_date AND schedule_time NOT NULL
- **Not Scheduled**: registered WHERE schedule_date AND schedule_time NULL
- **Attended**: registered WHERE otp_verified NOT NULL
- **Not Attended**: registered WHERE otp_verified NULL

### Integrity Constraints (Validated)
- registered + unregistered = total_applies
- scheduled + not_scheduled = registered
- attended + not_attended = registered

## API Endpoints
- POST `/api/login` — Login
- POST `/api/logout` — Logout
- GET `/api/auth/check` — Auth check
- POST `/api/upload/naukri` — Upload with NAUKRI_COLUMN_MAP mapping
- POST `/api/upload/pipeline` — Upload with PIPELINE_EXPECTED_COLUMNS + dedup
- GET `/api/dashboard-counts` — All funnel counts from registered_candidates
- GET `/api/data/{category}` — Drill-down data (8 categories)

## Code Architecture
```
/app/
├── backend/
│   ├── server.py (NAUKRI_COLUMN_MAP, PIPELINE_EXPECTED_COLUMNS, upload/analytics/data endpoints)
│   ├── tests/test_schema_refactor.py
│   └── .env
├── frontend/src/
│   ├── App.js
│   ├── context/AuthContext.js
│   ├── components/ProtectedRoute.js
│   └── pages/
│       ├── Login.js
│       └── Dashboard.js
├── test_data/
│   ├── naukri_test.csv (10 records, uses correct column names)
│   └── pipeline_test.csv (7 records, uses confirm_box/job_role)
```

## Testing Status (April 8, 2026)
- Backend: 20/20 tests passed (100%) — schema alignment, relational integrity, UPSERT
- Frontend: All features verified (100%) — confirm_box shown correctly
- Data alignment: Diana (Pune), Eve (Hyderabad) verified correct
- No data loss: 0 unmapped columns for both datasets

## Prioritized Backlog

### P1
- [ ] CSV export/download from data table modals
- [ ] Session persistence across hard page refreshes
- [ ] Search within data table modals

### P2
- [ ] Upload history view
- [ ] Progress bar during processing
- [ ] Role-based access (Admin/Recruiter)
- [ ] Advanced charts/visualizations
