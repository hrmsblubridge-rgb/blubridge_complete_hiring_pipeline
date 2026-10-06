"""
Test suite for new frontend structure APIs:
- /api/summary - Role-wise funnel statistics with filters
- /api/job-roles - Unique job roles with counts
- /api/role/{job_role} - Single role analytics
- Login and authentication
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

class TestHealthAndAuth:
    """Health check and authentication tests"""
    
    def test_api_health(self):
        """API health check returns healthy status"""
        response = requests.get(f"{BASE_URL}/api/")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert data["version"] == "4.0"
        print("✓ API health check passed")
    
    def test_login_success(self):
        """Login with admin/admin returns 200 and sets cookie"""
        session = requests.Session()
        response = session.post(f"{BASE_URL}/api/login", json={
            "username": "admin",
            "password": "admin"
        })
        assert response.status_code == 200
        data = response.json()
        assert data["success"] == True
        assert data["username"] == "admin"
        assert "access_token" in session.cookies
        print("✓ Login with admin/admin successful")
    
    def test_login_invalid_credentials(self):
        """Login with invalid credentials returns 401"""
        response = requests.post(f"{BASE_URL}/api/login", json={
            "username": "wrong",
            "password": "wrong"
        })
        assert response.status_code == 401
        print("✓ Invalid credentials returns 401")
    
    def test_endpoints_require_auth(self):
        """Protected endpoints return 401 without auth"""
        endpoints = ["/api/summary", "/api/job-roles", "/api/role/Software%20Engineer"]
        for endpoint in endpoints:
            response = requests.get(f"{BASE_URL}{endpoint}")
            assert response.status_code == 401, f"{endpoint} should require auth"
        print("✓ All endpoints require authentication")


class TestSummaryEndpoint:
    """Tests for /api/summary endpoint"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup authenticated session"""
        self.session = requests.Session()
        self.session.post(f"{BASE_URL}/api/login", json={
            "username": "admin",
            "password": "admin"
        })
    
    def test_summary_returns_data(self):
        """GET /api/summary returns role-wise funnel stats"""
        response = self.session.get(f"{BASE_URL}/api/summary")
        assert response.status_code == 200
        data = response.json()
        assert "data" in data
        assert "total_registered" in data
        assert isinstance(data["data"], list)
        print(f"✓ Summary returns {len(data['data'])} roles, total_registered={data['total_registered']}")
    
    def test_summary_has_7_roles(self):
        """GET /api/summary returns 7 unique job roles"""
        response = self.session.get(f"{BASE_URL}/api/summary")
        assert response.status_code == 200
        data = response.json()
        assert len(data["data"]) == 7, f"Expected 7 roles, got {len(data['data'])}"
        print(f"✓ Summary has 7 roles: {[r['job_role'] for r in data['data']]}")
    
    def test_summary_total_registered_is_7(self):
        """GET /api/summary total_registered equals 7"""
        response = self.session.get(f"{BASE_URL}/api/summary")
        assert response.status_code == 200
        data = response.json()
        assert data["total_registered"] == 7, f"Expected total_registered=7, got {data['total_registered']}"
        print("✓ total_registered = 7")
    
    def test_summary_row_structure(self):
        """Each row has all required funnel columns"""
        response = self.session.get(f"{BASE_URL}/api/summary")
        assert response.status_code == 200
        data = response.json()
        required_keys = ["job_role", "total_applicants", "shortlisted", "rejected", 
                        "scheduled", "not_scheduled", "attended", "not_attended"]
        for row in data["data"]:
            for key in required_keys:
                assert key in row, f"Missing key '{key}' in row"
        print("✓ All rows have required funnel columns")
    
    def test_summary_totals_match_expected(self):
        """Summary totals match expected values (7, 6, 2, 5, 2, 3, 4)"""
        response = self.session.get(f"{BASE_URL}/api/summary")
        assert response.status_code == 200
        data = response.json()
        
        totals = {
            "total_applicants": sum(r["total_applicants"] for r in data["data"]),
            "shortlisted": sum(r["shortlisted"] for r in data["data"]),
            "rejected": sum(r["rejected"] for r in data["data"]),
            "scheduled": sum(r["scheduled"] for r in data["data"]),
            "not_scheduled": sum(r["not_scheduled"] for r in data["data"]),
            "attended": sum(r["attended"] for r in data["data"]),
            "not_attended": sum(r["not_attended"] for r in data["data"]),
        }
        
        expected = {
            "total_applicants": 7,
            "shortlisted": 6,
            "rejected": 2,
            "scheduled": 5,
            "not_scheduled": 2,
            "attended": 3,
            "not_attended": 4,
        }
        
        for key, expected_val in expected.items():
            assert totals[key] == expected_val, f"Expected {key}={expected_val}, got {totals[key]}"
        
        print(f"✓ Totals match: total={totals['total_applicants']}, shortlisted={totals['shortlisted']}, rejected={totals['rejected']}, scheduled={totals['scheduled']}, not_scheduled={totals['not_scheduled']}, attended={totals['attended']}, not_attended={totals['not_attended']}")
    
    def test_summary_date_filter(self):
        """GET /api/summary with date filter returns filtered results"""
        response = self.session.get(f"{BASE_URL}/api/summary", params={
            "startDate": "2026-01-17",
            "endDate": "2026-01-20"
        })
        assert response.status_code == 200
        data = response.json()
        # Date filter should return subset of data
        assert isinstance(data["data"], list)
        print(f"✓ Date filter (2026-01-17 to 2026-01-20) returns {len(data['data'])} roles")
    
    def test_summary_search_filter_engineer(self):
        """GET /api/summary with search=Engineer returns 3 roles"""
        response = self.session.get(f"{BASE_URL}/api/summary", params={
            "search": "Engineer"
        })
        assert response.status_code == 200
        data = response.json()
        assert len(data["data"]) == 3, f"Expected 3 roles with 'Engineer', got {len(data['data'])}"
        role_names = [r["job_role"] for r in data["data"]]
        print(f"✓ Search 'Engineer' returns 3 roles: {role_names}")


class TestJobRolesEndpoint:
    """Tests for /api/job-roles endpoint"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup authenticated session"""
        self.session = requests.Session()
        self.session.post(f"{BASE_URL}/api/login", json={
            "username": "admin",
            "password": "admin"
        })
    
    def test_job_roles_returns_data(self):
        """GET /api/job-roles returns job roles with counts"""
        response = self.session.get(f"{BASE_URL}/api/job-roles")
        assert response.status_code == 200
        data = response.json()
        assert "job_roles" in data
        assert isinstance(data["job_roles"], list)
        print(f"✓ Job roles endpoint returns {len(data['job_roles'])} roles")
    
    def test_job_roles_has_7_roles(self):
        """GET /api/job-roles returns 7 unique job roles"""
        response = self.session.get(f"{BASE_URL}/api/job-roles")
        assert response.status_code == 200
        data = response.json()
        assert len(data["job_roles"]) == 7, f"Expected 7 roles, got {len(data['job_roles'])}"
        print(f"✓ Job roles has 7 unique roles")
    
    def test_job_roles_structure(self):
        """Each job role has job_role and count fields"""
        response = self.session.get(f"{BASE_URL}/api/job-roles")
        assert response.status_code == 200
        data = response.json()
        for role in data["job_roles"]:
            assert "job_role" in role, "Missing 'job_role' field"
            assert "count" in role, "Missing 'count' field"
            assert isinstance(role["count"], int), "count should be integer"
        print("✓ All roles have job_role and count fields")
    
    def test_job_roles_total_count_is_7(self):
        """Total count across all roles equals 7"""
        response = self.session.get(f"{BASE_URL}/api/job-roles")
        assert response.status_code == 200
        data = response.json()
        total = sum(r["count"] for r in data["job_roles"])
        assert total == 7, f"Expected total count=7, got {total}"
        print(f"✓ Total count across roles = 7")


class TestRoleAnalyticsEndpoint:
    """Tests for /api/role/{job_role} endpoint"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup authenticated session"""
        self.session = requests.Session()
        self.session.post(f"{BASE_URL}/api/login", json={
            "username": "admin",
            "password": "admin"
        })
    
    def test_role_analytics_software_engineer(self):
        """GET /api/role/Software%20Engineer returns single role stats"""
        response = self.session.get(f"{BASE_URL}/api/role/Software%20Engineer")
        assert response.status_code == 200
        data = response.json()
        assert "data" in data
        assert "total_registered" in data
        assert len(data["data"]) == 1, f"Expected 1 role, got {len(data['data'])}"
        assert data["data"][0]["job_role"] == "Software Engineer"
        print(f"✓ Software Engineer role analytics: {data['data'][0]}")
    
    def test_role_analytics_has_funnel_columns(self):
        """Role analytics has all funnel columns"""
        response = self.session.get(f"{BASE_URL}/api/role/Software%20Engineer")
        assert response.status_code == 200
        data = response.json()
        required_keys = ["job_role", "total_applicants", "shortlisted", "rejected", 
                        "scheduled", "not_scheduled", "attended", "not_attended"]
        for key in required_keys:
            assert key in data["data"][0], f"Missing key '{key}'"
        print("✓ Role analytics has all funnel columns")
    
    def test_role_analytics_with_date_filter(self):
        """GET /api/role/{role} with date filter works"""
        response = self.session.get(f"{BASE_URL}/api/role/Software%20Engineer", params={
            "startDate": "2026-01-01",
            "endDate": "2026-12-31"
        })
        assert response.status_code == 200
        data = response.json()
        assert "data" in data
        print(f"✓ Role analytics with date filter works")
    
    def test_role_analytics_nonexistent_role(self):
        """GET /api/role/{nonexistent} returns empty data"""
        response = self.session.get(f"{BASE_URL}/api/role/NonExistentRole123")
        assert response.status_code == 200
        data = response.json()
        assert data["data"] == []
        assert data["total_registered"] == 0
        print("✓ Nonexistent role returns empty data")


class TestUploadEndpoints:
    """Tests for upload endpoints"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup authenticated session"""
        self.session = requests.Session()
        self.session.post(f"{BASE_URL}/api/login", json={
            "username": "admin",
            "password": "admin"
        })
    
    def test_upload_naukri_csv(self):
        """Upload Naukri CSV via /api/upload/naukri"""
        with open("/app/test_data/naukri_test.csv", "rb") as f:
            response = self.session.post(
                f"{BASE_URL}/api/upload/naukri",
                files={"file": ("naukri_test.csv", f, "text/csv")}
            )
        assert response.status_code == 200
        data = response.json()
        assert data["success"] == True
        assert "inserted" in data
        assert "updated" in data
        assert "mapped_columns" in data
        print(f"✓ Naukri upload: inserted={data['inserted']}, updated={data['updated']}, mapped={data['mapped_columns']}")
    
    def test_upload_pipeline_csv(self):
        """Upload Pipeline CSV via /api/upload/pipeline"""
        with open("/app/test_data/pipeline_test.csv", "rb") as f:
            response = self.session.post(
                f"{BASE_URL}/api/upload/pipeline",
                files={"file": ("pipeline_test.csv", f, "text/csv")}
            )
        assert response.status_code == 200
        data = response.json()
        assert data["success"] == True
        assert "inserted" in data
        assert "updated" in data
        assert "mapped_columns" in data
        print(f"✓ Pipeline upload: inserted={data['inserted']}, updated={data['updated']}, mapped={data['mapped_columns']}")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
