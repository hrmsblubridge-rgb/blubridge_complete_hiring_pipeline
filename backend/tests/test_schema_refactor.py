"""
Test suite for Recruitment Analytics Schema Refactor
Tests: Column mapping, confirm_box field, data alignment, UPSERT logic, dashboard counts
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
        assert "version" in data
        print(f"✓ API healthy, version: {data['version']}")
    
    def test_login_with_admin_credentials(self):
        """Login with admin/admin returns success"""
        response = requests.post(f"{BASE_URL}/api/login", json={
            "username": "admin",
            "password": "admin"
        })
        assert response.status_code == 200
        data = response.json()
        assert data["success"] == True
        assert data["username"] == "admin"
        print("✓ Login with admin/admin successful")
    
    def test_login_invalid_credentials(self):
        """Login with wrong credentials returns 401"""
        response = requests.post(f"{BASE_URL}/api/login", json={
            "username": "wrong",
            "password": "wrong"
        })
        assert response.status_code == 401
        print("✓ Invalid credentials rejected with 401")


class TestNaukriUpload:
    """Naukri CSV upload and column mapping tests"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Login and get session"""
        self.session = requests.Session()
        response = self.session.post(f"{BASE_URL}/api/login", json={
            "username": "admin",
            "password": "admin"
        })
        assert response.status_code == 200
        yield
        self.session.close()
    
    def test_upload_naukri_csv(self):
        """Upload Naukri CSV with correct column names"""
        with open('/app/test_data/naukri_test.csv', 'rb') as f:
            files = {'file': ('naukri_test.csv', f, 'text/csv')}
            response = self.session.post(f"{BASE_URL}/api/upload/naukri", files=files)
        
        assert response.status_code == 200
        data = response.json()
        assert data["success"] == True
        assert data["total"] == 10
        assert "mapped_columns" in data
        assert "unmapped_columns" in data
        print(f"✓ Naukri upload: {data['inserted']} inserted, {data['updated']} updated")
        print(f"  Mapped columns: {data['mapped_columns']}, Unmapped: {data['unmapped_columns']}")
    
    def test_naukri_upsert_logic(self):
        """Re-upload same Naukri data gives 0 inserted, N updated"""
        # First upload
        with open('/app/test_data/naukri_test.csv', 'rb') as f:
            files = {'file': ('naukri_test.csv', f, 'text/csv')}
            self.session.post(f"{BASE_URL}/api/upload/naukri", files=files)
        
        # Second upload (UPSERT)
        with open('/app/test_data/naukri_test.csv', 'rb') as f:
            files = {'file': ('naukri_test.csv', f, 'text/csv')}
            response = self.session.post(f"{BASE_URL}/api/upload/naukri", files=files)
        
        assert response.status_code == 200
        data = response.json()
        assert data["inserted"] == 0, f"Expected 0 inserted, got {data['inserted']}"
        assert data["updated"] == 10, f"Expected 10 updated, got {data['updated']}"
        print(f"✓ UPSERT: 0 inserted, {data['updated']} updated")


class TestPipelineUpload:
    """Pipeline CSV upload and schema tests"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Login and get session"""
        self.session = requests.Session()
        response = self.session.post(f"{BASE_URL}/api/login", json={
            "username": "admin",
            "password": "admin"
        })
        assert response.status_code == 200
        yield
        self.session.close()
    
    def test_upload_pipeline_csv(self):
        """Upload Pipeline CSV with correct column names"""
        with open('/app/test_data/pipeline_test.csv', 'rb') as f:
            files = {'file': ('pipeline_test.csv', f, 'text/csv')}
            response = self.session.post(f"{BASE_URL}/api/upload/pipeline", files=files)
        
        assert response.status_code == 200
        data = response.json()
        assert data["success"] == True
        assert data["total"] == 7
        assert "mapped_columns" in data
        assert "unmapped_columns" in data
        print(f"✓ Pipeline upload: {data['inserted']} inserted, {data['updated']} updated")
        print(f"  Mapped columns: {data['mapped_columns']}, Unmapped: {data['unmapped_columns']}")
    
    def test_pipeline_upsert_logic(self):
        """Re-upload same Pipeline data gives 0 inserted, N updated"""
        # First upload
        with open('/app/test_data/pipeline_test.csv', 'rb') as f:
            files = {'file': ('pipeline_test.csv', f, 'text/csv')}
            self.session.post(f"{BASE_URL}/api/upload/pipeline", files=files)
        
        # Second upload (UPSERT)
        with open('/app/test_data/pipeline_test.csv', 'rb') as f:
            files = {'file': ('pipeline_test.csv', f, 'text/csv')}
            response = self.session.post(f"{BASE_URL}/api/upload/pipeline", files=files)
        
        assert response.status_code == 200
        data = response.json()
        assert data["inserted"] == 0, f"Expected 0 inserted, got {data['inserted']}"
        assert data["updated"] == 7, f"Expected 7 updated, got {data['updated']}"
        print(f"✓ UPSERT: 0 inserted, {data['updated']} updated")


class TestDashboardCounts:
    """Dashboard counts and relational integrity tests"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Login, upload test data, and get session"""
        self.session = requests.Session()
        response = self.session.post(f"{BASE_URL}/api/login", json={
            "username": "admin",
            "password": "admin"
        })
        assert response.status_code == 200
        
        # Upload test data
        with open('/app/test_data/naukri_test.csv', 'rb') as f:
            files = {'file': ('naukri_test.csv', f, 'text/csv')}
            self.session.post(f"{BASE_URL}/api/upload/naukri", files=files)
        
        with open('/app/test_data/pipeline_test.csv', 'rb') as f:
            files = {'file': ('pipeline_test.csv', f, 'text/csv')}
            self.session.post(f"{BASE_URL}/api/upload/pipeline", files=files)
        
        yield
        self.session.close()
    
    def test_dashboard_counts_structure(self):
        """Dashboard counts returns all required fields"""
        response = self.session.get(f"{BASE_URL}/api/dashboard-counts")
        assert response.status_code == 200
        data = response.json()
        
        required_fields = [
            "total_applies", "registered", "unregistered",
            "shortlisted", "rejected", "scheduled", "not_scheduled",
            "attended", "not_attended"
        ]
        for field in required_fields:
            assert field in data, f"Missing field: {field}"
        print(f"✓ Dashboard counts has all {len(required_fields)} required fields")
    
    def test_expected_counts(self):
        """Dashboard counts match expected values"""
        response = self.session.get(f"{BASE_URL}/api/dashboard-counts")
        data = response.json()
        
        # Expected: total=10, registered=7, unregistered=3
        assert data["total_applies"] == 10, f"Expected total=10, got {data['total_applies']}"
        assert data["registered"] == 7, f"Expected registered=7, got {data['registered']}"
        assert data["unregistered"] == 3, f"Expected unregistered=3, got {data['unregistered']}"
        
        # Expected: shortlisted=6, rejected=2
        assert data["shortlisted"] == 6, f"Expected shortlisted=6, got {data['shortlisted']}"
        assert data["rejected"] == 2, f"Expected rejected=2, got {data['rejected']}"
        
        # Expected: scheduled=5, not_scheduled=2
        assert data["scheduled"] == 5, f"Expected scheduled=5, got {data['scheduled']}"
        assert data["not_scheduled"] == 2, f"Expected not_scheduled=2, got {data['not_scheduled']}"
        
        # Expected: attended=3, not_attended=4
        assert data["attended"] == 3, f"Expected attended=3, got {data['attended']}"
        assert data["not_attended"] == 4, f"Expected not_attended=4, got {data['not_attended']}"
        
        print(f"✓ All counts match expected values")
        print(f"  total={data['total_applies']}, registered={data['registered']}, unregistered={data['unregistered']}")
        print(f"  shortlisted={data['shortlisted']}, rejected={data['rejected']}")
        print(f"  scheduled={data['scheduled']}, not_scheduled={data['not_scheduled']}")
        print(f"  attended={data['attended']}, not_attended={data['not_attended']}")
    
    def test_relational_integrity_partitions(self):
        """Verify relational integrity: reg+unreg=total, sched+not_sched=reg, att+not_att=reg"""
        response = self.session.get(f"{BASE_URL}/api/dashboard-counts")
        data = response.json()
        
        # Partition 1: registered + unregistered = total_applies
        assert data["registered"] + data["unregistered"] == data["total_applies"], \
            f"Partition failed: {data['registered']}+{data['unregistered']} != {data['total_applies']}"
        print(f"✓ Partition: registered({data['registered']}) + unregistered({data['unregistered']}) = total({data['total_applies']})")
        
        # Partition 2: scheduled + not_scheduled = registered
        assert data["scheduled"] + data["not_scheduled"] == data["registered"], \
            f"Partition failed: {data['scheduled']}+{data['not_scheduled']} != {data['registered']}"
        print(f"✓ Partition: scheduled({data['scheduled']}) + not_scheduled({data['not_scheduled']}) = registered({data['registered']})")
        
        # Partition 3: attended + not_attended = registered
        assert data["attended"] + data["not_attended"] == data["registered"], \
            f"Partition failed: {data['attended']}+{data['not_attended']} != {data['registered']}"
        print(f"✓ Partition: attended({data['attended']}) + not_attended({data['not_attended']}) = registered({data['registered']})")


class TestDataEndpoints:
    """Data endpoint tests for schema alignment"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Login, upload test data, and get session"""
        self.session = requests.Session()
        response = self.session.post(f"{BASE_URL}/api/login", json={
            "username": "admin",
            "password": "admin"
        })
        assert response.status_code == 200
        
        # Upload test data
        with open('/app/test_data/naukri_test.csv', 'rb') as f:
            files = {'file': ('naukri_test.csv', f, 'text/csv')}
            self.session.post(f"{BASE_URL}/api/upload/naukri", files=files)
        
        with open('/app/test_data/pipeline_test.csv', 'rb') as f:
            files = {'file': ('pipeline_test.csv', f, 'text/csv')}
            self.session.post(f"{BASE_URL}/api/upload/pipeline", files=files)
        
        yield
        self.session.close()
    
    def test_rejected_endpoint_has_confirm_box(self):
        """/api/data/rejected returns confirm_box field (not confirm)"""
        response = self.session.get(f"{BASE_URL}/api/data/rejected")
        assert response.status_code == 200
        data = response.json()
        
        assert "columns" in data
        assert "confirm_box" in data["columns"], f"confirm_box not in columns: {data['columns']}"
        assert "confirm" not in data["columns"], f"'confirm' should not be in columns: {data['columns']}"
        print(f"✓ Rejected endpoint has confirm_box in columns: {data['columns']}")
    
    def test_not_scheduled_endpoint_has_confirm_box(self):
        """/api/data/not-scheduled returns confirm_box field (not confirm)"""
        response = self.session.get(f"{BASE_URL}/api/data/not-scheduled")
        assert response.status_code == 200
        data = response.json()
        
        assert "columns" in data
        assert "confirm_box" in data["columns"], f"confirm_box not in columns: {data['columns']}"
        assert "confirm" not in data["columns"], f"'confirm' should not be in columns: {data['columns']}"
        print(f"✓ Not Scheduled endpoint has confirm_box in columns: {data['columns']}")
    
    def test_not_scheduled_diana_location(self):
        """Diana has location=Pune (no field misalignment)"""
        response = self.session.get(f"{BASE_URL}/api/data/not-scheduled")
        assert response.status_code == 200
        data = response.json()
        
        diana = next((r for r in data["data"] if r.get("name") == "Diana Lee"), None)
        assert diana is not None, "Diana Lee not found in not-scheduled"
        assert diana.get("location") == "Pune", f"Diana's location should be Pune, got: {diana.get('location')}"
        print(f"✓ Diana Lee has location=Pune (correct alignment)")
    
    def test_not_scheduled_eve_location(self):
        """Eve has location=Hyderabad (no field misalignment)"""
        response = self.session.get(f"{BASE_URL}/api/data/not-scheduled")
        assert response.status_code == 200
        data = response.json()
        
        eve = next((r for r in data["data"] if r.get("name") == "Eve Wilson"), None)
        assert eve is not None, "Eve Wilson not found in not-scheduled"
        assert eve.get("location") == "Hyderabad", f"Eve's location should be Hyderabad, got: {eve.get('location')}"
        print(f"✓ Eve Wilson has location=Hyderabad (correct alignment)")
    
    def test_unregistered_returns_correct_candidates(self):
        """Unregistered returns Harry, Ivy, Jack (not in pipeline)"""
        response = self.session.get(f"{BASE_URL}/api/data/unregistered")
        assert response.status_code == 200
        data = response.json()
        
        names = [r.get("name") for r in data["data"]]
        expected = ["Harry Patel", "Ivy Chen", "Jack Davis"]
        for name in expected:
            assert name in names, f"{name} should be in unregistered"
        print(f"✓ Unregistered contains: {names}")
    
    def test_attended_returns_correct_candidates(self):
        """Attended returns Alice, Charlie, Grace (otp_verified not null)"""
        response = self.session.get(f"{BASE_URL}/api/data/attended")
        assert response.status_code == 200
        data = response.json()
        
        names = [r.get("name") for r in data["data"]]
        expected = ["Alice Johnson", "Charlie Brown", "Grace Kim"]
        for name in expected:
            assert name in names, f"{name} should be in attended"
        print(f"✓ Attended contains: {names}")
    
    def test_rejected_returns_correct_candidates(self):
        """Rejected returns Bob Smith and Frank Garcia"""
        response = self.session.get(f"{BASE_URL}/api/data/rejected")
        assert response.status_code == 200
        data = response.json()
        
        names = [r.get("name") for r in data["data"]]
        expected = ["Bob Smith", "Frank Garcia"]
        for name in expected:
            assert name in names, f"{name} should be in rejected"
        print(f"✓ Rejected contains: {names}")


class TestAuthRequired:
    """Test that endpoints require authentication"""
    
    def test_dashboard_counts_requires_auth(self):
        """Dashboard counts returns 401 without auth"""
        response = requests.get(f"{BASE_URL}/api/dashboard-counts")
        assert response.status_code == 401
        print("✓ Dashboard counts requires auth (401)")
    
    def test_data_endpoints_require_auth(self):
        """Data endpoints return 401 without auth"""
        endpoints = [
            "unregistered", "registered", "shortlisted", "rejected",
            "scheduled", "not-scheduled", "attended", "not-attended"
        ]
        for endpoint in endpoints:
            response = requests.get(f"{BASE_URL}/api/data/{endpoint}")
            assert response.status_code == 401, f"/api/data/{endpoint} should require auth"
        print(f"✓ All {len(endpoints)} data endpoints require auth")
    
    def test_upload_endpoints_require_auth(self):
        """Upload endpoints return 401 without auth"""
        with open('/app/test_data/naukri_test.csv', 'rb') as f:
            files = {'file': ('test.csv', f, 'text/csv')}
            response = requests.post(f"{BASE_URL}/api/upload/naukri", files=files)
        assert response.status_code == 401
        
        with open('/app/test_data/pipeline_test.csv', 'rb') as f:
            files = {'file': ('test.csv', f, 'text/csv')}
            response = requests.post(f"{BASE_URL}/api/upload/pipeline", files=files)
        assert response.status_code == 401
        print("✓ Upload endpoints require auth (401)")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
