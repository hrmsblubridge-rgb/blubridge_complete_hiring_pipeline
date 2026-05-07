import { useNavigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import { ChartBar, FileText, CalendarCheck, PencilLine, Briefcase, FolderOpen, CalendarBlank, ShieldCheck, GraduationCap, MagnifyingGlass, Table, ArrowRight } from '@phosphor-icons/react';

const NAV_ITEMS = [
    { label: 'Analytics Dashboard', desc: 'Upload datasets, view summaries and applicants', icon: ChartBar, path: '/dashboard', tone: 'blue' },
    { label: 'Hiring Forms', desc: 'Create form types and application forms with conditions', icon: FileText, path: '/hiring-forms', tone: 'violet' },
    { label: 'Interview Schedule Reports', desc: 'View and export interview schedule data', icon: CalendarCheck, path: '/interview-reports', tone: 'cyan' },
    { label: 'Update Applicants Scores', desc: 'Manage rounds and update candidate scores', icon: PencilLine, path: '/update-scores', tone: 'emerald' },
    { label: 'Score & Round', desc: 'Excel-like table — per-round scores, status, induction dates', icon: Table, path: '/score-round', tone: 'sky' },
    { label: 'Candidate Journey', desc: 'View full lifecycle — rounds, scores, status, induction date', icon: MagnifyingGlass, path: '/candidate-journey', tone: 'indigo' },
    { label: 'Create Job Roles', desc: 'Define and manage job titles', icon: Briefcase, path: '/manage-job-roles', tone: 'navy' },
    { label: 'Create Job Openings', desc: 'Publish job openings for recruitment', icon: FolderOpen, path: '/job-openings', tone: 'rose' },
    { label: 'College Drives', desc: 'Configure interview schedules per college and role', icon: GraduationCap, path: '/college-schedules', tone: 'pink' },
    { label: 'Set Holidays', desc: 'Configure holidays to block interview scheduling', icon: CalendarBlank, path: '/set-holidays', tone: 'orange' },
    { label: 'Verify Applicant OTP', desc: 'Verify applicant attendance via phone and OTP', icon: ShieldCheck, path: '/verify-otp', tone: 'teal' },
];

const TONE = {
    blue:    { bg: 'bg-blue-50',    fg: 'text-blue-600',    ring: 'ring-blue-100' },
    violet:  { bg: 'bg-violet-50',  fg: 'text-violet-600',  ring: 'ring-violet-100' },
    cyan:    { bg: 'bg-cyan-50',    fg: 'text-cyan-600',    ring: 'ring-cyan-100' },
    emerald: { bg: 'bg-emerald-50', fg: 'text-emerald-600', ring: 'ring-emerald-100' },
    sky:     { bg: 'bg-sky-50',     fg: 'text-sky-600',     ring: 'ring-sky-100' },
    indigo:  { bg: 'bg-indigo-50',  fg: 'text-indigo-600',  ring: 'ring-indigo-100' },
    navy:    { bg: 'bg-[#e8ecf6]',  fg: 'text-[#1d3a8a]',   ring: 'ring-[#dde3f2]' },
    rose:    { bg: 'bg-rose-50',    fg: 'text-rose-600',    ring: 'ring-rose-100' },
    pink:    { bg: 'bg-pink-50',    fg: 'text-pink-600',    ring: 'ring-pink-100' },
    orange:  { bg: 'bg-orange-50',  fg: 'text-orange-600',  ring: 'ring-orange-100' },
    teal:    { bg: 'bg-teal-50',    fg: 'text-teal-600',    ring: 'ring-teal-100' },
};

export default function Home() {
    const { user } = useAuth();
    const navigate = useNavigate();

    const today = new Date().toLocaleDateString('en-US', { weekday: 'long', month: 'long', day: 'numeric', year: 'numeric' });

    return (
        <div className="min-h-screen" data-testid="home-page">
            {/* Page header */}
            <header className="bg-[#faf9f1] border-b border-[#e5e3d8] px-6 lg:px-10 py-6">
                <div className="mx-auto flex items-center justify-between flex-wrap gap-4">
                    <div className="pl-12 lg:pl-0">
                        <h1 className="text-2xl lg:text-3xl font-bold text-[#1a2332] tracking-tight">Welcome{user ? `, ${user.split(' ')[0]}` : ''}</h1>
                        <p className="text-sm text-[#6b7280] mt-1">{today}</p>
                    </div>
                    <div className="hidden md:flex items-center gap-2 text-xs font-semibold tracking-[0.16em] text-[#9b9787] uppercase">
                        <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse"></span>
                        BluBridge Hiring Pipeline
                    </div>
                </div>
            </header>

            <main className="mx-auto px-6 lg:px-10 py-8">
                <div className="mb-6">
                    <p className="text-[11px] font-semibold tracking-[0.2em] text-[#9b9787] uppercase">Modules</p>
                    <h2 className="text-xl font-semibold text-[#1a2332] mt-1">Choose a workspace to get started</h2>
                </div>

                <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-3 gap-4">
                    {NAV_ITEMS.map((item) => {
                        const t = TONE[item.tone];
                        return (
                            <button
                                key={item.path}
                                onClick={() => navigate(item.path)}
                                data-testid={`nav-${item.path.slice(1)}`}
                                className={`group relative text-left p-5 bg-[#fffdf7] border border-[#e5e3d8] rounded-2xl hover:shadow-md hover:-translate-y-0.5 hover:border-[#1d3a8a]/30 transition-all duration-200`}
                            >
                                <div className="flex items-start justify-between gap-3">
                                    <div className={`w-11 h-11 rounded-xl ${t.bg} ring-4 ${t.ring} flex items-center justify-center shrink-0`}>
                                        <item.icon size={22} weight="duotone" className={t.fg} />
                                    </div>
                                    <ArrowRight size={18} className="text-[#c8c6ba] group-hover:text-[#1d3a8a] group-hover:translate-x-0.5 transition-all" />
                                </div>
                                <div className="mt-4">
                                    <h3 className="text-[15px] font-semibold text-[#1a2332] leading-snug">{item.label}</h3>
                                    <p className="text-[13px] text-[#6b7280] mt-1 leading-relaxed">{item.desc}</p>
                                </div>
                            </button>
                        );
                    })}
                </div>
            </main>
        </div>
    );
}
