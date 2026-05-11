"""iter79 — Centralized display formatters for date + time.

Storage format in DB stays unchanged. These helpers normalize values for
all OUTGOING UI/Message/Email payloads.
  • Date  → dd-mm-yyyy
  • Time  → hh:mm AM/PM (12-hour)
"""
from __future__ import annotations

import re
from datetime import datetime
from typing import Optional


def fmt_date(s: Optional[str]) -> str:
    """Format any common date string to dd-mm-yyyy. Returns '' on falsy input.

    Accepts: YYYY-MM-DD, YYYY-MM-DDTHH:MM:SS+TZ, DD-MM-YYYY, DD/MM/YYYY,
    YYYY/MM/DD, ISO datetimes.
    """
    if not s:
        return ""
    txt = str(s).strip()
    if not txt:
        return ""

    # dd-mm-yyyy or dd/mm/yyyy
    m = re.match(r"^(\d{2})[-/](\d{2})[-/](\d{4})\b", txt)
    if m:
        return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
    # yyyy-mm-dd or yyyy/mm/dd
    m = re.match(r"^(\d{4})[-/](\d{2})[-/](\d{2})", txt)
    if m:
        return f"{m.group(3)}-{m.group(2)}-{m.group(1)}"
    # Try datetime parse
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d",
                "%d-%m-%Y", "%d/%m/%Y", "%Y/%m/%d"):
        try:
            dt = datetime.strptime(txt[:len(fmt) + 5], fmt) if "T" in fmt else datetime.strptime(txt, fmt)
            return dt.strftime("%d-%m-%Y")
        except ValueError:
            continue
    return txt  # give up; return raw


def fmt_time(s: Optional[str]) -> str:
    """Format a time string to `hh:mm AM/PM`. Returns '' on falsy input."""
    if not s:
        return ""
    raw = str(s).strip().upper().replace(".", "")
    if not raw:
        return ""
    # Already AM/PM-ish
    m = re.match(r"^(\d{1,2}):(\d{2})\s*(AM|PM)$", raw)
    if m:
        h = int(m.group(1)) % 24
        return f"{h:02d}:{m.group(2)} {m.group(3)}"
    m = re.match(r"^(\d{1,2})\s*(AM|PM)$", raw)
    if m:
        return f"{int(m.group(1)):02d}:00 {m.group(2)}"
    # 24-hour
    m = re.match(r"^(\d{1,2}):(\d{2})(?::\d{2})?$", raw)
    if m:
        h24 = int(m.group(1))
        mm = m.group(2)
        period = "PM" if h24 >= 12 else "AM"
        h12 = h24 % 12 or 12
        return f"{h12:02d}:{mm} {period}"
    return raw


def fmt_date_time(d: Optional[str], t: Optional[str]) -> str:
    dd = fmt_date(d)
    tt = fmt_time(t)
    if dd and tt:
        return f"{dd} {tt}"
    return dd or tt or ""
