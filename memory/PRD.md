# PRD — BluBridge Hiring Website · AI Calling Module

## Product goal
Hiring website (React + FastAPI + MongoDB) that schedules and verifies offline interviews, with an
AI Calling module (Bolna provider) covering (a) pre-interview confirmation and (b) OTP-based
missed-interview follow-up. Real dispatch is gated behind multiple independent safety controls;
preview is strictly mock-only.

## Non-negotiable safety invariants
- Preview Mongo: `hiring_ai_testing` only. Never `hr_analytics` (production).
- `AI_CALLING_ENABLED=false`, `ENABLE_EMAIL=false`, `ENABLE_WHATSAPP=false` in preview.
- Emergency Stop ON. AI Live OFF. Live Dispatch Authorization OFF.
- No real Bolna POST /call, no WhatsApp/email/SMS, no retention deletion, no production deploy.
- Never modify AiSensy, email, employee OTP verification, booking/rescheduling, or recruitment logic.
- Test records link only by `ai_test_candidates._id`; live by `bb_registrations._id`. Never cross-link.
- Provider API key/webhook secret encrypted at rest; never returned to frontend or logged.

## Architecture snapshot
- Backend: FastAPI, Motor async Mongo, package `backend/ai_calling/`
  (`router`, `calls`, `candidates`, `provider`, `modes`, `gate`, `dispatch`, `dryrun`, `live_prep`,
  `retention`, `consent`, `purposes`, `execution`, `store`, `bolna_client`, **`admin_auth`**).
- Mounted at `/api/ai-calling`. Admin auth via `_auth` (session cookie).
- Frontend: React (CRA + craco). **Six top-level tabs** under `/ai-calling/*`:
  Dashboard · Testing Mode · Live Mode · **Pending Authorization** · Call History · Settings.
- Shared frontend state: `useSafetyStatus.js` polls `/safety-status` every 15 s.

## Collections owned by this module
- `ai_call_settings`, `ai_test_candidates`, `ai_test_batches`, `ai_call_jobs`, `ai_calls`, `ai_call_audit`
- `ai_provider_settings`, `ai_provider_audit`, `ai_webhook_events`
- `ai_candidate_consents` (candidate-authored; immutable per candidate)
- `ai_admin_authorizations` (admin alternative-basis; never overwrites candidate consent)
- `ai_admin_authorization_audit` (append-only audit trail)
- `ai_consent_drafts` (editable; single doc `_id='current'`)
- `ai_consent_versions` (immutable published versions)
- Existing hiring collections (`bb_registrations`, etc.) are read-only from this module.

## What's implemented
### Slice 1 — unified safety status (prior commit)
Authoritative `/safety-status` endpoint, hardened `/emergency-stop` with separated engage/release
timestamps + typed-confirmation release + audit. Shared frontend hook, sticky `GlobalEmergencyStopBar`
on every tab, new `Settings → Safety Controls` panel. Dashboard contradictory text fixed.

### Slice 2 — Testing Mode UX
Rewritten `CallingControls.jsx`:
- Guided readiness header shows selected / eligible / blocked counts.
- Status message surfaces exactly which gate is blocking (from `/safety-status`), never guesses.
- Call pipeline indicator (checking → submitting → accepted) with spinner.
- Duplicate-click protection via `useRef` in-flight guard.
- Button supports single and bulk (eligible count included in label). Zero selected disables.
- Loading, success and error states on every action.

### Slice 3 — Pending Authorization, Consent Editor, Capacity, Preview
Backend `admin_auth.py`:
- `GET /api/ai-calling/pending-authorization` — future valid bookings only; excludes past,
  cancelled, superseded, replaced, Do-Not-Call, withdrawn. Returns per-registration coverage
  (candidate_scopes + granted_scopes → uncovered_purposes).
- `POST /api/ai-calling/pending-authorization/review` — bulk decisions (approve/defer/deny).
  Approve requires `policy_id` + `evidence_ref`. Per-record revalidation (booking still valid,
  no DNC/withdrawal). NEVER writes to `ai_candidate_consents`. Dispatch stays blocked.
- `GET /api/ai-calling/pending-authorization/audit` — append-only audit history.
- `GET /api/ai-calling/consent/editor` + `POST /consent/editor/draft` — open to any admin.
- `GET /api/ai-calling/consent/versions`, `POST /api/ai-calling/consent/publish` — publish is
  gated to the top-level admin (`Admin User`) and requires typed `PUBLISH CONSENT VERSION`.
  Published versions are immutable; existing consents keep the version originally accepted.
- `GET /api/ai-calling/capacity-summary` — explicit effective-daily explanation.
- `GET /api/ai-calling/preview/scenarios` — 5 confirmation + 10 missed-interview synthetic
  scenarios covering all 4 OTP states (unverified, verified, missing_blocked, verified_just_now).

Frontend: new tab + page `pages/ai-calling/PendingAuthorization.js` (filters, per-page select,
clear selection, bulk-review dialog with purpose-scoping and required evidence for approve).
Settings adds `CapacitySummaryPanel` and `ConsentEditorPanel`. New `PreviewScenariosPanel`.

### Slice 4 — Live Mode redesign
`LiveMode.js` reorganised into three clear sections: Eligible Candidates / Automatic Calling Queue /
Preview & Diagnostics. Shows both workflows side-by-side with purpose-specific timing, retry
and window. Activate Live Mode button remains disabled (phase-locked).

### Verification
- **Backend regression: 217 passed, 17 skipped** across all AI Calling tests including the new
  `test_slice234_pending_consent.py` (7 isolated tests: past/DNC/withdrawn exclusion, approve
  requires evidence, consent never touched, top-level-admin publish, immutability, draft
  validation, capacity shape, preview covers both purposes with all OTP states).
- Frontend compiled cleanly (webpack compiled successfully).
- Live backend curl: `/capacity-summary`, `/pending-authorization`, `/preview/scenarios`,
  `/consent/editor`, `/safety-status` all return the expected shapes. Safety state UNCHANGED:
  `emergency_stop=True`, `test_can_call=False`, `live_can_call=False`, provider v16 untouched.

## Authorization model
RBAC + ownership + publishing permission (single admin app). All admin routes protected by the
existing `_auth` dependency (deny-by-default). `admin_auth.publish_version` adds a second check:
`principal == TOP_LEVEL_ADMIN`. CSRF header required on all POSTs. Audit-logs every decision.

## Known limitations / do-not-retry
- No verified Bolna single-call recording/transcript deletion endpoint; retention deletion remains
  preview-only.
- Alternative-basis authorization UI is built but actual dispatch remains unavailable until a
  separately approved policy is activated.
- No automatic Live dispatch worker running. `Activate Live Mode` button is intentionally disabled.

## Roadmap
All approved slices (1–4) are now delivered pending user review. Further scope requires explicit
new approval. Nothing proceeds to real calling or production deployment automatically.
