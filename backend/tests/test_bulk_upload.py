"""
Test Bulk Upload Functionality - Iteration 17
Tests: POST /api/bulk-upload/{type}, GET /api/bulk-upload/status, 
       DELETE /api/bulk-upload/{type}/{filename}, POST /api/bulk-upload/process-now
"""
import pytest
import requests
import os
import time

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

class TestBulkUploadAPI:
    """Bulk Upload API tests"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Login and get session for authenticated requests"""
        self.session = requests.Session()
        login_res = self.session.post(f"{BASE_URL}/api/login", json={
            "username": "admin",
            "password": "admin"
        })
        assert login_res.status_code == 200, f"Login failed: {login_res.text}"
        print("Login successful")
    
    # ============ GET /api/bulk-upload/status ============
    def test_bulk_status_endpoint_returns_all_types(self):
        """GET /api/bulk-upload/status returns pending/processed for all 3 types"""
        res = self.session.get(f"{BASE_URL}/api/bulk-upload/status")
        assert res.status_code == 200, f"Status endpoint failed: {res.text}"
        data = res.json()
        
        # Verify all 3 types are present
        assert "naukri" in data, "Missing 'naukri' in status response"
        assert "pipeline" in data, "Missing 'pipeline' in status response"
        assert "score" in data, "Missing 'score' in status response"
        
        # Verify structure for each type
        for upload_type in ["naukri", "pipeline", "score"]:
            assert "pending" in data[upload_type], f"Missing 'pending' in {upload_type}"
            assert "processed" in data[upload_type], f"Missing 'processed' in {upload_type}"
            assert isinstance(data[upload_type]["pending"], list), f"pending should be list for {upload_type}"
            assert isinstance(data[upload_type]["processed"], list), f"processed should be list for {upload_type}"
        
        print(f"Status endpoint returns correct structure for all 3 types")
    
    # ============ POST /api/bulk-upload/naukri ============
    def test_bulk_upload_naukri_accepts_csv(self):
        """POST /api/bulk-upload/naukri accepts CSV file"""
        # Create a test CSV file content
        csv_content = b"Name,Email ID,Phone Number,Job Title\nTest User,test_bulk@example.com,9876543210,Developer"
        files = {'files': ('test_naukri.csv', csv_content, 'text/csv')}
        
        res = self.session.post(f"{BASE_URL}/api/bulk-upload/naukri", files=files)
        assert res.status_code == 200, f"Bulk upload naukri failed: {res.text}"
        data = res.json()
        
        assert data.get("success") == True, "Upload should succeed"
        assert "saved" in data, "Response should contain 'saved' list"
        assert data.get("count", 0) >= 1, "Should save at least 1 file"
        
        saved_filename = data["saved"][0] if data["saved"] else None
        print(f"Bulk upload naukri successful, saved: {saved_filename}")
        
        # Cleanup - delete the uploaded file
        if saved_filename:
            self.session.delete(f"{BASE_URL}/api/bulk-upload/naukri/{saved_filename}")
    
    def test_bulk_upload_naukri_rejects_invalid_type(self):
        """POST /api/bulk-upload/invalid returns 400"""
        csv_content = b"Name,Email\nTest,test@test.com"
        files = {'files': ('test.csv', csv_content, 'text/csv')}
        
        res = self.session.post(f"{BASE_URL}/api/bulk-upload/invalid_type", files=files)
        assert res.status_code == 400, f"Should reject invalid type, got {res.status_code}"
        print("Invalid type correctly rejected with 400")
    
    # ============ POST /api/bulk-upload/pipeline ============
    def test_bulk_upload_pipeline_accepts_csv(self):
        """POST /api/bulk-upload/pipeline accepts CSV file"""
        csv_content = b"name,email,phone,job_role\nPipeline Test,pipeline_bulk@test.com,1234567890,Analyst"
        files = {'files': ('test_pipeline.csv', csv_content, 'text/csv')}
        
        res = self.session.post(f"{BASE_URL}/api/bulk-upload/pipeline", files=files)
        assert res.status_code == 200, f"Bulk upload pipeline failed: {res.text}"
        data = res.json()
        
        assert data.get("success") == True, "Upload should succeed"
        assert data.get("count", 0) >= 1, "Should save at least 1 file"
        
        saved_filename = data["saved"][0] if data.get("saved") else None
        print(f"Bulk upload pipeline successful, saved: {saved_filename}")
        
        # Cleanup
        if saved_filename:
            self.session.delete(f"{BASE_URL}/api/bulk-upload/pipeline/{saved_filename}")
    
    # ============ POST /api/bulk-upload/score ============
    def test_bulk_upload_score_accepts_csv(self):
        """POST /api/bulk-upload/score accepts CSV file"""
        csv_content = b"name,email,phone,score,round_name\nScore Test,score_bulk@test.com,5555555555,85,Java"
        files = {'files': ('test_score.csv', csv_content, 'text/csv')}
        
        res = self.session.post(f"{BASE_URL}/api/bulk-upload/score", files=files)
        assert res.status_code == 200, f"Bulk upload score failed: {res.text}"
        data = res.json()
        
        assert data.get("success") == True, "Upload should succeed"
        assert data.get("count", 0) >= 1, "Should save at least 1 file"
        
        saved_filename = data["saved"][0] if data.get("saved") else None
        print(f"Bulk upload score successful, saved: {saved_filename}")
        
        # Cleanup
        if saved_filename:
            self.session.delete(f"{BASE_URL}/api/bulk-upload/score/{saved_filename}")
    
    # ============ DELETE /api/bulk-upload/{type}/{filename} ============
    def test_delete_pending_file(self):
        """DELETE /api/bulk-upload/naukri/{filename} removes file from pending"""
        # First upload a file
        csv_content = b"Name,Email ID,Phone Number\nDelete Test,delete_test@test.com,1111111111"
        files = {'files': ('delete_test.csv', csv_content, 'text/csv')}
        
        upload_res = self.session.post(f"{BASE_URL}/api/bulk-upload/naukri", files=files)
        assert upload_res.status_code == 200, "Upload should succeed"
        saved_filename = upload_res.json()["saved"][0]
        
        # Verify file is in pending
        status_res = self.session.get(f"{BASE_URL}/api/bulk-upload/status")
        pending_names = [f["name"] for f in status_res.json()["naukri"]["pending"]]
        assert saved_filename in pending_names, "File should be in pending"
        
        # Delete the file
        delete_res = self.session.delete(f"{BASE_URL}/api/bulk-upload/naukri/{saved_filename}")
        assert delete_res.status_code == 200, f"Delete failed: {delete_res.text}"
        assert delete_res.json().get("success") == True
        assert delete_res.json().get("deleted") == saved_filename
        
        # Verify file is no longer in pending
        status_res2 = self.session.get(f"{BASE_URL}/api/bulk-upload/status")
        pending_names2 = [f["name"] for f in status_res2.json()["naukri"]["pending"]]
        assert saved_filename not in pending_names2, "File should be removed from pending"
        
        print(f"Delete pending file successful: {saved_filename}")
    
    def test_delete_nonexistent_file_returns_404(self):
        """DELETE /api/bulk-upload/naukri/nonexistent.csv returns 404"""
        res = self.session.delete(f"{BASE_URL}/api/bulk-upload/naukri/nonexistent_file_12345.csv")
        assert res.status_code == 404, f"Should return 404 for nonexistent file, got {res.status_code}"
        print("Delete nonexistent file correctly returns 404")
    
    # ============ POST /api/bulk-upload/process-now ============
    def test_process_now_endpoint(self):
        """POST /api/bulk-upload/process-now processes pending files immediately"""
        # Upload a test file first
        csv_content = b"Name,Email ID,Phone Number,Job Title\nProcess Now Test,process_now@test.com,2222222222,Tester"
        files = {'files': ('process_now_test.csv', csv_content, 'text/csv')}
        
        upload_res = self.session.post(f"{BASE_URL}/api/bulk-upload/naukri", files=files)
        assert upload_res.status_code == 200, "Upload should succeed"
        saved_filename = upload_res.json()["saved"][0]
        
        # Trigger process-now
        process_res = self.session.post(f"{BASE_URL}/api/bulk-upload/process-now")
        assert process_res.status_code == 200, f"Process-now failed: {process_res.text}"
        data = process_res.json()
        
        assert "results" in data, "Response should contain 'results'"
        assert "naukri" in data["results"], "Results should contain 'naukri'"
        
        print(f"Process-now endpoint successful, results: {data['results']}")
        
        # Verify file moved to processed
        time.sleep(1)  # Small delay for file system
        status_res = self.session.get(f"{BASE_URL}/api/bulk-upload/status")
        processed_names = [f["name"] for f in status_res.json()["naukri"]["processed"]]
        pending_names = [f["name"] for f in status_res.json()["naukri"]["pending"]]
        
        # File should be in processed OR removed from pending (if processing succeeded)
        assert saved_filename not in pending_names or saved_filename in processed_names, \
            "File should be processed or moved from pending"
        print(f"File {saved_filename} processed successfully")
    
    # ============ Multiple Files Upload ============
    def test_bulk_upload_multiple_files(self):
        """POST /api/bulk-upload/naukri accepts multiple files"""
        csv1 = b"Name,Email ID,Phone Number\nMulti Test 1,multi1@test.com,3333333333"
        csv2 = b"Name,Email ID,Phone Number\nMulti Test 2,multi2@test.com,4444444444"
        
        files = [
            ('files', ('multi_test1.csv', csv1, 'text/csv')),
            ('files', ('multi_test2.csv', csv2, 'text/csv'))
        ]
        
        res = self.session.post(f"{BASE_URL}/api/bulk-upload/naukri", files=files)
        assert res.status_code == 200, f"Multi-file upload failed: {res.text}"
        data = res.json()
        
        assert data.get("success") == True
        assert data.get("count", 0) >= 2, f"Should save 2 files, got {data.get('count')}"
        
        print(f"Multiple files upload successful, saved {data.get('count')} files")
        
        # Cleanup
        for filename in data.get("saved", []):
            self.session.delete(f"{BASE_URL}/api/bulk-upload/naukri/{filename}")
    
    # ============ Auth Required ============
    def test_bulk_upload_requires_auth(self):
        """Bulk upload endpoints require authentication"""
        # Create new session without login
        unauth_session = requests.Session()
        
        csv_content = b"Name,Email\nTest,test@test.com"
        files = {'files': ('test.csv', csv_content, 'text/csv')}
        
        res = unauth_session.post(f"{BASE_URL}/api/bulk-upload/naukri", files=files)
        assert res.status_code == 401, f"Should require auth, got {res.status_code}"
        
        res2 = unauth_session.get(f"{BASE_URL}/api/bulk-upload/status")
        assert res2.status_code == 401, f"Status should require auth, got {res2.status_code}"
        
        print("Auth requirement verified for bulk upload endpoints")


class TestExistingSingleUploadStillWorks:
    """Verify existing single file upload endpoints still work"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Login and get session"""
        self.session = requests.Session()
        login_res = self.session.post(f"{BASE_URL}/api/login", json={
            "username": "admin",
            "password": "admin"
        })
        assert login_res.status_code == 200
    
    def test_single_naukri_upload_still_works(self):
        """POST /api/upload/naukri (single file) still works"""
        csv_content = b"Name,Email ID,Phone Number,Job Title\nSingle Upload Test,single_test@test.com,6666666666,Engineer"
        files = {'file': ('single_test.csv', csv_content, 'text/csv')}
        
        res = self.session.post(f"{BASE_URL}/api/upload/naukri", files=files)
        assert res.status_code == 200, f"Single upload failed: {res.text}"
        data = res.json()
        
        assert data.get("success") == True
        assert "inserted" in data or "updated" in data
        print(f"Single naukri upload still works: inserted={data.get('inserted')}, updated={data.get('updated')}")
    
    def test_single_pipeline_upload_still_works(self):
        """POST /api/upload/pipeline (single file) still works"""
        csv_content = b"name,email,phone,job_role\nSingle Pipeline Test,single_pipeline@test.com,7777777777,Manager"
        files = {'file': ('single_pipeline.csv', csv_content, 'text/csv')}
        
        res = self.session.post(f"{BASE_URL}/api/upload/pipeline", files=files)
        assert res.status_code == 200, f"Single pipeline upload failed: {res.text}"
        data = res.json()
        
        assert data.get("success") == True
        print(f"Single pipeline upload still works: inserted={data.get('inserted')}, updated={data.get('updated')}")
    
    def test_single_scoresheet_upload_still_works(self):
        """POST /api/upload/scoresheet (single file) still works"""
        csv_content = b"name,email,phone,score,round_name\nSingle Score Test,single_score@test.com,8888888888,90,Java"
        files = {'file': ('single_score.csv', csv_content, 'text/csv')}
        
        res = self.session.post(f"{BASE_URL}/api/upload/scoresheet", files=files)
        assert res.status_code == 200, f"Single scoresheet upload failed: {res.text}"
        data = res.json()
        
        assert data.get("success") == True
        print(f"Single scoresheet upload still works: inserted={data.get('inserted')}")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
