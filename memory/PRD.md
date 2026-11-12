# PRD — BluBridge Hiring Website · AI Calling Module

## Product goal
Hiring website (React + FastAPI + MongoDB) that schedules and verifies offline interviews, with an
**AI Calling** module (Bolna provider) that places (a) pre-interview confirmation calls and
(b) OTP-based missed-interview follow-up calls. All real dispatch is gated behind multiple safety
controls; preview is strictly mock-only.

## Non-negotiable safety invariants (never relaxed)
- Preview Mongo: `hiring_ai_testing` only. **Never** `hr_analytics` (production).
- `AI_CALLING_ENABLED=false`, `ENABLE_EMAIL=false`, `ENABLE_WHATSAPP=false` in preview.
- Emergency Stop ON. AI Live OFF. Live Dispatch Authorization OFF. No real dispatch worker running.
- No real Bolna `POST /call`, no WhatsApp/email/SMS, no retention deletion, no production deploy.
- Never modify AiSensy, email, employee OTP verification, booking/rescheduling, or recruitment logic.
- Test records link only by `ai_test_candidates._id`; live by `bb_registrations._id`. Never cross-link.
- Provider API key/webhook secret encrypted at rest, never returned to frontend or logged.

## Architecture snapshot
- Backend: FastAPI, Motor async Mongo, package `backend/ai_calling/`
  (`router`, `calls`, `candidates`, `provider`, `modes`, `gate`, `dispatch`, `dryrun`, `live_prep`,
  `retention`, `consent`, `purposes`, `execution`, `store`, `bolna_client`).
- Mounted at `/api/ai-calling`. Admin auth via `_auth` (session cookie).
- Frontend: React (CRA + craco), 5 top-level tabs under `/ai-calling/*`:
  Dashboard · Testing Mode · Live Mode · Call History · Settings. A sixth **Pending Authorization** tab
  is planned for Slice 3 (not yet implemented).
- Shared frontend state: `components/ai-calling/useSafetyStatus.js` polls `/safety-status` every 15 s.

## What's implemented (through current session)
### Prior phases (handoff summary)
- Bolna provider configuration, encrypted key, test connection, webhook intake, webhook hardening.
- Test-colleague management, dry-run eligibility, two-scenario scheduler, extraction normalisation
  for all 11 fields (6 core + 5 missed-interview). Candidate consent + DNC. Retention preview.
- One real controlled Phase 4B test call (user-confirmed).
- Two-scenario enhancement: `purposes.py`, purpose-aware mock dispatch, hard-coded single-call lock
  replaced by real safety/eligibility gates.
- Bolna extraction verification mismatch root-caused as stale cached `last_verification`; fresh run
  recognises all 11 fields. Primary row now reports `all 6 core + 5/5 missed`.

### This session — Slice 1 (safety-status unification)
- **New** `GET /api/ai-calling/safety-status` → single authoritative source of truth consumed by all
  tabs (`router.py`). Returns `emergency_stop`, `switches`, `server`, `provider`, `effective`,
  `limits`. Falls back to `authoritative=false` + "Safety status unavailable — calling blocked."
- **Fixed** `POST /api/ai-calling/emergency-stop` (`router.py`):
  - Writes `emergency_stop_at` only on engage, `emergency_stop_released_at` only on release
    (eliminates the `_at` newer-than-`released_at` drift that caused UI inconsistency).
  - Release requires body `confirmation = "RELEASE EMERGENCY STOP"` (returns 400 otherwise).
  - Idempotent: same-state calls return current state with no audit noise.
  - Writes a dedicated `ai_call_audit` entry per transition (previous/current/reason/by/side-effects).
- **Re-engaged** Emergency Stop in `hiring_ai_testing` with audit entry (per explicit user authorization).
- **New** `components/ai-calling/useSafetyStatus.js` hook (polling + `authoritative`-aware).
- **New** `components/ai-calling/GlobalEmergencyStopBar.jsx` — sticky top bar on every AI Calling tab:
  shows ON/OFF state, exposes **Engage** action (with reason). Release is NOT in this bar.
- **New** `components/ai-calling/SafetyControlsPanel.jsx` — Settings → Safety Controls section:
  Emergency Stop block (with release action requiring typed confirmation + reason), per-gate rows
  (AI Test, AI Live, Server Outbound, Live Dispatch Authorization, Bolna provider, Emergency Stop),
  and effective-permissions summary with blocker reasons. Explicitly labels `AI_CALLING_ENABLED`
  as a deployment-level flag, not a UI switch.
- **Updated** `components/ai-calling/AICallingHeader.jsx` — header now derives mode + estop badge
  from the shared hook (no more per-page `/summary` or `/settings` copies) and renders the global bar.
- **Updated** `pages/ai-calling/AICallingDashboard.js` — contradictory text removed; now shows the
  actual Emergency Stop, Server Outbound, Live Dispatch Authorization, and Bolna provider values
  from the shared hook; adds "Safety status unavailable" state and link to Settings → Safety Controls.
- **Updated** `pages/ai-calling/AICallingSettings.js` — old Emergency Stop block replaced by the
  new `SafetyControlsPanel`; removed the standalone "Server locks" card (now a row in Safety Controls).
- **Updated** `pages/ai-calling/TestingMode.js`, `LiveMode.js` — stopped passing stale per-page
  mode/emergency props; the shared header now handles both.

### Verification (Slice 1)
- 84 backend tests pass (`test_slice1_safety_status.py` 7 new + extraction, phase 4a/4b, webhook,
  two-purposes, bolna-11-fields, extraction-edge). Frontend compiled cleanly.
- Live backend validation via curl:
  - `GET /safety-status` returns `authoritative=true`, `emergency_stop.active=true`, `engaged_by="Admin User"`,
    test-call blocked by `Emergency Stop ON` + `Server outbound disabled`, live-call blocked by 5 gates.
  - `POST /emergency-stop` without CSRF → 400.
  - `POST /emergency-stop {active:false, reason:"x"}` (no confirmation) → 400
    "Releasing Emergency Stop requires typing: RELEASE EMERGENCY STOP".
  - Repeat engage (already ON) → 200, zero new audit entries.
- Authoritative safety state at end of Slice 1: `emergency_stop=True`, AI Test ON, AI Live OFF,
  Live Dispatch Authorization OFF, `AI_CALLING_ENABLED=false`, DB `hiring_ai_testing`.

## Roadmap (approved sequencing)
- **Slice 1 — DONE** (pending user review): unified safety status, global bar, Safety Controls, contradictory-message fixes.
- **Slice 2**: Testing Mode guided Test Calling Setup, single + bulk Call Now, clear call-status
  pipeline, button/toggle UX standardisation (tasks T4, T5, T6, T7).
- **Slice 3**: new **Pending Authorization** tab, admin-authorization audit (`ai_admin_authorizations`
  + `ai_admin_authorization_audit` — new, separate from `ai_candidate_consents`), consent editor
  with top-level-admin publish, capacity UX, synthetic two-purpose preview (T2, T9, T10, T12, T14, T15).
- **Slice 4**: Live Mode redesign, automatic worker contract (still non-dispatchable), final
  regression (T8, T11, T18, T19).

## Explicit "do not" list for all future slices
- No real Bolna `POST /call`, no WhatsApp/email dispatch, no retention deletion, no production deploy.
- Do not create duplicate candidate/booking/consent records.
- Do not overwrite `ai_candidate_consents` from admin screens; admin alternative-basis authorization
  lives in a separate collection.
- Do not auto-approve legacy candidates in bulk; keep real alternative-basis authorization blocked
  from dispatch until an approved policy is configured through a separate authorized process.
- Do not add an `Ignore Consent` toggle anywhere in the UI.

## Dead-ends / do-not-retry ledger (carry-forward)
- Do not reconnect preview to `hr_analytics` (caused 36 WhatsApp + 36 emails in the past).
- Do not reinstall full `backend/requirements.txt` (nonexistent `cx==1.2.0` breaks it).
- Do not use `GET /v2/agent/{agent_id}/extractions` on Bolna (returned 404). Use per-id
  `GET /dispositions/{id}?agent_id=…`.
- Expect dispositions on the agent as a flat list of UUID strings. The dispositions-list endpoint
  `/dispositions/?agent_id=…` returns `{agent_dispositions, global_dispositions}`.
- 13 total dispositions on the live agent = 11 ours (6 core + 5 missed, Interview Call Results)
  + 2 Bolna-managed (`Call Completion`, `Call Success` under `General`).
