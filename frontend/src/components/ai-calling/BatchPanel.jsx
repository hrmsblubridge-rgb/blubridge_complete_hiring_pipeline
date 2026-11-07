import { useState } from 'react';
import { toast } from 'sonner';
import { Play, Stop, ListChecks, CheckCircle, XCircle } from '@phosphor-icons/react';
import { aiApi, errMsg } from '../../pages/ai-calling/aiApi';
import { Card, SectionTitle } from './AICallingHeader';

export const BatchPanel = ({ selected, batches, reload, startEnabled }) => {
    const [name, setName] = useState('');
    const [checks, setChecks] = useState(null);

    const create = async () => {
        try { await aiApi.post('/test-batches', { name, candidate_ids: selected }); toast.success('Test batch created (no calls started)'); setName(''); reload(); }
        catch (e) { toast.error(errMsg(e)); }
    };
    const preflight = async (b) => {
        try { const r = await aiApi.post(`/test-batches/${b.id}/preflight`); setChecks({ batch: b, results: r.data.results }); }
        catch (e) { toast.error(errMsg(e)); }
    };
    const stop = async (b) => {
        try { await aiApi.post(`/test-batches/${b.id}/stop`); toast.success('Batch stopped'); reload(); }
        catch (e) { toast.error(errMsg(e)); }
    };

    return (
        <Card data-testid="batch-panel">
            <SectionTitle icon={ListChecks}>Test batches</SectionTitle>
            <div className="flex flex-wrap items-end gap-2">
                <input value={name} onChange={e => setName(e.target.value)} placeholder="Batch name (optional)" data-testid="batch-name-input"
                    className="flex-1 min-w-[200px] bg-white border border-[#e5e3d8] rounded-lg px-3 py-2.5 text-sm focus:outline-none focus:border-teal-500" />
                <button onClick={create} disabled={!selected.length} data-testid="batch-create-btn" className="px-4 py-2.5 rounded-lg bg-teal-700 hover:bg-teal-800 text-white text-sm font-semibold disabled:opacity-50">
                    Create batch from {selected.length} selected
                </button>
            </div>
            <div className="mt-4 space-y-2">
                {batches.length === 0 && <p className="text-sm text-[#9b9787]" data-testid="batch-empty">No batches yet. Select approved candidates above.</p>}
                {batches.map(b => (
                    <div key={b.id} className="flex flex-wrap items-center gap-2 border border-[#efede5] rounded-xl px-3 py-2.5" data-testid={`batch-row-${b.id}`}>
                        <div className="flex-1 min-w-[180px]">
                            <p className="text-sm font-semibold text-[#1a2332]">{b.name}</p>
                            <p className="text-xs text-[#6b7280]">{b.candidate_ids.length} recipient(s) · status: <b>{b.status}</b> · mode v{b.mode_version}</p>
                        </div>
                        <button onClick={() => preflight(b)} data-testid={`batch-preflight-${b.id}`} className="px-3 py-2 rounded-lg border border-[#e5e3d8] bg-white text-xs font-semibold hover:bg-[#efede5]">Run safety check</button>
                        <button disabled={!startEnabled} title={startEnabled ? '' : 'Disabled until Bolna API integration is approved'} data-testid={`batch-start-${b.id}`}
                            className="px-3 py-2 rounded-lg bg-teal-700 text-white text-xs font-semibold flex items-center gap-1 disabled:opacity-40 disabled:cursor-not-allowed"><Play size={12} weight="fill" /> Start Test Calls</button>
                        <button onClick={() => stop(b)} disabled={b.status === 'stopped'} data-testid={`batch-stop-${b.id}`} className="px-3 py-2 rounded-lg border border-rose-200 bg-rose-50 text-rose-700 text-xs font-semibold flex items-center gap-1 disabled:opacity-40"><Stop size={12} weight="fill" /> Stop Test Calls</button>
                    </div>
                ))}
            </div>
            {!startEnabled && <p className="text-xs text-[#6b7280] mt-3" data-testid="start-disabled-note">Start Test Calls stays disabled until the Bolna API integration is approved.</p>}
            {checks && (
                <div className="mt-4 border border-[#e5e3d8] rounded-xl p-3" data-testid="preflight-results">
                    <p className="text-sm font-semibold mb-2">Safety check — {checks.batch.name}</p>
                    {checks.results.map(r => (
                        <div key={r.candidate_id} className="mb-3">
                            <p className="text-sm">{r.candidate_name} {r.phone_masked} — {r.allowed ? <span className="text-emerald-700 font-bold">ALLOWED</span> : <span className="text-rose-700 font-bold">BLOCKED</span>}</p>
                            <ul className="grid sm:grid-cols-2 gap-x-4 mt-1">
                                {r.checks.map(c => (
                                    <li key={c.key} className="flex items-center gap-1.5 text-xs text-[#1a2332]">
                                        {c.ok ? <CheckCircle size={13} weight="fill" className="text-emerald-600" /> : <XCircle size={13} weight="fill" className="text-rose-500" />}
                                        {c.label}{c.detail ? <span className="text-[#9b9787]"> ({c.detail})</span> : null}
                                    </li>
                                ))}
                            </ul>
                        </div>
                    ))}
                </div>
            )}
        </Card>
    );
};
