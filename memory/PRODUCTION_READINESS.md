# AI Calling · Production Readiness Plan

> **Status**: PLAN ONLY — no production migrations run, no real calls placed,
> no live deployment performed as part of this task. All actions below are
> gated on explicit written user approval.

## 1. Non-negotiable preview-time invariants (currently enforced)
| Control | Enforced where | Default |
|---|---|---|
| `MONGO_DB_NAME` | `backend/.env` | `hiring_ai_testing` only |
| `AI_CALLING_ENABLED` | `backend/.env` | `false` |
| `ENABLE_WHATSAPP` / `ENABLE_EMAIL` | `backend/.env` | `false` |
| `emergency_stop` | `ai_call_settings` | `true` |
| `live_calling_stop` (**new**) | `ai_call_settings` | `true` |
| `test_calling_permitted` | `ai_call_settings` | `false` |
| `ai_live_enabled` | `ai_call_settings` | `false` |
| `live_dispatch_authorized` | `ai_call_settings` | `false` |
| `LIVE_DISPATCH_IMPLEMENTED` | `modes.py` constant | `False` |
| `BOLNA_INTEGRATION_APPROVED` | `gate.py` constant | `False` |

None of the above may be relaxed in the same change-set that bumps a release.

## 2. Independent admin-editable gates (Stage E)
Two switches editable from the admin UI, both audited and independently enforced
in `router.safety_status`, `modes.calling_status`, `modes.evaluate_live`,
`safety_flags.py` and `gate.py`:

| Switch | Blocks | Does NOT touch | Enabling requires |
|---|---|---|---|
| Global Emergency Stop | Test **and** Live | — | Live (already shipped) |
| **Live Calling Stop** | Live only | Test Mode | Live (new) |
| **Test Calling Permitted** | Test only | Live Mode | Typed `PERMIT TEST CALLING` |

Release-direction phrases:
- `RELEASE EMERGENCY STOP` — release global stop.
- `RELEASE LIVE CALLING STOP` — release Live-only stop.
- `PERMIT TEST CALLING` — grant Test-only outbound.

Engage/revoke directions require **no** phrase (fail-safe direction).

Gate identity is **strict**: a value other than exactly `True` for Test permission,
or anything other than exactly `False` for either Stop, is treated as "blocked".
Regression suites: `test_live_calling_stop_endpoints.py` + `test_independent_safety_switches_api.py` +
`test_test_calling_permitted_enforcement.py`.

## 3. Production database preservation — `hr_analytics`
- Do **not** reuse the preview database name. Production env must set
  `MONGO_DB_NAME=hr_analytics` directly on the host and nowhere else.
- Migration is **additive**. No `drop`, no `rename`, no `update_many` without
  `$setOnInsert`.
- Collections owned by this module (safe to create on first boot):
  `ai_call_settings`, `ai_test_candidates`, `ai_test_batches`, `ai_call_jobs`,
  `ai_calls`, `ai_call_audit`, `ai_provider_settings`, `ai_provider_audit`,
  `ai_webhook_events`, `ai_candidate_consents`, `ai_admin_authorizations`,
  `ai_admin_authorization_audit`, `ai_consent_drafts`, `ai_consent_versions`,
  `ai_upload_batches`.
- Existing production collections (`bb_registrations`, `bb_users`, booking flows,
  AiSensy, email OTP) are **read-only** from this module. Grep of
  `backend/ai_calling/` shows zero writes outside the collections above.
- No synthetic preview record is ever to be copied into production.

## 4. First-boot migration (idempotent)
`ensure_ai_indexes()` runs on startup and is safe to re-run. It:
1. Creates every index listed in §3 (idempotent in MongoDB).
2. Runs a one-time `$set` on `ai_call_settings` filtered by
   `ai_test_enabled: {"$exists": False}` — upgrades a legacy install exactly once.
3. `get_settings()` inserts the safe defaults from §1 via `$setOnInsert`, so an
   existing document is **never** overwritten.

Expected state on a fresh production boot:
```
{ "_id": "global",
  "emergency_stop": true,
  "live_calling_stop": true,
  "test_calling_permitted": false,
  "ai_test_enabled": true,  "ai_live_enabled": false,
  "live_dispatch_authorized": false,
  "mode_version": 2 }
```

## 5. Render / deployment checklist (env-var names only; values not stored here)
| Variable | Purpose | Required |
|---|---|---|
| `MONGO_URL` | Production cluster connection | yes |
| `MONGO_DB_NAME` | Must be `hr_analytics` | yes |
| `FRONTEND_URL` | CSRF origin whitelist | yes |
| `AI_CALLING_ENABLED` | Keep `false` until Release 2 | yes |
| `AI_LIVE_DEPLOYMENT_APPROVED` | Keep `false` until Release 3 | yes |
| `ENABLE_WHATSAPP` / `ENABLE_EMAIL` | Same policy as today | yes |
| `BOLNA_API_KEY` | Live Bolna key (set only at Release 2) | later |
| `PROVIDER_FERNET_KEY` | Required to decrypt any stored Bolna key | yes |

## 6. Four-release rollout
| # | Name | Preconditions | What changes | Safety-net |
|---|---|---|---|---|
| R1 | Code deploy, dry-only | §1 defaults in prod | Code + indexes live; `/safety-status` returns `authoritative: true`; every gate still blocks | All gates block; `AI_CALLING_ENABLED=false` |
| R2 | Single authorized Test call | `test_calling_permitted=true`, consented test recipient | Exactly one consented test number dialled via Bolna | Live Stop stays ON; Live blocked |
| R3 | Limited Live pilot | Written approval; `AI_LIVE_DEPLOYMENT_APPROVED=true`; `LIVE_DISPATCH_IMPLEMENTED=True`; `live_calling_stop=false`; `live_dispatch_authorized=true`; `live_pilot_daily_cap=5` | Pilot queue runs within cap | Engage Live Stop or Emergency Stop to abort instantly |
| R4 | Full automatic | Successful pilot; cap raised | Removed pilot cap; daily cap governs | Same aborts available |

Each release step is a **separate PR** with a **separate approval**. Do not bundle.

## 7. Rollback (feature-flag only — never DB deletion)
Escalation order:
1. Toggle **Live Calling Stop** ON → blocks new Live dispatch within one request.
2. Revoke **Test Calling Permitted** → blocks new Test dispatch.
3. Engage **Global Emergency Stop** → blocks BOTH and cancels pending jobs.
4. Set `AI_CALLING_ENABLED=false` on the host (requires redeploy).
5. If needed, flip `AI_LIVE_DEPLOYMENT_APPROVED=false`.

No step deletes rows. Audit entries in `ai_call_audit` remain for forensics.

## 8. Credential rotation
- `test_credentials.md` stores the preview admin password only. It is **not**
  copied into release packages, reports, or logs.
- Before production launch, rotate the production `Admin User` password through
  the standard reset flow and leave `test_credentials.md` pointing at a
  preview-only account.
- `BOLNA_API_KEY`, `PROVIDER_FERNET_KEY`, WhatsApp provider keys follow the
  existing secret workflow (`secrets` tool); nothing new introduced here.

## 9. What this task did and did not do
Done:
- Added two new audited admin-only endpoints and UI (Settings + Live Mode).
- Fixed drift in `router.safety_status`, `modes.calling_status`, `modes.evaluate_live`
  so every surface enforces both new flags consistently.
- Hardened `effective_test_permission` to strict-`True` identity.
- 24 new backend tests + 93 pre-existing relevant tests all green.

Not done (deliberate):
- No production DB connection, migration, or deploy executed.
- No real Bolna, WhatsApp, SMS, or email dispatch.
- No change to `AI_CALLING_ENABLED`, AiSensy, employee OTP, or booking flows.
- No password rotation performed.

**STOP point**: this plan requires explicit sign-off before any release step runs.
