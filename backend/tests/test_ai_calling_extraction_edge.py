"""Edge-case unit tests for extraction parsing + _extraction_check state logic (no network)."""
import asyncio
import types

from ai_calling import provider
from ai_calling.execution import normalize_extraction, EXTRACTION_FIELDS


def _r(obj=None, subj=None, status="completed"):
    return {"objective": obj, "subjective": subj, "status": status, "confidence": 0.5}


# --- parsing edge cases
def test_yes_no_unknown_variants():
    d = {"Interview Call Results": {"wants_reschedule": _r(obj="YES"), "requested_virtual": _r(obj="Unknown")}}
    r = normalize_extraction(d)
    assert r["wants_reschedule"] is True and r["requested_virtual"] is None


def test_garbage_inputs_safe():
    for bad in [None, "not json", 123, [], {"Interview Call Results": None}, {"Interview Call Results": "x"}]:
        r = normalize_extraction(bad)
        assert r["attendance_status"] == "UNKNOWN"


def test_unknown_attendance_never_confirmed():
    for v in ["unknown", "", None, "maybe", "Unclear"]:
        r = normalize_extraction({"Interview Call Results": {"attendance_status": _r(obj=v)}})
        assert r["attendance_status"] == "UNKNOWN"


def test_pending_status_returns_none():
    r = normalize_extraction({"Interview Call Results": {"call_summary": _r(subj="hi", status="pending")}})
    assert r["call_summary"] is None


# --- _extraction_check / state logic with fake bolna client
class FakeErr(Exception):
    def __init__(self, kind="provider_error"):
        self.kind = kind


def _fake_bc(defs_by_id, fail_ids=()):
    async def get_disposition(key, did, agent_id):
        if did in fail_ids:
            raise FakeErr()
        return defs_by_id[did]
    return types.SimpleNamespace(get_disposition=get_disposition, BolnaError=FakeErr)


def _defs(names, cat="Interview Call Results"):
    return {f"id{i}": {"name": n, "category": cat, "is_objective": True} for i, n in enumerate(names)}


def test_check_all_found():
    defs = _defs(EXTRACTION_FIELDS)
    r = asyncio.run(provider._extraction_check(_fake_bc(defs), "k", "a", {"dispositions": list(defs)}))
    assert r["source"] == "dispositions" and not r["fields_missing"]


def test_check_missing_readable():
    defs = _defs(EXTRACTION_FIELDS[:3])
    r = asyncio.run(provider._extraction_check(_fake_bc(defs), "k", "a", {"dispositions": list(defs)}))
    assert r["fields_missing"] == EXTRACTION_FIELDS[3:] and r["dispositions_unreadable"] == 0


def test_check_unreadable():
    defs = _defs(EXTRACTION_FIELDS)
    r = asyncio.run(provider._extraction_check(_fake_bc(defs, fail_ids=set(defs)), "k", "a", {"dispositions": list(defs)}))
    assert r["dispositions_unreadable"] == 6 and len(r["fields_missing"]) == 6


def test_check_fallback_no_dispositions():
    r = asyncio.run(provider._extraction_check(_fake_bc({}), "k", "a", {"agent_config": {"x": "attendance_status"}}))
    assert r["source"] == "agent_config" and "attendance_status" in r["fields_found"]
