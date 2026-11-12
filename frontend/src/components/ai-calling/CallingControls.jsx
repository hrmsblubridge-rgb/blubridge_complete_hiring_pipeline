// Enhanced Testing Mode CallingControls — single & bulk aware, with per-row blocking reasons,
// loading pipeline (checking → submitting → accepted), and duplicate-click protection.
import { useRef, useState } from 'react';
import { toast } from 'sonner';
import { PhoneOutgoing, Stop, Info, LockSimple, Spinner, CheckCircle, Warning } from '@phosphor-icons/react';
import { Link } from 'react-router-dom';
import { aiApi, errMsg } from '../../pages/ai-calling/aiApi';
import { useSafetyStatus, callingBlocked } from './useSafetyStatus';

const PIPELINE_LABELS = {
    idle: '',
    checking: 'Checking eligibility…',
    submitting: 'Submitting to provider…',
    accepted: 'Provider accepted · queued',
    failed: 'Failed',
    blocked: 'Blocked',
};

export const CallingControls = ({ selected = [], status, onCall }) => {
    const { safety } = useSafetyStatus();
    const blockedState = callingBlocked(safety);
    const [pipeline, setPipeline] = useState('idle');
    const inFlight = useRef(false);

    // Per-recipient eligibility: consent granted + not opted-out.
    const eligible = selected.filter(c => c.readiness === 'ready');
    const blocked = selected.filter(c => c.readiness !== 'ready');
    const canCall = eligible.length > 0 && !blockedState.blocked && !inFlight.current;

    const next = eligible[0];
    let reason = '';
    if (!selected.length) reason = 'Select at least one test colleague';
    else if (blockedState.blocked) reason = blockedState.reasons[0];
    else if (!eligible.length) reason = `All ${selected.length} selected recipient(s) lack test-call consent`;

    const stop = async () => {
        try { const r = (await aiApi.post('/calls/stop')).data; toast.success(`Stopped. Cancelled ${r.cancelled_jobs} pending job(s).`); }
        catch (e) { toast.error(errMsg(e)); }
    };

    const triggerCall = async () => {
        if (inFlight.current) return;  // duplicate-click guard
        inFlight.current = true; setPipeline('checking');
        setTimeout(() => setPipeline(p => p === 'checking' ? 'submitting' : p), 400);
        try { onCall?.(next); setPipeline('accepted'); }
        catch (e) { setPipeline('failed'); toast.error(errMsg(e)); }
        finally { setTimeout(() => { inFlight.current = false; setPipeline('idle'); }, 1500); }
    };

    const blk = status?.blocking_call;

    return (
        <div className="bg-[#fffdf7] border border-[#e5e3d8] rounded-2xl p-4 space-y-3" data-testid="calling-controls">
            {/* Guided readiness summary */}
            <div className="grid sm:grid-cols-3 gap-3 text-xs" data-testid="test-readiness">
                <div className="bg-white border border-[#e5e3d8] rounded-xl p-3">
                    <p className="text-[10px] uppercase tracking-wider text-[#9b9787]">Selected</p>
                    <p className="text-xl font-bold text-[#1a2332]" data-testid="test-readiness-selected">{selected.length}</p>
                </div>
                <div className="bg-white border border-emerald-200 rounded-xl p-3">
                    <p className="text-[10px] uppercase tracking-wider text-emerald-700">Eligible to call</p>
                    <p className="text-xl font-bold text-emerald-700" data-testid="test-readiness-eligible">{eligible.length}</p>
                </div>
                <div className="bg-white border border-rose-200 rounded-xl p-3">
                    <p className="text-[10px] uppercase tracking-wider text-rose-700">Blocked</p>
                    <p className="text-xl font-bold text-rose-700" data-testid="test-readiness-blocked">{blocked.length}</p>
                </div>
            </div>

            <div className="flex items-start gap-2 text-sm text-[#1a2332] bg-teal-50 border border-teal-200 rounded-xl px-3 py-2" data-testid="calling-status-message">
                <Info size={18} weight="duotone" className="text-teal-700 shrink-0 mt-0.5" />
                {blockedState.blocked ? (
                    <span data-testid="calling-block-reasons">Calling is blocked: <b>{blockedState.reasons.join(' · ')}</b>. Fix these in Settings → Safety Controls.</span>
                ) : eligible.length === 0 ? (
                    <span>Select a consented test colleague, then use <b>Call Now</b> on the row or <b>Call Selected</b>.</span>
                ) : (
                    <span>{eligible.length} eligible of {selected.length} selected. Each real call still requires typed confirmation.</span>
                )}
            </div>

            {blk && (
                <div className="text-sm bg-amber-50 border border-amber-200 text-amber-900 rounded-xl px-3 py-2" data-testid="blocking-call-banner">
                    Calling is locked: the call to <b>{blk.candidate_name}</b> is still <b>{blk.state.replace(/_/g, ' ')}</b>. <Link to="/ai-calling/history" className="underline font-semibold">View in Call History</Link>
                </div>
            )}

            {pipeline !== 'idle' && (
                <div className="flex items-center gap-2 text-sm bg-white border border-[#e5e3d8] rounded-xl px-3 py-2" data-testid="call-pipeline">
                    {pipeline === 'accepted' ? <CheckCircle size={16} className="text-emerald-600" /> :
                        pipeline === 'failed' || pipeline === 'blocked' ? <Warning size={16} className="text-rose-600" /> :
                        <Spinner size={16} className="animate-spin text-teal-700" />}
                    <span data-testid="call-pipeline-state">{PIPELINE_LABELS[pipeline]}</span>
                </div>
            )}

            <div className="flex flex-wrap gap-2">
                <button disabled={!canCall || !!reason} title={reason || 'Call one eligible recipient (first in selection)'}
                    onClick={triggerCall} data-testid="call-selected-btn"
                    className="px-4 py-2 rounded-lg bg-teal-700 text-white text-sm font-semibold flex items-center gap-2 disabled:opacity-40 disabled:cursor-not-allowed transition-colors hover:bg-teal-800">
                    {reason ? <LockSimple size={16} /> : <PhoneOutgoing size={16} />}
                    {inFlight.current ? 'Starting…' : `Call Selected (${eligible.length} eligible / ${selected.length} selected)`}
                </button>
                {reason && <span className="text-xs text-[#6b7280] self-center" data-testid="call-selected-reason">{reason}</span>}
                <button onClick={stop} data-testid="stop-calls-btn"
                    className="px-4 py-2 rounded-lg border border-rose-200 bg-rose-50 text-rose-700 text-sm font-semibold flex items-center gap-2 hover:bg-rose-100 transition-colors">
                    <Stop size={16} weight="fill" /> Stop Calls
                </button>
            </div>
        </div>
    );
};
