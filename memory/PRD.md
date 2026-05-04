# Recruitment Analytics — Product Requirements

## Original Problem Statement
BluBridge Hiring Pipeline — recruitment platform with analytics, hiring forms, interview scheduling, candidate management, automated WhatsApp + Email.

## Core Architecture
- **Frontend**: React + Tailwind + Shadcn UI
- **Backend**: FastAPI + Motor (async MongoDB) + bb_modules.py + messaging.py + bg_workers.py
- **Database**: MongoDB Atlas free tier (512 MB hard quota — design constraint)
- **Auth**: Admin User / Admin User (hardcoded JWT cookie)
- **Messaging**: AiSensy WhatsApp (API key 401 — pending) + SMTP Email (Gmail SSL 465)

## Classification Rule (May 2026 — VIEW-based)
Atlas free-tier quota prevents physical duplication of 100K pipeline into `registered_candidates`. We keep:
- `registered_candidates` = INNER JOIN of pipeline + naukri (19,913 enriched docs) — used by scoring/scheduling
- `pipeline_data` (100,798) = HR internal dataset → counts as "Registered"
- `naukri_applies` (35,469) with `_is_registered` flag → unmatched rows (15,555) counts as "Unregistered"

### Endpoints exposing the rule:
- `GET /api/data/classification` — live counts `{total_registered, total_unregistered, total_naukri, matched}`
- `GET /api/data/registered` — page through `pipeline_data`
- `GET /api/data/unregistered` — page through `naukri_applies WHERE _is_registered != True`
- `GET /api/summary` — adds `total_registered_hr` + `total_unregistered_naukri` on top-level response (legacy `total_registered` kept for backward compat)
- `GET /api/applicants`, `/attended`, `/job-roles` continue to read the enriched JOIN view

### Safety rule: all endpoints exclude `isTest: true` rows. All test seeds MUST tag `isTest: true` and delete after.

## OTP (Interview Scheduling)
- Window: `schedule_time - 3h` → `schedule_time - 1min` (`_worker_otp_generator`, 30s interval)
- Expiry: 8h post-send (`_worker_otp_expiry`)
- Fields (idempotent):
  - snake_case: `otp`, `otp_sent`, `otp_sent_at`, `otp_expired`, `otp_expired_at`, `otp_verified`
  - camelCase aliases (May 2026): `otpGeneratedAt`, `otpExpiry` (for external integrations)
- Written to: `bb_registrations` (primary) AND mirrored onto `registered_candidates` matched by email/phone

## Persisted Derived Fields
On `registered_candidates` and `naukri_applies`:
- `_college_status`, `_nirf_category`, `_college_resolved`, `_match_confidence`, `_normalized_job_role`, `_is_registered`

Re-derive via `python3 /app/backend/backfill_derived.py` or call `reprocess_matching()`.

## Live Messaging System
- AiSensy WhatsApp (5 campaigns), SMTP Email (Gmail SSL 465)
- TEST_MODE overrides recipients to `TEST_PHONE` / `TEST_EMAIL`
- Workers: OTP Generator, Schedule Link Sender, 24h Reminder, OTP Expiry, Missed Interview

## Changelog
- **May 2026** — Classification rule update (view-based), `/api/data/classification`, camelCase OTP aliases, isTest safety tagging. 14/14 backend tests (iter28).
- **May 2026** — Perf fix: persisted derived fields, DB-level aggregation. 18/18 tests (iter27).
- **Apr 2026** — Atlas DB swap, live messaging + background workers, registration UI clone, global Back Button.

## Prioritized Backlog
- **P1** — Fix AiSensy API key (401)
- **P2** — Upload History view
- **P2** — Advanced chart visualizations
- **P2** — Role-based access control (Admin vs Recruiter)
- **P2** — Refactor `/api/role` to use persisted fields
- **P3** — Upgrade Atlas tier if further data duplication is needed
- **P3** — Move routes → `/app/backend/routes/`, models → `/app/backend/models/`

## Feature Flags (.env)
`ENABLE_WHATSAPP`, `ENABLE_EMAIL`, `TEST_MODE`, `TEST_PHONE`, `TEST_EMAIL`, `MONGO_URL`, `DB_NAME`, `JWT_SECRET`, `SMTP_*`
