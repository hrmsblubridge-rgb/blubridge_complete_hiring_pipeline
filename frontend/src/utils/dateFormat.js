/**
 * Display formatters — applied uniformly across pages.
 *   Date: dd-mm-yyyy
 *   Time: 12-hour with AM/PM (e.g. "1:00 PM")
 *
 * All helpers are tolerant — return input unchanged on failure.
 */

export function formatDateDDMMYYYY(val) {
  if (!val || val === '-' || val === '') return val || '-';
  const s = String(val);
  // "2026-05-06" or "2026-05-06 14:22:00" or "2026-05-06T14:22:00Z"
  const m = s.match(/^(\d{4})-(\d{2})-(\d{2})/);
  if (m) return `${m[3]}-${m[2]}-${m[1]}`;
  // Already dd-mm-yyyy?
  if (/^\d{2}-\d{2}-\d{4}$/.test(s)) return s;
  // Fallback: ISO
  const d = new Date(s);
  if (!isNaN(d)) {
    const dd = String(d.getDate()).padStart(2, '0');
    const mm = String(d.getMonth() + 1).padStart(2, '0');
    return `${dd}-${mm}-${d.getFullYear()}`;
  }
  return s;
}

export function formatTime12H(val) {
  if (!val || val === '-' || val === '') return val || '-';
  const s = String(val).trim();
  // Already AM/PM?
  if (/\b(am|pm)\b/i.test(s)) return s.toUpperCase().replace('.', '');
  const m = s.match(/^(\d{1,2}):(\d{2})(?::(\d{2}))?$/);
  if (!m) return s;
  let h = parseInt(m[1], 10);
  const mm = m[2];
  if (isNaN(h)) return s;
  // iter83 — Historical-data heuristic: 9904 legacy pipeline_data rows have
  // afternoon interview slots (1 PM–5:30 PM) stored as 01:00–05:30 because an
  // upstream importer skipped the +12 PM offset. Interview slots only exist
  // between 10:00 and 17:30 in this app, so values with hour < 6 unambiguously
  // mean PM. Fix is DISPLAY-ONLY; storage stays untouched.
  if (h >= 1 && h < 6) h += 12;
  const period = h >= 12 ? 'PM' : 'AM';
  const h12 = ((h % 12) || 12);
  return `${h12}:${mm} ${period}`;
}

export function formatDateTime(date, time) {
  return `${formatDateDDMMYYYY(date)} ${formatTime12H(time)}`.trim();
}
