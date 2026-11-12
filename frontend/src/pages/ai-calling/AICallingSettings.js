import { useEffect, useState } from 'react';
import { toast } from 'sonner';
import { GearSix } from '@phosphor-icons/react';
import { aiApi, errMsg } from './aiApi';
import { AICallingHeader, Card, SectionTitle } from '../../components/ai-calling/AICallingHeader';
import { BolnaConfigPanel } from '../../components/ai-calling/BolnaConfigPanel';
import { ModeSwitchesPanel } from '../../components/ai-calling/ModeSwitchesPanel';
import { SafetyControlsPanel } from '../../components/ai-calling/SafetyControlsPanel';
import { CapacitySummaryPanel } from '../../components/ai-calling/CapacitySummaryPanel';
import { CandidateConsentSection } from '../../components/ai-calling/CandidateConsentSection';
import { RetentionPanel } from '../../components/ai-calling/RetentionPanel';
import { SchedulingPanel } from '../../components/ai-calling/SchedulingPanel';
import { useSafetyStatus } from '../../components/ai-calling/useSafetyStatus';

const inputCls = 'w-full bg-white border border-[#e5e3d8] rounded-lg px-3 py-2.5 text-sm focus:outline-none focus:border-teal-500';
const FIELDS = [
    ['daily_call_limit', 'Daily test call limit', 'number'],
    ['max_concurrent_calls', 'Max concurrent calls', 'number'],
    ['call_window_start', 'Call window start', 'time'],
    ['call_window_end', 'Call window end', 'time'],
    ['default_company_name', 'Default company name', 'text'],
    ['default_office_address', 'Default office address', 'text'],
];

export default function AICallingSettings() {
    const [, setS] = useState(null);
    const [f, setF] = useState({});
    const { safety, loading, refresh } = useSafetyStatus();
    const apply = (d) => { setS(d); setF(Object.fromEntries(FIELDS.map(([k]) => [k, d[k] ?? '']))); };
    useEffect(() => { aiApi.get('/settings').then(r => apply(r.data)).catch(e => toast.error(errMsg(e))); }, []);

    const save = async () => {
        const body = { ...f, daily_call_limit: Number(f.daily_call_limit), max_concurrent_calls: Number(f.max_concurrent_calls) };
        try { apply((await aiApi.put('/settings', body)).data); toast.success('Settings saved'); } catch (e) { toast.error(errMsg(e)); }
    };

    return (
        <div className="min-h-screen" data-testid="ai-settings-page">
            <AICallingHeader title="AI Calling Settings" subtitle="Safety controls, limits, defaults and provider configuration" />
            <main className="max-w-6xl mx-auto px-6 lg:px-10 py-6 space-y-5">
                <SafetyControlsPanel safety={safety} loading={loading} onChanged={refresh} />
                <ModeSwitchesPanel />
                <Card>
                    <SectionTitle icon={GearSix}>Limits & defaults</SectionTitle>
                    <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-3">
                        {FIELDS.map(([k, label, type]) => (
                            <label key={k} className="block">
                                <span className="text-[11px] font-semibold tracking-[0.16em] text-[#9b9787] uppercase block mb-1">{label}</span>
                                <input type={type} value={f[k] ?? ''} onChange={e => setF(p => ({ ...p, [k]: e.target.value }))} data-testid={`setting-${k}`} className={inputCls} />
                            </label>
                        ))}
                    </div>
                    <div className="flex justify-end mt-4"><button onClick={save} data-testid="settings-save-btn" className="px-5 py-2.5 rounded-lg bg-teal-700 hover:bg-teal-800 text-white text-sm font-semibold">Save settings</button></div>
                </Card>
                <BolnaConfigPanel />
                <CapacitySummaryPanel />
                <SchedulingPanel />
                <CandidateConsentSection />
                <RetentionPanel />
            </main>
        </div>
    );
}
