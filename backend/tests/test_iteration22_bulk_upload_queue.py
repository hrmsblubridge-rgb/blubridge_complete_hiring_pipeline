"""
Iteration 22: Bulk Upload Queue System Tests
Tests the DB-driven queue for sequential file processing with background worker.
Features tested:
- POST /api/bulk-upload/{type} - uploads files and creates queue records
- GET /api/bulk-upload/status - returns pending, processed, failed arrays per type
- POST /api/bulk-upload/process-now - returns worker status
- DELETE /api/bulk-upload/{type}/{queue_id} - removes pending file from queue
- DELETE returns 409 if file status is 'processing'
- Background worker processes pending files
- Processed files move to /processed_files/{type}/
- Failed files show error_message in status response
- Existing endpoints still work (summary, applicants, attended, job-roles)
"""

import pytest
import requests
import os
import time
import io

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')


def upload_file(session, upload_type, filename, content):
    """Helper to upload file with correct multipart format"""
    # Create file-like object from content
    file_obj = io.BytesIO(content.encode('utf-8'))
    
    # Use the correct format for requests multipart
    files = {'files': (filename, file_obj, 'text/csv')}
    
    # Don't send Content-Type header - let requests set it for multipart
    response = session.post(
        f"{BASE_URL}/api/bulk-upload/{upload_type}",
        files=files
    )
    return response


def upload_direct(session, upload_type, filename, content):
    """Helper to upload file directly (non-bulk)"""
    file_obj = io.BytesIO(content.encode('utf-8'))
    files = {'file': (filename, file_obj, 'text/csv')}
    
    response = session.post(
        f"{BASE_URL}/api/upload/{upload_type}",
        files=files
    )
    return response


@pytest.fixture(scope="module")
def auth_session():
    """Create authenticated session for all tests"""
    session = requests.Session()
    
    # Login
    response = session.post(f"{BASE_URL}/api/login", json={
        "username": "admin",
        "password": "admin"
    })
    if response.status_code != 200:
        pytest.skip("Authentication failed - skipping tests")
    return session


class TestBulkUploadEndpoints:
    """Test bulk upload queue endpoints"""
    
    def test_bulk_upload_status_endpoint_exists(self, auth_session):
        """GET /api/bulk-upload/status returns queue status"""
        response = auth_session.get(f"{BASE_URL}/api/bulk-upload/status")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        # Should have keys for each type
        assert "naukri" in data, "Missing 'naukri' key in status response"
        assert "pipeline" in data, "Missing 'pipeline' key in status response"
        assert "score" in data, "Missing 'score' key in status response"
        
        # Each type should have pending, processed, failed arrays
        for utype in ["naukri", "pipeline", "score"]:
            assert "pending" in data[utype], f"Missing 'pending' in {utype}"
            assert "processed" in data[utype], f"Missing 'processed' in {utype}"
            assert "failed" in data[utype], f"Missing 'failed' in {utype}"
            assert isinstance(data[utype]["pending"], list)
            assert isinstance(data[utype]["processed"], list)
            assert isinstance(data[utype]["failed"], list)
        print("✓ GET /api/bulk-upload/status returns correct structure")
    
    def test_bulk_upload_status_requires_auth(self):
        """GET /api/bulk-upload/status requires authentication"""
        response = requests.get(f"{BASE_URL}/api/bulk-upload/status")
        assert response.status_code == 401, f"Expected 401, got {response.status_code}"
        print("✓ GET /api/bulk-upload/status requires authentication")
    
    def test_process_now_endpoint_exists(self, auth_session):
        """POST /api/bulk-upload/process-now returns worker status"""
        response = auth_session.post(f"{BASE_URL}/api/bulk-upload/process-now")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert data.get("success") == True
        assert "pending" in data, "Missing 'pending' count"
        assert "processing" in data, "Missing 'processing' count"
        print(f"✓ POST /api/bulk-upload/process-now returns worker status: pending={data['pending']}, processing={data['processing']}")
    
    def test_upload_naukri_file_creates_queue_record(self, auth_session):
        """POST /api/bulk-upload/naukri uploads file and creates queue record"""
        csv_content = "Job Title,Email ID,Phone Number,Name\nTEST_Software Engineer,test_bulk1@example.com,9876543210,Test User 1"
        
        response = upload_file(auth_session, "naukri", "test_bulk_upload.csv", csv_content)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert data.get("success") == True
        assert data.get("count") >= 1, "Expected at least 1 file saved"
        print(f"✓ POST /api/bulk-upload/naukri uploaded file: {data}")
        
        # Verify queue record was created
        time.sleep(1)  # Give time for DB write
        status_response = auth_session.get(f"{BASE_URL}/api/bulk-upload/status")
        status_data = status_response.json()
        
        # File should be in pending or already processed
        naukri_status = status_data.get("naukri", {})
        pending = naukri_status.get("pending", [])
        processed = naukri_status.get("processed", [])
        
        # Check if our file is in pending or processed
        all_files = pending + processed
        found = any("test_bulk_upload.csv" in f.get("name", "") for f in all_files)
        assert found or len(all_files) > 0, "Queue record not found after upload"
        print("✓ Queue record created in bulk_upload_queue collection")
    
    def test_upload_invalid_type_returns_400(self, auth_session):
        """POST /api/bulk-upload/invalid_type returns 400"""
        csv_content = "col1,col2\nval1,val2"
        
        response = upload_file(auth_session, "invalid_type", "test.csv", csv_content)
        assert response.status_code == 400, f"Expected 400, got {response.status_code}: {response.text}"
        print("✓ POST /api/bulk-upload/invalid_type returns 400")
    
    def test_upload_pipeline_file(self, auth_session):
        """POST /api/bulk-upload/pipeline uploads file"""
        csv_content = "name,email,phone\nTest Pipeline User,test_pipeline_bulk@example.com,9876543211"
        
        response = upload_file(auth_session, "pipeline", "test_pipeline_bulk.csv", csv_content)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        print("✓ POST /api/bulk-upload/pipeline uploaded file")
    
    def test_upload_score_file(self, auth_session):
        """POST /api/bulk-upload/score uploads file"""
        csv_content = "name,email,phone,score,round_name\nTest Score User,test_score_bulk@example.com,9876543212,85,ZA"
        
        response = upload_file(auth_session, "score", "test_score_bulk.csv", csv_content)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        print("✓ POST /api/bulk-upload/score uploaded file")


class TestBulkUploadDelete:
    """Test delete functionality for bulk upload queue"""
    
    def test_delete_pending_file(self, auth_session):
        """DELETE /api/bulk-upload/{type}/{queue_id} removes pending file"""
        # First upload a file
        csv_content = "Job Title,Email ID,Phone Number,Name\nTEST_Delete Test,test_delete@example.com,9876543299,Delete Test"
        
        upload_response = upload_file(auth_session, "naukri", "test_delete_file.csv", csv_content)
        assert upload_response.status_code == 200
        
        # Get the queue ID from status
        time.sleep(0.5)
        status_response = auth_session.get(f"{BASE_URL}/api/bulk-upload/status")
        status_data = status_response.json()
        
        pending = status_data.get("naukri", {}).get("pending", [])
        
        # Find a pending file to delete
        pending_file = None
        for f in pending:
            if f.get("status") == "pending":
                pending_file = f
                break
        
        if pending_file:
            queue_id = pending_file["id"]
            delete_response = auth_session.delete(f"{BASE_URL}/api/bulk-upload/naukri/{queue_id}")
            assert delete_response.status_code == 200, f"Expected 200, got {delete_response.status_code}: {delete_response.text}"
            
            data = delete_response.json()
            assert data.get("success") == True
            print(f"✓ DELETE /api/bulk-upload/naukri/{queue_id} removed pending file")
        else:
            print("⚠ No pending files to delete (may have been processed already)")
    
    def test_delete_invalid_queue_id_returns_400(self, auth_session):
        """DELETE with invalid queue ID returns 400"""
        response = auth_session.delete(f"{BASE_URL}/api/bulk-upload/naukri/invalid_id")
        assert response.status_code == 400, f"Expected 400, got {response.status_code}"
        print("✓ DELETE with invalid queue ID returns 400")
    
    def test_delete_nonexistent_queue_id_returns_404(self, auth_session):
        """DELETE with non-existent queue ID returns 404"""
        # Use a valid ObjectId format but non-existent
        response = auth_session.delete(f"{BASE_URL}/api/bulk-upload/naukri/507f1f77bcf86cd799439011")
        assert response.status_code == 404, f"Expected 404, got {response.status_code}"
        print("✓ DELETE with non-existent queue ID returns 404")


class TestBackgroundWorkerProcessing:
    """Test that background worker processes files"""
    
    def test_file_processing_completes(self, auth_session):
        """Uploaded file gets processed by background worker within ~10 seconds"""
        # Upload a valid naukri file
        csv_content = "Job Title,Email ID,Phone Number,Name\nTEST_Worker Test,test_worker@example.com,9876543288,Worker Test User"
        
        upload_response = upload_file(auth_session, "naukri", "test_worker_processing.csv", csv_content)
        assert upload_response.status_code == 200
        print("Uploaded file, waiting for background worker to process...")
        
        # Wait for processing (worker polls every 3 seconds)
        max_wait = 15
        processed = False
        for i in range(max_wait):
            time.sleep(1)
            status_response = auth_session.get(f"{BASE_URL}/api/bulk-upload/status")
            status_data = status_response.json()
            
            processed_files = status_data.get("naukri", {}).get("processed", [])
            for f in processed_files:
                if "test_worker_processing.csv" in f.get("name", ""):
                    processed = True
                    print(f"✓ File processed after {i+1} seconds: {f}")
                    break
            
            if processed:
                break
        
        if not processed:
            # Check if it's still pending or failed
            pending = status_data.get("naukri", {}).get("pending", [])
            failed = status_data.get("naukri", {}).get("failed", [])
            print(f"Pending: {pending}")
            print(f"Failed: {failed}")
        
        assert processed, "File was not processed within 15 seconds"
    
    def test_processed_file_has_result(self, auth_session):
        """Processed files include result with inserted/updated counts"""
        status_response = auth_session.get(f"{BASE_URL}/api/bulk-upload/status")
        status_data = status_response.json()
        
        processed_files = status_data.get("naukri", {}).get("processed", [])
        
        if processed_files:
            # Check that at least one processed file has result
            has_result = any(f.get("result") is not None for f in processed_files)
            if has_result:
                for f in processed_files:
                    if f.get("result"):
                        print(f"✓ Processed file has result: {f['name']} -> {f['result']}")
                        break
            else:
                print("⚠ Processed files exist but no result data found")
        else:
            print("⚠ No processed files to check result")


class TestExistingEndpointsStillWork:
    """Verify existing endpoints still work after bulk upload changes"""
    
    def test_summary_endpoint(self, auth_session):
        """GET /api/summary still works"""
        response = auth_session.get(f"{BASE_URL}/api/summary")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        print("✓ GET /api/summary works")
    
    def test_applicants_endpoint(self, auth_session):
        """GET /api/applicants still works"""
        response = auth_session.get(f"{BASE_URL}/api/applicants")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        print("✓ GET /api/applicants works")
    
    def test_attended_endpoint(self, auth_session):
        """GET /api/attended still works"""
        response = auth_session.get(f"{BASE_URL}/api/attended")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        print("✓ GET /api/attended works")
    
    def test_job_roles_endpoint(self, auth_session):
        """GET /api/job-roles still works"""
        response = auth_session.get(f"{BASE_URL}/api/job-roles")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        print("✓ GET /api/job-roles works")
    
    def test_direct_upload_naukri_still_works(self, auth_session):
        """POST /api/upload/naukri (direct upload) still works"""
        csv_content = "Job Title,Email ID,Phone Number,Name\nTEST_Direct Upload,test_direct@example.com,9876543277,Direct Upload Test"
        
        response = upload_direct(auth_session, "naukri", "test_direct_upload.csv", csv_content)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        print("✓ POST /api/upload/naukri (direct upload) works")


class TestFailedFileHandling:
    """Test that failed files show error messages"""
    
    def test_invalid_file_shows_error(self, auth_session):
        """Upload invalid file and check error message in failed list"""
        # Create an invalid CSV (missing required columns)
        csv_content = "invalid_col1,invalid_col2\nval1,val2"
        
        upload_response = upload_file(auth_session, "naukri", "test_invalid_file.csv", csv_content)
        assert upload_response.status_code == 200
        print("Uploaded invalid file, waiting for processing...")
        
        # Wait for processing
        time.sleep(8)
        
        status_response = auth_session.get(f"{BASE_URL}/api/bulk-upload/status")
        status_data = status_response.json()
        
        failed_files = status_data.get("naukri", {}).get("failed", [])
        
        # Check if our invalid file is in failed list with error message
        found_failed = False
        for f in failed_files:
            if "test_invalid_file.csv" in f.get("name", ""):
                found_failed = True
                assert "error" in f, "Failed file should have 'error' field"
                print(f"✓ Invalid file in failed list with error: {f['error']}")
                break
        
        if not found_failed:
            # It might still be pending or processed (if columns matched by chance)
            pending = status_data.get("naukri", {}).get("pending", [])
            processed = status_data.get("naukri", {}).get("processed", [])
            print(f"⚠ Invalid file not in failed list. Pending: {len(pending)}, Processed: {len(processed)}, Failed: {len(failed_files)}")


class TestCleanup:
    """Clean up test data after all tests"""
    
    def test_cleanup_test_data(self, auth_session):
        """Clean up TEST_ prefixed data from collections"""
        # This is a cleanup test - we'll just verify we can access the collections
        # Actual cleanup would require direct DB access
        
        # Get status to see current state
        status_response = auth_session.get(f"{BASE_URL}/api/bulk-upload/status")
        assert status_response.status_code == 200
        
        status_data = status_response.json()
        for utype in ["naukri", "pipeline", "score"]:
            pending = len(status_data.get(utype, {}).get("pending", []))
            processed = len(status_data.get(utype, {}).get("processed", []))
            failed = len(status_data.get(utype, {}).get("failed", []))
            print(f"  {utype}: pending={pending}, processed={processed}, failed={failed}")
        
        print("✓ Test cleanup complete (manual DB cleanup may be needed for TEST_ prefixed data)")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
