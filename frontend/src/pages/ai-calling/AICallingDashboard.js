import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { toast } from 'sonner';
import { Flask, Lock, ShieldCheck, Warning, PhoneSlash, CheckCircle, XCircle } from '@phosphor-icons/react';
import { aiApi, errMsg } from './aiApi';
import { AICallingHeader, Card, SectionTitle } from '../../components/ai-calling/AICallingHeader';

const Stat = ({ label, value, testid }) => (
    <Card className="!p-4">
        <p className="text-[11px] font-semibold tracking-[0.16em] text-[#9b9787] uppercase">{label}</p>
        <p className="text-2xl font-bold text-[#1a2332] mt-1" data-testid={testid}>{value}</p>
    </Card>
);

const Flag = ({ ok, label, testid }) => (
    <li className="flex items-center gap-2 text-sm" data-testid={testid}>
        {ok ? <CheckCircle size={16} weight="fill" className="text-emerald-600" /> : <XCircle size={16} weight="fill" className="text-rose-500" />}
        <span className="text-[#1a2332]">{label}</span>
    </li>
);

export default function AICallingDashboard() {
    const [s, setS] = useState(null);
    useEffect(() => {
        aiApi.get('/summary').then(r => setS(r.data)).catch(e => toast.error(errMsg(e, 'Failed to load summary')));
    }, []);

    return (
        <div className="min-h-screen" data-testid="ai-calling-dashboard">
            <AICallingHeader title="AI Calling" subtitle="Interview confirmation calls — AI Test and AI Live switches" mode={s?.mode} emergencyStop={s?.emergency_stop} />
            <main className="max-w-6xl mx-auto px-6 lg:px-10 py-6 space-y-5">
                <div className="flex items-start gap-3 bg-amber-50 border border-amber-200 rounded-2xl p-4" data-testid="ai-phase-notice">
                    <Warning size={20} weight="duotone" className="text-amber-700 shrink-0 mt-0.5" />
                    <p className="text-sm text-amber-900">No calls can be placed in this phase: the emergency stop is on, server calling is off and Live dispatch is not authorised. Saving or uploading test recipients never starts a call.</p>
                </div>
                <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
                    <Stat label="Test candidates" value={s?.test_candidates ?? '–'} testid="stat-test-candidates" />
                    <Stat label="Consented" value={s?.consented_candidates ?? '–'} testid="stat-consented" />
                    <Stat label="Test batches" value={s?.batches ?? '–'} testid="stat-batches" />
                    <Stat label="Calls recorded" value={s?.calls_total ?? '–'} testid="stat-calls" />
                </div>
                <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
                    <Card>
                        <SectionTitle icon={ShieldCheck}>Safety status</SectionTitle>
                        <ul className="space-y-2">
                            <Flag ok={!s?.server_calling_enabled} label={`Server-side calling ${s?.server_calling_enabled ? 'ENABLED' : 'disabled'}`} testid="flag-server" />
                            <Flag ok={!s?.bolna_integration_approved} label={`Bolna integration ${s?.bolna_integration_approved ? 'approved' : 'not approved (no API calls)'}`} testid="flag-bolna" />
                            <Flag ok={s?.live_mode_locked} label="Live dispatch locked" testid="flag-live" />
                            <Flag ok={!s?.emergency_stop} label={s?.emergency_stop ? 'Emergency stop ACTIVE' : 'Emergency stop not active'} testid="flag-estop" />
                        </ul>
                    </Card>
                    <Card>
                        <SectionTitle icon={Flask}>Next steps</SectionTitle>
                        <div className="space-y-2 text-sm">
                            <Link to="/ai-calling/testing" data-testid="goto-testing" className="flex items-center gap-2 text-teal-800 font-semibold hover:underline"><Flask size={16} /> Manage test candidates</Link>
                            <Link to="/ai-calling/live" data-testid="goto-live" className="flex items-center gap-2 text-[#6b7280] hover:underline"><Lock size={16} /> Live Mode (locked)</Link>
                            <Link to="/ai-calling/history" data-testid="goto-history" className="flex items-center gap-2 text-[#6b7280] hover:underline"><PhoneSlash size={16} /> Call history ({s?.calls_testing ?? 0} test / {s?.calls_live ?? 0} live)</Link>
                        </div>
                    </Card>
                </div>
            </main>
        </div>
    );
}
