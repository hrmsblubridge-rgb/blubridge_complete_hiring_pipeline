# Recruitment Analytics System - PRD

## Project Overview
Full-stack recruitment analytics system. Ingests Naukri Applies and HR Pipeline datasets (CSV or XLSX), matches records via email/phone JOIN, provides role-wise funnel analytics and individual applicant drill-downs.

## Architecture
- **Frontend**: React + Tailwind CSS + Phosphor Icons
- **Backend**: FastAPI + Motor (async MongoDB)
- **Database**: MongoDB (naukri_applies, pipeline_data, registered_candidates)
- **Auth**: JWT cookie-based (admin/admin)

## Data Flow
```
Upload File (CSV/XLSX) → Parse → Apply Column Mapping → Normalize email/phone → clean_value (handle datetime.time, Timestamp) → UPSERT into DB → Re-normalize → Run JOIN matching → Rebuild registered_candidates → API → UI
```

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

## Normalization Rules
- Email: LOWERCASE + TRIM
- Phone: float→int, digits only, strip +91/91, strip leading zeros

## Matching Logic
```
ON (LOWER(TRIM(naukri.email)) = LOWER(TRIM(pipeline.email)) OR CLEAN_PHONE(naukri.phone) = CLEAN_PHONE(pipeline.phone))
```

## API Endpoints
- POST /api/login, /api/logout, GET /api/auth/check
- POST /api/upload/naukri, /api/upload/pipeline (CSV + XLSX)
- GET /api/status, /api/dashboard-counts, /api/summary, /api/job-roles
- GET /api/role?jobRole= (individual applicants with derived status)
- POST /api/reprocess, GET /api/debug/matching
- GET /api/data/{category}

## Completed Work
- [x] Core upload, matching, and analytics pipeline
- [x] Strict Status Hierarchy (email_type based)
- [x] Phone normalization (float→int, country codes, leading zeros)
- [x] Re-normalization during matching
- [x] Debug/Reprocess endpoints
- [x] Role Drilldown applicant table with status badges
- [x] **XLSX datetime.time serialization fix** — clean_value() handles Excel time objects (Apr 9)
- [x] **Date formatting** — midnight timestamps display as DD-Mon-YYYY (Apr 9)

## Backlog
### P1
- [ ] CSV export from summary and role drill-down tables
- [ ] Session persistence across page refreshes

### P2
- [ ] Upload history view
- [ ] Advanced chart visualizations on dashboard
- [ ] Role-based access control (Admin vs Recruiter)
