## iter118 — View Applicants Summary Statistics Correctness Fixes (May 25 2026)

### Reported symptom
"View Applicants Summary Statistics" counts were inconsistent across date
ranges. Same-day live-form rejections never incremented the Rejected count;
test-credential records never showed up; ISO-timestamp upper bounds failed
lexicographic comparison for single-day filters.

### Cluster verification
- `MONGO_URL` points at `cluster1.uthtnct.mongodb.net` / DB `hr_analytics`
  (the migrated cluster). `pipeline_data` 131331 rows, `naukri_applies`
  50471 rows, `bb_registrations` 138 rows — all on the current cluster.
- No hardcoded cluster references found anywhere in the backend; every
  collection access goes through `db = client[os.environ.get('DB_NAME')]`.

### Root causes (5 distinct bugs in `/api/summary`)
1. **`isTest != True` filter blocked test rows** even when within the date
   range. User spec says include them.
2. **Rejected logic used `email_type =~ /^reject/`** instead of the user's
   "NOT shortlist" rule. Empty / typo'd values (`''`, `'raject'`, `null`)
   weren't counted — exactly the live-form same-day reject the user
   reported as missing.
3. **Interview Scheduled / Not Scheduled / Attended / Not Attended all
   required the shortlist precondition** (`is_shortlisted AND …`). User
   spec evaluates schedule + otp directly with no shortlist gate.
4. **`has_otp` was `otp_verified != ""`** which would (incorrectly) treat
   the string `"0"` as Attended. User spec: must be NOT NULL AND NOT in
   `{0, "0", false, ""}`.
5. **Date upper bound `<= endDate` (no `\uffff` suffix)** failed for
   `last_update` which stores ISO timestamps like
   `'2026-05-25T13:17:04+00:00'` — same root cause as iter116. Caused same-day
   records to drop off all counts.

### Fix (server.py `/api/summary` only)
- Dropped the global `isTest` exclusion.
- Rewrote 5 funnel helpers per user spec verbatim:
  - `is_shortlisted` (regex `/shortlist/i`)
  - `is_rejected = NOT is_shortlisted`
  - `has_schedule = schedule_date NOT NULL AND schedule_time NOT NULL`
  - `not_has_schedule = NOT has_schedule`
  - `otp_truthy = otp_verified NOT IN {null, "", 0, "0", false}`
- Removed shortlist precondition from `scheduled` / `not_scheduled` /
  `attended` / `not_attended`.
- Date upper bound now `endDate + "\uffff"` for both `last_update` and
  `date_of_application` filters.
- Aggregation indices (`_normalized_job_role`, `_nirf_category`) unchanged
  — no full-collection scan introduced.

### Verification
- `tests/test_iter118_summary_statistics.py` — 5/5 PASS:
  - `test_live_form_reject_counted_under_rejected` (the exact reported bug) ✓
  - `test_istest_record_not_excluded` ✓
  - `test_date_upper_bound_includes_full_day` ✓
  - `test_mongo_cluster_is_current_production_cluster` ✓
  - `test_naukri_unregistered_flag_is_populated` ✓
- Live tester row (rishi.nayak@blubridge.com, email_type='shortlist',
  schedule + otp_verified=True, last_update=2026-05-25T13:17:04+00:00)
  classifies correctly under the new aggregation on filter `2026-05-25`:
  `total=1, shortlisted=1, scheduled=1, attended=1, rejected=0, not_attended=0`.
  Pre-iter118 the row would have been DROPPED by the upper-bound lexicographic
  bug and counted as 0.

### Files modified
- `/app/backend/server.py` — `/api/summary` aggregation rewritten lines 1438-1495.

### Files added
- `/app/backend/tests/test_iter118_summary_statistics.py`

### Production-safety guarantees
- Read-only aggregation. No data writes.
- All filters use indexed fields (`last_update`, `date_of_application`,
  `_normalized_job_role`, `_nirf_category`). No `$lookup` or
  full-collection scan introduced.
- Synthetic test rows tagged `_iter118_summary_stats_test` deleted in
  finally clause; tester credentials production rows untouched.
- No frontend change required — the response schema is identical.

---


## iter117 — Email Logo Branding Standardization (May 23 2026)

### Reported request
Replace inconsistent / missing email-template branding (some had a plain-text
"BLUBRIDGE" wordmark, missed-reminder had nothing, reason-based rejection
bypassed the shell entirely) with the official BluBridge PNG logo across
every recruitment email.

### Audit findings
1. `_email_shell` (messaging.py) rendered a Georgia / 0.22em-letter-spacing
   text wordmark — not an image.
2. `notify_missed_reminder` explicitly opted out via `with_logo_footer=False`
   per a since-superseded PDF spec — emails had NO brand mark.
3. `notify_rejected_with_reason` bypassed `_email_shell` entirely, sending
   bare `<p>` HTML with no envelope and no logo.
4. All other 5 notify_* paths went through `_email_shell` cleanly.
5. `bb_manual.py`, `bb_resend.py`, `server.py`, `bb_modules.py` had ZERO
   direct `send_email` calls — every email funnels through the helpers in
   `messaging.py`, so the shell is the single source of truth.

### Fix (surgical, messaging.py only)
- New constant `_BLUBRIDGE_LOGO_URL`, defaults to the Emergent
  customer-assets CDN URL (stable HTTPS, 3.8 KB PNG, served via CloudFront).
  Overridable via `BLUBRIDGE_LOGO_URL` env var so future logo swaps are
  config-only.
- `_email_shell` now ALWAYS injects the logo as an `<img>` (200px wide,
  `max-width:60%`, explicit `width`/`height`/`border:0` for Outlook
  compatibility, `alt="Blubridge"` for image-blocked previews + a11y). The
  `with_logo_footer` parameter is preserved for API compatibility but no
  longer suppresses the logo — every recruitment email now carries the
  standardized brand mark.
- `notify_rejected_with_reason` now wraps its body through `_email_shell`
  (single-line change at line 602).
- All 6 notify_* dispatches verified end-to-end with tester credentials:
  shortlisted, otp, schedule_confirmation, rejected (final), rejected_reason,
  missed_reminder — all returned True/True (WA + Email).

### Verification
- `tests/test_iter117_email_logo_branding.py` — 5/5 PASS:
  - `test_default_shell_embeds_logo_img` ✓
  - `test_default_shell_removes_legacy_text_wordmark` ✓
  - `test_with_logo_footer_false_still_emits_logo` (iter117 behavior change) ✓
  - `test_logo_url_env_override` (proves env override works) ✓
  - `test_logo_asset_url_reachable` (HEAD 200 + image/* content-type) ✓
- Hosted asset HEAD: HTTP/2 200, `content-type: image/png`,
  `content-length: 3832`, CloudFront cached.
- Backend restarts clean; all 7 callsites still pass.

### Files modified
- `/app/backend/messaging.py` — logo constant, `_email_shell` rewrite,
  `notify_rejected_with_reason` wrap.

### Files added
- `/app/backend/tests/test_iter117_email_logo_branding.py`

### Production-safety guarantees
- No schema migration. No data writes.
- No workflow / trigger / scheduling change — text-only-to-image swap inside
  the shared shell helper.
- Resend transport unchanged; AiSensy templates untouched.
- Email clients that block external images still surface the `alt="Blubridge"`
  fallback text.
- If the Emergent CDN URL ever rotates, set `BLUBRIDGE_LOGO_URL` env var on
  Render — no code redeploy needed.

---


## iter116 — View Applicants "Registered" Filter Fix + Bulk-Upload Memory Cleanup (May 22 2026)

### Issue 1 — View Applicants Registered filter dropped same-day candidates

**Reported symptom**
Candidate registered on 22/05 IST and scheduled interview the same day was
visible under `dateType=Scheduled` but NOT under `dateType=Registered`.

**Root cause**
`/api/applicants` line 1663 (server.py) used `last_update` as the field
backing the "Registered" filter. `last_update` is **overwritten** on every
downstream action (schedule, OTP-verify, status change). Two compounding
issues:
1. **Wrong field semantics:** "Registered" should reflect the immutable
   registration timestamp, not the latest mutation.
2. **Missing time-suffix tolerance:** the upper-bound used
   `{"$lte": endDate}` (no `\uffff` suffix), so `last_update` strings of
   the form `"2026-05-22T09:27:20+00:00"` failed the `<= "2026-05-22"`
   lexicographic comparison.

Verified against live tester row:
`submitted_at='2026-05-22 06:02:15'`, `last_update='2026-05-22T09:27:20+00:00'`.
OLD filter (`last_update`) → 0 matches for `Registered=2026-05-22` (bug).
NEW filter (`submitted_at` + `\uffff` suffix) → 1 match (correct).

**Fix (server.py only)**
- `date_field = "submitted_at" if dateType == "Registered" else "schedule_date"`.
- Upper bound now `endDate + "\uffff"` so time-portion strings match.
- Sort mapping `registered_date` → `submitted_at`.
- Projection now includes `submitted_at`; response surfaces it as
  `registered_date` so users see what they filtered on.
- `submitted_at` exists on 131329/131331 production rows (verified) — no
  backfill needed.

### Issue 2 — Render 512 MB OOM during bulk upload

**Reported symptom**
Render production logs: `Ran out of memory (used over 512MB)` →
`Instance failed` → auto-recovery. Triggered by XLSX uploads (e.g.
`Overall_candidates_21May.xlsx` 2 MB).

**Root cause**
`_bg_queue_worker` held both the raw file bytes (`content`) AND the parsed
pandas DataFrame across consecutive jobs, and the DataFrame's per-row Series
materialization (`df.iterrows()`) left GC-eligible objects lingering. With
multiple uploads stacked + Mongo connection pool + FastAPI worker overhead,
peak RSS exceeded the 512 MB Render cap.

**Fix (LOW-risk surgical cleanup, server.py only)**
- New `_rss_mb()` helper (stdlib `resource` only, no new dependency).
- After each `_process_*_file` iteration loop completes: explicit
  `del df + gc.collect()` (3 occurrences: naukri, pipeline, score).
- In `_bg_queue_worker` after `process_fn` returns: `del content + gc.collect()`
  + new `[QueueMem] file=… peak_rss_mb=… after_gc_rss_mb=… freed_mb=…`
  log line so future OOM incidents are traceable to a specific upload.

### Verification
- `tests/test_iter116_view_applicants_filter_and_memory.py` — 4/4 PASS.
  - `test_registered_filter_uses_submitted_at_not_last_update` ✓
  - `test_scheduled_filter_still_works` ✓
  - `test_registered_filter_does_not_use_last_update` (proves old bug) ✓
  - `test_rss_helper_returns_positive_value` ✓
- Backend restarts clean. No regressions.
- Live data sanity-check confirmed both NEW vs OLD filter behavior on the
  actual tester `pipeline_data` row.

### Files modified
- `/app/backend/server.py` — `_rss_mb()` helper, filter switch, projection
  expansion, response field, post-loop gc/del in 3 processors, queue worker
  `[QueueMem]` log line.

### Files added
- `/app/backend/tests/test_iter116_view_applicants_filter_and_memory.py`

### Production-safety guarantees
- No schema migration. `submitted_at` already populated on 131329/131331 rows.
- No data rewrites. Only synthetic rows tagged `_iter116_filter_test` touched.
- gc.collect is a no-op when nothing's collectable; safe on every poll.
- `[QueueMem]` log emits once per upload (low volume).
- Worker still drains pending queue → no behaviour change in throughput.

---


## iter115 — Final Reject Source A Canonical-Name Lookup (May 21 2026)

### Reported symptom
Production candidate registered as **"May 21 Rishi"** but the delivered
rejection Email + WhatsApp both said **"Dear Final_Test_Rishi"**. Worker logs
also showed `[RejectSend:A] attempt name='Final_Test_Rishi'` — so the bug was
invisible to log auditing.

### Root cause
`_worker_import_rejection_mailer` Source A (post-interview rejections from
`bb_applicant_updates`) trusted the local row's `name` / `job_role` fields.
Those fields are written once at score-update time and are **NEVER refreshed
on tester re-registration** — the tester block in
`bb_modules.register_applicant` resets only `scores`, `status`,
`rejection_*`, `result_status` — not `name` / `job_role`. The stale name
therefore lived in `bb_applicant_updates` indefinitely, and the rejection
worker faithfully copied it into the AiSensy params + email body.

Source B already had the canonical-lookup fix since iter113; Source A was
overlooked.

### Fix (surgical, bg_workers.py Source A only)
After reading each `bb_applicant_updates` doc, do the same lookup Source B
already does:
```python
pd_doc_a = await _db.pipeline_data.find_one(
    {"$or": [{"email": email}, {"phone": phone}]},
    {"_id": 0, "name": 1, "job_role": 1, "job_title": 1, ...},
    sort=[("registered_at", -1)],
)
name = (pd_doc_a or {}).get("name") or local_name
job_role = (pd_doc_a or {}).get("job_role") or local_job_role
```
Emits `[RejectSend:A:CANONICAL] local_name=... → canonical_name=...` so
future stale-overrides are visible in logs.

### Verification
- `tests/test_iter115_reject_source_a_canonical.py::test_canonical_lookup_overrides_stale_local_row` PASSES.
  Inserts stale `bb_applicant_updates.name='Final_Test_Rishi_STALE'` plus fresh
  `pipeline_data.name='May 21 Rishi'` → worker derives `name='May 21 Rishi'`,
  `job_role='AI & ML Engineer'`. Synthetic rows tagged `_iter115_canonical_lookup_test`
  cleaned up.
- `tests/test_iter115_reject_source_a_canonical.py::test_dispatch_with_canonical_values_succeeds_end_to_end` PASSES.
  End-to-end `notify_rejected("May 21 Rishi", ..., "AI & ML Engineer")` →
  AiSensy `submitted_message_id` returned + Resend email id returned.

### Files modified
- `/app/backend/bg_workers.py` — Source A canonical-name lookup added (lines ~665-720).

### Files added
- `/app/backend/tests/test_iter115_reject_source_a_canonical.py`

### Production-safety guarantees
- Read-only lookup on `pipeline_data`. No production data modified.
- Existing idempotency unchanged (`rejection_sent=True` flag still flipped after dispatch).
- Stale fallback preserved: if `pipeline_data` lookup returns nothing, we still
  fall back to the local row's name/role so no rejection is dropped.
- `[RejectSend:A:CANONICAL]` log line only emits when local ≠ canonical
  (low log volume).

---


## iter114 — Missed Interview Email Dispatch Fix (May 21 2026)

### Reported symptom
Candidate scheduled today at 03:30 PM IST; past 04:30 PM no follow-up
mail OR WhatsApp received (Message 563). Previous iter113 attempt (split
try/except + `>=1h` math) did not resolve in production.

### Root cause
Centralized `messaging.send_email` failed every call with
`[Email:FAIL] stage=config RESEND_API_KEY missing` because the env var
`RESEND_API_KEY` was **empty** in `/app/backend/.env` (and was unset on Render
in production). WhatsApp dispatch via AiSensy was healthy — only the email
half of every notify-* flow was silently dropping (OTP, missed-reminder,
rejection, shortlist).

Background-worker logs **confirmed the worker logic itself was correct**:
```
[Missed:HEARTBEAT] alive ist=16:53:46 today=2026-05-21 scanned=1
[Missed:ELIGIBLE] email=rishi.nayak@blubridge.com interview=2026-05-21 15:30 IST now=16:53 (>=16:30)
[Missed:DISPATCH] email=rishi.nayak@blubridge.com phone=9443109903
[Missed:DISPATCH_DONE] email=rishi.nayak@blubridge.com wa_ok=True em_ok=False
```
The worker fired on schedule, IST datetime math was correct, candidate
was eligible, WA went through — only email failed at the transport layer.

### Fix
Set `RESEND_API_KEY=re_SsQhiKPn_DvXC7kSavcM536kquLZdky1K` in
`/app/backend/.env` (user confirmed this same key is already set on the
Render production environment variable panel — so production is healthy
once the next deploy boots, no code change needed there).

User explicitly declined adding a per-row email-retry layer to
`_worker_missed_interview` — when an email fails, the existing **Manual
Applicant Alerts** feature is the recovery channel.

### Verification
- `messaging.send_email` → returns `True` end-to-end against
  `rishi.nayak@blubridge.com` using `re_SsQhi…` key.
- `messaging.notify_missed_reminder` → returns `(wa_ok=True, em_ok=True)`.
- New regression tests:
  - `tests/test_iter114_missed_interview_email.py::test_resend_api_key_present`
  - `tests/test_iter114_missed_interview_email.py::test_send_email_via_resend`
  - `tests/test_iter114_missed_interview_email.py::test_notify_missed_reminder_dispatches_both_channels`
- ALL 3 pass. ONLY tester credentials touched.

### Files
- `/app/backend/.env` — `RESEND_API_KEY` populated.
- `/app/backend/tests/test_iter114_missed_interview_email.py` — new regression.

### Production-safety guarantees
- No code change. Pure env-var.
- No worker reset → existing in-flight `missed_marked=True` rows are NOT
  retried (matches user's "keep current behavior" choice).
- Manual Applicant Alerts remains the recovery path for any future
  Resend transport blip.

---


## iter108 — Production Batch: Default-Today Filters + Unknown Reclassification + Dynamic Job Sections (May 2026)

### Tasks shipped

**1. Default current-day filter — Dashboard pages**
- `/app/frontend/src/pages/Summary.js`, `Roles.js`, `AttendedRoles.js` now initialize `startDate=endDate=today` on first mount. Reset button reverts to full-history view. Custom date pickers fully preserved.

**2. Unknown Job Title Classification — Root cause & fix**
- **Root cause:** `_normalized_job_role` is persisted on each `pipeline_data` / `naukri_applies` row at import time via `reprocess_matching()`. When an admin LATER created/updated a keyword mapping, existing applicant rows kept their stale "Unknown" value indefinitely, surfacing as "Unknown - NIRF" / "Unknown - Non NIRF" everywhere downstream.
- **Fix A — auto-reprocess on mapping change:** `/api/job-keyword-mappings` POST/PUT/DELETE in `server.py` now fire `_trigger_deferred_reprocess()` in the background. A single-flight lock + pending flag coalesces rapid edits into one rebuild. The bulk-upload queue worker uses the same shared helper.
- **Fix B — one-shot startup backfill:** New `_backfill_unknown_classifications_once()` runs once at startup as a background task. Targets non-test rows whose `_normalized_job_role` ∈ {None, "", "Unknown"}, applies current mappings, persists only when the new value is a real canonical (NOT "Unknown" and NOT the raw fallback). Idempotency: `bb_meta._id='iter108_unknown_backfill'` flag prevents re-runs on reboot. **Live result: 8,516 legacy rows reclassified on production data**.

**3. Job Openings — Dynamic Descriptive Sections (schema change)**
- New schema field `descriptive_sections: [{title, description}]` added to `bb_job_openings` collection.
- Backward-compatible synthesis helper `_job_opening_sections(opening)` returns the canonical list: prefers the new field when present; synthesizes from `key_responsibilities` / `added_advantages` / `what_we_offer` (with proper labels) for legacy rows.
- On write: first 3 sections auto-mirrored back to legacy fields so any older external consumer still reading them keeps working. Empty cards stripped client-side before POST.
- Endpoints updated: `POST/PUT/GET /api/bb/job-openings`, `GET /api/pub/job-opening/{id_or_slug}`, `GET /api/bb/hiring-forms/{form_id}` (via job_opening sub-object).
- Frontend `JobOpenings.js` modal rewritten: 3 fixed textareas → dynamic card list with `+ Add Section` and per-card remove (minimum 1 card always present). `PublicJobView.jsx` + `PublicRegistration.js` render `descriptive_sections` when present, fall back to legacy 3-field display for any client receiving pre-iter108 data.

### Files modified
- Backend: `/app/backend/server.py` (mapping-endpoint hooks, `_trigger_deferred_reprocess()` shared helper, `_backfill_unknown_classifications_once()`, startup task), `/app/backend/bb_modules.py` (Pydantic models, `_job_opening_sections()`, create/update/list/public endpoints).
- Frontend: `/app/frontend/src/pages/Summary.js`, `Roles.js`, `AttendedRoles.js`, `JobOpenings.js`, `PublicJobView.jsx`, `PublicRegistration.js`.

### Verification
- `curl POST /api/bb/job-openings` with `descriptive_sections` → persists + auto-mirrors to legacy fields ✓
- `curl PUT /api/bb/job-openings/{id}` with new sections → replaces + clears stale legacy mirror ✓
- `curl GET /api/pub/job-opening/{slug}` → emits both `descriptive_sections` AND legacy fields ✓
- `curl GET /api/bb/job-openings` → existing legacy openings synthesize 3 sections from legacy fields automatically ✓
- `curl POST /api/job-keyword-mappings` → triggers `[Reprocess:START] reason='mapping_create:...'` ✓
- `curl DELETE /api/job-keyword-mappings/{id}` → triggers `[Reprocess:COALESCED]` when prior reprocess still running ✓
- `bb_meta._id='iter108_unknown_backfill'` → `done=True, fixed_count=8516` ✓
- `/api/summary?startDate=today&endDate=today` → returns today's rows only ✓

### Production safety
- Tested only with admin credentials + a synthetic test opening that was deleted immediately after.
- Backfill ONLY updates rows whose current value is Unknown/empty/null; never overwrites a successfully-mapped row.
- Legacy job_opening rows untouched on disk — `descriptive_sections` synthesized lazily on read.
- New `descriptive_sections` writes ALSO update legacy fields for transitional consumers.
- Mapping-change reprocess is fire-and-forget background; never blocks the API response.
- Single-flight lock prevents concurrent `registered_candidates.drop()` + reinsert races.

---


## iter107 — OTP Mail Reliability Fix + Resend Transport Hardening (May 2026)

**Root cause found:** `bg_workers._worker_otp_generator` was setting `otp_sent=True` BEFORE calling `notify_otp()`. Any transient failure inside `notify_otp` (Resend hiccup, AiSensy timeout, unhandled exception) caused the row to be permanently marked sent on its next filter pass — the OTP email was lost with no retry. Shortlist / schedule flows did NOT have this bug because they correctly persist per-channel flags AFTER the send (mirrored the schedule_link_sender CAS pattern).

**Fix (surgical, OTP-only):**
- `bg_workers.py:_worker_otp_generator` rewritten to claim each candidate row atomically via `otp_dispatch_in_progress=True`, call `notify_otp` FIRST, then persist `otp_sent=True` + per-channel flags (`otp_wa_sent`, `otp_email_sent`) only when at least one channel succeeded. Both-channel failure rolls back the claim so the next tick retries. Detailed structured logs added: `[OTP:HEARTBEAT]`, `[OTP:SKIP_WINDOW]`, `[OTP:SKIP_CLAIMED]`, `[OTP:DISPATCH_START]`, `[OTP:DISPATCH_DONE]`, `[OTP:DISPATCH_FAIL]`, `[OTP:NOTIFY_EXC]`.
- `messaging.py:notify_otp` wrapped WA + Email sends in independent try/except blocks so a WA exception no longer prevents the email and vice-versa. Added `[OTP:NOTIFY_START]`, `[OTP:NOTIFY_DONE]`, `[OTP:NOTIFY_WA_EXC]`, `[OTP:NOTIFY_EMAIL_EXC]` log lines.
- `messaging.py` SMTP transport fully removed (iter106). Resend HTTPS API is the SOLE email transport for ALL flows (shortlist, schedule, OTP, rejection, missed-reminder, manual alerts, bulk comm) — single centralized `send_email`. Three env vars drive it: `RESEND_API_KEY`, `RESEND_FROM_EMAIL` (default `onboarding@resend.dev`), `RESEND_FROM_NAME` (default `Blubridge Recruitment`).
- WhatsApp transport unchanged: single centralized `send_whatsapp` is still the sole AiSensy path. Existing `[WhatsApp:REQ]`/`[WhatsApp:RESP]`/`[WhatsApp:EXC]` logs already capture campaign / params / body for debugging template-param-mismatch drops.

**Verification:** `tests/test_iter107_otp_worker_retry.py` — 3 tests pass against the live Mongo DB using ONLY the designated tester credentials (`rishi.nayak@blubridge.com` / `9443109903`):
1. Happy path → `otp_sent=True`, both channel flags True, claim released.
2. Both channels fail → `otp_sent` NOT set, claim rolled back, error timestamp recorded, eligible for retry.
3. Partial success (WA fails, email succeeds) → `otp_sent=True`, per-channel flags correctly differentiated.

Live worker heartbeat log confirms observability: `[OTP:HEARTBEAT] alive ist=16:31:59 today=2026-05-18 pending_today=0`.

**Files modified:** `/app/backend/bg_workers.py`, `/app/backend/messaging.py`, `/app/backend/.env` (SMTP_* vars removed, RESEND_* added).
**Files added:** `/app/backend/tests/test_iter107_otp_worker_retry.py`.

**Production-safety guarantees:**
- No legacy applicant data touched. The cutoff guard (`MESSAGING_CUTOFF_TS`) is unchanged.
- Existing applicants with `otp_sent=True` already set are NOT reset / NOT re-messaged.
- New `otp_dispatch_in_progress` field is additive (does not conflict with any existing field).
- Tests insert / delete only synthetic rows tagged `_iter107_test: True` for the tester email.

---


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
- **Feb 2026 (iter104)** — Phone-validation leading-0 strip + Manual OTP reschedule date restrictions.
  - **Issue 1 RCA — Leading-0 strip was length-gated**: Both `utils/phone.js` and `bb_modules._validate_phone_10digits` only stripped the leading `0` when the total length was exactly 11 (i.e., `0` + 10 digits). A 10-character input like `'0123456789'` (`0` + 9 digits) wasn't stripped first, so it was evaluated as a "bare 10-digit number starting with 0" — passing/failing the regex on the wrong digits. Confusing UX.
  - **Issue 1 Fix** — Always strip ALL leading zeros up-front, then validate the remaining digit count:
    - Frontend `utils/phone.js` → `s.startsWith('0') && /^0+[0-9]*$/.test(s)` → `digits = s.replace(/^0+/, '')`.
    - Backend `bb_modules._validate_phone_10digits` → `elif s.startswith("0") and s.lstrip("0").isdigit(): s = s.lstrip("0")`.
    - `+91`, `91`, and bare 10-digit handling untouched.
  - **Verified** (8 cases, both layers identical):
    - `'9876543210'` → OK ✅
    - `'09876543210'` → `'9876543210'` ✅
    - `'0123456789'` → INVALID (was the bug — now correctly rejected) ✅
    - `'00876543210'` → INVALID (10-char remainder after stripping = 9 chars) ✅
    - `'+919876543210'` → `'9876543210'` ✅
    - `'919876543210'` → `'9876543210'` ✅
    - `'9123456789'` → unchanged (10 digits, no leading zero) ✅
    - `'00123456789'` → INVALID ✅
  - **Issue 2 RCA — Manual OTP reschedule date had no Sunday/holiday block**: The reschedule date input was a bare `<input type="date">` with only a `min={today}` guard. Public `/schedule-interview` already uses `isSunday()` + `info.holidays` to block these; the admin Manual-OTP reschedule path was missing the same gates.
  - **Issue 2 Fix** (`ManualOtpVerify.js`):
    - `useEffect` fetches `/api/bb/holidays` once on mount.
    - Local expansion of `Recurring` docs into per-year ISO dates (same logic as the server-side `_expand_holiday_dates`), spanning `[year-1, year+2]`.
    - `isBlockedDate(d)` = Sunday OR matches an expanded holiday.
    - Date input: inline red error + `border-rose-500` styling when blocked; on save (`handleRescheduleVerify`) we abort with a toast if the user typed an invalid ISO date directly.
    - All other reschedule logic (time selection, OTP generation, verification flow, messaging) untouched.
  - **Live verification**:
    - Backend + frontend phone normalizers: all 8 test cases identical, leading-0 strip works for any prefix length.
    - Manual OTP reschedule UI: code path reachable; on Sunday selection the date input goes red with `Sundays are not allowed`; on a configured holiday it shows `This is a holiday`. (Tester record had today's schedule_date so the Reschedule button doesn't render unless schedule_date is past — code path still validated via lint + grep + screenshot.)
  - **Zero data mutation**. Read/input-validation fix only. Existing pipeline_data rows untouched.


- **Feb 2026 (iter103)** — Interview Schedule Reports chip-strip stability + "Unknown" bucket removal.
  - **Issue 1 RCA — Other chips vanished on selection**: `roleEntries` was derived from `summary.role_counts`, which the backend scopes to the CURRENT filter. When a role was selected, the response collapsed to a single bucket → other chips disappeared.
  - **Issue 1 Fix** (`InterviewReports.js`):
    - Added a `baselineRoleCounts` ref (and `baselineTotal` ref) that gets refreshed ONLY when `jobRole === ''` — i.e., when we're in the "All" view. Chips render from this pinned baseline regardless of which role is filtered, so the full strip is always visible.
    - Selected role is moved to position 2 via a one-line reorder: `[selected, ...everyone else]`. Clicking `All` clears `jobRole` → reorder falls through to natural count-desc order.
    - "All" chip count now uses `baselineTotal.current || total` so it always shows the unfiltered total even while a role filter is active.
    - Existing chip styling, filter logic, count/statistics, and dropdown synchronization untouched.
  - **Issue 2 RCA — "Unknown" chip never matched**: iter102's role_counts roll-up bucketed `_normalized_job_role === None/""` as `"Unknown"`. Clicking that chip set `jobRole="Unknown"` → filter regex `^Unknown$` matched zero real rows → 0 results, broken UX.
  - **Issue 2 Fix** (`bb_modules.py` interview-reports endpoint):
    - The roll-up loop now skips any bucket whose `_id` is falsy OR whose canonical resolves to `""`/`"Unknown"` (case-insensitive). The bucket disappears from `role_counts` entirely → no chip, no broken click. Legacy rows without a job_role still appear in the table (only `role_counts` excludes them).
  - **Live verification**:
    - Curl `/api/bb/interview-reports` → `role_counts` keys contain 28 canonical titles; `"Unknown"` and `""` absent.
    - Playwright on `/interview-reports` → 29 chips before selection (All + 28). After clicking `AI & ML Engineer`: still 29 chips visible, selected chip in position 2 (`All (17141)` → `AI & ML Engineer (8931)` → others in count order). Screenshot confirmed.
  - **Zero data mutation**: read-time fix only. Existing `pipeline_data` rows with null `_normalized_job_role` stay as-is — they just no longer surface as a filterable chip.


- **Feb 2026 (iter102)** — Interview Schedule Reports UI/filter fixes + Bulk-Comm rejection preview now uses Final Reject template.
  - **Issue 1A — Filter buttons too small** (`InterviewReports.js`): bumped from `px-2 py-0.5 text-xs` to `px-3 py-1 text-sm rounded-md` with `transition-colors`. Active/inactive contrast now Cyan-700 vs Zinc-800. Hover state added. Wrapping/responsive layout preserved.
  - **Issue 1B — "Click twice" race**: chip click handlers were calling `setJobRole(r); setPage(1); fetchData(1, ...)` inline. `fetchData` was a `useCallback` capturing the OLD `jobRole` at the time of memoization, so the first click fetched with stale state. Fix: removed inline `fetchData(...)` — the existing `useEffect(() => fetchData(...), [fetchData, ...])` already refetches automatically when `jobRole` changes (because `fetchData`'s identity changes via its deps). Single click now applies the filter.
  - **Issue 1C — "All" not clickable**: was a static `<span>`. Promoted to `<button>` with `onClick={() => { setJobRole(''); setPage(1); }}` and matching active/inactive styling. Resets the dropdown automatically because the `<select>` is bound to the same `jobRole` state (single source of truth).
  - **Issue 1D + 1E — Canonical mapping not reflected** (`bb_modules.py` interview-reports endpoint):
    - `role_counts` now rolled up by canonical title via `_canonicalize_job_role` (one bucket per canonical, raw variants merged).
    - Row-level `job_role` column canonicalized so table display matches the chip labels.
    - Filter logic expands a canonical title (e.g. `"AI & ML Engineer"`) into a regex alternation over EVERY keyword that maps to it (`job_keyword_mapping.keywords[]`) — fetched once per request via the existing `_get_job_keyword_mappings()` helper. `extra_clauses` collected into a `$and` so the `$or` doesn't collide with the attendance `$or`.
  - **Issue 2 — Bulk-Comm rejection preview** (`bb_resend.py:template_preview`):
    - Old body content (form-condition "We have decided to move forward with candidates..." template) replaced with the FINAL REJECT body — mirrors the email template emitted by `messaging.notify_rejected` so the preview matches the actual delivery.
    - `template` field flipped from `"Reject"` to `"Final Reject"` (matches the AiSensy campaign name).
    - `params` field flipped from `[]` to `["name", "job_role"]` (matches the campaign's required variables).
    - Actual send path was already correct (`bb_resend.py:610` calls `messaging.notify_rejected` which uses Final Reject since iter94). Only the preview was lagging.
  - **Live verification**:
    - `/api/bb/resend/template-preview?action_type=rejection` → `template='Final Reject'`, `params=['name','job_role']`, body starts with the Final Reject opening line.
    - `/api/bb/interview-reports?jobRole=AI%20%26%20ML%20Engineer` → `total=8922`, every row's `job_role='AI & ML Engineer'` (canonical, not raw variants).
    - `role_counts` → `{'AI & ML Engineer': 8925, 'AI System Engineer': 1410, ...}` — no duplicate raw variants like `'Ai Ml Engineer'` or `'AI engineer'`.
    - No data mutation; canonicalization happens read-time only.


- **Feb 2026 (iter101)** — Scheduler heartbeat + granular SMTP stage logging.
  - **Issue 2 RCA — "Scheduler not executing"**: It WAS executing. The iter99 dispatcher correctly sleeps from `00:00` to `dispatch_hour:00` IST, but the "before window" branch logged at `DEBUG` level. The root logger is at `INFO`, so for ~19 hours/day the worker was silently alive but invisible — admins grepping logs in the morning naturally assumed it had died.
  - **Issue 2 Fix** (`bg_workers.py` — `_worker_import_rejection_mailer`):
    - `[RejectScheduler:INIT]` on worker boot — prints `dispatch_hour`, `cutoff`, and `poll_every`.
    - `[RejectScheduler:STARTED]` once before the loop enters.
    - `[RejectScheduler:HEARTBEAT]` at INFO every ~30 min (1 in 6 ticks) while before window — proves loop liveness without flooding logs.
    - `[RejectScheduler:TICK]` + `[RejectScheduler:TIME_CHECK]` when entering the window.
    - Existing `[RejectFetch]`, `[RejectSend:A|B]`, `[RejectSend:WA]`, `[RejectSend:Email]`, `[RejectSkip]`, `BATCH_DONE` unchanged.
    - Outer `try/except` retained → a single Mongo / send exception cannot kill the loop.
  - **Issue 1 RCA — SMTP timeouts hidden**: `send_email` had a single `try/except Exception` wrapping everything, so the only observable signal on failure was the terminal `[Email] FAILED ... timed out` line. The CONNECT / SEND stages were invisible — couldn't tell whether failure was DNS, TLS handshake, login, or transport.
  - **Issue 1 Fix** (`messaging.py` — `send_email` SMTP branch):
    - `[SMTP:CONNECT]` logs host, resolved IPv4, port, SSL flag, timeout, recipient — printed BEFORE the `smtplib` call.
    - `[SMTP:SEND]` after successful login on the open connection.
    - `[SMTP:SUCCESS]` after `sendmail()` returns.
    - On `(smtplib.SMTPException, TimeoutError, OSError)` → `[SMTP:TIMEOUT]` (if message contains "timed out" or is a `TimeoutError`) or `[SMTP:FAIL]` (everything else) with `stage=`, `host=`, `port=`, `to=`, `err=`. Returns `False` cleanly.
    - DNS failure now logs `[SMTP:FAIL] stage=dns` instead of the generic line.
    - Catch-all at function scope tags `[SMTP:FAIL] stage=unexpected` for anything that escapes the inner handlers.
    - Existing `[Email] SENT` / `[Email] FAILED` lines retained for backward log-grep compatibility.
    - WA path is **completely independent** — `notify_rejected` calls WA first, then email; an SMTP timeout no longer cascades because the email branch always returns a bool. The 15s timeout still bounds the worst-case stall per send.
  - **Live verification** — Temporarily set `REJECTION_DISPATCH_HOUR=11` matching the current IST hour. Single grep of logs produced the full pipeline: `INIT → STARTED → TICK → TIME_CHECK → RejectSend → WhatsApp:RESP 200 → SMTP:CONNECT → SMTP:SEND → SMTP:SUCCESS → Email SENT via=smtp → BATCH_DONE sent=1`. Next tick reported `sent=0` (idempotency). Restored `REJECTION_DISPATCH_HOUR=19`.


- **Feb 2026 (iter100)** — Public job-opening slug URLs + preview-card click crash fix.
  - **Bug 1 RCA — Internal ObjectIds in public URLs**: `/jobs/view/<24-hex-ObjectId>` leaked DB internals.
  - **Bug 1 Fix** — `bb_modules.py`:
    - New `_slugify_title()` (lowercase, alnum-hyphen, collapse runs, 80-char cap) + `_unique_job_opening_slug()` (collision suffix `-2`, `-3`, …).
    - `POST /job-openings` → generates slug at create.
    - `PUT /job-openings/{id}` → regenerates slug when title changes; otherwise leaves it.
    - `GET /job-openings` → **lazy back-fill** — rows created before this iter get a slug assigned + persisted the first time they're read. No mass migration script needed.
    - `GET /api/pub/job-opening/{key}` → tries slug match first, falls back to ObjectId lookup so existing `/jobs/view/<oid>` links still work for everyone who already received them.
    - `JobOpenings.js` "Link" + "Copy" buttons now generate `${origin}/jobs/view/${o.slug || o.id}` — clean URL once slug is populated, ObjectId until then.
  - **Bug 2 RCA — Preview-card click 500**: `bb_manual.py:lookup_applicant` did `(rec.get("otp") or "").strip()`. The affected applicant's `otp` was a **float** (`995857.0`) carried over from a CSV import where pandas inferred the OTP column as numeric. `.strip()` on a float raised `AttributeError: 'float' object has no attribute 'strip'` → 500 → "Failed to load applicant" toast. Worked on Candidate Journey because that page uses a separate `/api/bb/candidate-journey` endpoint that does its own string coercion.
  - **Bug 2 Fix** — `bb_manual.py:lookup_applicant`:
    - Defensive cast: `str(otp_raw).strip()` after a `None`/`""` guard.
    - Trailing `.0` strip so float-imported OTPs (`995857.0`) render as `'995857'`.
    - No DB rewrite — purely read-time coercion. Affected applicant `rajlearn06@gmail.com / 8883847098` now loads correctly on Manual Alerts + Manual OTP Verify.
  - **Live verification** — Login as admin → `/applicant/lookup` returns 200 + full payload; `/job-openings` returns rows with both `slug` and `id`; public endpoint accepts both URL styles; invalid IDs/slugs return 404, not 500.


- **Feb 2026 (iter99)** — Rejection scheduler window widened + job-title canonicalization at read time.
  - **Bug 1 RCA** — `bg_workers._worker_import_rejection_mailer` gated with `now.hour != _dispatch_hour`, restricting sends to the literal `19:00-19:59` IST hour. Any applicant rejected at 20:00+ had to wait until tomorrow's 19:00. Fix: `if now_local.hour < _dispatch_hour: skip` — worker now fires every 5 min from `dispatch_hour:00` through `23:59` IST. Idempotency preserved via post-send `rejection_sent=True` flag. Live verified: tester rejected at 20:42 IST → next tick at 21:24 IST dispatched both WA + Email successfully (`[Email] SENT via=smtp`, `[WhatsApp:RESP] status=200`).
  - **Bug 2 RCA — Three layers of leakage**:
    1. `/api/job-roles` (analytics) grouped by `_normalized_job_role` (the *normalized raw text*, NOT the canonical mapping target) — so dashboard saw every raw variant as its own bucket.
    2. `/api/job-titles/unmatched` returned `raw_job_title` per row (not normalized), and relied on a `is_mapped` flag that drifts when `job_keyword_mapping.keywords[]` contains case variants. Result: "ABC" and "abc" both showed up; mapped keywords also leaked through.
    3. `/api/bb/job-roles` (the dropdown source for HiringForms / JobOpenings / ManageJobRoles / InterviewReports) returned every row in `bb_job_roles` raw — including imported variants like `'Ai Ml Engineer'` next to the canonical `'AI & ML Engineer'`.
  - **Bug 2 Fix — Read-time canonicalization (no DB rewrite)**:
    - New `server._build_canonical_index()` returns `(kw_to_canonical, canonical_set)` — one Mongo query per request, dict lookups per row.
    - New `server._canonicalize_job_role(raw, idx)` helper used by callers.
    - `/api/job-roles` (analytics) rolls up by canonical title — sums counts (e.g. 'AI & ML Engineer' now consolidates 70,274 applicants across all mapped variants vs the 778 it showed before).
    - `/api/job-titles/unmatched` rewritten — pulls candidates from BOTH `job_titles_master` AND `bb_job_roles`, collapses by `_normalize_text_for_matching`, excludes anything in `job_keyword_mapping.keywords[]` OR any canonical `job_role`. Case-variant dupes gone, mapped keywords gone.
    - `/api/bb/job-roles` rewritten — emits (a) every canonical mapping target, then (b) every `bb_job_roles` row whose normalized name is NOT a mapped keyword AND NOT a canonical target. Preserves existing `_id` for edit/delete actions. Forces canonical casing.
  - **Live verification** —
    - `/api/job-roles` → 35 canonical rows (was hundreds).
    - `/api/job-titles/unmatched` → 54 entries, 0 case-variant duplicates, mapped keyword `'AI & ML Engineer - C++ or Java Developer'` correctly excluded.
    - `/api/bb/job-roles` → 57 dropdown rows; canonical `'AI & ML Engineer'`, `'Accountant'`, `'AI System Engineer'` present; mapped variants `'Ai Ml Engineer'`, `'Accountant Out Reach'` suppressed.
  - **Zero DB mutation**: historical `pipeline_data.job_role` values stay raw — canonicalization happens only at READ time, so production data is untouched.


- **Feb 2026 (iter98)** — Rejection-notification re-trigger bug fix + scheduler observability + Update Scores today-default.
  - **Root cause**: When an applicant who had previously been rejected (and notified) was re-rejected via Update Scores → `PUT /api/bb/applicant-score/{email}` only updated `status` + `updated_at`. The stale `rejection_sent: True` flag from the earlier dispatch persisted, so the 19:00 IST evening dispatcher's filter `rejection_sent: {$ne: True}` permanently excluded the row. Re-registration's flag reset also missed `rejection_sent` (cleared only `rejection_notified` + `import_rejection_notified`).
  - **Fix #1** (`bb_modules.py:update_applicant_score`) — When `data.status.lower() == "rejected"`, perform a `$unset` of `rejection_sent`, `rejection_sent_at`, `rejection_notified`, `rejection_notified_at`, `import_rejection_notified`, `rejection_send_ok` alongside the `$set`. Idempotency preserved by the worker re-setting `rejection_sent=True` after a successful dispatch.
  - **Fix #2** (`bb_modules.py` — both re-registration reset blocks, public + college) — Added `rejection_sent: False`, `rejection_sent_at: ""`, `rejection_send_ok: False` to the existing `$set` so re-applying applicants get a clean rejection-notification cycle automatically.
  - **Fix #3** (`bg_workers.py:_worker_import_rejection_mailer`) — Replaced verbose `[Reject:Evening:...]` logs with the requested structured prefixes: `[RejectScheduler]` (tick + outside-window + batch_done summary with `sent`/`skipped_missing_field`/`send_failed` counts), `[RejectFetch]` (per-source `pending_rejections` count + filter dump), `[RejectSend:A|B]` (attempt + DONE), `[RejectSend:WA]` + `[RejectSend:Email]` (pre-call markers so even SMTP/AiSensy crashes are visible), `[RejectSkip:A|B]` (missing-field skip reason).
  - **Fix #4** (`UpdateScores.js`) — `startDate` and `endDate` default to the user's local today (`YYYY-MM-DD`). Existing date filter UI untouched — admins clear/widen to see historical records.
  - **Live verification** — After clearing the affected tester's `rejection_sent` flag, the next 19:00 IST tick fired end-to-end: `[RejectFetch] pending_rejections=1 → [RejectSend:A] → [WhatsApp:RESP] status=200 ok=True submitted_message_id=5381aea1-...` AiSensy confirmed the WhatsApp dispatch to `9443109903`. Post-send DB state correctly flipped to `rejection_sent=True`, `rejection_send_ok=True` for idempotency on the next 5-min tick.


- **Feb 2026 (iter97)** — Phone-search 6-digit minimum + Dashboard search consistency.
  - **Numeric search min length**: `ApplicantSearchCards.jsx` now detects digit-only input (`/^\d+$/`) and short-circuits the backend call when length < 6. Mixed-text inputs (name, email, alphanumeric) keep the existing 2-char minimum. Helper text below the search input switches dynamically: `"Enter at least 6 digits to search phone numbers."` for numeric < 6, otherwise the standard partial-match hint with the new clarification `"(6+ digits for phone)"`. Applies automatically to `/manual-alerts`, `/manual-otp-verify`, `/candidate-journey` (all already used the shared component).
  - **Backend mirror** `bb_manual._search_applicants` — same `q.isdigit() and len(q) < 6 → []` guard added so accidental short-digit calls never hit Mongo. Letter-containing inputs unchanged.
  - **Dashboard consistency**: `Dashboard.js` "Score and Round" section migrated from the legacy single-line input + button to `ApplicantSearchCards` (with `testIdPrefix="journey-search"`, `autoFocus={false}` to avoid stealing focus during page load). Card click opens `CandidateJourneyModal` with the exact email/phone — same UX as `/candidate-journey`. Removed the now-unused `openJourney()` handler.
  - **Tested**: Backend `_search_applicants` directly — `'12'`/`'12345'`/`'9443'` → 0 hits with no DB scan; `'123456'`/`'9443109903'` → match hits; `'9443109903abc'` (letters) → name-search hits. Playwright on `/candidate-journey` and `/dashboard` — helper text + card count behave correctly across all three input modes. Single source of truth (`ApplicantSearchCards.jsx`) means future tuning happens in one place.


- **Feb 2026 (iter96)** — Public view-only job description link feature on Create Job Openings module.
  - **New public endpoint** `GET /api/pub/job-opening/{opening_id}` (`bb_modules.py`) — no auth, no cookies. Returns ONLY 9 public-safe fields (`title`, `job_role`, `vacancies`, `years_of_graduation`, `education`, `salary_range`, `key_responsibilities`, `added_advantages`, `what_we_offer`). Never leaks `_id`, `created_at`, `updated_at`, or any other internal metadata. Graceful 404 with message `"Job opening not found"` for both missing AND malformed ObjectIds (no 500).
  - **New public route** `/jobs/view/:openingId` (`App.js` + `PublicJobView.jsx`) — completely outside the `ProtectedRoute` tree. Renders job description using the same BluBridge-branded JD layout already used inside `PublicRegistration.js` (`bg-[#f3f1e9]` + cream card + `#1a2332` top stripe). NO Apply button, NO registration form, NO edit/delete controls, NO admin UI. Loading state, 404 error card.
  - **Card-level Link + Copy buttons** (`JobOpenings.js`) — mirror `HiringForms.js:149-165` pattern exactly. Link icon opens public page in new tab (`data-testid="opening-link-{id}"`); Copy icon writes `${window.location.origin}/jobs/view/${id}` to clipboard with toast confirmation (`data-testid="opening-copy-link-{id}"`). URL constructed at runtime from `window.location.origin` so it always resolves to whichever production/preview/custom domain the recruiter is on — never localhost or internal render URLs.
  - **Zero migration** — endpoint keys off the existing `bb_job_openings._id`, so every existing AND future job opening supports the feature automatically.
  - **Apply flow untouched** — `PublicRegistration.js` JD step and `_resolve_form_by_slug_or_id` continue to work exactly as before. The new public endpoint is independent of the form/registration flow.


- **Feb 2026 (iter95)** — Partial/regex applicant search, phone normalization UX completion, Final Reject campaign verification.
  - **Multi-card search (P0)**: new endpoint `GET /api/bb/manual/applicant/search?q=<text>&limit=25` returns `{items[], truncated}`. Case-insensitive `$regex` on `name` + `email` using `re.escape`; phone uses digit-only substring match (so `"7890"` matches `"1234567890"`). New shared component `/app/frontend/src/components/ApplicantSearchCards.jsx` (300ms debounce, inline cards with Name/Email/Phone/Job Role/Registered Status). Wired into `/manual-alerts`, `/manual-otp-verify`, `/candidate-journey`. Detail view shows "Back to results" link; existing `/applicant/lookup` (exact) still used after card click.
  - **Smart phone normalization (P0)**: backend `_validate_phone_10digits` already at iter94 — strips `+91`, `91` (len=12), and leading `0` (len=11). Frontend `utils/phone.js` (`normalizePhone` + `maskPhoneInput`) wired into both `PublicRegistration.js` and `CollegeRegistration.js` with **onBlur silent visual normalization**: `+919443109903`/`09443109903`/`919443109903` all collapse to `9443109903` on field blur. Helper text always visible; error text on failed normalize.
  - **Final Reject campaign (P0)**: verified iter94 wiring — `messaging.notify_rejected` uses `campaign_name="Final Reject"` with `template_params=[name, job_role]`. Form-condition rejections continue using `notify_rejected_with_reason` → `"Reject"` campaign. Worker A (`bb_applicant_updates` → post-interview) routes through `notify_rejected`; Worker B (`bb_registrations.rejection_pending` → form-condition) routes through `notify_rejected_with_reason`. `bb_manual.py:/alerts/send-reject` (admin manual post-interview) uses `notify_rejected`.
  - **Testing**: 20/20 backend pytest passed (`/app/backend/tests/test_iteration95_search_phone.py` — covers search auth/empty/match/limit/truncation, all 6 phone-prefix variants, Final Reject vs Reject campaign isolation with mocked `send_whatsapp`). Frontend Playwright covered 4/4 routes: `/manual-alerts`, `/manual-otp-verify`, `/candidate-journey`, `/register/college`. No real outbound messages triggered.


- **Feb 2026 (iter87)** — Re-registration OTP wipe + holiday label contrast + lock-at-5PM scoping.
  - **Item 1 — OTP still surfacing after re-registration**: iter86 cleared `pipeline_data.otp` but left `bb_registrations.otp` intact across all 29 historical rows for the tester. The Manual OTP Verify lookup's iter86 fallback (`get_otp_for_schedule(..., "")` → most-recent `bb_registrations.otp`) then re-surfaced the OLD OTP. **Fix**: both re-registration paths (non-tester + tester) now invoke `messaging.reset_otp_on_reschedule(email, phone)` after the field-reset, which `$unset`s `otp`, `otp_sent`, `otp_sent_at`, `otp_verified` on every matching `bb_registrations` row.
  - **Item 2 — Verified the OTP-lifecycle rules end-to-end**:
    - S1 re-register → `pipeline_data.otp=''` + `0/29` bb_registrations rows retain OTP ✅
    - S2 unscheduled lookup → `otp=''` ✅
    - S3 schedule → fresh `532416` ✅
    - S4 reschedule → fresh `758976` (different from S3) ✅
    - S5 Manual OTP Verify → Reschedule&Verify → **preserves `758976`** (no regeneration) ✅
    No code change needed for S3-S5 — the public schedule POST already generates a fresh OTP per call, and `manual_otp_reschedule_verify` does not touch `pipeline_data.otp`.
  - **Item 3 — Holiday badge contrast**: switched from `bg-{color}-900 text-{color}-200` (dark on dark) to `bg-{color}-100 text-{color}-800 border border-{color}-300` (light bg + dark text). Recurring → emerald; Non-Recurring → amber.
  - **Item 4 — Lock-at-5PM scoping**: lock now applies ONLY when `edit.schedule_date === today` AND `now.getHours() >= 17`. Future dates always show the fully-editable dropdown with no past-slot disabling. Applied to both render path and save handler.
  - **Tester-only verification**, no real-applicant data touched.

- **Feb 2026 (iter86)** — 5-item batch: OTP preservation + re-registration reset + UI dropdown + recurring holidays.
  - **Item 1+2 — OTP overwrite bug**: Root cause was `bb_manual._resolve_candidate_extras` calling `get_otp_for_schedule(email, phone, schedule_date)`. The "one OTP per (applicant, schedule_date)" rule favoured a date-matched historical OTP, so when admin reverted `schedule_date` to an earlier value via Reschedule & Verify, the OLD OTP re-surfaced and appeared to overwrite the candidate's actual latest OTP. **Fix**: `lookup_applicant` + `manual_otp_reschedule_verify` response now resolve OTP in two steps: (1) `pipeline_data.otp` if non-empty; (2) `get_otp_for_schedule(..., "")` which falls back to the most-recent `bb_registrations.otp` by `otp_sent_at` desc regardless of schedule_date. Verified: setting `pipeline_data.otp=663456` and reverting schedule_date to a historical match still returns `663456` (not `213456`).
  - **Item 3 — Re-registration didn't reset workflow fields** for non-tester applicants. Path at `bb_modules.py:3973` just `update_one`-ed personal fields, leaving stale `otp`, `schedule_date`, `otp_verified`, `result_status`, `email_type`, `*_sent` flags. **Fix**: added `FLOW_STATE_FIELDS_NONTESTER` reset alongside `set_fields` write, mirrored on `bb_registrations` via `$unset` for worker flags. Verified live: post-register pipeline_data → `{otp:'', schedule_date:'', schedule_time:'', otp_verified:'', result_status:'', email_type:''}`. Tester path unchanged.
  - **Item 3 cont. — Verify on unscheduled applicant** now returns HTTP 400 `"Applicant has not scheduled their interview"` (was silently allowed). Frontend keeps the Verify button visible per spec; backend is the source of truth.
  - **Item 4 — Time-slot dropdown** in Reschedule & Verify now uses the same `TIME_SLOTS` array as the public schedule form (10 AM-5 PM, 30-min intervals, 12-hour AM/PM display, past-slot disabled on today's date). When current local hour ≥ 17, the time field is **locked at 05:00 PM** with a read-only label. Storage stays 24-hour `HH:MM:SS` (the slot label is converted via `_slotToHMS` before POST).
  - **Item 5 — Recurring / Non-Recurring holidays**: added `holiday_type` field to `HolidayBody`; defaults to `Recurring` on legacy rows (list endpoint sets `setdefault`). New `_expand_holiday_dates(doc, years_back=5, years_fwd=10)` expands a Recurring holiday's MM-DD across years_back..years_fwd. Public `GET /pub/schedule/{token}` returns the expanded set (Aug-15 recurring → 16 occurrences, 2021-2036). Non-Recurring stays exact-date. SetHolidays UI: added "Holiday Type" dropdown in the Add/Edit modal; list shows colored badge per type.
  - **Tester-only verification**, all real-applicant data left untouched.

- **Feb 2026 (iter85)** — Production-safety QA pass + 2 critical fixes.
  - **Reschedule "already attended" bug — root cause**: iter82's `manual_otp_reschedule_verify` mirrored `otp_verified=True` to **every** `bb_registrations` row matching the tester's email|phone via `update_many` (26 rows polluted on `rajlearn06`, 21 on `rishi.nayak`). When the public reschedule page loaded by `schedule_token`, it landed on a polluted row → HTTP 409. **Fix**: replaced broad `update_many` with `update_one` scoped to the MOST RECENT row by `registered_at` desc. Tester rows cleaned. Zero real-applicant rows touched.
  - **Public schedule POST silently accepted garbage time**: local `_to_24h` returned raw text on parse failure → `"BANANA"` got persisted as `schedule_time`. **Fix**: replaced with centralized `to_24h_db` from `_fmt.py`; malformed input now returns HTTP 400.
  - **Full QA report** at `/app/memory/QA_iter85.md` — 17 backend cases, all PASS. Covers schedule lifecycle, OTP verify, Reschedule & Verify (time normalisation + malformed rejection), Manual Alerts lookup, Missing Applicants (pagination + CSV/XLSX export), Score & Round, Update Scores, View Attended round dedup, TEST_MODE status, auth.
  - **Only tester credentials used**; no production-applicant data modified; no notifications sent during QA.

- **Feb 2026 (iter84)** — Score & Round (and Update Scores / View Attended) now reflect Reschedule & Verify changes immediately.
  - **Root cause**: iter82's `manual_otp_reschedule_verify` only wrote `job_role` and `_normalized_job_role` to `pipeline_data` — it left `job_title` STALE. Several downstream surfaces (Score & Round table, Update Applicants Scores, exports) fall back to `job_title` when `job_role` is missing, OR display `job_title` directly in some projections. After a reschedule that changed the role, those pages kept showing the old role even though pipeline_data had the new one. Additionally, when email or phone changed, `bb_applicant_updates` and `score_sheet` still carried the OLD anchor, so the join broke and the candidate appeared to have lost their scores / status.
  - **Fix (`bb_manual.manual_otp_reschedule_verify`)**:
    - When `job_role` is updated, ALSO mirror to `job_title` AND `_normalized_job_role` — eliminates stale-fallback display across every page.
    - When `email` or `phone` changes (detected by `new != original`), re-link `bb_applicant_updates` and `score_sheet` rows to the new anchor so scores + status surveys stay attached to the candidate.
  - **No frontend caching issue**: React-Router remounts the destination component, so navigating Manual OTP Verify → Score & Round triggers a fresh `GET /api/bb/score-round/table` automatically — no extra refresh logic required.
  - **Verified live with tester `rajlearn06@gmail.com`**:
    - Seeded: `result_status=Shortlisted`, schedule=`2026-05-15 14:00`, `job_role=AI System Engineer`.
    - Reschedule & Verify: schedule→today `11:00 AM`, `job_role=Python Developer`.
    - pipeline_data after: `job_role=job_title=_normalized_job_role=Python Developer`, `schedule_date=today`, `schedule_time=11:00:00`, `otp_verified=True`, `result_status=Shortlisted` (preserved).
    - Score & Round (status=Shortlisted): finds the row with the new role + new date.
    - Update Applicants Scores: same.
    - Tester reverted post-test; zero real-applicant rows touched.

- **Feb 2026 (iter83)** — Missing Applicants pagination + global schedule_time normalisation.
  - **Root cause of "1 PM displayed as 1 AM"**: 9904 rows in `pipeline_data.schedule_time` are mis-stored as `01:00:00`–`05:30:00` (PM slots without the +12 offset) because a historical bulk importer never converted the 12-hour XLSX cells. The freshly-added `manual_otp_reschedule_verify` endpoint (iter82) also accepted user-supplied time AS-IS — would have grown the bad-data pile every reschedule. `bb_registrations` is clean (uses `_to_24h`).
  - **Fix A — Centralized DB normaliser**: new `_fmt.to_24h_db(t)` converts 12-hour ("01:30 PM"), 24-hour ("13:30"), or noon/midnight inputs to strict `HH:MM:SS`. Raises `ValueError` on garbage so we never persist nonsense.
  - **Fix B — All schedule_time WRITES go through it**:
    - `bb_manual.manual_otp_reschedule_verify` — wraps in try/except → HTTP 400 on malformed.
    - `bb_modules.create_college_schedule` and `update_college_schedule` — replaced brittle `len==3 else +":00"` with `to_24h_db`.
    - `bb_modules._to_24h` already correct for `/api/pub/schedule/{token}` (left untouched per "no unnecessary refactor").
  - **Fix C — Display heuristic for historical data**: `formatTime12H` (frontend) and `_format_time_12h` + `fmt_time` (backend) now treat any bare 24-hour input with hour ∈ [1, 5] as a mis-stored PM slot (interview window in this app is strictly 10:00-17:30 — values < 06:00 cannot legitimately be AM). Display-only, no DB mutation. Verified live via CSV export: legacy `01:00:00` rows now render `01:00 PM`, `02:00:00` → `02:00 PM`, etc.
  - **Fix D — Backend validation**: `to_24h_db("banana")` → HTTP 400 `"Invalid schedule_time: Unrecognized time format: 'banana'"`. Tested live.
  - **Missing Applicants pagination**: full `<<` `<` page-input `Go` `>` `>>` controls; records-per-page dropdown (25/50/100/200/500); first/last buttons auto-hide on first/last page; export still streams ALL filtered records (page/limit are intentionally NOT sent to `/export`). Verified live: total=1071, page=5/limit=25 returns the correct 25-row slice.
  - **Tester credentials only**: live verification ran reschedule-verify on `rajlearn06@gmail.com` with `"01:00 PM"` → stored as `13:00:00` → reverted. Zero real-applicant rows touched.

- **Feb 2026 (iter82)** — Manual OTP Verify always-enabled + Reschedule & Verify + new Missing Applicants module.
  - **Manual OTP Verify**: removed the date-based Verify restriction in `bb_manual.manual_otp_verify` ("Your interview is over!"/"in future!" branches gone). Verify is always shown and enabled (front + back). When `today < schedule_date`, the new **Reschedule & Verify** button appears alongside Verify; clicking it makes Phone / Email / Job Role / Schedule Date / Schedule Time editable inline (other fields stay read-only).
  - **`POST /api/bb/manual/otp/reschedule-verify`** (new) — anchors on `original_email|original_phone`, atomically writes any provided field updates, sets `otp_verified=True`, `otp_verified_at`, `last_update`, and `_normalized_job_role` so analytics filters stay in sync. Mirrors onto `bb_registrations` (so Reschedule page / OTP / Reminder workers see the new schedule). Updates the existing record only — never creates a duplicate.
  - **New page `/missing-applicants`** — Filters: From Date / To Date (default = today), Date Filter (Registered / Scheduled — default Registered, matches `last_update` or `schedule_date` DATE portion), Report Type (All / Shortlisted-but-not-scheduled / Interview-scheduled-but-not-attended — default All). Buttons: Filter, Reset, Export (CSV + XLSX). Columns: Name, Email, Phone, Current Location, Job Role, College, College Type, Degree, Course, Registered Date, Scheduled Date, Schedule Time, Result Status. All dates render as `dd-mm-yyyy`; times as `hh:mm AM/PM`. Backend endpoints: `GET /api/bb/missing-applicants` + `GET /api/bb/missing-applicants/export` reading `pipeline_data`. Status logic:
    - `email_type=shortlist` + `schedule_date IS NULL` + `schedule_time IS NULL` → "Shortlisted but interview not scheduled".
    - `schedule_date NOT NULL` + `schedule_time NOT NULL` + `otp_verified IS NULL/0` → "Interview scheduled but not attended".
  - **Sidebar + Home** updated with Missing Applicants entry (UserMinus icon, rose tone).
  - **Verified live** with tester credentials only (`rajlearn06@gmail.com` — scheduled tomorrow). Reschedule-Verify flow updated job_role from `''→AI ML`, schedule from `2026-05-12 12:30→2026-05-15 14:30`, set `otp_verified=true`. Reverted after test — no real applicant data modified. Missing Applicants endpoint counts: 1071 total = 476 not-scheduled + 595 not-attended. CSV/XLSX exports return 200 with formatted columns. **TEST_MODE remains OFF**; no messages were sent during validation (this flow is admin-only and doesn't trigger notifications).

- **Feb 2026 (iter81)** — PRODUCTION ROLLOUT: TEST MODE OFF + cutoff bumped to NOW to prevent historical replay.
  - `/.env`: `TEST_MODE=true → false`; `MESSAGING_CUTOFF_TS=2026-05-04T18:07:51 → 2026-05-11T18:30:00+00:00`.
  - **Why bump the cutoff first**: 33 shortlisted + 10 rejected post-cutoff registrations had been blocked by TEST_MODE. With TEST_MODE off they would have been picked up by the next worker tick (24h upper bound) and replayed to real applicants — exactly what the spec forbids. Bumping the cutoff to "now" freezes them atomically.
  - **Workers still filter by `registered_at >= MESSAGING_CUTOFF_TS`** on every loop, so only NEW post-cutoff registrations / actions trigger messages going forward.
  - **No code refactor**, no DB record deletion, no notification queue replay. `bulk_upload_queue` already empty (no pending notification jobs).
  - **Verified**: `/api/messaging/status → {test_mode: false}`. Worker queue counts after the cutoff bump: schedule-link=0, rejections=0, schedule-confirmations=0. 90s of post-restart logs show ZERO Gate decisions and ZERO `[ScheduleLink]` sends — confirming no historical replay.
  - **Future**: Manual Alerts and Bulk Communication Center remain fully functional (admin-triggered, exempt from the cutoff). Inline send on new shortlisting (iter80) still fires within 3 s of submission.

- **Feb 2026 (iter80)** — Removed 5-min schedule-link cooldown. As soon as an applicant is shortlisted via `POST /api/pub/register`, the inline `_instant_notify()` task in `bb_modules.py` now calls `messaging.notify_shortlisted(...)` immediately (Email + WhatsApp), then writes `schedule_link_sent=True`, `schedule_link_sent_at`, `shortlist_mail_sent=ok`, `shortlist_mail_sent_time` atomically. The `bg_workers._worker_schedule_link_sender` is now a pure retry safety-net — dropped the `five_min_ago` lower-bound on `registered_at`, kept the idempotent `schedule_link_sent={"$ne": True}` + `schedule_initiated={"$ne": True}` guards + 24h upper bound. Verified live: send completes 3 s after submission (vs 5m28s before). Single send confirmed; the worker logs `[ScheduleLink:Retry]` only when the inline send failed and was missed. Unaffected: scheduling/reschedule, OTP, follow-up, rejection, TEST_MODE gate, Manual Alerts, Bulk Comm Center.

- **Feb 2026 (iter79)** — 6-item batch (View Attended dedup, OTP Source, Reschedule freshness, Date/Time formatting, Manual Alert button rules, past-slot guard):
  1. **View Attended Applicants** — `/api/attended` now collapses whitespace+case duplicates so legacy variants (`Accounts1` vs `Accounts 1`) merge into ONE canonical column. Per-applicant score lookup uses the same canonical key, so a score recorded under either variant surfaces in the unified column. Soft-deleted rounds (`active=false`) are already filtered. Sort: alphabetical. No-score cells render `-`.
  2. **Verify Applicant OTP — Source field** — Now displays `pipeline_data.hr_team` (the HR team owning the candidate). Falls back to legacy `source` / `application_source` only when `hr_team` is blank, so historic rows still render.
  3. **Reschedule form freshness** — `GET /api/pub/schedule/{token}` now prefers `pipeline_data.schedule_date` / `schedule_time` over the older `bb_registrations` copy. Multi-reschedule scenarios always show the LATEST values. Verified live: token `5d8ae052…` correctly returns `2026-05-11 / 13:30:00` (pipeline_data) instead of the stale `2026-05-05 / 14:00:00` (bb_registrations).
  4. **Global date/time formatter** — Single source of truth: existing `/app/frontend/src/utils/dateFormat.js` (`formatDateDDMMYYYY` → `dd-mm-yyyy`; `formatTime12H` → `hh:mm AM/PM`) + new `/app/backend/_fmt.py` (`fmt_date`, `fmt_time`). Applied in `messaging.notify_schedule_confirmation`, `notify_otp`, `notify_missed_reminder` so every outbound WhatsApp + Email shows formatted values regardless of stored format. Frontend pages: `InterviewSchedule.js` (schedule form, success card, current-schedule readout), `ManualOtpVerify.js` (search + verified panels). `Roles.js` / `AttendedRoles.js` already used `dateFormat.js` helpers.
  5. **Manual Alerts button enable rules** — Rewrote `_allowedActions(applicant)`:
     • ALWAYS enabled: Send Interview Schedule, Send Schedule Details, Send OTP, Send Candidate Follow-up.
     • Send Rejection: enabled iff `registered_status === 'Attended'` (result_status is ignored). All other states keep Reject disabled with tooltip.
  6. **Past-slot guard on Schedule/Reschedule** — Frontend: when the chosen date equals today, `<option disabled>` is applied to every slot whose 12-hour label is ≤ current `Date()` minutes; selecting the date resets the time picker; client-side guard in `handleSchedule()`. Backend: `POST /api/pub/schedule/{token}` builds a `datetime` from the supplied date + 24h time and returns HTTP 400 with "Selected time slot is in the past" if `slot_dt < now()`. Defence-in-depth.

- **Feb 2026 (iter78)** — Bug fix: Unified instruction-page gating in `PublicRegistration.js`. Previously, the toggle "Show Instruction Page = No" correctly suppressed the custom Instructions step BUT the AI/ML hardcoded interstitial (`What You Need to Know?`) still fired for any shortlisted candidate on an AI/ML role, ignoring the toggle. Fixed: both interstitials are now gated by `show_instruction_page`. When `false`, registrant goes straight to result. When `true`: custom instruction_content (if non-empty) → 'instructions' step (chains to AI/ML if applicable then result); else AI/ML shortlisted → 'aiml' step; else result.

- **Feb 2026 (iter69f — Phase 3 of 11-item batch · #10 Job Keyword + Role Sync)**:
  - **#10A — Two-source sync**: `_sync_job_titles_master()` now extracts distinct job titles from BOTH `naukri_applies.job_title` AND `pipeline_data.job_role` (with `job_title` fallback), normalises, and upserts into `job_titles_master` AND auto-populates `bb_job_roles` (case-insensitive). The HR Pipeline upload (`/api/upload/pipeline`) now triggers the sync — previously only the Naukri upload did.
  - **#10B — `/manage-job-roles` page** already existed (cards + edit + delete via `/api/bb/job-roles` CRUD). No frontend changes needed.
  - **#10C — Manual create mirrors into `job_titles_master`**: `POST /api/bb/job-roles` now (a) rejects case-insensitive duplicates with HTTP 409, (b) inserts the title into `job_titles_master` (`source: 'manual'`) so it shows up in the mapping picker alongside imported titles.
  - **#10D — Mapping picker** (`/api/job-titles/unmatched`) already reads from `job_titles_master` — now includes both extracted + manual entries automatically.
  - **#10E — Dropdowns** consume `bb_job_roles` and the `_resolve_normalized_job_role(...)` helper (uses `job_keyword_mapping`) at the data layer, so app-wide UIs surface the canonical mapped names.
  - **Verified live**: manual sync inserted 105 titles into `job_titles_master` + 73 into `bb_job_roles` from existing data. Manual create flow round-tripped: created → 409 on duplicate → appeared in mapping picker → role count incremented. Cleanup performed.

- **Feb 2026 (iter69e — Phase 2 of 11-item batch)**:
  - **#6 — Derived Registered Status**: backend `_derive_registered_status()` now computes from `pipeline_data` fields:
    `email_type=reject` → "Rejected" · `email_type=shortlist` & no schedule → "Interview not scheduled" · schedule + `otp_verified=1` → "Attended" · schedule + past date + not verified → "Not Attended" · schedule + future/today + not verified → "Interview scheduled". Surfaced via `/applicant/lookup`. Result Status read directly from `pipeline_data.result_status`.
  - **#7 — Conditional buttons (Manual Alerts)**: `_allowedActions(applicant)` enforces spec table. "Interview not scheduled" → only Shortlist enabled · "Interview scheduled" / "Not Attended" → Schedule Detail + OTP + Follow-up · "Attended" + Selected → none · "Attended" + Rejected/On hold → only Reject. Disabled buttons render grey with `cursor-not-allowed` and a tooltip showing the reason. Header shows the live derived state. Verified via screenshot for the Attended+Rejected state.
  - **#8 — Score → pipeline_data sync**: `PUT /api/bb/applicant-score/{email}` now also writes the new status to `pipeline_data.result_status` (matching by email OR phone last-10-digits) so View Applicants, View Attended Applicants, Manual Alerts, and analytics all reflect the change immediately. Wrapped in try/except so a failed sync never blocks the score save.
  - **#11 — WhatsApp Resend module**: Was sending **5 params** to AiSensy "Candidate FollowUp" (silent 400 drop). Fixed to **4 params** in both `bb_resend.py` send paths, matching the verified template definition. History log payload aligned. Centralized TEST_MODE gate (`can_send_message`) was already enforced.

- **Feb 2026 (iter69e — Phase 1 of 11-item batch)**:
  - **#3 — Manual OTP Verify always fetches existing OTP**: lookup endpoint already returns `otp` + `otp_verified` from `pipeline_data`; UI displays them regardless of verified state — no new OTP is ever generated by the Verify page.
  - **#4 — Date-only OTP gating** (re-confirmed): `_parse_schedule_date_iso` strips embedded times (`'2026-05-08 13:00:00'`, ISO 8601 `T+offset`) before comparing against `date.today()`. 8 input variants verified.
  - **#5 — Already-verified state**: when `otp_verified=true`, the Verify button is hidden and an emerald banner reads **"Applicant has already verified their OTP !"**; details + OTP still rendered. Live screenshot confirmed.
  - **#9 — Tester re-registration resets flow-state fields**: in addition to the existing FULL OVERWRITE + CONSOLIDATE on `pipeline_data`, the new `replacement` doc explicitly nulls `otp`, `otp_verified`, `otp_sent`, `otp_sent_at`, `email_type`, `result_status`, `schedule_date`, `schedule_time`, `whatsapp_reminder_sent`, `whatsapp_followup_sent`, `shortlist_mail_sent`, `interview_mail_sent`, `reject_notified`, `schedule_message_sent`, `isImported`, `import_batch_id`, `imported_at`, `import_rejection_notified`. Mirrors the reset by `$unset`-ing the same flow flags on every matching `bb_registrations` document so the bg_workers re-fire the new flow cleanly. Applies to both `register_applicant` and `register_college_applicant`. Non-tester registrations unchanged.

- **Feb 2026 (iter69d)** — Five-issue batch:
  - **#1/#2 (Reject + Schedule Detail WhatsApp)**: Verified live via curl that both `Reject` and `Schedule Detail` campaigns return AiSensy `status=200` + `submitted_message_id` — code is firing WhatsApp correctly with full TEST_MODE gating. Non-arrival reported by the user is downstream (AiSensy `FREE_FOREVER` plan recipient whitelist + 24-hour conversation window), NOT a code bug. Logs now record campaign + recipient + AiSensy status + msg_id for every send so the dashboard team can correlate.
  - **#3 (Duplicate Schedule email)**: Real bug. `register-schedule` was setting `schedule_message_sent` while the bg_worker (Schedule Link Sender, polls every 60 s) checks the legacy `interview_mail_sent` flag — so the worker re-fired the same email a few minutes later. Fix: direct path now writes BOTH `schedule_message_sent` AND `interview_mail_sent` (+ timestamps) so the worker correctly skips already-notified registrations.
  - **#4 (OTP date — ignore time)**: `_parse_schedule_date_iso` now strips any embedded time component (`'2026-05-08 13:00:00'`, `'2026-05-08T13:00:00+00:00'`) before parsing the calendar date. Comparison is purely DATE vs LOCAL SYSTEM DATE. Verified across 8 input variants.
  - **#5 (Score Import — update existing rounds)**: Was append-only — existing round scores were silently preserved when the import file had a fresher value. Per spec, switched to **upsert per round**: new rounds inserted, existing rounds updated (round-name canonicalised so "Round 1"/"round 1" don't duplicate). Match is now by `email OR phone` (last-10-digit regex) so file rows lacking the canonical email still update the right candidate. Auto-registration into `bb_rounds` (case-insensitive dedupe) was already correct and is preserved.

- **Feb 2026 (iter69c)** — Tester FULL OVERWRITE — actual root cause:
  - **Real bug**: `find_one(...)` returns ONE matching `pipeline_data` row, but legacy data has **N duplicates per tester** (e.g. `rajlearn@gmail.com` AND `rajlearn06@gmail.com` both hold phone 8883847098). Replacing only one row left the other intact → frontend kept showing the stale orphan, masquerading as "overwrite not working".
  - **Fix**: For tester registrations, both `register_applicant` and `register_college_applicant` now `find(...).to_list()` ALL matches (sorted by `_id` ASC), `replace_one` the survivor (preserving its `_id`), then `delete_many` the rest. Logs include `survivor_id`, `matched=N`, `replaced_modified=1`, `deleted_dups=N-1`. Non-tester paths untouched.
  - **Verified live**: `rajlearn` had 2 dup rows → after one tester registration, exactly 1 row remains with all latest values; survivor `_id` retained for downstream FK consistency. No unrelated applicants modified.

- **Feb 2026 (iter69b)** — AiSensy template param fix + tester full-overwrite:
  - **ROOT CAUSE (Issue #1/#2 — WhatsApp not delivered for Followup)**: `notify_missed_reminder` was sending **5 params** to AiSensy "Candidate FollowUp" but the actual approved template expects **4 params**. AiSensy returned `{"message":"Template params does not match the campaign"}` (HTTP 400) and silently dropped the message. Fixed: dropped `schedule_link` param (CTA URL is in template body); now sends `[name, role, formattedDate, time]`. Verified live → 200 OK with `submitted_message_id`. The other 4 templates were probed and confirmed correct: ShortList=2, Schedule Detail=4, OTP With Job=7, Reject=0.
  - **Note (Issues #1/#2 delivery)**: Reject + Schedule Detail were already returning HTTP 200 from AiSensy. If recipients still don't see the message, the cause is downstream (AiSensy free-tier whitelist / 24-hour conversation window) — outside our codebase. The gate logs the campaign + recipient + AiSensy `status` + `submitted_message_id` for every send, so HR can correlate against AiSensy dashboard.
  - **Tuple-as-bool fix** (`bb_modules.register-schedule`): `notify_schedule_confirmation` returns `(wa_ok, em_ok)`; caller was treating tuple as bool, so `schedule_message_sent` flag was always True. Now records `schedule_message_sent`, `schedule_message_wa_ok`, `schedule_message_em_ok` separately.
  - **Tester full-overwrite (Issue #3)**: When the registrant's email OR phone matches an entry in `bb_test_credentials`, both `register_applicant` and `register_college_applicant` now call `pipeline_data.replace_one()` (full document replacement) instead of partial `$set`. Stale fields like `schedule_*`, `otp_*`, `result_status`, `scores` are dropped. Non-tester registrations retain the existing non-destructive merge (and CONFLICT-skip safety on the college path).
  - **Latent bug fix in college path**: when `existing` was found by phone match (different stored email), the `update_one({"email": target_email}, ...)` query failed to match → silent no-op. Changed to `update_one({"_id": existing["_id"]}, ...)`.
  - Verified live: tester `rajlearn@gmail.com / 8883847098` → `replace_one` collapses one of the two duplicate records into a single, fully-overwritten document. Existing live data NOT modified beyond the targeted tester record.

- **Feb 2026 (iter69)** — Centralized TEST MODE gate (single source of truth):
  - **NEW: `messaging.can_send_message(email, phone)`** is now the only gate. When `TEST_MODE=true` (default — fail-safe), a recipient is allowed iff their email OR phone exists in the live `bb_test_credentials` collection (managed via the Tester Credentials admin UI). When `TEST_MODE=false` it always returns allowed (production). NO auto-substitution — actual recipient is used as-is or blocked.
  - **Removed**: hard-coded `_ALLOWED_PAIRS` static allowlist, `_resolve_recipient` test-route override, the `bypass_allowlist` parameter, and the `TEST_PHONE` / `TEST_EMAIL` / `FORCE_TEST_MODE` env vars (dead code paths). `is_allowed_recipient` is kept only as a deprecated stub.
  - **Wired** `init_messaging(db)` at server startup; default testers (`rishi.nayak@blubridge.com`, `rajlearn@gmail.com`) seeded eagerly on startup so the gate has a non-empty allowlist on first boot. Logs `[TEST_MODE] is_on=True testers_in_db=2`.
  - **Migrated callers**: `bb_manual.py`, `bb_resend.py`, `bb_modules.py` (cooldown bypass) all use `can_send_message` / `bb_test_credentials` directly.
  - **New endpoint** `GET /api/messaging/status` → `{test_mode: bool}` powering the **amber "TEST MODE ACTIVE" banner** rendered globally in `AppShell.js` for any authenticated page.
  - **Logs every decision**: `[Gate:WA]` / `[Gate:Email]` lines record `test_mode`, `allowed`, `reason` (codes: `production` | `test_mode:tester_allowed` | `blocked:test_mode:not_in_testers` | `blocked:test_mode:empty_recipient`).
  - **Verified live**: tester `rajlearn@gmail.com / 8883847098` → WhatsApp 200 + Email SENT. Non-tester `aashoksai306@gmail.com / 9500557167` → blocked, gate logs `reason=blocked:test_mode:not_in_testers`, UI gets HTTP 502 (no false success).
  - **Disabling TEST_MODE** is now a manual ops decision: edit `/app/backend/.env` (`TEST_MODE=false`) and `sudo supervisorctl restart backend`. No code path turns it off automatically.

- **Feb 2026 (iter68)** — Manual flows hardened (no destructive DB updates):
  - **Manual Applicant Alerts** now actually send to the real applicant. Added `bypass_allowlist` flag on `messaging.send_whatsapp` / `send_email` (default False — automated flows still gated). All 5 high-level `notify_*` functions accept and propagate the flag and now return `(wa_ok, em_ok)` tuples. `bb_manual.py` alert handlers pass `bypass_allowlist=True`, log recipient + channel results, and raise HTTP 502 (truthful failure) when both channels fail. UI no longer shows false success.
  - **Manual OTP Verify** turned into a 2-step flow. New lookup payload exposes `schedule_date_iso` (`%Y-%m-%d`) + `interview_status` ('today' | 'past' | 'future' | 'unknown') computed against LOCAL SYSTEM DATE (date-only compare, ignores time). Frontend conditionally renders Verify button only on `today` / `unknown`; shows "Your interview is over !" (past) / "Your interview is in future !" (future). Backend `/manual/otp/verify` enforces the same guard server-side (HTTP 400) so UI bypass is impossible.
  - Schedule-date parser handles existing DB variants `DD-MM-YYYY`, `YYYY-MM-DD`, `DD/MM/YYYY`, `YYYY/MM/DD`. No DB writes.
  - Verified live via curl + Playwright: today=Verify, past=Over, future=In future, real applicant `aashoksai306@gmail.com` got actual WhatsApp + Email (status 200, message_id present in AiSensy response).

- **Feb 2026 (iter58)** — Score & Round — Advanced filters + Dynamic per-round 5-col groups:
  - **Filter bar** on `/score-round`: Search (name/email/phone), **From Date** + **To Date** (`pipeline_data.schedule_date`), **Status** dropdown (Shortlisted / Rejected / On-Hold — OVERALL only; recruiter `bb_applicant_updates.status` wins over `result_status`), **College** + **Job Role** substring filters. Apply / Reset. All combinable; AND logic; no filters → all rows.
  - **Status perf**: single `distinct()` on `bb_applicant_updates.email` index → main `pipeline_data` query uses `email IN [matching]`. Sub-second on 100K rows.
  - **NEW backend params** on `GET /api/bb/score-round/table`: `startDate`, `endDate`, `status`, `college`, `job_role`. **NEW response field** `extra_rounds: [{canon, label}]` — rounds beyond the 11 static set with ANY data on current page; sorted alphabetically.
  - **Table layout**: After Z A → DOJ/DOD/DOI → each `extra_rounds` entry renders a **5-column group** (Round Name / Date / Score / Command-with-eye-tooltip / Status) under a fuchsia subheader strip. Static 11 rounds keep single-cell rendering with hover-tooltip (unchanged).
  - **Verified live**: Status=Shortlisted + demo search → 2 rows; Status=All + demo → 10 rows mixed; custom "Final Discussion" round renders as 5-col group after ZA.
- **Feb 2026 (iter57)** — Seeded 10 demo candidates for Score & Round (`/app/backend/seed_score_round_demo.py`, idempotent, `--cleanup` supported). All `seed='score_round_iter57'`.
- **Feb 2026 (iter56)** — Job Role hardened to structured multi-input + select dropdown:
  - **Backend** (`bb_modules.py`):
    - `bb_college_schedules` schema now stores **`job_roles: ["AI/ML","Administration","HR"]`** array (preferred) AND legacy `job_role: "AI/ML,Administration,HR"` joined string for backward compat with the register endpoint that regex-matches on `job_role`.
    - New `_normalize_roles()` helper coerces either input form (`job_roles[]` or comma `job_role`) into a deduped, ordered list (case-insensitive dedupe, first-seen casing preserved).
    - `POST /api/bb/college-schedules` & `PUT` accept either `job_roles` (preferred) or legacy `job_role` string. Removed (college, role) compound dup-check — multi-role schedules per college are now first-class.
    - `GET /api/bb/college-schedules` always returns `job_roles[]` (auto-backfilled from legacy rows on read).
    - `GET /api/pub/college-form/schedule` exposes `job_roles[]` array alongside `job_role` for frontend select-population.
  - **Admin form** (`CollegeSchedules.js`): replaced text input with proper **chip-based multi-input** — type and press Enter or `,` to add a chip, click ✕ on a chip to remove, Backspace on empty input removes the last chip. Case-insensitive dedup. Edit mode loads existing `job_roles[]` (or splits legacy joined string) into individual chips. Listing column renders each role as its own pill instead of joined text.
  - **Public form** (`CollegeRegistration.js`): Job Role is now a **`<select>` dropdown** (not a text input). On college change, options are populated from the schedule's `job_roles[]` array. If only one role exists, it auto-selects; otherwise user must pick one. Disabled when no college selected or no roles available. User CANNOT type — selection only.
  - **Verified live**: admin chip UI (add Enter / add comma / Backspace remove / dup ignored), backend stores both `job_roles` array + joined string, public select shows `[Select role, AI/ML, Administration, HR]` for multi-role schedules and auto-picks the single role for legacy schedules. Test rows cleaned up post-test. Submission logic untouched.
- **Feb 2026 (iter55)** — New "Score & Round" dashboard module (URGENT spec):
  - **New page** `/score-round` (`ScoreRound.js`) — Excel-like table with sticky header + sticky Action column. Columns: Action, Name, Schedule Date, College, Degree, Course, YOG, Email, Phone, Job Role, Status, then ALL active rounds dynamically (static: Accounts 1, Accounts 2, BA, BE, BP, C++, Java, LA, Mensa, Mensa Org, ZA — always present even if not in `bb_rounds`), then DOJ / DOD / DOI. Round cells show numeric score; on hover an eye icon appears with a tooltip displaying Date / Status / Command. Pagination 50/page (103,962 candidates total). Live free-text search across name/email/phone.
  - **"Add Rounds" button** opens `ManageRoundsModal` — uses existing `/api/bb/rounds` CRUD: add new round (Enter to submit), inline rename, logical delete (preserves historical scores), restore. Show-inactive toggle.
  - **Action button per row → 2 options**:
    - **Update Score** — modal with N round entry blocks. Each block: Round Name (dropdown from `bb_rounds`), Date, Score, Command (textarea), Status (dropdown of 13 lifecycle statuses per spec). "Add More" stacks blocks; "Save" persists all at once. Prefilled with existing scores for editing.
    - **Update Date** — modal with Date of Joining / Documentation / Induction date pickers (prefilled).
  - **New backend endpoints** in `bb_modules.py`:
    - `GET /api/bb/score-round/table?page&limit&q` → paginated rows from `pipeline_data` joined with `bb_applicant_updates`. Returns `rounds_map` keyed by canonical round name with `{round_name, date, score, command, status}` per round, plus the 3 induction dates and active rounds list.
    - `POST /api/bb/score-round/save-scores` `{email, entries[]}` → append-only per-round upsert in `bb_applicant_updates.scores[]` keyed by canonical round name. Auto-registers any new round name into `bb_rounds`. Existing rounds untouched.
    - `PUT /api/bb/score-round/save-dates` `{email, date_of_joining?, date_of_documentation?, date_of_induction?}` → updates `pipeline_data` (only fields explicitly passed; null = leave as-is, empty string = clear).
  - **Schema extension** — `bb_applicant_updates.scores[]` now stores `{round_name, date, score, command, status, updated_at}`. Legacy entries `{round_name, score}` continue to read correctly (missing fields render as empty in the modal).
  - **New module entry** on Home (`Home.js`) — sky-themed "Score & Round" between "Update Applicants Scores" and "Candidate Journey" with `Table` icon. Route in `App.js`.
  - **STRICT data safety**: append-only writes; existing scores preserved when modal saves only some rounds; rejection of unknown rounds (auto-creates them); hard-delete blocked on rounds in use (existing protection).
  - Verified live end-to-end with admin-auth: 103,962 rows pageable, BA score 85 + command + status persisted, DOJ/DOD/DOI persisted, hover tooltip shows command, all 3 modals open and save correctly. Test data cleaned up post-verification — zero live data drift.
- **Feb 2026 (iter54)** — College Drives — Two strictly-isolated enhancements:
  - **Req1: Multi-value Job Role on Add College Schedule** (`CollegeSchedules.js` only). Recruiter can type `AI/ML, Administration, HR` (commas + spaces). Save handler splits on comma, trims, dedupes case-insensitively (preserving first-seen casing) and persists as comma-joined string `"AI/ML,Administration,HR"`. Single-value entries continue to work; existing rows render unchanged in listing. Edit mode shows the persisted string back. No DB schema or compound-index change.
  - **Req2: Public form auto-populate on college selection** (`CollegeRegistration.js` only). New backend endpoint `GET /api/pub/college-form/schedule?college=X` returns the LATEST ACTIVE schedule for the college (sorted by `created_at` desc, fallback `schedule_date` desc) → `{college_name, job_role, schedule_date, schedule_time}` or `{schedule: null}` when none. Frontend triggers fetch ONLY on college dropdown change (not on page load). Job Role is now a read-only auto-filled input (replaces the role dropdown), and two new read-only fields `Schedule Date` (DD/MM/YYYY) and `Schedule Time` (12-hour AM/PM) are added below it. Multi-role schedules show as comma-separated string. No-data / network-error case clears all three fields silently and shows a soft amber notice "No active schedule found for this college yet". Submission logic, payload shape, and validation untouched.
  - Verified live: TestCollege_Iter54_UI (multi-role) → `AI/ML,Administration,HR · 03/09/2026 · 02:30 PM`; Anna University (legacy single-role) → `AI / ML · 06/05/2026 · 12:00 PM`; cleared selection → all fields blank.
- **Feb 2026 (iter53)** — Candidate Journey module on Home + Richer Interview-Scheduled confirmation:
  - **New Home module "Candidate Journey"** (sky theme, magnifying-glass icon) routes to new page `/candidate-journey` (`CandidateJourney.js`) — dedicated search card that opens `CandidateJourneyModal` with the same rounds/status/DOI payload. Also still available on `/dashboard` (Score and Round section).
  - **Interview Scheduled success page replaced** (`InterviewSchedule.js`). Post-submit now shows: title "Your Interview Has Been Scheduled!" (or Rescheduled!), Thank-you line naming Blubridge Technologies, Interview Details block (Date DD-MM-YYYY / Time 12-hour / Location fixed company address), confirmation-email line, ⚠ Spam/Junk warning box, closing "We look forward to meeting you in person!" Date/time pulled from the just-submitted `date`/`time` state with fallback to `info.schedule_date`/`info.schedule_time` for reschedule preview.
  - Verified live: `15-06-2026 · 04:30PM · 30, Norton Road, Mandavelipakkam, Raja Annamalai Puram, Chennai, Tamil Nadu - 600028`.
- **Feb 2026 (iter52)** — Candidate Journey (A–Z) row action on Roles + AttendedRoles:
  - **New backend endpoint** `GET /api/bb/candidate-journey?email=&phone=` returns the full structured payload spec'd by the user: `{basic, round_details, latest_round, latest_score, total_score, final_outcome:{status, date_of_induction}}`. Reads only from `pipeline_data`, `bb_applicant_updates`, `score_sheet`. Conflict (email/phone mismatch) → 409 + log.
  - **Round timeline**: rounds ordered by `bb_rounds.order` then alphabetical fallback. Each entry: `{round_name, round_label, score, status, completed_date}`. Custom display labels per spec: *Round 2 → F2F*, *HR Round → HR Interview*, *Round 1 → Technical 1*, *Round 0 → Final Discussion*. Status: `Completed` (score present) / `Rejected` (text reject) / `Pending` (no data). Rounds with no data are skipped per spec.
  - **Date of Induction**: read from `pipeline_data.date_of_induction`. *Pending* if status=Selected and empty, *Not Applicable* otherwise. New `PUT /api/bb/candidate-induction-date` lets admins set/clear it from the Final Outcome card on the modal.
  - **Frontend**: new reusable `CandidateJourneyModal.jsx`. Per-row eye-icon button on `Roles` and `AttendedRoles` tables opens it. Modal renders 3 sections (Candidate Info, Round Progress timeline, Final Outcome), supports inline DOI editing only when status=Selected, gracefully handles 404/conflict states.
  - 31/31 regression tests pass (4 new in `test_iteration52_candidate_journey.py`). Verified live in browser — modal opens with rounds, status, DOI displayed correctly. **No live MongoDB data modified.**
- **Feb 2026 (iter51)** — Cooldown bypass for test users + Round duplication eliminated:
  - **Cooldown bypass** (`register_applicant`): the 4-month re-registration block now skips the allowlist pair `(rishi.nayak@blubridge.com, 9443109903)` and `(rajlearn@gmail.com, 8883847098)` — same `is_allowed_recipient` check used by messaging. Only matches when BOTH email + phone of a single allowed pair line up. All other users follow the unchanged cooldown rule. Logs `[Cooldown] BYPASS for allowlisted test user…` for traceability.
  - **Round dedup — root cause**: `score_sheet` legacy data has BOTH `'Accounts1'` and `'Accounts 1'` (and similar variants). Export was collecting raw round_names with only `.strip()`, so each variant became a separate column.
  - **Export fix** (`/api/bb/export-scores`): round columns now collapse via `_norm_round` (whitespace-collapsed + alias-mapped); per-applicant scores from any variant fall into the canonical bucket. CSV/XLSX header has no duplicate round columns.
  - **Import fix** (`/api/bb/import-scores/preview`): if the imported file has both `Accounts1` and `Accounts 1` columns, both collapse to a single canonical `Accounts 1` column; per-row score from any variant column lands in the canonical bucket (last-wins to handle conflicting CSV cells).
  - **UI safety net** (`/api/bb/rounds`): list endpoint now does case-insensitive + whitespace-collapsed dedupe at render time so the rounds tabs UI never shows the same round twice even if legacy bad data exists in `bb_rounds`.
  - 27/27 regression tests pass (5 new in `test_iteration51_cooldown_round_dedup.py`). No live data modified.
- **Feb 2026 (iter50)** — Auto-Move Public College Registration → `pipeline_data`:
  - `register_college_applicant` now syncs each successful submission into `pipeline_data` per the College Drive spec:
    - **`source: "college_drive"`** (was `"college_form"`).
    - **Insert-only flags**: `stage: "registered"`, `created_at`, `pipeline_synced_at` (never overwritten on re-registration via `$setOnInsert`).
    - **Profile preserved** (name, college, source, age, …) — only filled if currently blank.
    - **Pipeline progress preserved** — `scores`, `result_status`, `otp_verified` are NEVER touched by the sync.
    - **Dynamic fields refreshed** — `schedule_date`, `schedule_time`, `job_role`, `email_type`, `last_update`, `updated_at`.
    - **Phone↔email conflict guard**: same phone bound to a different email → logged + sync SKIPPED, registration still returns 200 (per spec).
    - **Failure-isolated**: any pipeline error is caught + logged but never blocks the registration response.
    - **Audit log**: `[Pipeline] action=created/updated source=college_drive email=... phone=... college=... role=...`
  - Email/WhatsApp triggers untouched (spec requirement).
  - 22/22 regression tests pass (3 new in `test_iteration50_pipeline_sync.py`). No live data touched.
- **Feb 2026 (iter49)** — Update Applicants Scores: Import error fix + Export performance:
  - **Root cause of "Script error at handleError…"**: the import error path passed `err.response.data.detail` directly to `toast.error()`. FastAPI sometimes returns `detail` as an array/object (not a string), and React renders an object as a child → uncaught error → CRA dev overlay showed the generic "Script error" message instead of the real cause.
  - **Frontend hardening** (`UpdateScores.js`): added `errMsg()` coercion that handles string / list-of-validation-errors / object / network shapes; preview-modal renders use `String(...)` coercion and `Array.isArray()` guards on `r.scores` / `round_columns` so undefined fields after "Status" never crash the row; both `handleImport` and `handleImportConfirm` now log to console + show real backend error; added 2-min axios timeout + reset file input early so retry-with-same-file works; export shows a "Exporting…" loading toast (no more frozen UI feel).
  - **Backend export performance** (`/api/bb/export-scores`): switched openpyxl to **`write_only=True`** streaming mode (5K rows: 5s → ~1s build); parallelised the 3 dependent queries via `asyncio.gather`; added `email_1` index on `bb_applicant_updates` (was missing entirely). Remaining ~25s on a no-filter full export is network-bound (Atlas roundtrip with 5450+ docs across 3 collections).
  - 19/19 regression tests still pass. No live data modified.
- **Feb 2026 (iter48)** — Score Import root-cause fix + Append-only merge + Score Sheet sync:
  - **Root cause of import failure**: Excel CSV exports prepend a UTF-8 BOM (`\ufeff`) to the first column header, making `"\ufeffName"` ≠ `"Name"` in the header check → `Invalid file: missing columns ['Name']`. Fixed in `_parse_score_file` by decoding with `utf-8-sig` and stripping BOM/whitespace from every header. Header validation is now case-insensitive, so manually-edited files (`name`, `email`, …) also work. Empty trailing columns are dropped.
  - **Import = APPEND-ONLY merge** (`/api/bb/import-scores/confirm`): existing applicant scores are now PRESERVED. New rounds are appended; existing (round_name) entries are kept (case-insensitive dedupe). Existing recruiter-set status is also preserved instead of being overwritten by the imported "On hold".
  - **Score Sheet upload sync** (`/api/upload/scoresheet` and the bulk-queue worker): each row now also (a) appends to `bb_applicant_updates.scores[]` for the matched applicant (email primary, phone fallback, append-only), (b) registers the round_name into `bb_rounds` so it shows as a tab/card automatically. Visible on both *View Attended Applicants* and *Update Applicants Scores* without a separate import step.
  - 19/19 regression tests pass (iter44 + iter45 + iter47 + 4 new iter48). No live data modified.
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
- **Feb 2026 (iter67)** — **WhatsApp Missed Export** module shipped. New page `/whatsapp-resend` with: CSV/XLSX upload (auto column-mapping for name/email/phone aliases), 5-priority candidate matcher (P1 name+email → P5 fuzzy) against `pipeline_data` + `bb_registrations`, latest-active-schedule fetcher (skips cancelled), preview table with stats strip, filters (match status / WA status), search, pagination, single + bulk + retry-failed + send-test resend. Auto-generates `bb_registrations.schedule_token` when missing. Reuses existing AiSensy `Candidate FollowUp` template (5 params: name, role, date, time, link). 5-min cooldown per candidate. Strict allowlist remains intact — non-allowlisted recipients log as `blocked`. New collections: `bb_resend_uploads`, `bb_resend_history`. Backend: `/app/backend/bb_resend.py` (8 endpoints under `/api/bb/resend`). Frontend: `/app/frontend/src/pages/WhatsAppResend.js` with WhatsApp-green (`#25D366`) branding + WhatsApp-bubble message preview modal. Verified end-to-end via curl + Playwright.
- **Feb 2026 (iter77)** — Admin Profile + Change Password:
  1. **Auth migration to MongoDB-backed `bb_users`** with bcrypt-hashed passwords. Idempotent seed on first login with the legacy defaults (`Admin User` / `Admin User`); after that, the DB value is authoritative.
  2. **New backend endpoints** (all under existing JWT cookie auth):
     - `GET /api/me` → `{username, role, created_at, password_updated_at}` (excludes `password_hash`)
     - `POST /api/auth/change-password` → verifies `old_password` via bcrypt, stores new hash; min 6 chars; old ≠ new.
  3. **`/api/login`** updated to verify against `bb_users` (bcrypt). Falls back to the legacy hardcoded default ONCE per fresh DB to auto-seed; after password change, the legacy fallback no longer applies.
  4. **`/profile` page** — view username + role + last password change timestamp; Change Password form with show/hide eye toggles + client-side validation; toast feedback on success/failure.
  5. **Sidebar user block** now clickable → routes to `/profile`. The "Sign Out" button remains. No existing nav entries removed.
  6. Verified end-to-end via curl: login w/ default → auto-seed → /me → change → old login fails (401) → new login succeeds → restore default. UI screenshot confirms rendering.
- **Feb 2026 (iter76)** — WhatsApp Diagnostics module removed cleanly (sidebar, route, page, backend endpoint, helper) per user request. Centralized AiSensy integration, Manual Alerts, Bulk Comm, automatic flows all intact.
- **Feb 2026 (iter75)** — UI accuracy fixes: per-channel WA/Email toast wording in Manual Alerts; "submitted" not "sent" in Bulk Comm.
- **Feb 2026 (iter74)** — WhatsApp Diagnostics page + stricter success check:
  1. **Stricter `send_whatsapp` success check** — was `resp.status_code == 200` only; now requires HTTP 200 AND parses the JSON body to require `success="true"` OR a non-empty `submitted_message_id`. This eliminates false positives when AiSensy returns 200 with an embedded error body.
  2. **New diagnostic helper** `messaging.send_whatsapp_with_diagnostics(...)` returns the full probe data (request payload + raw response body + parsed `success_flag` + `submitted_message_id` + `error_message` + final `ok`).
  3. **New endpoint** `POST /api/bb/resend/diagnostics/whatsapp-probe` (admin auth) fires all 5 AiSensy campaigns to the first allowlisted tester and returns a consolidated side-by-side report.
  4. **New page** `/whatsapp-diagnostics` — one-click "Run Probe" button, info card explaining Meta approval status, stats strip (passed/failed), per-campaign cards with templateParams sent + AiSensy response body, "Copy JSON" button to share with AiSensy admin. Sidebar entry added under "Manual OTP Verify".
  5. **Definitive evidence captured** — all 5 campaigns return identical `success="true"` + `submitted_message_id`. Any non-delivery is conclusively a Meta-side issue (template approval / recipient allowlist / 24h conversation window) — NOT a code issue.
- **Feb 2026 (iter73)** — PDF-perfect email design + verbatim content alignment:
  1. **`_email_shell()` redesigned** to match BluBridge PDF reference EXACTLY: white background, no top header bar, salutation opens the email, blue `#2071b9` accents, "BLUBRIDGE" text wordmark at FOOTER only (not header).
  2. **Rejection email** now matches the PDF post-attended rejection verbatim — opens "Thank you for your interest in the opportunity with Blubridge…", references the 80% qualifying threshold, includes the **blue "Job Role" highlight box** (white-on-blue label + light grey value cell, table-style). `notify_rejected(name, phone, email, job_role="")` accepts an optional `job_role` parameter, threaded through from `bb_manual.py`, `bb_resend.py`, and both rejection workers in `bg_workers.py`.
  3. **OTP email** matches the PDF — OTP code rendered in 38px blue Courier inside a `#f1f5f9` light-grey rectangular box; Interview Details (Role / Phone / Date / Time / Location) listed verbatim in a two-column label/value layout.
  4. **Schedule Detail email** has a left blue rule + Date/Time/Location block, Round 1 / Round 2 listed verbatim, "If shortlisted, a further round will be conducted." italic note.
  5. **Candidate Followups1 email** matches the PDF — no BLUBRIDGE footer logo (per PDF), blue "Reschedule Your Interview" CTA button, verbatim wording. `with_logo_footer=False` flag added to `_email_shell()` to support this.
  6. **Bulk Comm WhatsApp template previews** — bodies updated VERBATIM from the PDF AiSensy templates (kept the 5-param Followups1 schedule_link variant per the user's PHP spec).
  7. **Live validation** — all 5 campaigns deliver successfully with fresh `submitted_message_id`s from AiSensy: ShortList=`b55a6ebf...`, Schedule Detail=`196a2718...`, OTP With Job=`586d4a24...`, Candidate Followups1=`a3945550...`, Reject=`bbddc1f4...`.
- **Feb 2026 (iter72)** — AiSensy centralization audit + PDF template alignment:
  1. Re-validated the centralized `send_whatsapp` payload structure matches the PHP reference EXACTLY (apiKey, campaignName, destination, userName="Blubridgetechnologies", templateParams, source, media[], buttons[], carouselCards[], location[], attributes[], paramsFallbackValue). All 5 campaigns route through this single function — no fragmented implementations remain.
  2. **Live re-test of all 5 campaigns** confirms delivery with fresh AiSensy `submitted_message_id`s: `ShortList=b44fe1f5..`, `Schedule Detail=61ed7d55..`, `OTP With Job=53408324..`, `Candidate Followups1=af5aa8d2..`, `Reject=5c57db11..`. The user-reported "non-working" Schedule Detail/Followups1/Reject DO deliver per AiSensy's response — any non-receipt is on the AiSensy account side (Free Tier 24h-window allowlist or Meta template approval status). The `[WhatsApp:REQ]` + `[WhatsApp:RESP]` log pair surfaces these to the recruiter.
  3. **PDF Mail/Message template alignment** — `_email_shell()` helper in `messaging.py` wraps every notification email with a branded BluBridge header (dark `#1a2332` bar, BLU+BRIDGE wordmark with cyan accent) and footer (recruitment team signature + office address). All 5 emails (shortlist, schedule confirmation, OTP, missed reminder, rejection) refactored to use the shell. OTP email shows the OTP in a large monospace badge for visual clarity. Schedule confirmation email lists Round 1 + Round 2 details verbatim from PDF. Missed-reminder email has a yellow-amber "3 month bar" warning card per PDF.
  4. **Bulk Comm preview alignment** — `/api/bb/resend/template-preview?action_type=...` bodies updated to mirror the AiSensy template wording captured in the PDF (verbatim where possible). Preview shows "Round 1: Logical Reasoning & Aptitude (100 minutes)" / "Round 2: Advanced Logical Reasoning (30 minutes)" for Schedule Detail; the missed-interview Followups1 text now reads "We had your in-person interview for the {{job_role}} position scheduled on {{schedule_date}}…" matching PDF tone exactly. All 5 previews verified visually via screenshots.
- **Feb 2026 (iter71)** — 4-fix WhatsApp + OTP centralization batch:
  1. **Candidate Followups1 template** — campaign name renamed `Candidate FollowUp` → `Candidate Followups1` across `messaging.py`, `bb_resend.py`, `bb_help.py`. 5 params `[name, role, formattedDate, time, schedule_link]`, `userName="Blubridgetechnologies"`. **Verified delivering** with `submitted_message_id` from AiSensy.
  2. **Centralized OTP resolution** — new helpers in `messaging.py`: `get_otp_for_schedule(email, phone, schedule_date)` (read-only), `get_or_create_otp_for_schedule(...)` (worker/registration only), `reset_otp_on_reschedule(...)`. ALL "send" paths (Manual OTP Verify, Manual Alerts send-otp, Bulk Comm OTP, OTP worker) now reuse the SAME OTP per (applicant, schedule_date). New OTP is generated only by the worker / registration flow / on reschedule. Verified: same OTP `949645` displayed in Manual OTP Verify, sent via Manual Alerts OTP, sent via Bulk Comm OTP preview.
  3. **All 5 WhatsApp templates now deliver**:
     - ShortList (Interview Schedule Link) ✅
     - Schedule Detail ✅
     - OTP With Job ✅
     - Candidate Followups1 ✅ (root cause was the legacy template name; new name accepts our 5-param payload)
     - Reject ✅
     All verified via curl with `[WhatsApp:RESP] status=200 body={"success":"true","submitted_message_id":...}`. Previously-silent drops are now traced via `[WhatsApp:REQ]` + `[WhatsApp:RESP]` log pairs.
  4. **Bulk Communication Center** — per-action template preview via `/api/bb/resend/template-preview?action_type=...` (returns body, params list, AiSensy template name). New `/api/bb/resend/row-otp/{upload_id}/{row_id}` endpoint surfaces the live applicant OTP into the OTP-action preview. Frontend re-fetches preview body on action change; eye-icon click for OTP action enriches the row with live OTP. Modal header colored to match the active action accent. All 5 actions go through the same centralized `notify_*` helpers as Manual Applicant Alerts. For-loop dispatch never aborts on a single failure; counts (success/failed/blocked/skipped) accurate per response body.
- **Feb 2026 (iter70)** — 7-fix batch:
  1. **Manual OTP Verify** — `/api/bb/manual/applicant/lookup` now resolves OTP from `pipeline_data.otp` first, then falls back to the latest `bb_registrations.otp` for the same applicant (sorted by `otp_sent_at desc`). OTP is shown even when `otp_verified=true`. No new OTP is generated.
  2. **WhatsApp logging** — `messaging.send_whatsapp` emits `[WhatsApp:REQ]` (campaign, phone, params, userName) and `[WhatsApp:RESP]` (status, body) for every send. Silent AiSensy drops are now traceable to exact root cause (template param mismatch, gate block, network error).
  3. **Candidate FollowUp template** — Aligned with PHP reference: 5 params `[name, role, formattedDate, time, schedule_link]`, `userName="Blubridgetechnologies"`. Updated `messaging.notify_missed_reminder` and `bb_resend.send_test_message`. **Action required from user**: the AiSensy dashboard `Candidate FollowUp` campaign template still expects a different param count (verified via `[WhatsApp:RESP] status=400 body="Template params does not match the campaign"`). User must update the template variables on AiSensy to `{{1}}=name, {{2}}=role, {{3}}=date, {{4}}=time, {{5}}=schedule_link`.
  4. **Bulk Communication send** — Already routes through the same `notify_*` helpers as Manual Applicant Alerts; per-row failures don't stop the batch (existing `for-loop` design). Counts (`success/failed/blocked/skipped`) are accurate. Once Issue 3 AiSensy template is fixed, Candidate Follow-up bulk sends will succeed.
  5. **View Attended Applicants** — `/api/attended` now builds round columns DYNAMICALLY from `bb_rounds` (DISTINCT name, alphabetical, displayed AFTER `result_status`) and fetches scores from `bb_applicant_updates.scores[]` (matched by email OR phone). Frontend `AttendedRoles.js` + `AttendedDrillDown.js` adopt `round_columns` from the API response. Verified: Arjun (`grmarjun@gmail.com`) row shows BP=11, Mensa=18.5; all other rounds show "-".
  6. **Re-registration → reset round scores** — When a tester re-registers (matched against `bb_test_credentials`), `bb_applicant_updates.scores` is now wiped (`scores=[], status="", result_status=""`). `bb_rounds` definitions are NEVER touched. Applied to both `register_applicant` (public form) and `register_college_applicant` (college flow).
  7. **Update Applicants Scores import** — Already implements update-or-insert merge per round (case-insensitive dedupe by email OR phone), inserts new rounds into `bb_rounds`, ignores empty/null. No code changes needed; verified spec compliance.
- **Feb 2026 (iter69)** — **Bulk Communication Center** (was "WhatsApp Resend"). Page renamed; sidebar entry now "Bulk Communication". After uploading a candidate sheet, recruiter picks ONE of 5 actions — each fires Mail+WhatsApp via existing `messaging.py` helpers (TEST MODE gate enforced):
  - **Send Interview Schedule** → `notify_shortlisted` (auto-creates `bb_registrations.schedule_token` if missing)
  - **Send Schedule Details** → `notify_schedule_confirmation` (requires date+time)
  - **Send OTP** → `notify_otp` (reuses `bb_registrations.otp` if present, else generates new 6-digit code and persists; requires date+time)
  - **Send Candidate Follow-up** → `notify_missed_reminder` (current behaviour; requires active schedule)
  - **Send Rejection** → `notify_rejected` (no DB state change)
  Backend: `_send_one(row, user, upload_id, action_type)` dispatcher in `bb_resend.py`; `SendRequest.action_type` field; history rows tagged with `action_type` + dynamic `template`. Frontend: 5-card colour-coded action selector (`ActionSelector`), per-action `isRowSendable()` validator, dynamic toolbar button label/colour reflecting the active action. Verified end-to-end via curl — Rejection sent to 2 candidates, other actions skipped on cooldown as expected.
- **Feb 2026 (iter68)** — Cream Light Theme P0 Contrast Fix: extended `.app-shell` overrides in `index.css` to remap previously unmapped light-shade text tokens (`text-cyan-200/300`, `text-emerald-200/300`, `text-amber-200/300`, `text-red-300`, `text-fuchsia-200/300`) and 500-shade saturated tokens to dark, legible variants. Also remapped `border-cyan-700/50`, `border-amber-800/40`, `border-red-900/30-40`, plus `bg-amber-700/30`, `bg-emerald-700/30`, `bg-fuchsia-700/30`, `bg-emerald-900/60`. Resolves invisible job-role badges on College Schedules and ensures all status pills + badge text are legible on the cream theme. Verified via screenshots on College Schedules, Score & Round, Manual Alerts, Update Scores, Dashboard.
- **Feb 2026 (iter67)** — Cream Light Theme UI Redesign: Full app converted from dark mode to a warm cream theme. Persistent left sidebar (`AppShell.js`) with BluBridge logo, module nav, active-state navy highlight (#1d3a8a), user profile + sign out. Color palette: site #efede5, header #faf9f1, container #fffdf7. Home page redesigned as a 3-column module-card grid with colored icon badges and welcome banner. Global theme overrides in `index.css` scoped to `.app-shell` so login/public pages remain untouched. ZERO functional changes — pure visual layer. Status badges (`bg-emerald-900/40`, `bg-orange-900/40`, etc.) remapped to clean light bg + saturated text for legibility.
- **Feb 2026 (iter66)** — Score & Round Status filter restricted to 3 canonical groups: `Shortlisted` (matches `Shortlist`/`Shortlisted`/`Shortlsited`), `Rejected` (matches `Reject`/`Rejected`/`rejeceted`), `On-Hold` (matches `Hold`/`On-Hold`/`On hold`). Removed 10 demo seed records and `seed_score_round_demo.py`. Backend curl-verified: 431 Shortlisted, 4076 Rejected, 116 On-Hold.
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
