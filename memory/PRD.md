# Recruitment Analytics PRD

## Original Problem Statement
Refactor and rebuild the application to enforce correct data flow from upload -> database -> analytics -> UI. The application must process Naukri Applies and HR Internal Pipeline datasets with exact column mapping, enforce relational integrity (Registered Users = INNER JOIN on email/phone), and operate as a stateful, database-driven system.

## Architecture
- Frontend: React, Shadcn UI, Tailwind CSS, Axios, React Router, dayjs
- Backend: FastAPI, PyJWT, Pandas
- Database: MongoDB
- Auth: Cookie-based JWT (hardcoded admin/admin)

## Core Collections
- `naukri_applies`, `pipeline_data`, `registered_candidates`, `score_sheet`, `users`

## Implemented Features
1. Independent CSV/XLSX uploads (Naukri, Pipeline, Score Sheet)
2. **Bulk Upload** with background processing (30s interval) for all 3 dataset types
3. Automatic matching/join when both datasets exist
4. Dashboard with uploads + bulk buttons + analytics navigation
5. Summary Statistics page with renamed columns
6. View Applicants — global registered table with filters and pagination
7. View Attended Applicants — global attended table with scores and filters
8. Dynamic page size dropdown (10-500)
9. Phone normalization (handles spaces, commas, +91/0091 prefixes)
10. Date display: DD-MM-YYYY (frontend only)
11. Strict status classification hierarchy

## Routes
- `/login`, `/dashboard`, `/summary`, `/roles`, `/attended-roles`

## API Endpoints
- Auth: POST `/api/login`, POST `/api/logout`, GET `/api/auth/check`
- Upload: POST `/api/upload/naukri`, `/api/upload/pipeline`, `/api/upload/scoresheet`
- Bulk: POST `/api/bulk-upload/{type}`, DELETE `/api/bulk-upload/{type}/{filename}`, GET `/api/bulk-upload/status`, POST `/api/bulk-upload/process-now`
- Data: GET `/api/summary`, `/api/job-roles`, `/api/applicants`, `/api/attended`

## Backlog
- P1: CSV export/download from tables
- P1: Session persistence across page refreshes
- P2: Upload History view
- P2: Advanced chart visualizations
- P2: Role-based access control (Admin vs Recruiter)
