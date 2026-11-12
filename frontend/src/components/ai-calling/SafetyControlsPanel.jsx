// Settings → Safety Controls.
// Displays every component of the authoritative safety state in one place, with the
// RELEASE Emergency Stop action (requires typed confirmation). Release never enables calling.
import { useState } from 'react';
import { toast } from 'sonner';
import { Siren, ShieldCheck, Warning, CheckCircle, XCircle, Spinner, Lock } from '@phosphor-icons/react';
import { aiApi, errMsg } from '../../pages/ai-calling/aiApi';
import { Card, SectionTitle } from './AICallingHeader';
import {
    Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter,
} from '../ui/dialog';

const Row = ({ ok, label, detail, testid, warn }) => (
    <li className="flex items-start gap-2 text-sm py-1" data-testid={testid}>
        {ok
            ? <CheckCircle size={16} weight="fill" className="text-emerald-600 mt-0.5" />
            : warn
                ? <Warning size={16} weight="fill" className="text-amber-600 mt-0.5" />
                : <XCircle size={16} weight="fill" className="text-rose-600 mt-0.5" />}
        <div className="flex-1">
            <p className="text-[#1a2332]"><b>{label}</b></p>
            {detail && <p className="text-xs text-[#6b7280]">{detail}</p>}
        </div>
    </li>
);

export const SafetyControlsPanel = ({ safety, loading, onChanged }) => {
    const [releaseOpen, setReleaseOpen] = useState(false);
    const [typed, setTyped] = useState('');
    const [reason, setReason] = useState('');
    const [busy, setBusy] = useState(false);

    if (loading && !safety) {
        return (
            <Card data-testid="safety-controls-loading">
                <SectionTitle icon={ShieldCheck}>Safety Controls</SectionTitle>
                <p className="text-sm text-[#6b7280] flex items-center gap-2"><Spinner size={14} className="animate-spin" /> Loading authoritative safety status…</p>
            </Card>
        );
    }
    if (!safety || safety.authoritative === false) {
        return (
            <Card data-testid="safety-controls-unavailable" className="border-rose-200">
                <SectionTitle icon={Warning}>Safety Controls</SectionTitle>
                <div className="bg-rose-50 border border-rose-200 rounded-xl px-3 py-2 text-sm text-rose-900 font-semibold">
                    Safety status unavailable — calling blocked.
                </div>
            </Card>
        );
    }
    const es = safety.emergency_stop || {};
    const sw = safety.switches || {};
    const sv = safety.server || {};
    const pv = safety.provider || {};
    const eff = safety.effective || {};
    const esActive = !!es.active;

    const release = async () => {
        if (typed !== 'RELEASE EMERGENCY STOP') { toast.error('Type the exact confirmation phrase'); return; }
        setBusy(true);
        try {
            await aiApi.post('/emergency-stop', { active: false, reason: reason.trim(), confirmation: 'RELEASE EMERGENCY STOP' });
            toast.success('Emergency Stop released. Calling is still blocked by the other gates.');
            setReleaseOpen(false); setTyped(''); setReason(''); onChanged?.();
        } catch (e) { toast.error(errMsg(e, 'Failed to release Emergency Stop')); } finally { setBusy(false); }
    };

    return (
        <Card data-testid="safety-controls-panel">
            <SectionTitle icon={ShieldCheck}>Safety Controls</SectionTitle>
            <p className="text-xs text-[#6b7280] mb-3">
                Every AI Calling screen reads this same authoritative state. Releasing Emergency Stop does NOT enable calling —
                each gate below must independently permit it.
            </p>

            {/* Emergency Stop */}
            <div className={`rounded-xl border p-3 mb-4 ${esActive ? 'bg-rose-50 border-rose-200' : 'bg-amber-50 border-amber-200'}`}
                data-testid="safety-estop-block">
                <div className="flex flex-wrap items-start justify-between gap-3">
                    <div className="flex items-start gap-2">
                        <Siren size={20} weight={esActive ? 'fill' : 'duotone'} className={esActive ? 'text-rose-700' : 'text-amber-700'} />
                        <div>
                            <p className="text-sm font-bold text-[#1a2332]">
                                Global Emergency Stop: <span data-testid="safety-estop-state">{esActive ? 'ON' : 'OFF'}</span>
                            </p>
                            {esActive && es.engaged_by && (
                                <p className="text-xs text-[#6b7280]">
                                    Engaged by <b>{es.engaged_by}</b> · {new Date(es.engaged_at).toLocaleString()}
                                    {es.engaged_reason ? ` · reason: ${es.engaged_reason}` : ''}
                                </p>
                            )}
                            {!esActive && es.released_by && (
                                <p className="text-xs text-[#6b7280]">
                                    Last release: by <b>{es.released_by}</b> · {new Date(es.released_at).toLocaleString()}
                                    {es.release_reason ? ` · reason: ${es.release_reason}` : ''}
                                </p>
                            )}
                        </div>
                    </div>
                    {esActive && (
                        <button onClick={() => setReleaseOpen(true)} data-testid="safety-estop-release-btn"
                            className="px-3 py-1.5 rounded-lg border border-rose-300 bg-white text-xs font-semibold text-rose-700 hover:bg-rose-100">
                            Release Emergency Stop
                        </button>
                    )}
                </div>
            </div>

            {/* Individual gates */}
            <ul className="divide-y divide-[#efede5]">
                <Row ok={sw.ai_test_enabled} label="AI Test Mode"
                    detail={sw.ai_test_enabled ? 'ON — test-list manual calls allowed by this gate' : 'OFF'}
                    testid="safety-row-ai-test" warn={!sw.ai_test_enabled} />
                <Row ok={sw.ai_live_enabled} label="AI Live Mode"
                    detail={sw.ai_live_enabled ? 'ON' : 'OFF — scheduled live calls blocked by this gate'}
                    testid="safety-row-ai-live" warn={!sw.ai_live_enabled} />
                <Row ok={sv.outbound_calling_enabled} label="Server Outbound Calling"
                    detail={sv.outbound_calling_enabled
                        ? `Enabled (${sv.outbound_calling_env_flag}=true)`
                        : `Disabled (${sv.outbound_calling_env_flag}=false). This is a deployment-level flag, not a UI switch.`}
                    testid="safety-row-server" warn={!sv.outbound_calling_enabled} />
                <Row ok={sw.live_dispatch_authorized} label="Live Dispatch Authorization"
                    detail={sw.live_dispatch_authorized ? 'Granted' : `OFF — typed phrase required${sw.live_dispatch_implemented ? '' : ' · and code path not yet implemented'}`}
                    testid="safety-row-live-auth" warn={!sw.live_dispatch_authorized} />
                <Row ok={pv.ready} label="Bolna Provider"
                    detail={`${pv.status || 'not_configured'}${pv.config_version != null ? ` · v${pv.config_version}` : ''}`}
                    testid="safety-row-provider" />
                <Row ok={!esActive} label="Emergency Stop"
                    detail={esActive ? 'Active — overrides every other permission' : 'Inactive (other gates still apply)'}
                    testid="safety-row-estop" />
            </ul>

            {/* Effective permissions */}
            <div className="mt-4 grid md:grid-cols-2 gap-3">
                <div className="bg-[#faf9f1] border border-[#e5e3d8] rounded-xl p-3" data-testid="safety-effective-test">
                    <p className="text-[11px] uppercase tracking-wider text-[#9b9787]">Effective — Test Mode calls</p>
                    <p className={`text-sm font-bold ${eff.can_place_test_call ? 'text-emerald-700' : 'text-rose-700'}`}>
                        {eff.can_place_test_call ? 'Permitted by current gates' : 'Blocked'}
                    </p>
                    {!eff.can_place_test_call && (
                        <ul className="mt-1 text-xs text-[#6b7280] list-disc pl-4 space-y-0.5">
                            {(eff.test_blockers || []).map(b => <li key={b.key}>{b.reason}</li>)}
                        </ul>
                    )}
                </div>
                <div className="bg-[#faf9f1] border border-[#e5e3d8] rounded-xl p-3" data-testid="safety-effective-live">
                    <p className="text-[11px] uppercase tracking-wider text-[#9b9787]">Effective — Live Mode calls</p>
                    <p className={`text-sm font-bold ${eff.can_place_live_call ? 'text-emerald-700' : 'text-rose-700'}`}>
                        {eff.can_place_live_call ? 'Permitted by current gates' : 'Blocked'}
                    </p>
                    {!eff.can_place_live_call && (
                        <ul className="mt-1 text-xs text-[#6b7280] list-disc pl-4 space-y-0.5">
                            {(eff.live_blockers || []).map(b => <li key={b.key}>{b.reason}</li>)}
                        </ul>
                    )}
                </div>
            </div>

            <p className="text-[11px] text-[#9b9787] mt-3 flex items-center gap-1">
                <Lock size={12} /> Server outbound flag ({sv.outbound_calling_env_flag}) is set via deployment configuration and
                is not editable from the UI by design.
            </p>

            <Dialog open={releaseOpen} onOpenChange={(o) => { setReleaseOpen(o); if (!o) { setTyped(''); setReason(''); } }}>
                <DialogContent data-testid="estop-release-dialog" className="bg-[#fffdf7]">
                    <DialogHeader>
                        <DialogTitle>Release Emergency Stop?</DialogTitle>
                        <DialogDescription>
                            This does NOT enable calling. AI Test Mode, AI Live Mode, Server Outbound Calling, Live Dispatch
                            Authorization and provider readiness remain exactly as they are now. No queued calls will start.
                        </DialogDescription>
                    </DialogHeader>
                    <div className="space-y-2">
                        <label className="block text-sm">
                            <span className="text-[11px] font-semibold tracking-wider text-[#9b9787] uppercase">Type: RELEASE EMERGENCY STOP</span>
                            <input autoFocus value={typed} onChange={(e) => setTyped(e.target.value)} data-testid="estop-release-typed"
                                className="mt-1 w-full bg-white border border-[#e5e3d8] rounded-lg px-3 py-2 text-sm font-mono" />
                        </label>
                        <label className="block text-sm">
                            <span className="text-[11px] font-semibold tracking-wider text-[#9b9787] uppercase">Reason</span>
                            <input value={reason} onChange={(e) => setReason(e.target.value)} maxLength={280} data-testid="estop-release-reason"
                                className="mt-1 w-full bg-white border border-[#e5e3d8] rounded-lg px-3 py-2 text-sm" />
                        </label>
                    </div>
                    <DialogFooter>
                        <button onClick={() => setReleaseOpen(false)} data-testid="estop-release-cancel"
                            className="px-4 py-2 rounded-lg border border-[#e5e3d8] bg-white text-sm font-semibold">Cancel</button>
                        <button onClick={release} disabled={busy || typed !== 'RELEASE EMERGENCY STOP' || !reason.trim()}
                            data-testid="estop-release-confirm"
                            className="px-4 py-2 rounded-lg bg-rose-700 text-white text-sm font-semibold disabled:opacity-50 flex items-center gap-2">
                            {busy && <Spinner size={14} className="animate-spin" />}
                            {busy ? 'Releasing…' : 'Release Emergency Stop'}
                        </button>
                    </DialogFooter>
                </DialogContent>
            </Dialog>
        </Card>
    );
};
