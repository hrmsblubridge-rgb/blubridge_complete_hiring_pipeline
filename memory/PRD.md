# Recruitment Analytics PRD

## Original Problem Statement
Refactor and rebuild the application to enforce correct data flow from upload -> database -> analytics -> UI. The application must process Naukri Applies and HR Internal Pipeline datasets with exact column mapping, enforce relational integrity (Registered Users = INNER JOIN on email/phone), and operate as a stateful, database-driven system.

## Architecture
- Frontend: React, Shadcn UI, Tailwind CSS, Axios, React Router
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
3. Dashboard with DB status bar and navigation
4. Summary Statistics page (`/summary`) with funnel metrics
5. View Applicants (`/roles`) -> Role Drilldown (`/roles/:jobRole`) with simplified table (no scores), search, date filters, pagination (100/page)
6. View Attended Applicants (`/attended-roles`) -> Attended Drilldown (`/attended/:jobRole`) with score columns, round filter, search, date filters, pagination
7. Strict status classification hierarchy (Shortlisted, Rejected, Attended, Not Attended, Registered)
8. Phone/email normalization, datetime serialization fixes

## Routes
- `/login` - Auth
- `/dashboard` - Upload + Navigation hub
- `/summary` - Funnel analytics table
- `/roles` - Job role cards
- `/roles/:jobRole` - Applicant table (simplified, no scores)
- `/attended-roles` - Attended role cards
- `/attended/:jobRole` - Attended applicant table with scores

## API Endpoints
- POST `/api/login`, POST `/api/logout`, GET `/api/auth/check`
- POST `/api/upload/naukri`, POST `/api/upload/pipeline`, POST `/api/upload/scoresheet`
- GET `/api/status`, GET `/api/summary`, GET `/api/job-roles`
- GET `/api/role?jobRole=&page=&search=&startDate=&endDate=`
- GET `/api/attended-roles`
- GET `/api/attended?jobRole=&page=&search=&startDate=&endDate=&round=`

## Backlog
- P1: CSV export/download from tables
- P1: Session persistence across page refreshes
- P2: Upload History view
- P2: Advanced chart visualizations
- P2: Role-based access control (Admin vs Recruiter)
