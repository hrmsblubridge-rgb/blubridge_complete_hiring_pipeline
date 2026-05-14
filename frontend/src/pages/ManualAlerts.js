/**
 * Manual Applicant Alerts (iter67 — Module #2)
 * --------------------------------------------
 * Search applicant by email + phone → display details → fire any of 5
 * messaging templates manually (shortlist, schedule detail, OTP, follow-up,
 * reject). Reuses /api/bb/manual/applicant/lookup + /api/bb/manual/alerts/*.
 */
import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import axios from 'axios';
import { toast } from 'sonner';
import {
    ArrowLeft, EnvelopeSimple,
    PaperPlaneTilt, ClipboardText,
    BellRinging, ShieldCheck, Prohibit, ArrowLeft as ArrowLeftIcon,
} from '@phosphor-icons/react';
import ApplicantSearchCards from '../components/ApplicantSearchCards';

const API = process.env.REACT_APP_BACKEND_URL;

// Per-status enable map (spec #7). Keys = derived registered_status; values =
// the action keys that are ALLOWED. For "Attended", an extra check on
// result_status (Selected vs Rejected/On hold) decides what's enabled.
const ENABLED_BY_STATUS = {
    'Interview not scheduled': ['shortlist'],
    'Interview scheduled':     ['schedule_detail', 'otp', 'followup'],
    'Not Attended':            ['schedule_detail', 'otp', 'followup'],
    'Attended':                [],   // refined below by result_status
    'Rejected':                [],
    '':                        [],   // unknown — keep all disabled, force admin to clarify
};

// iter79 — Spec #5 NEW RULE:
// • The 4 buttons below are ALWAYS enabled regardless of applicant status:
//   shortlist, schedule_detail, otp, followup
// • The "Send Rejection" button is enabled ONLY when registered_status === 'Attended'
//   (result_status is ignored).
function _allowedActions(applicant) {
    if (!applicant) return [];
    const allowed = ['shortlist', 'schedule_detail', 'otp', 'followup'];
    const rs = (applicant.registered_status || '').trim();
    if (rs === 'Attended') allowed.push('reject');
    return allowed;
}

const ACTION_BUTTONS = [
    { key: 'shortlist',       label: 'Send Interview Schedule',         endpoint: '/api/bb/manual/alerts/send-shortlist',       icon: PaperPlaneTilt, color: 'bg-emerald-600 hover:bg-emerald-700' },
    { key: 'schedule_detail', label: 'Send Schedule Details',           endpoint: '/api/bb/manual/alerts/send-schedule-detail', icon: ClipboardText,  color: 'bg-blue-600 hover:bg-blue-700' },
    { key: 'otp',             label: 'Send OTP',                        endpoint: '/api/bb/manual/alerts/send-otp',             icon: ShieldCheck,    color: 'bg-amber-600 hover:bg-amber-700' },
    { key: 'followup',        label: 'Send Candidate Follow-up',        endpoint: '/api/bb/manual/alerts/send-followup',        icon: BellRinging,    color: 'bg-violet-600 hover:bg-violet-700' },
    { key: 'reject',          label: 'Send Rejection',                  endpoint: '/api/bb/manual/alerts/send-reject',          icon: Prohibit,       color: 'bg-rose-600 hover:bg-rose-700' },
];

export default function ManualAlerts() {
    const navigate = useNavigate();
    const [query, setQuery] = useState('');
    const [applicant, setApplicant] = useState(null);
    const [loadingDetail, setLoadingDetail] = useState(false);
    const [sending, setSending] = useState('');

    // iter95 — Card click → fetch the full detail payload (registered_status,
    // result_status etc.) via the existing /applicant/lookup endpoint with
    // exact email+phone. Keeps the rest of the page (action buttons + state
    // derivation) untouched.
    const selectApplicant = async (card) => {
        setLoadingDetail(true);
        try {
            const params = {};
            if (card.email) params.email = card.email;
            if (card.phone) params.phone = card.phone;
            const r = await axios.get(`${API}/api/bb/manual/applicant/lookup`, {
                withCredentials: true, params,
            });
            setApplicant(r.data);
        } catch (e) {
            toast.error(e.response?.data?.detail || 'Failed to load applicant');
        } finally { setLoadingDetail(false); }
    };

    const handleClear = () => {
        setQuery(''); setApplicant(null);
    };

    const backToResults = () => {
        setApplicant(null);
    };

    const fireAction = async (btn) => {
        if (!applicant) return;
        setSending(btn.key);
        try {
            const r = await axios.post(`${API}${btn.endpoint}`,
                { email: applicant.email, phone: applicant.phone },
                { withCredentials: true }
            );
            if (r.data?.success) {
                // iter75 — Accurate UI status: AiSensy 200 only proves the
                // payload was accepted, NOT that Meta delivered. The
                // diagnostic page shows the live delivery state.
                const wa = r.data?.wa_ok;
                const em = r.data?.em_ok;
                if (wa === true && em === true) toast.success(`${btn.label} — submitted (WhatsApp + Email)`);
                else if (wa === true && em === false) toast.success(`${btn.label} — WhatsApp submitted (Email failed)`);
                else if (wa === false && em === true) toast.warning(`${btn.label} — Email sent. WhatsApp blocked by Meta engagement policy. Check AiSensy logs.`);
                else toast.success(`${btn.label} — submitted to AiSensy`);
            } else toast.error(`${btn.label} — failed`);
        } catch (e) {
            const detail = e.response?.data?.detail || `${btn.label} failed`;
            toast.error(detail);
        } finally { setSending(''); }
    };

    return (
        <div className="min-h-screen" data-testid="manual-alerts-page">
            <header className="bg-[#faf9f1] border-b border-[#e5e3d8] px-6 lg:px-10 py-5">
                <div className="max-w-5xl mx-auto flex items-center gap-3 pl-12 lg:pl-0">
                    <button onClick={() => navigate('/home')} data-testid="back-btn" className="p-2 rounded-lg hover:bg-[#efede5]">
                        <ArrowLeft size={18} className="text-[#1a2332]" />
                    </button>
                    <div className="w-10 h-10 rounded-xl flex items-center justify-center bg-violet-100">
                        <EnvelopeSimple size={22} weight="duotone" className="text-violet-700" />
                    </div>
                    <div>
                        <h1 className="text-xl lg:text-2xl font-bold text-[#1a2332] tracking-tight">Manual Applicant Alerts</h1>
                        <p className="text-xs text-[#6b7280] mt-0.5">Re-fire any messaging flow for a single candidate</p>
                    </div>
                </div>
            </header>

            <main className="max-w-5xl mx-auto px-6 lg:px-10 py-6 space-y-5">
                {/* Search — show multi-card picker when no applicant selected */}
                {!applicant && (
                    <ApplicantSearchCards
                        value={query}
                        onChange={setQuery}
                        onSelect={selectApplicant}
                        onCancel={handleClear}
                        testIdPrefix="manual-alerts"
                        placeholder="Type name, email, or phone (min 2 chars)…"
                    />
                )}
                {loadingDetail && (
                    <div className="bg-[#fffdf7] border border-[#e5e3d8] rounded-2xl p-6 text-center text-sm text-[#6b7280]" data-testid="manual-alerts-loading-detail">
                        Loading applicant…
                    </div>
                )}

                {/* Applicant details */}
                {applicant && (
                    <>
                        <div className="flex items-center justify-between gap-3">
                            <button onClick={backToResults} data-testid="manual-alerts-back-to-results"
                                className="inline-flex items-center gap-2 text-sm font-semibold text-[#1d3a8a] hover:underline">
                                <ArrowLeftIcon size={14} weight="bold" /> Back to results
                            </button>
                            <span className="text-[11px] text-[#9b9787]">Showing details for <strong className="text-[#1a2332]">{applicant.name || applicant.email}</strong></span>
                        </div>
                        <div className="bg-[#fffdf7] border border-[#e5e3d8] rounded-2xl overflow-hidden" data-testid="manual-alerts-details">
                        <div className="px-5 py-3 bg-[#faf9f1] border-b border-[#e5e3d8] text-sm font-semibold text-[#1a2332]">Applicant Details</div>
                        <div className="overflow-x-auto">
                            <table className="w-full text-sm">
                                <tbody>
                                    {[
                                        ['Name', applicant.name],
                                        ['Job Role', applicant.job_role],
                                        ['Phone', applicant.phone],
                                        ['Email', applicant.email],
                                        ['College Type', applicant.college_type],
                                        ['College', applicant.college],
                                        ['Degree', applicant.degree],
                                        ['Registered Status', applicant.registered_status],
                                        ['Attended', applicant.attended ? 'Yes' : 'No'],
                                        ['Result Status', applicant.result_status],
                                        ['HR Team / Source', applicant.hr_team],
                                    ].map(([k, v]) => (
                                        <tr key={k} className="border-b border-[#ece9dc] last:border-b-0">
                                            <td className="px-5 py-2.5 text-[#6b7280] w-44">{k}</td>
                                            <td className="px-5 py-2.5 text-[#1a2332] font-medium" data-testid={`field-${k.toLowerCase().replace(/\s+/g, '-')}`}>{v || '—'}</td>
                                        </tr>
                                    ))}
                                </tbody>
                            </table>
                        </div>
                    </div>
                    </>
                )}

                {/* Action buttons row */}
                {applicant && (() => {
                    const allowed = _allowedActions(applicant);
                    return (
                    <div className="bg-[#fffdf7] border border-[#e5e3d8] rounded-2xl p-5">
                        <p className="text-[11px] font-semibold tracking-[0.16em] text-[#9b9787] uppercase mb-3 flex items-center gap-2">
                            Trigger Manual Alert
                            <span className="text-[10px] normal-case tracking-normal text-[#6b7280] font-normal">
                                — derived state: <strong className="text-[#1a2332]">{applicant.registered_status || 'Unknown'}</strong>
                                {applicant.result_status && (<> · result: <strong className="text-[#1a2332]">{applicant.result_status}</strong></>)}
                            </span>
                        </p>
                        <div className="grid grid-cols-2 lg:grid-cols-5 gap-3">
                            {ACTION_BUTTONS.map((btn) => {
                                const enabled = allowed.includes(btn.key);
                                return (
                                <button
                                    key={btn.key}
                                    disabled={sending !== '' || !enabled}
                                    onClick={() => fireAction(btn)}
                                    data-testid={`action-${btn.key}`}
                                    title={enabled ? '' : `Not allowed for ${applicant.registered_status || 'this state'}`}
                                    className={`text-white text-xs font-semibold px-4 py-3 rounded-xl flex flex-col items-center gap-1.5 transition-colors ${enabled ? btn.color : 'bg-gray-300 cursor-not-allowed'} disabled:opacity-50`}
                                >
                                    <btn.icon size={20} weight="duotone" />
                                    <span className="text-center leading-tight">{sending === btn.key ? 'Sending…' : btn.label}</span>
                                    <span className="text-[10px] opacity-80">Mail + WhatsApp</span>
                                </button>
                                );
                            })}
                        </div>
                        <p className="text-[11px] text-[#9b9787] mt-3 leading-relaxed">
                            ⓘ Buttons enable based on the applicant's derived stage (spec #7). Outbound messages additionally obey TEST MODE — while ON, only Tester Credentials receive real WhatsApp / Email.
                        </p>
                    </div>
                    );
                })()}
            </main>
        </div>
    );
}
