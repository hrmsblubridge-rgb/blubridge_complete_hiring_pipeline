import { useCallback, useEffect, useState } from 'react';
import { toast } from 'sonner';
import { ClockCounterClockwise } from '@phosphor-icons/react';
import { aiApi, errMsg } from './aiApi';
import { AICallingHeader, Card, SectionTitle } from '../../components/ai-calling/AICallingHeader';
import { CallDetails } from '../../components/ai-calling/CallDetails';
import { StateBadge, fmtTime } from '../../components/ai-calling/callFormat';

const LIVE_STATES = ['Pending', 'In Progress'];

export default function CallHistory() {
    const [mode, setMode] = useState('testing');
    const [items, setItems] = useState([]);
    const [sel, setSel] = useState(null);

    const load = useCallback(() => aiApi.get(`/calls?mode=${mode}`).then(r => setItems(r.data.items)).catch(e => toast.error(errMsg(e))), [mode]);
    const open = (id) => aiApi.get(`/calls/${id}`).then(r => setSel(r.data)).catch(e => toast.error(errMsg(e)));
    useEffect(() => { setSel(null); load(); }, [load]);
    useEffect(() => {
        if (!items.some(c => LIVE_STATES.includes(c.ui_state))) return undefined;
        const t = setInterval(() => { load(); if (sel) open(sel.id); }, 30000);
        return () => clearInterval(t);
    }, [items, sel, load]);

    return (
        <div className="min-h-screen" data-testid="ai-history-page">
            <AICallingHeader title="Call History" subtitle="Call records, recordings, transcripts and extracted responses" />
            <main className="max-w-6xl mx-auto px-6 lg:px-10 py-6 space-y-5">
                <div className="flex gap-2">
                    {['testing', 'live'].map(m => (
                        <button key={m} onClick={() => setMode(m)} data-testid={`history-filter-${m}`}
                            className={`px-4 py-2 rounded-lg text-sm font-semibold border ${mode === m ? 'bg-teal-700 text-white border-teal-700' : 'bg-white border-[#e5e3d8] text-[#1a2332]'}`}>{m === 'testing' ? 'Test calls' : 'Live calls'}</button>
                    ))}
                </div>
                <Card data-testid="history-list">
                    <SectionTitle icon={ClockCounterClockwise}>{mode === 'testing' ? 'Test' : 'Live'} calls ({items.length})</SectionTitle>
                    {items.length === 0 ? <p className="text-sm text-[#9b9787]" data-testid="history-empty">No calls yet.</p> : (
                        <div className="overflow-x-auto">
                            <table className="w-full text-sm">
                                <thead className="text-[11px] uppercase tracking-wider text-[#9b9787]">
                                    <tr>{['Candidate', 'Phone', 'Call time', 'State', 'Bolna status', 'Duration', 'Attendance'].map(h => <th key={h} className="px-2 py-2 text-left font-semibold whitespace-nowrap">{h}</th>)}</tr>
                                </thead>
                                <tbody>
                                    {items.map(c => (
                                        <tr key={c.id} onClick={() => open(c.id)} data-testid={`history-row-${c.id}`} className={`border-t border-[#efede5] cursor-pointer hover:bg-[#faf9f1] ${sel?.id === c.id ? 'bg-[#faf9f1]' : ''}`}>
                                            <td className="px-2 py-2 font-semibold">{c.candidate_name}</td>
                                            <td className="px-2 py-2 font-mono text-xs">{c.phone_masked}</td>
                                            <td className="px-2 py-2 whitespace-nowrap">{fmtTime(c.dispatched_at || c.created_at)}</td>
                                            <td className="px-2 py-2"><StateBadge s={c.ui_state} /></td>
                                            <td className="px-2 py-2">{c.status || '—'}</td>
                                            <td className="px-2 py-2">{c.duration_seconds != null ? `${Math.round(c.duration_seconds)} s` : '—'}</td>
                                            <td className="px-2 py-2">{c.response?.attendance_status || 'UNKNOWN'}</td>
                                        </tr>
                                    ))}
                                </tbody>
                            </table>
                        </div>
                    )}
                </Card>
                {sel ? <CallDetails key={sel.id} call={sel} onUpdated={(d) => { setSel(d); load(); }} />
                    : items.length > 0 && <p className="text-sm text-[#9b9787]" data-testid="history-select-hint">Select a call to see the transcript, recording and extracted response.</p>}
            </main>
        </div>
    );
}
