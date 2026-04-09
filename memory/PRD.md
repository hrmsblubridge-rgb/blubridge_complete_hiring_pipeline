# Recruitment Analytics System - PRD

## Project Overview
Full-stack recruitment analytics system. Ingests Naukri Applies and HR Pipeline datasets independently, matches records via email/phone JOIN, provides role-wise funnel analytics.

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
5. **Schema mapping** — NAUKRI_COLUMN_MAP (65+ fields), PIPELINE_EXPECTED_COLUMNS (40 fields)

## API Endpoints
- POST /api/login, /api/logout, GET /api/auth/check
- POST /api/upload/naukri, /api/upload/pipeline
- GET /api/status
- GET /api/summary?startDate=&endDate=&search=
- GET /api/job-roles
- GET /api/role?jobRole=&startDate=&endDate=

## Pages
- /dashboard — Upload buttons + DB status + navigation
- /summary — Role-wise funnel table with date/search filters
- /roles — Clickable job role grid
- /roles/:jobRole — Drill-down for specific role

## Testing (April 9, 2026)
- Full E2E pipeline verified: Upload → DB → Matching → Analytics → UI
- All validation rules confirmed (sum of applicants = total registered)
- Independent upload flow verified (Naukri alone → Pipeline added → matching)
- DB cleaned and ready for production data

## Backlog
### P1
- [ ] CSV export from tables
- [ ] Session persistence across refreshes
### P2
- [ ] Upload history, advanced charts, role-based access
