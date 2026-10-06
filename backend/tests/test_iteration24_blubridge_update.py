"""
Iteration 24: BluBridge PDF Update Tests
Tests for:
1. Login credentials changed to 'Admin User'/'Admin User'
2. Holidays CRUD (/api/bb/holidays)
3. Verify OTP (/api/bb/verify-otp)
4. Public form endpoint (/api/pub/form/{formId})
5. Public registration with auto-shortlisting (/api/pub/register)
6. Public interview scheduling (/api/pub/schedule/{token})
7. Enhanced job openings with new fields
8. Hiring forms with job_description_attached field
9. Registration inserts into both bb_registrations AND registered_candidates
"""

import pytest
import requests
import os
import time

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

@pytest.fixture(scope="module")
def session():
    """Create a session for all tests"""
    return requests.Session()

@pytest.fixture(scope="module")
def auth_session(session):
    """Authenticate with new credentials"""
    response = session.post(f"{BASE_URL}/api/login", json={
        "username": "Admin User",
        "password": "Admin User"
    })
    assert response.status_code == 200, f"Login failed: {response.text}"
    return session


class TestLoginCredentials:
    """Test login with new and old credentials"""
    
    def test_login_with_new_credentials(self, session):
        """Login with 'Admin User'/'Admin User' should work"""
        response = session.post(f"{BASE_URL}/api/login", json={
            "username": "Admin User",
            "password": "Admin User"
        })
        assert response.status_code == 200
        data = response.json()
        assert data.get("success") == True
        assert data.get("username") == "Admin User"
        print("PASS: Login with new credentials 'Admin User'/'Admin User' works")
    
    def test_login_with_old_credentials_fails(self, session):
        """Login with old 'admin'/'admin' should fail"""
        response = session.post(f"{BASE_URL}/api/login", json={
            "username": "admin",
            "password": "admin"
        })
        assert response.status_code == 401
        print("PASS: Old credentials 'admin'/'admin' no longer work")


class TestHolidaysCRUD:
    """Test /api/bb/holidays CRUD operations"""
    
    def test_get_holidays(self, auth_session):
        """GET /api/bb/holidays returns list"""
        response = auth_session.get(f"{BASE_URL}/api/bb/holidays")
        assert response.status_code == 200
        data = response.json()
        assert "holidays" in data
        print(f"PASS: GET /api/bb/holidays returns {len(data['holidays'])} holidays")
    
    def test_create_holiday(self, auth_session):
        """POST /api/bb/holidays creates a holiday"""
        response = auth_session.post(f"{BASE_URL}/api/bb/holidays", json={
            "name": "TEST_Republic_Day",
            "date": "2026-01-26"
        })
        assert response.status_code == 200
        data = response.json()
        assert data.get("success") == True
        assert "id" in data
        print(f"PASS: POST /api/bb/holidays created holiday with id {data['id']}")
        return data["id"]
    
    def test_update_holiday(self, auth_session):
        """PUT /api/bb/holidays/{id} updates a holiday"""
        # First create
        create_resp = auth_session.post(f"{BASE_URL}/api/bb/holidays", json={
            "name": "TEST_Update_Holiday",
            "date": "2026-02-01"
        })
        holiday_id = create_resp.json()["id"]
        
        # Update
        response = auth_session.put(f"{BASE_URL}/api/bb/holidays/{holiday_id}", json={
            "name": "TEST_Updated_Holiday",
            "date": "2026-02-02"
        })
        assert response.status_code == 200
        assert response.json().get("success") == True
        print(f"PASS: PUT /api/bb/holidays/{holiday_id} updated successfully")
        
        # Cleanup
        auth_session.delete(f"{BASE_URL}/api/bb/holidays/{holiday_id}")
    
    def test_delete_holiday(self, auth_session):
        """DELETE /api/bb/holidays/{id} removes a holiday"""
        # First create
        create_resp = auth_session.post(f"{BASE_URL}/api/bb/holidays", json={
            "name": "TEST_Delete_Holiday",
            "date": "2026-03-01"
        })
        holiday_id = create_resp.json()["id"]
        
        # Delete
        response = auth_session.delete(f"{BASE_URL}/api/bb/holidays/{holiday_id}")
        assert response.status_code == 200
        assert response.json().get("success") == True
        print(f"PASS: DELETE /api/bb/holidays/{holiday_id} removed successfully")


class TestVerifyOTP:
    """Test /api/bb/verify-otp endpoint"""
    
    def test_verify_otp_invalid(self, auth_session):
        """POST /api/bb/verify-otp returns Invalid OTP for wrong data"""
        response = auth_session.post(f"{BASE_URL}/api/bb/verify-otp", json={
            "phone": "9999999999",
            "otp": "000000"
        })
        assert response.status_code == 200
        data = response.json()
        assert data.get("success") == False
        assert "Invalid OTP" in data.get("message", "")
        print("PASS: POST /api/bb/verify-otp returns Invalid OTP for wrong data")
    
    def test_verify_otp_missing_fields(self, auth_session):
        """POST /api/bb/verify-otp with missing fields returns 400"""
        response = auth_session.post(f"{BASE_URL}/api/bb/verify-otp", json={
            "phone": "",
            "otp": ""
        })
        assert response.status_code == 400
        print("PASS: POST /api/bb/verify-otp with empty fields returns 400")


class TestPublicFormEndpoint:
    """Test /api/pub/form/{formId} endpoint (no auth required)"""
    
    @pytest.fixture(scope="class")
    def test_form_id(self, auth_session):
        """Create test data: job role, form type, hiring form"""
        # Create job role
        role_resp = auth_session.post(f"{BASE_URL}/api/bb/job-roles", json={"name": "TEST_Software_Engineer"})
        role_id = role_resp.json().get("id")
        
        # Create form type
        type_resp = auth_session.post(f"{BASE_URL}/api/bb/form-types", json={"name": "TEST_Registration"})
        type_id = type_resp.json().get("id")
        
        # Create hiring form with conditions
        form_resp = auth_session.post(f"{BASE_URL}/api/bb/hiring-forms", json={
            "name": "TEST_2026_Batch_Hiring",
            "form_type_id": type_id,
            "job_role": "TEST_Software_Engineer",
            "conditions": {
                "age_min": 18,
                "age_max": 30,
                "grad_year_min": 2024,
                "grad_year_max": 2026,
                "locations": ["Bangalore", "Hyderabad"],
                "location_change": "Yes",
                "attend_in_person": "Yes",
                "college_limit": "Both"
            },
            "job_description_attached": False
        })
        form_id = form_resp.json().get("form", {}).get("id")
        
        yield form_id
        
        # Cleanup
        if form_id:
            auth_session.delete(f"{BASE_URL}/api/bb/hiring-forms/{form_id}")
        if type_id:
            auth_session.delete(f"{BASE_URL}/api/bb/form-types/{type_id}")
        if role_id:
            auth_session.delete(f"{BASE_URL}/api/bb/job-roles/{role_id}")
    
    def test_get_public_form_no_auth(self, test_form_id):
        """GET /api/pub/form/{formId} works without auth"""
        response = requests.get(f"{BASE_URL}/api/pub/form/{test_form_id}")
        assert response.status_code == 200
        data = response.json()
        assert data.get("id") == test_form_id
        assert "conditions" in data
        assert data.get("name") == "TEST_2026_Batch_Hiring"
        print(f"PASS: GET /api/pub/form/{test_form_id} returns form without auth")
    
    def test_get_public_form_invalid_id(self):
        """GET /api/pub/form/{invalid} returns 404"""
        response = requests.get(f"{BASE_URL}/api/pub/form/000000000000000000000000")
        assert response.status_code == 404
        print("PASS: GET /api/pub/form with invalid ID returns 404")


class TestPublicRegistration:
    """Test /api/pub/register endpoint with auto-shortlisting"""
    
    @pytest.fixture(scope="class")
    def test_form_with_conditions(self, auth_session):
        """Create form with strict conditions for testing shortlisting"""
        # Create job role
        role_resp = auth_session.post(f"{BASE_URL}/api/bb/job-roles", json={"name": "TEST_Data_Analyst"})
        role_id = role_resp.json().get("id")
        
        # Create form type
        type_resp = auth_session.post(f"{BASE_URL}/api/bb/form-types", json={"name": "TEST_Application"})
        type_id = type_resp.json().get("id")
        
        # Create hiring form with conditions
        form_resp = auth_session.post(f"{BASE_URL}/api/bb/hiring-forms", json={
            "name": "TEST_Conditional_Form",
            "form_type_id": type_id,
            "job_role": "TEST_Data_Analyst",
            "conditions": {
                "age_min": 20,
                "age_max": 28,
                "grad_year_min": 2024,
                "grad_year_max": 2026,
                "locations": ["Mumbai", "Pune"],
                "location_change": "Yes",
                "attend_in_person": "Yes",
                "college_limit": "Both"
            }
        })
        form_id = form_resp.json().get("form", {}).get("id")
        
        yield {"form_id": form_id, "type_id": type_id, "role_id": role_id}
        
        # Cleanup
        if form_id:
            auth_session.delete(f"{BASE_URL}/api/bb/hiring-forms/{form_id}")
        if type_id:
            auth_session.delete(f"{BASE_URL}/api/bb/form-types/{type_id}")
        if role_id:
            auth_session.delete(f"{BASE_URL}/api/bb/job-roles/{role_id}")
    
    def test_register_shortlisted(self, test_form_with_conditions):
        """POST /api/pub/register auto-shortlists when conditions met"""
        form_id = test_form_with_conditions["form_id"]
        response = requests.post(f"{BASE_URL}/api/pub/register", json={
            "form_id": form_id,
            "full_name": "TEST_John_Doe",
            "email": "test_john_shortlist@example.com",
            "phone": "9876543210",
            "age": 24,
            "current_location_state": "Maharashtra",
            "preferred_location_city": "Mumbai",
            "year_of_graduation": 2025,
            "degree": "B.Tech",
            "course": "Computer Science",
            "college": "IIT Bombay"
        })
        assert response.status_code == 200
        data = response.json()
        assert data.get("success") == True
        assert data.get("is_shortlisted") == True
        assert data.get("status") == "Interview Not Scheduled"
        assert data.get("schedule_token") is not None
        print(f"PASS: Registration shortlisted with token {data.get('schedule_token')}")
        return data.get("schedule_token")
    
    def test_register_rejected_age(self, test_form_with_conditions):
        """POST /api/pub/register rejects when age condition fails"""
        form_id = test_form_with_conditions["form_id"]
        response = requests.post(f"{BASE_URL}/api/pub/register", json={
            "form_id": form_id,
            "full_name": "TEST_Old_Person",
            "email": "test_old_reject@example.com",
            "phone": "9876543211",
            "age": 35,  # Above max age 28
            "preferred_location_city": "Mumbai",
            "year_of_graduation": 2025
        })
        assert response.status_code == 200
        data = response.json()
        assert data.get("is_shortlisted") == False
        assert data.get("status") == "Rejected"
        assert "Age above maximum" in data.get("rejected_reasons", [])
        print("PASS: Registration rejected due to age above maximum")
    
    def test_register_rejected_location(self, test_form_with_conditions):
        """POST /api/pub/register rejects when location condition fails"""
        form_id = test_form_with_conditions["form_id"]
        response = requests.post(f"{BASE_URL}/api/pub/register", json={
            "form_id": form_id,
            "full_name": "TEST_Wrong_Location",
            "email": "test_loc_reject@example.com",
            "phone": "9876543212",
            "age": 24,
            "preferred_location_city": "Chennai",  # Not in allowed locations
            "year_of_graduation": 2025,
            "location_change": "No"  # Required Yes
        })
        assert response.status_code == 200
        data = response.json()
        assert data.get("is_shortlisted") == False
        assert data.get("status") == "Rejected"
        print(f"PASS: Registration rejected due to location: {data.get('rejected_reasons')}")


class TestInterviewScheduling:
    """Test /api/pub/schedule/{token} endpoint"""
    
    @pytest.fixture(scope="class")
    def schedule_token(self, auth_session):
        """Create a shortlisted registration to get schedule token"""
        # Create job role
        role_resp = auth_session.post(f"{BASE_URL}/api/bb/job-roles", json={"name": "TEST_Schedule_Role"})
        role_id = role_resp.json().get("id")
        
        # Create form type
        type_resp = auth_session.post(f"{BASE_URL}/api/bb/form-types", json={"name": "TEST_Schedule_Type"})
        type_id = type_resp.json().get("id")
        
        # Create hiring form
        form_resp = auth_session.post(f"{BASE_URL}/api/bb/hiring-forms", json={
            "name": "TEST_Schedule_Form",
            "form_type_id": type_id,
            "job_role": "TEST_Schedule_Role",
            "conditions": {}  # No conditions = always shortlisted
        })
        form_id = form_resp.json().get("form", {}).get("id")
        
        # Register to get token
        reg_resp = requests.post(f"{BASE_URL}/api/pub/register", json={
            "form_id": form_id,
            "full_name": "TEST_Schedule_User",
            "email": "test_schedule_user@example.com",
            "phone": "9876543220"
        })
        token = reg_resp.json().get("schedule_token")
        
        yield {"token": token, "form_id": form_id, "type_id": type_id, "role_id": role_id}
        
        # Cleanup
        if form_id:
            auth_session.delete(f"{BASE_URL}/api/bb/hiring-forms/{form_id}")
        if type_id:
            auth_session.delete(f"{BASE_URL}/api/bb/form-types/{type_id}")
        if role_id:
            auth_session.delete(f"{BASE_URL}/api/bb/job-roles/{role_id}")
    
    def test_get_schedule_info(self, schedule_token):
        """GET /api/pub/schedule/{token} returns applicant info and holidays"""
        token = schedule_token["token"]
        response = requests.get(f"{BASE_URL}/api/pub/schedule/{token}")
        assert response.status_code == 200
        data = response.json()
        assert data.get("name") == "TEST_Schedule_User"
        assert data.get("email") == "test_schedule_user@example.com"
        assert "holidays" in data
        assert data.get("already_scheduled") == False
        print(f"PASS: GET /api/pub/schedule/{token} returns applicant info")
    
    def test_schedule_interview(self, schedule_token):
        """POST /api/pub/schedule/{token} schedules interview and generates OTP"""
        token = schedule_token["token"]
        response = requests.post(f"{BASE_URL}/api/pub/schedule/{token}", json={
            "date": "2026-02-15",
            "time": "10:00:00"
        })
        assert response.status_code == 200
        data = response.json()
        assert data.get("success") == True
        assert data.get("is_reschedule") == False
        assert data.get("otp") is not None
        assert len(data.get("otp", "")) == 6
        print(f"PASS: Interview scheduled with OTP {data.get('otp')}")
        return data.get("otp")
    
    def test_reschedule_interview(self, schedule_token):
        """POST /api/pub/schedule/{token} again reschedules (increments reschedule_count)"""
        token = schedule_token["token"]
        # First schedule
        requests.post(f"{BASE_URL}/api/pub/schedule/{token}", json={
            "date": "2026-02-16",
            "time": "11:00:00"
        })
        # Reschedule
        response = requests.post(f"{BASE_URL}/api/pub/schedule/{token}", json={
            "date": "2026-02-17",
            "time": "14:00:00"
        })
        assert response.status_code == 200
        data = response.json()
        assert data.get("success") == True
        assert data.get("is_reschedule") == True
        print("PASS: Interview rescheduled successfully")
    
    def test_invalid_token(self):
        """GET /api/pub/schedule/{invalid} returns 404"""
        response = requests.get(f"{BASE_URL}/api/pub/schedule/invalidtoken123")
        assert response.status_code == 404
        print("PASS: Invalid schedule token returns 404")


class TestEnhancedJobOpenings:
    """Test enhanced job openings with new fields"""
    
    def test_create_job_opening_with_all_fields(self, auth_session):
        """POST /api/bb/job-openings with all new fields"""
        response = auth_session.post(f"{BASE_URL}/api/bb/job-openings", json={
            "title": "TEST_Senior_Developer",
            "job_role": "Software Engineer",
            "vacancies": 5,
            "years_of_graduation": ["2024", "2025", "2026"],
            "education": ["B.Tech", "M.Tech", "MCA"],
            "salary_range": "8-12 LPA",
            "key_responsibilities": "Design and develop software\nCode review\nMentoring",
            "added_advantages": "AWS certification\nPython expertise",
            "what_we_offer": "Flexible hours\nRemote work\nHealth insurance"
        })
        assert response.status_code == 200
        data = response.json()
        assert data.get("success") == True
        opening_id = data.get("id")
        print(f"PASS: Created job opening with all new fields, id={opening_id}")
        
        # Verify by fetching
        list_resp = auth_session.get(f"{BASE_URL}/api/bb/job-openings")
        openings = list_resp.json().get("openings", [])
        created = next((o for o in openings if o.get("id") == opening_id), None)
        assert created is not None
        assert created.get("vacancies") == 5
        assert created.get("years_of_graduation") == ["2024", "2025", "2026"]
        assert created.get("education") == ["B.Tech", "M.Tech", "MCA"]
        assert created.get("salary_range") == "8-12 LPA"
        assert "Design and develop" in created.get("key_responsibilities", "")
        
        # Cleanup
        auth_session.delete(f"{BASE_URL}/api/bb/job-openings/{opening_id}")
        print("PASS: Verified all new fields are stored correctly")


class TestHiringFormsWithJD:
    """Test hiring forms with job_description_attached field"""
    
    def test_create_form_with_jd_attached(self, auth_session):
        """POST /api/bb/hiring-forms with job_description_attached and job_opening_id"""
        # Create job opening first
        opening_resp = auth_session.post(f"{BASE_URL}/api/bb/job-openings", json={
            "title": "TEST_JD_Opening",
            "job_role": "Developer",
            "vacancies": 3
        })
        opening_id = opening_resp.json().get("id")
        
        # Create form type
        type_resp = auth_session.post(f"{BASE_URL}/api/bb/form-types", json={"name": "TEST_JD_Type"})
        type_id = type_resp.json().get("id")
        
        # Create job role
        role_resp = auth_session.post(f"{BASE_URL}/api/bb/job-roles", json={"name": "TEST_JD_Role"})
        role_id = role_resp.json().get("id")
        
        # Create hiring form with JD attached
        form_resp = auth_session.post(f"{BASE_URL}/api/bb/hiring-forms", json={
            "name": "TEST_Form_With_JD",
            "form_type_id": type_id,
            "job_role": "TEST_JD_Role",
            "job_description_attached": True,
            "job_opening_id": opening_id
        })
        assert form_resp.status_code == 200
        form_data = form_resp.json()
        assert form_data.get("success") == True
        form_id = form_data.get("form", {}).get("id")
        
        # Verify form has JD fields
        forms_resp = auth_session.get(f"{BASE_URL}/api/bb/hiring-forms")
        forms = forms_resp.json().get("forms", [])
        created_form = next((f for f in forms if f.get("id") == form_id), None)
        assert created_form is not None
        assert created_form.get("job_description_attached") == True
        assert created_form.get("job_opening_id") == opening_id
        print("PASS: Hiring form created with job_description_attached and job_opening_id")
        
        # Verify public form endpoint includes job_opening
        pub_resp = requests.get(f"{BASE_URL}/api/pub/form/{form_id}")
        pub_data = pub_resp.json()
        assert pub_data.get("job_description_attached") == True
        assert "job_opening" in pub_data
        assert pub_data.get("job_opening", {}).get("title") == "TEST_JD_Opening"
        print("PASS: Public form endpoint includes job_opening details")
        
        # Cleanup
        auth_session.delete(f"{BASE_URL}/api/bb/hiring-forms/{form_id}")
        auth_session.delete(f"{BASE_URL}/api/bb/form-types/{type_id}")
        auth_session.delete(f"{BASE_URL}/api/bb/job-roles/{role_id}")
        auth_session.delete(f"{BASE_URL}/api/bb/job-openings/{opening_id}")


class TestExistingEndpoints:
    """Verify existing endpoints still work with new credentials"""
    
    def test_summary_endpoint(self, auth_session):
        """GET /api/summary still works"""
        response = auth_session.get(f"{BASE_URL}/api/summary")
        assert response.status_code == 200
        print("PASS: GET /api/summary works with new credentials")
    
    def test_applicants_endpoint(self, auth_session):
        """GET /api/applicants still works"""
        response = auth_session.get(f"{BASE_URL}/api/applicants")
        assert response.status_code == 200
        print("PASS: GET /api/applicants works with new credentials")
    
    def test_attended_endpoint(self, auth_session):
        """GET /api/attended still works"""
        response = auth_session.get(f"{BASE_URL}/api/attended")
        assert response.status_code == 200
        print("PASS: GET /api/attended works with new credentials")
    
    def test_job_roles_endpoint(self, auth_session):
        """GET /api/job-roles still works"""
        response = auth_session.get(f"{BASE_URL}/api/job-roles")
        assert response.status_code == 200
        print("PASS: GET /api/job-roles works with new credentials")
    
    def test_bulk_upload_status(self, auth_session):
        """GET /api/bulk-upload/status still works"""
        response = auth_session.get(f"{BASE_URL}/api/bulk-upload/status")
        assert response.status_code == 200
        print("PASS: GET /api/bulk-upload/status works with new credentials")


class TestCleanup:
    """Cleanup test data"""
    
    def test_cleanup_holidays(self, auth_session):
        """Remove TEST_ holidays"""
        response = auth_session.get(f"{BASE_URL}/api/bb/holidays")
        holidays = response.json().get("holidays", [])
        for h in holidays:
            if h.get("name", "").startswith("TEST_"):
                auth_session.delete(f"{BASE_URL}/api/bb/holidays/{h['id']}")
        print("PASS: Cleaned up TEST_ holidays")
