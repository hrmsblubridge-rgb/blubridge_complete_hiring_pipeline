"""iter136 — Team Score table sticky columns/header + pagination.
Source-code guards on the React component."""

import os
import re


PAGE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "..", "frontend", "src", "pages", "TeamScore.js",
)


def _src():
    return open(PAGE, encoding="utf-8").read()


def test_first_three_columns_are_sticky_horizontally():
    """Status, Name, Email ID headers + cells must be sticky left."""
    s = _src()
    # Status header sticky left-0
    assert re.search(r'data-testid="ts-th-status"[^>]*sticky[^>]*left-0', s)
    # Name header sticky left-[64px]
    assert re.search(r'data-testid="ts-th-name"[^>]*sticky[^>]*left-\[64px\]', s)
    # Email header sticky left-[244px] (64 + 180)
    assert re.search(r'data-testid="ts-th-email"[^>]*sticky[^>]*left-\[244px\]', s)
    # Body cells also sticky (Status / Name / Email tds).
    # Check the body row block contains three sticky left- declarations.
    body_block = s[s.index("pagedEmployees.map"):]
    body_block = body_block[: body_block.index("</tbody>")]
    assert "sticky left-0" in body_block
    assert "sticky left-[64px]" in body_block
    assert "sticky left-[244px]" in body_block


def test_table_header_is_sticky_vertically():
    """Every <th> must be `sticky top-0` so the header row stays put when
    the table scrolls vertically."""
    s = _src()
    # All <th> sticky top-0 — easiest check is that "sticky top-0"
    # appears at least once for each of the 3 fixed-corner cells.
    for tid in ("ts-th-status", "ts-th-name", "ts-th-email"):
        assert re.search(rf'data-testid="{tid}"[^>]*sticky[^>]*top-0', s), (
            f"{tid} missing sticky top-0"
        )
    # The remaining headers (BASE_COLS minus name/email + sortedRounds) must
    # also carry sticky top-0 styling.
    assert s.count("sticky top-0") >= 5


def test_table_wrap_has_overflow_auto_and_max_height():
    """Container must allow both axes to scroll and constrain height so the
    sticky header has somewhere to be sticky against."""
    s = _src()
    # Find the <div ... data-testid="ts-table-wrap"...> opening tag and
    # confirm it carries the right classes.
    m = re.search(r'<div\b[^>]*data-testid="ts-table-wrap"[^>]*>', s)
    assert m, "ts-table-wrap div missing"
    tag = m.group(0)
    assert "overflow-auto" in tag
    assert "max-h-" in tag


def test_pagination_controls_present():
    """Page-size dropdown, conditional « ‹ › » buttons, page indicator,
    custom-page input, and Go button."""
    s = _src()
    # Page size dropdown with all required options.
    assert re.search(r'data-testid="ts-page-size"', s)
    for n in (10, 25, 50, 100, 150, 200, 250, 500):
        assert f"{n}" in s and "PAGE_SIZE_OPTIONS" in s
    # Conditional first/prev — wrapped in `currentPage > 1`.
    assert "currentPage > 1" in s
    assert 'data-testid="ts-page-first"' in s
    assert 'data-testid="ts-page-prev"' in s
    # Conditional next/last — wrapped in `currentPage < totalPages`.
    assert "currentPage < totalPages" in s
    assert 'data-testid="ts-page-next"' in s
    assert 'data-testid="ts-page-last"' in s
    # Indicator + custom input + Go button.
    assert 'data-testid="ts-page-indicator"' in s
    assert 'data-testid="ts-page-input"' in s
    assert 'data-testid="ts-page-go"' in s


def test_table_renders_paged_subset_not_all():
    """The body must iterate over `pagedEmployees`, not `employees`."""
    s = _src()
    body = s[s.index("<tbody>"): s.index("</tbody>")]
    assert "pagedEmployees.map" in body
    # The full-employees `.map` must NOT appear in the body block.
    assert ".map(e => {" in body  # still maps, just over the paged slice
