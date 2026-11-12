// Admin control for the independent Live Calling Stop + Test Calling Permitted flags.
// - Live Calling Stop: defaults ON. Blocks ONLY Live dispatch. Independent of Global Emergency Stop.
// - Test Calling Permitted: defaults OFF. Enables ONLY Test outbound. Never unlocks Live.
// Both toggles are server-enforced (strict-True / strict-False identity). Releasing or enabling
// requires a typed confirmation to prevent accidents.
import { useState } from 'react';
import { toast } from 'sonner';
import { Siren, CheckCircle, XCircle, Spinner, Phone, PhoneSlash } from '@phosphor-icons/react';
import { aiApi, errMsg } from '../../pages/ai-calling/aiApi';
import {
    Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter,
} from '../ui/dialog';

const confirmPhrase = {
    live_release: 'RELEASE LIVE CALLING STOP',
    test_enable: 'PERMIT TEST CALLING',
};

export const IndependentSafetySwitches = ({ safety, onChanged, compact = false }) => {
    const [dlg, setDlg] = useState(null);     // 'live-engage' | 'live-release' | 'test-enable' | 'test-disable'
    const [typed, setTyped] = useState('');
    const [reason, setReason] = useState('');
    const [busy, setBusy] = useState(false);

    const sw = safety?.switches || {};
    const liveStop = !!sw.live_calling_stop;
    const testPermit = !!sw.test_calling_permitted;
    const liveMeta = safety?.live_calling_stop || {};
    const testMeta = safety?.test_calling_permitted || {};

    const close = () => { setDlg(null); setTyped(''); setReason(''); };

    const submit = async () => {
        if (!dlg) return;
        setBusy(true);
        try {
            if (dlg === 'live-engage') {
                await aiApi.post('/live-calling-stop', { active: true, reason: reason.trim() || null });
                toast.success('Live Calling Stop engaged. Test Mode is unaffected.');
            } else if (dlg === 'live-release') {
                if (typed !== confirmPhrase.live_release) { toast.error('Type the exact confirmation phrase'); setBusy(false); return; }
                await aiApi.post('/live-calling-stop', { active: false, reason: reason.trim() || null, confirmation: confirmPhrase.live_release });
                toast.success('Live Calling Stop released. Live still blocked by the other gates.');
            } else if (dlg === 'test-enable') {
                if (typed !== confirmPhrase.test_enable) { toast.error('Type the exact confirmation phrase'); setBusy(false); return; }
                await aiApi.post('/test-calling-permitted', { permitted: true, reason: reason.trim() || null, confirmation: confirmPhrase.test_enable });
                toast.success('Test calling permitted. Live Mode is unaffected.');
            } else if (dlg === 'test-disable') {
                await aiApi.post('/test-calling-permitted', { permitted: false, reason: reason.trim() || null });
                toast.success('Test calling revoked. Queued test jobs will fail the gate.');
            }
            close(); onChanged?.();
        } catch (e) { toast.error(errMsg(e, 'Switch update failed')); } finally { setBusy(false); }
    };

    const needsTyped = dlg === 'live-release' || dlg === 'test-enable';
    const expectedPhrase = dlg === 'live-release' ? confirmPhrase.live_release
        : dlg === 'test-enable' ? confirmPhrase.test_enable : '';

    const liveRow = (
        <div className={`rounded-xl border p-3 ${liveStop ? 'bg-rose-50 border-rose-200' : 'bg-emerald-50 border-emerald-200'}`}
            data-testid="live-calling-stop-row">
            <div className="flex flex-wrap items-start justify-between gap-3">
                <div className="flex items-start gap-2">
                    <PhoneSlash size={20} weight={liveStop ? 'fill' : 'duotone'} className={liveStop ? 'text-rose-700' : 'text-emerald-700'} />
                    <div>
                        <p className="text-sm font-bold text-[#1a2332]">
                            Live Calling Stop: <span data-testid="live-calling-stop-state">{liveStop ? 'ON' : 'OFF'}</span>
                        </p>
                        <p className="text-xs text-[#6b7280]">
                            Blocks only Live dispatch. Test Mode is unaffected. Independent of Global Emergency Stop.
                        </p>
                        {liveStop && liveMeta.engaged_by && (
                            <p className="text-xs text-[#6b7280] mt-1">
                                Engaged by <b>{liveMeta.engaged_by}</b> · {liveMeta.engaged_at ? new Date(liveMeta.engaged_at).toLocaleString() : ''}
                                {liveMeta.engaged_reason ? ` · ${liveMeta.engaged_reason}` : ''}
                            </p>
                        )}
                        {!liveStop && liveMeta.released_by && (
                            <p className="text-xs text-[#6b7280] mt-1">
                                Released by <b>{liveMeta.released_by}</b> · {liveMeta.released_at ? new Date(liveMeta.released_at).toLocaleString() : ''}
                                {liveMeta.release_reason ? ` · ${liveMeta.release_reason}` : ''}
                            </p>
                        )}
                    </div>
                </div>
                {liveStop ? (
                    <button onClick={() => setDlg('live-release')} data-testid="live-calling-stop-release-btn"
                        className="px-3 py-1.5 rounded-lg border border-rose-300 bg-white text-xs font-semibold text-rose-700 hover:bg-rose-100">
                        Release Live Stop
                    </button>
                ) : (
                    <button onClick={() => setDlg('live-engage')} data-testid="live-calling-stop-engage-btn"
                        className="px-3 py-1.5 rounded-lg border border-emerald-300 bg-white text-xs font-semibold text-emerald-700 hover:bg-emerald-100">
                        Engage Live Stop
                    </button>
                )}
            </div>
        </div>
    );

    const testRow = (
        <div className={`rounded-xl border p-3 ${testPermit ? 'bg-emerald-50 border-emerald-200' : 'bg-amber-50 border-amber-200'}`}
            data-testid="test-calling-permitted-row">
            <div className="flex flex-wrap items-start justify-between gap-3">
                <div className="flex items-start gap-2">
                    <Phone size={20} weight={testPermit ? 'fill' : 'duotone'} className={testPermit ? 'text-emerald-700' : 'text-amber-700'} />
                    <div>
                        <p className="text-sm font-bold text-[#1a2332]">
                            Test Calling Permitted: <span data-testid="test-calling-permitted-state">{testPermit ? 'ON' : 'OFF'}</span>
                        </p>
                        <p className="text-xs text-[#6b7280]">
                            Permits Test-Mode outbound only. Has zero effect on Live. Emergency Stop still overrides.
                        </p>
                        {testPermit && testMeta.permitted_by && (
                            <p className="text-xs text-[#6b7280] mt-1">
                                Permitted by <b>{testMeta.permitted_by}</b> · {testMeta.permitted_at ? new Date(testMeta.permitted_at).toLocaleString() : ''}
                                {testMeta.permitted_reason ? ` · ${testMeta.permitted_reason}` : ''}
                            </p>
                        )}
                        {!testPermit && testMeta.revoked_by && (
                            <p className="text-xs text-[#6b7280] mt-1">
                                Revoked by <b>{testMeta.revoked_by}</b> · {testMeta.revoked_at ? new Date(testMeta.revoked_at).toLocaleString() : ''}
                                {testMeta.revoked_reason ? ` · ${testMeta.revoked_reason}` : ''}
                            </p>
                        )}
                    </div>
                </div>
                {testPermit ? (
                    <button onClick={() => setDlg('test-disable')} data-testid="test-calling-permitted-revoke-btn"
                        className="px-3 py-1.5 rounded-lg border border-amber-300 bg-white text-xs font-semibold text-amber-700 hover:bg-amber-100">
                        Revoke Test Calling
                    </button>
                ) : (
                    <button onClick={() => setDlg('test-enable')} data-testid="test-calling-permitted-enable-btn"
                        className="px-3 py-1.5 rounded-lg border border-emerald-300 bg-white text-xs font-semibold text-emerald-700 hover:bg-emerald-100">
                        Enable Test Calling
                    </button>
                )}
            </div>
        </div>
    );

    const dialogTitle = {
        'live-engage': 'Engage Live Calling Stop?',
        'live-release': 'Release Live Calling Stop?',
        'test-enable': 'Permit Test-Mode outbound calling?',
        'test-disable': 'Revoke Test-Mode outbound calling?',
    }[dlg];
    const dialogBody = {
        'live-engage': 'All Live dispatch will be blocked by this gate. Test Mode is unaffected.',
        'live-release': 'Releasing does NOT enable Live calls — AI Live, Live Dispatch Authorization, Server flag and Bolna all remain in force.',
        'test-enable': 'Enables Test-Mode outbound calling to consented test recipients only. Live Mode is unaffected. Emergency Stop still overrides.',
        'test-disable': 'All pending/new Test-Mode call attempts will fail the gate. Live Mode is unaffected.',
    }[dlg];

    return (
        <div className={compact ? 'space-y-3' : 'space-y-3 mt-4'} data-testid="independent-safety-switches">
            {liveRow}
            {testRow}

            <Dialog open={!!dlg} onOpenChange={(o) => { if (!o) close(); }}>
                <DialogContent data-testid="independent-switch-dialog" className="bg-[#fffdf7]">
                    <DialogHeader>
                        <DialogTitle>{dialogTitle}</DialogTitle>
                        <DialogDescription>{dialogBody}</DialogDescription>
                    </DialogHeader>
                    <div className="space-y-2">
                        {needsTyped && (
                            <label className="block text-sm">
                                <span className="text-[11px] font-semibold tracking-wider text-[#9b9787] uppercase">Type: {expectedPhrase}</span>
                                <input autoFocus value={typed} onChange={(e) => setTyped(e.target.value)} data-testid="independent-switch-typed"
                                    className="mt-1 w-full bg-white border border-[#e5e3d8] rounded-lg px-3 py-2 text-sm font-mono" />
                            </label>
                        )}
                        <label className="block text-sm">
                            <span className="text-[11px] font-semibold tracking-wider text-[#9b9787] uppercase">Reason (optional)</span>
                            <input value={reason} onChange={(e) => setReason(e.target.value)} maxLength={280} data-testid="independent-switch-reason"
                                className="mt-1 w-full bg-white border border-[#e5e3d8] rounded-lg px-3 py-2 text-sm" />
                        </label>
                    </div>
                    <DialogFooter>
                        <button onClick={close} data-testid="independent-switch-cancel"
                            className="px-4 py-2 rounded-lg border border-[#e5e3d8] bg-white text-sm font-semibold">Cancel</button>
                        <button onClick={submit} disabled={busy || (needsTyped && typed !== expectedPhrase)}
                            data-testid="independent-switch-confirm"
                            className="px-4 py-2 rounded-lg bg-teal-700 text-white text-sm font-semibold disabled:opacity-50 flex items-center gap-2">
                            {busy && <Spinner size={14} className="animate-spin" />}
                            {busy ? 'Saving…' : 'Confirm'}
                        </button>
                    </DialogFooter>
                </DialogContent>
            </Dialog>
        </div>
    );
};

// Lightweight status pill — reused inside Live Mode so operators see the state at a glance.
export const LiveStopBadge = ({ safety }) => {
    const on = !!safety?.switches?.live_calling_stop;
    return (
        <span data-testid="live-stop-badge"
            className={`inline-flex items-center gap-1 px-2 py-1 rounded-md text-xs font-semibold border ${on ? 'bg-rose-50 text-rose-700 border-rose-200' : 'bg-emerald-50 text-emerald-700 border-emerald-200'}`}>
            {on ? <XCircle size={14} weight="fill" /> : <CheckCircle size={14} weight="fill" />}
            Live Calling Stop: {on ? 'ON' : 'OFF'}
        </span>
    );
};

// Emergency Stop reminder pill — used alongside the Live Stop badge.
export const EmergencyStopBadge = ({ safety }) => {
    const on = !!safety?.emergency_stop?.active;
    return (
        <span data-testid="emergency-stop-badge"
            className={`inline-flex items-center gap-1 px-2 py-1 rounded-md text-xs font-semibold border ${on ? 'bg-rose-50 text-rose-700 border-rose-200' : 'bg-zinc-50 text-zinc-700 border-zinc-200'}`}>
            <Siren size={14} weight={on ? 'fill' : 'duotone'} />
            Emergency Stop: {on ? 'ON' : 'OFF'}
        </span>
    );
};
