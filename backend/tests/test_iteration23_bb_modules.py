"""
Iteration 23: BB Modules Testing
Tests all new CRUD endpoints under /api/bb/* prefix:
- Job Roles CRUD
- Form Types CRUD
- Hiring Forms CRUD (with conditions)
- Rounds CRUD
- Job Openings CRUD
- Interview Reports (with filters and summary)
- Attended for Scores
- Applicant Score Update
Also verifies existing endpoints still work.
"""

import pytest
import requests
import os
import time

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

class TestAuth:
    """Authentication tests"""
    
    @pytest.fixture(scope="class")
    def session(self):
        """Create authenticated session"""
        s = requests.Session()
        s.headers.update({"Content-Type": "application/json"})
        # Login
        resp = s.post(f"{BASE_URL}/api/login", json={"username": "admin", "password": "admin"})
        assert resp.status_code == 200, f"Login failed: {resp.text}"
        return s
    
    def test_login_success(self):
        """Test login with valid credentials"""
        resp = requests.post(f"{BASE_URL}/api/login", json={"username": "admin", "password": "admin"})
        assert resp.status_code == 200
        data = resp.json()
        assert data.get("success") == True
        assert "username" in data
    
    def test_login_invalid(self):
        """Test login with invalid credentials"""
        resp = requests.post(f"{BASE_URL}/api/login", json={"username": "wrong", "password": "wrong"})
        assert resp.status_code == 401


class TestBBJobRoles:
    """BB Job Roles CRUD tests"""
    
    @pytest.fixture(scope="class")
    def auth_session(self):
        s = requests.Session()
        s.headers.update({"Content-Type": "application/json"})
        resp = s.post(f"{BASE_URL}/api/login", json={"username": "admin", "password": "admin"})
        assert resp.status_code == 200
        return s
    
    def test_list_job_roles(self, auth_session):
        """GET /api/bb/job-roles returns list"""
        resp = auth_session.get(f"{BASE_URL}/api/bb/job-roles")
        assert resp.status_code == 200
        data = resp.json()
        assert "roles" in data
        assert isinstance(data["roles"], list)
    
    def test_create_job_role(self, auth_session):
        """POST /api/bb/job-roles creates new role"""
        resp = auth_session.post(f"{BASE_URL}/api/bb/job-roles", json={"name": "TEST_AI_Engineer"})
        assert resp.status_code == 200
        data = resp.json()
        assert data.get("success") == True
        assert "id" in data
        assert data["name"] == "TEST_AI_Engineer"
        # Store for cleanup
        self.__class__.created_role_id = data["id"]
    
    def test_update_job_role(self, auth_session):
        """PUT /api/bb/job-roles/{id} updates role"""
        role_id = getattr(self.__class__, 'created_role_id', None)
        if not role_id:
            pytest.skip("No role created to update")
        resp = auth_session.put(f"{BASE_URL}/api/bb/job-roles/{role_id}", json={"name": "TEST_AI_Engineer_Updated"})
        assert resp.status_code == 200
        assert resp.json().get("success") == True
        
        # Verify update persisted
        resp = auth_session.get(f"{BASE_URL}/api/bb/job-roles")
        roles = resp.json().get("roles", [])
        updated = [r for r in roles if r["id"] == role_id]
        assert len(updated) == 1
        assert updated[0]["name"] == "TEST_AI_Engineer_Updated"
    
    def test_delete_job_role(self, auth_session):
        """DELETE /api/bb/job-roles/{id} removes role"""
        role_id = getattr(self.__class__, 'created_role_id', None)
        if not role_id:
            pytest.skip("No role created to delete")
        resp = auth_session.delete(f"{BASE_URL}/api/bb/job-roles/{role_id}")
        assert resp.status_code == 200
        assert resp.json().get("success") == True
        
        # Verify deletion
        resp = auth_session.get(f"{BASE_URL}/api/bb/job-roles")
        roles = resp.json().get("roles", [])
        assert not any(r["id"] == role_id for r in roles)
    
    def test_delete_nonexistent_role(self, auth_session):
        """DELETE /api/bb/job-roles/{invalid_id} returns 404"""
        resp = auth_session.delete(f"{BASE_URL}/api/bb/job-roles/000000000000000000000000")
        assert resp.status_code == 404
    
    def test_create_empty_name_fails(self, auth_session):
        """POST /api/bb/job-roles with empty name fails"""
        resp = auth_session.post(f"{BASE_URL}/api/bb/job-roles", json={"name": "   "})
        assert resp.status_code == 400


class TestBBFormTypes:
    """BB Form Types CRUD tests"""
    
    @pytest.fixture(scope="class")
    def auth_session(self):
        s = requests.Session()
        s.headers.update({"Content-Type": "application/json"})
        resp = s.post(f"{BASE_URL}/api/login", json={"username": "admin", "password": "admin"})
        assert resp.status_code == 200
        return s
    
    def test_list_form_types(self, auth_session):
        """GET /api/bb/form-types returns list"""
        resp = auth_session.get(f"{BASE_URL}/api/bb/form-types")
        assert resp.status_code == 200
        data = resp.json()
        assert "form_types" in data
        assert isinstance(data["form_types"], list)
    
    def test_create_form_type(self, auth_session):
        """POST /api/bb/form-types creates new type"""
        resp = auth_session.post(f"{BASE_URL}/api/bb/form-types", json={"name": "TEST_Registration"})
        assert resp.status_code == 200
        data = resp.json()
        assert data.get("success") == True
        assert "id" in data
        self.__class__.created_type_id = data["id"]
    
    def test_update_form_type(self, auth_session):
        """PUT /api/bb/form-types/{id} updates type"""
        type_id = getattr(self.__class__, 'created_type_id', None)
        if not type_id:
            pytest.skip("No type created to update")
        resp = auth_session.put(f"{BASE_URL}/api/bb/form-types/{type_id}", json={"name": "TEST_Registration_Updated"})
        assert resp.status_code == 200
        assert resp.json().get("success") == True
    
    def test_delete_form_type(self, auth_session):
        """DELETE /api/bb/form-types/{id} removes type"""
        type_id = getattr(self.__class__, 'created_type_id', None)
        if not type_id:
            pytest.skip("No type created to delete")
        resp = auth_session.delete(f"{BASE_URL}/api/bb/form-types/{type_id}")
        assert resp.status_code == 200


class TestBBHiringForms:
    """BB Hiring Forms CRUD tests with conditions"""
    
    @pytest.fixture(scope="class")
    def auth_session(self):
        s = requests.Session()
        s.headers.update({"Content-Type": "application/json"})
        resp = s.post(f"{BASE_URL}/api/login", json={"username": "admin", "password": "admin"})
        assert resp.status_code == 200
        return s
    
    @pytest.fixture(scope="class")
    def setup_form_type(self, auth_session):
        """Create a form type for testing hiring forms"""
        resp = auth_session.post(f"{BASE_URL}/api/bb/form-types", json={"name": "TEST_HiringFormType"})
        assert resp.status_code == 200
        type_id = resp.json()["id"]
        yield type_id
        # Cleanup
        auth_session.delete(f"{BASE_URL}/api/bb/form-types/{type_id}")
    
    def test_list_hiring_forms(self, auth_session):
        """GET /api/bb/hiring-forms returns list"""
        resp = auth_session.get(f"{BASE_URL}/api/bb/hiring-forms")
        assert resp.status_code == 200
        data = resp.json()
        assert "forms" in data
        assert isinstance(data["forms"], list)
    
    def test_create_hiring_form_with_conditions(self, auth_session, setup_form_type):
        """POST /api/bb/hiring-forms creates form with conditions"""
        form_type_id = setup_form_type
        payload = {
            "name": "TEST_2026_Batch_Hiring",
            "form_type_id": form_type_id,
            "job_role": "Software Engineer",
            "conditions": {
                "age_min": 18,
                "age_max": 30,
                "grad_year_min": 2024,
                "grad_year_max": 2026,
                "locations": ["Bangalore", "Hyderabad"],
                "location_change": "Yes",
                "attend_in_person": "Yes",
                "college_limit": "NIRF"
            }
        }
        resp = auth_session.post(f"{BASE_URL}/api/bb/hiring-forms", json=payload)
        assert resp.status_code == 200
        data = resp.json()
        assert data.get("success") == True
        assert "form" in data
        form = data["form"]
        assert form["name"] == "TEST_2026_Batch_Hiring"
        assert form["conditions"]["age_min"] == 18
        assert form["conditions"]["locations"] == ["Bangalore", "Hyderabad"]
        self.__class__.created_form_id = form["id"]
    
    def test_update_hiring_form(self, auth_session, setup_form_type):
        """PUT /api/bb/hiring-forms/{id} updates form"""
        form_id = getattr(self.__class__, 'created_form_id', None)
        if not form_id:
            pytest.skip("No form created to update")
        payload = {
            "name": "TEST_2026_Batch_Hiring_Updated",
            "conditions": {
                "age_min": 20,
                "age_max": 28
            }
        }
        resp = auth_session.put(f"{BASE_URL}/api/bb/hiring-forms/{form_id}", json=payload)
        assert resp.status_code == 200
        assert resp.json().get("success") == True
    
    def test_delete_hiring_form(self, auth_session):
        """DELETE /api/bb/hiring-forms/{id} removes form"""
        form_id = getattr(self.__class__, 'created_form_id', None)
        if not form_id:
            pytest.skip("No form created to delete")
        resp = auth_session.delete(f"{BASE_URL}/api/bb/hiring-forms/{form_id}")
        assert resp.status_code == 200
    
    def test_create_form_invalid_type_fails(self, auth_session):
        """POST /api/bb/hiring-forms with invalid form_type_id fails"""
        payload = {
            "name": "TEST_Invalid",
            "form_type_id": "000000000000000000000000",
            "job_role": "Test"
        }
        resp = auth_session.post(f"{BASE_URL}/api/bb/hiring-forms", json=payload)
        assert resp.status_code == 400


class TestBBRounds:
    """BB Rounds CRUD tests"""
    
    @pytest.fixture(scope="class")
    def auth_session(self):
        s = requests.Session()
        s.headers.update({"Content-Type": "application/json"})
        resp = s.post(f"{BASE_URL}/api/login", json={"username": "admin", "password": "admin"})
        assert resp.status_code == 200
        return s
    
    def test_list_rounds(self, auth_session):
        """GET /api/bb/rounds returns list"""
        resp = auth_session.get(f"{BASE_URL}/api/bb/rounds")
        assert resp.status_code == 200
        data = resp.json()
        assert "rounds" in data
        assert isinstance(data["rounds"], list)
    
    def test_create_round(self, auth_session):
        """POST /api/bb/rounds creates new round"""
        resp = auth_session.post(f"{BASE_URL}/api/bb/rounds", json={"name": "TEST_Technical_Round"})
        assert resp.status_code == 200
        data = resp.json()
        assert data.get("success") == True
        assert "id" in data
        self.__class__.created_round_id = data["id"]
    
    def test_update_round(self, auth_session):
        """PUT /api/bb/rounds/{id} updates round"""
        round_id = getattr(self.__class__, 'created_round_id', None)
        if not round_id:
            pytest.skip("No round created to update")
        resp = auth_session.put(f"{BASE_URL}/api/bb/rounds/{round_id}", json={"name": "TEST_Technical_Round_Updated"})
        assert resp.status_code == 200
    
    def test_delete_round(self, auth_session):
        """DELETE /api/bb/rounds/{id} removes round"""
        round_id = getattr(self.__class__, 'created_round_id', None)
        if not round_id:
            pytest.skip("No round created to delete")
        resp = auth_session.delete(f"{BASE_URL}/api/bb/rounds/{round_id}")
        assert resp.status_code == 200


class TestBBJobOpenings:
    """BB Job Openings CRUD tests"""
    
    @pytest.fixture(scope="class")
    def auth_session(self):
        s = requests.Session()
        s.headers.update({"Content-Type": "application/json"})
        resp = s.post(f"{BASE_URL}/api/login", json={"username": "admin", "password": "admin"})
        assert resp.status_code == 200
        return s
    
    def test_list_job_openings(self, auth_session):
        """GET /api/bb/job-openings returns list"""
        resp = auth_session.get(f"{BASE_URL}/api/bb/job-openings")
        assert resp.status_code == 200
        data = resp.json()
        assert "openings" in data
        assert isinstance(data["openings"], list)
    
    def test_create_job_opening(self, auth_session):
        """POST /api/bb/job-openings creates new opening"""
        payload = {
            "title": "TEST_Software_Engineer_2026",
            "job_role": "Software Engineer",
            "description": "Test job opening description"
        }
        resp = auth_session.post(f"{BASE_URL}/api/bb/job-openings", json=payload)
        assert resp.status_code == 200
        data = resp.json()
        assert data.get("success") == True
        assert "id" in data
        self.__class__.created_opening_id = data["id"]
    
    def test_update_job_opening(self, auth_session):
        """PUT /api/bb/job-openings/{id} updates opening"""
        opening_id = getattr(self.__class__, 'created_opening_id', None)
        if not opening_id:
            pytest.skip("No opening created to update")
        payload = {"title": "TEST_Software_Engineer_2026_Updated", "description": "Updated description"}
        resp = auth_session.put(f"{BASE_URL}/api/bb/job-openings/{opening_id}", json=payload)
        assert resp.status_code == 200
    
    def test_delete_job_opening(self, auth_session):
        """DELETE /api/bb/job-openings/{id} removes opening"""
        opening_id = getattr(self.__class__, 'created_opening_id', None)
        if not opening_id:
            pytest.skip("No opening created to delete")
        resp = auth_session.delete(f"{BASE_URL}/api/bb/job-openings/{opening_id}")
        assert resp.status_code == 200


class TestBBInterviewReports:
    """BB Interview Reports tests"""
    
    @pytest.fixture(scope="class")
    def auth_session(self):
        s = requests.Session()
        s.headers.update({"Content-Type": "application/json"})
        resp = s.post(f"{BASE_URL}/api/login", json={"username": "admin", "password": "admin"})
        assert resp.status_code == 200
        return s
    
    def test_get_interview_reports(self, auth_session):
        """GET /api/bb/interview-reports returns data with summary"""
        resp = auth_session.get(f"{BASE_URL}/api/bb/interview-reports")
        assert resp.status_code == 200
        data = resp.json()
        assert "data" in data
        assert "total" in data
        assert "summary" in data
        summary = data["summary"]
        assert "role_counts" in summary
        assert "attended" in summary
        assert "not_attended" in summary
        assert "premium_colleges" in summary
        assert "non_premium_colleges" in summary
    
    def test_interview_reports_with_filters(self, auth_session):
        """GET /api/bb/interview-reports with filters"""
        params = {
            "startDate": "2025-01-01",
            "endDate": "2026-12-31",
            "attendance": "Attended",
            "collegeType": "Premium"
        }
        resp = auth_session.get(f"{BASE_URL}/api/bb/interview-reports", params=params)
        assert resp.status_code == 200
        data = resp.json()
        assert "data" in data
        # All returned records should be Attended if filter applied
        for row in data["data"]:
            assert row.get("attendance") == "Attended"
    
    def test_interview_reports_pagination(self, auth_session):
        """GET /api/bb/interview-reports with pagination"""
        resp = auth_session.get(f"{BASE_URL}/api/bb/interview-reports", params={"page": 1, "limit": 10})
        assert resp.status_code == 200
        data = resp.json()
        assert data["page"] == 1
        assert data["limit"] == 10


class TestBBAttendedForScores:
    """BB Attended for Scores tests"""
    
    @pytest.fixture(scope="class")
    def auth_session(self):
        s = requests.Session()
        s.headers.update({"Content-Type": "application/json"})
        resp = s.post(f"{BASE_URL}/api/login", json={"username": "admin", "password": "admin"})
        assert resp.status_code == 200
        return s
    
    def test_get_attended_for_scores(self, auth_session):
        """GET /api/bb/attended-for-scores returns attended applicants"""
        resp = auth_session.get(f"{BASE_URL}/api/bb/attended-for-scores")
        assert resp.status_code == 200
        data = resp.json()
        assert "data" in data
        assert isinstance(data["data"], list)
        # Check structure of returned data
        if len(data["data"]) > 0:
            item = data["data"][0]
            assert "name" in item
            assert "email" in item
            assert "status" in item
            assert "scores" in item
    
    def test_attended_for_scores_with_date_filter(self, auth_session):
        """GET /api/bb/attended-for-scores with date filter"""
        params = {"startDate": "2025-01-01", "endDate": "2026-12-31"}
        resp = auth_session.get(f"{BASE_URL}/api/bb/attended-for-scores", params=params)
        assert resp.status_code == 200


class TestBBApplicantScoreUpdate:
    """BB Applicant Score Update tests"""
    
    @pytest.fixture(scope="class")
    def auth_session(self):
        s = requests.Session()
        s.headers.update({"Content-Type": "application/json"})
        resp = s.post(f"{BASE_URL}/api/login", json={"username": "admin", "password": "admin"})
        assert resp.status_code == 200
        return s
    
    def test_update_applicant_score(self, auth_session):
        """PUT /api/bb/applicant-score/{email} updates status and scores"""
        # Use a test email
        test_email = "test_score_update@example.com"
        payload = {
            "status": "Selected",
            "scores": [
                {"round_name": "Technical", "score": 85.5},
                {"round_name": "HR", "score": 90.0}
            ]
        }
        resp = auth_session.put(f"{BASE_URL}/api/bb/applicant-score/{test_email}", json=payload)
        assert resp.status_code == 200
        assert resp.json().get("success") == True
    
    def test_update_applicant_score_status_only(self, auth_session):
        """PUT /api/bb/applicant-score/{email} with status only"""
        test_email = "test_status_only@example.com"
        payload = {"status": "Rejected"}
        resp = auth_session.put(f"{BASE_URL}/api/bb/applicant-score/{test_email}", json=payload)
        assert resp.status_code == 200


class TestExistingEndpoints:
    """Verify existing endpoints still work"""
    
    @pytest.fixture(scope="class")
    def auth_session(self):
        s = requests.Session()
        s.headers.update({"Content-Type": "application/json"})
        resp = s.post(f"{BASE_URL}/api/login", json={"username": "admin", "password": "admin"})
        assert resp.status_code == 200
        return s
    
    def test_summary_endpoint(self, auth_session):
        """GET /api/summary still works"""
        resp = auth_session.get(f"{BASE_URL}/api/summary")
        assert resp.status_code == 200
        data = resp.json()
        assert "data" in data
    
    def test_applicants_endpoint(self, auth_session):
        """GET /api/applicants still works"""
        resp = auth_session.get(f"{BASE_URL}/api/applicants")
        assert resp.status_code == 200
        data = resp.json()
        assert "data" in data
    
    def test_attended_endpoint(self, auth_session):
        """GET /api/attended still works"""
        resp = auth_session.get(f"{BASE_URL}/api/attended")
        assert resp.status_code == 200
        data = resp.json()
        assert "data" in data
    
    def test_job_roles_endpoint(self, auth_session):
        """GET /api/job-roles still works"""
        resp = auth_session.get(f"{BASE_URL}/api/job-roles")
        assert resp.status_code == 200
        data = resp.json()
        assert "job_roles" in data
    
    def test_job_keyword_mappings_endpoint(self, auth_session):
        """GET /api/job-keyword-mappings still works"""
        resp = auth_session.get(f"{BASE_URL}/api/job-keyword-mappings")
        assert resp.status_code == 200
        data = resp.json()
        assert "mappings" in data
    
    def test_bulk_upload_status_endpoint(self, auth_session):
        """GET /api/bulk-upload/status still works"""
        resp = auth_session.get(f"{BASE_URL}/api/bulk-upload/status")
        assert resp.status_code == 200


class TestAuthRequired:
    """Test that BB endpoints require authentication"""
    
    def test_job_roles_requires_auth(self):
        """GET /api/bb/job-roles requires auth"""
        resp = requests.get(f"{BASE_URL}/api/bb/job-roles")
        assert resp.status_code == 401
    
    def test_form_types_requires_auth(self):
        """GET /api/bb/form-types requires auth"""
        resp = requests.get(f"{BASE_URL}/api/bb/form-types")
        assert resp.status_code == 401
    
    def test_hiring_forms_requires_auth(self):
        """GET /api/bb/hiring-forms requires auth"""
        resp = requests.get(f"{BASE_URL}/api/bb/hiring-forms")
        assert resp.status_code == 401
    
    def test_rounds_requires_auth(self):
        """GET /api/bb/rounds requires auth"""
        resp = requests.get(f"{BASE_URL}/api/bb/rounds")
        assert resp.status_code == 401
    
    def test_job_openings_requires_auth(self):
        """GET /api/bb/job-openings requires auth"""
        resp = requests.get(f"{BASE_URL}/api/bb/job-openings")
        assert resp.status_code == 401
    
    def test_interview_reports_requires_auth(self):
        """GET /api/bb/interview-reports requires auth"""
        resp = requests.get(f"{BASE_URL}/api/bb/interview-reports")
        assert resp.status_code == 401
    
    def test_attended_for_scores_requires_auth(self):
        """GET /api/bb/attended-for-scores requires auth"""
        resp = requests.get(f"{BASE_URL}/api/bb/attended-for-scores")
        assert resp.status_code == 401


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
