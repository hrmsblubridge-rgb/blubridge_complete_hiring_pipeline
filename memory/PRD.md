# Recruitment Analytics - Product Requirements Document

## Original Problem Statement
Build BluBridge Hiring Pipeline — a comprehensive recruitment platform with analytics, form-based hiring, interview scheduling, candidate management, and automated messaging.

## Core Architecture
- **Frontend**: React + Tailwind CSS + Shadcn UI + Phosphor Icons
- **Backend**: FastAPI + Motor (async MongoDB) + bb_modules.py + messaging.py + bg_workers.py
- **Database**: MongoDB
- **Auth**: Admin User / Admin User (JWT cookie)
- **Messaging**: AiSensy WhatsApp API + SMTP Email (Gmail)

## All Features (Complete)

### Core Platform
- Upload (Naukri, Pipeline, Score Sheet, College Rank), matching, derived statuses
- Summary, Applicants, Attended pages with filters + pagination
- DB-driven bulk upload queue, Job keyword mapping, Multi-criteria College matching

### BluBridge Extension Modules
- Home Page (8 buttons), Job Roles CRUD, Form Types + Hiring Forms with conditions
- Interview Schedule Reports (filters + export), Update Scores (export + import)
- Job Openings (vacancies, education, salary, responsibilities)
- Set Holidays, Verify Applicant OTP
- Public Registration Form with auto-shortlisting
- Interview Schedule/Reschedule with holiday blocking

### Live Messaging System (Completed - Apr 28, 2026)
- **messaging.py**: Centralized service with `_resolve_recipient()` for TEST_MODE guard
- **AiSensy WhatsApp**: 5 campaign templates (ShortList, Reject, Schedule Detail, OTP With Job, Candidate FollowUp)
- **SMTP Email**: Real sending via smtp.gmail.com:465 (hr@blubridge.com)
- **Feature Flags**: ENABLE_WHATSAPP, ENABLE_EMAIL, TEST_MODE in .env
- **TEST_MODE**: All recipients overridden to phone=9443109903, email=rishi.nayak@blubridge.com

### Background Workers (Completed - Apr 28, 2026)
- **OTP Generator** (every 60s): Generates + sends OTP 3h before interview, idempotent via `otp_sent` flag
- **Schedule Link Sender** (every 60s): Sends shortlist/reject notifications 5-30 min after registration, idempotent via `schedule_link_sent` flag
- **24h Reminder** (every 5 min): Re-sends schedule link if not scheduled after 24h, idempotent via `reminder_24h_sent` flag

## Feature Flags (.env)
- ENABLE_WHATSAPP=true — toggle WhatsApp sending
- ENABLE_EMAIL=true — toggle Email sending
- TEST_MODE=true — override all recipients to test phone/email
- TEST_PHONE=9443109903
- TEST_EMAIL=rishi.nayak@blubridge.com

## Prioritized Backlog
- P1: Fix AiSensy API key (currently returns 401 — user may need to regenerate)
- P2: OTP expiry after 8 hours (set otp_expired field)
- P2: Advanced chart visualizations, Role-based access control
