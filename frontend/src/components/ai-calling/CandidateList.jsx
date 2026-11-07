import { useState } from 'react';
import { toast } from 'sonner';
import { UsersThree, Trash, Prohibit, ArrowCounterClockwise, SealCheck, PencilSimple, PhoneOutgoing } from '@phosphor-icons/react';
import { aiApi, errMsg } from '../../pages/ai-calling/aiApi';
import { Card, SectionTitle } from './AICallingHeader';
import { ApproveDialog } from './ApproveDialog';
import { EditCandidateDialog } from './EditCandidateDialog';
import { BulkConfirmDialog } from './BulkConfirmDialog';
import { CandidateFilters } from './CandidateFilters';
import { READINESS, CALLING_DISABLED_MSG } from './constants';

const Approval = ({ c }) => c.opted_out ? <span className="text-xs text-zinc-600 font-semibold">Opted out</span>
    : c.approved ? <span className="text-xs text-emerald-700 font-semibold" title={`by ${c.approved_by} at ${c.approved_at}`}>Approved</span>
        : <span className="text-xs text-amber-700 font-semibold">Pending</span>;

const Btn = ({ title, onClick, children, testid, danger, disabled }) => (
    <button title={title} onClick={onClick} disabled={disabled} data-testid={testid}
        className={`p-1.5 rounded-lg border disabled:opacity-40 disabled:cursor-not-allowed ${danger ? 'border-rose-200 bg-rose-50 hover:bg-rose-100 text-rose-700' : 'border-[#e5e3d8] bg-white hover:bg-[#efede5] text-[#1a2332]'}`}>{children}</button>
);

const BulkBtn = ({ children, ...p }) => <button {...p} className="px-3 py-1.5 rounded-lg border border-[#e5e3d8] bg-white text-xs font-semibold hover:bg-[#efede5] disabled:opacity-40">{children}</button>;

export const CandidateList = ({ data, q, setQ, selected, setSelected, reload }) => {
    const [approving, setApproving] = useState(null);
    const [editing, setEditing] = useState(null);
    const [bulk, setBulk] = useState(null);
    const items = data.items || [];
    const selIds = Object.keys(selected);
    const act = async (fn, ok) => { try { await fn(); toast.success(ok); reload(); } catch (e) { toast.error(errMsg(e)); } };
    const toggle = (c) => setSelected(s => { const n = { ...s }; n[c.id] ? delete n[c.id] : (n[c.id] = c); return n; });
    const pageAll = items.length > 0 && items.every(c => selected[c.id]);
    const togglePage = () => setSelected(s => { const n = { ...s }; items.forEach(c => pageAll ? delete n[c.id] : (n[c.id] = c)); return n; });
    const bulkRevoke = () => act(() => aiApi.post('/test-candidates/bulk-revoke', { ids: selIds }), `Revoked ${selIds.length}`);
    const done = () => { setBulk(null); setSelected({}); reload(); };

    return (
        <Card data-testid="candidate-table">
            <SectionTitle icon={UsersThree}>Test candidates ({data.total ?? 0})</SectionTitle>
            <CandidateFilters q={q} setQ={setQ} />
            <div className="flex flex-wrap items-center gap-2 mb-3" data-testid="bulk-bar">
                <span className="text-xs text-[#6b7280]" data-testid="selected-count">{selIds.length} selected</span>
                <BulkBtn disabled={!selIds.length} onClick={() => setBulk('approve')} data-testid="bulk-approve-btn">Bulk approve</BulkBtn>
                <BulkBtn disabled={!selIds.length} onClick={bulkRevoke} data-testid="bulk-revoke-btn">Bulk revoke</BulkBtn>
                <BulkBtn disabled={!selIds.length} onClick={() => setBulk('delete')} data-testid="bulk-delete-btn">Delete selected</BulkBtn>
                <BulkBtn disabled={!selIds.length} onClick={() => setSelected({})} data-testid="clear-selection-btn">Clear selection</BulkBtn>
            </div>
            {items.length === 0 ? <p className="text-sm text-[#9b9787]" data-testid="candidate-empty">No test candidates match. Upload a sheet or add one manually.</p> : (
                <div className="overflow-x-auto">
                    <table className="w-full text-sm">
                        <thead className="text-[11px] uppercase tracking-wider text-[#9b9787]">
                            <tr>
                                <th className="px-2 py-2 text-left"><input type="checkbox" checked={pageAll} onChange={togglePage} data-testid="select-page" className="accent-teal-700" /></th>
                                {['Name', 'Phone', 'Role', 'Interview (IST)', 'Lang', 'Source', 'Approval', 'Call readiness', 'Actions'].map(h => <th key={h} className="px-2 py-2 text-left font-semibold whitespace-nowrap">{h}</th>)}
                            </tr>
                        </thead>
                        <tbody>
                            {items.map(c => {
                                const [rl, rc] = READINESS[c.readiness] || [c.readiness, ''];
                                return (
                                    <tr key={c.id} className="border-t border-[#efede5]" data-testid={`candidate-row-${c.id}`}>
                                        <td className="px-2 py-2"><input type="checkbox" checked={!!selected[c.id]} onChange={() => toggle(c)} data-testid={`select-${c.id}`} className="accent-teal-700" /></td>
                                        <td className="px-2 py-2"><p className="font-semibold text-[#1a2332]">{c.candidate_name}</p><p className="text-[10px] text-[#9b9787] font-mono">{c.test_candidate_id}</p></td>
                                        <td className="px-2 py-2 font-mono text-xs">{c.phone_masked}</td>
                                        <td className="px-2 py-2">{c.job_role}</td>
                                        <td className="px-2 py-2 whitespace-nowrap">{c.interview_date} {c.interview_time}</td>
                                        <td className="px-2 py-2">{c.language}</td>
                                        <td className="px-2 py-2 text-xs text-[#6b7280]">{c.source}{c.source === 'upload' && c.sheet_approved_flag ? ' (sheet: YES)' : ''}</td>
                                        <td className="px-2 py-2"><Approval c={c} /></td>
                                        <td className="px-2 py-2"><span className={`px-2 py-0.5 rounded-full text-[11px] font-bold whitespace-nowrap ${rc}`} data-testid={`readiness-${c.id}`}>{rl}</span></td>
                                        <td className="px-2 py-2">
                                            <div className="flex gap-1">
                                                {!c.approved && !c.opted_out && <Btn title="Approve" testid={`approve-${c.id}`} onClick={() => setApproving(c)}><SealCheck size={14} /></Btn>}
                                                {c.approved && <Btn title="Revoke approval" testid={`revoke-${c.id}`} onClick={() => act(() => aiApi.post(`/test-candidates/${c.id}/revoke`), 'Approval revoked')}><ArrowCounterClockwise size={14} /></Btn>}
                                                <Btn title="Edit" testid={`edit-${c.id}`} onClick={() => setEditing(c)}><PencilSimple size={14} /></Btn>
                                                <Btn title={c.opted_out ? 'Clear opt-out' : 'Mark opted out'} testid={`optout-${c.id}`} onClick={() => act(() => aiApi.post(`/test-candidates/${c.id}/opt-out`, { opted_out: !c.opted_out }), 'Updated')}><Prohibit size={14} /></Btn>
                                                <Btn title={CALLING_DISABLED_MSG} testid={`call-now-${c.id}`} disabled><PhoneOutgoing size={14} /></Btn>
                                                <Btn danger title="Delete" testid={`delete-${c.id}`} onClick={() => window.confirm(`Delete ${c.candidate_name}?`) && act(() => aiApi.delete(`/test-candidates/${c.id}`), 'Deleted')}><Trash size={14} /></Btn>
                                            </div>
                                        </td>
                                    </tr>
                                );
                            })}
                        </tbody>
                    </table>
                </div>
            )}
            <div className="flex items-center justify-between mt-3 text-xs text-[#6b7280]" data-testid="pagination">
                <span>Page {data.page || 1} of {data.pages || 1}</span>
                <div className="flex gap-2">
                    <BulkBtn disabled={(data.page || 1) <= 1} onClick={() => setQ(p => ({ ...p, page: p.page - 1 }))} data-testid="page-prev">Previous</BulkBtn>
                    <BulkBtn disabled={(data.page || 1) >= (data.pages || 1)} onClick={() => setQ(p => ({ ...p, page: p.page + 1 }))} data-testid="page-next">Next</BulkBtn>
                </div>
            </div>
            <ApproveDialog key={approving?.id || 'none'} candidate={approving} onClose={() => setApproving(null)} onDone={() => { setApproving(null); reload(); }} />
            <EditCandidateDialog candidate={editing} onClose={() => setEditing(null)} onDone={() => { setEditing(null); reload(); }} />
            <BulkConfirmDialog key={bulk || 'none'} action={bulk} items={Object.values(selected)} onClose={() => setBulk(null)} onDone={done} />
        </Card>
    );
};
