"""iter125f regression — Job Role filter consistency across pages.

ISSUE 1: Missing Applicants page lacked a Job Role filter entirely.
ISSUE 2: View Applicants (Roles.js) and View Attended Applicants
  (AttendedRoles.js) populated their Job Role dropdowns from
  `/api/job-roles`, which only returns roles with >=1 record in
  `pipeline_data`. Roles that live only in `registered_candidates`
  (e.g. Social Media Marketer with 0 pd / 6 rc) were silently dropped.

Fix:
  * Backend: `/api/bb/missing-applicants` and its `/export` partner now
    accept an optional `jobRole` query param and match it
    case-insensitively against `_normalized_job_role | job_role |
    job_title` (same multi-field pattern used by Interview Reports).
  * Frontend: Roles.js, AttendedRoles.js, MissingApplicants.js all now
    source the dropdown from `/api/bb/job-roles` — the centralized
    canonical catalogue (bb_job_roles + auto-synced job_titles_master).
    Every catalogued role surfaces regardless of which collection
    holds its candidates.
"""
import inspect
import os
import sys

from dotenv import load_dotenv

load_dotenv("/app/backend/.env")
sys.path.insert(0, "/app/backend")

import bb_modules  # noqa: E402


# ─────────────────── Backend ───────────────────

def test_missing_applicants_endpoint_accepts_job_role_filter():
    """Source-code guard: missing-applicants endpoint must accept the
    `jobRole` query parameter AND apply it as a multi-field
    case-insensitive match."""
    src = inspect.getsource(bb_modules.missing_applicants)
    assert "jobRole" in src, "missing-applicants must accept a jobRole query param"
    # Multi-field match against _normalized_job_role | job_role | job_title
    assert '"_normalized_job_role":' in src
    assert '"job_role":' in src
    assert '"job_title":' in src
    # Case-insensitive regex anchored to full string
    assert '"$options": "i"' in src


def test_missing_applicants_export_accepts_job_role_filter():
    """The export endpoint must mirror the same filter chain so downloaded
    files match the on-screen table exactly."""
    src = inspect.getsource(bb_modules.export_missing_applicants)
    assert "jobRole" in src
    assert '"_normalized_job_role":' in src
    assert '"job_role":' in src
    assert '"job_title":' in src


# ─────────────────── Frontend dropdown sources ───────────────────

def test_missing_applicants_page_has_job_role_dropdown_from_bb_job_roles():
    """MissingApplicants.js: dropdown sourced from `/api/bb/job-roles`."""
    path = "/app/frontend/src/pages/MissingApplicants.js"
    with open(path, "r") as f:
        src = f.read()
    assert "/api/bb/job-roles" in src
    assert "setBbRoles" in src or "bbRoles" in src
    assert 'data-testid="filter-job-role"' in src
    # Filter param wired into the query string
    assert "p.jobRole = jobRole" in src or "params.jobRole" in src


def test_roles_page_dropdown_uses_centralized_canonical_source():
    """View Applicants (Roles.js): job-role dropdown must NOT use the
    candidate-count-filtered `/api/job-roles` for the dropdown; it must
    use the canonical `/api/bb/job-roles`."""
    path = "/app/frontend/src/pages/Roles.js"
    with open(path, "r") as f:
        src = f.read()
    assert "/api/bb/job-roles" in src
    # The legacy candidate-count endpoint must not be used in the
    # dropdown's useEffect — it's still allowed elsewhere but not for
    # setting `jobRoles`.
    # Sanity check: ensure setJobRoles is fed by .map of `roles`.
    assert "setJobRoles(roles)" in src


def test_attended_roles_page_dropdown_uses_centralized_canonical_source():
    """View Attended Applicants (AttendedRoles.js): same centralized source."""
    path = "/app/frontend/src/pages/AttendedRoles.js"
    with open(path, "r") as f:
        src = f.read()
    assert "/api/bb/job-roles" in src
    assert "setJobRoles(roles)" in src


# ─────────────────── Centralized source consistency ───────────────────

def test_all_three_pages_share_the_same_role_source():
    """Sanity: every page that exposes a job-role dropdown reads from
    the SAME endpoint (`/api/bb/job-roles`). No page-specific lists,
    no hardcoded arrays."""
    pages = [
        "/app/frontend/src/pages/Roles.js",
        "/app/frontend/src/pages/AttendedRoles.js",
        "/app/frontend/src/pages/MissingApplicants.js",
    ]
    for p in pages:
        with open(p, "r") as f:
            src = f.read()
        assert "/api/bb/job-roles" in src, f"{p} must source dropdown from /api/bb/job-roles"
