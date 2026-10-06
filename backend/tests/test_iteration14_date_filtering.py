"""
Iteration 14: Date Filtering Tests
Tests the date filtering fix across /api/summary and /api/role endpoints.
Dates are now stored in ISO YYYY-MM-DD format (not DD-Mon-YYYY).

Test Data:
- Rishi S Nayak: 2026-03-24
- Gautham Kumar Reddy: 2026-03-23
- Madhumithaa G K: 2026-03-25
- Harshini V M: 2026-03-26
- Jona Delcy C A: 2026-03-27
"""

import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

@pytest.fixture(scope="module")
def auth_session():
    """Create authenticated session"""
    session = requests.Session()
    response = session.post(f"{BASE_URL}/api/login", json={
        "username": "admin",
        "password": "admin"
    })
    assert response.status_code == 200, f"Login failed: {response.text}"
    return session


class TestDataStatus:
    """Verify data counts and ISO date format"""
    
    def test_status_counts(self, auth_session):
        """GET /api/status: 5 naukri, 5 pipeline, 5 registered"""
        response = auth_session.get(f"{BASE_URL}/api/status")
        assert response.status_code == 200
        data = response.json()
        assert data["naukri_count"] == 5, f"Expected 5 naukri, got {data['naukri_count']}"
        assert data["pipeline_count"] == 5, f"Expected 5 pipeline, got {data['pipeline_count']}"
        assert data["registered_count"] == 5, f"Expected 5 registered, got {data['registered_count']}"
    
    def test_dates_in_iso_format(self, auth_session):
        """Verify dates stored in ISO format YYYY-MM-DD"""
        job_role = "AI & ML Engineer - C++ / Java Developer"
        response = auth_session.get(f"{BASE_URL}/api/role", params={"jobRole": job_role})
        assert response.status_code == 200
        data = response.json()
        
        # Expected dates in ISO format
        expected_dates = {
            "Rishi S Nayak": "2026-03-24",
            "Gautham Kumar Reddy": "2026-03-23",
            "Madhumithaa G K": "2026-03-25",
            "Harshini V M": "2026-03-26",
            "Jona Delcy C A": "2026-03-27"
        }
        
        for applicant in data["data"]:
            name = applicant["name"]
            date = applicant["date_of_application"]
            if name in expected_dates:
                assert date == expected_dates[name], f"{name}: expected {expected_dates[name]}, got {date}"
                # Verify ISO format (YYYY-MM-DD)
                assert len(date) == 10, f"Date {date} not in YYYY-MM-DD format"
                assert date[4] == "-" and date[7] == "-", f"Date {date} not in YYYY-MM-DD format"


class TestSummaryDateFiltering:
    """Test /api/summary endpoint date filtering"""
    
    def test_summary_no_filter_returns_all(self, auth_session):
        """GET /api/summary without date filter: returns all 5"""
        response = auth_session.get(f"{BASE_URL}/api/summary")
        assert response.status_code == 200
        data = response.json()
        assert len(data["data"]) == 1  # One job role
        assert data["data"][0]["total_applicants"] == 5
        assert data["total_registered"] == 5
    
    def test_summary_date_range_23_to_25(self, auth_session):
        """GET /api/summary with startDate=2026-03-23&endDate=2026-03-25: returns 3 applicants"""
        response = auth_session.get(f"{BASE_URL}/api/summary", params={
            "startDate": "2026-03-23",
            "endDate": "2026-03-25"
        })
        assert response.status_code == 200
        data = response.json()
        assert len(data["data"]) == 1
        assert data["data"][0]["total_applicants"] == 3, f"Expected 3, got {data['data'][0]['total_applicants']}"
        assert data["total_registered"] == 3
    
    def test_summary_single_date_24(self, auth_session):
        """GET /api/summary with startDate=2026-03-24&endDate=2026-03-24: returns 1 (Rishi only)"""
        response = auth_session.get(f"{BASE_URL}/api/summary", params={
            "startDate": "2026-03-24",
            "endDate": "2026-03-24"
        })
        assert response.status_code == 200
        data = response.json()
        assert len(data["data"]) == 1
        assert data["data"][0]["total_applicants"] == 1, f"Expected 1, got {data['data'][0]['total_applicants']}"
        assert data["total_registered"] == 1
    
    def test_summary_no_results_2020(self, auth_session):
        """GET /api/summary with startDate=2020-01-01&endDate=2020-12-31: returns 0 results"""
        response = auth_session.get(f"{BASE_URL}/api/summary", params={
            "startDate": "2020-01-01",
            "endDate": "2020-12-31"
        })
        assert response.status_code == 200
        data = response.json()
        assert len(data["data"]) == 0, f"Expected 0 results, got {len(data['data'])}"
        assert data["total_registered"] == 0


class TestRoleDateFiltering:
    """Test /api/role endpoint date filtering"""
    
    def test_role_no_filter_returns_all(self, auth_session):
        """GET /api/role without date: returns all 5"""
        job_role = "AI & ML Engineer - C++ / Java Developer"
        response = auth_session.get(f"{BASE_URL}/api/role", params={"jobRole": job_role})
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 5, f"Expected 5, got {data['total']}"
        assert len(data["data"]) == 5
    
    def test_role_date_range_24_to_26(self, auth_session):
        """GET /api/role with startDate=2026-03-24&endDate=2026-03-26: returns 3 applicants"""
        job_role = "AI & ML Engineer - C++ / Java Developer"
        response = auth_session.get(f"{BASE_URL}/api/role", params={
            "jobRole": job_role,
            "startDate": "2026-03-24",
            "endDate": "2026-03-26"
        })
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 3, f"Expected 3, got {data['total']}"
        
        # Verify correct applicants returned
        names = [a["name"] for a in data["data"]]
        assert "Rishi S Nayak" in names, "Rishi (2026-03-24) should be included"
        assert "Madhumithaa G K" in names, "Madhumithaa (2026-03-25) should be included"
        assert "Harshini V M" in names, "Harshini (2026-03-26) should be included"
        assert "Gautham Kumar Reddy" not in names, "Gautham (2026-03-23) should NOT be included"
        assert "Jona Delcy C A" not in names, "Jona (2026-03-27) should NOT be included"
    
    def test_role_single_date_25(self, auth_session):
        """GET /api/role with startDate=2026-03-25&endDate=2026-03-25: returns 1 (Madhumithaa only)"""
        job_role = "AI & ML Engineer - C++ / Java Developer"
        response = auth_session.get(f"{BASE_URL}/api/role", params={
            "jobRole": job_role,
            "startDate": "2026-03-25",
            "endDate": "2026-03-25"
        })
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1, f"Expected 1, got {data['total']}"
        assert data["data"][0]["name"] == "Madhumithaa G K"


class TestReprocessEndpoint:
    """Test /api/reprocess endpoint for date re-normalization"""
    
    def test_reprocess_normalizes_dates(self, auth_session):
        """POST /api/reprocess: correctly re-normalizes dates in existing data"""
        response = auth_session.post(f"{BASE_URL}/api/reprocess")
        assert response.status_code == 200
        data = response.json()
        assert data["success"] == True
        assert "Reprocessing complete" in data["message"]
        assert data["naukri_count"] == 5
        assert data["pipeline_count"] == 5
        assert data["registered_after"] == 5
        
        # Verify dates are still in ISO format after reprocess
        job_role = "AI & ML Engineer - C++ / Java Developer"
        role_response = auth_session.get(f"{BASE_URL}/api/role", params={"jobRole": job_role})
        assert role_response.status_code == 200
        role_data = role_response.json()
        
        for applicant in role_data["data"]:
            date = applicant["date_of_application"]
            # Verify ISO format
            assert len(date) == 10, f"Date {date} not in YYYY-MM-DD format after reprocess"
            assert date[4] == "-" and date[7] == "-", f"Date {date} not in YYYY-MM-DD format"
