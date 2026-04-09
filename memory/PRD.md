# Recruitment Analytics System - PRD

## Project Overview
Full-stack recruitment analytics system with data-driven, database-backed UI. Ingests Naukri Applies and HR Pipeline datasets, matches records, and provides role-wise funnel analytics.

## Architecture
- **Frontend**: React + Tailwind CSS + Phosphor Icons
- **Backend**: FastAPI + Motor (async MongoDB)
- **Database**: MongoDB (naukri_applies, pipeline_data, registered_candidates)
- **Auth**: JWT cookie-based (admin/admin)

## Navigation Flow
```
/login → /dashboard (Home)
  ├── Upload Naukri / Pipeline datasets (independent)
  ├── /summary (Role-wise funnel table with filters)
  └── /roles (Job role grid)
       └── /roles/:jobRole (Drill-down for specific role)
```

## Key Design Decisions
1. **Role API uses query param** (`/api/role?jobRole=`) not path param — avoids 404s from special chars (`&`, `/`, `+`)
2. **Uploads are independent** — each works alone; matching runs with whatever data exists
3. **DB-driven state** — `/api/status` returns live counts; dashboard reflects real DB state
4. **Registered = JOIN** — all analytics use `registered_candidates` (INNER JOIN of naukri + pipeline)

## API Endpoints
- POST /api/login, /api/logout, GET /api/auth/check
- POST /api/upload/naukri, /api/upload/pipeline
- GET /api/status (naukri_count, pipeline_count, registered_count)
- GET /api/summary?startDate=&endDate=&search=
- GET /api/job-roles
- GET /api/role?jobRole=&startDate=&endDate= (query param, NOT path param)
- GET /api/dashboard-counts (legacy)
- GET /api/data/{category} (legacy)

## Schema Mapping
- Naukri: NAUKRI_COLUMN_MAP (65+ fields)
- Pipeline: PIPELINE_EXPECTED_COLUMNS (40 fields, with dedup)
- registered_candidates: INNER JOIN merging ALL fields

## Code Structure
```
backend/server.py
frontend/src/
  App.js (routes)
  pages/Dashboard.js, Summary.js, Roles.js, RoleDrillDown.js
  context/AuthContext.js
  components/ProtectedRoute.js
```

## Testing (April 9, 2026)
- Backend: 13/13 passed (100%)
- Frontend: 19/19 passed (100%)
- All 3 fixes verified: query param API, independent uploads, DB-driven status

## Backlog
### P1
- [ ] CSV export from tables
- [ ] Session persistence across refreshes
### P2
- [ ] Upload history
- [ ] Advanced charts
- [ ] Role-based access
