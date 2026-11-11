"""Phase 7C-B1: PROPOSED call-data retention policy (90 days) with a read-only preview.

Nothing here deletes anything: `execute` always returns 423 and no cleanup worker exists.
Policy versions: ai_retention_policies. Legal holds: ai_retention_holds. Audit: ai_call_audit (no content).
"""
from datetime import datetime, timedelta, timezone

from bson import ObjectId
from fastapi import APIRouter, Body, HTTPException, Request

from .consent import top_level_admins
from .provider import _auth, _csrf
from .store import db, now_iso

retention_router = APIRouter(prefix="/retention")
PROPOSED_DAYS = 90
DELETION_APPROVED = False  # requires separate legal/operational approval
# (path, label) — removed after the retention period. Dotted paths are nested.
SENSITIVE = [("transcript", "Full transcript"), ("recording_url", "Recording (Bolna-hosted URL reference)"),
             ("extracted_data_raw", "Raw provider extraction payload"), ("response.candidate_questions", "Candidate questions"),
             ("response.call_summary", "Call summary"), ("response.rejection_reason", "Free-text rejection reason"),
             ("response.field_meta", "Extraction field metadata (may echo free text)")]
RETAINED = ["_id (internal call ID)", "registration_id / test_candidate_id", "created_at / completed_at", "state / status",
            "response.attendance_status", "response.wants_reschedule", "response.requested_virtual", "duration_seconds",
            "minimal audit entries (action, actor, time; no content)"]
STORAGE_MAP = [
    {"where": "MongoDB ai_calls", "holds": "transcript, recording URL reference, raw + normalised extraction", "covered": True},
    {"where": "MongoDB ai_live_mock_jobs.mock_call", "holds": "simulated results only (no real content)", "covered": True},
    {"where": "MongoDB ai_webhook_events", "holds": "execution ID, status, payload hash, source IP — no transcript/recording", "covered": False},
    {"where": "MongoDB ai_call_audit", "holds": "actions and actors only — no conversation content", "covered": False},
    {"where": "Bolna (provider) execution records", "holds": "recording audio, transcript, extracted data",
     "covered": False, "note": "No documented per-execution DELETE API. Only DELETE /v2/agent/{id} (removes the whole agent and ALL its executions). Per-call deletion needs Bolna support — UNVERIFIED."},
    {"where": "Database backups / exports", "holds": "copies of ai_calls if backups or exports exist",
     "covered": False, "note": "Backup rotation must also be <= the approved period; no AI-call export feature exists."},
    {"where": "Server logs", "holds": "IDs and statuses only (transcripts are not logged)", "covered": False},
]


def _get(doc: dict, path: str):
    for part in path.split("."):
        doc = doc.get(part) if isinstance(doc, dict) else None
    return doc


def _present(v) -> bool:
    return v not in (None, "", [], {})


async def _admin(request: Request, top: bool = False) -> str:
    user = await _auth(request)
    if top and user not in top_level_admins():
        raise HTTPException(403, "Only a top-level administrator can manage retention")
    return user


async def current_policy() -> dict:
    p = await db().ai_retention_policies.find_one({}, sort=[("version", -1)])
    if not p:
        p = {"version": 1, "days": PROPOSED_DAYS, "status": "proposed", "deletion_enabled": False, "created_by": "system",
             "created_at": now_iso(), "notes": "Initial proposal — requires legal and operational review"}
        await db().ai_retention_policies.update_one({"version": 1}, {"$setOnInsert": p}, upsert=True)
        p = await db().ai_retention_policies.find_one({"version": 1})
    return {k: v for k, v in p.items() if k != "_id"}


@retention_router.get("/policy")
async def get_policy(request: Request):
    user = await _admin(request)
    hist = [{k: v for k, v in h.items() if k != "_id"} async for h in db().ai_retention_policies.find({}).sort("version", -1)]
    return {"policy": await current_policy(), "history": hist, "sensitive_fields": [lbl for _, lbl in SENSITIVE],
            "retained_fields": RETAINED, "storage_map": STORAGE_MAP, "deletion_approved": DELETION_APPROVED,
            "can_manage": user in top_level_admins(),
            "retained_basis": "Structured outcomes are kept only for interview operations and reporting; their own "
                              "retention period must also be approved — not kept indefinitely by default."}


@retention_router.post("/policy")
async def propose_policy(request: Request, body: dict = Body(...)):  # noqa: B008
    user = await _admin(request, top=True)
    _csrf(request)
    days = body.get("days")
    if not isinstance(days, int) or not 30 <= days <= 3650:
        raise HTTPException(400, "days must be a whole number between 30 and 3650")
    cur = await current_policy()
    doc = {"version": cur["version"] + 1, "days": days, "status": "proposed", "deletion_enabled": False,
           "created_by": user, "created_at": now_iso(), "notes": str(body.get("notes") or "")[:300]}
    await db().ai_retention_policies.insert_one(doc)
    await db().ai_call_audit.insert_one({"action": "retention_policy_proposed", "by": user, "detail": {"version": doc["version"], "days": days}, "at": now_iso()})
    return await get_policy(request)


async def _holds() -> set:
    return {h["call_id"] async for h in db().ai_retention_holds.find({"released_at": None}, {"call_id": 1})}


def _age_days(doc: dict, now: datetime):
    ts = doc.get("completed_at") or doc.get("created_at")
    try:
        t = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
    except ValueError:
        return None
    return (now - (t if t.tzinfo else t.replace(tzinfo=timezone.utc))).days


async def build_preview(now: datetime = None, days: int = None) -> dict:
    """Read-only: which records/fields WOULD be removed under the proposed policy. Writes nothing to call data."""
    now = now or datetime.now(timezone.utc)
    pol = await current_policy()
    days = days or pol["days"]
    holds, rows = await _holds(), []
    counts = {"records": 0, "eligible": 0, "on_hold": 0, "not_yet_due": 0, "nothing_sensitive": 0}
    async for c in db().ai_calls.find({}):
        counts["records"] += 1
        cid, age = str(c["_id"]), _age_days(c, now)
        fields = [lbl for path, lbl in SENSITIVE if _present(_get(c, path))]
        if cid in holds:
            st = "on_hold"
        elif not fields:
            st = "nothing_sensitive"
        elif age is not None and age >= days:
            st = "eligible"
        else:
            st = "not_yet_due"
        counts[st] += 1
        due = None
        if c.get("completed_at") or c.get("created_at"):
            try:
                due = (datetime.fromisoformat(str(c.get("completed_at") or c.get("created_at")).replace("Z", "+00:00")) + timedelta(days=days)).isoformat()
            except ValueError:
                due = None
        rows.append({"call_id": cid, "mode": c.get("mode"), "candidate_name": c.get("candidate_name"), "created_at": c.get("created_at"),
                     "age_days": age, "eligible_from": due, "status": st, "fields": fields,
                     "provider_copy": "Bolna execution record — provider deletion UNVERIFIED" if c.get("execution_id") else None,
                     "actions": [f"Remove {f}" for f in fields] if st == "eligible" else []})
    return {"dry_run": True, "deleted": 0, "as_of": now.isoformat(), "policy": pol, "days": days, "counts": counts, "rows": rows,
            "warning": "PREVIEW ONLY — NOTHING IS DELETED. Deletion is not approved."}


@retention_router.get("/preview")
async def preview(request: Request, days: int = None):
    user = await _admin(request)
    if days is not None and not 1 <= days <= 3650:
        raise HTTPException(400, "days must be 1–3650")
    out = await build_preview(days=days)
    await db().ai_call_audit.insert_one({"action": "retention_preview", "by": user,
                                         "detail": {"days": out["days"], **out["counts"]}, "at": now_iso()})
    return out


@retention_router.post("/holds")
async def add_hold(request: Request, body: dict = Body(...)):  # noqa: B008
    user = await _admin(request, top=True)
    _csrf(request)
    cid, reason = str(body.get("call_id") or ""), str(body.get("reason") or "").strip()[:300]
    if not ObjectId.is_valid(cid) or not await db().ai_calls.find_one({"_id": ObjectId(cid)}, {"_id": 1}):
        raise HTTPException(404, "Call not found")
    if not reason:
        raise HTTPException(400, "A reason is required for a legal hold")
    if await db().ai_retention_holds.find_one({"call_id": cid, "released_at": None}):
        raise HTTPException(409, "This call is already on hold")
    await db().ai_retention_holds.insert_one({"call_id": cid, "reason": reason, "by": user, "at": now_iso(), "released_at": None})
    await db().ai_call_audit.insert_one({"action": "retention_hold_added", "by": user, "call_id": cid, "at": now_iso()})
    return {"held": True, "call_id": cid}


@retention_router.post("/holds/{call_id}/release")
async def release_hold(call_id: str, request: Request):
    user = await _admin(request, top=True)
    _csrf(request)
    res = await db().ai_retention_holds.update_one({"call_id": call_id, "released_at": None},
                                                   {"$set": {"released_at": now_iso(), "released_by": user}})
    if not res.modified_count:
        raise HTTPException(404, "No active hold")
    await db().ai_call_audit.insert_one({"action": "retention_hold_released", "by": user, "call_id": call_id, "at": now_iso()})
    return {"held": False, "call_id": call_id}


@retention_router.post("/execute")
async def execute(request: Request):
    user = await _admin(request, top=True)
    _csrf(request)
    await db().ai_call_audit.insert_one({"action": "retention_execute_refused", "by": user, "at": now_iso()})
    raise HTTPException(423, "Retention deletion is not approved. Nothing was deleted.")
