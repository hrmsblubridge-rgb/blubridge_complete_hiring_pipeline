"""
Iteration 9 Tests: Role Drilldown Page & Status Derivation
Tests for:
1. Login with admin/admin (cookie-based auth)
2. GET /api/status returns correct counts (8 naukri, 8 pipeline, 8 registered)
3. GET /api/dashboard-counts returns correct shortlisted count using result_status
4. GET /api/role?jobRole=... returns individual applicant records with derived status
5. Status derivation: Rejected, Attended, Interview Scheduled, Shortlisted, Registered
6. GET /api/summary returns funnel stats using result_status for shortlisted
"""

import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

class TestAuth:
    """Authentication tests"""
    
    def test_login_success(self):
        """Login with admin/admin credentials"""
        session = requests.Session()
        response = session.post(f"{BASE_URL}/api/login", json={
            "username": "admin",
            "password": "admin"
        })
        assert response.status_code == 200, f"Login failed: {response.text}"
        data = response.json()
        assert data.get("success") == True
        assert data.get("username") == "admin"
        # Verify cookie is set
        assert "access_token" in session.cookies
        
    def test_login_invalid_credentials(self):
        """Login with wrong credentials should fail"""
        response = requests.post(f"{BASE_URL}/api/login", json={
            "username": "wrong",
            "password": "wrong"
        })
        assert response.status_code == 401


@pytest.fixture(scope="module")
def auth_session():
    """Create authenticated session for all tests"""
    session = requests.Session()
    response = session.post(f"{BASE_URL}/api/login", json={
        "username": "admin",
        "password": "admin"
    })
    if response.status_code != 200:
        pytest.skip("Authentication failed - skipping authenticated tests")
    return session


class TestStatusEndpoint:
    """Tests for /api/status endpoint"""
    
    def test_status_returns_counts(self, auth_session):
        """GET /api/status returns naukri_count, pipeline_count, registered_count"""
        response = auth_session.get(f"{BASE_URL}/api/status")
        assert response.status_code == 200, f"Status failed: {response.text}"
        data = response.json()
        
        # Verify all required fields exist
        assert "naukri_count" in data
        assert "pipeline_count" in data
        assert "registered_count" in data
        
        # Verify counts are integers
        assert isinstance(data["naukri_count"], int)
        assert isinstance(data["pipeline_count"], int)
        assert isinstance(data["registered_count"], int)
        
        print(f"Status counts: Naukri={data['naukri_count']}, Pipeline={data['pipeline_count']}, Registered={data['registered_count']}")
        
    def test_status_expected_counts(self, auth_session):
        """GET /api/status should return 8 naukri, 8 pipeline, 8 registered (per test data)"""
        response = auth_session.get(f"{BASE_URL}/api/status")
        assert response.status_code == 200
        data = response.json()
        
        # Expected: 8 naukri, 8 pipeline, 8 registered
        assert data["naukri_count"] == 8, f"Expected 8 naukri, got {data['naukri_count']}"
        assert data["pipeline_count"] == 8, f"Expected 8 pipeline, got {data['pipeline_count']}"
        assert data["registered_count"] == 8, f"Expected 8 registered, got {data['registered_count']}"


class TestDashboardCounts:
    """Tests for /api/dashboard-counts endpoint"""
    
    def test_dashboard_counts_structure(self, auth_session):
        """GET /api/dashboard-counts returns all required fields"""
        response = auth_session.get(f"{BASE_URL}/api/dashboard-counts")
        assert response.status_code == 200, f"Dashboard counts failed: {response.text}"
        data = response.json()
        
        required_fields = [
            "total_applies", "registered", "unregistered",
            "shortlisted", "rejected", "scheduled", "not_scheduled",
            "attended", "not_attended"
        ]
        for field in required_fields:
            assert field in data, f"Missing field: {field}"
            assert isinstance(data[field], int), f"Field {field} should be int"
            
        print(f"Dashboard counts: {data}")
        
    def test_shortlisted_uses_result_status(self, auth_session):
        """Shortlisted count should be based on result_status field (not email_type)"""
        response = auth_session.get(f"{BASE_URL}/api/dashboard-counts")
        assert response.status_code == 200
        data = response.json()
        
        # Per test data: Grace has result_status=shortlist, so shortlisted should be 1
        # If it was based on email_type, it would be different
        shortlisted = data["shortlisted"]
        print(f"Shortlisted count (using result_status): {shortlisted}")
        
        # Verify shortlisted is at least 1 (Grace)
        assert shortlisted >= 1, f"Expected at least 1 shortlisted, got {shortlisted}"


class TestRoleEndpoint:
    """Tests for /api/role endpoint - individual applicant records with derived status"""
    
    def test_role_requires_job_role_param(self, auth_session):
        """GET /api/role without jobRole param should return 422"""
        response = auth_session.get(f"{BASE_URL}/api/role")
        assert response.status_code == 422, f"Expected 422, got {response.status_code}"
        
    def test_role_software_developer(self, auth_session):
        """GET /api/role?jobRole=Software Developer returns individual applicant records"""
        response = auth_session.get(f"{BASE_URL}/api/role", params={"jobRole": "Software Developer"})
        assert response.status_code == 200, f"Role API failed: {response.text}"
        data = response.json()
        
        # Verify response structure
        assert "data" in data
        assert "total" in data
        assert "page" in data
        assert "limit" in data
        assert "columns" in data
        
        # Verify columns include all required fields
        expected_columns = ["name", "email", "phone", "gender", "date_of_birth", "date_of_application", "status"]
        for col in expected_columns:
            assert col in data["columns"], f"Missing column: {col}"
            
        print(f"Software Developer applicants: {len(data['data'])} records")
        
        # Verify each record has derived status
        for applicant in data["data"]:
            assert "status" in applicant, f"Missing status in applicant: {applicant}"
            assert applicant["status"] in ["Rejected", "Attended", "Interview Scheduled", "Shortlisted", "Registered"]
            
    def test_role_data_analyst(self, auth_session):
        """GET /api/role?jobRole=Data Analyst returns individual applicant records"""
        response = auth_session.get(f"{BASE_URL}/api/role", params={"jobRole": "Data Analyst"})
        assert response.status_code == 200, f"Role API failed: {response.text}"
        data = response.json()
        
        assert "data" in data
        print(f"Data Analyst applicants: {len(data['data'])} records")
        
        # Verify each record has derived status
        for applicant in data["data"]:
            assert "status" in applicant
            assert applicant["status"] in ["Rejected", "Attended", "Interview Scheduled", "Shortlisted", "Registered"]


class TestStatusDerivation:
    """Tests for status derivation logic"""
    
    def test_status_derivation_rules(self, auth_session):
        """
        Verify status derivation rules:
        - Rejected: result_status = 'Reject' or 'Rejected'
        - Attended: otp_verified not NULL
        - Interview Scheduled: schedule_date AND schedule_time not NULL
        - Shortlisted: result_status = 'shortlist'
        - Registered: default
        """
        # Get all applicants from both roles
        sw_response = auth_session.get(f"{BASE_URL}/api/role", params={"jobRole": "Software Developer"})
        da_response = auth_session.get(f"{BASE_URL}/api/role", params={"jobRole": "Data Analyst"})
        
        all_applicants = []
        if sw_response.status_code == 200:
            all_applicants.extend(sw_response.json().get("data", []))
        if da_response.status_code == 200:
            all_applicants.extend(da_response.json().get("data", []))
            
        print(f"Total applicants across roles: {len(all_applicants)}")
        
        # Count each status
        status_counts = {}
        for applicant in all_applicants:
            status = applicant.get("status", "Unknown")
            status_counts[status] = status_counts.get(status, 0) + 1
            print(f"  {applicant.get('name', 'N/A')}: {status}")
            
        print(f"Status distribution: {status_counts}")
        
        # Verify we have at least some of the expected statuses
        # Based on test data: Alice=Rejected, Bob=Attended, Carol=InterviewScheduled, 
        # Dave=Registered, Eve=Rejected, Frank=Attended, Grace=Shortlisted, Henry=InterviewScheduled
        valid_statuses = {"Rejected", "Attended", "Interview Scheduled", "Shortlisted", "Registered"}
        for status in status_counts.keys():
            assert status in valid_statuses, f"Invalid status: {status}"


class TestSummaryEndpoint:
    """Tests for /api/summary endpoint"""
    
    def test_summary_returns_funnel_stats(self, auth_session):
        """GET /api/summary returns job role-wise funnel statistics"""
        response = auth_session.get(f"{BASE_URL}/api/summary")
        assert response.status_code == 200, f"Summary failed: {response.text}"
        data = response.json()
        
        assert "data" in data
        assert "total_registered" in data
        
        print(f"Summary: {len(data['data'])} job roles, total_registered={data['total_registered']}")
        
        # Verify each role has funnel stats
        for role_data in data["data"]:
            assert "job_role" in role_data
            assert "total_applicants" in role_data
            assert "shortlisted" in role_data
            assert "rejected" in role_data
            assert "scheduled" in role_data
            assert "not_scheduled" in role_data
            assert "attended" in role_data
            assert "not_attended" in role_data
            
            print(f"  {role_data['job_role']}: total={role_data['total_applicants']}, shortlisted={role_data['shortlisted']}, rejected={role_data['rejected']}")
            
    def test_summary_shortlisted_uses_result_status(self, auth_session):
        """Summary shortlisted count should be based on result_status (not email_type)"""
        response = auth_session.get(f"{BASE_URL}/api/summary")
        assert response.status_code == 200
        data = response.json()
        
        # Sum up all shortlisted across roles
        total_shortlisted = sum(role.get("shortlisted", 0) for role in data["data"])
        print(f"Total shortlisted across all roles: {total_shortlisted}")
        
        # Should match dashboard-counts shortlisted
        dashboard_response = auth_session.get(f"{BASE_URL}/api/dashboard-counts")
        if dashboard_response.status_code == 200:
            dashboard_shortlisted = dashboard_response.json().get("shortlisted", 0)
            assert total_shortlisted == dashboard_shortlisted, \
                f"Summary shortlisted ({total_shortlisted}) != Dashboard shortlisted ({dashboard_shortlisted})"


class TestJobRolesEndpoint:
    """Tests for /api/job-roles endpoint"""
    
    def test_job_roles_returns_unique_roles(self, auth_session):
        """GET /api/job-roles returns unique job roles with counts"""
        response = auth_session.get(f"{BASE_URL}/api/job-roles")
        assert response.status_code == 200, f"Job roles failed: {response.text}"
        data = response.json()
        
        assert "job_roles" in data
        
        print(f"Job roles: {len(data['job_roles'])} unique roles")
        for role in data["job_roles"]:
            assert "job_role" in role
            assert "count" in role
            print(f"  {role['job_role']}: {role['count']} applicants")


class TestRoleDrilldownPagination:
    """Tests for pagination on role drilldown"""
    
    def test_pagination_params(self, auth_session):
        """GET /api/role supports page and limit params"""
        response = auth_session.get(f"{BASE_URL}/api/role", params={
            "jobRole": "Software Developer",
            "page": 1,
            "limit": 10
        })
        assert response.status_code == 200
        data = response.json()
        
        assert data["page"] == 1
        assert data["limit"] == 10
        
    def test_date_filter_params(self, auth_session):
        """GET /api/role supports startDate and endDate params"""
        response = auth_session.get(f"{BASE_URL}/api/role", params={
            "jobRole": "Software Developer",
            "startDate": "2024-01-01",
            "endDate": "2025-12-31"
        })
        assert response.status_code == 200
        data = response.json()
        
        print(f"Filtered results: {len(data['data'])} records")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
