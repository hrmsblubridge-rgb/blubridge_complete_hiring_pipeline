# Recruitment Analytics System - PRD

## Project Overview
Full-stack recruitment analytics system. Ingests Naukri Applies, HR Pipeline, and Score Sheet datasets. Matches records via email/phone JOIN, provides role-wise funnel analytics, individual applicant drill-downs with per-round scores.

## Architecture
- **Frontend**: React + Tailwind CSS + Phosphor Icons
- **Backend**: FastAPI + Motor (async MongoDB)
- **Database**: MongoDB (naukri_applies, pipeline_data, registered_candidates, score_sheet)
- **Auth**: JWT cookie-based (admin/admin)

## STRICT STATUS HIERARCHY (email_type field)
```
Registered
├── Shortlisted (email_type IN 'shortlist', 'shortlisted')
│   ├── Interview Scheduled (has schedule_date AND schedule_time)
│   │   ├── Attended (otp_verified IS NOT NULL)
│   │   └── Not Attended (otp_verified IS NULL)
│   └── Interview Not Scheduled (no schedule_date/time)
├── Rejected (email_type IN 'reject', 'rejected')
└── Other Registered
```

## Score Sheet Integration
- Upload: CSV/XLSX with fields: name, email, phone, score, round_name
- Storage: score_sheet collection, multiple rows per applicant (different rounds)
- Matching: via pipeline_data (email OR phone), NOT naukri directly
- Display: Only for "Attended" status candidates
- Round columns: ZA, C++, Java, BA, LA, Mensa Org, Accounts2, Accounts1, BE, Mensa, BP
- Total Score: Sum of all round scores

## Summary Table Columns (10)
Job Role | Total Naukri | Total Registered | Total Unregistered | Total Shortlisted | Total Rejected | Interview Scheduled | Without Interview | Attended | Didn't Attend

## API Endpoints
- POST /api/upload/naukri, /api/upload/pipeline, /api/upload/scoresheet (CSV + XLSX)
- GET /api/status (includes score_sheet_count)
- GET /api/summary (includes total_naukri, total_registered, total_unregistered)
- GET /api/role?jobRole= (19 columns: 7 base + 11 score + Total Score)
- POST /api/reprocess, GET /api/debug/matching

## Completed Work
- [x] Core upload, matching, analytics pipeline
- [x] Strict Status Hierarchy (email_type based)
- [x] Phone normalization (float→int, country codes, leading zeros)
- [x] XLSX datetime.time serialization fix
- [x] Summary: Total Naukri, Registered, Unregistered columns (Apr 10)
- [x] Score Sheet upload endpoint + collection (Apr 10)
- [x] Role Drilldown: 12 score columns with round mapping (Apr 10)
- [x] Score display restricted to Attended status only (Apr 10)

## Backlog
### P1
- [ ] CSV export from summary and role drill-down tables
- [ ] Session persistence across page refreshes

### P2
- [ ] Upload history view
- [ ] Advanced chart visualizations on dashboard
- [ ] Role-based access control (Admin vs Recruiter)
