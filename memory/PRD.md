# Recruitment Analytics - Product Requirements Document

## Original Problem Statement
Build BluBridge Hiring Pipeline — a comprehensive recruitment platform with analytics, form-based hiring, interview scheduling, and candidate management.

## Core Architecture
- **Frontend**: React + Tailwind CSS + Shadcn UI + Phosphor Icons
- **Backend**: FastAPI + Motor (async MongoDB) + bb_modules.py (separate router)
- **Database**: MongoDB
- **Auth**: Admin User / Admin User (JWT cookie)

## Implemented Features

### Phase 1-3: Core Platform + Analytics + Enhancements (Completed)
- Upload (Naukri, Pipeline, Score Sheet, College Rank), matching, derived statuses
- Summary, Applicants, Attended pages with filters + pagination
- DB-driven bulk upload queue, Job keyword mapping, College matching

### Phase 4-6: Previous Extensions (Completed)
- Job Role Normalization, Multi-criteria College Matching, Bulk Upload Queue

### Phase 7: BluBridge Extension Modules (Completed - Apr 21)
- Home Page (8 buttons), Job Roles CRUD, Form Types + Hiring Forms, Interview Reports, Update Scores, Job Openings, Rounds

### Phase 8: Full PDF Implementation (Completed - Apr 22)
**Login**: Credentials updated to `Admin User` / `Admin User`

**Home Page**: 8 navigation buttons — Analytics Dashboard, Hiring Forms, Interview Schedule Reports, Update Applicants Scores, Create Job Roles, Create Job Openings, Set Holidays, Verify Applicant OTP

**Set Holidays** (`/set-holidays`): CRUD for holidays (name + date). Holidays block interview scheduling dates.

**Verify Applicant OTP** (`/verify-otp`): Phone + OTP verification. Updates otp_verified in both bb_registrations and registered_candidates.

**Public Registration Form** (`/register/:formId`): No-auth public page. Fields: Full Name, Email, Phone, Age, State, City, Grad Year, Degree, Course, College. Conditional: Location Change + Attend In Person questions (shown when city doesn't match location limit). AI&ML roles show Deep Learning Research Team info page. Auto-shortlisting engine checks all conditions.

**Interview Schedule** (`/schedule-interview/:token`): No-auth public page via unique token. Pre-filled Name/Email/Phone. Date picker (blocks Sundays + holidays). Time slots (30-min, 10AM-5PM). Reschedule support. OTP auto-generated.

**Enhanced Job Openings**: New fields — vacancies, years_of_graduation (multi), education (multi), salary_range, key_responsibilities, added_advantages, what_we_offer

**Enhanced Hiring Forms**: Link button on cards (opens public registration), "Job description attached?" (Yes/No) with job opening selector. When JD attached, public link shows job description before registration form.

**Auto-Shortlisting**: Checks age, graduation year, location limits, location_change, attend_in_person, college NIRF status. Single failed condition = Rejected.

**Analytics Integration**: Registrations write to both `bb_registrations` AND `registered_candidates` for Dashboard visibility.

**STUBBED**: Email/WhatsApp messaging (status updates happen, no messages sent)

## DB Collections
### Existing (UNTOUCHED)
- naukri_applies, pipeline_data, registered_candidates, score_sheet, college_rank_list
- job_keyword_mapping, job_titles_master, bulk_upload_queue

### New (bb_ prefix)
- bb_job_roles, bb_form_types, bb_hiring_forms, bb_rounds, bb_job_openings
- bb_holidays: {name, date, created_at}
- bb_registrations: {form_id, full_name, email, phone, age, status, schedule_token, otp, schedule_date, schedule_time, ...}
- bb_applicant_updates: {email, status, scores[]}

## API Endpoints
### Existing (UNTOUCHED): /api/login, /api/upload/*, /api/bulk-upload/*, /api/summary, /api/applicants, /api/attended, /api/job-roles, /api/job-keyword-mappings
### BB Admin: /api/bb/job-roles, /api/bb/form-types, /api/bb/hiring-forms, /api/bb/rounds, /api/bb/job-openings, /api/bb/holidays, /api/bb/verify-otp, /api/bb/interview-reports, /api/bb/attended-for-scores, /api/bb/applicant-score/{email}
### Public (no auth): /api/pub/form/{formId}, /api/pub/register, /api/pub/schedule/{token}

## Prioritized Backlog
- P1: Email/WhatsApp integration (currently stubbed)
- P1: OTP auto-generation 3 hours before interview
- P1: OTP expiry after 8 hours
- P2: Reminder emails 2 hours after missed interview
- P2: Advanced chart visualizations, Role-based access control
