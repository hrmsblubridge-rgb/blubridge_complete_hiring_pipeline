import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import axios from 'axios';
import { toast } from 'sonner';
import { ArrowLeft, SpinnerGap, UserCheck } from '@phosphor-icons/react';

const API = process.env.REACT_APP_BACKEND_URL;

export default function AttendedRoles() {
    const navigate = useNavigate();
    const [roles, setRoles] = useState([]);
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        (async () => {
            try {
                const res = await axios.get(`${API}/api/attended-roles`, { withCredentials: true });
                setRoles(res.data.job_roles || []);
            } catch { toast.error('Failed to load attended roles'); }
            finally { setLoading(false); }
        })();
    }, []);

    return (
        <div className="min-h-screen bg-[#0a0a0a] text-white" data-testid="attended-roles-page">
            <header className="border-b border-zinc-800 px-8 py-5 flex items-center gap-4">
                <button onClick={() => navigate('/dashboard')} data-testid="back-btn" className="p-2 hover:bg-zinc-800 transition-colors">
                    <ArrowLeft size={20} />
                </button>
                <div>
                    <h1 className="text-xl font-semibold tracking-tight">Attended Applicants</h1>
                    <p className="text-sm text-zinc-500">Select a job role to view attended applicants with scores</p>
                </div>
            </header>

            <div className="px-8 py-8">
                {loading ? (
                    <div className="flex justify-center py-20"><SpinnerGap size={32} className="animate-spin text-zinc-500" /></div>
                ) : roles.length === 0 ? (
                    <div className="text-center py-20 text-zinc-500" data-testid="empty-state">No attended applicants found.</div>
                ) : (
                    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4" data-testid="roles-grid">
                        {roles.map((r, i) => (
                            <button key={i} onClick={() => navigate(`/attended/${encodeURIComponent(r.job_role)}`)}
                                data-testid={`attended-role-card-${i}`}
                                className="flex items-center gap-4 px-6 py-5 bg-zinc-900 border border-zinc-800 hover:border-emerald-600 transition-all text-left group">
                                <UserCheck size={24} className="text-emerald-500 shrink-0" />
                                <div className="min-w-0 flex-1">
                                    <p className="font-medium truncate group-hover:text-emerald-400 transition-colors">{r.job_role}</p>
                                    <p className="text-sm text-zinc-500">{r.count} attended</p>
                                </div>
                            </button>
                        ))}
                    </div>
                )}
            </div>
        </div>
    );
}
