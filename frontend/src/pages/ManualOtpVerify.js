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
    };

    const interviewStatus = applicant?.interview_status || 'unknown';

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

                {/* Step 2 — Applicant details + conditional Verify */}
                {applicant && !verified && (
                    <div className="bg-[#fffdf7] border border-[#e5e3d8] rounded-2xl overflow-hidden" data-testid="manual-otp-applicant">
                        <div className="px-5 py-3 bg-[#faf9f1] border-b border-[#e5e3d8] text-sm font-semibold text-[#1a2332]">Applicant Details</div>
                        <table className="w-full text-sm">
                            <tbody>
                                {[
                                    ['Name', applicant.name],
                                    ['Phone', applicant.phone],
                                    ['Email', applicant.email],
                                    ['Job Role', applicant.job_role],
                                    ['College Type', applicant.college_type],
                                    ['Source (HR Team)', applicant.hr_team],
                                    ['Schedule Date', fmtDate(applicant.schedule_date)],
                                    ['Schedule Time', fmtTime(applicant.schedule_time)],
                                    ['OTP', applicant.otp],
                                    ['Currently Verified?', applicant.otp_verified ? 'Yes' : 'No'],
                                ].map(([k, v]) => (
                                    <tr key={k} className="border-b border-[#ece9dc] last:border-b-0">
                                        <td className="px-5 py-2.5 text-[#6b7280] w-44">{k}</td>
                                        <td className="px-5 py-2.5 text-[#1a2332] font-medium">{v || '—'}</td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>

                        {/* Date-based / verified-state conditional action */}
                        <div className="px-5 py-4 border-t border-[#ece9dc] bg-[#faf9f1]">
                            {applicant.otp_verified ? (
                                <div className="flex items-center gap-2 text-emerald-800 bg-emerald-50 border border-emerald-200 rounded-lg px-4 py-3 text-sm font-semibold"
                                    data-testid="manual-otp-status-already-verified">
                                    <CheckCircle size={18} weight="fill" />
                                    Applicant has already verified their OTP !
                                </div>
                            ) : interviewStatus === 'today' ? (
                                <button onClick={handleVerify} disabled={verifying} data-testid="manual-otp-verify-btn"
                                    className="px-5 py-2.5 rounded-lg bg-amber-600 hover:bg-amber-700 text-white font-semibold text-sm flex items-center gap-2 disabled:opacity-60">
                                    <ShieldCheck size={16} weight="bold" /> {verifying ? 'Verifying…' : 'Verify'}
                                </button>
                            ) : interviewStatus === 'past' ? (
                                <div className="flex items-center gap-2 text-rose-700 bg-rose-50 border border-rose-200 rounded-lg px-4 py-3 text-sm font-semibold"
                                    data-testid="manual-otp-status-past">
                                    <WarningCircle size={18} weight="duotone" />
                                    Your interview is over !
                                </div>
                            ) : interviewStatus === 'future' ? (
                                <div className="flex items-center gap-2 text-blue-700 bg-blue-50 border border-blue-200 rounded-lg px-4 py-3 text-sm font-semibold"
                                    data-testid="manual-otp-status-future">
                                    <Clock size={18} weight="duotone" />
                                    Your interview is in future !
                                </div>
                            ) : (
                                <>
                                    <div className="flex items-center gap-2 text-amber-700 bg-amber-50 border border-amber-200 rounded-lg px-4 py-3 text-sm font-semibold mb-3"
                                        data-testid="manual-otp-status-unknown">
                                        <WarningCircle size={18} weight="duotone" />
                                        No schedule date on record — Verify is allowed.
                                    </div>
                                    <button onClick={handleVerify} disabled={verifying} data-testid="manual-otp-verify-btn"
                                        className="px-5 py-2.5 rounded-lg bg-amber-600 hover:bg-amber-700 text-white font-semibold text-sm flex items-center gap-2 disabled:opacity-60">
                                        <ShieldCheck size={16} weight="bold" /> {verifying ? 'Verifying…' : 'Verify'}
                                    </button>
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
