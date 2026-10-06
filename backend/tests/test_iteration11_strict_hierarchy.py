"""
Iteration 11: STRICT STATUS HIERARCHY Tests
Tests the new hierarchy where:
- Shortlisted/Rejected use email_type field (NOT result_status)
- Scheduled = subset of Shortlisted (has schedule_date/time)
- Attended = subset of Scheduled (has otp_verified)

Expected counts with test data (10 Naukri, 9 Pipeline):
- registered=9, shortlisted=6, rejected=2
- scheduled=4, not_scheduled=2
- attended=2, not_attended=2

Hierarchy constraints:
- shortlisted(6) = scheduled(4) + not_scheduled(2)
- scheduled(4) = attended(2) + not_attended(2)
"""

import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

class TestAuth:
    """Authentication tests"""
    
    def test_login_success(self):
        """Login with admin/admin credentials"""
        response = requests.post(f"{BASE_URL}/api/login", json={
            "username": "admin",
            "password": "admin"
        })
        assert response.status_code == 200, f"Login failed: {response.text}"
        data = response.json()
        assert data.get("success") == True
        assert "username" in data
        print("✓ Login successful with admin/admin")


class TestStatusEndpoint:
    """Test /api/status endpoint for data counts"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Login and get session"""
        self.session = requests.Session()
        login_resp = self.session.post(f"{BASE_URL}/api/login", json={
            "username": "admin",
            "password": "admin"
        })
        assert login_resp.status_code == 200
    
    def test_status_counts(self):
        """GET /api/status shows naukri=10, pipeline=9, registered=9"""
        response = self.session.get(f"{BASE_URL}/api/status")
        assert response.status_code == 200, f"Status failed: {response.text}"
        data = response.json()
        
        print(f"Status response: {data}")
        
        # Verify expected counts
        assert data.get("naukri_count") == 10, f"Expected naukri=10, got {data.get('naukri_count')}"
        assert data.get("pipeline_count") == 9, f"Expected pipeline=9, got {data.get('pipeline_count')}"
        assert data.get("registered_count") == 9, f"Expected registered=9, got {data.get('registered_count')}"
        print("✓ Status counts correct: naukri=10, pipeline=9, registered=9")


class TestDashboardCounts:
    """Test /api/dashboard-counts with STRICT HIERARCHY"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Login and get session"""
        self.session = requests.Session()
        login_resp = self.session.post(f"{BASE_URL}/api/login", json={
            "username": "admin",
            "password": "admin"
        })
        assert login_resp.status_code == 200
    
    def test_dashboard_counts_hierarchy(self):
        """GET /api/dashboard-counts: verify strict hierarchy counts"""
        response = self.session.get(f"{BASE_URL}/api/dashboard-counts")
        assert response.status_code == 200, f"Dashboard counts failed: {response.text}"
        data = response.json()
        
        print(f"Dashboard counts: {data}")
        
        # Verify expected counts based on email_type hierarchy
        assert data.get("shortlisted") == 6, f"Expected shortlisted=6, got {data.get('shortlisted')}"
        assert data.get("rejected") == 2, f"Expected rejected=2, got {data.get('rejected')}"
        assert data.get("scheduled") == 4, f"Expected scheduled=4, got {data.get('scheduled')}"
        assert data.get("not_scheduled") == 2, f"Expected not_scheduled=2, got {data.get('not_scheduled')}"
        assert data.get("attended") == 2, f"Expected attended=2, got {data.get('attended')}"
        assert data.get("not_attended") == 2, f"Expected not_attended=2, got {data.get('not_attended')}"
        
        print("✓ Dashboard counts correct: shortlisted=6, rejected=2, scheduled=4, not_scheduled=2, attended=2, not_attended=2")
    
    def test_hierarchy_constraint_shortlisted(self):
        """Verify: shortlisted(6) = scheduled(4) + not_scheduled(2)"""
        response = self.session.get(f"{BASE_URL}/api/dashboard-counts")
        assert response.status_code == 200
        data = response.json()
        
        shortlisted = data.get("shortlisted", 0)
        scheduled = data.get("scheduled", 0)
        not_scheduled = data.get("not_scheduled", 0)
        
        assert shortlisted == scheduled + not_scheduled, \
            f"Hierarchy violation: shortlisted({shortlisted}) != scheduled({scheduled}) + not_scheduled({not_scheduled})"
        print(f"✓ Hierarchy valid: shortlisted({shortlisted}) = scheduled({scheduled}) + not_scheduled({not_scheduled})")
    
    def test_hierarchy_constraint_scheduled(self):
        """Verify: scheduled(4) = attended(2) + not_attended(2)"""
        response = self.session.get(f"{BASE_URL}/api/dashboard-counts")
        assert response.status_code == 200
        data = response.json()
        
        scheduled = data.get("scheduled", 0)
        attended = data.get("attended", 0)
        not_attended = data.get("not_attended", 0)
        
        assert scheduled == attended + not_attended, \
            f"Hierarchy violation: scheduled({scheduled}) != attended({attended}) + not_attended({not_attended})"
        print(f"✓ Hierarchy valid: scheduled({scheduled}) = attended({attended}) + not_attended({not_attended})")


class TestRoleEndpoint:
    """Test /api/role endpoint for individual applicant status"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Login and get session"""
        self.session = requests.Session()
        login_resp = self.session.post(f"{BASE_URL}/api/login", json={
            "username": "admin",
            "password": "admin"
        })
        assert login_resp.status_code == 200
    
    def test_software_developer_applicants(self):
        """GET /api/role?jobRole=Software Developer: 5 applicants with correct statuses"""
        response = self.session.get(f"{BASE_URL}/api/role", params={"jobRole": "Software Developer"})
        assert response.status_code == 200, f"Role endpoint failed: {response.text}"
        data = response.json()
        
        print(f"Software Developer applicants: {data}")
        
        assert data.get("total") == 5, f"Expected 5 applicants, got {data.get('total')}"
        
        # Build name->status map
        applicants = {a["name"]: a["status"] for a in data.get("data", [])}
        print(f"Applicant statuses: {applicants}")
        
        # Expected statuses based on hierarchy
        expected = {
            "Alice Johnson": "Attended",
            "Bob Smith": "Not Attended",
            "Dave Wilson": "Attended",
            "Frank Lee": "Not Attended",
            "Henry Chen": "Shortlisted"
        }
        
        for name, expected_status in expected.items():
            actual_status = applicants.get(name)
            assert actual_status == expected_status, \
                f"{name}: expected '{expected_status}', got '{actual_status}'"
            print(f"✓ {name}: {actual_status}")
    
    def test_data_analyst_applicants(self):
        """GET /api/role?jobRole=Data Analyst: 4 applicants with correct statuses"""
        response = self.session.get(f"{BASE_URL}/api/role", params={"jobRole": "Data Analyst"})
        assert response.status_code == 200, f"Role endpoint failed: {response.text}"
        data = response.json()
        
        print(f"Data Analyst applicants: {data}")
        
        assert data.get("total") == 4, f"Expected 4 applicants, got {data.get('total')}"
        
        # Build name->status map
        applicants = {a["name"]: a["status"] for a in data.get("data", [])}
        print(f"Applicant statuses: {applicants}")
        
        # Expected statuses based on hierarchy
        # Note: Actual data has "Ivy Wang" not "Ivy Martinez"
        expected = {
            "Carol Davis": "Shortlisted",
            "Eve Brown": "Rejected",
            "Grace Kim": "Registered",  # email_type='general' -> Registered
            "Ivy Wang": "Rejected"
        }
        
        for name, expected_status in expected.items():
            actual_status = applicants.get(name)
            assert actual_status == expected_status, \
                f"{name}: expected '{expected_status}', got '{actual_status}'"
            print(f"✓ {name}: {actual_status}")


class TestSummaryEndpoint:
    """Test /api/summary endpoint for funnel statistics"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Login and get session"""
        self.session = requests.Session()
        login_resp = self.session.post(f"{BASE_URL}/api/login", json={
            "username": "admin",
            "password": "admin"
        })
        assert login_resp.status_code == 200
    
    def test_summary_software_developer(self):
        """GET /api/summary: Software Developer stats"""
        response = self.session.get(f"{BASE_URL}/api/summary")
        assert response.status_code == 200, f"Summary failed: {response.text}"
        data = response.json()
        
        print(f"Summary response: {data}")
        
        # Find Software Developer stats
        sw_dev = None
        for role in data.get("data", []):
            if role.get("job_role") == "Software Developer":
                sw_dev = role
                break
        
        assert sw_dev is not None, "Software Developer not found in summary"
        
        # Expected: total=5, shortlisted=5, rejected=0, scheduled=4, attended=2
        assert sw_dev.get("total_applicants") == 5, f"Expected total=5, got {sw_dev.get('total_applicants')}"
        assert sw_dev.get("shortlisted") == 5, f"Expected shortlisted=5, got {sw_dev.get('shortlisted')}"
        assert sw_dev.get("rejected") == 0, f"Expected rejected=0, got {sw_dev.get('rejected')}"
        assert sw_dev.get("scheduled") == 4, f"Expected scheduled=4, got {sw_dev.get('scheduled')}"
        assert sw_dev.get("attended") == 2, f"Expected attended=2, got {sw_dev.get('attended')}"
        
        print(f"✓ Software Developer: total=5, shortlisted=5, rejected=0, scheduled=4, attended=2")
    
    def test_summary_data_analyst(self):
        """GET /api/summary: Data Analyst stats"""
        response = self.session.get(f"{BASE_URL}/api/summary")
        assert response.status_code == 200
        data = response.json()
        
        # Find Data Analyst stats
        da = None
        for role in data.get("data", []):
            if role.get("job_role") == "Data Analyst":
                da = role
                break
        
        assert da is not None, "Data Analyst not found in summary"
        
        # Expected: total=4, shortlisted=1, rejected=2, scheduled=0, attended=0
        assert da.get("total_applicants") == 4, f"Expected total=4, got {da.get('total_applicants')}"
        assert da.get("shortlisted") == 1, f"Expected shortlisted=1, got {da.get('shortlisted')}"
        assert da.get("rejected") == 2, f"Expected rejected=2, got {da.get('rejected')}"
        assert da.get("scheduled") == 0, f"Expected scheduled=0, got {da.get('scheduled')}"
        assert da.get("attended") == 0, f"Expected attended=0, got {da.get('attended')}"
        
        print(f"✓ Data Analyst: total=4, shortlisted=1, rejected=2, scheduled=0, attended=0")


class TestDataEndpoints:
    """Test /api/data/* endpoints for drill-down data"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Login and get session"""
        self.session = requests.Session()
        login_resp = self.session.post(f"{BASE_URL}/api/login", json={
            "username": "admin",
            "password": "admin"
        })
        assert login_resp.status_code == 200
    
    def test_data_shortlisted(self):
        """GET /api/data/shortlisted: returns 6 records (email_type based)"""
        response = self.session.get(f"{BASE_URL}/api/data/shortlisted")
        assert response.status_code == 200, f"Shortlisted data failed: {response.text}"
        data = response.json()
        
        print(f"Shortlisted data: total={data.get('total')}")
        
        assert data.get("total") == 6, f"Expected 6 shortlisted, got {data.get('total')}"
        print("✓ Shortlisted returns 6 records")
    
    def test_data_rejected(self):
        """GET /api/data/rejected: returns 2 records (email_type based, NOT result_status)"""
        response = self.session.get(f"{BASE_URL}/api/data/rejected")
        assert response.status_code == 200, f"Rejected data failed: {response.text}"
        data = response.json()
        
        print(f"Rejected data: total={data.get('total')}, records={data.get('data')}")
        
        assert data.get("total") == 2, f"Expected 2 rejected, got {data.get('total')}"
        print("✓ Rejected returns 2 records (email_type based)")
    
    def test_data_scheduled(self):
        """GET /api/data/scheduled: returns 4 records (SUBSET of shortlisted)"""
        response = self.session.get(f"{BASE_URL}/api/data/scheduled")
        assert response.status_code == 200, f"Scheduled data failed: {response.text}"
        data = response.json()
        
        print(f"Scheduled data: total={data.get('total')}")
        
        assert data.get("total") == 4, f"Expected 4 scheduled, got {data.get('total')}"
        print("✓ Scheduled returns 4 records (subset of shortlisted)")
    
    def test_data_not_scheduled(self):
        """GET /api/data/not-scheduled: returns 2 records (SUBSET of shortlisted)"""
        response = self.session.get(f"{BASE_URL}/api/data/not-scheduled")
        assert response.status_code == 200, f"Not-scheduled data failed: {response.text}"
        data = response.json()
        
        print(f"Not-scheduled data: total={data.get('total')}")
        
        assert data.get("total") == 2, f"Expected 2 not-scheduled, got {data.get('total')}"
        print("✓ Not-scheduled returns 2 records (subset of shortlisted)")
    
    def test_data_attended(self):
        """GET /api/data/attended: returns 2 records (SUBSET of scheduled)"""
        response = self.session.get(f"{BASE_URL}/api/data/attended")
        assert response.status_code == 200, f"Attended data failed: {response.text}"
        data = response.json()
        
        print(f"Attended data: total={data.get('total')}")
        
        assert data.get("total") == 2, f"Expected 2 attended, got {data.get('total')}"
        print("✓ Attended returns 2 records (subset of scheduled)")
    
    def test_data_not_attended(self):
        """GET /api/data/not-attended: returns 2 records (SUBSET of scheduled)"""
        response = self.session.get(f"{BASE_URL}/api/data/not-attended")
        assert response.status_code == 200, f"Not-attended data failed: {response.text}"
        data = response.json()
        
        print(f"Not-attended data: total={data.get('total')}")
        
        assert data.get("total") == 2, f"Expected 2 not-attended, got {data.get('total')}"
        print("✓ Not-attended returns 2 records (subset of scheduled)")


class TestDebugMatching:
    """Test /api/debug/matching endpoint"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Login and get session"""
        self.session = requests.Session()
        login_resp = self.session.post(f"{BASE_URL}/api/login", json={
            "username": "admin",
            "password": "admin"
        })
        assert login_resp.status_code == 200
    
    def test_debug_matching_counts(self):
        """GET /api/debug/matching: all 9 matched records, 1 unmatched (Jack)"""
        response = self.session.get(f"{BASE_URL}/api/debug/matching")
        assert response.status_code == 200, f"Debug matching failed: {response.text}"
        data = response.json()
        
        print(f"Debug matching: matched={data.get('matched')}, unmatched={data.get('unmatched')}")
        
        assert data.get("matched") == 9, f"Expected 9 matched, got {data.get('matched')}"
        assert data.get("unmatched") == 1, f"Expected 1 unmatched, got {data.get('unmatched')}"
        
        # Verify Jack Brown is unmatched
        unmatched_names = [d["naukri_name"] for d in data.get("details", []) if not d.get("matched")]
        print(f"Unmatched: {unmatched_names}")
        assert "Jack Brown" in unmatched_names, "Jack Brown should be unmatched"
        
        print("✓ Debug matching: 9 matched, 1 unmatched (Jack Brown)")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
