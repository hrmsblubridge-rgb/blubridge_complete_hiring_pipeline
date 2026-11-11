import { useEffect, useState } from 'react';
import { toast } from 'sonner';
import { Warning } from '@phosphor-icons/react';
import { aiApi, errMsg } from '../../pages/ai-calling/aiApi';
import { Card } from './AICallingHeader';
import { LiveReadiness } from './LiveReadiness';
import { fmtTime } from './callFormat';

const OUTCOMES = ['CONFIRMED', 'RESCHEDULE_REQUESTED', 'DECLINED', 'DO_NOT_CALL', 'no_answer', 'timeout', 'failed'];
const btn = 'px-3 py-2 rounded-lg text-sm font-semibold border disabled:opacity-40';

const JobsTable = ({ jobs }) => (
    <div className="overflow-x-auto" data-testid="mock-jobs-table">
        <table className="w-full text-sm">
            <thead className="text-[11px] uppercase tracking-wider text-[#9b9787]">
                <tr>{['Candidate', 'Attempt', 'Planned call', 'Status', 'Reasons / blocked by', 'Mock result'].map(h => <th key={h} className="px-2 py-2 text-left font-semibold">{h}</th>)}</tr>
            </thead>
            <tbody>
                {jobs.map(j => (
                    <tr key={j.id} className="border-t border-[#efede5] align-top" data-testid={`mock-job-${j.id}`}>
                        <td className="px-2 py-2"><div className="font-semibold">{j.candidate_name}</div><div className="font-mono text-xs text-[#6b7280]">{j.phone_masked} · {j.source}</div></td>
                        <td className="px-2 py-2">{j.attempt}</td>
                        <td className="px-2 py-2 whitespace-nowrap">{fmtTime(j.planned_at) || '—'}</td>
                        <td className="px-2 py-2 font-semibold" data-testid="mock-job-status">{j.status}</td>
                        <td className="px-2 py-2 text-xs text-[#6b7280] max-w-[16rem]">{[...(j.reasons || []), ...(j.gate_failed || []).map(k => `gate:${k}`)].join(', ') || '—'}</td>
                        <td className="px-2 py-2 text-xs">{j.mock_call ? `${j.mock_call.extracted?.attendance_status || j.mock_call.provider_status} · request sent: no` : '—'}</td>
                    </tr>
                ))}
            </tbody>
        </table>
    </div>
);

// Phase 7C-A mock scheduler + worker. Jobs are non-dispatchable; nothing is ever sent to Bolna.
export const LivePrepPanel = () => {
    const [d, setD] = useState(null);
    const [busy, setBusy] = useState(false);
    const [outcome, setOutcome] = useState('CONFIRMED');
    const load = () => aiApi.get('/live-prep/overview').then(r => setD(r.data)).catch(e => toast.error(errMsg(e)));
    useEffect(() => { load(); }, []);
    const run = async (path, body, msg) => {
        setBusy(true);
        try { const r = await aiApi.post(path, body); toast.success(msg(r.data)); await load(); } catch (e) { toast.error(errMsg(e)); } finally { setBusy(false); }
    };
    return (
        <div className="space-y-5" data-testid="live-prep-panel">
            <div className="flex items-center gap-3 bg-amber-100 border-2 border-amber-400 rounded-2xl px-5 py-4" data-testid="live-prep-warning">
                <Warning size={26} weight="fill" className="text-amber-700 shrink-0" />
                <p className="text-base font-extrabold tracking-wide text-amber-900">MOCK ONLY — NO PHONE CALLS WILL BE PLACED.</p>
            </div>
            {d && <LiveReadiness readiness={d.readiness} monitoring={d.monitoring} />}
            <Card>
                <div className="flex flex-wrap items-center gap-2 mb-4">
                    <button disabled={busy} onClick={() => run('/live-prep/plan', { source: 'fixtures' }, r => `Planned: ${JSON.stringify(r.counts)}`)} data-testid="mock-plan-fixtures-btn" className={`${btn} bg-teal-700 text-white border-teal-700`}>Plan from synthetic bookings</button>
                    <button disabled={busy} onClick={() => run('/live-prep/plan', { source: 'bb_registrations' }, r => `Planned: ${JSON.stringify(r.counts)}`)} data-testid="mock-plan-real-btn" className={`${btn} bg-white border-[#e5e3d8]`}>Plan from real bookings</button>
                    <select value={outcome} onChange={e => setOutcome(e.target.value)} data-testid="mock-outcome-select" className="px-2 py-2 rounded-lg border border-[#e5e3d8] text-sm">
                        {OUTCOMES.map(o => <option key={o} value={o}>{o}</option>)}
                    </select>
                    <button disabled={busy} onClick={() => run('/live-prep/mock-tick', { outcome }, r => (r.claimed ? `Mock worker: ${r.result}` : 'No mock job is due now'))} data-testid="mock-tick-btn" className={`${btn} bg-white border-[#e5e3d8]`}>Run mock worker once</button>
                    <button disabled={busy} onClick={() => run('/live-prep/mock-jobs/clear', {}, r => `Cleared ${r.deleted} mock jobs`)} data-testid="mock-clear-btn" className={`${btn} bg-white border-rose-200 text-rose-700`}>Clear mock jobs</button>
                </div>
                {d && (d.jobs.length ? <JobsTable jobs={d.jobs} /> : <p className="text-sm text-[#9b9787]" data-testid="mock-jobs-empty">No mock jobs yet.</p>)}
            </Card>
        </div>
    );
};
