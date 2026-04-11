# Recruitment Analytics PRD

## Original Problem Statement
Refactor and rebuild the application to enforce correct data flow from upload -> database -> analytics -> UI. The application must process Naukri Applies and HR Internal Pipeline datasets with exact column mapping, enforce relational integrity (Registered Users = INNER JOIN on email/phone), and operate as a stateful, database-driven system.

## Architecture
- Frontend: React, Shadcn UI, Tailwind CSS, Axios, React Router, dayjs
- Backend: FastAPI, PyJWT, Pandas
- Database: MongoDB
- Auth: Cookie-based JWT (hardcoded admin/admin)

## Core Collections
- `naukri_applies`: Uploaded Naukri dataset
- `pipeline_data`: Uploaded HR pipeline dataset
- `registered_candidates`: Auto-computed INNER JOIN on email/phone
- `score_sheet`: Uploaded score sheets mapped to attendees
- `users`: Auth credentials

## Implemented Features
1. Independent CSV/XLSX uploads (Naukri, Pipeline, Score Sheet)
2. Automatic matching/join when both datasets exist
3. Dashboard with uploads + analytics navigation (no dataset count bar)
4. Summary Statistics page (`/summary`) — renamed columns: Shortlisted, Rejected, Interview Scheduled, Interview Not Scheduled, Attended, Not Attended
5. View Applicants (`/roles`) — **global registered applicants table** with Job Role dropdown, Date Filter Type (Registered/Scheduled), date range, search, pagination (100/page)
6. View Attended Applicants (`/attended-roles`) — **global attended applicants table** with Job Role dropdown, Round filter, date range, search, score columns in alphabetical order, pagination
7. Date display format: DD-MM-YYYY (frontend only, DB stores YYYY-MM-DD)
8. Strict status classification hierarchy
9. Phone/email normalization, datetime serialization fixes

## Routes
- `/login` - Auth
- `/dashboard` - Upload + Navigation hub
- `/summary` - Funnel analytics table
- `/roles` - Global registered applicants table
- `/attended-roles` - Global attended applicants table

## Removed Routes (2026-04-11)
- `/roles/:jobRole` - Old role drilldown (replaced by global table)
- `/attended/:jobRole` - Old attended drilldown (replaced by global table)

## API Endpoints
- POST `/api/login`, POST `/api/logout`, GET `/api/auth/check`
- POST `/api/upload/naukri`, POST `/api/upload/pipeline`, POST `/api/upload/scoresheet`
- GET `/api/summary`, GET `/api/job-roles`
- GET `/api/applicants?jobRole=&dateType=&startDate=&endDate=&search=&page=&limit=` (NEW - global registered table)
- GET `/api/attended?jobRole=&round=&startDate=&endDate=&search=&page=&limit=` (MODIFIED - jobRole now optional)
- GET `/api/role?jobRole=&page=&search=&startDate=&endDate=` (legacy, still works)

## Removed Endpoints
- `/api/status` (dashboard dataset counts)
- `/api/dashboard-counts`

## Backlog
- P1: CSV export/download from tables
- P1: Session persistence across page refreshes
- P2: Upload History view
- P2: Advanced chart visualizations
- P2: Role-based access control (Admin vs Recruiter)
