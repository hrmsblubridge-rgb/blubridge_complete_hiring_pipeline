// Pending Authorization tab. Reads from /pending-authorization and submits bulk decisions to
// /pending-authorization/review. This UI NEVER creates candidate consent; admin decisions live
// in separate admin-authorization collections and NEVER trigger dispatch.
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { toast } from 'sonner';
import { ClipboardText, CheckCircle, XCircle, Clock, Spinner, Shield, Warning } from '@phosphor-icons/react';
import { aiApi, errMsg } from './aiApi';
import { AICallingHeader, Card, SectionTitle } from '../../components/ai-calling/AICallingHeader';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from '../../components/ui/dialog';

const PURPOSES = [
    { key: 'interview_confirmation', label: 'Pre-Interview Confirmation' },
    { key: 'missed_interview_followup', label: 'Missed-Interview Follow-up' },
];

export default function PendingAuthorization() {
    const [data, setData] = useState({ items: [], total: 0, page: 1, page_size: 50 });
    const [filters, setFilters] = useState({ job_role: '', date_from: '', date_to: '' });
    const [selected, setSelected] = useState({});   // {registration_id: snapshot}
    const [loading, setLoading] = useState(false);
    const [reviewOpen, setReviewOpen] = useState(false);
    const [reviewBusy, setReviewBusy] = useState(false);
    const [purposes, setPurposes] = useState({ interview_confirmation: true, missed_interview_followup: false });
    const [policyId, setPolicyId] = useState('');
    const [evidence, setEvidence] = useState('');
    const [reason, setReason] = useState('');
    const [decision, setDecision] = useState('approve');
    const inFlight = useRef(false);

    const load = useCallback(async (p = 1) => {
        setLoading(true);
        try {
            const params = new URLSearchParams();
            Object.entries({ ...filters, page: p, page_size: 50 }).forEach(([k, v]) => { if (v) params.set(k, v); });
            const r = (await aiApi.get('/pending-authorization?' + params.toString())).data;
            setData(r);
        } catch (e) { toast.error(errMsg(e, 'Failed to load pending authorizations')); } finally { setLoading(false); }
    }, [filters]);

    useEffect(() => { load(1); }, [load]);

    const selectedIds = useMemo(() => Object.keys(selected), [selected]);
    const pickAllOnPage = () => {
        const next = { ...selected };
        data.items.forEach(i => { next[i.registration_id] = i; });
        setSelected(next);
    };
    const clearAll = () => setSelected({});
    const togglePurpose = (k) => setPurposes(p => ({ ...p, [k]: !p[k] }));

    const review = async () => {
        if (inFlight.current || reviewBusy) return;
        const chosenPurposes = Object.entries(purposes).filter(([, v]) => v).map(([k]) => k);
        if (!chosenPurposes.length) { toast.error('Pick at least one calling purpose'); return; }
        if (decision === 'approve' && (!policyId.trim() || !evidence.trim())) {
            toast.error('Approval requires policy ID and evidence reference'); return;
        }
        inFlight.current = true; setReviewBusy(true);
        try {
            const body = {
                registration_ids: selectedIds, purposes: chosenPurposes, decision,
                policy_id: policyId.trim() || null, evidence_ref: evidence.trim() || null,
                reason: reason.trim() || null,
            };
            const r = (await aiApi.post('/pending-authorization/review', body)).data;
            toast.success(`${r.approved.length} approved · ${r.deferred.length} deferred · ${r.denied.length} denied · ${r.skipped.length} skipped. No call was started.`);
            setReviewOpen(false); setSelected({}); setPolicyId(''); setEvidence(''); setReason(''); load(data.page);
        } catch (e) { toast.error(errMsg(e, 'Review failed')); } finally { inFlight.current = false; setReviewBusy(false); }
    };

    return (
        <div className="min-h-screen" data-testid="pending-authorization-page">
            <AICallingHeader title="Pending Authorization" subtitle="Admin alternative-basis review — never overrides candidate opt-outs or starts calls" />
            <main className="max-w-6xl mx-auto px-6 lg:px-10 py-6 space-y-5">
                <Card className="border-amber-200">
                    <div className="flex items-start gap-2 text-sm text-amber-900">
                        <Warning size={18} weight="fill" className="shrink-0 mt-0.5 text-amber-700" />
                        <p>Reviewing here <b>never</b> creates candidate consent and <b>never</b> starts a phone call.
                            Candidate Do-Not-Call and withdrawn consent always override any admin decision. Actual dispatch stays
                            blocked by every safety gate (Emergency Stop, Server Outbound Calling, Live Dispatch Authorization).</p>
                    </div>
                </Card>

                <Card>
                    <SectionTitle icon={ClipboardText}>Filters</SectionTitle>
                    <div className="grid sm:grid-cols-4 gap-3">
                        <input placeholder="Job role" value={filters.job_role} onChange={e => setFilters(f => ({ ...f, job_role: e.target.value }))}
                            data-testid="pa-filter-job" className="bg-white border border-[#e5e3d8] rounded-lg px-3 py-2 text-sm" />
                        <input type="date" value={filters.date_from} onChange={e => setFilters(f => ({ ...f, date_from: e.target.value }))}
                            data-testid="pa-filter-from" className="bg-white border border-[#e5e3d8] rounded-lg px-3 py-2 text-sm" />
                        <input type="date" value={filters.date_to} onChange={e => setFilters(f => ({ ...f, date_to: e.target.value }))}
                            data-testid="pa-filter-to" className="bg-white border border-[#e5e3d8] rounded-lg px-3 py-2 text-sm" />
                        <button onClick={() => load(1)} disabled={loading} data-testid="pa-apply-filters"
                            className="px-4 py-2 rounded-lg bg-teal-700 text-white text-sm font-semibold disabled:opacity-50 flex items-center gap-2">
                            {loading && <Spinner size={14} className="animate-spin" />} Apply
                        </button>
                    </div>
                </Card>

                <Card>
                    <div className="flex flex-wrap items-center justify-between gap-2 mb-3">
                        <SectionTitle icon={Shield}>Candidates needing review ({data.total})</SectionTitle>
                        <div className="flex gap-2">
                            <button onClick={pickAllOnPage} data-testid="pa-select-page" className="px-3 py-1.5 rounded-lg border border-[#e5e3d8] bg-white text-xs font-semibold">Select page</button>
                            <button onClick={clearAll} data-testid="pa-clear-selection" className="px-3 py-1.5 rounded-lg border border-[#e5e3d8] bg-white text-xs font-semibold">Clear selection ({selectedIds.length})</button>
                            <button onClick={() => setReviewOpen(true)} disabled={!selectedIds.length} data-testid="pa-review-btn"
                                className="px-4 py-1.5 rounded-lg bg-teal-700 text-white text-xs font-bold disabled:opacity-40">
                                Review Selected for Authorization ({selectedIds.length})
                            </button>
                        </div>
                    </div>
                    {loading && !data.items.length ? <p className="text-sm text-[#6b7280] flex items-center gap-2"><Spinner size={14} className="animate-spin" /> Loading…</p> :
                        data.items.length === 0 ? <p className="text-sm text-[#6b7280]" data-testid="pa-empty">No future bookings require authorization review.</p> : (
                        <div className="overflow-x-auto">
                            <table className="w-full text-sm">
                                <thead className="text-[11px] uppercase tracking-wider text-[#9b9787]">
                                    <tr><th className="px-2 py-2 text-left"></th>{['Candidate', 'Role', 'Phone', 'Interview', 'Booking', 'Consent', 'Uncovered', 'Reason'].map(h => <th key={h} className="px-2 py-2 text-left font-semibold whitespace-nowrap">{h}</th>)}</tr>
                                </thead>
                                <tbody>
                                    {data.items.map(i => (
                                        <tr key={i.registration_id} className="border-t border-[#efede5]" data-testid={`pa-row-${i.registration_id}`}>
                                            <td className="px-2 py-2"><input type="checkbox" checked={!!selected[i.registration_id]} onChange={e => setSelected(s => ({ ...s, [i.registration_id]: e.target.checked ? i : undefined }))} data-testid={`pa-check-${i.registration_id}`} /></td>
                                            <td className="px-2 py-2 font-semibold">{i.candidate_name}</td>
                                            <td className="px-2 py-2">{i.job_role}</td>
                                            <td className="px-2 py-2 font-mono text-xs">{i.phone_masked}</td>
                                            <td className="px-2 py-2 whitespace-nowrap">{i.interview_date} {i.interview_time}</td>
                                            <td className="px-2 py-2">{i.booking_status || '—'}</td>
                                            <td className="px-2 py-2">{i.consent_status} {i.consent_version ? `(${i.consent_version})` : ''}</td>
                                            <td className="px-2 py-2">{i.uncovered_purposes.join(', ')}</td>
                                            <td className="px-2 py-2 text-xs text-[#6b7280]">{i.review_reason}</td>
                                        </tr>
                                    ))}
                                </tbody>
                            </table>
                        </div>
                    )}
                    <div className="flex justify-between items-center mt-3 text-xs text-[#6b7280]">
                        <span>Page {data.page}</span>
                        <div className="flex gap-2">
                            <button disabled={data.page <= 1} onClick={() => load(data.page - 1)} className="px-3 py-1 rounded border border-[#e5e3d8] bg-white disabled:opacity-40">Prev</button>
                            <button disabled={data.items.length < data.page_size} onClick={() => load(data.page + 1)} className="px-3 py-1 rounded border border-[#e5e3d8] bg-white disabled:opacity-40">Next</button>
                        </div>
                    </div>
                </Card>
            </main>

            <Dialog open={reviewOpen} onOpenChange={o => !reviewBusy && setReviewOpen(o)}>
                <DialogContent data-testid="pa-review-dialog" className="bg-[#fffdf7] max-w-xl">
                    <DialogHeader>
                        <DialogTitle>Review {selectedIds.length} selected candidate{selectedIds.length !== 1 ? 's' : ''}</DialogTitle>
                        <DialogDescription>No call will be started. This records an admin alternative-basis decision only;
                            it never writes to candidate consent. Candidate opt-outs always win.</DialogDescription>
                    </DialogHeader>
                    <div className="space-y-3">
                        <div>
                            <p className="text-[11px] font-semibold tracking-wider text-[#9b9787] uppercase mb-1">Calling purposes (each is independent)</p>
                            {PURPOSES.map(p => (
                                <label key={p.key} className="flex items-center gap-2 text-sm">
                                    <input type="checkbox" checked={purposes[p.key]} onChange={() => togglePurpose(p.key)} data-testid={`pa-purpose-${p.key}`} />
                                    {p.label}
                                </label>
                            ))}
                        </div>
                        <div>
                            <p className="text-[11px] font-semibold tracking-wider text-[#9b9787] uppercase mb-1">Decision</p>
                            <select value={decision} onChange={e => setDecision(e.target.value)} data-testid="pa-decision" className="bg-white border border-[#e5e3d8] rounded-lg px-3 py-2 text-sm">
                                <option value="approve">Approve (alternative basis)</option>
                                <option value="defer">Defer for more evidence</option>
                                <option value="deny">Deny</option>
                            </select>
                        </div>
                        <input value={policyId} onChange={e => setPolicyId(e.target.value)} placeholder="Approved lawful-basis policy ID (required for approve)"
                            data-testid="pa-policy" className="w-full bg-white border border-[#e5e3d8] rounded-lg px-3 py-2 text-sm" />
                        <input value={evidence} onChange={e => setEvidence(e.target.value)} placeholder="Evidence reference (required for approve)"
                            data-testid="pa-evidence" className="w-full bg-white border border-[#e5e3d8] rounded-lg px-3 py-2 text-sm" />
                        <input value={reason} onChange={e => setReason(e.target.value)} placeholder="Reason / notes (optional)"
                            data-testid="pa-reason" maxLength={500} className="w-full bg-white border border-[#e5e3d8] rounded-lg px-3 py-2 text-sm" />
                    </div>
                    <DialogFooter>
                        <button onClick={() => setReviewOpen(false)} disabled={reviewBusy} data-testid="pa-review-cancel"
                            className="px-4 py-2 rounded-lg border border-[#e5e3d8] bg-white text-sm font-semibold">Cancel</button>
                        <button onClick={review} disabled={reviewBusy} data-testid="pa-review-submit"
                            className="px-4 py-2 rounded-lg bg-teal-700 text-white text-sm font-semibold disabled:opacity-50 flex items-center gap-2">
                            {reviewBusy ? <><Spinner size={14} className="animate-spin" /> Saving…</> : <><CheckCircle size={14} /> Save Decision</>}
                        </button>
                    </DialogFooter>
                </DialogContent>
            </Dialog>
        </div>
    );
}
