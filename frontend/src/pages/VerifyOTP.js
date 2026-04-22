import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import axios from 'axios';
import { ArrowLeft, ShieldCheck } from '@phosphor-icons/react';

const API = process.env.REACT_APP_BACKEND_URL;

export default function VerifyOTP() {
    const navigate = useNavigate();
    const [phone, setPhone] = useState('');
    const [otp, setOtp] = useState('');
    const [result, setResult] = useState(null);
    const [loading, setLoading] = useState(false);

    const handleVerify = async () => {
        if (!phone.trim() || !otp.trim()) { setResult({ success: false, message: 'Phone and OTP required' }); return; }
        setLoading(true);
        try {
            const r = await axios.post(`${API}/api/bb/verify-otp`, { phone: phone.trim(), otp: otp.trim() }, { withCredentials: true });
            setResult(r.data);
        } catch (e) {
            setResult({ success: false, message: e.response?.data?.detail || 'Verification failed' });
        } finally { setLoading(false); }
    };

    return (
        <div className="min-h-screen bg-[#0a0a0a] text-white" data-testid="verify-otp-page">
            <header className="border-b border-zinc-800 px-8 py-5 flex items-center gap-4">
                <button onClick={() => navigate('/home')} data-testid="back-btn" className="p-2 hover:bg-zinc-800"><ArrowLeft size={20} /></button>
                <h1 className="text-xl font-semibold tracking-tight">Verify Applicant OTP</h1>
            </header>
            <main className="max-w-md mx-auto px-6 py-16">
                <div className="bg-zinc-900 border border-zinc-800 p-8 space-y-6">
                    <div className="text-center"><ShieldCheck size={48} className="mx-auto mb-2 text-zinc-600" /><h2 className="text-lg font-semibold">Verify OTP</h2></div>
                    <div className="space-y-1.5"><label className="text-xs text-zinc-500 uppercase tracking-wider">Phone Number</label>
                        <input type="text" value={phone} onChange={e => setPhone(e.target.value)} placeholder="Enter phone number" data-testid="phone-input"
                            className="w-full bg-zinc-800 border border-zinc-700 px-3 py-2 text-sm focus:outline-none focus:border-zinc-500" /></div>
                    <div className="space-y-1.5"><label className="text-xs text-zinc-500 uppercase tracking-wider">OTP</label>
                        <input type="text" value={otp} onChange={e => setOtp(e.target.value)} placeholder="Enter OTP" data-testid="otp-input"
                            className="w-full bg-zinc-800 border border-zinc-700 px-3 py-2 text-sm focus:outline-none focus:border-zinc-500" /></div>
                    <button onClick={handleVerify} disabled={loading} data-testid="verify-btn"
                        className="w-full flex items-center justify-center gap-2 px-4 py-2.5 bg-emerald-700 hover:bg-emerald-600 text-sm font-medium disabled:opacity-50">
                        <ShieldCheck size={16} /> VERIFY OTP
                    </button>
                    {result && (
                        <div className={`p-4 text-center text-sm font-medium rounded ${result.success ? 'bg-emerald-900/30 text-emerald-400 border border-emerald-800/50' : 'bg-red-900/30 text-red-400 border border-red-800/50'}`} data-testid="verify-result">
                            {result.message}
                        </div>
                    )}
                </div>
            </main>
        </div>
    );
}
