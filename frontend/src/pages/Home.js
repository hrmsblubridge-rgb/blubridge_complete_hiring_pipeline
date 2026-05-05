import { useNavigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import { ChartBar, FileText, CalendarCheck, PencilLine, Briefcase, FolderOpen, SignOut, CalendarBlank, ShieldCheck, GraduationCap } from '@phosphor-icons/react';

const NAV_ITEMS = [
    { label: 'Analytics Dashboard', desc: 'Upload datasets, view summaries and applicants', icon: ChartBar, path: '/dashboard', color: 'amber' },
    { label: 'Hiring Forms', desc: 'Create form types and application forms with conditions', icon: FileText, path: '/hiring-forms', color: 'violet' },
    { label: 'Interview Schedule Reports', desc: 'View and export interview schedule data', icon: CalendarCheck, path: '/interview-reports', color: 'cyan' },
    { label: 'Update Applicants Scores', desc: 'Manage rounds and update candidate scores', icon: PencilLine, path: '/update-scores', color: 'emerald' },
    { label: 'Create Job Roles', desc: 'Define and manage job titles', icon: Briefcase, path: '/manage-job-roles', color: 'blue' },
    { label: 'Create Job Openings', desc: 'Publish job openings for recruitment', icon: FolderOpen, path: '/job-openings', color: 'rose' },
    { label: 'College Drives', desc: 'Configure interview schedules per college and role', icon: GraduationCap, path: '/college-schedules', color: 'pink' },
    { label: 'Set Holidays', desc: 'Configure holidays to block interview scheduling', icon: CalendarBlank, path: '/set-holidays', color: 'orange' },
    { label: 'Verify Applicant OTP', desc: 'Verify applicant attendance via phone and OTP', icon: ShieldCheck, path: '/verify-otp', color: 'teal' },
];

const COLOR_MAP = {
    amber: { border: 'hover:border-amber-600', icon: 'group-hover:text-amber-500' },
    violet: { border: 'hover:border-violet-600', icon: 'group-hover:text-violet-500' },
    cyan: { border: 'hover:border-cyan-600', icon: 'group-hover:text-cyan-500' },
    emerald: { border: 'hover:border-emerald-600', icon: 'group-hover:text-emerald-500' },
    blue: { border: 'hover:border-blue-600', icon: 'group-hover:text-blue-500' },
    rose: { border: 'hover:border-rose-600', icon: 'group-hover:text-rose-500' },
    pink: { border: 'hover:border-pink-600', icon: 'group-hover:text-pink-500' },
    orange: { border: 'hover:border-orange-600', icon: 'group-hover:text-orange-500' },
    teal: { border: 'hover:border-teal-600', icon: 'group-hover:text-teal-500' },
};

export default function Home() {
    const { logout } = useAuth();
    const navigate = useNavigate();

    const handleLogout = async () => {
        try { await fetch(`${process.env.REACT_APP_BACKEND_URL}/api/logout`, { method: 'POST', credentials: 'include' }); } catch {}
        logout();
        navigate('/login');
    };

    return (
        <div className="min-h-screen bg-[#0a0a0a] text-white" data-testid="home-page">
            <header className="border-b border-zinc-800 px-8 py-5 flex items-center justify-between">
                <h1 className="text-xl font-semibold tracking-tight">BluBridge Hiring Pipeline</h1>
                <button onClick={handleLogout} data-testid="logout-btn"
                    className="flex items-center gap-2 text-sm text-zinc-400 hover:text-white transition-colors">
                    <SignOut size={18} /> Logout
                </button>
            </header>
            <main className="max-w-3xl mx-auto px-6 py-12 space-y-4">
                <h2 className="text-sm font-medium text-zinc-500 uppercase tracking-widest mb-2">Modules</h2>
                {NAV_ITEMS.map((item) => {
                    const c = COLOR_MAP[item.color];
                    return (
                        <button key={item.path} onClick={() => navigate(item.path)} data-testid={`nav-${item.path.slice(1)}`}
                            className={`w-full flex items-center gap-4 px-6 py-5 bg-zinc-900 border border-zinc-800 ${c.border} hover:bg-zinc-900/80 transition-all group text-left`}>
                            <item.icon size={28} className={`text-zinc-500 ${c.icon} transition-colors`} />
                            <div>
                                <div className="text-base font-medium">{item.label}</div>
                                <div className="text-sm text-zinc-500 mt-0.5">{item.desc}</div>
                            </div>
                        </button>
                    );
                })}
            </main>
        </div>
    );
}
