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
  ├── Upload Naukri / Pipeline datasets
  ├── /summary (Role-wise funnel table with filters)
  └── /roles (Job role grid)
       └── /roles/:jobRole (Drill-down for specific role)
```

## Pages

### Dashboard (/dashboard)
- Upload Naukri Applies Dataset button
- Upload HR Internal Pipeline Dataset button
- View Applicants Summary Statistics → /summary
- View Applicants → /roles

### Summary (/summary)
- Filters: Start Date, End Date, Search (job role), Filter, Reset, Back
- Table: Job Role, Total Applicants, Shortlisted, Rejected, Scheduled, Not Scheduled, Attended, Not Attended
- TOTAL row with column sums
- All data from registered_candidates only

### Roles (/roles)
- Grid of clickable job role boxes
- Each shows role name + registered applicant count
- Click → /roles/:jobRole

### Role Drill-Down (/roles/:jobRole)
- Same table as Summary but filtered for one role
- Date filters + Reset + Back

## Schema Mapping
- Naukri: NAUKRI_COLUMN_MAP (65+ fields, "Email ID"→email, "Phone Number"→phone, etc.)
- Pipeline: PIPELINE_EXPECTED_COLUMNS (40 fields, confirm_box, job_role, etc.)
- registered_candidates: INNER JOIN merging ALL fields from both

## API Endpoints
- POST /api/login, /api/logout, GET /api/auth/check
- POST /api/upload/naukri, /api/upload/pipeline
- GET /api/summary?startDate=&endDate=&search=
- GET /api/job-roles
- GET /api/role/{jobRole}?startDate=&endDate=
- GET /api/dashboard-counts (legacy)
- GET /api/data/{category} (legacy, 8 categories)

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
- Backend: 21/21 passed (100%)
- Frontend: 16/16 passed (100%)
- Filters (date, search, reset): verified
- Navigation flow: verified
- Upload via dashboard: verified

## Backlog
### P1
- [ ] CSV export from tables
- [ ] Session persistence across refreshes
### P2
- [ ] Upload history
- [ ] Advanced charts
- [ ] Role-based access
