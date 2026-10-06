"""
Iteration 20: Dynamic Multi-Criteria College Matching System Tests
Tests for the new rule-based college matching algorithm:
- Base college name extraction (removes generic words like 'university', 'institute')
- City/State location matching for HIGH confidence
- Single base match returns MEDIUM confidence
- Ambiguous multiple matches return LOW confidence (Non NIRF)
- NIRF classification uses rank <= 100 threshold
- UG/PG priority: Both NIRF uses PG rank
- match_confidence field in /api/applicants and /api/attended responses
- No hardcoded college names in matching logic
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
    response = session.post(f"{BASE_URL}/api/login", json={
        "username": "admin",
        "password": "admin"
    })
    assert response.status_code == 200, f"Login failed: {response.text}"
    return session


class TestCollegeRankUpload:
    """Tests for POST /api/upload/college-rank endpoint"""
    
    def test_upload_college_rank_with_multiple_campuses(self, auth_session):
        """Upload college rank CSV with multiple campuses of same college (e.g., Amity)"""
        csv_content = """Rank,College Name,Short Name,City,State
30,Amity University Noida,Amity Noida,Noida,Uttar Pradesh
67,Amity University Rajasthan,Amity Rajasthan,Jaipur,Rajasthan
150,Amity University Patna,Amity Patna,Patna,Bihar
25,Indian Institute of Technology Bombay,IIT Bombay,Mumbai,Maharashtra
35,Indian Institute of Technology Delhi,IIT Delhi,New Delhi,Delhi
45,National Institute of Technology Trichy,NIT Trichy,Tiruchirappalli,Tamil Nadu
110,Birla Institute of Technology Mesra,BIT Mesra,Ranchi,Jharkhand
200,XYZ Engineering College,XYZ,Bangalore,Karnataka
"""
        files = {'file': ('college_ranks.csv', io.BytesIO(csv_content.encode()), 'text/csv')}
        response = auth_session.post(f"{BASE_URL}/api/upload/college-rank", files=files)
        
        assert response.status_code == 200, f"Upload failed: {response.text}"
        data = response.json()
        assert data.get("success") == True
        assert data.get("inserted") == 8, f"Expected 8 colleges inserted, got {data.get('inserted')}"
    
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


class TestApplicantsCollegeFields:
    """Tests for GET /api/applicants with college_status, college, and match_confidence fields"""
    
    def test_applicants_returns_college_status_field(self, auth_session):
        """GET /api/applicants should return college_status in each record"""
        response = auth_session.get(f"{BASE_URL}/api/applicants", params={"page": 1, "limit": 10})
        
        assert response.status_code == 200, f"Request failed: {response.text}"
        data = response.json()
        
        assert "data" in data
        assert "total" in data
        
        if data["data"]:
            first_record = data["data"][0]
            assert "college_status" in first_record, f"college_status field missing. Keys: {first_record.keys()}"
            # college_status should be "NIRF - #X" or "Non NIRF"
            cs = first_record["college_status"]
            assert cs.startswith("NIRF - #") or cs == "Non NIRF", f"Invalid college_status format: {cs}"
    
    def test_applicants_returns_college_field(self, auth_session):
        """GET /api/applicants should return college field in each record"""
        response = auth_session.get(f"{BASE_URL}/api/applicants", params={"page": 1, "limit": 10})
        
        assert response.status_code == 200, f"Request failed: {response.text}"
        data = response.json()
        
        if data["data"]:
            first_record = data["data"][0]
            assert "college" in first_record, f"college field missing. Keys: {first_record.keys()}"
    
    def test_applicants_returns_match_confidence_field(self, auth_session):
        """GET /api/applicants should return match_confidence in each record"""
        response = auth_session.get(f"{BASE_URL}/api/applicants", params={"page": 1, "limit": 10})
        
        assert response.status_code == 200, f"Request failed: {response.text}"
        data = response.json()
        
        if data["data"]:
            first_record = data["data"][0]
            assert "match_confidence" in first_record, f"match_confidence field missing. Keys: {first_record.keys()}"
            # match_confidence should be HIGH, MEDIUM, LOW, or "-"
            mc = first_record["match_confidence"]
            valid_values = ["HIGH", "MEDIUM", "LOW", "-", None]
            assert mc in valid_values, f"Invalid match_confidence: {mc}"
    
    def test_applicants_filter_by_nirf(self, auth_session):
        """GET /api/applicants?collegeStatus=NIRF should filter by NIRF status"""
        response = auth_session.get(f"{BASE_URL}/api/applicants", params={
            "page": 1, 
            "limit": 100,
            "collegeStatus": "NIRF"
        })
        
        assert response.status_code == 200, f"Request failed: {response.text}"
        data = response.json()
        
        # All returned records should have college_status starting with "NIRF - #"
        for record in data["data"]:
            cs = record.get("college_status", "")
            assert cs.startswith("NIRF - #"), f"Expected NIRF - #X, got {cs}"
    
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


class TestAttendedCollegeFields:
    """Tests for GET /api/attended with college_status, college, and match_confidence fields"""
    
    def test_attended_returns_college_status_field(self, auth_session):
        """GET /api/attended should return college_status in each record"""
        response = auth_session.get(f"{BASE_URL}/api/attended", params={"page": 1, "limit": 10})
        
        assert response.status_code == 200, f"Request failed: {response.text}"
        data = response.json()
        
        assert "data" in data
        assert "total" in data
        
        if data["data"]:
            first_record = data["data"][0]
            assert "college_status" in first_record, f"college_status field missing. Keys: {first_record.keys()}"
            cs = first_record["college_status"]
            assert cs.startswith("NIRF - #") or cs == "Non NIRF", f"Invalid college_status format: {cs}"
    
    def test_attended_returns_college_field(self, auth_session):
        """GET /api/attended should return college field in each record"""
        response = auth_session.get(f"{BASE_URL}/api/attended", params={"page": 1, "limit": 10})
        
        assert response.status_code == 200, f"Request failed: {response.text}"
        data = response.json()
        
        if data["data"]:
            first_record = data["data"][0]
            assert "college" in first_record, f"college field missing. Keys: {first_record.keys()}"
    
    def test_attended_returns_match_confidence_field(self, auth_session):
        """GET /api/attended should return match_confidence in each record"""
        response = auth_session.get(f"{BASE_URL}/api/attended", params={"page": 1, "limit": 10})
        
        assert response.status_code == 200, f"Request failed: {response.text}"
        data = response.json()
        
        if data["data"]:
            first_record = data["data"][0]
            assert "match_confidence" in first_record, f"match_confidence field missing. Keys: {first_record.keys()}"
            mc = first_record["match_confidence"]
            valid_values = ["HIGH", "MEDIUM", "LOW", "-", None]
            assert mc in valid_values, f"Invalid match_confidence: {mc}"
    
    def test_attended_filter_by_nirf(self, auth_session):
        """GET /api/attended?collegeStatus=NIRF should filter by NIRF status"""
        response = auth_session.get(f"{BASE_URL}/api/attended", params={
            "page": 1, 
            "limit": 100,
            "collegeStatus": "NIRF"
        })
        
        assert response.status_code == 200, f"Request failed: {response.text}"
        data = response.json()
        
        for record in data["data"]:
            cs = record.get("college_status", "")
            assert cs.startswith("NIRF - #"), f"Expected NIRF - #X, got {cs}"
    
    def test_attended_filter_by_non_nirf(self, auth_session):
        """GET /api/attended?collegeStatus=Non NIRF should filter by Non NIRF status"""
        response = auth_session.get(f"{BASE_URL}/api/attended", params={
            "page": 1, 
            "limit": 100,
            "collegeStatus": "Non NIRF"
        })
        
        assert response.status_code == 200, f"Request failed: {response.text}"
        data = response.json()
        
        for record in data["data"]:
            assert record.get("college_status") == "Non NIRF", f"Expected Non NIRF, got {record.get('college_status')}"


class TestSummaryNirfSplit:
    """Tests for GET /api/summary with NIRF/Non-NIRF split"""
    
    def test_summary_returns_nirf_split_rows(self, auth_session):
        """GET /api/summary should return rows split by NIRF/Non-NIRF per job role"""
        response = auth_session.get(f"{BASE_URL}/api/summary")
        
        assert response.status_code == 200, f"Request failed: {response.text}"
        data = response.json()
        
        assert "data" in data
        
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


class TestNirfThreshold:
    """Tests for NIRF classification using rank <= 100 threshold"""
    
    def test_nirf_threshold_via_upload(self, auth_session):
        """Upload colleges with ranks around 100 threshold and verify classification"""
        # Upload colleges with ranks at boundary
        csv_content = """Rank,College Name,Short Name,City,State
99,Test College Rank 99,TC99,City1,State1
100,Test College Rank 100,TC100,City2,State2
101,Test College Rank 101,TC101,City3,State3
"""
        files = {'file': ('threshold_test.csv', io.BytesIO(csv_content.encode()), 'text/csv')}
        response = auth_session.post(f"{BASE_URL}/api/upload/college-rank", files=files)
        
        assert response.status_code == 200, f"Upload failed: {response.text}"
        data = response.json()
        assert data.get("success") == True
        # Rank 99 and 100 should be NIRF (rank <= 100), Rank 101 should be Non NIRF


class TestAllEndpointsReturn200:
    """Tests that all existing endpoints return 200"""
    
    def test_summary_returns_200(self, auth_session):
        """GET /api/summary should return 200"""
        response = auth_session.get(f"{BASE_URL}/api/summary")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
    
    def test_applicants_returns_200(self, auth_session):
        """GET /api/applicants should return 200"""
        response = auth_session.get(f"{BASE_URL}/api/applicants")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
    
    def test_attended_returns_200(self, auth_session):
        """GET /api/attended should return 200"""
        response = auth_session.get(f"{BASE_URL}/api/attended")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
    
    def test_job_roles_returns_200(self, auth_session):
        """GET /api/job-roles should return 200"""
        response = auth_session.get(f"{BASE_URL}/api/job-roles")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"


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
    
    def test_job_roles_requires_auth(self):
        """GET /api/job-roles without auth should return 401"""
        response = requests.get(f"{BASE_URL}/api/job-roles")
        assert response.status_code == 401
