import { fmtTime } from './callFormat';

const CLS = {
    SCHEDULED: 'bg-emerald-100 text-emerald-800', SKIPPED: 'bg-zinc-200 text-zinc-700',
    NEEDS_REVIEW: 'bg-amber-100 text-amber-800', INVALIDATED: 'bg-rose-100 text-rose-700',
};
const LABEL = { SCHEDULED: 'Scheduled', SKIPPED: 'Skipped', NEEDS_REVIEW: 'Needs Review', INVALIDATED: 'Invalidated' };

const Badge = ({ s }) => <span className={`px-2 py-0.5 rounded-full text-[11px] font-bold whitespace-nowrap ${CLS[s] || 'bg-zinc-100'}`} data-testid="dry-run-status-badge">{LABEL[s] || s}</span>;

export const DryRunJobsTable = ({ jobs, onReschedule, showConsent = false }) => (
    <div className="overflow-x-auto" data-testid="dry-run-jobs-table">
        <table className="w-full text-sm">
            <thead className="text-[11px] uppercase tracking-wider text-[#9b9787]">
                <tr>{['Candidate', 'Job role', 'Interview / 24 h target', 'Planned AI call', 'Retry (live only)', ...(showConsent ? ['Consent'] : []), 'Status', 'Reason', ''].map(h =>
                    <th key={h} className="px-2 py-2 text-left font-semibold whitespace-nowrap">{h}</th>)}</tr>
            </thead>
            <tbody>
                {jobs.map(j => (
                    <tr key={j.id} className={`border-t border-[#efede5] align-top ${j.status === 'INVALIDATED' ? 'opacity-60' : ''}`} data-testid={`dry-run-job-${j.id}`}>
                        <td className="px-2 py-2"><div className="font-semibold">{j.candidate_name}</div><div className="font-mono text-xs text-[#6b7280]">{j.phone_masked}</div></td>
                        <td className="px-2 py-2">{j.job_role}</td>
                        <td className="px-2 py-2 whitespace-nowrap">{fmtTime(j.interview_at) || '—'}<div className="text-xs text-[#9b9787]">{j.target_at ? `target ${fmtTime(j.target_at)}` : ''}</div></td>
                        <td className="px-2 py-2 max-w-[13rem]" data-testid="dry-run-planned">
                            <span className="whitespace-nowrap">{fmtTime(j.planned_at) || '—'}</span>
                            {j.adjustments?.map(a => <div key={a} className="text-[11px] text-amber-700">{a}</div>)}
                        </td>
                        <td className="px-2 py-2 whitespace-nowrap text-xs">{j.status === 'SCHEDULED' ? (j.retry?.eligible ? fmtTime(j.retry.planned_at) : 'Not eligible') : '—'}</td>
                        {showConsent && <td className="px-2 py-2 text-xs" data-testid="real-consent">{j.consent}</td>}
                        <td className="px-2 py-2"><Badge s={j.status} /></td>
                        <td className="px-2 py-2 text-xs font-mono break-words max-w-[11rem]" data-testid="dry-run-reason">{j.reasons?.join(', ') || '—'}</td>
                        <td className="px-2 py-2">
                            {!showConsent && ['SCHEDULED', 'NEEDS_REVIEW'].includes(j.status) && (
                                <button onClick={() => onReschedule(j.booking_id)} data-testid={`dry-run-reschedule-${j.id}`}
                                    className="text-[11px] px-2 py-1 rounded border border-[#e5e3d8] bg-white hover:bg-[#efede5] whitespace-nowrap">Simulate reschedule</button>
                            )}
                        </td>
                    </tr>
                ))}
            </tbody>
        </table>
    </div>
);
