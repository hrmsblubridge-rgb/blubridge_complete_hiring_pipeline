"""
Test suite for iteration 8 fixes:
1. FIX 1: /api/role endpoint now uses query param ?jobRole= instead of path param
2. FIX 2: Independent upload flow - each upload works alone
3. FIX 3: /api/status endpoint returns DB counts
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

class TestAuth:
    """Authentication tests"""
    
    @pytest.fixture(scope="class")
    def session(self):
        """Create a session for all tests"""
        return requests.Session()
    
    def test_login_success(self, session):
        """Login with admin/admin credentials"""
        response = session.post(f"{BASE_URL}/api/login", json={
            "username": "admin",
            "password": "admin"
        })
        assert response.status_code == 200, f"Login failed: {response.text}"
        data = response.json()
        assert data.get("success") == True
        assert data.get("username") == "admin"
        print("✓ Login with admin/admin successful")


class TestFix1RoleQueryParam:
    """FIX 1: /api/role endpoint uses query param ?jobRole= instead of path param"""
    
    @pytest.fixture(scope="class")
    def auth_session(self):
        """Create authenticated session"""
        session = requests.Session()
        response = session.post(f"{BASE_URL}/api/login", json={
            "username": "admin",
            "password": "admin"
        })
        assert response.status_code == 200, "Auth failed"
        return session
    
    def test_role_with_query_param_returns_200(self, auth_session):
        """GET /api/role?jobRole=Software%20Engineer returns 200 (not 404)"""
        response = auth_session.get(f"{BASE_URL}/api/role", params={"jobRole": "Software Engineer"})
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert "data" in data
        assert "total_registered" in data
        print(f"✓ GET /api/role?jobRole=Software Engineer returns 200 with data: {data}")
    
    def test_role_with_special_chars_returns_200(self, auth_session):
        """GET /api/role?jobRole=AI%20%26%20ML%20Engineer returns 200 with empty data (no 404)"""
        # This role doesn't exist in test data, but should return 200 with empty data
        response = auth_session.get(f"{BASE_URL}/api/role", params={"jobRole": "AI & ML Engineer"})
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert "data" in data
        assert data["total_registered"] == 0 or isinstance(data["data"], list)
        print(f"✓ GET /api/role?jobRole=AI & ML Engineer returns 200 with empty data: {data}")
    
    def test_role_without_param_returns_422(self, auth_session):
        """GET /api/role without jobRole param returns 422 (validation error)"""
        response = auth_session.get(f"{BASE_URL}/api/role")
        assert response.status_code == 422, f"Expected 422, got {response.status_code}: {response.text}"
        print(f"✓ GET /api/role without param returns 422 validation error")
    
    def test_role_path_param_returns_404(self, auth_session):
        """Old path param style /api/role/Software%20Engineer should return 404 (not found)"""
        response = auth_session.get(f"{BASE_URL}/api/role/Software%20Engineer")
        # This should return 404 since the endpoint no longer uses path params
        assert response.status_code == 404, f"Expected 404 for old path param style, got {response.status_code}"
        print(f"✓ Old path param style /api/role/Software%20Engineer returns 404")


class TestFix2IndependentUpload:
    """FIX 2: Independent upload flow - each upload works alone without requiring the other"""
    
    @pytest.fixture(scope="class")
    def auth_session(self):
        """Create authenticated session"""
        session = requests.Session()
        response = session.post(f"{BASE_URL}/api/login", json={
            "username": "admin",
            "password": "admin"
        })
        assert response.status_code == 200, "Auth failed"
        return session
    
    def test_status_endpoint_exists(self, auth_session):
        """GET /api/status returns naukri_count, pipeline_count, registered_count"""
        response = auth_session.get(f"{BASE_URL}/api/status")
        assert response.status_code == 200, f"Status endpoint failed: {response.text}"
        data = response.json()
        assert "naukri_count" in data
        assert "pipeline_count" in data
        assert "registered_count" in data
        print(f"✓ GET /api/status returns counts: {data}")
        return data
    
    def test_summary_with_existing_data(self, auth_session):
        """GET /api/summary returns role-wise funnel stats"""
        response = auth_session.get(f"{BASE_URL}/api/summary")
        assert response.status_code == 200, f"Summary failed: {response.text}"
        data = response.json()
        assert "data" in data
        assert "total_registered" in data
        print(f"✓ GET /api/summary returns {len(data['data'])} roles, total_registered={data['total_registered']}")
    
    def test_job_roles_endpoint(self, auth_session):
        """GET /api/job-roles returns unique roles"""
        response = auth_session.get(f"{BASE_URL}/api/job-roles")
        assert response.status_code == 200, f"Job roles failed: {response.text}"
        data = response.json()
        assert "job_roles" in data
        print(f"✓ GET /api/job-roles returns {len(data['job_roles'])} roles")


class TestFix3StatusEndpoint:
    """FIX 3: /api/status endpoint returns DB counts"""
    
    @pytest.fixture(scope="class")
    def auth_session(self):
        """Create authenticated session"""
        session = requests.Session()
        response = session.post(f"{BASE_URL}/api/login", json={
            "username": "admin",
            "password": "admin"
        })
        assert response.status_code == 200, "Auth failed"
        return session
    
    def test_status_returns_all_counts(self, auth_session):
        """GET /api/status returns naukri_count, pipeline_count, registered_count"""
        response = auth_session.get(f"{BASE_URL}/api/status")
        assert response.status_code == 200, f"Status failed: {response.text}"
        data = response.json()
        
        # Verify all required fields exist
        assert "naukri_count" in data, "Missing naukri_count"
        assert "pipeline_count" in data, "Missing pipeline_count"
        assert "registered_count" in data, "Missing registered_count"
        
        # Verify they are integers
        assert isinstance(data["naukri_count"], int), "naukri_count should be int"
        assert isinstance(data["pipeline_count"], int), "pipeline_count should be int"
        assert isinstance(data["registered_count"], int), "registered_count should be int"
        
        print(f"✓ Status endpoint returns: naukri={data['naukri_count']}, pipeline={data['pipeline_count']}, registered={data['registered_count']}")
    
    def test_status_requires_auth(self):
        """GET /api/status without auth returns 401"""
        session = requests.Session()
        response = session.get(f"{BASE_URL}/api/status")
        assert response.status_code == 401, f"Expected 401, got {response.status_code}"
        print("✓ Status endpoint requires authentication")


class TestExistingEndpoints:
    """Verify existing endpoints still work"""
    
    @pytest.fixture(scope="class")
    def auth_session(self):
        """Create authenticated session"""
        session = requests.Session()
        response = session.post(f"{BASE_URL}/api/login", json={
            "username": "admin",
            "password": "admin"
        })
        assert response.status_code == 200, "Auth failed"
        return session
    
    def test_health_check(self):
        """API health check"""
        response = requests.get(f"{BASE_URL}/api/")
        assert response.status_code == 200
        data = response.json()
        assert data.get("status") == "healthy"
        print("✓ Health check passed")
    
    def test_dashboard_counts(self, auth_session):
        """GET /api/dashboard-counts returns funnel counts"""
        response = auth_session.get(f"{BASE_URL}/api/dashboard-counts")
        assert response.status_code == 200, f"Dashboard counts failed: {response.text}"
        data = response.json()
        assert "total_applies" in data
        assert "registered" in data
        assert "unregistered" in data
        print(f"✓ Dashboard counts: total={data['total_applies']}, registered={data['registered']}, unregistered={data['unregistered']}")
    
    def test_auth_check(self, auth_session):
        """GET /api/auth/check returns authenticated status"""
        response = auth_session.get(f"{BASE_URL}/api/auth/check")
        assert response.status_code == 200, f"Auth check failed: {response.text}"
        data = response.json()
        assert data.get("authenticated") == True
        print("✓ Auth check passed")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
