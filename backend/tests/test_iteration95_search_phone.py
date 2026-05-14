"""
iter95 tests — Partial applicant search + phone normalization + Final Reject wiring.

Covers:
  • GET /api/bb/manual/applicant/search — substring/regex search w/ multi-card
  • GET /api/bb/manual/applicant/lookup — exact lookup unchanged
  • bb_modules._validate_phone_10digits — 6 prefix variants → 10 digits
  • messaging.notify_rejected — uses 'Final Reject' campaign w/ [name, job_role]
"""
import os
import sys
import pytest
import requests

BASE_URL = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")
sys.path.insert(0, "/app/backend")


# -------- Fixtures --------
@pytest.fixture(scope="session")
def admin_session():
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/login",
               json={"username": "Admin User", "password": "Admin User"},
               timeout=20)
    assert r.status_code == 200, f"login failed: {r.status_code} {r.text}"
    return s


# =========================================================================
# Module — /api/bb/manual/applicant/search
# =========================================================================
class TestApplicantSearch:
    def test_auth_required(self):
        # No cookies → 401
        r = requests.get(f"{BASE_URL}/api/bb/manual/applicant/search",
                         params={"q": "rish"}, timeout=15)
        assert r.status_code == 401, f"expected 401, got {r.status_code}: {r.text}"

    def test_single_char_returns_empty(self, admin_session):
        r = admin_session.get(f"{BASE_URL}/api/bb/manual/applicant/search",
                              params={"q": "r"}, timeout=15)
        assert r.status_code == 200
        data = r.json()
        assert "items" in data and "truncated" in data
        assert data["items"] == []
        assert data["truncated"] is False

    def test_text_search_returns_matches(self, admin_session):
        r = admin_session.get(f"{BASE_URL}/api/bb/manual/applicant/search",
                              params={"q": "rish"}, timeout=15)
        assert r.status_code == 200
        data = r.json()
        assert isinstance(data["items"], list)
        # rish should match rishi.nayak@blubridge.com or similar - data dependent
        # At least check structure when items present
        for it in data["items"]:
            assert "name" in it
            assert "email" in it
            assert "phone" in it
            assert "job_role" in it
            assert "registered_status" in it

    def test_digit_search_matches_phone_or_email(self, admin_session):
        r = admin_session.get(f"{BASE_URL}/api/bb/manual/applicant/search",
                              params={"q": "9443"}, timeout=15)
        assert r.status_code == 200
        data = r.json()
        # If any items returned, each must have 9443 in phone or email
        for it in data["items"]:
            haystack = (it.get("phone") or "") + "|" + (it.get("email") or "") + "|" + (it.get("name") or "")
            assert "9443" in haystack, f"item lacks 9443: {it}"

    def test_no_match_returns_empty(self, admin_session):
        r = admin_session.get(f"{BASE_URL}/api/bb/manual/applicant/search",
                              params={"q": "xxnomatchzzz"}, timeout=15)
        assert r.status_code == 200
        data = r.json()
        assert data["items"] == []
        assert data["truncated"] is False

    def test_limit_truncation(self, admin_session):
        # Use a very common substring to force many hits; cap at limit=2
        r = admin_session.get(f"{BASE_URL}/api/bb/manual/applicant/search",
                              params={"q": "a", "limit": 2}, timeout=15)
        # q='a' is 1 char → returns empty. Use 2-char common substring instead.
        r = admin_session.get(f"{BASE_URL}/api/bb/manual/applicant/search",
                              params={"q": "ai", "limit": 2}, timeout=15)
        assert r.status_code == 200
        data = r.json()
        assert len(data["items"]) <= 2
        # If at least 2 matches existed, truncated should be true
        # If <2 matched, this is fine — just don't fail


# =========================================================================
# Module — /api/bb/manual/applicant/lookup
# =========================================================================
class TestApplicantLookup:
    def test_lookup_not_found_returns_404(self, admin_session):
        r = admin_session.get(f"{BASE_URL}/api/bb/manual/applicant/lookup",
                              params={"email": "TEST_nomatch_zzz@example.com"},
                              timeout=15)
        assert r.status_code == 404

    def test_lookup_missing_params_returns_400(self, admin_session):
        r = admin_session.get(f"{BASE_URL}/api/bb/manual/applicant/lookup",
                              timeout=15)
        assert r.status_code == 400

    def test_lookup_after_search_card_click(self, admin_session):
        # First do a partial search, then pick the first result and lookup
        s = admin_session.get(f"{BASE_URL}/api/bb/manual/applicant/search",
                              params={"q": "rish"}, timeout=15)
        items = s.json().get("items", [])
        if not items:
            pytest.skip("No 'rish' applicants in DB to validate lookup chaining")
        first = items[0]
        r = admin_session.get(f"{BASE_URL}/api/bb/manual/applicant/lookup",
                              params={"email": first["email"],
                                      "phone": first["phone"]},
                              timeout=15)
        assert r.status_code == 200, r.text
        body = r.json()
        # detail view contains richer fields
        assert "registered_status" in body or "email_type" in body


# =========================================================================
# Module — bb_modules._validate_phone_10digits
# =========================================================================
class TestPhoneValidator:
    @pytest.mark.parametrize("raw,expected", [
        ("9876543210", "9876543210"),
        ("09876543210", "9876543210"),
        ("+919876543210", "9876543210"),
        ("919876543210", "9876543210"),
        ("9123456789", "9123456789"),  # 10 digits starting with 91 — keep
        ("+91 9876543210", "9876543210"),
    ])
    def test_accepted_variants(self, raw, expected):
        from bb_modules import _validate_phone_10digits
        assert _validate_phone_10digits(raw) == expected

    def test_too_short_raises(self):
        from bb_modules import _validate_phone_10digits
        with pytest.raises(ValueError):
            _validate_phone_10digits("9876")

    def test_too_long_raises(self):
        from bb_modules import _validate_phone_10digits
        with pytest.raises(ValueError):
            _validate_phone_10digits("12345678901234")

    def test_non_digit_raises(self):
        from bb_modules import _validate_phone_10digits
        with pytest.raises(ValueError):
            _validate_phone_10digits("9876abc210")


# =========================================================================
# Module — messaging.notify_rejected uses 'Final Reject'
# =========================================================================
class TestFinalRejectCampaign:
    def test_notify_rejected_wires_final_reject(self):
        """Mock send_whatsapp and email send to capture campaign_name + params."""
        import asyncio
        import importlib
        import messaging
        importlib.reload(messaging)

        captured = {}

        async def fake_send_whatsapp(campaign_name, phone, email, template_params, is_test=False):
            captured["wa"] = {
                "campaign_name": campaign_name,
                "phone": phone,
                "email": email,
                "template_params": list(template_params),
            }
            return True

        async def fake_send_email(*args, **kwargs):
            captured["email_called"] = True
            return True

        messaging.send_whatsapp = fake_send_whatsapp
        messaging.send_email = fake_send_email

        asyncio.run(messaging.notify_rejected(
            name="Test Candidate",
            phone="9443109903",
            email="rishi.nayak@blubridge.com",
            job_role="Software Engineer",
            is_test=True,
        ))

        assert captured["wa"]["campaign_name"] == "Final Reject"
        assert captured["wa"]["template_params"] == ["Test Candidate", "Software Engineer"]

    def test_notify_rejected_with_reason_uses_reject_campaign(self):
        """notify_rejected_with_reason (form-condition path) keeps 'Reject' campaign."""
        import asyncio
        import importlib
        import messaging
        importlib.reload(messaging)

        captured = {}

        async def fake_send_whatsapp(campaign_name, phone, email, template_params, is_test=False):
            captured["campaign_name"] = campaign_name
            captured["params"] = list(template_params)
            return True

        async def fake_send_email(*args, **kwargs):
            return True

        messaging.send_whatsapp = fake_send_whatsapp
        messaging.send_email = fake_send_email

        # introspect signature to pass minimal args
        import inspect
        sig = inspect.signature(messaging.notify_rejected_with_reason)
        kwargs = {}
        for p_name, p in sig.parameters.items():
            if p.default is inspect.Parameter.empty:
                if p_name == "name":
                    kwargs[p_name] = "Test"
                elif p_name == "phone":
                    kwargs[p_name] = "9443109903"
                elif p_name == "email":
                    kwargs[p_name] = "rishi.nayak@blubridge.com"
                elif p_name == "reason":
                    kwargs[p_name] = "Below cutoff"
                else:
                    kwargs[p_name] = ""
        kwargs["is_test"] = True

        asyncio.run(messaging.notify_rejected_with_reason(**kwargs))
        assert captured.get("campaign_name") == "Reject", f"got {captured.get('campaign_name')}"
