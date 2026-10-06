"""
Iteration 31: Validate /api/summary refactor to pipeline-first aggregation.
- /api/summary.total_registered ≈ 100798 (HR pipeline_data total), NOT 19913 (JOIN view).
- /api/data/classification.total_registered must equal /api/summary.total_registered.
- /api/applicants still returns 19913-backed pagination (unchanged contract).
- pipeline_data records have 5 new derived fields (_college_status, _nirf_category,
  _college_resolved, _match_confidence, _normalized_job_role).
- Collection counts unchanged: pipeline_data=100798, naukri_applies=35469,
  registered_candidates=19913.
"""
import os
import time
import pytest
import requests
from motor.motor_asyncio import AsyncIOMotorClient

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
USERNAME = "Admin User"
PASSWORD = "Admin User"

# Expected baselines from problem statement
EXP_PIPELINE_TOTAL = 100798
EXP_NAUKRI_TOTAL = 35469
EXP_REGISTERED_JOIN = 19913
EXP_UNREGISTERED = 15555


# ------------------- fixtures -------------------
@pytest.fixture(scope="session")
def client():
    s = requests.Session()
    r = s.post(
        f"{BASE_URL}/api/login",
        json={"username": USERNAME, "password": PASSWORD},
        timeout=15,
    )
    assert r.status_code == 200, f"Login failed: {r.status_code} {r.text}"
    # Cookie is auto-persisted in session
    return s


# ------------------- /api/summary -------------------
class TestSummaryTopLevel:
    def test_summary_top_level_counts(self, client):
        t0 = time.time()
        r = client.get(f"{BASE_URL}/api/summary", timeout=30)
        elapsed = time.time() - t0
        assert r.status_code == 200, r.text
        assert elapsed < 10, f"Summary took {elapsed:.2f}s (>10s SLA)"
        data = r.json()

        # Must include new pipeline-first totals
        assert "total_registered" in data
        assert "total_naukri" in data
        assert "total_unregistered_naukri" in data

        tr = data["total_registered"]
        tn = data["total_naukri"]
        tu = data["total_unregistered_naukri"]

        # total_registered must be pipeline-based (~100798), NOT JOIN view (19913)
        assert tr != EXP_REGISTERED_JOIN, (
            f"total_registered={tr} matches 19913 JOIN view — refactor not applied!"
        )
        assert abs(tr - EXP_PIPELINE_TOTAL) <= 500, (
            f"total_registered={tr}, expected ~{EXP_PIPELINE_TOTAL} (+/-500)"
        )
        assert abs(tn - EXP_NAUKRI_TOTAL) <= 500, (
            f"total_naukri={tn}, expected ~{EXP_NAUKRI_TOTAL}"
        )
        assert abs(tu - EXP_UNREGISTERED) <= 500, (
            f"total_unregistered_naukri={tu}, expected ~{EXP_UNREGISTERED}"
        )

    def test_per_row_sum_equals_top_level(self, client):
        r = client.get(f"{BASE_URL}/api/summary", timeout=30)
        assert r.status_code == 200
        data = r.json()
        rows = data.get("data") or data.get("rows") or []
        assert rows, f"No rows in summary: keys={list(data.keys())}"

        # Sum per-row total_registered
        row_sum = sum(int(row.get("total_registered", 0)) for row in rows)
        top_level = int(data["total_registered"])
        # Allow small drift for "other/unknown" bucket handling
        assert abs(row_sum - top_level) <= max(5, top_level * 0.02), (
            f"Sum of per-row total_registered={row_sum}, top-level={top_level}"
        )

    def test_per_row_schema(self, client):
        r = client.get(f"{BASE_URL}/api/summary", timeout=30)
        data = r.json()
        rows = data.get("data") or data.get("rows") or []
        assert rows
        sample = rows[0]
        # job_role must be formatted '<role> - <NIRF|Non NIRF>'
        jr = sample.get("job_role", "")
        assert " - " in jr, f"job_role missing ' - ' separator: {jr!r}"
        tail = jr.rsplit(" - ", 1)[-1].strip()
        assert tail in ("NIRF", "Non NIRF"), f"unexpected tail bucket: {tail!r}"

        # Required funnel fields
        for key in ("total_registered", "total_naukri", "total_unregistered",
                    "shortlisted", "rejected", "scheduled", "attended"):
            assert key in sample, f"missing key {key} in row; keys={list(sample.keys())}"


class TestSummaryFilters:
    def test_summary_date_filter_200(self, client):
        r = client.get(
            f"{BASE_URL}/api/summary",
            params={"startDate": "2026-01-01", "endDate": "2026-12-31"},
            timeout=30,
        )
        assert r.status_code == 200
        data = r.json()
        assert "total_registered" in data

    def test_summary_search_filter(self, client):
        r = client.get(f"{BASE_URL}/api/summary", params={"search": "AI"}, timeout=30)
        assert r.status_code == 200
        rows = r.json().get("data") or r.json().get("rows") or []
        for row in rows:
            assert "ai" in row.get("job_role", "").lower(), (
                f"search=AI returned non-matching role: {row.get('job_role')}"
            )


# ------------------- /api/data/classification consistency -------------------
class TestClassificationConsistency:
    def test_classification_matches_summary(self, client):
        cls = client.get(f"{BASE_URL}/api/data/classification", timeout=20).json()
        summ = client.get(f"{BASE_URL}/api/summary", timeout=30).json()

        assert cls["total_registered"] == summ["total_registered"], (
            f"classification.total_registered={cls['total_registered']} != "
            f"summary.total_registered={summ['total_registered']}"
        )
        # Allow key name tolerance
        unreg_cls = cls.get("total_unregistered")
        unreg_sum = summ.get("total_unregistered_naukri")
        assert unreg_cls == unreg_sum, (
            f"classification.total_unregistered={unreg_cls} != "
            f"summary.total_unregistered_naukri={unreg_sum}"
        )

    def test_classification_absolute_counts(self, client):
        cls = client.get(f"{BASE_URL}/api/data/classification", timeout=20).json()
        assert abs(cls["total_registered"] - EXP_PIPELINE_TOTAL) <= 500
        assert abs(cls.get("total_unregistered", 0) - EXP_UNREGISTERED) <= 500


# ------------------- /api/applicants unchanged -------------------
class TestApplicantsUnchanged:
    def test_applicants_pagination_still_19913(self, client):
        r = client.get(f"{BASE_URL}/api/applicants",
                       params={"page": 1, "limit": 10}, timeout=20)
        assert r.status_code == 200
        data = r.json()
        total = data.get("total") or data.get("totalRecords") or 0
        # Must be JOIN-backed (~19913), NOT pipeline total
        assert abs(total - EXP_REGISTERED_JOIN) <= 500, (
            f"/api/applicants total={total}, expected ~{EXP_REGISTERED_JOIN} "
            f"(JOIN view must remain unchanged)"
        )
        rows = data.get("data") or data.get("rows") or []
        assert len(rows) <= 10


class TestLegacyUnchanged:
    def test_job_roles_200(self, client):
        r = client.get(f"{BASE_URL}/api/job-roles", timeout=15)
        assert r.status_code == 200
        body = r.json()
        assert isinstance(body, (list, dict))

    def test_attended_200(self, client):
        r = client.get(f"{BASE_URL}/api/attended",
                       params={"page": 1, "limit": 10}, timeout=15)
        assert r.status_code == 200


# ------------------- Funnel sanity -------------------
class TestFunnelSanity:
    def test_largest_role_funnel_monotonic(self, client):
        data = client.get(f"{BASE_URL}/api/summary", timeout=30).json()
        rows = data.get("data") or data.get("rows") or []
        assert rows
        top = max(rows, key=lambda r: int(r.get("total_registered", 0)))
        tr = int(top["total_registered"])
        sh = int(top.get("shortlisted", 0))
        sc = int(top.get("scheduled", 0))
        at = int(top.get("attended", 0))
        assert sh <= tr, f"shortlisted({sh}) > total_registered({tr}) for {top.get('job_role')}"
        assert sc <= sh, f"scheduled({sc}) > shortlisted({sh}) for {top.get('job_role')}"
        assert at <= sc, f"attended({at}) > scheduled({sc}) for {top.get('job_role')}"


# ------------------- DB-level data safety + derived fields -------------------
@pytest.fixture
async def mongo_db():
    mongo_url = os.environ.get("MONGO_URL")
    db_name = os.environ.get("DB_NAME")
    assert mongo_url and db_name, "MONGO_URL/DB_NAME missing"
    mclient = AsyncIOMotorClient(mongo_url)
    try:
        yield mclient[db_name]
    finally:
        mclient.close()


@pytest.mark.asyncio
async def test_collection_counts_unchanged(mongo_db):
    pipeline_count = await mongo_db.pipeline_data.count_documents({})
    naukri_count = await mongo_db.naukri_applies.count_documents({})
    reg_count = await mongo_db.registered_candidates.count_documents({})
    assert abs(pipeline_count - EXP_PIPELINE_TOTAL) <= 500, (
        f"pipeline_data count={pipeline_count} (expected ~{EXP_PIPELINE_TOTAL})"
    )
    assert abs(naukri_count - EXP_NAUKRI_TOTAL) <= 500, (
        f"naukri_applies count={naukri_count} (expected ~{EXP_NAUKRI_TOTAL})"
    )
    assert abs(reg_count - EXP_REGISTERED_JOIN) <= 500, (
        f"registered_candidates count={reg_count} (expected ~{EXP_REGISTERED_JOIN})"
    )


@pytest.mark.asyncio
async def test_pipeline_derived_fields_backfilled(mongo_db):
    # 4 classification-critical fields must be at 100% (or very near).
    # _match_confidence is CONDITIONAL — only set for pipeline rows that match
    # a naukri row on email/phone. Not all pipeline rows have naukri twins.
    critical = ["_college_status", "_nirf_category", "_college_resolved",
                "_normalized_job_role"]
    total = await mongo_db.pipeline_data.count_documents({})
    for f in critical:
        n = await mongo_db.pipeline_data.count_documents({f: {"$exists": True, "$ne": None}})
        coverage = n / total if total else 0
        assert coverage >= 0.99, (
            f"Derived field {f} only at {n}/{total}={coverage:.1%} (expected >=99%)"
        )
    # _match_confidence just needs to EXIST on >=50% (matched-rows subset).
    mc = await mongo_db.pipeline_data.count_documents(
        {"_match_confidence": {"$exists": True}}
    )
    assert mc / total >= 0.50, f"_match_confidence field coverage={mc}/{total} too low"


@pytest.mark.asyncio
async def test_pipeline_spot_check_has_original_plus_derived(mongo_db):
    # 4 fields must be non-null; _match_confidence must at least EXIST as a key
    non_null_required = ["_college_status", "_nirf_category", "_college_resolved",
                         "_normalized_job_role"]
    doc = await mongo_db.pipeline_data.find_one({"_normalized_job_role": {"$ne": None}})
    assert doc, "No pipeline_data doc with _normalized_job_role found"
    original_candidates = ["email", "phone", "name", "candidate_name",
                           "job_role", "college", "last_update"]
    present_originals = [k for k in original_candidates if k in doc]
    assert present_originals, f"Spot doc missing original fields; keys={list(doc.keys())}"
    for f in non_null_required:
        assert f in doc and doc[f] is not None, f"Derived field missing/null: {f}"
    assert "_match_confidence" in doc, "_match_confidence key missing from doc"
    assert doc["_nirf_category"] in ("NIRF", "Non NIRF"), (
        f"Unexpected _nirf_category: {doc['_nirf_category']!r}"
    )
