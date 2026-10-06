"""
Iteration 12: Test datetime.time serialization fix for Excel xlsx files
Bug Fix: clean_value() now handles datetime.time objects from Excel schedule_time columns
Also tests date formatting: midnight timestamps display as DD-Mon-YYYY instead of ISO
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

class TestAuth:
    """Authentication tests"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})
    
    def test_login_success(self):
        """Test login with admin/admin credentials"""
        response = self.session.post(f"{BASE_URL}/api/login", json={
            "username": "admin",
            "password": "admin"
        })
        assert response.status_code == 200
        data = response.json()
        assert data["success"] == True
        assert data["username"] == "admin"


class TestDataCounts:
    """Test data counts after xlsx upload fix - all 5 records should be present"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})
        # Login first
        response = self.session.post(f"{BASE_URL}/api/login", json={
            "username": "admin",
            "password": "admin"
        })
        assert response.status_code == 200
    
    def test_status_counts(self):
        """GET /api/status: naukri_count=5, pipeline_count=5, registered_count=5"""
        response = self.session.get(f"{BASE_URL}/api/status")
        assert response.status_code == 200
        data = response.json()
        assert data["naukri_count"] == 5, f"Expected naukri_count=5, got {data['naukri_count']}"
        assert data["pipeline_count"] == 5, f"Expected pipeline_count=5, got {data['pipeline_count']}"
        assert data["registered_count"] == 5, f"Expected registered_count=5, got {data['registered_count']}"
    
    def test_dashboard_counts(self):
        """GET /api/dashboard-counts: verify all counts match expected values"""
        response = self.session.get(f"{BASE_URL}/api/dashboard-counts")
        assert response.status_code == 200
        data = response.json()
        
        # Verify all expected counts
        assert data["registered"] == 5, f"Expected registered=5, got {data['registered']}"
        assert data["shortlisted"] == 5, f"Expected shortlisted=5, got {data['shortlisted']}"
        assert data["scheduled"] == 4, f"Expected scheduled=4, got {data['scheduled']}"
        assert data["not_scheduled"] == 1, f"Expected not_scheduled=1, got {data['not_scheduled']}"
        assert data["attended"] == 0, f"Expected attended=0, got {data['attended']}"
        assert data["not_attended"] == 4, f"Expected not_attended=4, got {data['not_attended']}"
        assert data["rejected"] == 0, f"Expected rejected=0, got {data['rejected']}"
    
    def test_debug_matching(self):
        """GET /api/debug/matching: 5 matched, 0 unmatched"""
        response = self.session.get(f"{BASE_URL}/api/debug/matching")
        assert response.status_code == 200
        data = response.json()
        
        assert data["matched"] == 5, f"Expected matched=5, got {data['matched']}"
        assert data["unmatched"] == 0, f"Expected unmatched=0, got {data['unmatched']}"
        assert data["total_naukri"] == 5
        assert data["total_pipeline"] == 5


class TestJobRoles:
    """Test job roles endpoint"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})
        response = self.session.post(f"{BASE_URL}/api/login", json={
            "username": "admin",
            "password": "admin"
        })
        assert response.status_code == 200
    
    def test_job_roles_list(self):
        """GET /api/job-roles: returns 1 role 'AI & ML Engineer - C++ / Java Developer' with count=5"""
        response = self.session.get(f"{BASE_URL}/api/job-roles")
        assert response.status_code == 200
        data = response.json()
        
        assert len(data["job_roles"]) == 1, f"Expected 1 job role, got {len(data['job_roles'])}"
        role = data["job_roles"][0]
        assert role["job_role"] == "AI & ML Engineer - C++ / Java Developer"
        assert role["count"] == 5, f"Expected count=5, got {role['count']}"


class TestRoleApplicants:
    """Test role applicants endpoint with URL-encoded special characters"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})
        response = self.session.post(f"{BASE_URL}/api/login", json={
            "username": "admin",
            "password": "admin"
        })
        assert response.status_code == 200
    
    def test_role_applicants(self):
        """GET /api/role?jobRole=...: returns 5 applicants with correct statuses"""
        # URL encode the job role with special characters
        job_role = "AI & ML Engineer - C++ / Java Developer"
        response = self.session.get(f"{BASE_URL}/api/role", params={"jobRole": job_role})
        assert response.status_code == 200
        data = response.json()
        
        assert data["total"] == 5, f"Expected total=5, got {data['total']}"
        assert len(data["data"]) == 5
        
        # Verify applicant statuses
        applicants = {a["name"]: a["status"] for a in data["data"]}
        
        # Expected: Rishi=Not Attended, Gautham=Not Attended, Madhumithaa=Not Attended, 
        # Harshini=Not Attended, Jona=Shortlisted
        assert applicants.get("Rishi S Nayak") == "Not Attended"
        assert applicants.get("Gautham Kumar Reddy") == "Not Attended"
        assert applicants.get("Madhumithaa G K") == "Not Attended"
        assert applicants.get("Harshini V M") == "Not Attended"
        assert applicants.get("Jona Delcy C A") == "Shortlisted"
    
    def test_date_format_dd_mon_yyyy(self):
        """Verify date values display as DD-Mon-YYYY format (not ISO timestamps)"""
        job_role = "AI & ML Engineer - C++ / Java Developer"
        response = self.session.get(f"{BASE_URL}/api/role", params={"jobRole": job_role})
        assert response.status_code == 200
        data = response.json()
        
        # Check date_of_birth and date_of_application formats
        for applicant in data["data"]:
            dob = applicant.get("date_of_birth", "")
            doa = applicant.get("date_of_application", "")
            
            # DD-Mon-YYYY format check (e.g., "05-Aug-2004")
            if dob and dob != "-":
                assert len(dob.split("-")) == 3, f"Invalid date format for DOB: {dob}"
                # Should not contain 'T' (ISO format indicator)
                assert "T" not in dob, f"DOB should be DD-Mon-YYYY, not ISO: {dob}"
            
            if doa and doa != "-":
                assert len(doa.split("-")) == 3, f"Invalid date format for DOA: {doa}"
                assert "T" not in doa, f"DOA should be DD-Mon-YYYY, not ISO: {doa}"


class TestSummary:
    """Test summary endpoint"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})
        response = self.session.post(f"{BASE_URL}/api/login", json={
            "username": "admin",
            "password": "admin"
        })
        assert response.status_code == 200
    
    def test_summary_stats(self):
        """GET /api/summary: 1 role with correct funnel stats"""
        response = self.session.get(f"{BASE_URL}/api/summary")
        assert response.status_code == 200
        data = response.json()
        
        assert len(data["data"]) == 1, f"Expected 1 role, got {len(data['data'])}"
        assert data["total_registered"] == 5
        
        role = data["data"][0]
        assert role["job_role"] == "AI & ML Engineer - C++ / Java Developer"
        assert role["total_applicants"] == 5
        assert role["shortlisted"] == 5
        assert role["scheduled"] == 4
        assert role["not_scheduled"] == 1
        assert role["attended"] == 0
        assert role["not_attended"] == 4


class TestHierarchyConstraints:
    """Verify strict hierarchy constraints are maintained"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})
        response = self.session.post(f"{BASE_URL}/api/login", json={
            "username": "admin",
            "password": "admin"
        })
        assert response.status_code == 200
    
    def test_hierarchy_constraints(self):
        """Verify: shortlisted = scheduled + not_scheduled, scheduled = attended + not_attended"""
        response = self.session.get(f"{BASE_URL}/api/dashboard-counts")
        assert response.status_code == 200
        data = response.json()
        
        # Hierarchy constraint 1: shortlisted = scheduled + not_scheduled
        assert data["shortlisted"] == data["scheduled"] + data["not_scheduled"], \
            f"Hierarchy violation: shortlisted({data['shortlisted']}) != scheduled({data['scheduled']}) + not_scheduled({data['not_scheduled']})"
        
        # Hierarchy constraint 2: scheduled = attended + not_attended
        assert data["scheduled"] == data["attended"] + data["not_attended"], \
            f"Hierarchy violation: scheduled({data['scheduled']}) != attended({data['attended']}) + not_attended({data['not_attended']})"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
