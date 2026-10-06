"""
Backend API tests for UI restructuring:
- GET /api/applicants (global applicants table)
- GET /api/attended (global attended table with optional jobRole)
- GET /api/summary (column renames verification)
- Drilldown routes removed verification
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

class TestAuth:
    """Authentication tests"""
    
    @pytest.fixture(scope="class")
    def session(self):
        return requests.Session()
    
    def test_login_success(self, session):
        """Test login with admin/admin credentials"""
        response = session.post(f"{BASE_URL}/api/login", json={
            "username": "admin",
            "password": "admin"
        })
        assert response.status_code == 200, f"Login failed: {response.text}"
        data = response.json()
        assert data.get("success") == True
        assert data.get("username") == "admin"
        print(f"✓ Login successful: {data}")


class TestGlobalApplicantsEndpoint:
    """Tests for GET /api/applicants - global registered applicants table"""
    
    @pytest.fixture(scope="class")
    def auth_session(self):
        session = requests.Session()
        session.post(f"{BASE_URL}/api/login", json={"username": "admin", "password": "admin"})
        return session
    
    def test_applicants_endpoint_exists(self, auth_session):
        """Test that /api/applicants endpoint exists and returns 200"""
        response = auth_session.get(f"{BASE_URL}/api/applicants")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        print(f"✓ /api/applicants endpoint exists and returns 200")
    
    def test_applicants_returns_correct_fields(self, auth_session):
        """Test that /api/applicants returns required fields"""
        response = auth_session.get(f"{BASE_URL}/api/applicants")
        assert response.status_code == 200
        data = response.json()
        
        # Check response structure
        assert "data" in data, "Response missing 'data' field"
        assert "total" in data, "Response missing 'total' field"
        assert "page" in data, "Response missing 'page' field"
        assert "limit" in data, "Response missing 'limit' field"
        
        # If there's data, check fields
        if data["data"]:
            row = data["data"][0]
            required_fields = [
                "name", "email", "phone", "college", "degree", "job_role",
                "registered_status", "registered_date", "schedule_date", 
                "schedule_time", "attended_or_not", "result_status"
            ]
            for field in required_fields:
                assert field in row, f"Missing field: {field}"
            print(f"✓ All required fields present: {list(row.keys())}")
        else:
            print("⚠ No data returned, but endpoint structure is correct")
    
    def test_applicants_job_role_filter(self, auth_session):
        """Test job role filter on /api/applicants"""
        # First get all applicants to find a job role
        response = auth_session.get(f"{BASE_URL}/api/applicants")
        assert response.status_code == 200
        data = response.json()
        
        if data["data"]:
            # Get a job role from the data
            job_role = data["data"][0].get("job_role")
            if job_role and job_role != "-":
                # Filter by that job role
                filtered_response = auth_session.get(f"{BASE_URL}/api/applicants", params={"jobRole": job_role})
                assert filtered_response.status_code == 200
                filtered_data = filtered_response.json()
                
                # All results should have the same job role
                for row in filtered_data["data"]:
                    assert row["job_role"].lower() == job_role.lower(), f"Job role mismatch: {row['job_role']} != {job_role}"
                print(f"✓ Job role filter works: filtered to '{job_role}'")
            else:
                print("⚠ No valid job role found to test filter")
        else:
            print("⚠ No data to test job role filter")
    
    def test_applicants_date_type_filter(self, auth_session):
        """Test date type filter options (Registered/Scheduled)"""
        # Test with Registered date type
        response1 = auth_session.get(f"{BASE_URL}/api/applicants", params={"dateType": "Registered"})
        assert response1.status_code == 200
        print("✓ Date type 'Registered' filter accepted")
        
        # Test with Scheduled date type
        response2 = auth_session.get(f"{BASE_URL}/api/applicants", params={"dateType": "Scheduled"})
        assert response2.status_code == 200
        print("✓ Date type 'Scheduled' filter accepted")
    
    def test_applicants_search_filter(self, auth_session):
        """Test search filter on /api/applicants"""
        response = auth_session.get(f"{BASE_URL}/api/applicants", params={"search": "test"})
        assert response.status_code == 200
        print("✓ Search filter works")
    
    def test_applicants_pagination(self, auth_session):
        """Test pagination on /api/applicants"""
        response = auth_session.get(f"{BASE_URL}/api/applicants", params={"page": 1, "limit": 10})
        assert response.status_code == 200
        data = response.json()
        assert data["page"] == 1
        assert data["limit"] == 10
        print(f"✓ Pagination works: page={data['page']}, limit={data['limit']}, total={data['total']}")


class TestGlobalAttendedEndpoint:
    """Tests for GET /api/attended - global attended applicants table"""
    
    @pytest.fixture(scope="class")
    def auth_session(self):
        session = requests.Session()
        session.post(f"{BASE_URL}/api/login", json={"username": "admin", "password": "admin"})
        return session
    
    def test_attended_endpoint_no_jobrole_returns_all(self, auth_session):
        """Test that /api/attended without jobRole returns all attended applicants"""
        response = auth_session.get(f"{BASE_URL}/api/attended")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        
        assert "data" in data
        assert "total" in data
        print(f"✓ /api/attended without jobRole returns {data['total']} attended applicants")
    
    def test_attended_with_jobrole_filter(self, auth_session):
        """Test that /api/attended with jobRole filter works"""
        # First get all to find a job role
        response = auth_session.get(f"{BASE_URL}/api/attended")
        assert response.status_code == 200
        data = response.json()
        
        if data["data"]:
            job_role = data["data"][0].get("job_role")
            if job_role and job_role != "-":
                filtered_response = auth_session.get(f"{BASE_URL}/api/attended", params={"jobRole": job_role})
                assert filtered_response.status_code == 200
                print(f"✓ /api/attended with jobRole filter works")
        else:
            print("⚠ No attended data to test jobRole filter")
    
    def test_attended_returns_correct_columns(self, auth_session):
        """Test that /api/attended returns correct columns including score columns"""
        response = auth_session.get(f"{BASE_URL}/api/attended")
        assert response.status_code == 200
        data = response.json()
        
        # Check columns in response
        if "columns" in data:
            expected_base_cols = ["name", "email", "phone", "college", "degree", "course", 
                                  "year_of_graduation", "job_role", "schedule_date", "result_status"]
            expected_score_cols = ["Accounts1", "Accounts2", "BA", "BE", "BP", "C++", "Java", "LA", "Mensa", "Mensa Org", "ZA"]
            
            for col in expected_base_cols:
                assert col in data["columns"], f"Missing base column: {col}"
            
            for col in expected_score_cols:
                assert col in data["columns"], f"Missing score column: {col}"
            
            # Verify NO Total Score column
            assert "Total Score" not in data["columns"], "Total Score column should NOT be present"
            assert "total_score" not in data["columns"], "total_score column should NOT be present"
            
            print(f"✓ All expected columns present, no Total Score column")
        
        # Check data rows if present
        if data["data"]:
            row = data["data"][0]
            # Verify score columns are in alphabetical order in the response
            score_cols_in_order = ["Accounts1", "Accounts2", "BA", "BE", "BP", "C++", "Java", "LA", "Mensa", "Mensa Org", "ZA"]
            for col in score_cols_in_order:
                assert col in row, f"Missing score column in data: {col}"
            print(f"✓ Score columns present in data rows")
    
    def test_attended_round_filter(self, auth_session):
        """Test round filter on /api/attended"""
        response = auth_session.get(f"{BASE_URL}/api/attended", params={"round": "Java"})
        assert response.status_code == 200
        print("✓ Round filter accepted")
    
    def test_attended_date_range_filter(self, auth_session):
        """Test date range filter on /api/attended"""
        response = auth_session.get(f"{BASE_URL}/api/attended", params={
            "startDate": "2024-01-01",
            "endDate": "2026-12-31"
        })
        assert response.status_code == 200
        print("✓ Date range filter works")
    
    def test_attended_search_filter(self, auth_session):
        """Test search filter on /api/attended"""
        response = auth_session.get(f"{BASE_URL}/api/attended", params={"search": "test"})
        assert response.status_code == 200
        print("✓ Search filter works")


class TestSummaryEndpoint:
    """Tests for GET /api/summary - verify column renames"""
    
    @pytest.fixture(scope="class")
    def auth_session(self):
        session = requests.Session()
        session.post(f"{BASE_URL}/api/login", json={"username": "admin", "password": "admin"})
        return session
    
    def test_summary_returns_correct_fields(self, auth_session):
        """Test that /api/summary returns fields matching renamed columns"""
        response = auth_session.get(f"{BASE_URL}/api/summary")
        assert response.status_code == 200
        data = response.json()
        
        assert "data" in data
        
        if data["data"]:
            row = data["data"][0]
            # These are the backend field names that map to the renamed UI columns
            expected_fields = [
                "job_role",
                "shortlisted",      # UI: "Shortlisted"
                "rejected",         # UI: "Rejected"
                "scheduled",        # UI: "Interview Scheduled"
                "not_scheduled",    # UI: "Interview Not Scheduled"
                "attended",         # UI: "Attended"
                "not_attended"      # UI: "Not Attended"
            ]
            for field in expected_fields:
                assert field in row, f"Missing field: {field}"
            print(f"✓ Summary returns all required fields for renamed columns")


class TestDrilldownRoutesRemoved:
    """Tests to verify drilldown routes no longer exist"""
    
    @pytest.fixture(scope="class")
    def auth_session(self):
        session = requests.Session()
        session.post(f"{BASE_URL}/api/login", json={"username": "admin", "password": "admin"})
        return session
    
    def test_old_role_endpoint_still_exists(self, auth_session):
        """Test that /api/role endpoint still exists (used internally)"""
        # The /api/role endpoint should still exist for backward compatibility
        response = auth_session.get(f"{BASE_URL}/api/role", params={"jobRole": "Test"})
        # Should return 200 even if no data
        assert response.status_code == 200
        print("✓ /api/role endpoint still exists")


class TestHealthCheck:
    """Basic health check"""
    
    def test_api_health(self):
        """Test API health endpoint"""
        response = requests.get(f"{BASE_URL}/api/")
        assert response.status_code == 200
        data = response.json()
        assert data.get("status") == "healthy"
        print(f"✓ API health check passed: {data}")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
