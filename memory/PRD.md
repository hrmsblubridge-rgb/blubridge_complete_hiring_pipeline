# PRD — BluBridge Hiring Website · AI Calling Module

## Product goal
Hiring website (React + FastAPI + MongoDB) scheduling offline interviews. AI Calling module
(Bolna) handles pre-interview confirmation + OTP-based missed-interview follow-up. Real dispatch
is gated behind independent safety controls; preview is strictly mock-only.

## Non-negotiable safety invariants
- Preview Mongo: `hiring_ai_testing` only. Never `hr_analytics` (production).
- `AI_CALLING_ENABLED=false`, `ENABLE_EMAIL=false`, `ENABLE_WHATSAPP=false` in preview.
- Emergency Stop ON · AI Live OFF · Live Dispatch Authorization OFF · `test_calling_permitted` OFF.
- No real Bolna POST /call, WhatsApp/email, retention deletion, or production deploy.
- Never modify AiSensy, email, employee OTP, booking/rescheduling, or recruitment logic.
- Admin authorization NEVER writes `ai_candidate_consents`.

## Architecture snapshot
- Backend package `backend/ai_calling/`: `router`, `calls`, `candidates`, `provider`, `modes`,
  `gate`, `dispatch`, `dryrun`, `live_prep`, `retention`, `consent`, `purposes`, `execution`,
  `store`, `bolna_client`, `admin_auth`, **`safety_flags`** (new).
- Mounted at `/api/ai-calling`. Admin auth via session cookie + `X-CSRF-Intent: ai-calling` header.
- Frontend: 6 tabs — Dashboard · Testing · Live · Pending Authorization · Call History · Settings.
- Shared frontend state: `useSafetyStatus.js` (single-flight, dedup, retry-threshold).

## Collections (owned by this module)
- Existing: `ai_call_settings`, `ai_test_candidates`, `ai_test_batches`, `ai_call_jobs`,
  `ai_calls`, `ai_call_audit`, `ai_provider_settings`, `ai_provider_audit`, `ai_webhook_events`,
  `ai_candidate_consents`.
- Added by Slice 3: `ai_admin_authorizations`, `ai_admin_authorization_audit`,
  `ai_consent_drafts`, `ai_consent_versions`.
- All additive. No existing document schema altered.

## What's implemented
### Slice 1 — unified authoritative safety status
Backend `/safety-status`, hardened `/emergency-stop` (separated engage/release timestamps, typed
confirmation on release, idempotent, audited). Shared frontend hook, sticky `GlobalEmergencyStopBar`,
new `Settings → Safety Controls` panel.

### Slice 2 — Testing Mode UX
Rewritten `CallingControls.jsx` with guided readiness counts, pipeline indicator, duplicate-click
guard. Stop Calls button is hidden when no active job/batch exists (Stage A3).

### Slice 3 — Pending Authorization + Consent Editor + Capacity + Preview
Backend `admin_auth.py` with purpose-scoped bulk review, append-only audit, consent drafts +
immutable versions (publish restricted to `Admin User`), capacity summary, and 15 synthetic
preview scenarios covering both purposes.

### Slice 4 — Live Mode redesign
Three sections: Eligible / Automatic Calling Queue / Preview & Diagnostics. Both workflows shown.

### Stage A fixes (this session)
- **A1 reliability**: `useSafetyStatus` now uses AbortController, module-level request dedup, and
  a 2-failure threshold before flipping to `authoritative=false`. Keeps last-known-good data on
  transient errors. Rapid tab navigation no longer flips the Pending Authorization page to
  "Safety status unavailable".
- **A2 merge**: single `CandidateConsentSection` combines published view + draft editor + inline
  booking-form preview + version/audit history. Draft and published states are visually distinct.
  Old `ConsentPreview` + `ConsentEditorPanel` removed from Settings.
- **A3 Stop Calls**: button only renders when `hasActive` (blocking call OR active jobs/batch).
  A neutral hint replaces it otherwise, with a pointer to Emergency Stop in Safety Controls.
- **A4 UX regression**: loading indicators, success/error toasts, and section-level locking
  consistent across Save Settings, Test Connection, Call Now, Publish Consent, Stop Calls,
  Bulk Review, and Emergency Stop engage/release.

### Stage B readiness
- **B1**: both purposes preserved (confirm 1–7d, retry +60m, 10–19 IST; missed 1h–7d, retry +30m,
  10–19:30 IST, OTP revalidated at every stage).
- **B2**: employee OTP flow untouched.
- **B3**: isolated dispatch tests cover accepted, rejected, timeout, idempotent replay, and
  Emergency-Stop cancellation — all via mocked Bolna client (no real POST /call).
- **B4**: new `test_calling_permitted` setting (defaults OFF, server-enforced in `safety_flags`,
  cannot unlock Live). Flipping test-only ON permits Test-Mode calling only; Live still blocked.
- **B5**: Bolna agent read-only verification is already wired in `/provider/test-connection`.
  Number-to-agent entitlement cannot be verified by public Bolna APIs; documented as a Release-2
  prerequisite (`PRODUCTION_READINESS.md §7`).

### Stage C preview validation
- **C1**: 15 synthetic scenarios (5 confirmation + 10 missed) covering all 4 OTP interpretations,
  reschedule, DNC, running-late, claims-attended, no-answer retry, calling-window edges.
- **C2**: 500-synthetic-job queue test — all retained, earliest-due ordered, pilot-cap non-destructive.
- **C3**: Pending Authorization already tested for past/DNC/withdrawn exclusion + policy +
  evidence requirements.
- **C4**: full suite green.

## Final regression
**Backend: 219 passed, 17 skipped** across all 16 ai_calling test files (phase 2 → 7cb1 +
Slice 1/234 + Stage BC + webhook + two-purposes + extraction-edge + bolna-11-fields).
Frontend compiles cleanly.

## Stage D (prepared, NOT executed)
See `memory/PRODUCTION_READINESS.md` for:
1. Production DB preservation (hr_analytics untouched).
2. Render config checklist + required env vars (names only).
3. Additive migration plan with idempotent index creation.
4. Four-release strategy (code deploy → single test call → limited pilot → full ops).
5. Rollback via feature flags only (never DB deletion).

## Known limitations
- No verified Bolna per-recording deletion endpoint; retention stays preview-only.
- Number-to-agent entitlement not verifiable via public Bolna APIs.
- Admin alternative-basis authorization UI is built but actual dispatch requires a separately
  approved policy + `LIVE_DISPATCH_IMPLEMENTED=True` + `live_dispatch_authorized=True`.
