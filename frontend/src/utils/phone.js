// iter94 — Centralized phone normalization helper.
// Mirrors backend `_validate_phone_10digits` in /app/backend/bb_modules.py.
// Accepts user-friendly variants and returns the bare 10-digit form (or null
// if the input cannot be normalized to exactly 10 digits).

const HELPER_TEXT =
    'You may enter: 10-digit mobile number, or with leading 0, or with +91, ' +
    'or with 91 prefix. System will normalize automatically.';

const ERROR_TEXT = 'Phone number must contain 10 digits.';

/**
 * Strip user-friendly prefixes; return either { ok:true, value:'9876543210' }
 * or { ok:false, error: '...' }.
 *
 *   "9876543210"      -> ok, '9876543210'
 *   "09876543210"     -> ok, '9876543210'  (strip leading 0)
 *   "+919876543210"   -> ok, '9876543210'  (strip +91)
 *   "919876543210"    -> ok, '9876543210'  (strip 91)
 *   "9123456789"      -> ok, '9123456789'  (10 digits starting with 91 is valid)
 *   anything else     -> error
 */
export function normalizePhone(raw) {
    const s = String(raw || '').trim().replace(/\s+/g, '');
    let digits = s;
    if (s.startsWith('+91') && s.length === 13 && /^\+91[0-9]{10}$/.test(s)) {
        digits = s.slice(3);
    } else if (s.startsWith('0') && /^0+[0-9]*$/.test(s)) {
        // iter104 — Always strip every leading zero up-front, then validate
        // the remainder. Previously the strip was gated to length === 11
        // (one leading 0 + 10 digits), so a 10-char input like "0123456789"
        // produced a misleading 'invalid' error before the user could finish
        // typing. Now any "0…", "00…", etc. is collapsed first and the
        // remaining digit count drives the verdict.
        digits = s.replace(/^0+/, '');
    } else if (s.startsWith('91') && s.length === 12 && /^[0-9]{12}$/.test(s)) {
        digits = s.slice(2);
    }
    if (/^[0-9]{10}$/.test(digits)) return { ok: true, value: digits };
    return { ok: false, error: ERROR_TEXT };
}

export const PHONE_HELPER_TEXT = HELPER_TEXT;
export const PHONE_ERROR_TEXT = ERROR_TEXT;

/**
 * Input-mask helper — strips disallowed characters while user types so the
 * field never contains anything weird. Keeps digits + a single leading '+'.
 */
export function maskPhoneInput(v) {
    if (!v) return '';
    let s = String(v).replace(/[^\d+]/g, '');
    if (s.indexOf('+') > 0) s = s.replace(/\+/g, '');
    if (s.length > 13) s = s.slice(0, 13);
    return s;
}
