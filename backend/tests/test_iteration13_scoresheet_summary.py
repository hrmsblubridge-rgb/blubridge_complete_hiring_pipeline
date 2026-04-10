"""
Iteration 13: Test Score Sheet Upload, Summary Columns, and Role Drilldown Score Columns

Features to test:
1. GET /api/status: includes score_sheet_count field
2. POST /api/upload/scoresheet: accepts CSV with name/email/phone/score/round_name columns
3. GET /api/summary: includes total_naukri, total_registered, total_unregistered per role
4. GET /api/role: returns 19 columns (7 base + 11 score + 1 Total Score)
5. Score columns only populated for Attended status candidates
"""

import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

class TestAuth:
    """Authentication tests"""
    
    @pytest.fixture(scope="class")
    def session(self):
        """Create a session for authenticated requests"""
        s = requests.Session()
        return s
    
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


class TestStatusEndpoint:
    """Test /api/status endpoint includes score_sheet_count"""
    
    @pytest.fixture(scope="class")
    def auth_session(self):
        """Create authenticated session"""
        s = requests.Session()
        s.post(f"{BASE_URL}/api/login", json={"username": "admin", "password": "admin"})
        return s
    
    def test_status_includes_score_sheet_count(self, auth_session):
        """GET /api/status should include score_sheet_count field"""
        response = auth_session.get(f"{BASE_URL}/api/status")
        assert response.status_code == 200, f"Status failed: {response.text}"
        data = response.json()
        
        # Verify all expected fields
        assert "naukri_count" in data, "Missing naukri_count"
        assert "pipeline_count" in data, "Missing pipeline_count"
        assert "registered_count" in data, "Missing registered_count"
        assert "score_sheet_count" in data, "Missing score_sheet_count"
        
        print(f"✓ Status response: naukri={data['naukri_count']}, pipeline={data['pipeline_count']}, registered={data['registered_count']}, score_sheet={data['score_sheet_count']}")


class TestSummaryEndpoint:
    """Test /api/summary endpoint includes new columns"""
    
    @pytest.fixture(scope="class")
    def auth_session(self):
        """Create authenticated session"""
        s = requests.Session()
        s.post(f"{BASE_URL}/api/login", json={"username": "admin", "password": "admin"})
        return s
    
    def test_summary_includes_naukri_columns(self, auth_session):
        """GET /api/summary should include total_naukri, total_registered, total_unregistered"""
        response = auth_session.get(f"{BASE_URL}/api/summary")
        assert response.status_code == 200, f"Summary failed: {response.text}"
        data = response.json()
        
        assert "data" in data, "Missing data field"
        assert len(data["data"]) > 0, "No summary data returned"
        
        # Check first row has all required columns
        first_row = data["data"][0]
        required_columns = [
            "job_role", "total_naukri", "total_registered", "total_unregistered",
            "shortlisted", "rejected", "scheduled", "not_scheduled", "attended", "not_attended"
        ]
        
        for col in required_columns:
            assert col in first_row, f"Missing column: {col}"
        
        print(f"✓ Summary row: {first_row}")
        
        # Verify expected values based on test data
        # total_naukri=5, total_registered=5, total_unregistered=0
        assert first_row["total_naukri"] == 5, f"Expected total_naukri=5, got {first_row['total_naukri']}"
        assert first_row["total_registered"] == 5, f"Expected total_registered=5, got {first_row['total_registered']}"
        assert first_row["total_unregistered"] == 0, f"Expected total_unregistered=0, got {first_row['total_unregistered']}"
        
        print(f"✓ Summary values verified: total_naukri=5, total_registered=5, total_unregistered=0")


class TestRoleDrilldownScoreColumns:
    """Test /api/role endpoint returns score columns"""
    
    @pytest.fixture(scope="class")
    def auth_session(self):
        """Create authenticated session"""
        s = requests.Session()
        s.post(f"{BASE_URL}/api/login", json={"username": "admin", "password": "admin"})
        return s
    
    def test_role_returns_19_columns(self, auth_session):
        """GET /api/role should return 19 columns (7 base + 11 score + 1 Total Score)"""
        # URL encode the job role with special characters
        job_role = "AI & ML Engineer - C++ / Java Developer"
        response = auth_session.get(f"{BASE_URL}/api/role", params={"jobRole": job_role})
        assert response.status_code == 200, f"Role endpoint failed: {response.text}"
        data = response.json()
        
        assert "columns" in data, "Missing columns field"
        columns = data["columns"]
        
        # Expected 19 columns
        expected_base = ["name", "email", "phone", "gender", "date_of_birth", "date_of_application", "status"]
        expected_score = ["ZA", "C++", "Java", "BA", "LA", "Mensa Org", "Accounts2", "Accounts1", "BE", "Mensa", "BP"]
        expected_total = ["Total Score"]
        
        expected_columns = expected_base + expected_score + expected_total
        
        assert len(columns) == 19, f"Expected 19 columns, got {len(columns)}: {columns}"
        
        for col in expected_columns:
            assert col in columns, f"Missing column: {col}"
        
        print(f"✓ Role endpoint returns 19 columns: {columns}")
    
    def test_rishi_attended_has_scores(self, auth_session):
        """Rishi (Attended status) should show scores: ZA=85, C++=78, Java=90, BA=88, Total Score=341"""
        job_role = "AI & ML Engineer - C++ / Java Developer"
        response = auth_session.get(f"{BASE_URL}/api/role", params={"jobRole": job_role})
        assert response.status_code == 200, f"Role endpoint failed: {response.text}"
        data = response.json()
        
        # Find Rishi in the data
        rishi = None
        for applicant in data["data"]:
            if "Rishi" in str(applicant.get("name", "")):
                rishi = applicant
                break
        
        assert rishi is not None, "Rishi not found in applicants"
        
        # Verify Rishi has Attended status
        assert rishi["status"] == "Attended", f"Expected Rishi status=Attended, got {rishi['status']}"
        
        # Verify scores
        assert rishi.get("ZA") == 85, f"Expected ZA=85, got {rishi.get('ZA')}"
        assert rishi.get("C++") == 78, f"Expected C++=78, got {rishi.get('C++')}"
        assert rishi.get("Java") == 90, f"Expected Java=90, got {rishi.get('Java')}"
        assert rishi.get("BA") == 88, f"Expected BA=88, got {rishi.get('BA')}"
        assert rishi.get("Total Score") == 341, f"Expected Total Score=341, got {rishi.get('Total Score')}"
        
        print(f"✓ Rishi scores verified: ZA=85, C++=78, Java=90, BA=88, Total Score=341")
    
    def test_non_attended_show_dash(self, auth_session):
        """Non-attended candidates should show '-' for all score columns"""
        job_role = "AI & ML Engineer - C++ / Java Developer"
        response = auth_session.get(f"{BASE_URL}/api/role", params={"jobRole": job_role})
        assert response.status_code == 200, f"Role endpoint failed: {response.text}"
        data = response.json()
        
        score_columns = ["ZA", "C++", "Java", "BA", "LA", "Mensa Org", "Accounts2", "Accounts1", "BE", "Mensa", "BP", "Total Score"]
        
        # Find a non-attended candidate
        non_attended = None
        for applicant in data["data"]:
            if applicant.get("status") != "Attended":
                non_attended = applicant
                break
        
        if non_attended:
            for col in score_columns:
                assert non_attended.get(col) == "-", f"Expected {col}='-' for non-attended, got {non_attended.get(col)}"
            print(f"✓ Non-attended candidate '{non_attended.get('name')}' shows '-' for all score columns")
        else:
            print("⚠ No non-attended candidates found to verify")


class TestScoreSheetUpload:
    """Test /api/upload/scoresheet endpoint"""
    
    @pytest.fixture(scope="class")
    def auth_session(self):
        """Create authenticated session"""
        s = requests.Session()
        s.post(f"{BASE_URL}/api/login", json={"username": "admin", "password": "admin"})
        return s
    
    def test_scoresheet_upload_endpoint_exists(self, auth_session):
        """POST /api/upload/scoresheet should exist and require file"""
        # Test without file - should return 422 (validation error)
        response = auth_session.post(f"{BASE_URL}/api/upload/scoresheet")
        # 422 means endpoint exists but requires file
        assert response.status_code in [400, 422], f"Unexpected status: {response.status_code}"
        print(f"✓ Score sheet upload endpoint exists (returns {response.status_code} without file)")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
