"""iter140 — Team Score modal scrollable bodies. Source-code guard.

The Employee modal (Add + Edit) and Rounds modal must use the three-region
flex layout so a growing pair list / round list never pushes the footer
buttons off-screen.
"""

import os
import re


PAGE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "..", "frontend", "src", "pages", "TeamScore.js",
)


def _src():
    return open(PAGE, encoding="utf-8").read()


def _modal_block(label):
    """Return the JSX block for the given component name."""
    s = _src()
    start = s.index(f"function {label}(")
    end = s.index("\n}\n", start) + 2
    return s[start:end]


def test_employee_modal_uses_three_region_flex_layout():
    block = _modal_block("EmployeeModal")
    # Outer card carries flex flex-col + max-h-[90vh] + min-h-0
    # so the scroll body can honour the cap.
    assert "flex flex-col max-h-[90vh] min-h-0" in block
    # Scrollable body is marked with the data-testid AND has flex-1
    # min-h-0 overflow-y-auto.
    assert 'data-testid="ts-emp-modal-body"' in block
    m = re.search(
        r'<div\b[^>]*flex-1 min-h-0 overflow-y-auto[^>]*data-testid="ts-emp-modal-body"',
        block,
    )
    assert m, "Employee modal body missing flex-1 min-h-0 overflow-y-auto"
    # Footer wrapping Cancel / Add|Update has `shrink-0` so it stays pinned.
    # Locate the line with `ts-emp-submit` and verify ancestor has shrink-0.
    submit_line_idx = block.index('data-testid="ts-emp-submit"')
    # Walk backwards to find the enclosing <div ...> tag.
    pre = block[:submit_line_idx]
    enclosing_div = pre.rfind("<div")
    parent_div_open = block[enclosing_div: pre.rfind(">") + 1]
    assert "shrink-0" in parent_div_open, (
        f"Submit button's enclosing div should be shrink-0; got: {parent_div_open!r}"
    )


def test_rounds_modal_uses_three_region_flex_layout():
    block = _modal_block("RoundsModal")
    assert "flex flex-col max-h-[90vh] min-h-0" in block
    assert "flex-1 min-h-0 overflow-y-auto" in block


def test_employee_modal_inputs_can_shrink_inside_flex_row():
    """The per-pair select must include `min-w-0` so it shrinks instead
    of overflowing horizontally when the round name is very long."""
    block = _modal_block("EmployeeModal")
    # The select tag spans multiple lines and contains an arrow function
    # in onChange, which breaks naive `<select[^>]*>` regex. Grab the
    # substring from `<select` up to its `>` skipping over braces.
    idx = block.index("data-testid={`ts-emp-pair-round-")
    # Walk backwards to find the opening `<select`.
    open_tag = block.rfind("<select", 0, idx)
    # Walk forward to find the matching `>` that closes the JSX opening
    # tag. Naive but works because the className section is BEFORE the
    # data-testid attribute.
    near = block[open_tag: idx + 200]
    assert "flex-1" in near and "min-w-0" in near, (
        f"per-pair select must have `flex-1 min-w-0`, got: {near!r}"
    )
