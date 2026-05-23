"""iter117 — Email template branding regression.

Before: `_email_shell` rendered a plain-text wordmark "BLUBRIDGE" (Georgia,
0.22em letter-spacing, color #2071b9) as the footer brand mark. The
missed-reminder template explicitly opted out via `with_logo_footer=False`,
meaning it had NO brand mark at all. Other paths like
`notify_rejected_with_reason` bypassed `_email_shell` entirely and sent raw
`<p>` HTML — no shell, no logo, inconsistent branding.

After (iter117):
* `_email_shell` now ALWAYS injects the official BluBridge PNG logo as an
  `<img>` referencing the Emergent customer-assets CDN URL (stable HTTPS).
* The `with_logo_footer` param is preserved for API compat but no longer
  suppresses the logo — every recruitment email carries the brand mark.
* `notify_rejected_with_reason` now routes its body through `_email_shell`.

Tests use ONLY tester credentials.
"""

import os
import sys

import pytest
from dotenv import load_dotenv

load_dotenv("/app/backend/.env")
sys.path.insert(0, "/app/backend")


def test_default_shell_embeds_logo_img():
    from messaging import _email_shell, _BLUBRIDGE_LOGO_URL
    html = _email_shell("<p>hello</p>")
    assert "<img src=" in html
    assert _BLUBRIDGE_LOGO_URL in html
    assert 'alt="Blubridge"' in html


def test_default_shell_removes_legacy_text_wordmark():
    """The old Georgia / letter-spacing text wordmark must no longer render."""
    from messaging import _email_shell
    html = _email_shell("<p>hello</p>")
    assert "letter-spacing:0.22em" not in html
    # The literal 'BLUBRIDGE' text styled as a `<p>` (old marker) must be gone.
    assert (
        'font-family:Georgia' not in html
        or "BLUBRIDGE</p>" not in html
    )


def test_with_logo_footer_false_still_emits_logo():
    """iter117 — `with_logo_footer=False` MUST still embed the official logo
    (previously suppressed it for missed-reminder). Param kept for API
    compatibility but behavior is now: always-include."""
    from messaging import _email_shell, _BLUBRIDGE_LOGO_URL
    html = _email_shell("<p>hello</p>", with_logo_footer=False)
    assert _BLUBRIDGE_LOGO_URL in html
    assert "<img src=" in html


def test_logo_url_env_override():
    """Operators can swap the logo URL via env var without code change."""
    from importlib import reload
    os.environ["BLUBRIDGE_LOGO_URL"] = "https://example.test/custom-logo.png"
    try:
        import messaging
        reload(messaging)
        assert messaging._BLUBRIDGE_LOGO_URL == "https://example.test/custom-logo.png"
        html = messaging._email_shell("<p>body</p>")
        assert "https://example.test/custom-logo.png" in html
    finally:
        os.environ.pop("BLUBRIDGE_LOGO_URL", None)
        import messaging  # noqa: F401
        reload(messaging)  # restore default for other tests


def test_logo_asset_url_reachable():
    """The hosted asset must return HTTP 200 with image/png content-type."""
    import httpx
    from messaging import _BLUBRIDGE_LOGO_URL
    r = httpx.head(_BLUBRIDGE_LOGO_URL, follow_redirects=True, timeout=10.0)
    assert r.status_code == 200, f"Logo asset unreachable: {r.status_code}"
    ctype = r.headers.get("content-type", "")
    assert "image/" in ctype, f"Unexpected content-type: {ctype!r}"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
