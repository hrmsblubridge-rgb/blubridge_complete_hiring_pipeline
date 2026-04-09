import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import axios from 'axios';
import { toast } from 'sonner';
import { ArrowLeft, Users, SpinnerGap } from '@phosphor-icons/react';

const API = process.env.REACT_APP_BACKEND_URL;

export default function Roles() {
    const navigate = useNavigate();
    const [roles, setRoles] = useState([]);
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        let mounted = true;
        const fetchRoles = async () => {
            try {
                const res = await axios.get(`${API}/api/job-roles`, { withCredentials: true });
                if (mounted) setRoles(res.data.job_roles);
            } catch (err) {
                if (mounted) toast.error('Failed to load job roles');
            } finally {
                if (mounted) setLoading(false);
            }
        };
        fetchRoles();
        return () => { mounted = false; };
    }, []);

    return (
        <div className="min-h-screen bg-[#0a0a0a] text-white" data-testid="roles-page">
            <header className="border-b border-zinc-800 px-8 py-5 flex items-center gap-4">
                <button onClick={() => navigate('/dashboard')} data-testid="back-btn"
                    className="p-2 hover:bg-zinc-800 transition-colors">
                    <ArrowLeft size={20} />
                </button>
                <h1 className="text-xl font-semibold tracking-tight">View Applicants</h1>
            </header>

            <main className="px-8 py-8">
                {loading ? (
                    <div className="flex items-center justify-center py-20" data-testid="loading-spinner">
                        <SpinnerGap size={32} className="animate-spin text-zinc-500" />
                    </div>
                ) : roles.length === 0 ? (
                    <div className="text-center py-20 text-zinc-500" data-testid="empty-state">
                        No registered applicants found. Upload both datasets to see role-wise data.
                    </div>
                ) : (
                    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4" data-testid="roles-grid">
                        {roles.map((role, i) => (
                            <button key={i}
                                onClick={() => navigate(`/roles/${encodeURIComponent(role.job_role)}`)}
                                data-testid={`role-card-${i}`}
                                className="text-left bg-zinc-900 border border-zinc-800 hover:border-violet-600 px-5 py-5 transition-all group">
                                <div className="flex items-start justify-between gap-3">
                                    <div className="min-w-0">
                                        <div className="text-base font-medium truncate group-hover:text-violet-400 transition-colors">
                                            {role.job_role}
                                        </div>
                                        <div className="text-sm text-zinc-500 mt-1">Registered Applicants</div>
                                    </div>
                                    <div className="flex items-center gap-1.5 shrink-0">
                                        <Users size={16} className="text-zinc-600" />
                                        <span className="text-2xl font-semibold tabular-nums text-zinc-300">{role.count}</span>
                                    </div>
                                </div>
                            </button>
                        ))}
                    </div>
                )}
            </main>
        </div>
    );
}
