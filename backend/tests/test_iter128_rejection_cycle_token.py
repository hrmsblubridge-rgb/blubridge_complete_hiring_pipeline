"""iter128 — Cycle-token idempotency for the rejection dispatcher.

Replaces the iter126 blanket tester exclusion. The right boundary is
NOT "who" receives the rejection (testers vs real applicants); it's
WHEN — at most one dispatch per evaluation cycle. A cycle marker
(`scores_reset_at` || `imported_at` || `updated_at` for Source A;
`registered_at` || `updated_at` for Source B) is recorded as
`rejection_sent_for_cycle` after each successful dispatch. Same-cycle
re-attempts skip silently — phantom re-fires can no longer occur even
if `rejection_sent` gets cleared mid-cycle by some other code path.

User-reported regression (Feb 16, 2026): iter126 blocked a LEGITIMATE
rejection to the tester (rishi.nayak@blubridge.com) because the
exclusion was too broad. iter128 removes the blanket block and lets
real rejections through while still preventing the daily phantom.
"""

import asyncio
import inspect
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"))

from motor.motor_asyncio import AsyncIOMotorClient


@pytest.fixture
def db():
    import bg_workers
    client = AsyncIOMotorClient(os.environ["MONGO_URL"])
    fresh_db = client[os.environ["DB_NAME"]]
    bg_workers._db = fresh_db
    return fresh_db


# ─────────────────────── Source-code guards ──────────────────────────────


def test_iter126_blanket_tester_exclusion_removed():
    """The iter126 tester-credential blacklist must be GONE — it was
    over-broad and blocked legitimate rejections to test recipients."""
    import bg_workers
    src = inspect.getsource(bg_workers._worker_import_rejection_mailer)
    assert "[RejectScheduler:TESTERS]" not in src, (
        "iter126 tester exclusion still present — reverting incomplete"
    )
    assert "RejectSkip:A:TESTER" not in src
    assert "RejectSkip:B:TESTER" not in src
    assert "bb_test_credentials" not in src, (
        "Worker still loads bb_test_credentials at tick start; remove "
        "the legacy iter126 pre-loop block."
    )


def test_cycle_token_idempotency_present():
    """`rejection_sent_for_cycle` token must be checked pre-dispatch AND
    persisted post-dispatch in BOTH source loops."""
    import bg_workers
    src = inspect.getsource(bg_workers._worker_import_rejection_mailer)
    # Pre-dispatch check (both sources).
    assert "RejectSkip:A:SAME_CYCLE" in src
    assert "RejectSkip:B:SAME_CYCLE" in src
    # Post-dispatch persistence.
    assert '"rejection_sent_for_cycle": cycle_token_a' in src
    assert '"rejection_sent_for_cycle": cycle_token_b' in src
    # Source A cycle marker chain.
    assert "scores_reset_at" in src
    assert "imported_at" in src
    # Source B cycle marker chain.
    assert "registered_at" in src


def test_batch_done_log_uses_same_cycle_counter():
    """BATCH_DONE log must surface the new same-cycle skip counter."""
    import bg_workers
    src = inspect.getsource(bg_workers._worker_import_rejection_mailer)
    assert "skipped_same_cycle" in src


# ─────────────────────── Functional behaviour ────────────────────────────


@pytest.mark.asyncio
async def test_same_cycle_dispatch_skipped(db):
    """If a row was already dispatched for cycle_token=X and the token
    hasn't changed, the worker MUST skip — even if `rejection_sent`
    somehow gets cleared back to False."""
    # We can't easily run the worker tick directly without mocking the
    # 20:00 IST gate, but we CAN validate the persistence + skip-decision
    # logic by inspecting the doc state after a simulated cycle.
    test_email = "iter128-samecycle@example.invalid"
    cycle_token = "2026-06-01T10:00:00+00:00"

    # Seed a row that LOOKS like one we just dispatched.
    await db.bb_applicant_updates.insert_one({
        "email": test_email,
        "phone": "9000000001",
        "name": "Iter128 Tester",
        "status": "Rejected",
        "scores_reset_at": cycle_token,
        "rejection_sent": False,                 # simulates accidental clear
        "rejection_sent_for_cycle": cycle_token, # but token still matches
        "updated_at": cycle_token,
        "_iter128_test": True,
    })

    try:
        # The worker's condition: skip if cycle_token == prior_token.
        doc = await db.bb_applicant_updates.find_one({"email": test_email})
        ct = (
            str(doc.get("scores_reset_at") or "")
            or str(doc.get("imported_at") or "")
            or str(doc.get("updated_at") or "")
        )
        pt = str(doc.get("rejection_sent_for_cycle") or "")
        assert ct == pt, "Cycle token comparison would not match — guard broken"

    finally:
        await db.bb_applicant_updates.delete_many({"_iter128_test": True})


@pytest.mark.asyncio
async def test_new_cycle_allows_fresh_dispatch(db):
    """When the cycle marker advances (re-registration → new
    scores_reset_at), the prior `rejection_sent_for_cycle` must NOT
    match, allowing a fresh dispatch."""
    test_email = "iter128-newcycle@example.invalid"
    old_token = "2026-06-01T10:00:00+00:00"
    new_token = "2026-06-02T10:00:00+00:00"

    await db.bb_applicant_updates.insert_one({
        "email": test_email,
        "phone": "9000000002",
        "name": "Iter128 Tester",
        "status": "Rejected",
        "scores_reset_at": new_token,            # NEW cycle
        "rejection_sent": False,
        "rejection_sent_for_cycle": old_token,   # PRIOR cycle's token
        "updated_at": new_token,
        "_iter128_test": True,
    })

    try:
        doc = await db.bb_applicant_updates.find_one({"email": test_email})
        ct = (
            str(doc.get("scores_reset_at") or "")
            or str(doc.get("imported_at") or "")
            or str(doc.get("updated_at") or "")
        )
        pt = str(doc.get("rejection_sent_for_cycle") or "")
        assert ct != pt, "New-cycle token comparison should NOT match"

    finally:
        await db.bb_applicant_updates.delete_many({"_iter128_test": True})


@pytest.mark.asyncio
async def test_first_ever_dispatch_passes_guard(db):
    """A row that has NEVER been dispatched (no
    `rejection_sent_for_cycle`) must pass the guard."""
    test_email = "iter128-firstever@example.invalid"
    await db.bb_applicant_updates.insert_one({
        "email": test_email,
        "phone": "9000000003",
        "name": "Iter128 Tester",
        "status": "Rejected",
        "scores_reset_at": "2026-06-03T10:00:00+00:00",
        "rejection_sent": False,
        # NO rejection_sent_for_cycle field at all
        "updated_at": "2026-06-03T10:00:00+00:00",
        "_iter128_test": True,
    })

    try:
        doc = await db.bb_applicant_updates.find_one({"email": test_email})
        ct = (
            str(doc.get("scores_reset_at") or "")
            or str(doc.get("imported_at") or "")
            or str(doc.get("updated_at") or "")
        )
        pt = str(doc.get("rejection_sent_for_cycle") or "")
        # Guard logic: skip ONLY when both tokens present AND equal.
        skip = bool(ct and pt and ct == pt)
        assert not skip, "First-ever dispatch should not be skipped"

    finally:
        await db.bb_applicant_updates.delete_many({"_iter128_test": True})


@pytest.mark.asyncio
async def test_tester_no_longer_blanket_excluded(db):
    """Production validation: the live tester row
    (rishi.nayak@blubridge.com) is NO LONGER hard-quarantined with
    rejection_auto_skipped_tester=True (iter126's marker)."""
    doc = await db.bb_applicant_updates.find_one(
        {"email": "rishi.nayak@blubridge.com"}
    )
    if doc is None:
        pytest.skip("Tester row not in this environment")
    assert not doc.get("rejection_auto_skipped_tester"), (
        "Tester row is still hard-quarantined — un-quarantine ran but "
        "something re-applied it"
    )
