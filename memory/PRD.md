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
Login → Dashboard (Upload Datasets via modal → View Analytics → Drill-down into categories)
```
- Independent file uploads (Naukri and Pipeline can be uploaded separately)
- Records are UPSERTED using (email OR phone) as composite unique identity
- After each upload, automatic re-matching runs to update registration status
- All counts and data are DB-driven (no frontend state dependency)

## Core Features (Implemented)

### Authentication
- [x] JWT cookie-based auth (httpOnly, samesite=lax)
- [x] Login/Logout endpoints
- [x] Auth check endpoint
- [x] Protected routes

### Data Upload (Modal-based)
- [x] Upload Naukri CSV/XLSX via modal
- [x] Upload Pipeline CSV/XLSX via modal
- [x] Auto-detect email, phone, and other columns
- [x] UPSERT logic (email OR phone matching - no duplicates)
- [x] Auto re-matching after each upload
- [x] Error reporting (first 10 errors)
- [x] 10MB file size limit

### Analytics Dashboard
- [x] Summary cards (Total Applies, Registered, Unregistered)
- [x] Hierarchical drill-down panels:
  - Unregistered Applicants
  - Registered Applicants
    - Shortlisted (email_type contains 'shortlist')
      - Interview Scheduled (schedule_date not null)
        - Attended (otp_verified not null)
        - Not Attended (has schedule, no otp_verified)
      - Interview Not Scheduled (shortlisted but no schedule_date)
    - Rejected (result_status matches 'reject')
- [x] Floating modal windows with scrollable data tables
- [x] Category-specific column visibility
- [x] Pagination (50 records per page)

### Category-Specific Field Mappings
- **Unregistered**: name, email, phone, job_title, date_of_application, gender, date_of_birth
- **Registered**: name, email, phone, job_title, date_of_application, gender, date_of_birth
- **Shortlisted**: name, email, phone, job_title, date_of_application, gender, location, email_type
- **Rejected**: name, email, phone, job_title, date_of_application, gender, date_of_birth, location, loca_change, attend_inperson, email_type, confirm
- **Scheduled**: name, email, phone, job_title, date_of_application, gender, schedule_date, schedule_time, reschedule_count
- **Not Scheduled**: name, email, phone, job_title, date_of_application, gender, date_of_birth, location, loca_change, attend_inperson, email_type, confirm
- **Attended**: name, email, phone, job_title, date_of_application, gender, date_of_birth, schedule_date, schedule_time, reschedule_count, otp_verified, result_mail, result_update, result_status
- **Not Attended**: name, email, phone, job_title, date_of_application, gender, date_of_birth, schedule_date, schedule_time, reschedule_count, otp_verified, otp_expired

## API Endpoints
- POST `/api/login` - Login
- POST `/api/logout` - Logout
- GET `/api/auth/check` - Check auth status
- POST `/api/upload/naukri` - Upload Naukri data
- POST `/api/upload/pipeline` - Upload Pipeline data
- GET `/api/dashboard-counts` - Get all funnel counts
- GET `/api/data/unregistered` - Drill-down data
- GET `/api/data/registered` - Drill-down data
- GET `/api/data/shortlisted` - Drill-down data
- GET `/api/data/rejected` - Drill-down data
- GET `/api/data/scheduled` - Drill-down data
- GET `/api/data/not-scheduled` - Drill-down data
- GET `/api/data/attended` - Drill-down data
- GET `/api/data/not-attended` - Drill-down data

## Database Collections
- `naukri_applies` - Naukri applicant data with _is_registered flag
- `pipeline_data` - Pipeline/HR internal data

## Code Architecture
```
/app/
├── backend/
│   ├── .env
│   ├── requirements.txt
│   ├── server.py
│   └── tests/
│       └── test_recruitment_api.py
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
- Backend: 23/23 tests passed (100%)
- Frontend: All features verified (100%)
- UPSERT logic: Verified (re-upload updates, no duplicates)
- Auth: Cookie-based JWT working correctly

## Prioritized Backlog

### P1 - Important
- [ ] Session persistence verification across hard page refreshes
- [ ] CSV export/download from data table modals
- [ ] Bulk data re-upload without full reset

### P2 - Nice to Have
- [ ] Upload history view
- [ ] Progress bar during file processing
- [ ] Role-based access (Admin/Recruiter)
- [ ] Advanced charts/visualizations
- [ ] Search within data table modals
- [ ] Email notifications
