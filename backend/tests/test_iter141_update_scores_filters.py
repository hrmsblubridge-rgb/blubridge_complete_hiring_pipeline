"""iter141 — Update Applicants Scores filter additions.

Backend:
- /api/bb/attended-for-scores accepts optional name/email/phone (case-
  insensitive substring) query params.
- /api/bb/attended-for-scores/filters returns distinct name/email/phone
  values across the same baseline (pipeline_data + registered_candidates
  with otp_verified set).

Frontend:
- Filters are combo-box inputs (input list= + datalist) so they support
  BOTH typing and dropdown selection.
- Table renders EMAIL and PHONE columns adjacent to NAME.
"""

import os
import re


PAGE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "..", "frontend", "src", "pages", "UpdateScores.js",
)


def _src():
    return open(PAGE, encoding="utf-8").read()


def test_backend_endpoint_accepts_filter_params():
    """Source guard on bb_modules.py."""
    bb = open(
        os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "bb_modules.py"),
        encoding="utf-8",
    ).read()
    # Endpoint signature must accept the three new params.
    sig_block = bb[bb.index("async def get_attended_for_scores"):
                    bb.index("):", bb.index("async def get_attended_for_scores")) + 2]
    assert "name: Optional[str]" in sig_block
    assert "email: Optional[str]" in sig_block
    assert "phone: Optional[str]" in sig_block
    # Distinct-values endpoint exists.
    assert "/attended-for-scores/filters" in bb
    assert "async def get_attended_score_filter_options" in bb


def test_frontend_filters_are_combo_boxes():
    s = _src()
    for tid, lid in (
        ("us-filter-name", "us-filter-name-list"),
        ("us-filter-email", "us-filter-email-list"),
        ("us-filter-phone", "us-filter-phone-list"),
    ):
        # The input must declare list={lid} so the browser binds it to the
        # datalist of suggestions. Attributes can appear in any order.
        idx = s.index(f'data-testid="{tid}"')
        # Walk to the enclosing <input ...> tag.
        tag_start = s.rfind("<input", 0, idx)
        tag_end = s.index(">", idx)
        tag = s[tag_start: tag_end + 1]
        assert f'list="{lid}"' in tag, f"{tid} not wired to datalist {lid}; tag: {tag!r}"
        # The datalist itself must be rendered and bind to filterOpts.
        field = tid.split("-")[-1]
        m2 = re.search(rf'<datalist id="{lid}">.*?filterOpts\.{field}', s, re.DOTALL)
        assert m2, f"datalist {lid} missing or not bound to filterOpts.{field}"


def test_filter_state_is_sent_via_refs():
    """The fetch must read filter values from filterRefs.current so that
    select/typing into the inputs does not auto-trigger a refetch
    (preserving the explicit Apply button UX)."""
    s = _src()
    assert "filterRefs.current" in s
    assert "params.name = " in s
    assert "params.email = " in s
    assert "params.phone = " in s


def test_table_renders_email_and_phone_columns():
    s = _src()
    cols_block = s[s.index("const COLUMNS = ["): s.index("]", s.index("const COLUMNS = ["))]
    assert "'email'" in cols_block
    assert "'phone'" in cols_block
    # NAME -> EMAIL -> PHONE order
    name_idx = cols_block.index("'name'")
    email_idx = cols_block.index("'email'")
    phone_idx = cols_block.index("'phone'")
    assert name_idx < email_idx < phone_idx, (
        "Email + Phone columns must appear adjacent to (and after) Name"
    )
    # Body cells render the values.
    assert "data-testid={`score-row-${i}-email`}" in s
    assert "data-testid={`score-row-${i}-phone`}" in s


def test_reset_and_all_records_clear_new_filters():
    s = _src()
    # Both buttons must call the 3 new setters in their onClick handler.
    # Walk back from the data-testid to the enclosing <button ...> tag and
    # confirm the setters appear in the onClick body.
    for tid in ("reset-btn", "all-records-btn"):
        idx = s.index(f'data-testid="{tid}"')
        tag_start = s.rfind("<button", 0, idx)
        tag_end = s.index(">", idx)
        tag = s[tag_start: tag_end + 1]
        for setter in ("setFilterName('')", "setFilterEmail('')", "setFilterPhone('')"):
            assert setter in tag, f"{tid} button missing {setter}"
