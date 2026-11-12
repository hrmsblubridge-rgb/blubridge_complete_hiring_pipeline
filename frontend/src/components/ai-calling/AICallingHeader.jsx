import { NavLink } from 'react-router-dom';
import { PhoneCall } from '@phosphor-icons/react';
import { MODE_STYLES } from '../../pages/ai-calling/aiApi';
import { GlobalEmergencyStopBar } from './GlobalEmergencyStopBar';
import { useSafetyStatus } from './useSafetyStatus';

const TABS = [
    { to: '/ai-calling', label: 'Dashboard', end: true },
    { to: '/ai-calling/testing', label: 'Testing Mode' },
    { to: '/ai-calling/live', label: 'Live Mode' },
    { to: '/ai-calling/pending-authorization', label: 'Pending Authorization' },
    { to: '/ai-calling/history', label: 'Call History' },
    { to: '/ai-calling/settings', label: 'Settings' },
];

// Shared across every AI Calling page. All callers derive mode/emergency-stop state from one
// authoritative /safety-status read, never from per-page /summary or /settings copies.
export const AICallingHeader = ({ title, subtitle }) => {
    const { safety, loading, refresh } = useSafetyStatus();
    const estop = !!safety?.emergency_stop?.active;
    const mode = safety?.switches?.ai_live_enabled ? 'live' : safety?.switches?.ai_test_enabled ? 'testing' : 'off';
    return (
        <>
            <GlobalEmergencyStopBar safety={safety} loading={loading} onChanged={refresh} />
            <header className="bg-[#faf9f1] border-b border-[#e5e3d8] px-6 lg:px-10 pt-5" data-testid="ai-calling-header">
                <div className="max-w-6xl mx-auto pl-12 lg:pl-0">
                    <div className="flex flex-wrap items-center gap-3">
                        <div className="w-10 h-10 rounded-xl flex items-center justify-center bg-teal-100">
                            <PhoneCall size={22} weight="duotone" className="text-teal-700" />
                        </div>
                        <div className="flex-1 min-w-0">
                            <h1 className="text-xl lg:text-2xl font-bold text-[#1a2332] tracking-tight">{title}</h1>
                            <p className="text-xs text-[#6b7280] mt-0.5">{subtitle}</p>
                        </div>
                        <span data-testid="ai-mode-badge" className={`px-3 py-1 rounded-full border text-[11px] font-bold uppercase tracking-wider ${MODE_STYLES[mode]}`}>
                            Mode: {mode}
                        </span>
                        {estop && (
                            <span data-testid="ai-estop-badge" className="px-3 py-1 rounded-full border border-rose-300 bg-rose-100 text-rose-800 text-[11px] font-bold uppercase tracking-wider">
                                Emergency Stop ON
                            </span>
                        )}
                    </div>
                    <nav className="flex gap-1 mt-4 overflow-x-auto" data-testid="ai-calling-tabs">
                        {TABS.map(t => (
                            <NavLink key={t.to} to={t.to} end={t.end} data-testid={`ai-tab-${t.label.toLowerCase().replace(/\s+/g, '-')}`}
                                className={({ isActive }) => `px-4 py-2.5 text-[13px] font-semibold whitespace-nowrap border-b-2 transition-colors ${isActive ? 'border-teal-600 text-teal-800' : 'border-transparent text-[#6b7280] hover:text-[#1a2332]'}`}>
                                {t.label}
                            </NavLink>
                        ))}
                    </nav>
                </div>
            </header>
        </>
    );
};

export const Card = ({ children, className = '', ...rest }) => (
    <div className={`bg-[#fffdf7] border border-[#e5e3d8] rounded-2xl p-5 ${className}`} {...rest}>{children}</div>
);

export const SectionTitle = ({ icon: Icon, children }) => (
    <div className="flex items-center gap-2 mb-3">
        {Icon && <Icon size={18} weight="duotone" className="text-teal-700" />}
        <h2 className="text-sm font-semibold text-[#1a2332]">{children}</h2>
    </div>
);
