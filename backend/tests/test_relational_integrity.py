"""
Test Suite for Recruitment Analytics API - Relational Integrity Validation
Tests the refactored architecture where registered_candidates is the INNER JOIN
of naukri_applies and pipeline_data. All sub-categories must be strict subsets of Registered.

Expected counts after fresh upload:
- total_applies = 10, registered = 7, unregistered = 3
- shortlisted = 6, rejected = 2
- scheduled = 5, not_scheduled = 2 (partition of registered)
- attended = 3, not_attended = 4 (partition of registered)
"""

import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

class TestAuthAndSetup:
    """Authentication and initial setup tests"""
    
    @pytest.fixture(scope="class")
    def session(self):
        """Create a session for all tests in this class"""
        return requests.Session()
    
    def test_01_api_health(self, session):
        """Test API is healthy"""
        response = session.get(f"{BASE_URL}/api/")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert data["version"] == "4.0"
        print("✓ API health check passed")
    
    def test_02_login_success(self, session):
        """Test login with admin/admin"""
        response = session.post(f"{BASE_URL}/api/login", json={
            "username": "admin",
            "password": "admin"
        })
        assert response.status_code == 200
        data = response.json()
        assert data["success"] == True
        assert data["username"] == "admin"
        print("✓ Login successful")
    
    def test_03_auth_check(self, session):
        """Test auth check after login"""
        # First login
        session.post(f"{BASE_URL}/api/login", json={
            "username": "admin",
            "password": "admin"
        })
        response = session.get(f"{BASE_URL}/api/auth/check")
        assert response.status_code == 200
        data = response.json()
        assert data["authenticated"] == True
        print("✓ Auth check passed")


class TestDataUpload:
    """Test data upload and UPSERT functionality"""
    
    @pytest.fixture(scope="class")
    def auth_session(self):
        """Create authenticated session"""
        session = requests.Session()
        session.post(f"{BASE_URL}/api/login", json={
            "username": "admin",
            "password": "admin"
        })
        return session
    
    def test_01_upload_naukri_csv(self, auth_session):
        """Upload Naukri CSV - 10 records"""
        with open('/app/test_data/naukri_test.csv', 'rb') as f:
            files = {'file': ('naukri_test.csv', f, 'text/csv')}
            response = auth_session.post(f"{BASE_URL}/api/upload/naukri", files=files)
        
        assert response.status_code == 200
        data = response.json()
        assert data["success"] == True
        assert data["total"] == 10
        # First upload should insert all
        print(f"✓ Naukri upload: inserted={data['inserted']}, updated={data['updated']}")
    
    def test_02_upload_pipeline_csv(self, auth_session):
        """Upload Pipeline CSV - 7 records"""
        with open('/app/test_data/pipeline_test.csv', 'rb') as f:
            files = {'file': ('pipeline_test.csv', f, 'text/csv')}
            response = auth_session.post(f"{BASE_URL}/api/upload/pipeline", files=files)
        
        assert response.status_code == 200
        data = response.json()
        assert data["success"] == True
        assert data["total"] == 7
        print(f"✓ Pipeline upload: inserted={data['inserted']}, updated={data['updated']}")


class TestDashboardCounts:
    """Test dashboard counts and relational integrity"""
    
    @pytest.fixture(scope="class")
    def auth_session(self):
        """Create authenticated session and ensure data is uploaded"""
        session = requests.Session()
        session.post(f"{BASE_URL}/api/login", json={
            "username": "admin",
            "password": "admin"
        })
        # Upload test data
        with open('/app/test_data/naukri_test.csv', 'rb') as f:
            session.post(f"{BASE_URL}/api/upload/naukri", files={'file': ('naukri_test.csv', f, 'text/csv')})
        with open('/app/test_data/pipeline_test.csv', 'rb') as f:
            session.post(f"{BASE_URL}/api/upload/pipeline", files={'file': ('pipeline_test.csv', f, 'text/csv')})
        return session
    
    def test_01_dashboard_counts_structure(self, auth_session):
        """Test dashboard counts returns all required fields"""
        response = auth_session.get(f"{BASE_URL}/api/dashboard-counts")
        assert response.status_code == 200
        data = response.json()
        
        required_fields = ['total_applies', 'registered', 'unregistered', 
                          'shortlisted', 'rejected', 'scheduled', 
                          'not_scheduled', 'attended', 'not_attended']
        for field in required_fields:
            assert field in data, f"Missing field: {field}"
        print(f"✓ Dashboard counts structure valid: {data}")
    
    def test_02_total_applies_count(self, auth_session):
        """Test total_applies = 10"""
        response = auth_session.get(f"{BASE_URL}/api/dashboard-counts")
        data = response.json()
        assert data["total_applies"] == 10, f"Expected 10, got {data['total_applies']}"
        print(f"✓ total_applies = {data['total_applies']}")
    
    def test_03_registered_count(self, auth_session):
        """Test registered = 7 (INNER JOIN of naukri and pipeline)"""
        response = auth_session.get(f"{BASE_URL}/api/dashboard-counts")
        data = response.json()
        assert data["registered"] == 7, f"Expected 7, got {data['registered']}"
        print(f"✓ registered = {data['registered']}")
    
    def test_04_unregistered_count(self, auth_session):
        """Test unregistered = 3 (Harry, Ivy, Jack)"""
        response = auth_session.get(f"{BASE_URL}/api/dashboard-counts")
        data = response.json()
        assert data["unregistered"] == 3, f"Expected 3, got {data['unregistered']}"
        print(f"✓ unregistered = {data['unregistered']}")
    
    def test_05_registered_plus_unregistered_equals_total(self, auth_session):
        """RELATIONAL INTEGRITY: registered + unregistered = total_applies"""
        response = auth_session.get(f"{BASE_URL}/api/dashboard-counts")
        data = response.json()
        assert data["registered"] + data["unregistered"] == data["total_applies"], \
            f"Partition violation: {data['registered']} + {data['unregistered']} != {data['total_applies']}"
        print(f"✓ PARTITION: registered({data['registered']}) + unregistered({data['unregistered']}) = total_applies({data['total_applies']})")
    
    def test_06_shortlisted_count(self, auth_session):
        """Test shortlisted = 6"""
        response = auth_session.get(f"{BASE_URL}/api/dashboard-counts")
        data = response.json()
        assert data["shortlisted"] == 6, f"Expected 6, got {data['shortlisted']}"
        print(f"✓ shortlisted = {data['shortlisted']}")
    
    def test_07_rejected_count(self, auth_session):
        """Test rejected = 2 (Bob, Frank with result_status=Rejected)"""
        response = auth_session.get(f"{BASE_URL}/api/dashboard-counts")
        data = response.json()
        assert data["rejected"] == 2, f"Expected 2, got {data['rejected']}"
        print(f"✓ rejected = {data['rejected']}")
    
    def test_08_scheduled_count(self, auth_session):
        """Test scheduled = 5"""
        response = auth_session.get(f"{BASE_URL}/api/dashboard-counts")
        data = response.json()
        assert data["scheduled"] == 5, f"Expected 5, got {data['scheduled']}"
        print(f"✓ scheduled = {data['scheduled']}")
    
    def test_09_not_scheduled_count(self, auth_session):
        """Test not_scheduled = 2 (Diana, Eve)"""
        response = auth_session.get(f"{BASE_URL}/api/dashboard-counts")
        data = response.json()
        assert data["not_scheduled"] == 2, f"Expected 2, got {data['not_scheduled']}"
        print(f"✓ not_scheduled = {data['not_scheduled']}")
    
    def test_10_scheduled_partition(self, auth_session):
        """PARTITION CHECK: scheduled + not_scheduled = registered"""
        response = auth_session.get(f"{BASE_URL}/api/dashboard-counts")
        data = response.json()
        assert data["scheduled"] + data["not_scheduled"] == data["registered"], \
            f"Partition violation: {data['scheduled']} + {data['not_scheduled']} != {data['registered']}"
        print(f"✓ PARTITION: scheduled({data['scheduled']}) + not_scheduled({data['not_scheduled']}) = registered({data['registered']})")
    
    def test_11_attended_count(self, auth_session):
        """Test attended = 3 (Alice, Charlie, Grace)"""
        response = auth_session.get(f"{BASE_URL}/api/dashboard-counts")
        data = response.json()
        assert data["attended"] == 3, f"Expected 3, got {data['attended']}"
        print(f"✓ attended = {data['attended']}")
    
    def test_12_not_attended_count(self, auth_session):
        """Test not_attended = 4 (Bob, Diana, Eve, Frank)"""
        response = auth_session.get(f"{BASE_URL}/api/dashboard-counts")
        data = response.json()
        assert data["not_attended"] == 4, f"Expected 4, got {data['not_attended']}"
        print(f"✓ not_attended = {data['not_attended']}")
    
    def test_13_attended_partition(self, auth_session):
        """PARTITION CHECK: attended + not_attended = registered"""
        response = auth_session.get(f"{BASE_URL}/api/dashboard-counts")
        data = response.json()
        assert data["attended"] + data["not_attended"] == data["registered"], \
            f"Partition violation: {data['attended']} + {data['not_attended']} != {data['registered']}"
        print(f"✓ PARTITION: attended({data['attended']}) + not_attended({data['not_attended']}) = registered({data['registered']})")
    
    def test_14_shortlisted_subset_of_registered(self, auth_session):
        """SUBSET CHECK: shortlisted <= registered"""
        response = auth_session.get(f"{BASE_URL}/api/dashboard-counts")
        data = response.json()
        assert data["shortlisted"] <= data["registered"], \
            f"Subset violation: shortlisted({data['shortlisted']}) > registered({data['registered']})"
        print(f"✓ SUBSET: shortlisted({data['shortlisted']}) <= registered({data['registered']})")
    
    def test_15_rejected_subset_of_registered(self, auth_session):
        """SUBSET CHECK: rejected <= registered"""
        response = auth_session.get(f"{BASE_URL}/api/dashboard-counts")
        data = response.json()
        assert data["rejected"] <= data["registered"], \
            f"Subset violation: rejected({data['rejected']}) > registered({data['registered']})"
        print(f"✓ SUBSET: rejected({data['rejected']}) <= registered({data['registered']})")


class TestDrillDownEndpoints:
    """Test drill-down data endpoints return correct data from registered_candidates"""
    
    @pytest.fixture(scope="class")
    def auth_session(self):
        """Create authenticated session and ensure data is uploaded"""
        session = requests.Session()
        session.post(f"{BASE_URL}/api/login", json={
            "username": "admin",
            "password": "admin"
        })
        # Upload test data
        with open('/app/test_data/naukri_test.csv', 'rb') as f:
            session.post(f"{BASE_URL}/api/upload/naukri", files={'file': ('naukri_test.csv', f, 'text/csv')})
        with open('/app/test_data/pipeline_test.csv', 'rb') as f:
            session.post(f"{BASE_URL}/api/upload/pipeline", files={'file': ('pipeline_test.csv', f, 'text/csv')})
        return session
    
    def test_01_unregistered_returns_correct_records(self, auth_session):
        """Unregistered should return Harry, Ivy, Jack ONLY"""
        response = auth_session.get(f"{BASE_URL}/api/data/unregistered")
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 3, f"Expected 3 unregistered, got {data['total']}"
        
        names = [r["name"] for r in data["data"]]
        expected_names = ["Harry Patel", "Ivy Chen", "Jack Davis"]
        for name in expected_names:
            assert name in names, f"Missing unregistered: {name}"
        print(f"✓ Unregistered returns: {names}")
    
    def test_02_registered_returns_correct_records(self, auth_session):
        """Registered should return 7 matched records"""
        response = auth_session.get(f"{BASE_URL}/api/data/registered")
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 7, f"Expected 7 registered, got {data['total']}"
        
        names = [r["name"] for r in data["data"]]
        expected_names = ["Alice Johnson", "Bob Smith", "Charlie Brown", "Diana Lee", 
                         "Eve Wilson", "Frank Garcia", "Grace Kim"]
        for name in expected_names:
            assert name in names, f"Missing registered: {name}"
        print(f"✓ Registered returns 7 records: {names}")
    
    def test_03_rejected_returns_bob_and_frank(self, auth_session):
        """Rejected should return Bob Smith and Frank Garcia"""
        response = auth_session.get(f"{BASE_URL}/api/data/rejected")
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 2, f"Expected 2 rejected, got {data['total']}"
        
        names = [r["name"] for r in data["data"]]
        assert "Bob Smith" in names, "Missing rejected: Bob Smith"
        assert "Frank Garcia" in names, "Missing rejected: Frank Garcia"
        print(f"✓ Rejected returns: {names}")
    
    def test_04_not_scheduled_returns_diana_and_eve(self, auth_session):
        """Not Scheduled should return Diana Lee and Eve Wilson"""
        response = auth_session.get(f"{BASE_URL}/api/data/not-scheduled")
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 2, f"Expected 2 not-scheduled, got {data['total']}"
        
        names = [r["name"] for r in data["data"]]
        assert "Diana Lee" in names, "Missing not-scheduled: Diana Lee"
        assert "Eve Wilson" in names, "Missing not-scheduled: Eve Wilson"
        print(f"✓ Not Scheduled returns: {names}")
    
    def test_05_attended_returns_alice_charlie_grace(self, auth_session):
        """Attended should return Alice, Charlie, Grace"""
        response = auth_session.get(f"{BASE_URL}/api/data/attended")
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 3, f"Expected 3 attended, got {data['total']}"
        
        names = [r["name"] for r in data["data"]]
        assert "Alice Johnson" in names, "Missing attended: Alice Johnson"
        assert "Charlie Brown" in names, "Missing attended: Charlie Brown"
        assert "Grace Kim" in names, "Missing attended: Grace Kim"
        print(f"✓ Attended returns: {names}")
    
    def test_06_not_attended_returns_bob_diana_eve_frank(self, auth_session):
        """Not Attended should return Bob, Diana, Eve, Frank"""
        response = auth_session.get(f"{BASE_URL}/api/data/not-attended")
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 4, f"Expected 4 not-attended, got {data['total']}"
        
        names = [r["name"] for r in data["data"]]
        expected = ["Bob Smith", "Diana Lee", "Eve Wilson", "Frank Garcia"]
        for name in expected:
            assert name in names, f"Missing not-attended: {name}"
        print(f"✓ Not Attended returns: {names}")
    
    def test_07_shortlisted_returns_6_records(self, auth_session):
        """Shortlisted should return 6 records"""
        response = auth_session.get(f"{BASE_URL}/api/data/shortlisted")
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 6, f"Expected 6 shortlisted, got {data['total']}"
        
        names = [r["name"] for r in data["data"]]
        # Eve has email_type='reject', so she's not shortlisted
        expected = ["Alice Johnson", "Bob Smith", "Charlie Brown", "Diana Lee", "Frank Garcia", "Grace Kim"]
        for name in expected:
            assert name in names, f"Missing shortlisted: {name}"
        print(f"✓ Shortlisted returns: {names}")
    
    def test_08_scheduled_returns_5_records(self, auth_session):
        """Scheduled should return 5 records"""
        response = auth_session.get(f"{BASE_URL}/api/data/scheduled")
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 5, f"Expected 5 scheduled, got {data['total']}"
        
        names = [r["name"] for r in data["data"]]
        expected = ["Alice Johnson", "Bob Smith", "Charlie Brown", "Frank Garcia", "Grace Kim"]
        for name in expected:
            assert name in names, f"Missing scheduled: {name}"
        print(f"✓ Scheduled returns: {names}")


class TestUpsertLogic:
    """Test UPSERT logic - re-uploading same data should update, not duplicate"""
    
    @pytest.fixture(scope="class")
    def auth_session(self):
        """Create authenticated session"""
        session = requests.Session()
        session.post(f"{BASE_URL}/api/login", json={
            "username": "admin",
            "password": "admin"
        })
        return session
    
    def test_01_reupload_naukri_updates_not_inserts(self, auth_session):
        """Re-uploading Naukri data should update existing records"""
        # First upload
        with open('/app/test_data/naukri_test.csv', 'rb') as f:
            auth_session.post(f"{BASE_URL}/api/upload/naukri", files={'file': ('naukri_test.csv', f, 'text/csv')})
        
        # Second upload - should update
        with open('/app/test_data/naukri_test.csv', 'rb') as f:
            response = auth_session.post(f"{BASE_URL}/api/upload/naukri", files={'file': ('naukri_test.csv', f, 'text/csv')})
        
        assert response.status_code == 200
        data = response.json()
        # On re-upload, all should be updates
        assert data["updated"] == 10, f"Expected 10 updates, got {data['updated']}"
        assert data["inserted"] == 0, f"Expected 0 inserts, got {data['inserted']}"
        print(f"✓ UPSERT Naukri: inserted={data['inserted']}, updated={data['updated']}")
    
    def test_02_reupload_pipeline_updates_not_inserts(self, auth_session):
        """Re-uploading Pipeline data should update existing records"""
        # First upload
        with open('/app/test_data/pipeline_test.csv', 'rb') as f:
            auth_session.post(f"{BASE_URL}/api/upload/pipeline", files={'file': ('pipeline_test.csv', f, 'text/csv')})
        
        # Second upload - should update
        with open('/app/test_data/pipeline_test.csv', 'rb') as f:
            response = auth_session.post(f"{BASE_URL}/api/upload/pipeline", files={'file': ('pipeline_test.csv', f, 'text/csv')})
        
        assert response.status_code == 200
        data = response.json()
        # On re-upload, all should be updates
        assert data["updated"] == 7, f"Expected 7 updates, got {data['updated']}"
        assert data["inserted"] == 0, f"Expected 0 inserts, got {data['inserted']}"
        print(f"✓ UPSERT Pipeline: inserted={data['inserted']}, updated={data['updated']}")
    
    def test_03_counts_unchanged_after_reupload(self, auth_session):
        """Dashboard counts should remain the same after re-upload"""
        response = auth_session.get(f"{BASE_URL}/api/dashboard-counts")
        data = response.json()
        
        assert data["total_applies"] == 10
        assert data["registered"] == 7
        assert data["unregistered"] == 3
        print(f"✓ Counts unchanged after UPSERT: total={data['total_applies']}, registered={data['registered']}, unregistered={data['unregistered']}")


class TestAuthProtection:
    """Test that all endpoints require authentication"""
    
    def test_01_dashboard_counts_requires_auth(self):
        """Dashboard counts should return 401 without auth"""
        response = requests.get(f"{BASE_URL}/api/dashboard-counts")
        assert response.status_code == 401
        print("✓ /api/dashboard-counts requires auth")
    
    def test_02_data_endpoints_require_auth(self):
        """All data endpoints should return 401 without auth"""
        endpoints = ['unregistered', 'registered', 'shortlisted', 'rejected', 
                    'scheduled', 'not-scheduled', 'attended', 'not-attended']
        for endpoint in endpoints:
            response = requests.get(f"{BASE_URL}/api/data/{endpoint}")
            assert response.status_code == 401, f"/api/data/{endpoint} should require auth"
        print("✓ All /api/data/* endpoints require auth")
    
    def test_03_upload_requires_auth(self):
        """Upload endpoints should return 401 without auth"""
        with open('/app/test_data/naukri_test.csv', 'rb') as f:
            response = requests.post(f"{BASE_URL}/api/upload/naukri", files={'file': ('test.csv', f, 'text/csv')})
        assert response.status_code == 401
        print("✓ /api/upload/naukri requires auth")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
