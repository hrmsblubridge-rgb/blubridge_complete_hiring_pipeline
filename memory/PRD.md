# Recruitment Analytics - Product Requirements Document

## Original Problem Statement
Build BluBridge Hiring Pipeline — a comprehensive recruitment platform with analytics, form-based hiring, interview scheduling, and candidate management.

## Core Architecture
- **Frontend**: React + Tailwind CSS + Shadcn UI + Phosphor Icons
- **Backend**: FastAPI + Motor (async MongoDB) + bb_modules.py (separate router)
- **Database**: MongoDB
- **Auth**: Admin User / Admin User (JWT cookie)

## Implemented Features (All Phases Complete)

### Core Platform
- Upload (Naukri, Pipeline, Score Sheet, College Rank), matching, derived statuses
- Summary, Applicants, Attended pages with filters + pagination
- DB-driven bulk upload queue, Job keyword mapping, College matching

### BluBridge Extension Modules
- Home Page (8 buttons), Job Roles CRUD, Form Types + Hiring Forms with conditions
- Interview Schedule Reports with filters + CSV export
- Update Applicants Scores with Rounds CRUD, Export report, Import report
- Job Openings (enhanced: vacancies, education, salary, responsibilities, advantages, what_we_offer)
- Set Holidays, Verify Applicant OTP
- Public Registration Form with auto-shortlisting
- Interview Schedule/Reschedule with holiday blocking

### Messaging (STUBBED - not triggered)
- AiSensy WhatsApp API functions coded
- SMTP Email functions coded
- All messaging is logged but NOT executed

## DB Collections
- Existing: naukri_applies, pipeline_data, registered_candidates, score_sheet, college_rank_list, job_keyword_mapping, job_titles_master, bulk_upload_queue
- New: bb_job_roles, bb_form_types, bb_hiring_forms, bb_rounds, bb_job_openings, bb_holidays, bb_registrations, bb_applicant_updates

## Prioritized Backlog
- P1: Enable Email/WhatsApp messaging (currently stubbed)
- P1: Background OTP generation 3h before interview
- P1: OTP expiry after 8h, missed interview reminders
- P2: Advanced charts, Role-based access control
