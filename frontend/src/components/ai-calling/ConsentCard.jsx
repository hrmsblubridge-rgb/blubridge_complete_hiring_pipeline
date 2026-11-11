import { useState } from 'react';
import { toast } from 'sonner';
import { aiApi, errMsg } from '../../pages/ai-calling/aiApi';
import { DncDialog } from './DncDialog';

const fmt = (v) => (v ? new Date(v).toLocaleString('en-IN', { timeZone: 'Asia/Kolkata', dateStyle: 'medium', timeStyle: 'short' }) : '—');
const Row = ({ label, value, testid }) => (
    <div className="flex justify-between gap-3 text-xs"><span className="text-zinc-500">{label}</span><span className="text-zinc-200 text-right" data-testid={testid}>{value}</span></div>
);

// Admin-only consent / Do Not Call status for ONE exact registration ID.
export const ConsentCard = ({ c, onChange }) => {
    const [dialog, setDialog] = useState(null);
    const [busy, setBusy] = useState(false);
    const submit = async (reason) => {
        setBusy(true);
        try {
            const r = await aiApi.post(`/consent/admin/${c.registration_id}/dnc`, { action: dialog, reason, confirm: true });
            onChange(r.data); setDialog(null); toast.success(dialog === 'mark' ? 'Do Not Call marked' : 'Admin Do Not Call removed');
        } catch (e) { toast.error(errMsg(e)); } finally { setBusy(false); }
    };
    const id = c.registration_id.slice(-6);
    return (
        <div className="border border-zinc-800 p-3 space-y-1.5" data-testid={`consent-card-${c.registration_id}`}>
            <Row label="Registration" value={`…${id}`} />
            <Row label="AI calling consent" value={c.consent_status} testid={`consent-status-${id}`} />
            <Row label="Consent date / source" value={`${fmt(c.consent_timestamp)} · ${c.consent_source || '—'}`} />
            {c.consent_withdrawn_at && <Row label="Withdrawn" value={fmt(c.consent_withdrawn_at)} />}
            <Row label="Do Not Call" value={c.do_not_call ? `Yes (${c.dnc_sources.join(', ')})` : 'No'} testid={`dnc-status-${id}`} />
            {c.do_not_call && <Row label="Marked by / reason" value={`${c.dnc_by || '—'} · ${c.dnc_reason || '—'}`} />}
            <Row label="Last change" value={fmt(c.last_change_at)} />
            <div className="flex gap-2 pt-1">
                {!c.dnc_sources.includes('ADMIN') && (
                    <button onClick={() => setDialog('mark')} data-testid={`dnc-mark-btn-${id}`} className="text-xs px-2 py-1 border border-red-800/60 text-red-400 hover:bg-red-900/30">Mark Do Not Call</button>
                )}
                {c.dnc_sources.includes('ADMIN') && (
                    <button onClick={() => setDialog('remove')} disabled={!c.can_remove_dnc} data-testid={`dnc-remove-btn-${id}`}
                        title={c.can_remove_dnc ? '' : 'Only a top-level administrator can remove Do Not Call'}
                        className="text-xs px-2 py-1 border border-emerald-800/60 text-emerald-400 hover:bg-emerald-900/30 disabled:opacity-40">Remove Do Not Call</button>
                )}
            </div>
            {c.dnc_sources.some(s => s !== 'ADMIN') && (
                <p className="text-[11px] text-zinc-500" data-testid={`dnc-locked-note-${id}`}>The candidate asked not to be called. Admins cannot remove this.</p>
            )}
            {c.history?.length > 0 && (
                <ul className="pt-1 space-y-0.5" data-testid={`consent-audit-${id}`}>
                    {c.history.slice(0, 5).map((h, i) => (
                        <li key={i} className="text-[11px] text-zinc-500">{fmt(h.at)} · {h.type === 'dnc' ? `DNC ${h.action} (${h.source})` : `consent ${h.status} (${h.source})`} · {h.by}</li>
                    ))}
                </ul>
            )}
            {dialog && <DncDialog action={dialog} busy={busy} onCancel={() => setDialog(null)} onConfirm={submit} />}
        </div>
    );
};
