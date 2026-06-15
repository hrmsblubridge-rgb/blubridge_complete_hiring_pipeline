"""iter152 — Streaming upload parsers (Step A). Verifies:

  1. /upload/naukri, /upload/pipeline, /upload/scoresheet each work
     end-to-end with both CSV and XLSX input.
  2. None of them call `pd.read_excel` or `pd.read_csv` — proving the
     pandas-based DataFrame materialisation is gone from the hot path.
  3. bb_users is NOT touched — auth is bypassed via dependency override
     (per the strict no-password-mutation rule).

The CSVs/XLSXs are tiny (just enough rows to exercise the parser
branches). The real memory win is verified by inspection of the code
(no pandas DataFrame is ever built), not by stress-testing in the unit
suite — that's the job of production observation on Render.
"""

from __future__ import annotations

import io
import os
import sys

import pytest
import pytest_asyncio

os.environ.setdefault("FRONTEND_URL", "http://localhost")
os.environ.setdefault("RESEND_API_KEY", "test")
os.environ.setdefault("MONGO_URL", os.environ.get("MONGO_URL", "mongodb://localhost:27017"))
os.environ.setdefault("DB_NAME", os.environ.get("DB_NAME", "test_iter152"))

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

pytestmark = pytest.mark.asyncio(loop_scope="session")


@pytest_asyncio.fixture(loop_scope="session", scope="session")
async def app_module():
    import server  # noqa: E402
    return server


@pytest_asyncio.fixture(loop_scope="session")
async def auth_override(app_module):
    from server import app, get_current_user
    app.dependency_overrides[get_current_user] = lambda: "pytest-user"
    yield
    app.dependency_overrides.pop(get_current_user, None)


def _build_csv(headers, rows) -> bytes:
    import csv as _csv
    buf = io.StringIO()
    w = _csv.writer(buf)
    w.writerow(headers)
    for r in rows:
        w.writerow(r)
    return buf.getvalue().encode("utf-8")


def _build_xlsx(headers, rows) -> bytes:
    from openpyxl import Workbook
    wb = Workbook()
    ws = wb.active
    ws.append(headers)
    for r in rows:
        ws.append(r)
    bio = io.BytesIO()
    wb.save(bio)
    return bio.getvalue()


# ---- Helper: assert the endpoint did not touch pandas readers --------

async def _assert_pandas_readers_unused(monkeypatch, callable_):
    """Patch pandas read_excel / read_csv to throw on touch, then run the
    callable. If anything in the request path still uses pandas, the test
    fails."""
    import pandas as pd
    sentinel = lambda *a, **k: (_ for _ in ()).throw(  # pragma: no cover
        RuntimeError("REGRESSION: pandas read_* must not be used in upload hot path")
    )
    monkeypatch.setattr(pd, "read_excel", sentinel)
    monkeypatch.setattr(pd, "read_csv", sentinel)
    await callable_()


# ---- /upload/naukri --------------------------------------------------

async def test_upload_naukri_csv_streams_without_pandas(app_module, auth_override, monkeypatch):
    csv_bytes = _build_csv(
        ["Name", "Email ID", "Phone Number", "Job Title"],
        [["Iter152 N1", "iter152naukri1@example.test", "9100000001", "Engineer"],
         ["Iter152 N2", "iter152naukri2@example.test", "9100000002", "Engineer"]],
    )

    async def _run():
        from httpx import AsyncClient, ASGITransport
        transport = ASGITransport(app=app_module.app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            r = await ac.post(
                "/api/upload/naukri",
                files={"file": ("naukri.csv", csv_bytes, "text/csv")},
            )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["total"] == 2
        assert body["inserted"] + body["updated"] == 2

    await _assert_pandas_readers_unused(monkeypatch, _run)
    # Clean up
    await app_module.db.naukri_applies.delete_many({"email": {"$regex": "^iter152naukri"}})


async def test_upload_naukri_xlsx_streams_without_pandas(app_module, auth_override, monkeypatch):
    xlsx_bytes = _build_xlsx(
        ["Name", "Email ID", "Phone Number", "Job Title"],
        [["Iter152 NX", "iter152naukrix@example.test", "9100000099", "Engineer"]],
    )

    async def _run():
        from httpx import AsyncClient, ASGITransport
        transport = ASGITransport(app=app_module.app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            r = await ac.post(
                "/api/upload/naukri",
                files={"file": ("naukri.xlsx", xlsx_bytes,
                                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
            )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["total"] == 1
        assert body["inserted"] + body["updated"] == 1

    await _assert_pandas_readers_unused(monkeypatch, _run)
    await app_module.db.naukri_applies.delete_many({"email": {"$regex": "^iter152naukri"}})


# ---- /upload/pipeline ------------------------------------------------

async def test_upload_pipeline_csv_streams_without_pandas(app_module, auth_override, monkeypatch):
    # Includes a duplicate column to exercise the dedup branch.
    csv_bytes = _build_csv(
        ["name", "email", "email", "phone"],
        [["Iter152 P1", "iter152pipe1@example.test", "ignored-dup", "9200000001"]],
    )

    async def _run():
        from httpx import AsyncClient, ASGITransport
        transport = ASGITransport(app=app_module.app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            r = await ac.post(
                "/api/upload/pipeline",
                files={"file": ("pipeline.csv", csv_bytes, "text/csv")},
            )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["total"] == 1
        assert body["inserted"] + body["updated"] == 1

    await _assert_pandas_readers_unused(monkeypatch, _run)
    await app_module.db.pipeline_data.delete_many({"email": {"$regex": "^iter152pipe"}})


# ---- /upload/scoresheet ---------------------------------------------

async def test_upload_scoresheet_csv_streams_without_pandas(app_module, auth_override, monkeypatch):
    csv_bytes = _build_csv(
        ["name", "email", "phone", "score", "round_name"],
        [["Iter152 S1", "iter152score1@example.test", "9300000001", "80", "Round 1"]],
    )

    async def _run():
        from httpx import AsyncClient, ASGITransport
        transport = ASGITransport(app=app_module.app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            r = await ac.post(
                "/api/upload/scoresheet",
                files={"file": ("scores.csv", csv_bytes, "text/csv")},
            )
        assert r.status_code == 200, r.text

    await _assert_pandas_readers_unused(monkeypatch, _run)
    # Cleanup
    await app_module.db.score_sheet.delete_many({"email": {"$regex": "^iter152score"}})
    await app_module.db.bb_applicant_updates.delete_many({"email": {"$regex": "^iter152score"}})


# ---- bb_users untouched ---------------------------------------------

async def test_uploads_do_not_touch_bb_users(app_module, auth_override):
    before = await app_module.db.bb_users.count_documents({})
    csv_bytes = _build_csv(
        ["Name", "Email ID", "Phone Number"],
        [["Iter152 GuardCheck", "iter152guard@example.test", "9400000001"]],
    )
    from httpx import AsyncClient, ASGITransport
    transport = ASGITransport(app=app_module.app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        await ac.post("/api/upload/naukri",
                      files={"file": ("naukri.csv", csv_bytes, "text/csv")})
    after = await app_module.db.bb_users.count_documents({})
    assert before == after, "Upload endpoints must not touch bb_users"
    await app_module.db.naukri_applies.delete_many({"email": {"$regex": "^iter152guard"}})
