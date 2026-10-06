"""
Iteration 19: Job Role Normalization via Keywords Mapping System
Tests for:
- CRUD API for job-keyword-mappings
- Job role normalization in /api/job-roles, /api/summary, /api/applicants, /api/attended
- Filtering by normalized job role
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

class TestJobKeywordMappingsCRUD:
    """Test CRUD operations for job-keyword-mappings endpoint"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Login and get session for authenticated requests"""
        self.session = requests.Session()
        login_resp = self.session.post(f"{BASE_URL}/api/login", json={
            "username": "admin",
            "password": "admin"
        })
        assert login_resp.status_code == 200, f"Login failed: {login_resp.text}"
        yield
        # Cleanup: delete any test mappings created
        try:
            mappings_resp = self.session.get(f"{BASE_URL}/api/job-keyword-mappings")
            if mappings_resp.status_code == 200:
                for m in mappings_resp.json().get("mappings", []):
                    if m.get("job_role", "").startswith("TEST_"):
                        self.session.delete(f"{BASE_URL}/api/job-keyword-mappings/{m['id']}")
        except:
            pass
    
    def test_list_mappings_returns_200(self):
        """GET /api/job-keyword-mappings returns 200 with mappings array"""
        resp = self.session.get(f"{BASE_URL}/api/job-keyword-mappings")
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()
        assert "mappings" in data, "Response should have 'mappings' key"
        assert isinstance(data["mappings"], list), "mappings should be a list"
    
    def test_list_mappings_requires_auth(self):
        """GET /api/job-keyword-mappings requires authentication"""
        resp = requests.get(f"{BASE_URL}/api/job-keyword-mappings")
        assert resp.status_code == 401, f"Expected 401 without auth, got {resp.status_code}"
    
    def test_create_mapping_success(self):
        """POST /api/job-keyword-mappings creates a new mapping"""
        payload = {
            "job_role": "TEST_AI Engineer",
            "keywords": ["ai", "machine learning", "ml"]
        }
        resp = self.session.post(f"{BASE_URL}/api/job-keyword-mappings", json=payload)
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()
        assert data.get("success") == True, "Response should have success=True"
        assert "id" in data, "Response should have 'id' field"
        assert data.get("job_role") == "TEST_AI Engineer"
        assert data.get("keywords") == ["ai", "machine learning", "ml"]
        
        # Verify it appears in list
        list_resp = self.session.get(f"{BASE_URL}/api/job-keyword-mappings")
        mappings = list_resp.json().get("mappings", [])
        found = any(m.get("id") == data["id"] for m in mappings)
        assert found, "Created mapping should appear in list"
    
    def test_create_mapping_requires_auth(self):
        """POST /api/job-keyword-mappings requires authentication"""
        resp = requests.post(f"{BASE_URL}/api/job-keyword-mappings", json={
            "job_role": "Test Role",
            "keywords": ["test"]
        })
        assert resp.status_code == 401, f"Expected 401 without auth, got {resp.status_code}"
    
    def test_update_mapping_success(self):
        """PUT /api/job-keyword-mappings/{id} updates an existing mapping"""
        # First create a mapping
        create_resp = self.session.post(f"{BASE_URL}/api/job-keyword-mappings", json={
            "job_role": "TEST_Update Role",
            "keywords": ["original"]
        })
        assert create_resp.status_code == 200
        mapping_id = create_resp.json()["id"]
        
        # Update it
        update_resp = self.session.put(f"{BASE_URL}/api/job-keyword-mappings/{mapping_id}", json={
            "job_role": "TEST_Updated Role",
            "keywords": ["updated", "new keyword"]
        })
        assert update_resp.status_code == 200, f"Expected 200, got {update_resp.status_code}: {update_resp.text}"
        assert update_resp.json().get("success") == True
        
        # Verify update persisted
        list_resp = self.session.get(f"{BASE_URL}/api/job-keyword-mappings")
        mappings = list_resp.json().get("mappings", [])
        updated = next((m for m in mappings if m.get("id") == mapping_id), None)
        assert updated is not None, "Updated mapping should exist"
        assert updated.get("job_role") == "TEST_Updated Role"
        assert updated.get("keywords") == ["updated", "new keyword"]
    
    def test_update_mapping_not_found(self):
        """PUT /api/job-keyword-mappings/{id} returns 404 for non-existent mapping"""
        resp = self.session.put(f"{BASE_URL}/api/job-keyword-mappings/000000000000000000000000", json={
            "job_role": "Test"
        })
        assert resp.status_code == 404, f"Expected 404, got {resp.status_code}"
    
    def test_update_mapping_invalid_id(self):
        """PUT /api/job-keyword-mappings/{id} returns 400 for invalid ID format"""
        resp = self.session.put(f"{BASE_URL}/api/job-keyword-mappings/invalid-id", json={
            "job_role": "Test"
        })
        assert resp.status_code == 400, f"Expected 400, got {resp.status_code}"
    
    def test_delete_mapping_success(self):
        """DELETE /api/job-keyword-mappings/{id} deletes a mapping"""
        # First create a mapping
        create_resp = self.session.post(f"{BASE_URL}/api/job-keyword-mappings", json={
            "job_role": "TEST_Delete Role",
            "keywords": ["delete"]
        })
        assert create_resp.status_code == 200
        mapping_id = create_resp.json()["id"]
        
        # Delete it
        delete_resp = self.session.delete(f"{BASE_URL}/api/job-keyword-mappings/{mapping_id}")
        assert delete_resp.status_code == 200, f"Expected 200, got {delete_resp.status_code}: {delete_resp.text}"
        assert delete_resp.json().get("success") == True
        
        # Verify it's gone
        list_resp = self.session.get(f"{BASE_URL}/api/job-keyword-mappings")
        mappings = list_resp.json().get("mappings", [])
        found = any(m.get("id") == mapping_id for m in mappings)
        assert not found, "Deleted mapping should not appear in list"
    
    def test_delete_mapping_not_found(self):
        """DELETE /api/job-keyword-mappings/{id} returns 404 for non-existent mapping"""
        resp = self.session.delete(f"{BASE_URL}/api/job-keyword-mappings/000000000000000000000000")
        assert resp.status_code == 404, f"Expected 404, got {resp.status_code}"
    
    def test_delete_mapping_requires_auth(self):
        """DELETE /api/job-keyword-mappings/{id} requires authentication"""
        resp = requests.delete(f"{BASE_URL}/api/job-keyword-mappings/000000000000000000000000")
        assert resp.status_code == 401, f"Expected 401 without auth, got {resp.status_code}"


class TestJobRoleNormalization:
    """Test job role normalization in various endpoints"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Login and get session for authenticated requests"""
        self.session = requests.Session()
        login_resp = self.session.post(f"{BASE_URL}/api/login", json={
            "username": "admin",
            "password": "admin"
        })
        assert login_resp.status_code == 200, f"Login failed: {login_resp.text}"
        yield
    
    def test_job_roles_endpoint_returns_normalized_roles(self):
        """GET /api/job-roles returns normalized role names when mappings exist"""
        resp = self.session.get(f"{BASE_URL}/api/job-roles")
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()
        assert "job_roles" in data, "Response should have 'job_roles' key"
        # Each role should have job_role and count
        for role in data["job_roles"]:
            assert "job_role" in role, "Each role should have 'job_role' field"
            assert "count" in role, "Each role should have 'count' field"
    
    def test_summary_endpoint_returns_normalized_roles(self):
        """GET /api/summary groups by normalized job role"""
        resp = self.session.get(f"{BASE_URL}/api/summary")
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()
        assert "data" in data, "Response should have 'data' key"
        # Each row should have job_role field
        for row in data["data"]:
            assert "job_role" in row, "Each row should have 'job_role' field"
    
    def test_applicants_endpoint_returns_normalized_job_role(self):
        """GET /api/applicants shows normalized job_role in response"""
        resp = self.session.get(f"{BASE_URL}/api/applicants")
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()
        assert "data" in data, "Response should have 'data' key"
        # Each applicant should have job_role field
        for applicant in data["data"]:
            assert "job_role" in applicant, "Each applicant should have 'job_role' field"
    
    def test_attended_endpoint_returns_normalized_job_role(self):
        """GET /api/attended shows normalized job_role in response"""
        resp = self.session.get(f"{BASE_URL}/api/attended")
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()
        assert "data" in data, "Response should have 'data' key"
        # Each attended applicant should have job_role field
        for applicant in data["data"]:
            assert "job_role" in applicant, "Each applicant should have 'job_role' field"
    
    def test_applicants_filter_by_normalized_job_role(self):
        """GET /api/applicants?jobRole=X filters by normalized job role"""
        # First get list of job roles
        roles_resp = self.session.get(f"{BASE_URL}/api/job-roles")
        if roles_resp.status_code == 200 and roles_resp.json().get("job_roles"):
            first_role = roles_resp.json()["job_roles"][0]["job_role"]
            # Filter by that role
            filter_resp = self.session.get(f"{BASE_URL}/api/applicants", params={"jobRole": first_role})
            assert filter_resp.status_code == 200, f"Expected 200, got {filter_resp.status_code}"
            # All returned applicants should have that job_role
            for applicant in filter_resp.json().get("data", []):
                assert applicant.get("job_role") == first_role, f"Expected job_role={first_role}, got {applicant.get('job_role')}"
        else:
            pytest.skip("No job roles available to test filtering")
    
    def test_attended_filter_by_normalized_job_role(self):
        """GET /api/attended?jobRole=X filters by normalized job role"""
        # First get list of job roles
        roles_resp = self.session.get(f"{BASE_URL}/api/job-roles")
        if roles_resp.status_code == 200 and roles_resp.json().get("job_roles"):
            first_role = roles_resp.json()["job_roles"][0]["job_role"]
            # Filter by that role
            filter_resp = self.session.get(f"{BASE_URL}/api/attended", params={"jobRole": first_role})
            assert filter_resp.status_code == 200, f"Expected 200, got {filter_resp.status_code}"
            # All returned applicants should have that job_role
            for applicant in filter_resp.json().get("data", []):
                assert applicant.get("job_role") == first_role, f"Expected job_role={first_role}, got {applicant.get('job_role')}"
        else:
            pytest.skip("No job roles available to test filtering")


class TestEmptyStateTableHeaders:
    """Test that table headers remain visible even when tables are empty"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Login and get session for authenticated requests"""
        self.session = requests.Session()
        login_resp = self.session.post(f"{BASE_URL}/api/login", json={
            "username": "admin",
            "password": "admin"
        })
        assert login_resp.status_code == 200, f"Login failed: {login_resp.text}"
        yield
    
    def test_applicants_with_nonexistent_filter_returns_empty_data(self):
        """GET /api/applicants with non-matching filter returns empty data array (not error)"""
        resp = self.session.get(f"{BASE_URL}/api/applicants", params={"jobRole": "NONEXISTENT_ROLE_XYZ123"})
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()
        assert "data" in data, "Response should have 'data' key"
        assert isinstance(data["data"], list), "data should be a list"
        assert data.get("total") == 0 or len(data["data"]) == 0, "Should return empty data for non-matching filter"
    
    def test_attended_with_nonexistent_filter_returns_empty_data(self):
        """GET /api/attended with non-matching filter returns empty data array (not error)"""
        resp = self.session.get(f"{BASE_URL}/api/attended", params={"jobRole": "NONEXISTENT_ROLE_XYZ123"})
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()
        assert "data" in data, "Response should have 'data' key"
        assert isinstance(data["data"], list), "data should be a list"
    
    def test_summary_with_nonexistent_search_returns_empty_data(self):
        """GET /api/summary with non-matching search returns empty data array (not error)"""
        resp = self.session.get(f"{BASE_URL}/api/summary", params={"search": "NONEXISTENT_ROLE_XYZ123"})
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()
        assert "data" in data, "Response should have 'data' key"
        assert isinstance(data["data"], list), "data should be a list"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
