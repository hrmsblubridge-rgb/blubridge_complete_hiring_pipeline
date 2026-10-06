"""
Iteration 10: Testing Matching Logic Fix
- Phone normalization: float→int conversion, leading zero stripping
- Re-normalization during matching
- /api/reprocess endpoint
- /api/debug/matching endpoint
- Edge cases: uppercase emails, +91 prefix phones, phone-only matches, email-only matches
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


class TestMatchingLogicFix:
    """Tests for the matching/normalization fix"""
    
    def test_login_success(self, auth_session):
        """Verify login works with admin/admin"""
        response = auth_session.get(f"{BASE_URL}/api/auth/check")
        assert response.status_code == 200
        data = response.json()
        assert data["authenticated"] == True
        assert data["username"] == "admin"
        print("✓ Login with admin/admin successful")
    
    def test_status_shows_all_8_registered(self, auth_session):
        """GET /api/status shows correct counts - all 8 should be registered"""
        response = auth_session.get(f"{BASE_URL}/api/status")
        assert response.status_code == 200
        data = response.json()
        assert data["naukri_count"] == 8, f"Expected 8 naukri, got {data['naukri_count']}"
        assert data["pipeline_count"] == 8, f"Expected 8 pipeline, got {data['pipeline_count']}"
        assert data["registered_count"] == 8, f"Expected 8 registered, got {data['registered_count']}"
        print(f"✓ Status: naukri={data['naukri_count']}, pipeline={data['pipeline_count']}, registered={data['registered_count']}")
    
    def test_debug_matching_all_8_matched(self, auth_session):
        """GET /api/debug/matching shows all 8 naukri records matched to pipeline (0 unmatched)"""
        response = auth_session.get(f"{BASE_URL}/api/debug/matching")
        assert response.status_code == 200
        data = response.json()
        assert data["total_naukri"] == 8
        assert data["total_pipeline"] == 8
        assert data["matched"] == 8, f"Expected 8 matched, got {data['matched']}"
        assert data["unmatched"] == 0, f"Expected 0 unmatched, got {data['unmatched']}"
        print(f"✓ Debug matching: {data['matched']} matched, {data['unmatched']} unmatched")
    
    def test_debug_matching_details(self, auth_session):
        """Verify matching details for edge cases"""
        response = auth_session.get(f"{BASE_URL}/api/debug/matching")
        assert response.status_code == 200
        data = response.json()
        
        # Build lookup by name
        details_by_name = {d["naukri_name"]: d for d in data["details"]}
        
        # Alice: UPPERCASE email (ALICE@test.com → alice@test.com)
        alice = details_by_name.get("Alice Johnson")
        assert alice is not None, "Alice Johnson not found"
        assert alice["matched"] == True, "Alice should be matched"
        assert alice["naukri_email"] == "alice@test.com", f"Alice email not normalized: {alice['naukri_email']}"
        print(f"✓ Alice (uppercase email): matched via {alice['match_type']}")
        
        # Bob: +91 prefix phone
        bob = details_by_name.get("Bob Smith")
        assert bob is not None, "Bob Smith not found"
        assert bob["matched"] == True, "Bob should be matched"
        print(f"✓ Bob (+91 prefix phone): matched via {bob['match_type']}")
        
        # Carol: mixed case email
        carol = details_by_name.get("Carol Davis")
        assert carol is not None, "Carol Davis not found"
        assert carol["matched"] == True, "Carol should be matched"
        print(f"✓ Carol (mixed case email): matched via {carol['match_type']}")
        
        # Dave: 91- prefix phone
        dave = details_by_name.get("Dave Wilson")
        assert dave is not None, "Dave Wilson not found"
        assert dave["matched"] == True, "Dave should be matched"
        print(f"✓ Dave (91- prefix phone): matched via {dave['match_type']}")
        
        # Eve: phone-only match (no email)
        eve = details_by_name.get("Eve Brown")
        assert eve is not None, "Eve Brown not found"
        assert eve["matched"] == True, "Eve should be matched"
        assert eve["match_type"] == "phone", f"Eve should match by phone, got {eve['match_type']}"
        print(f"✓ Eve (phone-only): matched via {eve['match_type']}")
        
        # Frank: email-only match (no phone)
        frank = details_by_name.get("Frank Lee")
        assert frank is not None, "Frank Lee not found"
        assert frank["matched"] == True, "Frank should be matched"
        assert frank["match_type"] == "email", f"Frank should match by email, got {frank['match_type']}"
        print(f"✓ Frank (email-only): matched via {frank['match_type']}")
    
    def test_dashboard_counts_correct(self, auth_session):
        """GET /api/dashboard-counts shows correct subcategories"""
        response = auth_session.get(f"{BASE_URL}/api/dashboard-counts")
        assert response.status_code == 200
        data = response.json()
        
        assert data["total_applies"] == 8
        assert data["registered"] == 8
        assert data["unregistered"] == 0
        assert data["shortlisted"] == 1, f"Expected shortlisted=1, got {data['shortlisted']}"
        assert data["rejected"] == 2, f"Expected rejected=2, got {data['rejected']}"
        assert data["scheduled"] == 6, f"Expected scheduled=6, got {data['scheduled']}"
        assert data["attended"] == 4, f"Expected attended=4, got {data['attended']}"
        print(f"✓ Dashboard counts: shortlisted={data['shortlisted']}, rejected={data['rejected']}, scheduled={data['scheduled']}, attended={data['attended']}")
    
    def test_reprocess_endpoint(self, auth_session):
        """POST /api/reprocess re-normalizes and rebuilds matching correctly"""
        response = auth_session.post(f"{BASE_URL}/api/reprocess")
        assert response.status_code == 200
        data = response.json()
        
        assert data["success"] == True
        assert "Reprocessing complete" in data["message"]
        assert data["naukri_count"] == 8
        assert data["pipeline_count"] == 8
        assert data["registered_after"] == 8, f"Expected 8 registered after reprocess, got {data['registered_after']}"
        print(f"✓ Reprocess: registered_before={data['registered_before']}, registered_after={data['registered_after']}, change={data['change']}")
    
    def test_role_software_developer(self, auth_session):
        """GET /api/role?jobRole=Software Developer returns 5 applicants with correct status"""
        response = auth_session.get(f"{BASE_URL}/api/role", params={"jobRole": "Software Developer"})
        assert response.status_code == 200
        data = response.json()
        
        assert data["total"] == 5, f"Expected 5 Software Developer applicants, got {data['total']}"
        
        # Verify status distribution
        statuses = [a["status"] for a in data["data"]]
        assert "Rejected" in statuses, "Should have Rejected status"
        assert "Attended" in statuses, "Should have Attended status"
        assert "Interview Scheduled" in statuses, "Should have Interview Scheduled status"
        print(f"✓ Software Developer: {data['total']} applicants, statuses: {set(statuses)}")
    
    def test_role_data_analyst(self, auth_session):
        """GET /api/role?jobRole=Data Analyst returns 3 applicants with correct status"""
        response = auth_session.get(f"{BASE_URL}/api/role", params={"jobRole": "Data Analyst"})
        assert response.status_code == 200
        data = response.json()
        
        assert data["total"] == 3, f"Expected 3 Data Analyst applicants, got {data['total']}"
        
        # Verify status distribution
        statuses = [a["status"] for a in data["data"]]
        assert "Shortlisted" in statuses, "Should have Shortlisted status"
        assert "Rejected" in statuses, "Should have Rejected status"
        assert "Interview Scheduled" in statuses, "Should have Interview Scheduled status"
        print(f"✓ Data Analyst: {data['total']} applicants, statuses: {set(statuses)}")
    
    def test_summary_funnel_stats(self, auth_session):
        """GET /api/summary returns correct funnel stats"""
        response = auth_session.get(f"{BASE_URL}/api/summary")
        assert response.status_code == 200
        data = response.json()
        
        assert data["total_registered"] == 8, f"Expected total_registered=8, got {data['total_registered']}"
        assert len(data["data"]) == 2, f"Expected 2 job roles, got {len(data['data'])}"
        
        # Verify job roles
        roles = {r["job_role"]: r for r in data["data"]}
        assert "Software Developer" in roles
        assert "Data Analyst" in roles
        
        # Verify Software Developer stats
        sd = roles["Software Developer"]
        assert sd["total_applicants"] == 5
        
        # Verify Data Analyst stats
        da = roles["Data Analyst"]
        assert da["total_applicants"] == 3
        assert da["shortlisted"] == 1, f"Expected Data Analyst shortlisted=1, got {da['shortlisted']}"
        
        print(f"✓ Summary: total_registered={data['total_registered']}, roles={list(roles.keys())}")
    
    def test_job_roles_endpoint(self, auth_session):
        """GET /api/job-roles returns unique roles with counts"""
        response = auth_session.get(f"{BASE_URL}/api/job-roles")
        assert response.status_code == 200
        data = response.json()
        
        assert "job_roles" in data
        roles = {r["job_role"]: r["count"] for r in data["job_roles"]}
        assert roles.get("Software Developer") == 5
        assert roles.get("Data Analyst") == 3
        print(f"✓ Job roles: {roles}")


class TestPhoneNormalization:
    """Tests specifically for phone normalization edge cases"""
    
    def test_normalize_phone_float_conversion(self, auth_session):
        """Verify float phone numbers are correctly converted (9876543210.0 → 9876543210)"""
        response = auth_session.get(f"{BASE_URL}/api/debug/matching")
        assert response.status_code == 200
        data = response.json()
        
        # All phone numbers should be clean integers without decimal points
        for detail in data["details"]:
            phone = detail["naukri_phone"]
            if phone:
                assert "." not in phone, f"Phone should not have decimal: {phone}"
                assert phone.isdigit() or phone == "", f"Phone should be digits only: {phone}"
        print("✓ All phone numbers correctly normalized (no float artifacts)")
    
    def test_normalize_phone_country_code_stripped(self, auth_session):
        """Verify +91 and 91- prefixes are stripped"""
        response = auth_session.get(f"{BASE_URL}/api/debug/matching")
        assert response.status_code == 200
        data = response.json()
        
        for detail in data["details"]:
            phone = detail["naukri_phone"]
            if phone:
                assert not phone.startswith("91"), f"Phone should not start with 91: {phone}"
                assert len(phone) <= 10, f"Phone should be max 10 digits: {phone}"
        print("✓ All phone numbers have country codes stripped")
    
    def test_normalize_phone_leading_zeros_stripped(self, auth_session):
        """Verify leading zeros are stripped (09876543212 → 9876543212)"""
        response = auth_session.get(f"{BASE_URL}/api/debug/matching")
        assert response.status_code == 200
        data = response.json()
        
        for detail in data["details"]:
            phone = detail["naukri_phone"]
            if phone and len(phone) > 1:
                # Leading zeros should be stripped for phones > 10 digits
                assert not (phone.startswith("0") and len(phone) > 10), f"Phone has leading zero: {phone}"
        print("✓ Leading zeros correctly handled")


class TestEmailNormalization:
    """Tests specifically for email normalization edge cases"""
    
    def test_normalize_email_lowercase(self, auth_session):
        """Verify uppercase emails are lowercased"""
        response = auth_session.get(f"{BASE_URL}/api/debug/matching")
        assert response.status_code == 200
        data = response.json()
        
        for detail in data["details"]:
            email = detail["naukri_email"]
            if email:
                assert email == email.lower(), f"Email should be lowercase: {email}"
        print("✓ All emails correctly lowercased")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
