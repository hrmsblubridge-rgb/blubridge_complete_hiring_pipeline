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
- **Feb 2026 (iter47)** — Score Import Sync + WhatsApp Template + Domain-Agnostic URLs:
  - **Imported rounds → bb_rounds**: `POST /api/bb/import-scores/confirm` now upserts each distinct round name from the imported file into `bb_rounds` (case-insensitive dedupe; restores soft-deleted rounds; tags `source: "imported"`). Frontend tabs/cards UI surfaces them automatically alongside manually-created rounds. Zero / empty / non-numeric scores are skipped per spec.
  - **Update modal data source**: `/api/bb/attended-for-scores` already returns merged rounds — no change needed; modal now reflects manual + imported rounds correctly.
  - **WhatsApp `Candidate FollowUp` template**: 4 → **5 params** `[name, role, formattedDate, time, schedule_link]`. Updated `messaging.notify_missed_reminder`. Campaign name unchanged.
  - **Registration form URLs domain-agnostic**: `HiringForms.js` already uses relative `/register/{slug}` (works on any host). Added a **Copy** button that builds the absolute URL at runtime via `window.location.origin` (`xyz.com/register/ai-ml`, `abc.com/register/ai-ml`, etc.). DB stores only the slug — no full URL persisted.
  - 15/15 regression tests pass (iter44 + iter45 + iter47). No live data touched.
- **Feb 2026 (iter46)** — Bulk Upload UX improvements:
  - **Live row-count progress** during processing — worker writes `progress = {processed, total, percent}` to the queue doc every 200 rows; status endpoint surfaces it; frontend modal renders an animated progress bar (`247 / 5,000 rows · 4%`) with auto-polling every 1.5s while a job is active. Verified live: `200/5000 → 400/5000 (4% → 8%)` updates in ~15s.
  - **Real upload errors surfaced** — frontend `BulkUploadModal` now shows the actual server error (`Upload failed: 413 Payload Too Large`, `Upload failed: 401 Unauthorized`, etc.) instead of a generic "Upload failed" toast. Adds 5-min axios timeout for large multi-file uploads + soft warning toast for files >50 MB.
  - All 13 prior regression tests (iter44 + iter45) still pass.
- **Feb 2026 (iter45)** — Exact Score Mapping with Round Detection (Email + Phone matching):
  - `bb_modules._build_round_wise_scores(email, phone, pick='latest'|'highest'|'lowest')` groups all `score_sheet` entries by canonical round name; picks one entry per round per the rule.
  - `bb_modules._norm_round` canonicalises aliases (Technical 1 → Round 1, HR Interview → HR Round, Final Discussion → Final Round, Accounts1 → Accounts 1, Mensa Org variants).
  - **NEW endpoint** `GET /api/bb/candidate-score-summary?email&phone&pick=` returns `{round_wise_scores, latest_round, latest_score, total_score, rounds, conflict}`.
  - `GET /api/bb/attended-for-scores` now also includes `round_wise_scores`, `latest_round`, `latest_score`, `total_score` per row (legacy `scores[]` preserved for backward compat).
  - `POST /api/upload/scoresheet` rewritten to **non-destructive smart upsert** — per (email-or-phone, canonical round) it only overwrites older/missing records. Same-phone-different-email rows are flagged + skipped. Returns `{inserted, updated, skipped_newer, skipped_conflict}`.
  - `PUT /api/bb/applicant-score/{email}` merges new scores with existing (per canonical round) instead of replacing the whole list.
  - One-time dedupe script `/app/backend/dedupe_score_sheet.py` collapses legacy duplicate score rows. Dry-run identified 998 distinct (candidate, round) groups in 3514 records → ~2516 duplicate rows ready to remove.
  - 7/7 regression tests pass — `tests/test_iteration45_score_matching.py`. Iter44 13/13 pass overall.
- **Feb 2026 (iter44)** — Smart Candidate Matching + Legacy Data Fix:
  - `bb_modules._resolve_candidate_extras(email, phone)` reads `bb_registrations` then `naukri_applies` to fill `college_type`, `source`, `college` when `pipeline_data` lacks them. Used by `/api/bb/verify-otp` as a runtime fallback (read-only, no DB write).
  - VerifyOTP success card now shows `College`, `College Type`, `Source` — N/A only when no source has the data.
  - `register_applicant` + `register_college_applicant` upsert into `pipeline_data` with NON-DESTRUCTIVE merge: profile fields (name, college, college_type, source, etc.) are preserved on existing records; only DYNAMIC fields (job_role, schedule_*, last_update) update. New records get the full payload.
  - One-time backfill script `/app/backend/backfill_pipeline_extras.py` (dry-run by default; `--apply` to commit). Skips email↔phone conflicts after de-duping comma-joined legacy emails.
  - 6/6 regression tests pass — `tests/test_iteration44_smart_matching.py`.
- **May 2026 (iter41)** — Bulk Upload pipeline fully rebuilt: (a) per-row `update_one` in `reprocess_matching()` replaced with `bulk_write` chunks of 1000; (b) deferred `reprocess_matching()` runs via `asyncio.create_task` (fire-and-forget) with single-flight `asyncio.Lock`; (c) phantom `error: 'Invalid upload_type'` writer bypassed via private `status='queued'` + `owner='e1_recruitment_app'` discriminator and atomic `find_one_and_update` claim; (d) detailed stage logging at upload/parse/process/move/complete; (e) `POST /api/bulk-upload/{type}/clear-failed` endpoint to clean stale failed rows. **Test result: 14/14 PASS (iter41)**.
- **May 2026 (iter41)** — Hiring Form: new "Show Instruction Page?" radio (Yes/No, default No) below "Job description attached?". When Yes + non-empty content, public registration redirects to a customizable Instruction Page (HTML allowed) with Continue button, then proceeds to result. Saved on `bb_hiring_forms.show_instruction_page` + `instruction_content`. Returned by `GET /api/pub/form/{slug}`.
- **May 2026 (iter41)** — Messaging: OTP worker now uses **IST (UTC+5:30)** consistently (`_local_now()` helper), respects [interview-3h, interview-1min] window incl. short-notice (interview within 3h). Continuous rejection mailer (every 60s) for any `bb_applicant_updates.status='Rejected'` post-MESSAGING_CUTOFF_TS, idempotent via `rejection_notified` flag. `verify-otp` now also updates `pipeline_data.status='Attended'` + `otp_verified='1'` so "View Attended Applicants" / counts stay consistent.
- **Feb 2026 (iter35)** — Slug-based registration URLs (`/register/ai-ml`) + Candidate Evaluation Engine: structured response `{status, reason, message, showSchedule, scheduleLink}` with reasons `AGE | GRADUATION_YEAR | LOCATION | GENERAL`; instant Email + WhatsApp post-evaluation (workers remain as fallback); dynamic frontend result page with reason-specific copy + Schedule Interview CTA. Backward compat: ObjectId URLs still work. 8/8 pytest + frontend E2E PASS.
- **May 2026** — Classification rule update (view-based), `/api/data/classification`, camelCase OTP aliases, isTest safety tagging. 14/14 backend tests (iter28).
- **May 2026** — Perf fix: persisted derived fields, DB-level aggregation. 18/18 tests (iter27).
- **Apr 2026** — Atlas DB swap, live messaging + background workers, registration UI clone, global Back Button.

## Prioritized Backlog
- **P1** — Add explicit form flag (e.g. `conditions.show_aiml_interstitial`) instead of role string parsing in PublicRegistration.js (currently brittle)
- **P1** — Refactor `bb_modules.py` (1540 lines) → split into `bb_pub_register.py`, `bb_slug.py`, `bb_hiring_forms.py`
- **P1** — Hard-require `FRONTEND_URL` env at startup (Schedule link breaks if missing)
- **P1** — Fix AiSensy API key (401)
- **P2** — Configure dedicated AiSensy WhatsApp templates per rejection reason (currently all rejections share one Reject template)
- **P2** — Upload History view
- **P2** — Advanced chart visualizations
- **P2** — Role-based access control (Admin vs Recruiter)
- **P2** — Refactor `/api/role` to use persisted fields
- **P3** — Upgrade Atlas tier if further data duplication is needed
- **P3** — Move routes → `/app/backend/routes/`, models → `/app/backend/models/`

## Feature Flags (.env)
`ENABLE_WHATSAPP`, `ENABLE_EMAIL`, `TEST_MODE`, `TEST_PHONE`, `TEST_EMAIL`, `MONGO_URL`, `DB_NAME`, `JWT_SECRET`, `SMTP_*`
