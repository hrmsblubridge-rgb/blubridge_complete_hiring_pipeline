import { useEffect, useState } from 'react';
import { Prohibit, Pulse } from '@phosphor-icons/react';
import { aiApi } from '../../pages/ai-calling/aiApi';
import { Card, SectionTitle } from './AICallingHeader';
import { fmtTime } from './callFormat';

const Cell = ({ label, value, testid, warn }) => (
    <div className={`rounded-xl px-3 py-2 border ${warn ? 'bg-amber-50 border-amber-200' : 'bg-[#faf9f1] border-[#e5e3d8]'}`}>
        <p className="text-[11px] uppercase tracking-wider text-[#9b9787]">{label}</p>
        <p className="text-sm font-bold text-[#1a2332]" data-testid={testid}>{value}</p>
    </div>
);

// Read-only live worker status. The worker never runs in this phase.
export const LiveWorkerStatus = () => {
    const [w, setW] = useState(null);
    useEffect(() => { aiApi.get('/live-prep/worker-status').then(r => setW(r.data)).catch(() => setW(false)); }, []);
    if (w === false) return null;
    const m = w?.monitoring?.limits;
    const readyOk = w?.readiness?.checks?.filter(c => c.ok).length ?? 0;
    return (
        <Card>
            <div className="flex items-center gap-2 bg-rose-50 border border-rose-200 rounded-xl px-4 py-3 mb-4" data-testid="live-disabled-banner">
                <Prohibit size={20} weight="bold" className="text-rose-700" />
                <p className="text-sm font-extrabold tracking-wide text-rose-900">{w?.banner || 'LIVE CALLING DISABLED — PREPARATION ONLY'}</p>
            </div>
            <SectionTitle icon={Pulse}>Live worker (mock provider only)</SectionTitle>
            {w && (
                <div className="grid grid-cols-2 sm:grid-cols-4 gap-2" data-testid="live-worker-status">
                    <Cell label="Worker" value={w.running ? 'Running' : 'Stopped (disabled)'} testid="worker-running" />
                    <Cell label="Pending / due now" value={`${w.pending} / ${w.due_now}`} testid="worker-pending" />
                    <Cell label="Daily usage (mock)" value={`${m.mock_used_today} / ${m.daily_cap}`} testid="worker-daily" />
                    <Cell label="Concurrent (mock)" value={`${m.mock_active} / ${m.concurrent}`} testid="worker-concurrent" />
                    <Cell label="Excluded: no consent" value={`${w.exclusions.no_valid_consent} of ${w.exclusions.bookings}`} testid="worker-no-consent" />
                    <Cell label="Excluded: Do Not Call" value={w.exclusions.do_not_call} testid="worker-dnc" />
                    <Cell label="Unresolved calls" value={w.unresolved + (w.monitoring.pending_reconciliation || 0)} testid="worker-unresolved" warn={w.unresolved > 0} />
                    <Cell label="Readiness" value={`${readyOk} / ${w.readiness.checks.length} checks`} testid="worker-readiness" />
                </div>
            )}
            <p className="text-xs text-[#6b7280] mt-3" data-testid="worker-last-run">
                Last scheduler run: {w?.last_run ? `${fmtTime(w.last_run.at)} (${w.last_run.source}, by ${w.last_run.by})` : 'never'}
            </p>
        </Card>
    );
};
