import { useState } from 'react';
import { toast } from 'sonner';
import { UsersThree, Trash, Prohibit, ArrowCounterClockwise, SealCheck } from '@phosphor-icons/react';
import { aiApi, errMsg } from '../../pages/ai-calling/aiApi';
import { Card, SectionTitle } from './AICallingHeader';
import { ApproveDialog } from './ApproveDialog';

const Status = ({ c }) => {
    if (c.opted_out) return <span className="px-2 py-0.5 rounded-full bg-zinc-200 text-zinc-700 text-[11px] font-bold">Opted out</span>;
    if (c.approved) return <span className="px-2 py-0.5 rounded-full bg-emerald-100 text-emerald-800 text-[11px] font-bold">Approved</span>;
    return <span className="px-2 py-0.5 rounded-full bg-amber-100 text-amber-800 text-[11px] font-bold">Pending approval</span>;
};

const IconBtn = ({ title, onClick, children, testid, danger }) => (
    <button title={title} onClick={onClick} data-testid={testid}
        className={`p-1.5 rounded-lg border ${danger ? 'border-rose-200 bg-rose-50 hover:bg-rose-100 text-rose-700' : 'border-[#e5e3d8] bg-white hover:bg-[#efede5] text-[#1a2332]'}`}>{children}</button>
);

export const TestCandidateTable = ({ items, selected, setSelected, reload }) => {
    const [approving, setApproving] = useState(null);
    const act = async (fn, ok) => { try { await fn(); toast.success(ok); reload(); } catch (e) { toast.error(errMsg(e)); } };
    const toggle = (id) => setSelected(s => s.includes(id) ? s.filter(x => x !== id) : [...s, id]);
    const selectable = items.filter(c => c.approved && !c.opted_out);
    const allOn = selectable.length > 0 && selectable.every(c => selected.includes(c.id));

    return (
        <Card data-testid="candidate-table">
            <SectionTitle icon={UsersThree}>Test candidates ({items.length})</SectionTitle>
            {items.length === 0 ? <p className="text-sm text-[#9b9787]" data-testid="candidate-empty">No test candidates yet. Upload a sheet or add one manually.</p> : (
                <div className="overflow-x-auto">
                    <table className="w-full text-sm">
                        <thead className="text-[11px] uppercase tracking-wider text-[#9b9787]">
                            <tr>
                                <th className="px-2 py-2 text-left"><input type="checkbox" checked={allOn} disabled={!selectable.length} onChange={() => setSelected(allOn ? [] : selectable.map(c => c.id))} data-testid="select-all-approved" className="accent-teal-700" /></th>
                                {['Name', 'Phone', 'Role', 'Interview', 'Lang', 'Source', 'Status', ''].map(h => <th key={h} className="px-2 py-2 text-left font-semibold">{h}</th>)}
                            </tr>
                        </thead>
                        <tbody>
                            {items.map(c => (
                                <tr key={c.id} className="border-t border-[#efede5]" data-testid={`candidate-row-${c.id}`}>
                                    <td className="px-2 py-2"><input type="checkbox" disabled={!c.approved || c.opted_out} checked={selected.includes(c.id)} onChange={() => toggle(c.id)} data-testid={`select-${c.id}`} className="accent-teal-700" /></td>
                                    <td className="px-2 py-2 font-semibold text-[#1a2332]">{c.candidate_name}</td>
                                    <td className="px-2 py-2 font-mono text-xs">{c.phone_masked}</td>
                                    <td className="px-2 py-2">{c.job_role}</td>
                                    <td className="px-2 py-2 whitespace-nowrap">{c.interview_date} {c.interview_time}</td>
                                    <td className="px-2 py-2">{c.language}</td>
                                    <td className="px-2 py-2 text-xs text-[#6b7280]">{c.source}{c.source === 'upload' && c.sheet_approved_flag ? ' (sheet: yes)' : ''}</td>
                                    <td className="px-2 py-2"><Status c={c} /></td>
                                    <td className="px-2 py-2">
                                        <div className="flex gap-1 justify-end">
                                            {!c.approved && !c.opted_out && <IconBtn title="Approve" testid={`approve-${c.id}`} onClick={() => setApproving(c)}><SealCheck size={14} /></IconBtn>}
                                            {c.approved && <IconBtn title="Revoke approval" testid={`revoke-${c.id}`} onClick={() => act(() => aiApi.post(`/test-candidates/${c.id}/revoke`), 'Approval revoked')}><ArrowCounterClockwise size={14} /></IconBtn>}
                                            <IconBtn title={c.opted_out ? 'Clear opt-out' : 'Mark opted out'} testid={`optout-${c.id}`} onClick={() => act(() => aiApi.post(`/test-candidates/${c.id}/opt-out`, { opted_out: !c.opted_out }), 'Updated')}><Prohibit size={14} /></IconBtn>
                                            <IconBtn danger title="Delete" testid={`delete-${c.id}`} onClick={() => window.confirm(`Delete ${c.candidate_name}?`) && act(() => aiApi.delete(`/test-candidates/${c.id}`), 'Deleted')}><Trash size={14} /></IconBtn>
                                        </div>
                                    </td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
                </div>
            )}
            <ApproveDialog candidate={approving} onClose={() => setApproving(null)} onDone={() => { setApproving(null); reload(); }} />
        </Card>
    );
};
