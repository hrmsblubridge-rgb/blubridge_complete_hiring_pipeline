import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import axios from 'axios';
import { ArrowLeft } from '@phosphor-icons/react';

const API = process.env.REACT_APP_BACKEND_URL;

export default function VerifyOTP() {
    const navigate = useNavigate();
    const [phone, setPhone] = useState('');
    const [otp, setOtp] = useState('');
    const [result, setResult] = useState(null);
    const [loading, setLoading] = useState(false);

    const handleVerify = async () => {
        if (!phone.trim() || !otp.trim()) {
            setResult({ success: false, message: 'Phone and OTP required' });
            return;
        }
        setLoading(true);
        try {
            const r = await axios.post(`${API}/api/bb/verify-otp`,
                { phone: phone.trim(), otp: otp.trim() },
                { withCredentials: true }
            );
            setResult(r.data);
        } catch (e) {
            setResult({ success: false, message: e.response?.data?.detail || 'Verification failed' });
        } finally {
            setLoading(false);
        }
    };

    const candidate = result?.candidate;

    return (
        <div className="min-h-screen bg-[#f3f1e9]" data-testid="verify-otp-page">
            <header className="bg-[#efede5] border-b border-gray-300 py-4 px-6 flex items-center justify-between">
                <button
                    onClick={() => (window.history.length > 1 ? navigate(-1) : navigate('/home'))}
                    data-testid="back-btn"
                    className="p-2 hover:bg-black/5 rounded-md text-gray-700"
                >
                    <ArrowLeft size={20} />
                </button>
                <img src="/blubridge-logo.webp" alt="Blubridge" className="" />
                <span className="w-10" />
            </header>

            <main className="max-w-md mx-auto px-4 py-12">
                <div className="bg-[#fffdf7] rounded-xl shadow-sm p-8 space-y-6 text-gray-900">
                    <h2 className="text-2xl font-bold text-[#1f3a8a] flex items-center justify-center gap-2 tracking-tight">
                        <span aria-hidden="true">🔓</span> Verify OTP
                    </h2>

                    {!result?.success && (
                        <>
                            <div className="space-y-1.5">
                                <label className="text-xs text-gray-500 uppercase tracking-wider">Phone Number</label>
                                <input
                                    type="text"
                                    value={phone}
                                    onChange={(e) => setPhone(e.target.value)}
                                    placeholder="Enter phone number"
                                    data-testid="phone-input"
                                    className="w-full bg-[#f5f5f5] border border-gray-200 rounded px-3 py-2.5 text-sm focus:outline-none focus:border-blue-400 focus:bg-white"
                                />
                            </div>
                            <div className="space-y-1.5">
                                <label className="text-xs text-gray-500 uppercase tracking-wider">OTP</label>
                                <input
                                    type="text"
                                    value={otp}
                                    onChange={(e) => setOtp(e.target.value)}
                                    placeholder="Enter OTP"
                                    data-testid="otp-input"
                                    className="w-full bg-[#f5f5f5] border border-gray-200 rounded px-3 py-2.5 text-sm focus:outline-none focus:border-blue-400 focus:bg-white"
                                />
                            </div>
                            <button
                                onClick={handleVerify}
                                disabled={loading}
                                data-testid="verify-btn"
                                className="w-full py-3 bg-emerald-700 hover:bg-emerald-600 text-white font-bold rounded-lg disabled:opacity-50 tracking-wide"
                            >
                                {loading ? 'VERIFYING…' : 'VERIFY OTP'}
                            </button>
                        </>
                    )}

                    {result && !result.success && (
                        <div
                            className="p-4 text-center text-sm font-medium rounded bg-red-50 text-red-700 border border-red-200"
                            data-testid="verify-result"
                        >
                            {result.message}
                        </div>
                    )}

                    {result?.success && (
                        <div className="space-y-5" data-testid="verify-success">
                            <p
                                className="text-emerald-700 text-sm font-medium flex items-center justify-center gap-2"
                                data-testid="verify-success-message"
                            >
                                <span aria-hidden="true">✅</span> OTP verified successfully!
                            </p>

                            <div
                                className="bg-emerald-50 border-l-4 border-emerald-500 rounded-r-lg p-5 space-y-3"
                                data-testid="candidate-details-card"
                            >
                                <h3 className="text-base font-bold text-[#1f3a8a] flex items-center gap-2">
                                    <span aria-hidden="true">👤</span> Candidate Details
                                </h3>
                                <Detail label="Name" value={candidate?.name} testid="cand-name" />
                                <Detail label="Phone" value={candidate?.phone} testid="cand-phone" />
                                <Detail label="Email" value={candidate?.email} testid="cand-email" />
                                <Detail label="Job Role" value={candidate?.job_role} testid="cand-jobrole" />
                                <Detail label="College" value={candidate?.college || 'N/A'} testid="cand-college" />
                                <Detail label="College Type" value={candidate?.college_type || 'N/A'} testid="cand-collegetype" />
                                <Detail label="Source" value={candidate?.source || 'N/A'} testid="cand-source" />
                            </div>

                            <button
                                onClick={() => {
                                    setResult(null);
                                    setPhone('');
                                    setOtp('');
                                }}
                                data-testid="verify-another-btn"
                                className="w-full py-2.5 bg-gray-100 hover:bg-gray-200 text-gray-700 font-medium rounded-lg text-sm"
                            >
                                Verify Another Applicant
                            </button>
                        </div>
                    )}
                </div>
            </main>
        </div>
    );
}

function Detail({ label, value, testid }) {
    return (
        <div className="text-sm">
            <span className="font-bold text-gray-900">{label}:</span>{' '}
            <span className="text-gray-700" data-testid={testid}>{value || '—'}</span>
        </div>
    );
}
