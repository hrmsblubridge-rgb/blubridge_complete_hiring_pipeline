import { useState } from 'react';
import { toast } from 'sonner';
import { Warning, ArrowsClockwise } from '@phosphor-icons/react';
import { aiApi, errMsg } from '../../pages/ai-calling/aiApi';
import { Card } from './AICallingHeader';
import { DryRunJobsTable } from './DryRunJobsTable';
import { fmtTime } from './callFormat';

// Read-only plan for existing bookings (bb_registrations). Creates no jobs, never dials.
export const RealBookingsPreview = () => {
    const [d, setD] = useState(null);
    const [busy, setBusy] = useState(false);
    const run = async () => {
        setBusy(true);
        try { setD((await aiApi.get('/dry-run/real-preview')).data); } catch (e) { toast.error(errMsg(e)); } finally { setBusy(false); }
    };
    const rows = (d?.rows || []).map(r => ({ ...r, id: r.registration_id, reasons: r.reasons, consent: r.consent_status }));
    return (
        <div className="space-y-5" data-testid="real-bookings-preview">
            <div className="flex items-center gap-3 bg-amber-100 border-2 border-amber-400 rounded-2xl px-5 py-4" data-testid="real-dry-run-warning">
                <Warning size={26} weight="fill" className="text-amber-700 shrink-0" />
                <p className="text-base font-extrabold tracking-wide text-amber-900">DRY RUN — NO PHONE CALLS WILL BE PLACED.</p>
            </div>
            <Card>
                <div className="flex flex-wrap items-center gap-3 mb-4">
                    <button onClick={run} disabled={busy} data-testid="real-preview-run-btn" className="px-4 py-2 rounded-lg bg-teal-700 text-white text-sm font-semibold flex items-center gap-2 disabled:opacity-40">
                        <ArrowsClockwise size={16} /> {busy ? 'Working…' : 'Run preview'}
                    </button>
                    <span className="text-xs text-[#6b7280]" data-testid="real-preview-meta">
                        {d ? `${d.bookings} bookings read from ${d.source} at ${fmtTime(d.generated_at)} · eligible ${d.eligible} · ineligible ${d.ineligible} · needs review ${d.counts.NEEDS_REVIEW}` : 'Reads existing bookings only. Nothing is saved and no call jobs are created.'}
                    </span>
                </div>
                {d && (rows.length ? <DryRunJobsTable jobs={rows} showConsent onReschedule={() => {}} />
                    : <p className="text-sm text-[#9b9787]" data-testid="real-preview-empty">No booked interviews in this database.</p>)}
            </Card>
        </div>
    );
};
