// A sticky bar shown on every AI Calling tab. It is the single visible indicator of the
// authoritative Emergency Stop state. ENGAGING is available here (with confirmation). RELEASING
// is intentionally NOT exposed here — release lives only in Settings → Safety Controls.
import { useState } from 'react';
import { toast } from 'sonner';
import { Siren, Warning, ShieldCheck, Spinner } from '@phosphor-icons/react';
import { aiApi, errMsg } from '../../pages/ai-calling/aiApi';
import {
    Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter,
} from '../ui/dialog';

export const GlobalEmergencyStopBar = ({ safety, loading, onChanged }) => {
    const [open, setOpen] = useState(false);
    const [reason, setReason] = useState('');
    const [busy, setBusy] = useState(false);

    if (loading && !safety) {
        return (
            <div data-testid="estop-bar-loading"
                className="sticky top-0 z-30 bg-zinc-100 border-b border-zinc-200 px-4 py-2 text-xs text-zinc-700 flex items-center gap-2">
                <Spinner size={14} className="animate-spin" /> Checking safety status…
            </div>
        );
    }
    if (!safety || safety.authoritative === false) {
        return (
            <div data-testid="estop-bar-unavailable"
                className="sticky top-0 z-30 bg-rose-700 text-white px-4 py-2 text-xs font-semibold flex items-center gap-2">
                <Warning size={14} weight="fill" /> Safety status unavailable — calling blocked.
            </div>
        );
    }
    const active = !!safety.emergency_stop?.active;

    const engage = async () => {
        if (!reason.trim()) { toast.error('Enter a short reason'); return; }
        setBusy(true);
        try {
            await aiApi.post('/emergency-stop', { active: true, reason: reason.trim() });
            toast.success('Emergency Stop engaged. Pending jobs were cancelled.');
            setOpen(false); setReason(''); onChanged?.();
        } catch (e) { toast.error(errMsg(e, 'Failed to engage Emergency Stop')); } finally { setBusy(false); }
    };

    return (
        <div data-testid="estop-bar" aria-live="polite"
            className={`sticky top-0 z-30 border-b px-4 py-2 flex items-center justify-between gap-3 ${
                active ? 'bg-rose-700 text-white border-rose-800' : 'bg-amber-50 text-amber-900 border-amber-200'
            }`}>
            <div className="flex items-center gap-2 text-xs font-semibold">
                {active ? <Siren size={16} weight="fill" /> : <ShieldCheck size={16} weight="fill" />}
                <span data-testid="estop-bar-state">
                    Emergency Stop: <b>{active ? 'ON' : 'OFF'}</b>
                </span>
                {active && safety.emergency_stop?.engaged_by && (
                    <span className="opacity-80 hidden sm:inline">
                        · by {safety.emergency_stop.engaged_by} at {new Date(safety.emergency_stop.engaged_at).toLocaleString()}
                    </span>
                )}
                {!active && (
                    <span className="opacity-80 hidden sm:inline">· No real call can start without server flag + provider + authorization</span>
                )}
            </div>
            {!active && (
                <button data-testid="estop-bar-engage-btn" onClick={() => setOpen(true)}
                    className="shrink-0 px-3 py-1.5 rounded-md bg-rose-700 text-white text-xs font-bold hover:bg-rose-800">
                    Engage Emergency Stop
                </button>
            )}
            {active && (
                <span className="shrink-0 text-[11px] font-semibold uppercase tracking-wider opacity-90">
                    Release available in Settings → Safety Controls
                </span>
            )}

            <Dialog open={open} onOpenChange={(o) => { setOpen(o); if (!o) setReason(''); }}>
                <DialogContent data-testid="estop-engage-dialog" className="bg-[#fffdf7]">
                    <DialogHeader>
                        <DialogTitle>Engage Emergency Stop?</DialogTitle>
                        <DialogDescription>
                            All pending AI call jobs will be cancelled and running test batches will stop. This does NOT change
                            modes or provider settings. Release is available only from Settings → Safety Controls.
                        </DialogDescription>
                    </DialogHeader>
                    <label className="block text-sm mt-1">
                        <span className="text-[11px] font-semibold tracking-wider text-[#9b9787] uppercase">Reason</span>
                        <input autoFocus value={reason} onChange={(e) => setReason(e.target.value)} maxLength={280}
                            data-testid="estop-engage-reason"
                            className="mt-1 w-full bg-white border border-[#e5e3d8] rounded-lg px-3 py-2 text-sm" />
                    </label>
                    <DialogFooter>
                        <button onClick={() => setOpen(false)} data-testid="estop-engage-cancel"
                            className="px-4 py-2 rounded-lg border border-[#e5e3d8] bg-white text-sm font-semibold">Cancel</button>
                        <button onClick={engage} disabled={busy || !reason.trim()} data-testid="estop-engage-confirm"
                            className="px-4 py-2 rounded-lg bg-rose-700 text-white text-sm font-semibold disabled:opacity-50 flex items-center gap-2">
                            {busy && <Spinner size={14} className="animate-spin" />}
                            {busy ? 'Engaging…' : 'Engage Emergency Stop'}
                        </button>
                    </DialogFooter>
                </DialogContent>
            </Dialog>
        </div>
    );
};
