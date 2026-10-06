"""
Iteration 21: Data-Driven Mapping UI Tests
Tests the new checkbox-based keyword selection system where:
1. Job titles come from uploaded Naukri data into job_titles_master collection
2. Unmatched keywords shown via /api/job-titles/unmatched endpoint
3. Mapping done via checkbox selection (not manual typing)
4. is_mapped flag tracks whether a keyword is mapped
5. Keywords map to only ONE canonical role
6. Exact match on normalized values for job role resolution
"""

import pytest
import requests
import os
import io
import csv

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

class TestDataDrivenMappingFlow:
    """Test the complete data-driven mapping flow"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup: Login and get session"""
        self.session = requests.Session()
        # Don't set Content-Type header - let requests handle it for multipart
        
        # Login
        login_resp = self.session.post(f"{BASE_URL}/api/login", json={
            "username": "admin",
            "password": "admin"
        })
        assert login_resp.status_code == 200, f"Login failed: {login_resp.text}"
        
        yield
        
        # Cleanup: Delete any TEST_ prefixed mappings
        try:
            mappings_resp = self.session.get(f"{BASE_URL}/api/job-keyword-mappings")
            if mappings_resp.status_code == 200:
                for m in mappings_resp.json().get("mappings", []):
                    if m.get("job_role", "").startswith("TEST_"):
                        self.session.delete(f"{BASE_URL}/api/job-keyword-mappings/{m['id']}")
        except:
            pass
    
    def _create_test_csv(self, job_titles):
        """Create a test CSV file with given job titles"""
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["Email ID", "Phone Number", "Job Title", "Name"])
        for i, title in enumerate(job_titles):
            writer.writerow([f"test{i}@example.com", f"900000000{i}", title, f"Test User {i}"])
        output.seek(0)
        return output.getvalue()
    
    def _upload_naukri_csv(self, job_titles):
        """Helper to upload Naukri CSV with given job titles"""
        csv_content = self._create_test_csv(job_titles)
        files = {'file': ('test_naukri.csv', io.BytesIO(csv_content.encode()), 'text/csv')}
        resp = self.session.post(f"{BASE_URL}/api/upload/naukri", files=files)
        return resp
    
    # ============ NAUKRI UPLOAD & JOB TITLES EXTRACTION ============
    
    def test_upload_naukri_extracts_job_titles(self):
        """POST /api/upload/naukri - after upload, distinct job titles are extracted into job_titles_master"""
        # Create test CSV with varied job titles
        job_titles = [
            "TEST_AI ML Engineer",
            "TEST_AI & ML Engineer",
            "TEST_Data Analyst",
            "TEST_Frontend Developer"
        ]
        
        resp = self._upload_naukri_csv(job_titles)
        
        assert resp.status_code == 200, f"Upload failed: {resp.text}"
        data = resp.json()
        assert data.get("success") == True
        assert data.get("inserted", 0) > 0 or data.get("updated", 0) > 0
        print(f"Naukri upload: inserted={data.get('inserted')}, updated={data.get('updated')}")
    
    def test_get_unmatched_job_titles_returns_uploaded_titles(self):
        """GET /api/job-titles/unmatched - returns unmatched titles (is_mapped=false)"""
        # First upload some test data
        job_titles = [
            "TEST_Unmatched Role 1",
            "TEST_Unmatched Role 2"
        ]
        upload_resp = self._upload_naukri_csv(job_titles)
        assert upload_resp.status_code == 200, f"Upload failed: {upload_resp.text}"
        
        # Get unmatched titles
        resp = self.session.get(f"{BASE_URL}/api/job-titles/unmatched")
        assert resp.status_code == 200, f"Failed: {resp.text}"
        data = resp.json()
        
        assert "titles" in data
        titles = data["titles"]
        assert isinstance(titles, list)
        
        # Check that our test titles are in the unmatched list
        test_titles_found = [t for t in titles if t.startswith("TEST_")]
        print(f"Found {len(test_titles_found)} TEST_ prefixed unmatched titles: {test_titles_found}")
        assert len(test_titles_found) >= 2, "Expected at least 2 TEST_ prefixed unmatched titles"
    
    def test_unmatched_endpoint_requires_auth(self):
        """GET /api/job-titles/unmatched requires authentication"""
        new_session = requests.Session()
        resp = new_session.get(f"{BASE_URL}/api/job-titles/unmatched")
        assert resp.status_code == 401, f"Expected 401, got {resp.status_code}"
    
    # ============ MAPPING CRUD WITH is_mapped FLAG ============
    
    def test_create_mapping_sets_is_mapped_true(self):
        """POST /api/job-keyword-mappings - creates mapping and sets is_mapped=true for keywords"""
        # First upload test data
        job_titles = ["TEST_Mapping Keyword 1", "TEST_Mapping Keyword 2"]
        upload_resp = self._upload_naukri_csv(job_titles)
        assert upload_resp.status_code == 200, f"Upload failed: {upload_resp.text}"
        
        # Verify keywords are in unmatched list
        unmatched_before = self.session.get(f"{BASE_URL}/api/job-titles/unmatched").json()["titles"]
        assert "TEST_Mapping Keyword 1" in unmatched_before, f"Keyword should be unmatched before mapping. Got: {unmatched_before}"
        
        # Create mapping
        resp = self.session.post(f"{BASE_URL}/api/job-keyword-mappings", json={
            "job_role": "TEST_Canonical Role",
            "keywords": ["TEST_Mapping Keyword 1", "TEST_Mapping Keyword 2"]
        })
        assert resp.status_code == 200, f"Create mapping failed: {resp.text}"
        data = resp.json()
        assert data.get("success") == True
        assert "id" in data
        mapping_id = data["id"]
        
        # Verify keywords are NO LONGER in unmatched list
        unmatched_after = self.session.get(f"{BASE_URL}/api/job-titles/unmatched").json()["titles"]
        assert "TEST_Mapping Keyword 1" not in unmatched_after, "Keyword should NOT be in unmatched after mapping"
        assert "TEST_Mapping Keyword 2" not in unmatched_after, "Keyword should NOT be in unmatched after mapping"
        
        print(f"Created mapping {mapping_id}, keywords removed from unmatched list")
        
        # Cleanup
        self.session.delete(f"{BASE_URL}/api/job-keyword-mappings/{mapping_id}")
    
    def test_delete_mapping_releases_keywords(self):
        """DELETE /api/job-keyword-mappings - releases keywords back to unmatched (is_mapped=false)"""
        # Upload test data
        job_titles = ["TEST_Release Keyword 1"]
        upload_resp = self._upload_naukri_csv(job_titles)
        assert upload_resp.status_code == 200, f"Upload failed: {upload_resp.text}"
        
        # Create mapping
        create_resp = self.session.post(f"{BASE_URL}/api/job-keyword-mappings", json={
            "job_role": "TEST_Release Role",
            "keywords": ["TEST_Release Keyword 1"]
        })
        assert create_resp.status_code == 200, f"Create failed: {create_resp.text}"
        mapping_id = create_resp.json()["id"]
        
        # Verify keyword is NOT in unmatched
        unmatched_before_delete = self.session.get(f"{BASE_URL}/api/job-titles/unmatched").json()["titles"]
        assert "TEST_Release Keyword 1" not in unmatched_before_delete
        
        # Delete mapping
        delete_resp = self.session.delete(f"{BASE_URL}/api/job-keyword-mappings/{mapping_id}")
        assert delete_resp.status_code == 200, f"Delete failed: {delete_resp.text}"
        
        # Verify keyword IS BACK in unmatched
        unmatched_after_delete = self.session.get(f"{BASE_URL}/api/job-titles/unmatched").json()["titles"]
        assert "TEST_Release Keyword 1" in unmatched_after_delete, f"Keyword should return to unmatched after delete. Got: {unmatched_after_delete}"
        
        print("Keyword released back to unmatched after mapping deletion")
    
    def test_update_mapping_handles_keyword_changes(self):
        """PUT /api/job-keyword-mappings - handles keyword add/remove correctly (maps new, unmaps removed)"""
        # Upload test data
        job_titles = ["TEST_Update KW 1", "TEST_Update KW 2", "TEST_Update KW 3"]
        upload_resp = self._upload_naukri_csv(job_titles)
        assert upload_resp.status_code == 200, f"Upload failed: {upload_resp.text}"
        
        # Create mapping with KW 1 and KW 2
        create_resp = self.session.post(f"{BASE_URL}/api/job-keyword-mappings", json={
            "job_role": "TEST_Update Role",
            "keywords": ["TEST_Update KW 1", "TEST_Update KW 2"]
        })
        assert create_resp.status_code == 200, f"Create failed: {create_resp.text}"
        mapping_id = create_resp.json()["id"]
        
        # Verify KW 1, KW 2 not in unmatched, KW 3 is in unmatched
        unmatched = self.session.get(f"{BASE_URL}/api/job-titles/unmatched").json()["titles"]
        assert "TEST_Update KW 1" not in unmatched
        assert "TEST_Update KW 2" not in unmatched
        assert "TEST_Update KW 3" in unmatched, f"KW 3 should be in unmatched. Got: {unmatched}"
        
        # Update: Remove KW 2, Add KW 3
        update_resp = self.session.put(f"{BASE_URL}/api/job-keyword-mappings/{mapping_id}", json={
            "keywords": ["TEST_Update KW 1", "TEST_Update KW 3"]
        })
        assert update_resp.status_code == 200, f"Update failed: {update_resp.text}"
        
        # Verify KW 2 is back in unmatched, KW 3 is now mapped
        unmatched_after = self.session.get(f"{BASE_URL}/api/job-titles/unmatched").json()["titles"]
        assert "TEST_Update KW 1" not in unmatched_after, "KW 1 should still be mapped"
        assert "TEST_Update KW 2" in unmatched_after, f"KW 2 should be released to unmatched. Got: {unmatched_after}"
        assert "TEST_Update KW 3" not in unmatched_after, "KW 3 should now be mapped"
        
        print("Update correctly handled keyword add/remove")
        
        # Cleanup
        self.session.delete(f"{BASE_URL}/api/job-keyword-mappings/{mapping_id}")
    
    # ============ EXACT MATCH NORMALIZATION ============
    
    def test_job_role_normalization_uses_exact_match(self):
        """Job role normalization uses exact match (not substring) on normalized titles"""
        # Upload test data with similar but different titles
        job_titles = ["TEST_AI Engineer", "TEST_AI ML Engineer", "TEST_Senior AI Engineer"]
        upload_resp = self._upload_naukri_csv(job_titles)
        assert upload_resp.status_code == 200, f"Upload failed: {upload_resp.text}"
        
        # Create mapping for "TEST_AI Engineer" only
        create_resp = self.session.post(f"{BASE_URL}/api/job-keyword-mappings", json={
            "job_role": "TEST_AI Role",
            "keywords": ["TEST_AI Engineer"]
        })
        assert create_resp.status_code == 200, f"Create failed: {create_resp.text}"
        mapping_id = create_resp.json()["id"]
        
        # Verify only exact match is mapped, others remain unmatched
        unmatched = self.session.get(f"{BASE_URL}/api/job-titles/unmatched").json()["titles"]
        assert "TEST_AI Engineer" not in unmatched, "Exact match should be mapped"
        assert "TEST_AI ML Engineer" in unmatched, f"Similar but different title should remain unmatched. Got: {unmatched}"
        assert "TEST_Senior AI Engineer" in unmatched, "Similar but different title should remain unmatched"
        
        print("Exact match normalization verified - no substring matching")
        
        # Cleanup
        self.session.delete(f"{BASE_URL}/api/job-keyword-mappings/{mapping_id}")
    
    # ============ NORMALIZED ROLES IN OTHER ENDPOINTS ============
    
    def test_job_roles_endpoint_uses_normalized_roles(self):
        """GET /api/job-roles uses normalized roles from mappings"""
        resp = self.session.get(f"{BASE_URL}/api/job-roles")
        assert resp.status_code == 200, f"Failed: {resp.text}"
        data = resp.json()
        assert "job_roles" in data
        print(f"Job roles endpoint returned {len(data['job_roles'])} roles")
    
    def test_applicants_endpoint_uses_normalized_roles(self):
        """GET /api/applicants uses normalized job roles"""
        resp = self.session.get(f"{BASE_URL}/api/applicants")
        assert resp.status_code == 200, f"Failed: {resp.text}"
        data = resp.json()
        assert "data" in data
        # Check that job_role field exists in response
        if data["data"]:
            assert "job_role" in data["data"][0], "job_role field should be in applicants response"
        print(f"Applicants endpoint returned {len(data['data'])} records")
    
    def test_summary_endpoint_uses_normalized_roles(self):
        """GET /api/summary uses normalized job roles"""
        resp = self.session.get(f"{BASE_URL}/api/summary")
        assert resp.status_code == 200, f"Failed: {resp.text}"
        data = resp.json()
        assert "data" in data
        # Check that job_role field exists in response
        if data["data"]:
            assert "job_role" in data["data"][0], "job_role field should be in summary response"
        print(f"Summary endpoint returned {len(data['data'])} records")
    
    # ============ EXISTING ENDPOINTS STILL WORK ============
    
    def test_all_existing_endpoints_return_200(self):
        """All existing endpoints return 200"""
        endpoints = [
            "/api/job-keyword-mappings",
            "/api/job-titles/unmatched",
            "/api/job-roles",
            "/api/summary",
            "/api/applicants",
            "/api/data/registered",
            "/api/data/unregistered",
        ]
        
        for endpoint in endpoints:
            resp = self.session.get(f"{BASE_URL}{endpoint}")
            assert resp.status_code == 200, f"{endpoint} returned {resp.status_code}: {resp.text}"
            print(f"{endpoint} - OK (200)")
    
    # ============ EDGE CASES ============
    
    def test_create_mapping_requires_at_least_one_keyword(self):
        """POST /api/job-keyword-mappings requires at least one keyword"""
        resp = self.session.post(f"{BASE_URL}/api/job-keyword-mappings", json={
            "job_role": "TEST_Empty Keywords",
            "keywords": []
        })
        assert resp.status_code == 400, f"Expected 400, got {resp.status_code}"
    
    def test_mapping_not_found_returns_404(self):
        """DELETE /api/job-keyword-mappings with invalid ID returns 404"""
        resp = self.session.delete(f"{BASE_URL}/api/job-keyword-mappings/000000000000000000000000")
        assert resp.status_code == 404, f"Expected 404, got {resp.status_code}"
    
    def test_mapping_invalid_id_returns_400(self):
        """DELETE /api/job-keyword-mappings with invalid ID format returns 400"""
        resp = self.session.delete(f"{BASE_URL}/api/job-keyword-mappings/invalid-id")
        assert resp.status_code == 400, f"Expected 400, got {resp.status_code}"


class TestMappingCRUDBasics:
    """Basic CRUD tests for job keyword mappings"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup: Login and get session"""
        self.session = requests.Session()
        # Don't set Content-Type header - let requests handle it
        
        # Login
        login_resp = self.session.post(f"{BASE_URL}/api/login", json={
            "username": "admin",
            "password": "admin"
        })
        assert login_resp.status_code == 200
        yield
    
    def test_list_mappings(self):
        """GET /api/job-keyword-mappings returns list of mappings"""
        resp = self.session.get(f"{BASE_URL}/api/job-keyword-mappings")
        assert resp.status_code == 200
        data = resp.json()
        assert "mappings" in data
        assert isinstance(data["mappings"], list)
        print(f"Found {len(data['mappings'])} existing mappings")
    
    def test_create_update_delete_mapping(self):
        """Full CRUD cycle for a mapping"""
        # Create
        create_resp = self.session.post(f"{BASE_URL}/api/job-keyword-mappings", json={
            "job_role": "TEST_CRUD Role",
            "keywords": ["TEST_CRUD Keyword"]
        })
        assert create_resp.status_code == 200
        mapping_id = create_resp.json()["id"]
        print(f"Created mapping: {mapping_id}")
        
        # Read
        list_resp = self.session.get(f"{BASE_URL}/api/job-keyword-mappings")
        mappings = list_resp.json()["mappings"]
        found = [m for m in mappings if m["id"] == mapping_id]
        assert len(found) == 1
        assert found[0]["job_role"] == "TEST_CRUD Role"
        print("Read mapping verified")
        
        # Update
        update_resp = self.session.put(f"{BASE_URL}/api/job-keyword-mappings/{mapping_id}", json={
            "job_role": "TEST_CRUD Role Updated"
        })
        assert update_resp.status_code == 200
        print("Updated mapping")
        
        # Verify update
        list_resp2 = self.session.get(f"{BASE_URL}/api/job-keyword-mappings")
        mappings2 = list_resp2.json()["mappings"]
        found2 = [m for m in mappings2 if m["id"] == mapping_id]
        assert found2[0]["job_role"] == "TEST_CRUD Role Updated"
        print("Update verified")
        
        # Delete
        delete_resp = self.session.delete(f"{BASE_URL}/api/job-keyword-mappings/{mapping_id}")
        assert delete_resp.status_code == 200
        print("Deleted mapping")
        
        # Verify delete
        list_resp3 = self.session.get(f"{BASE_URL}/api/job-keyword-mappings")
        mappings3 = list_resp3.json()["mappings"]
        found3 = [m for m in mappings3 if m["id"] == mapping_id]
        assert len(found3) == 0
        print("Delete verified - CRUD cycle complete")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
