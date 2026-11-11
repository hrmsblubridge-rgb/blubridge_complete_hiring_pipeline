import { useEffect, useState } from 'react';
import { toast } from 'sonner';
import { Archive } from '@phosphor-icons/react';
import { aiApi, errMsg } from '../../pages/ai-calling/aiApi';
import { Card, SectionTitle } from './AICallingHeader';
import { fmtTime } from './callFormat';

const STATUS = { eligible: 'Would be cleaned', not_yet_due: 'Not yet due', on_hold: 'Legal hold', nothing_sensitive: 'No sensitive data' };

const PreviewTable = ({ rows }) => (
    <div className="overflow-x-auto" data-testid="retention-preview-table">
        <table className="w-full text-sm">
            <thead className="text-[11px] uppercase tracking-wider text-[#9b9787]">
                <tr>{['Call', 'Mode', 'Age', 'Eligible from', 'Status', 'Fields affected'].map(h => <th key={h} className="px-2 py-2 text-left font-semibold">{h}</th>)}</tr>
            </thead>
            <tbody>
                {rows.map(r => (
                    <tr key={r.call_id} className="border-t border-[#efede5] align-top" data-testid={`retention-row-${r.call_id}`}>
                        <td className="px-2 py-2"><div className="font-semibold">{r.candidate_name || '—'}</div><div className="font-mono text-xs text-[#6b7280]">{r.call_id.slice(-8)}</div></td>
                        <td className="px-2 py-2">{r.mode}</td>
                        <td className="px-2 py-2">{r.age_days ?? '—'} d</td>
                        <td className="px-2 py-2 whitespace-nowrap">{fmtTime(r.eligible_from) || '—'}</td>
                        <td className="px-2 py-2 font-semibold" data-testid={`retention-row-status-${r.call_id}`}>{STATUS[r.status] || r.status}</td>
                        <td className="px-2 py-2 text-xs text-[#6b7280] min-w-[14rem] max-w-[18rem]">{r.fields.join(', ') || '—'}{r.provider_copy && <div className="text-amber-700">{r.provider_copy}</div>}</td>
                    </tr>
                ))}
            </tbody>
        </table>
    </div>
);

// Proposed retention policy + read-only preview. Nothing is ever deleted from here.
export const RetentionPanel = () => {
    const [pol, setPol] = useState(null);
    const [pv, setPv] = useState(null);
    const [days, setDays] = useState('');
    const [busy, setBusy] = useState(false);
    useEffect(() => { aiApi.get('/retention/policy').then(r => setPol(r.data)).catch(e => toast.error(errMsg(e))); }, []);
    const run = async () => {
        setBusy(true);
        try { setPv((await aiApi.get('/retention/preview', { params: days ? { days: Number(days) } : {} })).data); } catch (e) { toast.error(errMsg(e)); } finally { setBusy(false); }
    };
    return (
        <Card data-testid="retention-panel">
            <SectionTitle icon={Archive}>Call recording &amp; transcript retention (proposal)</SectionTitle>
            <p className="text-sm font-bold text-amber-800 mb-2" data-testid="retention-warning">PREVIEW ONLY — NOTHING IS DELETED. Deletion is not approved.</p>
            {pol && (
                <div className="grid sm:grid-cols-2 gap-4 text-xs text-[#1a2332] mb-4">
                    <div>
                        <p data-testid="retention-policy-days"><b>Proposed period:</b> {pol.policy.days} days (version {pol.policy.version}, {pol.policy.status})</p>
                        <p className="mt-2 font-semibold">Removed after the period</p>
                        <ul className="list-disc ml-4">{pol.sensitive_fields.map(f => <li key={f}>{f}</li>)}</ul>
                    </div>
                    <div>
                        <p className="font-semibold">Kept (minimum operational data)</p>
                        <ul className="list-disc ml-4">{pol.retained_fields.map(f => <li key={f}>{f}</li>)}</ul>
                        <p className="mt-2 text-[#6b7280]">{pol.retained_basis}</p>
                    </div>
                    <div className="sm:col-span-2" data-testid="retention-storage-map">
                        <p className="font-semibold">Where call data lives</p>
                        <ul className="space-y-1 mt-1">{pol.storage_map.map(s => <li key={s.where}><b>{s.where}:</b> {s.holds}{s.note && <span className="text-amber-700"> — {s.note}</span>}</li>)}</ul>
                    </div>
                </div>
            )}
            <div className="flex flex-wrap items-center gap-2 mb-3">
                <input value={days} onChange={e => setDays(e.target.value.replace(/\D/g, '').slice(0, 4))} placeholder={`${pol?.policy.days ?? 90} days`}
                    data-testid="retention-days-input" className="w-28 border border-[#e5e3d8] rounded-lg px-2 py-2 text-sm" />
                <button onClick={run} disabled={busy} data-testid="retention-preview-btn" className="px-4 py-2 rounded-lg bg-teal-700 text-white text-sm font-semibold disabled:opacity-50">{busy ? 'Working…' : 'Run retention preview'}</button>
                {pv && <span className="text-xs text-[#6b7280]" data-testid="retention-preview-counts">{pv.counts.records} calls · {pv.counts.eligible} would be cleaned · {pv.counts.not_yet_due} not yet due · {pv.counts.on_hold} on hold · deleted: {pv.deleted}</span>}
            </div>
            {pv && (pv.rows.length ? <PreviewTable rows={pv.rows} /> : <p className="text-sm text-[#9b9787]">No call records.</p>)}
        </Card>
    );
};
