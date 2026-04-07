import requests
import sys
import json
from datetime import datetime
import io

class RecruitmentAPITester:
    def __init__(self, base_url="https://hire-analytics-4.preview.emergentagent.com"):
        self.base_url = base_url
        self.session = requests.Session()
        self.tests_run = 0
        self.tests_passed = 0
        self.admin_credentials = {
            "email": "admin@recruitment.com",
            "password": "Admin123!"
        }

    def run_test(self, name, method, endpoint, expected_status, data=None, files=None):
        """Run a single API test"""
        url = f"{self.base_url}/api/{endpoint}"
        headers = {'Content-Type': 'application/json'} if not files else {}

        self.tests_run += 1
        print(f"\n🔍 Testing {name}...")
        
        try:
            if method == 'GET':
                response = self.session.get(url, headers=headers)
            elif method == 'POST':
                if files:
                    response = self.session.post(url, files=files)
                else:
                    response = self.session.post(url, json=data, headers=headers)
            elif method == 'DELETE':
                response = self.session.delete(url, headers=headers)

            success = response.status_code == expected_status
            if success:
                self.tests_passed += 1
                print(f"✅ Passed - Status: {response.status_code}")
                try:
                    return success, response.json() if response.content else {}
                except:
                    return success, {}
            else:
                print(f"❌ Failed - Expected {expected_status}, got {response.status_code}")
                try:
                    error_detail = response.json()
                    print(f"   Error: {error_detail}")
                except:
                    print(f"   Response: {response.text}")
                return False, {}

        except Exception as e:
            print(f"❌ Failed - Error: {str(e)}")
            return False, {}

    def test_health_check(self):
        """Test API health check"""
        success, response = self.run_test(
            "Health Check",
            "GET",
            "",
            200
        )
        return success

    def test_admin_login(self):
        """Test admin login"""
        success, response = self.run_test(
            "Admin Login",
            "POST",
            "auth/login",
            200,
            data=self.admin_credentials
        )
        if success:
            print(f"   Logged in as: {response.get('name')} ({response.get('role')})")
        return success

    def test_user_registration(self):
        """Test user registration"""
        test_user = {
            "name": f"Test User {datetime.now().strftime('%H%M%S')}",
            "email": f"test_{datetime.now().strftime('%H%M%S')}@test.com",
            "password": "TestPass123!"
        }
        
        success, response = self.run_test(
            "User Registration",
            "POST",
            "auth/register",
            200,
            data=test_user
        )
        if success:
            print(f"   Registered user: {response.get('name')}")
        return success

    def test_get_current_user(self):
        """Test get current user endpoint"""
        success, response = self.run_test(
            "Get Current User",
            "GET",
            "auth/me",
            200
        )
        if success:
            print(f"   Current user: {response.get('name')} ({response.get('email')})")
        return success

    def test_logout(self):
        """Test logout"""
        success, response = self.run_test(
            "Logout",
            "POST",
            "auth/logout",
            200
        )
        return success

    def test_analytics_empty(self):
        """Test analytics endpoint with no data"""
        # Login first
        self.test_admin_login()
        
        success, response = self.run_test(
            "Analytics (Empty State)",
            "GET",
            "analytics",
            200
        )
        if success:
            print(f"   Total applies: {response.get('total_naukri_applies', 0)}")
            print(f"   Job roles: {len(response.get('job_roles', []))}")
        return success

    def test_upload_naukri_no_file(self):
        """Test Naukri upload without file"""
        success, response = self.run_test(
            "Naukri Upload (No File)",
            "POST",
            "upload/naukri",
            422  # FastAPI validation error for missing file
        )
        return success

    def test_upload_pipeline_no_file(self):
        """Test Pipeline upload without file"""
        success, response = self.run_test(
            "Pipeline Upload (No File)",
            "POST",
            "upload/pipeline",
            422  # FastAPI validation error for missing file
        )
        return success

    def test_process_data_empty(self):
        """Test data processing with no data"""
        success, response = self.run_test(
            "Process Data (Empty)",
            "POST",
            "process-data",
            200
        )
        if success:
            print(f"   Processed: {response.get('total_processed', 0)} records")
        return success

    def test_download_analytics_no_data(self):
        """Test CSV download with no data"""
        success, response = self.run_test(
            "Download Analytics (No Data)",
            "GET",
            "analytics/download",
            404  # Should return 404 when no data
        )
        return success

    def test_upload_naukri_with_sample_data(self):
        """Test Naukri upload with sample CSV data"""
        # Create sample CSV data
        csv_data = """Name,Email,Phone Number,Job Role
John Doe,john@example.com,9876543210,Software Engineer
Jane Smith,jane@example.com,9876543211,Data Analyst
Bob Johnson,bob@example.com,9876543212,Product Manager"""
        
        files = {
            'file': ('test_naukri.csv', io.StringIO(csv_data), 'text/csv')
        }
        
        success, response = self.run_test(
            "Naukri Upload (Sample Data)",
            "POST",
            "upload/naukri",
            200,
            files=files
        )
        if success:
            print(f"   Valid records: {response.get('valid_records', 0)}")
            print(f"   Total records: {response.get('total_records', 0)}")
        return success

    def test_upload_pipeline_with_sample_data(self):
        """Test Pipeline upload with sample CSV data"""
        # Create sample CSV data
        csv_data = """Name,Email,Phone Number,Job Role,Status
John Doe,john@example.com,9876543210,Software Engineer,shortlisted
Jane Smith,jane@example.com,9876543211,Data Analyst,rejected
Bob Johnson,bob@example.com,9876543212,Product Manager,scheduled"""
        
        files = {
            'file': ('test_pipeline.csv', io.StringIO(csv_data), 'text/csv')
        }
        
        success, response = self.run_test(
            "Pipeline Upload (Sample Data)",
            "POST",
            "upload/pipeline",
            200,
            files=files
        )
        if success:
            print(f"   Valid records: {response.get('valid_records', 0)}")
            print(f"   Total records: {response.get('total_records', 0)}")
        return success

    def test_process_data_with_data(self):
        """Test data processing with uploaded data"""
        success, response = self.run_test(
            "Process Data (With Data)",
            "POST",
            "process-data",
            200
        )
        if success:
            print(f"   Processed: {response.get('total_processed', 0)} records")
            print(f"   Registered: {response.get('registered', 0)}")
            print(f"   Not Registered: {response.get('not_registered', 0)}")
        return success

    def test_analytics_with_data(self):
        """Test analytics endpoint with processed data"""
        success, response = self.run_test(
            "Analytics (With Data)",
            "GET",
            "analytics",
            200
        )
        if success:
            print(f"   Total applies: {response.get('total_naukri_applies', 0)}")
            print(f"   Registered: {response.get('registered', 0)}")
            print(f"   Shortlisted: {response.get('shortlisted', 0)}")
            print(f"   Job roles: {response.get('job_roles', [])}")
        return success

    def test_analytics_with_filter(self):
        """Test analytics endpoint with job role filter"""
        success, response = self.run_test(
            "Analytics (Filtered)",
            "GET",
            "analytics?job_role=Software Engineer",
            200
        )
        if success:
            print(f"   Filtered applies: {response.get('total_naukri_applies', 0)}")
        return success

    def test_download_analytics_with_data(self):
        """Test CSV download with data"""
        success, response = self.run_test(
            "Download Analytics (With Data)",
            "GET",
            "analytics/download",
            200
        )
        return success

def main():
    print("🚀 Starting Recruitment Analytics API Tests")
    print("=" * 50)
    
    tester = RecruitmentAPITester()
    
    # Test sequence
    tests = [
        tester.test_health_check,
        tester.test_admin_login,
        tester.test_user_registration,
        tester.test_get_current_user,
        tester.test_analytics_empty,
        tester.test_upload_naukri_no_file,
        tester.test_upload_pipeline_no_file,
        tester.test_process_data_empty,
        tester.test_download_analytics_no_data,
        tester.test_upload_naukri_with_sample_data,
        tester.test_upload_pipeline_with_sample_data,
        tester.test_process_data_with_data,
        tester.test_analytics_with_data,
        tester.test_analytics_with_filter,
        tester.test_download_analytics_with_data,
        tester.test_logout,
    ]
    
    # Run all tests
    for test in tests:
        try:
            test()
        except Exception as e:
            print(f"❌ Test failed with exception: {str(e)}")
    
    # Print results
    print("\n" + "=" * 50)
    print(f"📊 Tests completed: {tester.tests_passed}/{tester.tests_run}")
    success_rate = (tester.tests_passed / tester.tests_run * 100) if tester.tests_run > 0 else 0
    print(f"📈 Success rate: {success_rate:.1f}%")
    
    if success_rate >= 80:
        print("🎉 Backend tests mostly successful!")
        return 0
    else:
        print("⚠️  Backend has significant issues")
        return 1

if __name__ == "__main__":
    sys.exit(main())