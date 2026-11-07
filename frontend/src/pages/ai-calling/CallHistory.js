import { useEffect, useState } from 'react';
import { toast } from 'sonner';
import { ClockCounterClockwise, Waveform, ChatText, ListBullets } from '@phosphor-icons/react';
import { aiApi, errMsg } from './aiApi';
import { AICallingHeader, Card, SectionTitle } from '../../components/ai-calling/AICallingHeader';

const Placeholder = ({ icon: Icon, title, text, testid }) => (
    <Card data-testid={testid}>
        <SectionTitle icon={Icon}>{title}</SectionTitle>
        <div className="border border-dashed border-[#e5e3d8] rounded-xl p-6 text-center text-sm text-[#9b9787]">{text}</div>
    </Card>
);

export default function CallHistory() {
    const [mode, setMode] = useState('testing');
    const [items, setItems] = useState([]);
    const [sel, setSel] = useState(null);

    useEffect(() => {
        aiApi.get(`/calls?mode=${mode}`).then(r => { setItems(r.data.items); setSel(null); }).catch(e => toast.error(errMsg(e)));
    }, [mode]);

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
                    {items.length === 0 ? <p className="text-sm text-[#9b9787]" data-testid="history-empty">No calls yet. Calls appear here once Bolna integration is approved.</p> : (
                        <ul className="divide-y divide-[#efede5]">
                            {items.map(c => (
                                <li key={c.id}><button onClick={() => setSel(c)} data-testid={`history-row-${c.id}`} className="w-full text-left py-2 text-sm hover:bg-[#faf9f1]">{c.candidate_name || c.execution_id} · {c.status} · {c.outcome || '—'}</button></li>
                            ))}
                        </ul>
                    )}
                </Card>
                <div className="grid lg:grid-cols-3 gap-5">
                    <Placeholder icon={Waveform} title="Recording" testid="recording-placeholder" text={sel?.recording_url ? 'Recording available' : 'Recording player will appear here.'} />
                    <Placeholder icon={ChatText} title="Transcript" testid="transcript-placeholder" text={sel?.transcript || 'Full transcript will appear here.'} />
                    <Placeholder icon={ListBullets} title="Extracted response" testid="extracted-placeholder" text={sel?.outcome || 'Attendance, reschedule, decline, virtual request and questions will appear here.'} />
                </div>
            </main>
        </div>
    );
}
