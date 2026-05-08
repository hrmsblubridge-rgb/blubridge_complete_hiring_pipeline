/**
 * Manual OTP Verify (iter67 — Module #4)
 * --------------------------------------
 * Mark `otp_verified=true` on a pipeline_data record where email + phone
 * belong to the same applicant. Surfaces the resulting record after verify.
 */
import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import axios from 'axios';
import { toast } from 'sonner';
import { ArrowLeft, ShieldCheck, X, CheckCircle } from '@phosphor-icons/react';

const API = process.env.REACT_APP_BACKEND_URL;

export default function ManualOtpVerify() {
    const navigate = useNavigate();
    const [email, setEmail] = useState('');
    const [phone, setPhone] = useState('');
    const [verifying, setVerifying] = useState(false);
    const [result, setResult] = useState(null);

    const handleVerify = async () => {
        if (!email || !phone) { toast.error('Both email and phone are required'); return; }
        setVerifying(true);
        setResult(null);
        try {
            const r = await axios.post(`${API}/api/bb/manual/otp/verify`,
                { email, phone },
                { withCredentials: true }
            );
            setResult(r.data.applicant);
            toast.success('OTP verified — applicant marked as Attended');
        } catch (e) {
            toast.error(e.response?.data?.detail || 'Verify failed');
        } finally { setVerifying(false); }
    };

    const handleCancel = () => {
        setEmail(''); setPhone(''); setResult(null);
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
                <div className="bg-[#fffdf7] border border-[#e5e3d8] rounded-2xl p-5 flex flex-wrap items-end gap-3">
                    <div className="flex-1 min-w-[200px]">
                        <label className="text-[11px] font-semibold tracking-[0.16em] text-[#9b9787] uppercase block mb-1">Email</label>
                        <input value={email} onChange={(e) => setEmail(e.target.value)} placeholder="candidate@example.com"
                            data-testid="manual-otp-email"
                            className="w-full bg-[#faf9f1] border border-[#e5e3d8] rounded-lg px-3 py-2 text-sm text-[#1a2332] outline-none focus:border-[#1d3a8a]" />
                    </div>
                    <div className="flex-1 min-w-[200px]">
                        <label className="text-[11px] font-semibold tracking-[0.16em] text-[#9b9787] uppercase block mb-1">Phone</label>
                        <input value={phone} onChange={(e) => setPhone(e.target.value)} placeholder="9876543210"
                            data-testid="manual-otp-phone"
                            className="w-full bg-[#faf9f1] border border-[#e5e3d8] rounded-lg px-3 py-2 text-sm text-[#1a2332] outline-none focus:border-[#1d3a8a]" />
                    </div>
                    <button onClick={handleVerify} disabled={verifying} data-testid="manual-otp-verify-btn"
                        className="px-5 py-2.5 rounded-lg bg-amber-600 hover:bg-amber-700 text-white font-semibold text-sm flex items-center gap-2 disabled:opacity-60">
                        <ShieldCheck size={16} weight="bold" /> {verifying ? 'Verifying…' : 'Verify'}
                    </button>
                    <button onClick={handleCancel} data-testid="manual-otp-cancel-btn"
                        className="px-5 py-2.5 rounded-lg border border-[#e5e3d8] bg-[#fffdf7] text-[#1a2332] font-semibold text-sm hover:bg-[#efede5] flex items-center gap-2">
                        <X size={16} /> Cancel
                    </button>
                </div>

                {result && (
                    <div className="bg-[#fffdf7] border border-emerald-200 rounded-2xl overflow-hidden" data-testid="manual-otp-result">
                        <div className="px-5 py-3 bg-emerald-50 border-b border-emerald-200 flex items-center gap-2">
                            <CheckCircle size={18} weight="fill" className="text-emerald-700" />
                            <h2 className="text-sm font-semibold text-emerald-800">Applicant Verified</h2>
                        </div>
                        <table className="w-full text-sm">
                            <tbody>
                                {[
                                    ['Name', result.name],
                                    ['Phone', result.phone],
                                    ['Email', result.email],
                                    ['Job Role', result.job_role],
                                    ['College Type', result.college_type],
                                    ['Source (HR Team)', result.source],
                                    ['Schedule Date', result.schedule_date],
                                    ['Schedule Time', result.schedule_time],
                                    ['OTP', result.otp],
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
