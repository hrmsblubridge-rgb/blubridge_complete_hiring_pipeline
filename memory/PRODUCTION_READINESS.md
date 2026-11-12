# BluBridge Hiring Website · AI Calling — Production Readiness

**Status**: Preview-only engineering complete. No production deployment is authorized by this document.

## 1. Preserve the original production database (D1)
- Production DB: **`hr_analytics`** (on Render). Never touched by any preview code.
- Preview DB: **`hiring_ai_testing`** (Emergent). All testing runs here.
- Every backend read/write is scoped by `MONGO_URL` + `DB_NAME` from `backend/.env`. The AI Calling
  module adds **only new collections**:
    - `ai_admin_authorizations`, `ai_admin_authorization_audit`
    - `ai_consent_drafts`, `ai_consent_versions`
    - `ai_call_audit` (already existed)
  Existing hiring collections (`bb_registrations`, consent, OTP, AiSensy state) are **read-only**
  from this module. No existing document schema is altered.

## 2. Production architecture checklist (D2)
Verified in code (no production access performed):
- Render service: existing FastAPI service; no new service required. Backend served on the same
  process at `/api/ai-calling/*`.
- Environment variables that must be present in production (names only, never values):
    - `MONGO_URL` (must point to `hr_analytics`), `DB_NAME`, `JWT_SECRET`, `COOKIE_SECRET`,
      `AI_PROVIDER_ENCRYPTION_KEY`, `AI_CALLING_ENABLED` (**must be `false` on first deploy**),
      `BOLNA_API_KEY` (only if not stored encrypted in DB), `BOLNA_AGENT_ID`, `WEBHOOK_SECRET`.
- Existing `AI_TRUSTED_PROXY_HOPS` and CSRF handling are preserved.
- Existing authentication (session cookie + `X-CSRF-Intent: ai-calling` on POSTs) is preserved
  on every new route.
- Required indexes (created idempotently on startup by `ensure_admin_auth_indexes`):
    - `ai_admin_authorizations.registration_id` (unique)
    - `ai_admin_authorization_audit.(registration_id, at desc)`
    - `ai_consent_versions.version_id` (unique)
    - `ai_consent_versions.published_at`

## 3. Migration plan (D3)
Additive and idempotent:
1. Deploy new code to Render (AI_CALLING_ENABLED=false). Startup runs `ensure_admin_auth_indexes()`
   which creates the new collections lazily. **No existing collection is touched.**
2. No data backfill runs. Candidate consents that predate the new editor are visible as
   `LEGACY_UNVERIFIED` in Pending Authorization without any write.
3. Existing live bookings keep their original `registration_id`.
4. If preview/production schemas diverge in a field name later discovered during deployment,
   migration is **read-adapters only** (in `candidates.py`); no rewrite.

## 4. Release strategy (D4)
**Nothing below is executed by this task.** All require a separate explicit approval.

### Release 1 — Code deploy, calling disabled
- Pre-check: `AI_CALLING_ENABLED=false`, `ENABLE_WHATSAPP=false` NOT required in prod, but the
  AI Calling module never sends WhatsApp/email itself; it only reads candidate records.
- Deploy via Render. Verify `/api/ai-calling/safety-status` returns `authoritative=true`,
  `emergency_stop.active=true`, `effective.can_place_test_call=false`,
  `effective.can_place_live_call=false`.
- Verify existing booking flow, OTP verification and AiSensy workflow still work.
- Spot-check Pending Authorization lists real future candidates (count only, no action).

### Release 2 — Controlled single test call
- Flip `test_calling_permitted` to `true` **temporarily** via Settings → Safety Controls (new
  control; defaults OFF; server-enforced).
- Verify the specific test colleague's consent and masked phone.
- Place one call via Call Now with typed confirmation.
- Verify execution_id, webhook, transcript, recording, and all 11 extraction fields appear in
  Candidate Profile AI Calling History.
- Flip `test_calling_permitted` back to OFF immediately after.

### Release 3 — Limited Live pilot
- Legal / telecom DPDP consent review signed off.
- Set `live_pilot_daily_cap` to a small number (e.g. 10).
- Flip `live_dispatch_authorized` with typed confirmation and `AI_CALLING_ENABLED=true` (deploy
  env change).
- Monitor results, opt-outs, failures.

### Release 4 — Full automatic operation
- Remove pilot cap, let scheduler drive both purposes.
- Keep all per-call gates (consent, DNC, calling window, OTP for missed-follow-up, retries).

## 5. Rollback (D5)
- Frontend/backend: redeploy prior Render commit; new collections are harmless if left.
- Feature flags: set `AI_CALLING_ENABLED=false`; set `emergency_stop=true`; set
  `test_calling_permitted=false`; set `live_dispatch_authorized=false`. Any ONE of these
  independently stops every call.
- Queue pause: Emergency Stop cancels all `pending` jobs (`cancel_reason: emergency_stop`).
- Webhook: route remains live (idempotent record-only); no replay storm.
- Duplicate-call prevention: `idempotency_key` on `ai_calls` + unique execution_id.
- **Never use database deletion as rollback.** All new collections are additive.

## 6. Legal / compliance (remaining)
- India DPDP: confirm lawful basis + candidate-specific evidence record before approving any
  alternative-basis authorization in Pending Authorization.
- Telecom DLT/DND: verify Bolna/Plivo account has valid outbound entitlement on the purchased number.
- Recording retention: no verified Bolna per-recording delete endpoint; 90-day retention remains
  preview-only.
- Consent wording: must be published by the top-level admin after legal sign-off.

## 7. Bolna provider-side limitations
- No verified per-recording deletion endpoint.
- Agent↔calling-number association cannot be fully verified via a read-only Bolna API in all
  cases. A known-safe read: `GET /v2/agent/{agent_id}` returns `dispositions` + metadata. Number
  entitlement must be verified by a Bolna account manager or a side-channel console.
- Extraction nested under `extracted_data["Interview Call Results"]`; parser already handles this
  and all 11 fields (6 core + 5 missed-interview).

## 8. Safety invariants on every deploy
- Preview DB name in `backend/.env` must NEVER equal `hr_analytics`.
- `AI_CALLING_ENABLED` is deployment-level only; it is NOT editable from the admin UI.
- `emergency_stop`, `ai_test_enabled`, `ai_live_enabled`, `live_dispatch_authorized`,
  `test_calling_permitted` are all independent. Releasing one NEVER affects another.
- Admin alternative-basis approvals NEVER write to `ai_candidate_consents`.
