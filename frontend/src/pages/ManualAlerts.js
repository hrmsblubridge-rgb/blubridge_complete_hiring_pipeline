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
    ArrowLeft, MagnifyingGlass, X, EnvelopeSimple, ChatCircleText,
    PaperPlaneTilt, ClipboardText, BellRinging, ShieldCheck, Prohibit,
} from '@phosphor-icons/react';

const API = process.env.REACT_APP_BACKEND_URL;

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
    const [loading, setLoading] = useState(false);
    const [sending, setSending] = useState('');

    const handleSearch = async () => {
        const q = query.trim();
        if (!q) { toast.error('Enter an email or phone number'); return; }
        const isEmail = q.includes('@');
        const params = isEmail ? { email: q } : { phone: q };
        setLoading(true);
        setApplicant(null);
        try {
            const r = await axios.get(`${API}/api/bb/manual/applicant/lookup`, {
                withCredentials: true, params,
            });
            setApplicant(r.data);
            toast.success('Applicant found');
        } catch (e) {
            toast.error(e.response?.data?.detail || 'Applicant not found');
        } finally { setLoading(false); }
    };

    const handleCancel = () => {
        setQuery(''); setApplicant(null);
    };

    const fireAction = async (btn) => {
        if (!applicant) return;
        setSending(btn.key);
        try {
            const r = await axios.post(`${API}${btn.endpoint}`,
                { email: applicant.email, phone: applicant.phone },
                { withCredentials: true }
            );
            if (r.data?.success) toast.success(`${btn.label} — sent`);
            else toast.error(`${btn.label} — failed`);
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
                {/* Search row */}
                <div className="bg-[#fffdf7] border border-[#e5e3d8] rounded-2xl p-5 flex flex-wrap items-end gap-3">
                    <div className="flex-1 min-w-[260px]">
                        <label className="text-[11px] font-semibold tracking-[0.16em] text-[#9b9787] uppercase block mb-1">Search</label>
                        <input
                            value={query}
                            onChange={(e) => setQuery(e.target.value)}
                            onKeyDown={(e) => { if (e.key === 'Enter') handleSearch(); }}
                            placeholder="Enter applicant email or phone number"
                            data-testid="manual-alerts-query"
                            className="w-full bg-[#faf9f1] border border-[#e5e3d8] rounded-lg px-3 py-2 text-sm text-[#1a2332] outline-none focus:border-[#1d3a8a]"
                        />
                    </div>
                    <button onClick={handleSearch} disabled={loading} data-testid="manual-alerts-search-btn"
                        className="px-5 py-2.5 rounded-lg bg-[#1d3a8a] hover:bg-[#162d6e] text-white font-semibold text-sm flex items-center gap-2 disabled:opacity-60">
                        <MagnifyingGlass size={16} weight="bold" /> {loading ? 'Searching…' : 'Search'}
                    </button>
                    <button onClick={handleCancel} data-testid="manual-alerts-cancel-btn"
                        className="px-5 py-2.5 rounded-lg border border-[#e5e3d8] bg-[#fffdf7] text-[#1a2332] font-semibold text-sm hover:bg-[#efede5] flex items-center gap-2">
                        <X size={16} /> Cancel
                    </button>
                </div>

                {/* Applicant details */}
                {applicant && (
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
                )}

                {/* Action buttons row */}
                {applicant && (
                    <div className="bg-[#fffdf7] border border-[#e5e3d8] rounded-2xl p-5">
                        <p className="text-[11px] font-semibold tracking-[0.16em] text-[#9b9787] uppercase mb-3">Trigger Manual Alert</p>
                        <div className="grid grid-cols-2 lg:grid-cols-5 gap-3">
                            {ACTION_BUTTONS.map((btn) => (
                                <button
                                    key={btn.key}
                                    disabled={sending !== ''}
                                    onClick={() => fireAction(btn)}
                                    data-testid={`action-${btn.key}`}
                                    className={`text-white text-xs font-semibold px-4 py-3 rounded-xl flex flex-col items-center gap-1.5 transition-colors disabled:opacity-50 ${btn.color}`}
                                >
                                    <btn.icon size={20} weight="duotone" />
                                    <span className="text-center leading-tight">{sending === btn.key ? 'Sending…' : btn.label}</span>
                                    <span className="text-[10px] opacity-80">Mail + WhatsApp</span>
                                </button>
                            ))}
                        </div>
                        <p className="text-[11px] text-[#9b9787] mt-3 leading-relaxed">
                            ⓘ Outbound messages obey the global TEST MODE gate. While TEST MODE is ON, sends succeed only when the recipient (email OR phone) is on the Tester Credentials list. Add testers in the <strong>Tester Credentials</strong> page; failures here mean the candidate is not yet a tester.
                        </p>
                    </div>
                )}
            </main>
        </div>
    );
}
