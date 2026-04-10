# Recruitment Analytics System - PRD

## Project Overview
Full-stack recruitment analytics system. Ingests Naukri Applies, HR Pipeline, and Score Sheet datasets. Matches records via email/phone JOIN, provides role-wise funnel analytics, individual applicant drill-downs with per-round scores.

## Architecture
- **Frontend**: React + Tailwind CSS + Phosphor Icons
- **Backend**: FastAPI + Motor (async MongoDB)
- **Database**: MongoDB (naukri_applies, pipeline_data, registered_candidates, score_sheet)
- **Auth**: JWT cookie-based (admin/admin)

## Date Storage
All dates stored as **ISO YYYY-MM-DD** (e.g., "2026-03-24"). `normalize_date()` converts DD-MMM-YYYY, DD-MM-YYYY, and Timestamp formats at upload time.

## STRICT STATUS HIERARCHY (email_type field)
```
Registered
├── Shortlisted (email_type IN 'shortlist', 'shortlisted')
│   ├── Interview Scheduled → Attended / Not Attended
│   └── Interview Not Scheduled
├── Rejected (email_type IN 'reject', 'rejected')
└── Other Registered
```

## Score Sheet Integration
- Upload CSV/XLSX: name, email, phone, score, round_name
- Match via pipeline_data (email OR phone)
- Only display for "Attended" status
- 11 round columns + Total Score

## API Endpoints
- POST /api/upload/naukri, /api/upload/pipeline, /api/upload/scoresheet
- GET /api/status, /api/dashboard-counts, /api/summary, /api/job-roles
- GET /api/role?jobRole=&startDate=&endDate=&page=&limit=
- POST /api/reprocess, GET /api/debug/matching

## Completed Work
- [x] Core upload, matching, analytics pipeline
- [x] Strict Status Hierarchy
- [x] Phone normalization (float→int)
- [x] XLSX datetime.time serialization fix
- [x] Summary: Naukri/Registered/Unregistered columns
- [x] Score Sheet upload + per-round scoring in drilldown
- [x] **Date filtering fix**: ISO YYYY-MM-DD storage + normalize_date() (Apr 10)

## Backlog
### P1
- [ ] CSV export from summary and role drill-down tables
- [ ] Session persistence across page refreshes

### P2
- [ ] Upload history view
- [ ] Advanced chart visualizations
- [ ] Role-based access control
