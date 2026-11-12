import { useEffect, useState } from 'react';
import { toast } from 'sonner';
import { Lock, CalendarCheck, ArrowClockwise, MapPin, UserCircle, Queue, Alarm, Eye } from '@phosphor-icons/react';
import { aiApi, errMsg } from './aiApi';
import { AICallingHeader, Card, SectionTitle } from '../../components/ai-calling/AICallingHeader';
import { DryRunPreview } from '../../components/ai-calling/DryRunPreview';
import { RealBookingsPreview } from '../../components/ai-calling/RealBookingsPreview';
import { LivePrepPanel } from '../../components/ai-calling/LivePrepPanel';
import { PreviewScenariosPanel } from '../../components/ai-calling/PreviewScenariosPanel';

const Rule = ({ icon: Icon, title, text }) => (
    <div className="flex gap-3">
        <Icon size={20} weight="duotone" className="text-[#6b7280] shrink-0 mt-0.5" />
        <div><p className="text-sm font-semibold text-[#1a2332]">{title}</p><p className="text-xs text-[#6b7280]">{text}</p></div>
    </div>
);

export default function LiveMode() {
    const [st, setSt] = useState(null);
    const [tab, setTab] = useState('eligible');
    useEffect(() => { aiApi.get('/live/status').then(r => setSt(r.data)).catch(e => toast.error(errMsg(e))); }, []);

    return (
        <div className="min-h-screen" data-testid="ai-live-page">
            <AICallingHeader title="Live Mode" subtitle="Two automatic calling workflows — dispatch remains blocked" />
            <main className="max-w-6xl mx-auto px-6 lg:px-10 py-6 space-y-5">
                <div className="flex items-start gap-3 bg-rose-50 border border-rose-200 rounded-2xl p-4" data-testid="live-locked-banner">
                    <Lock size={22} weight="duotone" className="text-rose-700 shrink-0" />
                    <div>
                        <p className="text-sm font-bold text-rose-900">Live Mode is locked</p>
                        <p className="text-sm text-rose-900/80">The automatic worker is implemented but the real dispatch path is disabled. Real bookings are only read for dry-run and mock previews.</p>
                    </div>
                </div>

                <Card>
                    <SectionTitle icon={CalendarCheck}>Automatic calling workflows (after approval)</SectionTitle>
                    <div className="grid sm:grid-cols-2 gap-4">
                        <div className="border border-[#e5e3d8] rounded-xl p-3" data-testid="live-workflow-confirm">
                            <p className="text-sm font-bold text-teal-800 mb-2">Pre-Interview Confirmation</p>
                            <Rule icon={CalendarCheck} title="Default timing" text="1 day before interview · configurable 1–7 days" />
                            <Rule icon={ArrowClockwise} title="Retry" text="One retry +60 min if no-answer" />
                            <Rule icon={MapPin} title="Calling window" text="10:00–19:00 IST" />
                        </div>
                        <div className="border border-[#e5e3d8] rounded-xl p-3" data-testid="live-workflow-missed">
                            <p className="text-sm font-bold text-rose-800 mb-2">Missed-Interview Follow-up (OTP-based)</p>
                            <Rule icon={Alarm} title="Default timing" text="1 hour after interview · configurable 1h–7 days" />
                            <Rule icon={ArrowClockwise} title="Retry" text="One retry +30 min if no-answer" />
                            <Rule icon={MapPin} title="Calling window" text="10:00–19:30 IST · OTP re-checked before every attempt" />
                        </div>
                    </div>
                    <p className="text-[11px] text-[#9b9787] mt-3">Normal operation does NOT require manual Call Now. The scheduler handles eligible candidates automatically once every safety gate permits it.</p>
                </Card>

                <button disabled data-testid="live-activate-btn" title="Locked in this phase" className="px-5 py-2.5 rounded-lg bg-rose-700 text-white text-sm font-semibold opacity-40 cursor-not-allowed flex items-center gap-2">
                    <Lock size={16} /> Activate Live Mode (locked)
                </button>

                <div className="flex gap-2 overflow-x-auto" role="tablist">
                    {[['eligible', 'Eligible Candidates', UserCircle], ['queue', 'Automatic Calling Queue', Queue], ['preview', 'Preview & Diagnostics', Eye]].map(([k, l, Icon]) => (
                        <button key={k} role="tab" aria-selected={tab === k} onClick={() => setTab(k)} data-testid={`live-tab-${k}`}
                            className={`px-4 py-2 rounded-lg text-sm font-semibold border whitespace-nowrap flex items-center gap-1 ${tab === k ? 'bg-teal-700 text-white border-teal-700' : 'bg-white border-[#e5e3d8] text-[#1a2332]'}`}>
                            <Icon size={14} /> {l}
                        </button>
                    ))}
                </div>

                {tab === 'eligible' ? <RealBookingsPreview />
                 : tab === 'queue' ? <LivePrepPanel />
                 : <><PreviewScenariosPanel /><DryRunPreview /></>}
            </main>
        </div>
    );
}
