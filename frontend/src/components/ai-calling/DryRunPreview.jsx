import { useCallback, useEffect, useState } from 'react';
import { toast } from 'sonner';
import { Warning, Play, Database, CalendarDots } from '@phosphor-icons/react';
import { aiApi, errMsg } from '../../pages/ai-calling/aiApi';
import { Card, SectionTitle } from './AICallingHeader';
import { DryRunJobsTable } from './DryRunJobsTable';
import { fmtTime } from './callFormat';

const Stat = ({ k, v, testid }) => (
    <div className="bg-white border border-[#e5e3d8] rounded-xl px-4 py-3">
        <p className="text-[11px] uppercase tracking-wider text-[#9b9787]">{k}</p>
        <p className="text-2xl font-bold text-[#1a2332]" data-testid={testid}>{v ?? '—'}</p>
    </div>
);

export const DryRunPreview = () => {
    const [d, setD] = useState(null);
    const [busy, setBusy] = useState(false);
    const load = useCallback(() => aiApi.get('/dry-run/preview').then(r => setD(r.data)).catch(e => toast.error(errMsg(e))), []);
    useEffect(() => { load(); }, [load]);

    const act = async (fn, ok) => {
        if (busy) return;
        setBusy(true);
        try { const r = (await fn()).data; toast.success(ok(r)); await load(); }
        catch (e) { toast.error(errMsg(e)); } finally { setBusy(false); }
    };
    const c = d?.last_run?.counts || {};
    const current = (d?.jobs || []).filter(j => j.status !== 'INVALIDATED');
    const invalid = (d?.jobs || []).filter(j => j.status === 'INVALIDATED');

    return (
        <div className="space-y-5" data-testid="dry-run-preview">
            <div className="flex items-center gap-3 bg-amber-100 border-2 border-amber-400 rounded-2xl px-5 py-4" data-testid="dry-run-warning">
                <Warning size={26} weight="fill" className="text-amber-700 shrink-0" />
                <p className="text-base font-extrabold tracking-wide text-amber-900">{d?.warning || 'DRY RUN — NO PHONE CALLS WILL BE PLACED.'}</p>
            </div>
            <Card>
                <SectionTitle icon={CalendarDots}>Scheduling preview (synthetic bookings only)</SectionTitle>
                <p className="text-xs text-[#6b7280] mb-4">
                    Plans a confirmation call {d?.rules?.hours_before ?? 24} h before each interview, moved forward into {d?.rules?.window}. At least {d?.rules?.min_lead_hours ?? 2} h must remain before the interview, otherwise Needs Review.
                    Live Mode would allow {d?.rules?.no_answer_retries_in_live ?? 1} no-answer retry ({d?.rules?.retry_gap_minutes ?? 60} min later); no retries run here.
                </p>
                <div className="flex flex-wrap gap-2 mb-4">
                    <button disabled={busy} onClick={() => act(() => aiApi.post('/dry-run/fixtures/seed'), r => `Loaded ${r.seeded} synthetic bookings`)} data-testid="dry-run-seed-btn"
                        className="px-4 py-2 rounded-lg border border-[#e5e3d8] bg-white text-sm font-semibold flex items-center gap-2 hover:bg-[#efede5] disabled:opacity-40"><Database size={16} /> Load synthetic bookings</button>
                    <button disabled={busy || !d?.fixtures} onClick={() => act(() => aiApi.post('/dry-run/plan'), r => `Planned ${r.bookings} bookings (dry run)`)} data-testid="dry-run-plan-btn"
                        className="px-4 py-2 rounded-lg bg-teal-700 text-white text-sm font-semibold flex items-center gap-2 hover:bg-teal-800 disabled:opacity-40"><Play size={16} weight="fill" /> {busy ? 'Working…' : 'Run dry-run planning'}</button>
                    <span className="text-xs text-[#6b7280] self-center" data-testid="dry-run-last-run">
                        {d?.last_run ? `Last run: ${fmtTime(d.last_run.at)} by ${d.last_run.by}` : 'Not run yet'} · {d?.fixtures ?? 0} synthetic bookings
                    </span>
                </div>
                <div className="grid grid-cols-2 sm:grid-cols-5 gap-3 mb-5">
                    <Stat k="Eligible" v={d?.last_run?.eligible} testid="dry-run-eligible-count" />
                    <Stat k="Ineligible" v={d?.last_run?.ineligible} testid="dry-run-ineligible-count" />
                    <Stat k="Scheduled" v={c.SCHEDULED} testid="dry-run-scheduled-count" />
                    <Stat k="Skipped" v={c.SKIPPED} testid="dry-run-skipped-count" />
                    <Stat k="Needs Review" v={c.NEEDS_REVIEW} testid="dry-run-review-count" />
                </div>
                {current.length ? <DryRunJobsTable jobs={current} onReschedule={(id) => act(() => aiApi.post(`/dry-run/fixtures/${id}/reschedule`), () => 'Synthetic booking moved one day later. Run planning again.')} />
                    : <p className="text-sm text-[#9b9787]" data-testid="dry-run-empty">No dry-run jobs yet. Load synthetic bookings, then run dry-run planning.</p>}
            </Card>
            {invalid.length > 0 && (
                <Card data-testid="dry-run-invalidated">
                    <SectionTitle icon={CalendarDots}>Invalidated plans ({invalid.length})</SectionTitle>
                    <DryRunJobsTable jobs={invalid} onReschedule={() => {}} />
                </Card>
            )}
        </div>
    );
};
