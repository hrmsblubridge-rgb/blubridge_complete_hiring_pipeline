# iter85 QA Checklist — Production-Safe Pass (TEST_MODE=OFF)

> **Testers used (only):** `rajlearn06@gmail.com` / `8883847098` · `rishi.nayak@blubridge.com` / `9443109903`
> **Zero production-applicant rows touched.**
> **Zero notifications sent to real applicants.**

---

## 🔧 Root Cause + Fix — Reschedule "already attended" bug

**Root cause:** iter82's `manual_otp_reschedule_verify` mirrored `otp_verified=True` to **every** `bb_registrations` row matching `email|phone` via `update_many` — 26 historical rows for `rajlearn06@gmail.com` got polluted. When the public reschedule link loaded by `schedule_token`, it landed on a polluted row → HTTP 409 "You have already attended the interview".

**Fixes:**
- `bb_manual.manual_otp_reschedule_verify` — replaced broad `update_many` with `update_one` scoped to the MOST RECENT row (`sort=[('registered_at', -1)]`). Historical cycles are no longer rewritten.
- One-shot data cleanup on tester rows only: 26 polluted `rajlearn06` rows + 21 `rishi.nayak` rows reset to `otp_verified=False`. Zero real-applicant rows touched.
- `bb_modules.schedule_interview` (public POST) — replaced its local `_to_24h` (which fell back to storing raw text) with the centralized `to_24h_db`; malformed time now returns HTTP 400 instead of persisting `"BANANA"`.
- One-shot data cleanup: reset the single `schedule_time=BANANA` row that the QA pass had created.

---

## 📋 Test Checklist (17 cases, all PASS)

| ID  | Area                     | Test                                                              | Expected         | Actual           | Status |
| --- | ------------------------ | ----------------------------------------------------------------- | ---------------- | ---------------- | ------ |
| A1  | Public Form              | `GET /api/pub/form/ai-ml-college-placement-form`                  | returns `id`     | id returned      | ✅ PASS |
| B1  | Schedule / Reschedule    | `POST /pub/schedule/{token}` valid future slot                    | HTTP 200         | HTTP 200         | ✅ PASS |
| B2  | Schedule guards          | Past date+time slot                                               | HTTP 400         | HTTP 400         | ✅ PASS |
| B3  | Schedule guards          | Malformed time `"banana"` **(FIXED iter85)**                      | HTTP 400         | HTTP 400         | ✅ FIXED |
| B4  | Schedule freshness       | `GET /pub/schedule/{token}` shows latest 24h time                 | `14:30:00`       | `14:30:00`       | ✅ PASS |
| C1  | **Reschedule block**     | `otp_verified=True` on the matching row blocks reschedule         | HTTP 409         | HTTP 409         | ✅ PASS |
| C2  | **No-false-block**       | Stale historical rows on the same email/phone do NOT block (iter85) | HTTP 200 on fresh token | HTTP 200    | ✅ FIXED |
| D1  | Manual Alerts            | `GET /manual/applicant/lookup?email=…`                            | tester row       | tester returned  | ✅ PASS |
| E1  | Reschedule&Verify        | UI sends `"03:30 PM"` → DB persists `15:30:00`                    | 24h stored       | `15:30:00`       | ✅ PASS |
| E2  | Reschedule&Verify        | Malformed time rejected (iter83)                                  | HTTP 400         | HTTP 400         | ✅ PASS |
| F1  | Missing Applicants       | Pagination `page=2&limit=25` returns 25 rows                      | 25 rows          | 25 rows          | ✅ PASS |
| F2  | Missing Applicants       | CSV export streams ALL filtered rows                              | HTTP 200, CSV    | 247 KB CSV       | ✅ PASS |
| F3  | Missing Applicants       | XLSX export streams ALL filtered rows                             | HTTP 200, XLSX   | 49 KB XLSX       | ✅ PASS |
| G1  | Score & Round            | Tester appears after Reschedule&Verify (when result_status=Shortlisted) | total=1 | total=1          | ✅ PASS |
| H1  | Update Applicants Scores | `/api/bb/attended-for-scores` returns tester                      | tester returned  | tester returned  | ✅ PASS |
| I1  | View Attended            | Round columns are dynamically built + unique                      | 15 unique cols   | 15 unique cols   | ✅ PASS |
| J1  | TEST_MODE                | `/api/messaging/status`                                           | `test_mode:false`| `test_mode:false`| ✅ PASS |
| K1  | Auth                     | `/api/me` after login                                             | `Admin User`     | `Admin User`     | ✅ PASS |

---

## Edge-Case Coverage (already shipped + verified earlier this session)

- iter78: AI/ML interstitial gated by Show-Instruction-Page toggle
- iter79: View Attended round dedup (whitespace+case); Manual Alerts button rules (4 always-enabled, Reject only when Attended); past-time slot disabling
- iter80: Schedule-link Email + WhatsApp dispatched in **3 s** (was 5 min)
- iter81: TEST_MODE OFF + cutoff bumped to 2026-05-11T18:30 → zero historical replay (worker queues = 0)
- iter82: Manual OTP Verify Reschedule & Verify
- iter83: `schedule_time` stored as strict `HH:MM:SS`; display heuristic fixes 9904 legacy mis-stored rows on-the-fly; Missing Applicants pagination
- iter84: `job_role` + `job_title` + `_normalized_job_role` synced; `bb_applicant_updates` / `score_sheet` re-linked on email/phone change

---

## Manual UI Spot-Checks Still Recommended (User Verification)

- [ ] Tester reschedule via the actual public link → confirm no 409 "already attended" appears when `otp_verified` is false on the matching row.
- [ ] Manual OTP Verify → Reschedule & Verify a tester → land on Score & Round, confirm new schedule + new role appear.
- [ ] View Attended Applicants → confirm round columns are deduped (no `Accounts1` and `Accounts 1` simultaneously) and PM slots display as `01:00 PM`-`05:00 PM`.
- [ ] Missing Applicants page → pagination `<<` `<` `>` `>>` and Go input behave; Export downloads ALL filtered rows.
- [ ] Bulk Communication Center previews — verify 12-hour AM/PM in the WhatsApp + Mail preview cards.

---

## Cleanup Confirmation

- All tester rows reverted to neutral state at end of QA run.
- All polluted `otp_verified=True` legacy rows on testers cleaned.
- The single `schedule_time=BANANA` corruption (created by QA test B3 before the fix) reset to `14:30:00`.
- Zero real-applicant rows touched throughout. **TEST_MODE remains OFF.**
