"""
Iteration 38 — Backend tests for:
  - Rounds CRUD (active/inactive flag, uniqueness, in_use guard, rename cascade, restore)
  - College Schedules CRUD (HR drives) + Public college-form endpoints
"""
import os
import time
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://score-round-staging.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"
PUB = f"{BASE_URL}/api/pub"


@pytest.fixture(scope="session")
def admin_session():
    s = requests.Session()
    r = s.post(f"{API}/login", json={"username": "Admin User", "password": "Admin User"}, timeout=20)
    assert r.status_code == 200, f"Login failed: {r.status_code} {r.text}"
    return s


# --------- ROUNDS ---------
class TestRounds:
    def test_list_active_rounds_default(self, admin_session):
        r = admin_session.get(f"{API}/bb/rounds", timeout=20)
        assert r.status_code == 200
        data = r.json()
        assert "rounds" in data
        for rd in data["rounds"]:
            # active by default
            assert rd.get("active", True) is True

    def test_list_with_include_inactive(self, admin_session):
        r = admin_session.get(f"{API}/bb/rounds?includeInactive=true", timeout=20)
        assert r.status_code == 200
        assert "rounds" in r.json()

    def test_full_round_lifecycle_create_update_delete_restore(self, admin_session):
        ts = int(time.time())
        name = f"TEST_Round_{ts}"

        # CREATE
        r = admin_session.post(f"{API}/bb/rounds", json={"name": name}, timeout=20)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body.get("success") is True
        assert body.get("active") is True
        assert body.get("order") == 0
        rid = body["id"]

        # GET verifies persistence
        r = admin_session.get(f"{API}/bb/rounds", timeout=20)
        names = [x["name"] for x in r.json()["rounds"]]
        assert name in names

        # DUPLICATE (case-insensitive) → 409
        r = admin_session.post(f"{API}/bb/rounds", json={"name": name.lower()}, timeout=20)
        assert r.status_code == 409
        assert "already exists" in r.json().get("detail", "").lower()

        # UPDATE rename
        new_name = f"{name}_renamed"
        r = admin_session.put(f"{API}/bb/rounds/{rid}", json={"name": new_name}, timeout=20)
        assert r.status_code == 200, r.text

        r = admin_session.get(f"{API}/bb/rounds", timeout=20)
        names = [x["name"] for x in r.json()["rounds"]]
        assert new_name in names and name not in names

        # LOGICAL DELETE (no ?hard) → in_use field returned
        r = admin_session.delete(f"{API}/bb/rounds/{rid}", timeout=20)
        assert r.status_code == 200
        body = r.json()
        assert body.get("deleted") == "logical"
        assert "in_use" in body

        # active list excludes
        r = admin_session.get(f"{API}/bb/rounds", timeout=20)
        names = [x["name"] for x in r.json()["rounds"]]
        assert new_name not in names

        # includeInactive shows
        r = admin_session.get(f"{API}/bb/rounds?includeInactive=true", timeout=20)
        rounds = r.json()["rounds"]
        match = [x for x in rounds if x["id"] == rid]
        assert len(match) == 1 and match[0].get("active") is False

        # RESTORE
        r = admin_session.post(f"{API}/bb/rounds/{rid}/restore", timeout=20)
        assert r.status_code == 200

        # HARD delete (not in use) — should succeed
        r = admin_session.delete(f"{API}/bb/rounds/{rid}?hard=true", timeout=20)
        assert r.status_code == 200
        assert r.json().get("deleted") == "hard"

    def test_hard_delete_blocked_when_round_in_use(self, admin_session):
        """If we can find an existing in-use round (referenced by score_sheet),
        attempt hard delete and expect 409. Otherwise, skip."""
        r = admin_session.get(f"{API}/bb/rounds", timeout=20)
        assert r.status_code == 200
        rounds = r.json()["rounds"]
        # Try each — first one that returns in_use=True on logical delete is our candidate
        # Safer approach: try hard delete on a known seeded round name
        candidates = [x for x in rounds if x.get("name", "").lower() in ("hr round", "technical round", "mr round", "managerial round")]
        if not candidates:
            pytest.skip("No likely-in-use round found in this DB to validate hard-delete block")
        # Try hard delete — expect 409 OR 200 (if not actually used). We accept either,
        # but if 200, restore by recreating.
        rid = candidates[0]["id"]
        rname = candidates[0]["name"]
        r = admin_session.delete(f"{API}/bb/rounds/{rid}?hard=true", timeout=20)
        if r.status_code == 200:
            # not in use — re-create it for cleanliness
            admin_session.post(f"{API}/bb/rounds", json={"name": rname}, timeout=20)
            pytest.skip(f"Round {rname} was not in use; hard delete succeeded")
        assert r.status_code == 409
        assert "Cannot hard-delete" in r.json().get("detail", "") or "referenced" in r.json().get("detail", "").lower()


# --------- COLLEGE SCHEDULES ---------
class TestCollegeSchedules:
    @pytest.fixture(scope="class")
    def created_ids(self):
        return []

    def test_list_schedules(self, admin_session):
        r = admin_session.get(f"{API}/bb/college-schedules", timeout=20)
        assert r.status_code == 200
        assert "schedules" in r.json()

    def test_create_schedule_lifecycle(self, admin_session, created_ids):
        ts = int(time.time())
        college = f"TEST_College_{ts}"
        role = "TEST_AI_Role"
        payload = {
            "college_name": college,
            "job_role": role,
            "schedule_date": "2026-03-15",
            "schedule_time": "10:30",
        }
        r = admin_session.post(f"{API}/bb/college-schedules", json=payload, timeout=20)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["success"] is True
        sched = body["schedule"]
        assert sched["college_name"] == college
        assert sched["job_role"] == role
        assert sched["schedule_time"] == "10:30:00"  # auto-suffix :00
        sched_id = sched["id"]
        created_ids.append(sched_id)

        # DUPLICATE (case-insensitive) → 409
        dup_payload = dict(payload, college_name=college.upper(), job_role=role.lower())
        r = admin_session.post(f"{API}/bb/college-schedules", json=dup_payload, timeout=20)
        assert r.status_code == 409

        # UPDATE
        r = admin_session.put(
            f"{API}/bb/college-schedules/{sched_id}",
            json={"schedule_time": "11:00", "notes": "Updated"},
            timeout=20,
        )
        assert r.status_code == 200

        # GET verifies update
        r = admin_session.get(f"{API}/bb/college-schedules", timeout=20)
        match = [x for x in r.json()["schedules"] if x["id"] == sched_id]
        assert len(match) == 1
        assert match[0]["schedule_time"] == "11:00:00"
        assert match[0]["notes"] == "Updated"

        # PUT block duplicate on rename — create another and try renaming to collide
        ts2 = ts + 1
        college2 = f"TEST_College_{ts2}"
        r2 = admin_session.post(f"{API}/bb/college-schedules", json={
            "college_name": college2, "job_role": role,
            "schedule_date": "2026-03-16", "schedule_time": "12:00",
        }, timeout=20)
        assert r2.status_code == 200
        sched2 = r2.json()["schedule"]
        created_ids.append(sched2["id"])
        # rename college2 -> college (collision on (college, role))
        r3 = admin_session.put(f"{API}/bb/college-schedules/{sched2['id']}",
                               json={"college_name": college}, timeout=20)
        assert r3.status_code == 409

        # LOGICAL DELETE
        r = admin_session.delete(f"{API}/bb/college-schedules/{sched_id}", timeout=20)
        assert r.status_code == 200
        assert r.json().get("deleted") == "logical"

        # Active list excludes
        r = admin_session.get(f"{API}/bb/college-schedules", timeout=20)
        ids = [x["id"] for x in r.json()["schedules"]]
        assert sched_id not in ids

        # includeInactive shows
        r = admin_session.get(f"{API}/bb/college-schedules?includeInactive=true", timeout=20)
        all_ids = [x["id"] for x in r.json()["schedules"]]
        assert sched_id in all_ids

        # RESTORE
        r = admin_session.post(f"{API}/bb/college-schedules/{sched_id}/restore", timeout=20)
        assert r.status_code == 200

        # Cleanup: hard delete both
        for sid in created_ids:
            admin_session.delete(f"{API}/bb/college-schedules/{sid}?hard=true", timeout=20)


# --------- PUBLIC ENDPOINTS ---------
class TestPublicCollegeForm:
    @pytest.fixture(scope="class")
    def seeded_schedule(self, admin_session):
        """Create a fresh isolated schedule for public-flow validation."""
        ts = int(time.time())
        college = f"TESTPUB_College_{ts}"
        role = f"TESTPUB_Role_{ts}"
        r = admin_session.post(f"{API}/bb/college-schedules", json={
            "college_name": college, "job_role": role,
            "schedule_date": "2026-04-20", "schedule_time": "14:30",
        }, timeout=20)
        assert r.status_code == 200
        sched_id = r.json()["schedule"]["id"]
        yield {"college": college, "role": role, "id": sched_id}
        admin_session.delete(f"{API}/bb/college-schedules/{sched_id}?hard=true", timeout=20)

    def test_pub_colleges_list(self, seeded_schedule):
        r = requests.get(f"{PUB}/college-form/colleges", timeout=20)
        assert r.status_code == 200
        cols = r.json()["colleges"]
        assert seeded_schedule["college"] in cols

    def test_pub_roles_filtered_by_college(self, seeded_schedule):
        r = requests.get(f"{PUB}/college-form/roles", params={"college": seeded_schedule["college"]}, timeout=20)
        assert r.status_code == 200
        roles = r.json()["roles"]
        assert seeded_schedule["role"] in roles
        # Roles for an unrelated college should not include our seeded role
        r2 = requests.get(f"{PUB}/college-form/roles", params={"college": "NonExistent_xyz_12345"}, timeout=20)
        assert r2.status_code == 200
        assert seeded_schedule["role"] not in r2.json()["roles"]

    def test_pub_register_success(self, seeded_schedule):
        ts = int(time.time())
        email = f"test_pub_reg_{ts}@example.com"
        payload = {
            "full_name": "Test Reg User",
            "email": email,
            "phone": "9999999991",
            "age": 22,
            "gender": "Male",
            "college": seeded_schedule["college"],
            "job_role": seeded_schedule["role"],
            "degree": "BTech",
            "course": "CS",
            "year_of_graduation": 2025,
            "current_location_state": "TN",
            "preferred_location_city": "Chennai",
        }
        r = requests.post(f"{PUB}/college-form/register", json=payload, timeout=30)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["success"] is True
        assert body["schedule_date"] == "2026-04-20"
        assert body["schedule_time"] == "14:30:00"
        assert body["college"] == seeded_schedule["college"]
        assert body["job_role"] == seeded_schedule["role"]

    def test_pub_register_invalid_combo_422(self, seeded_schedule):
        payload = {
            "full_name": "Bad Combo",
            "email": f"bad_combo_{int(time.time())}@example.com",
            "phone": "9999999992",
            "college": seeded_schedule["college"],
            "job_role": "ZZ_Nonexistent_Role_xyz",
        }
        r = requests.post(f"{PUB}/college-form/register", json=payload, timeout=30)
        assert r.status_code == 422
        assert "No interview schedule" in r.json().get("detail", "")
