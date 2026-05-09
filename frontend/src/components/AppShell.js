import { useState, useEffect } from 'react';
import { NavLink, useNavigate } from 'react-router-dom';
import axios from 'axios';
import { useAuth } from '../context/AuthContext';
import {
    SquaresFour, ChartBar, FileText, CalendarCheck, PencilLine, Table,
    MagnifyingGlass, Briefcase, FolderOpen, GraduationCap, CalendarBlank,
    ShieldCheck, SignOut, List, X, UserCircle, WhatsappLogo, Question,
    EnvelopeSimple, Flask,
} from '@phosphor-icons/react';

const API = process.env.REACT_APP_BACKEND_URL;

const NAV = [
    { label: 'Modules', icon: SquaresFour, path: '/home' },
    { label: 'Analytics Dashboard', icon: ChartBar, path: '/dashboard' },
    { label: 'Hiring Forms', icon: FileText, path: '/hiring-forms' },
    { label: 'Interview Schedule Reports', icon: CalendarCheck, path: '/interview-reports' },
    { label: 'Update Applicants Scores', icon: PencilLine, path: '/update-scores' },
    { label: 'Score & Round', icon: Table, path: '/score-round' },
    { label: 'Candidate Journey', icon: MagnifyingGlass, path: '/candidate-journey' },
    { label: 'Bulk Communication', icon: WhatsappLogo, path: '/whatsapp-resend' },
    { label: 'Manual Applicant Alerts', icon: EnvelopeSimple, path: '/manual-alerts' },
    { label: 'Manual OTP Verify', icon: ShieldCheck, path: '/manual-otp-verify' },
    { label: 'Tester Credentials', icon: Flask, path: '/tester-credentials' },
    { label: 'Create Job Roles', icon: Briefcase, path: '/manage-job-roles' },
    { label: 'Create Job Openings', icon: FolderOpen, path: '/job-openings' },
    { label: 'College Drives', icon: GraduationCap, path: '/college-schedules' },
    { label: 'Set Holidays', icon: CalendarBlank, path: '/set-holidays' },
    { label: 'Verify Applicant OTP', icon: ShieldCheck, path: '/verify-otp' },
    // { label: 'Help & Templates', icon: Question, path: '/help' },
];

export default function AppShell({ children }) {
    const { user, logout } = useAuth();
    const navigate = useNavigate();
    const [open, setOpen] = useState(false);
    const [testMode, setTestMode] = useState(null);

    useEffect(() => {
        let mounted = true;
        axios.get(`${API}/api/messaging/status`, { withCredentials: true })
            .then((r) => { if (mounted) setTestMode(!!r.data?.test_mode); })
            .catch(() => { if (mounted) setTestMode(null); });
        return () => { mounted = false; };
    }, []);

    const handleLogout = async () => {
        await logout();
        navigate('/login');
    };

    const initials = (user || 'A').toString().trim().split(/\s+/).map(s => s[0]).slice(0, 2).join('').toUpperCase() || 'A';

    return (
        <div className="app-shell min-h-screen bg-[#efede5]" data-testid="app-shell">
            {/* Mobile menu trigger */}
            <button
                onClick={() => setOpen(!open)}
                className="lg:hidden fixed top-4 left-4 z-50 p-2 bg-[#faf9f1] border border-[#e5e3d8] rounded-lg shadow-sm"
                data-testid="sidebar-toggle"
                aria-label="Toggle sidebar"
            >
                {open ? <X size={20} className="text-[#1a2332]" /> : <List size={20} className="text-[#1a2332]" />}
            </button>

            {/* Sidebar */}
            <aside
                className={`fixed top-0 left-0 z-40 h-screen w-[260px] bg-[#faf9f1] border-r border-[#e5e3d8] flex flex-col transform transition-transform duration-200 ${open ? 'translate-x-0' : '-translate-x-full'} lg:translate-x-0`}
                data-testid="app-sidebar"
            >
                {/* Logo */}
                <div className="px-6 py-5 border-b border-[#e5e3d8] flex items-center justify-center bg-[#fffdf7]">
                    <img src="/blubridge-logo.webp" alt="BluBridge" className="w-auto object-contain" />
                </div>

                {/* Nav */}
                <nav className="flex-1 overflow-y-auto px-3 py-4">
                    <p className="px-3 text-[10px] font-semibold tracking-[0.18em] text-[#9b9787] uppercase mb-2">Main Menu</p>
                    <ul className="space-y-1">
                        {NAV.map((item) => (
                            <li key={item.path}>
                                <NavLink
                                    to={item.path}
                                    onClick={() => setOpen(false)}
                                    data-testid={`sidenav-${item.path.slice(1) || 'home'}`}
                                    className={({ isActive }) =>
                                        `flex items-center gap-3 px-3 py-2.5 rounded-lg text-[13px] font-medium transition-colors ${
                                            isActive
                                                ? 'bg-[#1d3a8a] text-white shadow-sm'
                                                : 'text-[#3f4655] hover:bg-[#efede5] hover:text-[#1a2332]'
                                        }`
                                    }
                                >
                                    <item.icon size={18} weight="duotone" />
                                    <span className="truncate">{item.label}</span>
                                </NavLink>
                            </li>
                        ))}
                    </ul>
                </nav>

                {/* User block */}
                <div className="border-t border-[#e5e3d8] p-3 bg-[#fffdf7]">
                    <div className="flex items-center gap-3 px-2 py-2">
                        <div className="w-9 h-9 rounded-full bg-[#1d3a8a] text-white flex items-center justify-center text-sm font-semibold flex-shrink-0">
                            {initials}
                        </div>
                        <div className="flex-1 min-w-0">
                            <p className="text-[13px] font-semibold text-[#1a2332] truncate" data-testid="sidenav-user">{user || 'Admin'}</p>
                            <p className="text-[11px] text-[#6b7280]">HR Team</p>
                        </div>
                    </div>
                    <button
                        onClick={handleLogout}
                        data-testid="sidenav-logout-btn"
                        className="mt-2 w-full flex items-center gap-2 px-3 py-2 rounded-lg text-[13px] font-medium text-[#3f4655] hover:bg-[#efede5] hover:text-[#b91c1c] transition-colors"
                    >
                        <SignOut size={16} weight="duotone" />
                        Sign Out
                    </button>
                </div>
            </aside>

            {/* Backdrop on mobile */}
            {open && (
                <div
                    className="lg:hidden fixed inset-0 bg-black/30 z-30"
                    onClick={() => setOpen(false)}
                />
            )}

            {/* Main content */}
            <div className="lg:pl-[260px] min-h-screen">
                {testMode === true && (
                    <div
                        className="sticky top-0 z-30 w-full bg-amber-100 border-b border-amber-300 text-amber-900 text-[12px] font-semibold py-1.5 px-4 flex items-center justify-center gap-2"
                        data-testid="test-mode-banner"
                    >
                        <Flask size={14} weight="fill" />
                        TEST MODE ACTIVE — outbound WhatsApp / Email is delivered only to recipients on the Tester Credentials list.
                    </div>
                )}
                {children}
            </div>
        </div>
    );
}
