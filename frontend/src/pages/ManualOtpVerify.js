/**
 * Manual OTP Verify (iter68 — date-aware, 2-step flow)
 * ----------------------------------------------------
 * Step 1: Search by email + phone → show applicant details.
 * Step 2: Show "Verify" button only if scheduled interview date is TODAY.
 *         - schedule_date < today  → button hidden, message "Your interview is over !"
 *         - schedule_date > today  → button hidden, message "Your interview is in future !"
 *         - schedule_date == today → "Verify" button visible.
 * On Verify success: pipeline_data.otp_verified = true (handled by backend).
 */
import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import axios from 'axios';
import { toast } from 'sonner';
import {
    ArrowLeft, ShieldCheck, X, CheckCircle, MagnifyingGlass,
    WarningCircle, Clock,
} from '@phosphor-icons/react';
import { formatDateDDMMYYYY as fmtDate, formatTime12H as fmtTime } from '../utils/dateFormat';

const API = process.env.REACT_APP_BACKEND_URL;

// iter86 — Same slot grid as the public InterviewSchedule.js form.
const TIME_SLOTS = ['10:00 AM','10:30 AM','11:00 AM','11:30 AM','12:00 PM','12:30 PM','01:00 PM','01:30 PM','02:00 PM','02:30 PM','03:00 PM','03:30 PM','04:00 PM','04:30 PM','05:00 PM'];

function _slotMinutes(label) {
    const [tm, period] = label.split(' ');
    let [h, m] = tm.split(':').map(Number);
    if (period === 'PM' && h !== 12) h += 12;
    if (period === 'AM' && h === 12) h = 0;
    return h * 60 + m;
}
function _slotToHMS(label) {
    if (!label) return '';
    const m = _slotMinutes(label);
    const hh = Math.floor(m / 60), mm = m % 60;
    return `${String(hh).padStart(2,'0')}:${String(mm).padStart(2,'0')}:00`;
}
function _hmsToSlot(hms) {
    // Convert "13:30:00" → "01:30 PM" if matches a known slot; else the closest format
    if (!hms) return '';
    const [h, m] = hms.split(':').map(Number);
    if (isNaN(h) || isNaN(m)) return '';
    // iter86 — Match the display heuristic used elsewhere: hours < 6 are
    // legacy mis-stored PM slots → shift to PM for the dropdown selection.
    let hh = h;
    if (hh >= 1 && hh < 6) hh += 12;
    const period = hh >= 12 ? 'PM' : 'AM';
    const h12 = ((hh % 12) || 12);
    const label = `${String(h12).padStart(2,'0')}:${String(m).padStart(2,'0')} ${period}`;
    return TIME_SLOTS.includes(label) ? label : '';
}

// iter86 — Small row helper for the applicant details table. Keeps inline-edit
// inputs and read-only cells visually consistent without re-templating each row.
function Row({ k, v }) {
    return (
        <tr className="border-b border-[#ece9dc] last:border-b-0">
            <td className="px-5 py-2.5 text-[#6b7280] w-44 align-top">{k}</td>
            <td className="px-5 py-2.5 text-[#1a2332] font-medium">{v ?? '—'}</td>
        </tr>
    );
}

export default function ManualOtpVerify() {
    const navigate = useNavigate();
    const [query, setQuery] = useState('');
    const [searching, setSearching] = useState(false);
    const [verifying, setVerifying] = useState(false);
    const [applicant, setApplicant] = useState(null);  // lookup payload
    const [verified, setVerified] = useState(null);    // post-verify applicant payload

    const handleSearch = async () => {
        const q = query.trim();
        if (!q) { toast.error('Enter an email or phone number'); return; }
        const isEmail = q.includes('@');
        const params = isEmail ? { email: q } : { phone: q };
        setSearching(true);
        setApplicant(null);
        setVerified(null);
        try {
            const r = await axios.get(`${API}/api/bb/manual/applicant/lookup`, {
                withCredentials: true, params,
            });
            setApplicant(r.data);
            toast.success('Applicant found');
        } catch (e) {
            toast.error(e.response?.data?.detail || 'Applicant not found');
        } finally { setSearching(false); }
    };

    const handleVerify = async () => {
        setVerifying(true);
        try {
            const r = await axios.post(`${API}/api/bb/manual/otp/verify`,
                { email: applicant.email, phone: applicant.phone },
                { withCredentials: true }
            );
            setVerified(r.data.applicant);
            toast.success('OTP verified — applicant marked as Attended');
        } catch (e) {
            toast.error(e.response?.data?.detail || 'Verify failed');
        } finally { setVerifying(false); }
    };

    const handleCancel = () => {
        setQuery(''); setApplicant(null); setVerified(null);
        setRescheduling(false); setEdit({});
    };

    // iter82 — Reschedule & Verify state
    const [rescheduling, setRescheduling] = useState(false);
    const [edit, setEdit] = useState({});      // {phone,email,job_role,schedule_date,schedule_time}
    const [savingResch, setSavingResch] = useState(false);

    // YYYY-MM-DD comparison (today < scheduled)
    const _today = new Date().toISOString().slice(0, 10);
    const _schedISO = (applicant?.schedule_date || '').slice(0, 10);
    const canReschedule = !!_schedISO && _today < _schedISO;

    const startReschedule = () => {
        setRescheduling(true);
        setEdit({
            phone:         applicant.phone || '',
            email:         applicant.email || '',
            job_role:      applicant.job_role || '',
            schedule_date: (applicant.schedule_date || '').slice(0, 10),
            schedule_time: _hmsToSlot(applicant.schedule_time || ''),
        });
    };
    const cancelReschedule = () => { setRescheduling(false); setEdit({}); };

    const handleRescheduleVerify = async () => {
        setSavingResch(true);
        try {
            // iter87 — Lock-at-5PM ONLY when selected date is today AND past 5 PM.
            const _now = new Date();
            const _isLockedToday = edit.schedule_date === _today && _now.getHours() >= 17;
            const slotLabel = _isLockedToday ? '05:00 PM' : edit.schedule_time;
            const r = await axios.post(`${API}/api/bb/manual/otp/reschedule-verify`,
                {
                    original_email: applicant.email,
                    original_phone: applicant.phone,
                    phone:         edit.phone,
                    email:         edit.email,
                    job_role:      edit.job_role,
                    schedule_date: edit.schedule_date,
                    schedule_time: _slotToHMS(slotLabel),
                },
                { withCredentials: true }
            );
            setVerified(r.data.applicant);
            setRescheduling(false);
            toast.success('Rescheduled and verified — applicant marked as Attended');
        } catch (e) {
            toast.error(e.response?.data?.detail || 'Reschedule & Verify failed');
        } finally { setSavingResch(false); }
    };

    return (
        <div className="min-h-screen" data-testid="manual-otp-verify-page">
            <header className="bg-[#faf9f1] border-b border-[#e5e3d8] px-6 lg:px-10 py-5">
                <div className="max-w-3xl mx-auto flex items-center gap-3 pl-12 lg:pl-0">
                    <button onClick={() => navigate('/home')} data-testid="back-btn" className="p-2 rounded-lg hover:bg-[#efede5]">
                        <ArrowLeft size={18} className="text-[#1a2332]" />
                    </button>
                    <div className="w-10 h-10 rounded-xl flex items-center justify-center bg-amber-100">
                        <ShieldCheck size={22} weight="duotone" className="text-amber-700" />
                    </div>
                    <div>
                        <h1 className="text-xl lg:text-2xl font-bold text-[#1a2332] tracking-tight">Manual OTP Verify</h1>
                        <p className="text-xs text-[#6b7280] mt-0.5">Mark a candidate as Attended (otp_verified = true)</p>
                    </div>
                </div>
            </header>

            <main className="max-w-3xl mx-auto px-6 lg:px-10 py-6 space-y-5">
                {/* Step 1 — Search */}
                <div className="bg-[#fffdf7] border border-[#e5e3d8] rounded-2xl p-5 flex flex-wrap items-end gap-3">
                    <div className="flex-1 min-w-[260px]">
                        <label className="text-[11px] font-semibold tracking-[0.16em] text-[#9b9787] uppercase block mb-1">Search</label>
                        <input
                            value={query}
                            onChange={(e) => setQuery(e.target.value)}
                            onKeyDown={(e) => { if (e.key === 'Enter') handleSearch(); }}
                            placeholder="Enter applicant email or phone number"
                            data-testid="manual-otp-query"
                            className="w-full bg-[#faf9f1] border border-[#e5e3d8] rounded-lg px-3 py-2 text-sm text-[#1a2332] outline-none focus:border-[#1d3a8a]"
                        />
                    </div>
                    <button onClick={handleSearch} disabled={searching} data-testid="manual-otp-search-btn"
                        className="px-5 py-2.5 rounded-lg bg-[#1d3a8a] hover:bg-[#162d6e] text-white font-semibold text-sm flex items-center gap-2 disabled:opacity-60">
                        <MagnifyingGlass size={16} weight="bold" /> {searching ? 'Searching…' : 'Search'}
                    </button>
                    <button onClick={handleCancel} data-testid="manual-otp-cancel-btn"
                        className="px-5 py-2.5 rounded-lg border border-[#e5e3d8] bg-[#fffdf7] text-[#1a2332] font-semibold text-sm hover:bg-[#efede5] flex items-center gap-2">
                        <X size={16} /> Cancel
                    </button>
                </div>

                {/* Step 2 — Applicant details + Verify / Reschedule & Verify */}
                {applicant && !verified && (
                    <div className="bg-[#fffdf7] border border-[#e5e3d8] rounded-2xl overflow-hidden" data-testid="manual-otp-applicant">
                        <div className="px-5 py-3 bg-[#faf9f1] border-b border-[#e5e3d8] text-sm font-semibold text-[#1a2332] flex items-center justify-between">
                            <span>Applicant Details</span>
                            {rescheduling && <span className="text-amber-700 text-xs">Editing — Phone / Email / Job Role / Date / Time</span>}
                        </div>
                        <table className="w-full text-sm">
                            <tbody>
                                <Row k="Name" v={applicant.name} />
                                <Row k="Phone" v={rescheduling
                                    ? <input value={edit.phone} onChange={(e) => setEdit(s => ({...s, phone: e.target.value}))} data-testid="resch-phone" className="w-full bg-white border border-[#e5e3d8] rounded px-2 py-1.5 text-sm" />
                                    : (applicant.phone || '—')} />
                                <Row k="Email" v={rescheduling
                                    ? <input value={edit.email} onChange={(e) => setEdit(s => ({...s, email: e.target.value}))} data-testid="resch-email" className="w-full bg-white border border-[#e5e3d8] rounded px-2 py-1.5 text-sm" />
                                    : (applicant.email || '—')} />
                                <Row k="Job Role" v={rescheduling
                                    ? <input value={edit.job_role} onChange={(e) => setEdit(s => ({...s, job_role: e.target.value}))} data-testid="resch-jobrole" className="w-full bg-white border border-[#e5e3d8] rounded px-2 py-1.5 text-sm" />
                                    : (applicant.job_role || '—')} />
                                <Row k="College Type" v={applicant.college_type} />
                                <Row k="Source (HR Team)" v={applicant.hr_team} />
                                <Row k="Schedule Date" v={rescheduling
                                    ? <input type="date" value={edit.schedule_date} min={_today} onChange={(e) => setEdit(s => ({...s, schedule_date: e.target.value}))} data-testid="resch-date" className="bg-white border border-[#e5e3d8] rounded px-2 py-1.5 text-sm" />
                                    : (fmtDate(applicant.schedule_date) || '—')} />
                                <Row k="Schedule Time" v={rescheduling ? (() => {
                                    // iter87 — Use the same TIME_SLOTS dropdown as the public
                                    // Interview Schedule form. Lock-at-5PM ONLY applies when
                                    // the selected date IS today AND current local hour ≥ 17.
                                    // Future dates always show a fully-editable dropdown.
                                    const _now = new Date();
                                    const _isToday = edit.schedule_date === _today;
                                    const _isAfter5PM = _isToday && _now.getHours() >= 17;
                                    const _minMins = _isToday ? (_now.getHours() * 60 + _now.getMinutes()) : -1;
                                    if (_isAfter5PM) {
                                        return (
                                            <div className="flex items-center gap-2 text-sm" data-testid="resch-time-locked">
                                                <span className="font-semibold text-[#1a2332]">05:00 PM</span>
                                                <span className="text-[11px] text-[#9b9787]">(locked — current time is past 5 PM)</span>
                                            </div>
                                        );
                                    }
                                    return (
                                        <select value={edit.schedule_time} onChange={(e) => setEdit(s => ({...s, schedule_time: e.target.value}))} data-testid="resch-time"
                                            className="bg-white border border-[#e5e3d8] rounded px-2 py-1.5 text-sm">
                                            <option value="">Select Time</option>
                                            {TIME_SLOTS.map(t => {
                                                const disabled = _minMins >= 0 && _slotMinutes(t) <= _minMins;
                                                return <option key={t} value={t} disabled={disabled}>{t}{disabled ? '  (past)' : ''}</option>;
                                            })}
                                        </select>
                                    );
                                })() : (fmtTime(applicant.schedule_time) || '—')} />
                                <Row k="OTP" v={applicant.otp} />
                                <Row k="Currently Verified?" v={applicant.otp_verified ? 'Yes' : 'No'} />
                            </tbody>
                        </table>

                        {/* iter82 — Always-enabled Verify + optional Reschedule & Verify */}
                        <div className="px-5 py-4 border-t border-[#ece9dc] bg-[#faf9f1] flex flex-wrap gap-3">
                            {applicant.otp_verified ? (
                                <div className="flex items-center gap-2 text-emerald-800 bg-emerald-50 border border-emerald-200 rounded-lg px-4 py-3 text-sm font-semibold w-full"
                                    data-testid="manual-otp-status-already-verified">
                                    <CheckCircle size={18} weight="fill" />
                                    Applicant has already verified their OTP !
                                </div>
                            ) : rescheduling ? (
                                <>
                                    <button onClick={handleRescheduleVerify} disabled={savingResch} data-testid="manual-otp-resched-verify-save"
                                        className="px-5 py-2.5 rounded-lg bg-amber-600 hover:bg-amber-700 text-white font-semibold text-sm flex items-center gap-2 disabled:opacity-60">
                                        <ShieldCheck size={16} weight="bold" /> {savingResch ? 'Saving…' : 'Save & Verify'}
                                    </button>
                                    <button onClick={cancelReschedule} disabled={savingResch} data-testid="manual-otp-resched-cancel"
                                        className="px-5 py-2.5 rounded-lg border border-[#e5e3d8] bg-[#fffdf7] text-[#1a2332] font-semibold text-sm hover:bg-[#efede5]">
                                        Discard changes
                                    </button>
                                </>
                            ) : (
                                <>
                                    <button onClick={handleVerify} disabled={verifying} data-testid="manual-otp-verify-btn"
                                        className="px-5 py-2.5 rounded-lg bg-amber-600 hover:bg-amber-700 text-white font-semibold text-sm flex items-center gap-2 disabled:opacity-60">
                                        <ShieldCheck size={16} weight="bold" /> {verifying ? 'Verifying…' : 'Verify'}
                                    </button>
                                    {canReschedule && (
                                        <button onClick={startReschedule} data-testid="manual-otp-reschedule-verify-btn"
                                            className="px-5 py-2.5 rounded-lg bg-blue-600 hover:bg-blue-700 text-white font-semibold text-sm flex items-center gap-2">
                                            <Clock size={16} weight="bold" /> Reschedule & Verify
                                        </button>
                                    )}
                                </>
                            )}
                        </div>
                    </div>
                )}

                {/* Post-verify success */}
                {verified && (
                    <div className="bg-[#fffdf7] border border-emerald-200 rounded-2xl overflow-hidden" data-testid="manual-otp-result">
                        <div className="px-5 py-3 bg-emerald-50 border-b border-emerald-200 flex items-center gap-2">
                            <CheckCircle size={18} weight="fill" className="text-emerald-700" />
                            <h2 className="text-sm font-semibold text-emerald-800">Applicant Verified</h2>
                        </div>
                        <table className="w-full text-sm">
                            <tbody>
                                {[
                                    ['Name', verified.name],
                                    ['Phone', verified.phone],
                                    ['Email', verified.email],
                                    ['Job Role', verified.job_role],
                                    ['College Type', verified.college_type],
                                    ['Source (HR Team)', verified.source],
                                    ['Schedule Date', fmtDate(verified.schedule_date)],
                                    ['Schedule Time', fmtTime(verified.schedule_time)],
                                    ['OTP', verified.otp],
                                ].map(([k, v]) => (
                                    <tr key={k} className="border-b border-[#ece9dc] last:border-b-0">
                                        <td className="px-5 py-2.5 text-[#6b7280] w-44">{k}</td>
                                        <td className="px-5 py-2.5 text-[#1a2332] font-medium">{v || '—'}</td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    </div>
                )}
            </main>
        </div>
    );
}
