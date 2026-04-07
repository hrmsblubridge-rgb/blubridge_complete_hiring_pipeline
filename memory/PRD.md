# Recruitment Analytics System - PRD

## Project Overview
Full-stack web application for recruitment analytics that ingests Naukri Applies and Pipeline Data, processes them, matches records, and displays a funnel-based analytics dashboard.

## User Personas
1. **Recruiters** - Upload candidate data and view analytics
2. **HR Managers** - Monitor recruitment funnel and track conversion rates
3. **Admin** - Manage system access

## Core Requirements (Static)
- JWT-based authentication
- File upload (CSV/XLSX) with 10MB limit
- Data validation and normalization
- Candidate matching (email primary, phone fallback)
- Funnel visualization
- Job role filtering
- CSV export

## What's Been Implemented (April 7, 2026)

### Authentication System
- [x] JWT auth with httpOnly cookies
- [x] Login/Register pages
- [x] Protected routes
- [x] Admin seeding on startup
- [x] Token refresh mechanism

### Data Upload
- [x] `/upload/naukri` - Naukri Applies upload
- [x] `/upload/pipeline` - Pipeline Data upload
- [x] File validation (CSV, XLSX)
- [x] Schema validation (required columns)
- [x] Data normalization (email lowercase, phone cleanup)
- [x] Duplicate detection
- [x] Error reporting

### Data Processing
- [x] `/api/process` - Match candidates between datasets
- [x] Email/phone matching
- [x] Status classification

### Analytics Dashboard
- [x] Funnel visualization
- [x] Summary stats cards
- [x] Job role filter
- [x] CSV download
- [x] Empty state handling

### Design
- [x] Swiss brutalist theme (light)
- [x] Syne + DM Sans typography
- [x] Sharp edges, 1px borders
- [x] Phosphor icons
- [x] Responsive layout

## API Endpoints
- POST `/api/auth/register`
- POST `/api/auth/login`
- POST `/api/auth/logout`
- GET `/api/auth/me`
- POST `/api/auth/refresh`
- POST `/api/upload/naukri`
- POST `/api/upload/pipeline`
- POST `/api/process`
- GET `/api/analytics?job_role=`
- GET `/api/analytics/download?job_role=`

## Database Collections
- `users` - User accounts
- `naukri_applies` - Naukri job applications
- `pipeline_data` - Recruitment pipeline data
- `processed_candidates` - Matched/processed candidates
- `upload_history` - Upload logs

## Prioritized Backlog

### P0 - Critical (Completed)
- [x] Authentication
- [x] File uploads
- [x] Data processing
- [x] Analytics dashboard

### P1 - Important (Future)
- [ ] Bulk delete/reset data
- [ ] Upload history view
- [ ] Real-time processing on upload

### P2 - Nice to Have
- [ ] Role-based access (Admin/Recruiter)
- [ ] Advanced charts (bar, pie)
- [ ] Date range filtering
- [ ] Email notifications

## Next Tasks
1. Add upload history tracking page
2. Implement data reset functionality
3. Add more chart types to dashboard
