"""
Iteration 15: Backend API Tests for Recruitment Analytics App
Tests: Login, Status, Job Roles, Role Drilldown, Attended Roles, Attended Drilldown
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

class TestAuth:
    """Authentication endpoint tests"""
    
    def test_login_success(self):
        """Test login with admin/admin credentials"""
        response = requests.post(f"{BASE_URL}/api/login", json={
            "username": "admin",
            "password": "admin"
        })
        assert response.status_code == 200, f"Login failed: {response.text}"
        data = response.json()
        assert data.get("success") == True
        assert data.get("username") == "admin"
        print(f"✓ Login successful: {data}")
    
    def test_login_invalid_credentials(self):
        """Test login with wrong credentials"""
        response = requests.post(f"{BASE_URL}/api/login", json={
            "username": "wrong",
            "password": "wrong"
        })
        assert response.status_code == 401
        print("✓ Invalid credentials correctly rejected")


class TestStatusEndpoint:
    """Test /api/status endpoint"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Login and get session cookie"""
        self.session = requests.Session()
        login_resp = self.session.post(f"{BASE_URL}/api/login", json={
            "username": "admin",
            "password": "admin"
        })
        assert login_resp.status_code == 200, "Login failed in setup"
    
    def test_status_returns_counts(self):
        """GET /api/status returns naukri_count, pipeline_count, registered_count"""
        response = self.session.get(f"{BASE_URL}/api/status")
        assert response.status_code == 200, f"Status failed: {response.text}"
        data = response.json()
        
        # Verify required fields exist
        assert "naukri_count" in data, "Missing naukri_count"
        assert "pipeline_count" in data, "Missing pipeline_count"
        assert "registered_count" in data, "Missing registered_count"
        
        # Verify counts are integers
        assert isinstance(data["naukri_count"], int)
        assert isinstance(data["pipeline_count"], int)
        assert isinstance(data["registered_count"], int)
        
        print(f"✓ Status: naukri={data['naukri_count']}, pipeline={data['pipeline_count']}, registered={data['registered_count']}")


class TestJobRolesEndpoint:
    """Test /api/job-roles endpoint"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        self.session = requests.Session()
        login_resp = self.session.post(f"{BASE_URL}/api/login", json={
            "username": "admin",
            "password": "admin"
        })
        assert login_resp.status_code == 200
    
    def test_job_roles_returns_list(self):
        """GET /api/job-roles returns job roles list"""
        response = self.session.get(f"{BASE_URL}/api/job-roles")
        assert response.status_code == 200, f"Job roles failed: {response.text}"
        data = response.json()
        
        assert "job_roles" in data, "Missing job_roles field"
        assert isinstance(data["job_roles"], list)
        
        if len(data["job_roles"]) > 0:
            role = data["job_roles"][0]
            assert "job_role" in role, "Missing job_role in role object"
            assert "count" in role, "Missing count in role object"
            print(f"✓ Job roles: {len(data['job_roles'])} roles found. First: {role}")
        else:
            print("✓ Job roles: Empty list (no registered candidates)")


class TestRoleEndpoint:
    """Test /api/role endpoint - paginated applicant data"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        self.session = requests.Session()
        login_resp = self.session.post(f"{BASE_URL}/api/login", json={
            "username": "admin",
            "password": "admin"
        })
        assert login_resp.status_code == 200
    
    def test_role_with_valid_job_role(self):
        """GET /api/role?jobRole=... returns paginated applicant data with status field"""
        # Use the job role from test data
        job_role = "AI & ML Engineer - C++ / Java Developer"
        response = self.session.get(f"{BASE_URL}/api/role", params={
            "jobRole": job_role,
            "page": 1
        })
        assert response.status_code == 200, f"Role endpoint failed: {response.text}"
        data = response.json()
        
        # Verify response structure
        assert "data" in data, "Missing data field"
        assert "total" in data, "Missing total field"
        assert "page" in data, "Missing page field"
        assert "columns" in data, "Missing columns field"
        
        # Verify columns include status (no score columns per requirements)
        expected_cols = ["name", "email", "phone", "gender", "date_of_birth", "date_of_application", "status"]
        assert data["columns"] == expected_cols, f"Columns mismatch: {data['columns']}"
        
        if len(data["data"]) > 0:
            applicant = data["data"][0]
            assert "status" in applicant, "Missing status field in applicant"
            print(f"✓ Role endpoint: {data['total']} applicants. First: {applicant['name']}, status={applicant['status']}")
        else:
            print(f"✓ Role endpoint: 0 applicants for role '{job_role}'")
    
    def test_role_search_filter(self):
        """Test search functionality on /api/role"""
        job_role = "AI & ML Engineer - C++ / Java Developer"
        response = self.session.get(f"{BASE_URL}/api/role", params={
            "jobRole": job_role,
            "page": 1,
            "search": "Rishi"  # Search by name
        })
        assert response.status_code == 200, f"Search failed: {response.text}"
        data = response.json()
        
        # If search returns results, verify they match
        if data["total"] > 0:
            for applicant in data["data"]:
                name_match = "rishi" in applicant.get("name", "").lower()
                email_match = "rishi" in applicant.get("email", "").lower()
                phone_match = "rishi" in applicant.get("phone", "").lower()
                assert name_match or email_match or phone_match, f"Search result doesn't match: {applicant}"
            print(f"✓ Search filter: Found {data['total']} results for 'Rishi'")
        else:
            print("✓ Search filter: No results (expected if no matching data)")
    
    def test_role_date_filter(self):
        """Test date filtering on /api/role"""
        job_role = "AI & ML Engineer - C++ / Java Developer"
        response = self.session.get(f"{BASE_URL}/api/role", params={
            "jobRole": job_role,
            "page": 1,
            "startDate": "2026-03-24",
            "endDate": "2026-03-26"
        })
        assert response.status_code == 200, f"Date filter failed: {response.text}"
        data = response.json()
        print(f"✓ Date filter: {data['total']} applicants between 2026-03-24 and 2026-03-26")


class TestAttendedRolesEndpoint:
    """Test /api/attended-roles endpoint"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        self.session = requests.Session()
        login_resp = self.session.post(f"{BASE_URL}/api/login", json={
            "username": "admin",
            "password": "admin"
        })
        assert login_resp.status_code == 200
    
    def test_attended_roles_returns_list(self):
        """GET /api/attended-roles returns job roles with attended counts"""
        response = self.session.get(f"{BASE_URL}/api/attended-roles")
        assert response.status_code == 200, f"Attended roles failed: {response.text}"
        data = response.json()
        
        assert "job_roles" in data, "Missing job_roles field"
        assert isinstance(data["job_roles"], list)
        
        # Per context: currently 0 attended applicants, so list should be empty
        if len(data["job_roles"]) == 0:
            print("✓ Attended roles: Empty list (no attended applicants - expected)")
        else:
            role = data["job_roles"][0]
            assert "job_role" in role, "Missing job_role"
            assert "count" in role, "Missing count"
            print(f"✓ Attended roles: {len(data['job_roles'])} roles. First: {role}")


class TestAttendedEndpoint:
    """Test /api/attended endpoint - attended applicants with scores"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        self.session = requests.Session()
        login_resp = self.session.post(f"{BASE_URL}/api/login", json={
            "username": "admin",
            "password": "admin"
        })
        assert login_resp.status_code == 200
    
    def test_attended_requires_job_role(self):
        """GET /api/attended without jobRole should fail or return empty"""
        response = self.session.get(f"{BASE_URL}/api/attended")
        # FastAPI will return 422 for missing required query param
        assert response.status_code == 422, f"Expected 422 for missing jobRole, got {response.status_code}"
        print("✓ Attended endpoint correctly requires jobRole parameter")
    
    def test_attended_with_job_role(self):
        """GET /api/attended?jobRole=... returns attended applicants with score columns"""
        job_role = "AI & ML Engineer - C++ / Java Developer"
        response = self.session.get(f"{BASE_URL}/api/attended", params={
            "jobRole": job_role,
            "page": 1
        })
        assert response.status_code == 200, f"Attended endpoint failed: {response.text}"
        data = response.json()
        
        # Verify response structure
        assert "data" in data, "Missing data field"
        assert "total" in data, "Missing total field"
        assert "page" in data, "Missing page field"
        assert "columns" in data, "Missing columns field"
        
        # Verify score columns are present
        score_cols = ["ZA", "C++", "Java", "BA", "LA", "Mensa Org", "Accounts2", "Accounts1", "BE", "Mensa", "BP"]
        for col in score_cols:
            assert col in data["columns"], f"Missing score column: {col}"
        assert "Total Score" in data["columns"], "Missing Total Score column"
        
        # Per context: 0 attended applicants expected
        if data["total"] == 0:
            print("✓ Attended endpoint: 0 attended applicants (expected - no otp_verified)")
        else:
            print(f"✓ Attended endpoint: {data['total']} attended applicants")
    
    def test_attended_search_filter(self):
        """Test search functionality on /api/attended"""
        job_role = "AI & ML Engineer - C++ / Java Developer"
        response = self.session.get(f"{BASE_URL}/api/attended", params={
            "jobRole": job_role,
            "page": 1,
            "search": "test"
        })
        assert response.status_code == 200, f"Search failed: {response.text}"
        print(f"✓ Attended search filter works: {response.json()['total']} results")
    
    def test_attended_round_filter(self):
        """Test round filtering on /api/attended"""
        job_role = "AI & ML Engineer - C++ / Java Developer"
        response = self.session.get(f"{BASE_URL}/api/attended", params={
            "jobRole": job_role,
            "page": 1,
            "round": "ZA"
        })
        assert response.status_code == 200, f"Round filter failed: {response.text}"
        print(f"✓ Attended round filter works: {response.json()['total']} results for round 'ZA'")


class TestPagination:
    """Test pagination on endpoints"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        self.session = requests.Session()
        login_resp = self.session.post(f"{BASE_URL}/api/login", json={
            "username": "admin",
            "password": "admin"
        })
        assert login_resp.status_code == 200
    
    def test_role_pagination(self):
        """Test pagination on /api/role"""
        job_role = "AI & ML Engineer - C++ / Java Developer"
        
        # Page 1
        resp1 = self.session.get(f"{BASE_URL}/api/role", params={
            "jobRole": job_role,
            "page": 1,
            "limit": 2
        })
        assert resp1.status_code == 200
        data1 = resp1.json()
        
        assert data1["page"] == 1
        assert data1["limit"] == 2
        
        # If more than 2 records, test page 2
        if data1["total"] > 2:
            resp2 = self.session.get(f"{BASE_URL}/api/role", params={
                "jobRole": job_role,
                "page": 2,
                "limit": 2
            })
            assert resp2.status_code == 200
            data2 = resp2.json()
            assert data2["page"] == 2
            print(f"✓ Pagination: Page 1 has {len(data1['data'])} items, Page 2 has {len(data2['data'])} items")
        else:
            print(f"✓ Pagination: Only {data1['total']} records, single page")


class TestAuthRequired:
    """Test that endpoints require authentication"""
    
    def test_status_requires_auth(self):
        """GET /api/status without auth should fail"""
        response = requests.get(f"{BASE_URL}/api/status")
        assert response.status_code == 401, f"Expected 401, got {response.status_code}"
        print("✓ /api/status correctly requires authentication")
    
    def test_job_roles_requires_auth(self):
        """GET /api/job-roles without auth should fail"""
        response = requests.get(f"{BASE_URL}/api/job-roles")
        assert response.status_code == 401
        print("✓ /api/job-roles correctly requires authentication")
    
    def test_attended_roles_requires_auth(self):
        """GET /api/attended-roles without auth should fail"""
        response = requests.get(f"{BASE_URL}/api/attended-roles")
        assert response.status_code == 401
        print("✓ /api/attended-roles correctly requires authentication")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
