/**
 * Profile (iter77) — view profile info + change password.
 */
import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import axios from 'axios';
import { toast } from 'sonner';
import { ArrowLeft, User, Lock, Eye, EyeSlash, CheckCircle, Shield } from '@phosphor-icons/react';

const API = process.env.REACT_APP_BACKEND_URL;

export default function Profile() {
    const navigate = useNavigate();
    const [me, setMe] = useState(null);
    const [oldPw, setOldPw] = useState('');
    const [newPw, setNewPw] = useState('');
    const [confirmPw, setConfirmPw] = useState('');
    const [showOld, setShowOld] = useState(false);
    const [showNew, setShowNew] = useState(false);
    const [submitting, setSubmitting] = useState(false);

    useEffect(() => {
        axios.get(`${API}/api/me`, { withCredentials: true })
            .then(r => setMe(r.data))
            .catch(() => navigate('/login'));
    }, [navigate]);

    const submit = async (e) => {
        e.preventDefault();
        if (!oldPw || !newPw || !confirmPw) {
            toast.error('All fields are required');
            return;
        }
        if (newPw !== confirmPw) {
            toast.error('New password and confirmation do not match');
            return;
        }
        if (newPw.length < 6) {
            toast.error('New password must be at least 6 characters');
            return;
        }
        setSubmitting(true);
        try {
            await axios.post(`${API}/api/auth/change-password`,
                { old_password: oldPw, new_password: newPw },
                { withCredentials: true });
            toast.success('Password updated successfully');
            setOldPw(''); setNewPw(''); setConfirmPw('');
        } catch (err) {
            toast.error(err.response?.data?.detail || 'Failed to update password');
        } finally { setSubmitting(false); }
    };

    const initials = (me?.username || 'A').split(' ').map(s => s[0]).join('').slice(0, 2).toUpperCase();

    return (
        <div className="min-h-screen" data-testid="profile-page">
            <header className="bg-[#faf9f1] border-b border-[#e5e3d8] px-6 lg:px-10 py-5">
                <div className="max-w-4xl mx-auto flex items-center gap-3 pl-12 lg:pl-0">
                    <button onClick={() => navigate('/home')} data-testid="back-btn"
                        className="p-2 rounded-lg hover:bg-[#efede5]">
                        <ArrowLeft size={18} className="text-[#1a2332]" />
                    </button>
                    <div className="w-10 h-10 rounded-xl flex items-center justify-center" style={{ backgroundColor: '#1d3a8a20' }}>
                        <User size={22} weight="duotone" color="#1d3a8a" />
                    </div>
                    <div>
                        <h1 className="text-xl lg:text-2xl font-bold text-[#1a2332] tracking-tight">My Profile</h1>
                        <p className="text-xs text-[#6b7280] mt-0.5">View account info and manage your password</p>
                    </div>
                </div>
            </header>

            <main className="px-6 lg:px-10 py-8 max-w-4xl mx-auto space-y-6">
                {/* Profile card */}
                <section className="bg-[#fffdf7] border border-[#e5e3d8] rounded-2xl p-6" data-testid="profile-card">
                    <div className="flex items-center gap-5">
                        <div className="w-20 h-20 rounded-full bg-[#1d3a8a] text-white flex items-center justify-center text-2xl font-bold">
                            {initials}
                        </div>
                        <div>
                            <p className="text-xl font-bold text-[#1a2332]" data-testid="profile-username">{me?.username || '—'}</p>
                            <div className="mt-1 flex items-center gap-2">
                                <Shield size={14} weight="fill" className="text-[#1d3a8a]" />
                                <span className="text-sm font-medium text-[#3f4655] capitalize">{me?.role || 'admin'}</span>
                            </div>
                            {me?.password_updated_at && (
                                <p className="text-xs text-[#6b7280] mt-2">
                                    Password last changed:{' '}
                                    <span className="font-mono">{new Date(me.password_updated_at).toLocaleString()}</span>
                                </p>
                            )}
                        </div>
                    </div>
                </section>

                {/* Change Password */}
                <section className="bg-[#fffdf7] border border-[#e5e3d8] rounded-2xl p-6" data-testid="change-password-section">
                    <div className="flex items-center gap-2 mb-4">
                        <Lock size={18} weight="duotone" className="text-[#1d3a8a]" />
                        <h2 className="text-lg font-bold text-[#1a2332]">Change Password</h2>
                    </div>
                    <form onSubmit={submit} className="space-y-4 max-w-md">
                        <PasswordField
                            label="Current Password" value={oldPw} onChange={setOldPw}
                            show={showOld} toggle={() => setShowOld(s => !s)}
                            testId="old-password" />
                        <PasswordField
                            label="New Password" value={newPw} onChange={setNewPw}
                            show={showNew} toggle={() => setShowNew(s => !s)}
                            testId="new-password" hint="At least 6 characters" />
                        <PasswordField
                            label="Confirm New Password" value={confirmPw} onChange={setConfirmPw}
                            show={showNew} toggle={() => setShowNew(s => !s)}
                            testId="confirm-password" />
                        <button type="submit" disabled={submitting}
                            data-testid="change-password-submit"
                            className="w-full px-4 py-2.5 rounded-lg text-white text-sm font-semibold flex items-center justify-center gap-2 disabled:opacity-50"
                            style={{ backgroundColor: '#1d3a8a' }}>
                            <CheckCircle size={16} weight="bold" />
                            {submitting ? 'Updating…' : 'Update Password'}
                        </button>
                    </form>
                </section>
            </main>
        </div>
    );
}

function PasswordField({ label, value, onChange, show, toggle, testId, hint }) {
    return (
        <div>
            <label className="block text-xs font-semibold text-[#374151] mb-1.5">{label}</label>
            <div className="relative">
                <input
                    type={show ? 'text' : 'password'}
                    value={value}
                    onChange={(e) => onChange(e.target.value)}
                    data-testid={testId}
                    className="w-full px-3 py-2.5 pr-10 rounded-lg border border-[#e5e3d8] bg-[#faf9f1] text-sm text-[#1a2332] focus:outline-none focus:border-[#1d3a8a] focus:ring-1 focus:ring-[#1d3a8a]"
                />
                <button type="button" onClick={toggle}
                    className="absolute right-2 top-1/2 -translate-y-1/2 p-1 text-[#6b7280] hover:text-[#1a2332]">
                    {show ? <EyeSlash size={16} /> : <Eye size={16} />}
                </button>
            </div>
            {hint && <p className="mt-1 text-xs text-[#6b7280]">{hint}</p>}
        </div>
    );
}
