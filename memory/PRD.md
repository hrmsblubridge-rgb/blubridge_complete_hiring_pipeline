# Recruitment Analytics — Product Requirements

## Original Problem Statement
Build BluBridge Hiring Pipeline — a recruitment platform with analytics, hiring forms, interview scheduling, candidate management, and automated WhatsApp + Email messaging.

## Core Architecture
- **Frontend**: React + Tailwind + Shadcn UI + Phosphor Icons
- **Backend**: FastAPI + Motor (async MongoDB) + bb_modules.py + messaging.py + bg_workers.py
- **Database**: MongoDB Atlas (free tier — has `allowDiskUse` + 32MB sort restrictions)
- **Auth**: Hardcoded `Admin User` / `Admin User` (JWT cookie)
- **Messaging**: AiSensy WhatsApp + SMTP Email (Gmail SSL 465)

## Persisted Derived Fields (added May 2026 — perf optimization)
On `registered_candidates` and `naukri_applies` we now persist:
- `_college_status` — `"NIRF - #<rank>"` or `"Non NIRF"`
- `_nirf_category` — `"NIRF"` or `"Non NIRF"`
- `_college_resolved` — best-matched college string
- `_match_confidence` — HIGH | MEDIUM | LOW | None
- `_normalized_job_role` — canonical role from `job_keyword_mapping`

This eliminates 20K-doc in-memory scans on every API request. Endpoints filter and aggregate at the DB level.

## Endpoints (now Atlas-free-tier safe)
- `GET /api/summary` — aggregation pipeline grouping by `_normalized_job_role` + `_nirf_category`
- `GET /api/applicants` — `.find({...}).skip().limit()` with persisted-field filters; aggregation `$sort` on indexed `name`
- `GET /api/job-roles` — `$group` aggregation
- `GET /api/attended` — DB-level pagination + per-page score lookup (no full score_sheet scan)
- `GET /api/attended-roles` — aggregation pipeline

## Backfill / Reprocess
- One-time backfill: `python3 /app/backend/backfill_derived.py`
- Auto-runs after `reprocess_matching` (which is invoked from `/api/reprocess` and bulk uploads)
- Indexes auto-created on `_normalized_job_role`, `_nirf_category`, `_college_status`, `name`, `schedule_date`

## Live Messaging System
- AiSensy WhatsApp (5 campaigns), SMTP Email (Gmail SSL 465)
- TEST_MODE overrides recipients to `TEST_PHONE` / `TEST_EMAIL`
- Background workers: OTP Generator, Schedule Link Sender, 24h Reminder, OTP Expiry, Missed Interview

## Feature Flags (.env)
- `ENABLE_WHATSAPP`, `ENABLE_EMAIL`, `TEST_MODE`, `TEST_PHONE`, `TEST_EMAIL`
- `MONGO_URL`, `DB_NAME`, `JWT_SECRET`, `SMTP_*`

## Changelog
- **May 2026** — Performance fix: persisted derived fields, all hot endpoints DB-level optimized; pass 18/18 backend regression (`iteration_27.json`).
- **Apr 2026** — Atlas DB swap, registered_candidates rebuilt (19,913 docs).
- **Apr 2026** — Live messaging + background workers, registration UI clone, global Back Button.

## Prioritized Backlog
- **P1** — Fix AiSensy API key (currently 401, gracefully handled)
- **P2** — Upload History view
- **P2** — Advanced chart visualizations on dashboard
- **P2** — Role-based access control (Admin vs Recruiter)
- **P2** — Refactor `/api/role` to use persisted fields (currently legacy path)
- **P3** — Move routes into `/app/backend/routes/`, models into `/app/backend/models/`
