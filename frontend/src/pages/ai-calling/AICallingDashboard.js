import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { toast } from 'sonner';
import { Flask, Lock, ShieldCheck, PhoneSlash, CheckCircle, XCircle, Warning } from '@phosphor-icons/react';
import { aiApi, errMsg } from './aiApi';
import { AICallingHeader, Card, SectionTitle } from '../../components/ai-calling/AICallingHeader';
import { LiveWorkerStatus } from '../../components/ai-calling/LiveWorkerStatus';
import { useSafetyStatus } from '../../components/ai-calling/useSafetyStatus';

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
    const { safety } = useSafetyStatus();
    useEffect(() => {
        aiApi.get('/summary').then(r => setS(r.data)).catch(e => toast.error(errMsg(e, 'Failed to load summary')));
    }, []);

    const estop = !!safety?.emergency_stop?.active;
    const srv = !!safety?.server?.outbound_calling_enabled;
    const liveAuth = !!safety?.switches?.live_dispatch_authorized;
    const providerReady = !!safety?.provider?.ready;
    const statusUnavailable = safety && safety.authoritative === false;

    return (
        <div className="min-h-screen" data-testid="ai-calling-dashboard">
            <AICallingHeader title="AI Calling" subtitle="Interview confirmation calls — AI Test and AI Live switches" />
            <main className="max-w-6xl mx-auto px-6 lg:px-10 py-6 space-y-5">
                {statusUnavailable ? (
                    <div className="flex items-start gap-3 bg-rose-50 border border-rose-200 rounded-2xl p-4" data-testid="ai-phase-notice-unavailable">
                        <Warning size={20} weight="fill" className="text-rose-700 shrink-0 mt-0.5" />
                        <p className="text-sm text-rose-900 font-semibold">Safety status unavailable — calling blocked.</p>
                    </div>
                ) : (
                    <div className="flex items-start gap-3 bg-amber-50 border border-amber-200 rounded-2xl p-4" data-testid="ai-phase-notice">
                        <Warning size={20} weight="duotone" className="text-amber-700 shrink-0 mt-0.5" />
                        <p className="text-sm text-amber-900">
                            Current gates: Emergency Stop is <b>{estop ? 'ON' : 'OFF'}</b>, Server Outbound Calling is <b>{srv ? 'ON' : 'OFF'}</b>,
                            Live Dispatch Authorization is <b>{liveAuth ? 'ON' : 'OFF'}</b>. Any one of these being OFF is enough to block a real call.
                            Saving or uploading test recipients never starts a call.
                        </p>
                    </div>
                )}
                <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
                    <Stat label="Test candidates" value={s?.test_candidates ?? '–'} testid="stat-test-candidates" />
                    <Stat label="Consented" value={s?.consented_candidates ?? '–'} testid="stat-consented" />
                    <Stat label="Test batches" value={s?.batches ?? '–'} testid="stat-batches" />
                    <Stat label="Calls recorded" value={s?.calls_total ?? '–'} testid="stat-calls" />
                </div>
                <LiveWorkerStatus />
                <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
                    <Card>
                        <SectionTitle icon={ShieldCheck}>Safety status</SectionTitle>
                        {statusUnavailable ? (
                            <p className="text-sm text-rose-700 font-semibold" data-testid="dashboard-safety-unavailable">
                                Safety status unavailable — calling blocked.
                            </p>
                        ) : (
                            <ul className="space-y-2">
                                <Flag ok={!estop} label={`Emergency Stop ${estop ? 'ON (overrides everything)' : 'OFF'}`} testid="flag-estop" />
                                <Flag ok={srv} label={`Server Outbound Calling ${srv ? 'enabled' : 'disabled (deployment-level)'}`} testid="flag-server" />
                                <Flag ok={liveAuth} label={`Live Dispatch Authorization ${liveAuth ? 'granted' : 'OFF'}`} testid="flag-live" />
                                <Flag ok={providerReady} label={`Bolna provider ${providerReady ? 'verified' : 'not verified'}`} testid="flag-bolna" />
                            </ul>
                        )}
                        <p className="text-[11px] text-[#9b9787] mt-3">
                            All AI Calling tabs read this same authoritative state. Change it from Settings → Safety Controls.
                        </p>
                    </Card>
                    <Card>
                        <SectionTitle icon={Flask}>Next steps</SectionTitle>
                        <div className="space-y-2 text-sm">
                            <Link to="/ai-calling/testing" data-testid="goto-testing" className="flex items-center gap-2 text-teal-800 font-semibold hover:underline"><Flask size={16} /> Manage test candidates</Link>
                            <Link to="/ai-calling/live" data-testid="goto-live" className="flex items-center gap-2 text-[#6b7280] hover:underline"><Lock size={16} /> Live Mode</Link>
                            <Link to="/ai-calling/history" data-testid="goto-history" className="flex items-center gap-2 text-[#6b7280] hover:underline"><PhoneSlash size={16} /> Call history ({s?.calls_testing ?? 0} test / {s?.calls_live ?? 0} live)</Link>
                            <Link to="/ai-calling/settings" data-testid="goto-settings" className="flex items-center gap-2 text-[#6b7280] hover:underline"><ShieldCheck size={16} /> Settings → Safety Controls</Link>
                        </div>
                    </Card>
                </div>
            </main>
        </div>
    );
}
