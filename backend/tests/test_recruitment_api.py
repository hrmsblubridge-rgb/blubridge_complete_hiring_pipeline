"""
Recruitment Analytics API Tests
Tests for: Login, Auth Check, Upload Naukri/Pipeline, Dashboard Counts, Drill-down Data Endpoints
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Test credentials
TEST_USERNAME = "admin"
TEST_PASSWORD = "admin"

# Test data file paths
NAUKRI_CSV_PATH = "/app/test_data/naukri_test.csv"
PIPELINE_CSV_PATH = "/app/test_data/pipeline_test.csv"


class TestHealthCheck:
    """Health check endpoint tests"""
    
    def test_api_health(self):
        """Test API root endpoint returns healthy status"""
        response = requests.get(f"{BASE_URL}/api/")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert "version" in data
        print(f"✓ API Health: {data}")


class TestAuthentication:
    """Authentication endpoint tests"""
    
    def test_login_success(self):
        """Test login with valid credentials"""
        response = requests.post(f"{BASE_URL}/api/login", json={
            "username": TEST_USERNAME,
            "password": TEST_PASSWORD
        })
        assert response.status_code == 200
        data = response.json()
        assert data["success"] == True
        assert data["username"] == TEST_USERNAME
        print(f"✓ Login Success: {data}")
    
    def test_login_invalid_credentials(self):
        """Test login with invalid credentials"""
        response = requests.post(f"{BASE_URL}/api/login", json={
            "username": "wrong",
            "password": "wrong"
        })
        assert response.status_code == 401
        print("✓ Login with invalid credentials returns 401")
    
    def test_auth_check_without_token(self):
        """Test auth check without token returns 401"""
        response = requests.get(f"{BASE_URL}/api/auth/check")
        assert response.status_code == 401
        print("✓ Auth check without token returns 401")
    
    def test_auth_check_with_cookie(self):
        """Test auth check with valid cookie"""
        session = requests.Session()
        # Login first
        login_response = session.post(f"{BASE_URL}/api/login", json={
            "username": TEST_USERNAME,
            "password": TEST_PASSWORD
        })
        assert login_response.status_code == 200
        
        # Check auth
        auth_response = session.get(f"{BASE_URL}/api/auth/check")
        assert auth_response.status_code == 200
        data = auth_response.json()
        assert data["authenticated"] == True
        assert data["username"] == TEST_USERNAME
        print(f"✓ Auth check with cookie: {data}")
    
    def test_logout(self):
        """Test logout endpoint"""
        session = requests.Session()
        # Login first
        session.post(f"{BASE_URL}/api/login", json={
            "username": TEST_USERNAME,
            "password": TEST_PASSWORD
        })
        
        # Logout
        logout_response = session.post(f"{BASE_URL}/api/logout")
        assert logout_response.status_code == 200
        data = logout_response.json()
        assert data["success"] == True
        print(f"✓ Logout: {data}")


class TestUploadEndpoints:
    """Upload endpoint tests"""
    
    @pytest.fixture
    def auth_session(self):
        """Create authenticated session"""
        session = requests.Session()
        response = session.post(f"{BASE_URL}/api/login", json={
            "username": TEST_USERNAME,
            "password": TEST_PASSWORD
        })
        if response.status_code != 200:
            pytest.skip("Authentication failed")
        return session
    
    def test_upload_naukri_csv(self, auth_session):
        """Test uploading Naukri CSV file"""
        with open(NAUKRI_CSV_PATH, 'rb') as f:
            files = {'file': ('naukri_test.csv', f, 'text/csv')}
            response = auth_session.post(f"{BASE_URL}/api/upload/naukri", files=files)
        
        assert response.status_code == 200
        data = response.json()
        assert data["success"] == True
        assert "inserted" in data or "updated" in data
        assert data["total"] == 10  # 10 records in test file
        print(f"✓ Naukri Upload: {data}")
    
    def test_upload_pipeline_csv(self, auth_session):
        """Test uploading Pipeline CSV file"""
        with open(PIPELINE_CSV_PATH, 'rb') as f:
            files = {'file': ('pipeline_test.csv', f, 'text/csv')}
            response = auth_session.post(f"{BASE_URL}/api/upload/pipeline", files=files)
        
        assert response.status_code == 200
        data = response.json()
        assert data["success"] == True
        assert "inserted" in data or "updated" in data
        assert data["total"] == 7  # 7 records in test file
        print(f"✓ Pipeline Upload: {data}")
    
    def test_upload_without_auth(self):
        """Test upload without authentication returns 401"""
        with open(NAUKRI_CSV_PATH, 'rb') as f:
            files = {'file': ('naukri_test.csv', f, 'text/csv')}
            response = requests.post(f"{BASE_URL}/api/upload/naukri", files=files)
        
        assert response.status_code == 401
        print("✓ Upload without auth returns 401")
    
    def test_upsert_logic_no_duplicates(self, auth_session):
        """Test UPSERT logic - re-uploading same data should update not duplicate"""
        # First upload
        with open(NAUKRI_CSV_PATH, 'rb') as f:
            files = {'file': ('naukri_test.csv', f, 'text/csv')}
            response1 = auth_session.post(f"{BASE_URL}/api/upload/naukri", files=files)
        
        assert response1.status_code == 200
        data1 = response1.json()
        
        # Second upload of same data
        with open(NAUKRI_CSV_PATH, 'rb') as f:
            files = {'file': ('naukri_test.csv', f, 'text/csv')}
            response2 = auth_session.post(f"{BASE_URL}/api/upload/naukri", files=files)
        
        assert response2.status_code == 200
        data2 = response2.json()
        
        # Second upload should have all updates, no new inserts
        assert data2["updated"] == 10 or data2["inserted"] == 0
        print(f"✓ UPSERT Logic: First upload - inserted: {data1.get('inserted', 0)}, updated: {data1.get('updated', 0)}")
        print(f"✓ UPSERT Logic: Second upload - inserted: {data2.get('inserted', 0)}, updated: {data2.get('updated', 0)}")


class TestDashboardCounts:
    """Dashboard counts endpoint tests"""
    
    @pytest.fixture
    def auth_session(self):
        """Create authenticated session"""
        session = requests.Session()
        response = session.post(f"{BASE_URL}/api/login", json={
            "username": TEST_USERNAME,
            "password": TEST_PASSWORD
        })
        if response.status_code != 200:
            pytest.skip("Authentication failed")
        return session
    
    def test_dashboard_counts_structure(self, auth_session):
        """Test dashboard counts returns correct structure"""
        response = auth_session.get(f"{BASE_URL}/api/dashboard-counts")
        assert response.status_code == 200
        data = response.json()
        
        # Check all required fields exist
        required_fields = [
            "total_applies", "registered", "unregistered",
            "shortlisted", "rejected", "scheduled", 
            "not_scheduled", "attended", "not_attended"
        ]
        for field in required_fields:
            assert field in data, f"Missing field: {field}"
        
        print(f"✓ Dashboard Counts Structure: {data}")
    
    def test_dashboard_counts_values(self, auth_session):
        """Test dashboard counts have expected values after uploads"""
        # First ensure data is uploaded
        with open(NAUKRI_CSV_PATH, 'rb') as f:
            files = {'file': ('naukri_test.csv', f, 'text/csv')}
            auth_session.post(f"{BASE_URL}/api/upload/naukri", files=files)
        
        with open(PIPELINE_CSV_PATH, 'rb') as f:
            files = {'file': ('pipeline_test.csv', f, 'text/csv')}
            auth_session.post(f"{BASE_URL}/api/upload/pipeline", files=files)
        
        # Get counts
        response = auth_session.get(f"{BASE_URL}/api/dashboard-counts")
        assert response.status_code == 200
        data = response.json()
        
        # Validate counts based on test data
        # Naukri has 10 records, Pipeline has 7 records
        # 7 people in pipeline match 7 in naukri (by email/phone)
        assert data["total_applies"] == 10, f"Expected 10 total applies, got {data['total_applies']}"
        assert data["registered"] == 7, f"Expected 7 registered, got {data['registered']}"
        assert data["unregistered"] == 3, f"Expected 3 unregistered, got {data['unregistered']}"
        
        # Pipeline data analysis:
        # shortlist email_type: Alice, Bob, Charlie, Diana, Frank, Grace = 6
        # reject email_type: Eve = 1 (but result_status Rejected: Bob, Frank = 2)
        assert data["shortlisted"] == 6, f"Expected 6 shortlisted, got {data['shortlisted']}"
        assert data["rejected"] == 2, f"Expected 2 rejected, got {data['rejected']}"
        
        # Scheduled (has schedule_date): Alice, Bob, Charlie, Frank, Grace = 5
        assert data["scheduled"] == 5, f"Expected 5 scheduled, got {data['scheduled']}"
        
        # Not scheduled (shortlisted but no schedule_date): Diana = 1
        assert data["not_scheduled"] == 1, f"Expected 1 not_scheduled, got {data['not_scheduled']}"
        
        # Attended (otp_verified not null): Alice, Charlie, Grace = 3
        assert data["attended"] == 3, f"Expected 3 attended, got {data['attended']}"
        
        # Not attended (scheduled but otp_verified null): Bob, Frank = 2
        assert data["not_attended"] == 2, f"Expected 2 not_attended, got {data['not_attended']}"
        
        print(f"✓ Dashboard Counts Values: {data}")
    
    def test_dashboard_counts_without_auth(self):
        """Test dashboard counts without auth returns 401"""
        response = requests.get(f"{BASE_URL}/api/dashboard-counts")
        assert response.status_code == 401
        print("✓ Dashboard counts without auth returns 401")


class TestDrillDownEndpoints:
    """Drill-down data endpoint tests"""
    
    @pytest.fixture
    def auth_session(self):
        """Create authenticated session and ensure data is uploaded"""
        session = requests.Session()
        response = session.post(f"{BASE_URL}/api/login", json={
            "username": TEST_USERNAME,
            "password": TEST_PASSWORD
        })
        if response.status_code != 200:
            pytest.skip("Authentication failed")
        
        # Upload test data
        with open(NAUKRI_CSV_PATH, 'rb') as f:
            files = {'file': ('naukri_test.csv', f, 'text/csv')}
            session.post(f"{BASE_URL}/api/upload/naukri", files=files)
        
        with open(PIPELINE_CSV_PATH, 'rb') as f:
            files = {'file': ('pipeline_test.csv', f, 'text/csv')}
            session.post(f"{BASE_URL}/api/upload/pipeline", files=files)
        
        return session
    
    def test_unregistered_endpoint(self, auth_session):
        """Test /api/data/unregistered endpoint"""
        response = auth_session.get(f"{BASE_URL}/api/data/unregistered?page=1&limit=50")
        assert response.status_code == 200
        data = response.json()
        
        assert "data" in data
        assert "total" in data
        assert "columns" in data
        assert data["total"] == 3  # Harry, Ivy, Jack not in pipeline
        print(f"✓ Unregistered: {data['total']} records, columns: {data['columns']}")
    
    def test_registered_endpoint(self, auth_session):
        """Test /api/data/registered endpoint"""
        response = auth_session.get(f"{BASE_URL}/api/data/registered?page=1&limit=50")
        assert response.status_code == 200
        data = response.json()
        
        assert "data" in data
        assert "total" in data
        assert data["total"] == 7  # 7 matched in pipeline
        print(f"✓ Registered: {data['total']} records")
    
    def test_shortlisted_endpoint(self, auth_session):
        """Test /api/data/shortlisted endpoint"""
        response = auth_session.get(f"{BASE_URL}/api/data/shortlisted?page=1&limit=50")
        assert response.status_code == 200
        data = response.json()
        
        assert "data" in data
        assert data["total"] == 6  # 6 with email_type=shortlist
        print(f"✓ Shortlisted: {data['total']} records")
    
    def test_rejected_endpoint(self, auth_session):
        """Test /api/data/rejected endpoint"""
        response = auth_session.get(f"{BASE_URL}/api/data/rejected?page=1&limit=50")
        assert response.status_code == 200
        data = response.json()
        
        assert "data" in data
        assert data["total"] == 2  # Bob and Frank with result_status=Rejected
        print(f"✓ Rejected: {data['total']} records")
    
    def test_scheduled_endpoint(self, auth_session):
        """Test /api/data/scheduled endpoint"""
        response = auth_session.get(f"{BASE_URL}/api/data/scheduled?page=1&limit=50")
        assert response.status_code == 200
        data = response.json()
        
        assert "data" in data
        assert data["total"] == 5  # 5 with schedule_date
        print(f"✓ Scheduled: {data['total']} records")
    
    def test_not_scheduled_endpoint(self, auth_session):
        """Test /api/data/not-scheduled endpoint"""
        response = auth_session.get(f"{BASE_URL}/api/data/not-scheduled?page=1&limit=50")
        assert response.status_code == 200
        data = response.json()
        
        assert "data" in data
        assert data["total"] == 1  # Diana shortlisted but no schedule
        print(f"✓ Not Scheduled: {data['total']} records")
    
    def test_attended_endpoint(self, auth_session):
        """Test /api/data/attended endpoint"""
        response = auth_session.get(f"{BASE_URL}/api/data/attended?page=1&limit=50")
        assert response.status_code == 200
        data = response.json()
        
        assert "data" in data
        assert data["total"] == 3  # Alice, Charlie, Grace with otp_verified
        print(f"✓ Attended: {data['total']} records")
    
    def test_not_attended_endpoint(self, auth_session):
        """Test /api/data/not-attended endpoint"""
        response = auth_session.get(f"{BASE_URL}/api/data/not-attended?page=1&limit=50")
        assert response.status_code == 200
        data = response.json()
        
        assert "data" in data
        assert data["total"] == 2  # Bob, Frank scheduled but no otp_verified
        print(f"✓ Not Attended: {data['total']} records")
    
    def test_pagination(self, auth_session):
        """Test pagination works correctly"""
        # Get first page with limit 2
        response = auth_session.get(f"{BASE_URL}/api/data/registered?page=1&limit=2")
        assert response.status_code == 200
        data = response.json()
        
        assert data["page"] == 1
        assert data["limit"] == 2
        assert len(data["data"]) <= 2
        print(f"✓ Pagination: page={data['page']}, limit={data['limit']}, returned={len(data['data'])}")
    
    def test_drilldown_without_auth(self):
        """Test drill-down endpoints without auth return 401"""
        endpoints = [
            "unregistered", "registered", "shortlisted", "rejected",
            "scheduled", "not-scheduled", "attended", "not-attended"
        ]
        for endpoint in endpoints:
            response = requests.get(f"{BASE_URL}/api/data/{endpoint}")
            assert response.status_code == 401, f"Expected 401 for {endpoint}, got {response.status_code}"
        print("✓ All drill-down endpoints return 401 without auth")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
