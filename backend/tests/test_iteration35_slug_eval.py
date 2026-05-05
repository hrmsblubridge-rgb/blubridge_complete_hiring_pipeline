"""Iteration 35 Tests — slug-based form URLs + Candidate Evaluation Engine.

Covers:
- GET /api/pub/form/{slug or ObjectId} (backward compat + 404)
- POST /api/pub/register structured response (SHORTLISTED / REJECTED with reason classification)
"""
import os
import time
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://applicant-details.preview.emergentagent.com").rstrip("/")
SLUG = "ai-ml"
OBJECT_ID = "69f9ae18dec9a8c504283e7c"


@pytest.fixture(scope="module")
def session():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


def _ts_email(tag: str) -> str:
    return f"test_iter35_{tag}_{int(time.time()*1000)}@example.com"


# ---- GET /api/pub/form/{slug or id} ----
class TestPublicFormResolution:
    def test_get_form_by_slug(self, session):
        r = session.get(f"{BASE_URL}/api/pub/form/{SLUG}")
        assert r.status_code == 200, r.text
        data = r.json()
        assert data.get("slug") == SLUG
        assert "id" in data
        assert "conditions" in data

    def test_get_form_by_objectid_backward_compat(self, session):
        r = session.get(f"{BASE_URL}/api/pub/form/{OBJECT_ID}")
        assert r.status_code == 200, r.text
        data = r.json()
        # Should resolve to same form (slug present, id matches OBJECT_ID)
        assert data.get("id") == OBJECT_ID
        assert data.get("slug") == SLUG

    def test_get_form_nonexistent_slug_returns_404(self, session):
        r = session.get(f"{BASE_URL}/api/pub/form/non-existent-slug-xyz-123")
        assert r.status_code == 404


# ---- POST /api/pub/register with structured evaluation ----
class TestRegistrationEvaluation:
    BASE_PAYLOAD = {
        "form_id": SLUG,
        "full_name": "Iter35 Test",
        "phone": "9000000001",
        "current_location_state": "Tamil Nadu",
        "preferred_location_city": "Chennai",
        "year_of_graduation": 2024,
        "degree": "B.Tech",
        "course": "Computer Science",
        "college": "IIT Madras",
        "location_change": "Yes",
        "attend_in_person": "Yes",
        "age": 24,
    }

    def _post(self, session, **overrides):
        payload = dict(self.BASE_PAYLOAD)
        payload.update(overrides)
        r = session.post(f"{BASE_URL}/api/pub/register", json=payload)
        assert r.status_code == 200, r.text
        return r.json()

    def test_reject_age(self, session):
        data = self._post(session, email=_ts_email("age"), age=15)
        assert data["status"] == "REJECTED"
        assert data["reason"] == "AGE", f"expected AGE got {data}"
        assert data["showSchedule"] is False
        assert isinstance(data["message"], str) and len(data["message"]) > 0

    def test_reject_graduation_year(self, session):
        data = self._post(session, email=_ts_email("grad"), year_of_graduation=2018)
        assert data["status"] == "REJECTED"
        assert data["reason"] == "GRADUATION_YEAR", f"expected GRADUATION_YEAR got {data}"
        assert data["showSchedule"] is False

    def test_reject_location(self, session):
        data = self._post(
            session,
            email=_ts_email("loc"),
            preferred_location_city="Mumbai",
            location_change="No",
            attend_in_person="No",
        )
        assert data["status"] == "REJECTED"
        assert data["reason"] == "LOCATION", f"expected LOCATION got {data}"
        assert data["showSchedule"] is False

    def test_shortlisted_valid_candidate(self, session):
        data = self._post(session, email=_ts_email("ok"))
        assert data["status"] == "SHORTLISTED", data
        assert data["reason"] == ""
        assert data["showSchedule"] is True
        assert data.get("schedule_token")
        assert data.get("scheduleLink")
        assert "/schedule-interview/" in data["scheduleLink"]

    def test_register_with_objectid_works(self, session):
        # Backward compat: POST with ObjectId form_id should also work
        data = self._post(session, form_id=OBJECT_ID, email=_ts_email("byid"))
        assert data["status"] == "SHORTLISTED"
        assert data.get("schedule_token")


@pytest.fixture(scope="module", autouse=True)
def cleanup():
    yield
    # Best-effort cleanup of test_iter35_ docs is left to admin tooling;
    # registration data is keyed by unique emails so no overlap with other tests.
