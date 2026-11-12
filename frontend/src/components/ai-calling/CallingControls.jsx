import { toast } from 'sonner';
import { PhoneOutgoing, Stop, Info, LockSimple } from '@phosphor-icons/react';
import { Link } from 'react-router-dom';
import { aiApi, errMsg } from '../../pages/ai-calling/aiApi';

export const CallingControls = ({ selected = [], status, onCall }) => {
    const selectedCount = selected.length;
    const next = selected.find(c => c.readiness === 'ready');
    const reason = !selectedCount ? 'Select at least one test colleague'
        : status?.block_reasons?.length ? status.block_reasons[0]
            : !next ? 'None of the selected recipients has test-call consent' : '';
    const stop = async () => {
        try { const r = (await aiApi.post('/calls/stop')).data; toast.success(`Stopped. Cancelled ${r.cancelled_jobs} pending job(s).`); }
        catch (e) { toast.error(errMsg(e)); }
    };
    const blk = status?.blocking_call;
    return (
        <div className="bg-[#fffdf7] border border-[#e5e3d8] rounded-2xl p-4 space-y-3" data-testid="calling-controls">
            <div className="flex items-start gap-2 text-sm text-[#1a2332] bg-teal-50 border border-teal-200 rounded-xl px-3 py-2" data-testid="calling-status-message">
                <Info size={18} weight="duotone" className="text-teal-700 shrink-0 mt-0.5" />
                {status?.single_call_enabled
                    ? <span>Calling is available for one or more consenting test colleagues: use the <b>Call Now</b> phone icon on a recipient. Each call needs a typed confirmation.</span>
                    : <span data-testid="calling-block-reasons">Calling is blocked: <b>{(status?.block_reasons || ['status unavailable']).join(' · ')}</b>. One selected recipient is enough once these are cleared.</span>}
            </div>
            {blk && (
                <div className="text-sm bg-amber-50 border border-amber-200 text-amber-900 rounded-xl px-3 py-2" data-testid="blocking-call-banner">
                    Calling is locked: the call to <b>{blk.candidate_name}</b> is still <b>{blk.state.replace(/_/g, ' ')}</b>. <Link to="/ai-calling/history" className="underline font-semibold">View in Call History</Link>
                </div>
            )}
            <div className="flex flex-wrap gap-2">
                <button disabled={!!reason} title={reason || 'Calls go one at a time; each needs a typed confirmation'} onClick={() => onCall?.(next)} data-testid="call-selected-btn"
                    className="px-4 py-2 rounded-lg bg-teal-700 text-white text-sm font-semibold flex items-center gap-2 disabled:opacity-40 disabled:cursor-not-allowed">
                    {reason ? <LockSimple size={16} /> : null} <PhoneOutgoing size={16} /> Call Selected ({selectedCount})
                </button>
                {reason && <span className="text-xs text-[#6b7280] self-center" data-testid="call-selected-reason">{reason}</span>}
                <button onClick={stop} data-testid="stop-calls-btn" className="px-4 py-2 rounded-lg border border-rose-200 bg-rose-50 text-rose-700 text-sm font-semibold flex items-center gap-2 hover:bg-rose-100">
                    <Stop size={16} weight="fill" /> Stop Calls
                </button>
            </div>
        </div>
    );
};
