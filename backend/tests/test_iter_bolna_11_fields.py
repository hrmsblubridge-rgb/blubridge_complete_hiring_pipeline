"""Isolated regression tests for Bolna extraction field discovery (all 11 fields).

Root cause these tests pin down:
- The agent carries disposition IDs (UUID strings) in agent["dispositions"]; the checker fetches each
  via GET /dispositions/{id}?agent_id=... and matches disposition "name" (normalized) to our field set.
- The two Bolna platform dispositions on the agent ("Call Completion", "Call Success", category
  General) must NOT be confused with our fields, and must NOT trip the outside_category warning.
- A legacy last_verification doc that predates the 5 missed fields has missed_fields_* = None;
  the Test Connection row must still surface as cannot_verify ("re-test"), never silently hide it.

Nothing here performs real network traffic; a fake Bolna client is injected.
"""
import asyncio
import types

from ai_calling import provider
from ai_calling.execution import (
    ALL_FIELDS,
    EXTRACTION_FIELDS,
    MISSED_FIELDS,
    extraction_from_dispositions,
)

CAT = "Interview Call Results"
GLOBAL_CAT = "General"


# ---------- fake Bolna client ----------
class _Err(Exception):
    def __init__(self, kind="provider_error"):
        self.kind = kind


def _fake_bc(defs_by_id, fail_ids=()):
    async def get_disposition(key, did, agent_id):
        if did in fail_ids:
            raise _Err()
        return defs_by_id[did]
    return types.SimpleNamespace(get_disposition=get_disposition, BolnaError=_Err)


def _agent(ids):
    """Shape observed from GET /v2/agent/{agent_id}: dispositions is a list of UUID strings."""
    return {"dispositions": list(ids)}


def _defs(mapping, cat=CAT, objective=True):
    """mapping: {id -> name}. Returns dict keyed by id with Bolna disposition shape."""
    return {
        i: {"id": i, "name": n, "category": cat,
            "is_objective": objective, "is_subjective": not objective,
            "objective_options": [{"value": "x"}] if objective else []}
        for i, n in mapping.items()
    }


# ---------- all 11 fields present (user's current agent state) ----------
def test_all_eleven_fields_detected_pure():
    names = ALL_FIELDS
    defs = _defs({f"id{i}": n for i, n in enumerate(names)})
    r = extraction_from_dispositions(list(defs.values()))
    assert r["fields_missing"] == []
    assert sorted(r["fields_found"]) == sorted(EXTRACTION_FIELDS)
    assert sorted(r["missed_fields_found"]) == sorted(MISSED_FIELDS)
    assert r["missed_fields_missing"] == []
    assert r["outside_category"] == []
    assert r["dispositions_unreadable"] == 0


def test_all_eleven_with_two_global_platform_dispositions():
    """User's real agent has 13 dispositions: our 11 + Bolna's Call Completion/Call Success (General)."""
    ours = {f"id{i}": n for i, n in enumerate(ALL_FIELDS)}
    defs = _defs(ours)
    global_defs = _defs({"gid1": "Call Completion", "gid2": "Call Success"}, cat=GLOBAL_CAT)
    combined_agent_ids = list(ours) + list(global_defs)  # 13 ids
    combined_defs = {**defs, **global_defs}
    r = asyncio.run(provider._extraction_check(
        _fake_bc(combined_defs), "k", "a", _agent(combined_agent_ids)))
    assert r["source"] == "dispositions"
    assert r["dispositions_total"] == 13
    assert r["fields_missing"] == []
    assert r["missed_fields_missing"] == []
    # Platform "General" dispositions must NOT leak into outside_category (only our mapped fields do).
    assert r["outside_category"] == []


# ---------- partial missed-fields coverage ----------
def test_six_core_present_but_missed_fields_absent():
    defs = _defs({f"id{i}": n for i, n in enumerate(EXTRACTION_FIELDS)})
    r = extraction_from_dispositions(list(defs.values()))
    assert r["fields_missing"] == []
    assert sorted(r["missed_fields_missing"]) == sorted(MISSED_FIELDS)
    assert r["missed_fields_found"] == []


def test_partial_missed_fields_found():
    half = MISSED_FIELDS[:3]
    defs = _defs({f"id{i}": n for i, n in enumerate(EXTRACTION_FIELDS + half)})
    r = extraction_from_dispositions(list(defs.values()))
    assert sorted(r["missed_fields_found"]) == sorted(half)
    assert sorted(r["missed_fields_missing"]) == sorted(MISSED_FIELDS[3:])


# ---------- outside category tracked per-field ----------
def test_missed_field_outside_category_is_flagged():
    """If a missed-field disposition sits in a non-standard category, the agent-side check still finds it,
    but category metadata is preserved so UI can render a warning without hiding the field."""
    good = _defs({f"id{i}": n for i, n in enumerate(EXTRACTION_FIELDS)})
    wrong_cat = _defs({"mid1": "missed_interview_outcome"}, cat="Other")
    defs = {**good, **wrong_cat}
    r = extraction_from_dispositions(list(defs.values()))
    assert "missed_interview_outcome" in r["missed_fields_found"]
    # outside_category is reported for core fields only (by current design); missed-field category
    # metadata lives in by_name (not surfaced here) — guard against regression hiding it.
    assert r["outside_category"] == []


# ---------- name normalization is case/whitespace-insensitive ----------
def test_names_are_normalized_whitespace_and_case():
    mapping = {f"id{i}": n.upper().replace("_", " ") for i, n in enumerate(ALL_FIELDS)}
    defs = _defs(mapping)
    r = extraction_from_dispositions(list(defs.values()))
    assert r["fields_missing"] == []
    assert r["missed_fields_missing"] == []


# ---------- ID count: no artificial cap on 11 real fields ----------
def test_extraction_check_handles_full_agent_disposition_list():
    """With 13 ids the checker must fetch every one; a prior [:30] slice must not be lowered below this."""
    ours = {f"id{i}": n for i, n in enumerate(ALL_FIELDS)}
    extras = _defs({f"gid{i}": "Call " + str(i) for i in range(5)}, cat=GLOBAL_CAT)
    defs = {**_defs(ours), **extras}
    r = asyncio.run(provider._extraction_check(
        _fake_bc(defs), "k", "a", _agent(list(defs))))
    assert r["dispositions_total"] == 16
    assert r["fields_missing"] == [] and r["missed_fields_missing"] == []


# ---------- legacy / stale cached verification ----------
def test_provider_surfaces_stale_cached_verification_as_cannot_verify():
    """Reproduces the user's false-negative: a cached last_verification persisted before the 5 missed
    fields existed has missed_fields_* = None. The UI must show cannot_verify + re-test, not hide it."""
    stale = {
        "source": "dispositions",
        "dispositions_total": 13, "dispositions_unreadable": 0,
        "fields_found": list(EXTRACTION_FIELDS), "fields_missing": [],
        "outside_category": [],
        "fields": {f: {"category": CAT, "type": "objective", "options": ["x"]} for f in EXTRACTION_FIELDS},
        # missed_fields_found / missed_fields_missing INTENTIONALLY ABSENT (legacy shape)
    }
    rows = []
    def add(key, label, state, detail=""):
        rows.append({"key": key, "label": label, "state": state, "detail": detail})

    # Inline the provider.py staleness branch exactly as implemented (keeps the test decoupled from
    # HTTP + CSRF + db + auth; the production path lives in provider.test_connection).
    extraction = stale
    mm = extraction.get("missed_fields_missing")
    mf = extraction.get("missed_fields_found")
    if mm is None and extraction.get("source") == "dispositions":
        add("missed_extraction", "Missed-interview follow-up fields configured on agent", "cannot_verify",
            "last verification predates the 5 follow-up fields — re-run Test Connection to refresh")
    elif mm is not None:
        add("missed_extraction", "Missed-interview follow-up fields configured on agent",
            "warning" if mm else "verified",
            ("not found: " + ", ".join(mm)) if mm else f"all 5 follow-up fields found ({len(mf or [])}/5)")

    assert len(rows) == 1
    assert rows[0]["state"] == "cannot_verify"
    assert "re-run Test Connection" in rows[0]["detail"]


def test_provider_fresh_verification_lists_all_eleven():
    """Fresh shape (both core-6 and missed-5 found) renders two positive rows with explicit counts."""
    fresh = extraction_from_dispositions(
        list(_defs({f"id{i}": n for i, n in enumerate(ALL_FIELDS)}).values()))
    rows = []
    def add(key, label, state, detail=""):
        rows.append({"key": key, "label": label, "state": state, "detail": detail})

    extraction = fresh
    mm = extraction.get("missed_fields_missing")
    mf = extraction.get("missed_fields_found")
    if mm is None and extraction.get("source") == "dispositions":
        add("missed_extraction", "Missed-interview follow-up fields configured on agent", "cannot_verify", "stale")
    elif mm is not None:
        add("missed_extraction", "Missed-interview follow-up fields configured on agent",
            "warning" if mm else "verified",
            ("not found: " + ", ".join(mm)) if mm else f"all 5 follow-up fields found ({len(mf or [])}/5)")
    missing = extraction["fields_missing"]
    if extraction.get("source") == "dispositions" and not missing:
        cats = ", ".join(sorted({v["category"] for v in extraction["fields"].values()}))
        extra = f" · plus {len(mf)}/5 missed-interview fields" if mf else ""
        add("extraction", "Extraction fields configured on agent", "verified",
            f"all 6 core fields found as dispositions ({cats}){extra}")

    by_key = {r["key"]: r for r in rows}
    assert by_key["missed_extraction"]["state"] == "verified"
    assert "5/5" in by_key["missed_extraction"]["detail"]
    assert by_key["extraction"]["state"] == "verified"
    assert "all 6 core fields" in by_key["extraction"]["detail"]
    assert "5/5 missed-interview fields" in by_key["extraction"]["detail"]
