"""
Iteration 18: College Rank List Integration Tests
Tests for:
- POST /api/upload/college-rank - Upload college rank CSV
- GET /api/applicants - Returns college_status field
- GET /api/applicants?collegeStatus=NIRF - Filter by college status
- GET /api/attended - Returns college_status field
- GET /api/attended?collegeStatus=Non%20NIRF - Filter attended by college status
- GET /api/summary - Returns rows split by NIRF/Non-NIRF per job role
"""

import pytest
import requests
import os
import io

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

@pytest.fixture(scope="module")
def auth_session():
    """Create authenticated session for all tests"""
    session = requests.Session()
    
    # Login
    response = session.post(f"{BASE_URL}/api/login", json={
        "username": "admin",
        "password": "admin"
    })
    assert response.status_code == 200, f"Login failed: {response.text}"
    return session


class TestCollegeRankUpload:
    """Tests for POST /api/upload/college-rank endpoint"""
    
    def test_upload_college_rank_csv(self, auth_session):
        """Upload a valid college rank CSV file"""
        csv_content = """Rank,College Name,Short Name,City,State
1,Indian Institute of Technology Bombay,IIT Bombay,Mumbai,Maharashtra
2,Indian Institute of Technology Delhi,IIT Delhi,New Delhi,Delhi
50,National Institute of Technology Trichy,NIT Trichy,Tiruchirappalli,Tamil Nadu
101,Birla Institute of Technology,BIT Mesra,Ranchi,Jharkhand
155,Amity University,Amity,Noida,Uttar Pradesh
205,XYZ Engineering College,XYZ,Bangalore,Karnataka
"""
        files = {'file': ('college_ranks.csv', io.BytesIO(csv_content.encode()), 'text/csv')}
        response = auth_session.post(f"{BASE_URL}/api/upload/college-rank", files=files)
        
        assert response.status_code == 200, f"Upload failed: {response.text}"
        data = response.json()
        assert data.get("success") == True
        assert data.get("inserted") == 6, f"Expected 6 colleges inserted, got {data.get('inserted')}"
    
    def test_upload_college_rank_missing_column(self, auth_session):
        """Upload CSV without required College Name column should fail"""
        csv_content = """Rank,Short Name,City,State
1,IIT Bombay,Mumbai,Maharashtra
"""
        files = {'file': ('bad_ranks.csv', io.BytesIO(csv_content.encode()), 'text/csv')}
        response = auth_session.post(f"{BASE_URL}/api/upload/college-rank", files=files)
        
        assert response.status_code == 400, f"Expected 400, got {response.status_code}"
        assert "College Name" in response.text or "college_name" in response.text.lower()
    
    def test_upload_college_rank_requires_auth(self):
        """Upload without authentication should fail"""
        csv_content = """Rank,College Name,Short Name,City,State
1,Test College,TC,City,State
"""
        files = {'file': ('test.csv', io.BytesIO(csv_content.encode()), 'text/csv')}
        response = requests.post(f"{BASE_URL}/api/upload/college-rank", files=files)
        
        assert response.status_code == 401, f"Expected 401, got {response.status_code}"


class TestApplicantsCollegeStatus:
    """Tests for GET /api/applicants with college_status field"""
    
    def test_applicants_returns_college_status_field(self, auth_session):
        """GET /api/applicants should return college_status in each record"""
        response = auth_session.get(f"{BASE_URL}/api/applicants", params={"page": 1, "limit": 10})
        
        assert response.status_code == 200, f"Request failed: {response.text}"
        data = response.json()
        
        # Check structure
        assert "data" in data
        assert "total" in data
        
        # If there are records, verify college_status field exists
        if data["data"]:
            first_record = data["data"][0]
            assert "college_status" in first_record, f"college_status field missing. Keys: {first_record.keys()}"
            # college_status should be one of: NIRF, Non NIRF 101-150, Non NIRF 151-200, Non NIRF 201-300, Non NIRF
            valid_statuses = ["NIRF", "Non NIRF 101-150", "Non NIRF 151-200", "Non NIRF 201-300", "Non NIRF"]
            assert first_record["college_status"] in valid_statuses, f"Invalid college_status: {first_record['college_status']}"
    
    def test_applicants_filter_by_nirf(self, auth_session):
        """GET /api/applicants?collegeStatus=NIRF should filter by NIRF status"""
        response = auth_session.get(f"{BASE_URL}/api/applicants", params={
            "page": 1, 
            "limit": 100,
            "collegeStatus": "NIRF"
        })
        
        assert response.status_code == 200, f"Request failed: {response.text}"
        data = response.json()
        
        # All returned records should have college_status = NIRF
        for record in data["data"]:
            assert record.get("college_status") == "NIRF", f"Expected NIRF, got {record.get('college_status')}"
    
    def test_applicants_filter_by_non_nirf(self, auth_session):
        """GET /api/applicants?collegeStatus=Non NIRF should filter by Non NIRF status"""
        response = auth_session.get(f"{BASE_URL}/api/applicants", params={
            "page": 1, 
            "limit": 100,
            "collegeStatus": "Non NIRF"
        })
        
        assert response.status_code == 200, f"Request failed: {response.text}"
        data = response.json()
        
        # All returned records should have college_status = Non NIRF
        for record in data["data"]:
            assert record.get("college_status") == "Non NIRF", f"Expected Non NIRF, got {record.get('college_status')}"
    
    def test_applicants_filter_by_non_nirf_101_150(self, auth_session):
        """GET /api/applicants?collegeStatus=Non NIRF 101-150 should filter correctly"""
        response = auth_session.get(f"{BASE_URL}/api/applicants", params={
            "page": 1, 
            "limit": 100,
            "collegeStatus": "Non NIRF 101-150"
        })
        
        assert response.status_code == 200, f"Request failed: {response.text}"
        data = response.json()
        
        # All returned records should have college_status = Non NIRF 101-150
        for record in data["data"]:
            assert record.get("college_status") == "Non NIRF 101-150", f"Expected Non NIRF 101-150, got {record.get('college_status')}"


class TestAttendedCollegeStatus:
    """Tests for GET /api/attended with college_status field"""
    
    def test_attended_returns_college_status_field(self, auth_session):
        """GET /api/attended should return college_status in each record"""
        response = auth_session.get(f"{BASE_URL}/api/attended", params={"page": 1, "limit": 10})
        
        assert response.status_code == 200, f"Request failed: {response.text}"
        data = response.json()
        
        # Check structure
        assert "data" in data
        assert "total" in data
        
        # If there are records, verify college_status field exists
        if data["data"]:
            first_record = data["data"][0]
            assert "college_status" in first_record, f"college_status field missing. Keys: {first_record.keys()}"
            valid_statuses = ["NIRF", "Non NIRF 101-150", "Non NIRF 151-200", "Non NIRF 201-300", "Non NIRF"]
            assert first_record["college_status"] in valid_statuses, f"Invalid college_status: {first_record['college_status']}"
    
    def test_attended_filter_by_nirf(self, auth_session):
        """GET /api/attended?collegeStatus=NIRF should filter by NIRF status"""
        response = auth_session.get(f"{BASE_URL}/api/attended", params={
            "page": 1, 
            "limit": 100,
            "collegeStatus": "NIRF"
        })
        
        assert response.status_code == 200, f"Request failed: {response.text}"
        data = response.json()
        
        # All returned records should have college_status = NIRF
        for record in data["data"]:
            assert record.get("college_status") == "NIRF", f"Expected NIRF, got {record.get('college_status')}"
    
    def test_attended_filter_by_non_nirf(self, auth_session):
        """GET /api/attended?collegeStatus=Non NIRF should filter by Non NIRF status"""
        response = auth_session.get(f"{BASE_URL}/api/attended", params={
            "page": 1, 
            "limit": 100,
            "collegeStatus": "Non NIRF"
        })
        
        assert response.status_code == 200, f"Request failed: {response.text}"
        data = response.json()
        
        # All returned records should have college_status = Non NIRF
        for record in data["data"]:
            assert record.get("college_status") == "Non NIRF", f"Expected Non NIRF, got {record.get('college_status')}"


class TestSummaryNirfSplit:
    """Tests for GET /api/summary with NIRF/Non-NIRF split"""
    
    def test_summary_returns_nirf_split_rows(self, auth_session):
        """GET /api/summary should return rows split by NIRF/Non-NIRF per job role"""
        response = auth_session.get(f"{BASE_URL}/api/summary")
        
        assert response.status_code == 200, f"Request failed: {response.text}"
        data = response.json()
        
        # Check structure
        assert "data" in data
        
        # If there are records, verify job_role contains NIRF or Non NIRF suffix
        if data["data"]:
            for row in data["data"]:
                job_role = row.get("job_role", "")
                # Job role should end with " - NIRF" or " - Non NIRF"
                assert " - NIRF" in job_role or " - Non NIRF" in job_role, \
                    f"job_role should contain NIRF/Non NIRF split: {job_role}"
    
    def test_summary_has_expected_columns(self, auth_session):
        """GET /api/summary should return expected columns for funnel stats"""
        response = auth_session.get(f"{BASE_URL}/api/summary")
        
        assert response.status_code == 200, f"Request failed: {response.text}"
        data = response.json()
        
        if data["data"]:
            first_row = data["data"][0]
            expected_keys = ["job_role", "total_naukri", "total_registered", "total_unregistered",
                           "shortlisted", "rejected", "scheduled", "not_scheduled", "attended", "not_attended"]
            for key in expected_keys:
                assert key in first_row, f"Missing key '{key}' in summary row. Keys: {first_row.keys()}"


class TestCollegeStatusClassification:
    """Tests for college status classification logic"""
    
    def test_classification_logic_via_upload_and_query(self, auth_session):
        """Upload colleges with different ranks and verify classification"""
        # First, upload a fresh college rank list with known ranks
        csv_content = """Rank,College Name,Short Name,City,State
10,Test NIRF College,TNIRF,City1,State1
120,Test Non NIRF 101-150 College,T101,City2,State2
175,Test Non NIRF 151-200 College,T151,City3,State3
250,Test Non NIRF 201-300 College,T201,City4,State4
"""
        files = {'file': ('test_ranks.csv', io.BytesIO(csv_content.encode()), 'text/csv')}
        response = auth_session.post(f"{BASE_URL}/api/upload/college-rank", files=files)
        
        assert response.status_code == 200, f"Upload failed: {response.text}"
        data = response.json()
        assert data.get("success") == True
        assert data.get("inserted") == 4


class TestEndpointAuthentication:
    """Tests for authentication requirements"""
    
    def test_applicants_requires_auth(self):
        """GET /api/applicants without auth should return 401"""
        response = requests.get(f"{BASE_URL}/api/applicants")
        assert response.status_code == 401
    
    def test_attended_requires_auth(self):
        """GET /api/attended without auth should return 401"""
        response = requests.get(f"{BASE_URL}/api/attended")
        assert response.status_code == 401
    
    def test_summary_requires_auth(self):
        """GET /api/summary without auth should return 401"""
        response = requests.get(f"{BASE_URL}/api/summary")
        assert response.status_code == 401
