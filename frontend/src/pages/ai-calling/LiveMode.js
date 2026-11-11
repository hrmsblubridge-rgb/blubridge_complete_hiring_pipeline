import { useEffect, useState } from 'react';
import { toast } from 'sonner';
import { Lock, CalendarCheck, ArrowClockwise, MapPin, UserCircle } from '@phosphor-icons/react';
import { aiApi, errMsg } from './aiApi';
import { AICallingHeader, Card, SectionTitle } from '../../components/ai-calling/AICallingHeader';
import { DryRunPreview } from '../../components/ai-calling/DryRunPreview';
import { RealBookingsPreview } from '../../components/ai-calling/RealBookingsPreview';

const Rule = ({ icon: Icon, title, text }) => (
    <div className="flex gap-3">
        <Icon size={20} weight="duotone" className="text-[#6b7280] shrink-0 mt-0.5" />
        <div><p className="text-sm font-semibold text-[#1a2332]">{title}</p><p className="text-xs text-[#6b7280]">{text}</p></div>
    </div>
);

export default function LiveMode() {
    const [st, setSt] = useState(null);
    const [tab, setTab] = useState('synthetic');
    useEffect(() => { aiApi.get('/live/status').then(r => setSt(r.data)).catch(e => toast.error(errMsg(e))); }, []);

    return (
        <div className="min-h-screen" data-testid="ai-live-page">
            <AICallingHeader title="Live Mode" subtitle="Calls to real booked candidates — locked in this phase" mode={st?.active ? 'live' : undefined} />
            <main className="max-w-6xl mx-auto px-6 lg:px-10 py-6 space-y-5">
                <div className="flex items-start gap-3 bg-rose-50 border border-rose-200 rounded-2xl p-4" data-testid="live-locked-banner">
                    <Lock size={22} weight="duotone" className="text-rose-700 shrink-0" />
                    <div>
                        <p className="text-sm font-bold text-rose-900">Live Mode is locked</p>
                        <p className="text-sm text-rose-900/80">Activation is blocked on the server. No real candidate is read or called in this phase.</p>
                    </div>
                </div>
                <Card>
                    <SectionTitle icon={CalendarCheck}>How Live Mode will work (after approval)</SectionTitle>
                    <div className="grid sm:grid-cols-2 gap-4">
                        <Rule icon={UserCircle} title="Eligible candidates" text="Booked interviews from the existing hiring records (read-only), excluding attended, missed, rescheduled-out or superseded bookings." />
                        <Rule icon={CalendarCheck} title="Call timing" text={`One confirmation call ${st?.call_hours_before ?? 24} hours before the interview, inside the configured call window.`} />
                        <Rule icon={ArrowClockwise} title="Retry" text={`${st?.no_answer_retries ?? 1} retry only when the first call is not answered.`} />
                        <Rule icon={MapPin} title="Interview location" text={st?.interview_location || 'Offline — Chennai office'} />
                    </div>
                </Card>
                <button disabled data-testid="live-activate-btn" title="Locked in this phase" className="px-5 py-2.5 rounded-lg bg-rose-700 text-white text-sm font-semibold opacity-40 cursor-not-allowed flex items-center gap-2">
                    <Lock size={16} /> Activate Live Mode (locked)
                </button>
                <div className="flex gap-2" role="tablist">
                    {[['synthetic', 'Synthetic Bookings'], ['real', 'Real Bookings']].map(([k, l]) => (
                        <button key={k} role="tab" aria-selected={tab === k} onClick={() => setTab(k)} data-testid={`live-tab-${k}`}
                            className={`px-4 py-2 rounded-lg text-sm font-semibold border ${tab === k ? 'bg-teal-700 text-white border-teal-700' : 'bg-white border-[#e5e3d8] text-[#1a2332]'}`}>{l}</button>
                    ))}
                </div>
                {tab === 'synthetic' ? <DryRunPreview /> : <RealBookingsPreview />}
            </main>
        </div>
    );
}
