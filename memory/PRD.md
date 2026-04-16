# Recruitment Analytics PRD

## Original Problem Statement
Refactor and rebuild the application to enforce correct data flow from upload -> database -> analytics -> UI. The application must process Naukri Applies and HR Internal Pipeline datasets with exact column mapping, enforce relational integrity (Registered Users = INNER JOIN on email/phone), and operate as a stateful, database-driven system.

## Architecture
- Frontend: React, Shadcn UI, Tailwind CSS, Axios, React Router, dayjs
- Backend: FastAPI, PyJWT, Pandas
- Database: MongoDB
- Auth: Cookie-based JWT (hardcoded admin/admin)

## Core Collections
- `naukri_applies`, `pipeline_data`, `registered_candidates`, `score_sheet`, `college_rank_list`, `users`

## Implemented Features
1. Independent CSV/XLSX uploads (Naukri, Pipeline, Score Sheet, **College Rank List**)
2. Bulk Upload with sequential queue processing
3. Automatic matching/join when both datasets exist
4. Dashboard with uploads + bulk buttons + analytics navigation
5. Summary Statistics — split by **NIRF / Non-NIRF** per job role
6. View Applicants — global table with **college_status** column and filter
7. View Attended Applicants — global table with scores, **college_status** column and filter
8. Dynamic page size dropdown (10-500)
9. Phone normalization, date formatting (DD-MM-YYYY)
10. Strict status classification hierarchy
11. **College Rank Integration**: Matches ug_university/pg_university against college rank list. NIRF classification: 1-100=NIRF, 101-150=Non NIRF 101-150, 151-200=Non NIRF 151-200, 201-300=Non NIRF 201-300, No match=Non NIRF

## Routes
- `/login`, `/dashboard`, `/summary`, `/roles`, `/attended-roles`

## API Endpoints
- Auth: POST `/api/login`, POST `/api/logout`, GET `/api/auth/check`
- Upload: POST `/api/upload/naukri`, `/api/upload/pipeline`, `/api/upload/scoresheet`, **`/api/upload/college-rank`**
- Bulk: POST `/api/bulk-upload/{type}`, DELETE `/api/bulk-upload/{type}/{filename}`, GET `/api/bulk-upload/status`, POST `/api/bulk-upload/process-now`
- Data: GET `/api/summary`, `/api/job-roles`, `/api/applicants?collegeStatus=`, `/api/attended?collegeStatus=`

## Backlog
- P1: CSV export/download from tables
- P1: Session persistence across page refreshes
- P2: Upload History view
- P2: Advanced chart visualizations
- P2: Role-based access control (Admin vs Recruiter)
